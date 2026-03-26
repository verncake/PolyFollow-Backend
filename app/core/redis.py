"""
Upstash Redis connection singleton for the Polymarket Follow-Alpha system.
"""
from upstash_redis import Redis
from typing import Optional
import os


_redis_client: Optional[Redis] = None


def get_redis() -> Redis:
    """
    Returns the singleton Redis client instance.
    Initializes connection on first call using environment variables.
    """
    global _redis_client

    if _redis_client is None:
        upstash_url = os.getenv("UPSTASH_REDIS_REST_URL")
        upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

        if not upstash_url or not upstash_token:
            raise RuntimeError(
                "Missing Upstash Redis configuration. "
                "Please set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN in .env"
            )

        _redis_client = Redis(
            url=upstash_url,
            token=upstash_token,
        )

    return _redis_client


def ping_redis() -> bool:
    """
    Test Redis connection with PING command.
    Returns True if connection is healthy.
    """
    try:
        client = get_redis()
        result = client.ping()
        return result == "PONG"
    except Exception:
        return False


async def close_redis():
    """
    Close Redis connection. No-op for upstash_redis as it doesn't maintain persistent connections.
    Kept for API compatibility.
    """
    global _redis_client
    _redis_client = None
