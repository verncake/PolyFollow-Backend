"""
Base HTTP client for Polymarket APIs.

Provides retry logic and error handling for all API clients.
"""
import httpx
from typing import Optional, Any
import asyncio
import os


# Exponential backoff retry settings
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_MULTIPLIER = 2.0


class PolymarketAPIError(Exception):
    """Custom exception for Polymarket API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


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
        backoff = INITIAL_BACKOFF

        last_error: Exception = Exception("Unknown error")

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.request(method, url, **kwargs)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited - retry with backoff
                    last_error = PolymarketAPIError(
                        "Rate limited by Polymarket API",
                        status_code=429,
                    )
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
                await asyncio.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER

        raise last_error

    def _build_url(self, path: str) -> str:
        """Build full URL from base URL and path."""
        return f"{self.base_url}{path}"
