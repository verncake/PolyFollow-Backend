"""
Base HTTP client for Polymarket APIs.

Provides retry logic, rate limiting, and error handling for all API clients.
"""
import httpx
from typing import Optional, Any
import asyncio
import random
import time


# Exponential backoff retry settings
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_MULTIPLIER = 2.0
MAX_BACKOFF = 60.0  # seconds - cap to prevent excessive waits
JITTER_FACTOR = 0.3  # ±30% randomization to prevent thundering herd


class PolymarketAPIError(Exception):
    """Custom exception for Polymarket API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter using a sliding window counter.

    Tracks request counts per host within a time window to proactively
    avoid hitting rate limits.
    """

    def __init__(self, requests_per_second: int = 10, window_seconds: float = 1.0):
        self.requests_per_second = requests_per_second
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def _get_key(self, host: str) -> str:
        return host.lower()

    def _cleanup_old_requests(self, key: str, now: float) -> None:
        """Remove requests outside the current window."""
        if key in self._requests:
            self._requests[key] = [
                t for t in self._requests[key] if now - t < self.window_seconds
            ]

    async def acquire(self, host: str) -> float:
        """
        Acquire permission to make a request.

        If rate limit would be exceeded, waits until it's safe.

        Args:
            host: The host to rate limit per

        Returns:
            Time waited in seconds (0 if no wait needed)
        """
        key = self._get_key(host)
        now = time.monotonic()

        self._cleanup_old_requests(key, now)

        request_count = len(self._requests.get(key, []))
        wait_time = 0.0

        if request_count >= self.requests_per_second:
            # Calculate how long until oldest request in window expires
            oldest = self._requests[key][0] if self._requests[key] else now
            wait_time = (oldest + self.window_seconds) - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                now = time.monotonic()
                self._cleanup_old_requests(key, now)

        # Record this request
        if key not in self._requests:
            self._requests[key] = []
        self._requests[key].append(now)

        return wait_time

    def reset(self, host: Optional[str] = None) -> None:
        """Reset rate limit tracking for a host, or all hosts if None."""
        if host is None:
            self._requests.clear()
        else:
            key = self._get_key(host)
            self._requests.pop(key, None)


# Global rate limiter instance (10 req/s is conservative for Polymarket)
_global_rate_limiter: Optional[InMemoryRateLimiter] = None


def get_rate_limiter() -> InMemoryRateLimiter:
    """Get the global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = InMemoryRateLimiter(requests_per_second=10)
    return _global_rate_limiter


def set_rate_limiter(limiter: InMemoryRateLimiter) -> None:
    """Set a custom rate limiter (for testing)."""
    global _global_rate_limiter
    _global_rate_limiter = limiter


class BasePolymarketClient:
    """
    Base async client with retry logic and error handling.
    All other clients inherit from this class.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request_with_retry(
        self, method: str, url: str, **kwargs
    ) -> dict[str, Any] | list:
        """
        Make an HTTP request with exponential backoff retry.

        Features:
        - Exponential backoff with jitter to prevent thundering herd
        - Respects Retry-After header on 429 responses
        - Proactive rate limiting via in-memory rate limiter

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            **kwargs: Additional arguments to pass to httpx request

        Returns:
            Response JSON as dict or list

        Raises:
            PolymarketAPIError: If all retries fail or response is not 2xx
        """
        client = await self._get_client()
        rate_limiter = get_rate_limiter()

        # Parse host for rate limiting
        parsed_url = httpx.URL(url)
        host = parsed_url.host or ""

        backoff = INITIAL_BACKOFF
        last_error: Exception = Exception("Unknown error")

        for attempt in range(MAX_RETRIES):
            # Proactive rate limiting - wait if we're going too fast
            await rate_limiter.acquire(host)

            try:
                response = await client.request(method, url, **kwargs)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited - determine wait time
                    last_error = PolymarketAPIError(
                        "Rate limited by Polymarket API",
                        status_code=429,
                    )
                    # Try to get Retry-After header first
                    retry_after = response.headers.get("retry-after")
                    if retry_after:
                        try:
                            # Could be seconds or HTTP date
                            if retry_after.isdigit():
                                backoff = float(retry_after)
                            else:
                                # HTTP date - calculate seconds until that time
                                from email.utils import parsedate_to_datetime
                                retry_time = parsedate_to_datetime(retry_after)
                                backoff = max(0.1, (retry_time - __import__('datetime').datetime.now(retry_time.tzinfo)).total_seconds())
                        except (ValueError, TypeError):
                            pass  # Use exponential backoff fallback
                elif response.status_code >= 500:
                    # Server error - retry
                    last_error = PolymarketAPIError(
                        f"Polymarket server error: {response.status_code}",
                        status_code=response.status_code,
                    )
                else:
                    # Client error (400, 404, etc.) - don't retry, raise immediately
                    raise PolymarketAPIError(
                        f"API request failed: {response.status_code}",
                        status_code=response.status_code,
                    )

            except httpx.TimeoutException as e:
                last_error = PolymarketAPIError(f"Request timeout: {e}")
            except httpx.HTTPError as e:
                last_error = PolymarketAPIError(f"HTTP error: {e}")

            if attempt < MAX_RETRIES - 1:
                # Add jitter: ±JITTER_FACTOR to prevent thundering herd
                jitter = backoff * JITTER_FACTOR * (2 * random.random() - 1)
                sleep_time = min(backoff + jitter, MAX_BACKOFF)
                await asyncio.sleep(sleep_time)
                backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)

        raise last_error

    def _build_url(self, path: str) -> str:
        """Build full URL from base URL and path."""
        return f"{self.base_url}{path}"
