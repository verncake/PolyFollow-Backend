"""
Upstash Redis connection singleton for the Polymarket Follow-Alpha system.
"""
from datetime import datetime
from upstash_redis import Redis
from typing import Optional
import json
import os
import uuid


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


def store_pnl_history(redis: Redis, address: str, period: str, data_points: list[dict], ttl_seconds: int = 86400) -> None:
    """
    Store PnL history data points in Redis sorted set.

    Uses ZADD with timestamp as score for efficient time-range queries.
    Each data point: {timestamp, cumulative_pnl, position_count}

    Args:
        redis: Redis client instance
        address: Wallet address
        period: Time period (1d, 1w, 1m, 6m, 1y)
        data_points: List of {timestamp, cumulative_pnl, position_count}
        ttl_seconds: TTL for the key (default 24 hours for 1d, longer for longer periods)
    """
    key = f"pnl:history:{address.lower()}:{period}"
    if not data_points:
        return

    # Delete existing key first
    redis.delete(key)

    # Add all data points with ZADD
    for point in data_points:
        timestamp = point["timestamp"]
        value = json.dumps({
            "cumulative_pnl": point["cumulative_pnl"],
            "position_count": point.get("position_count", 0),
        })
        redis.zadd(key, {value: float(timestamp)})

    # Set TTL
    redis.expire(key, ttl_seconds)


def get_pnl_history(
    redis: Redis,
    address: str,
    period: str,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
) -> list[dict]:
    """
    Get PnL history data points from Redis sorted set.

    Args:
        redis: Redis client instance
        address: Wallet address
        period: Time period (1d, 1w, 1m, 6m, 1y)
        start_ts: Start timestamp (unix epoch), optional
        end_ts: End timestamp (unix epoch), optional

    Returns:
        List of {timestamp, cumulative_pnl, position_count}
    """
    key = f"pnl:history:{address.lower()}:{period}"

    # Get all members with scores in range
    if start_ts is not None and end_ts is not None:
        # ZRANGEBYSCORE with scores
        results = redis.zrangebyscore(
            key,
            min=float(start_ts),
            max=float(end_ts),
            withscores=True,
        )
    else:
        # Get all
        results = redis.zrange(key, withscores=True)

    data_points = []
    for member, score in results:
        try:
            data = json.loads(member)
            data_points.append({
                "timestamp": int(score),
                "cumulative_pnl": data["cumulative_pnl"],
                "position_count": data.get("position_count", 0),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    # Sort by timestamp
    data_points.sort(key=lambda x: x["timestamp"])

    return data_points


def get_pnl_history_ttl_seconds(period: str) -> int:
    """
    Get TTL in seconds for a given period.

    Args:
        period: Time period (1d, 1w, 1m, 6m, 1y)

    Returns:
        TTL in seconds
    """
    ttl_map = {
        "1d": 86400,      # 24 hours
        "1w": 604800,     # 7 days
        "1m": 2592000,    # 30 days
        "6m": 15552000,   # 180 days
        "1y": 31536000,   # 365 days
    }
    return ttl_map.get(period, 86400)


# Distributed Lock for sync operations
SYNC_LOCK_PREFIX = "sync:lock:"
SYNC_LOCK_TTL_SECONDS = 300  # 5 minutes


class SyncLock:
    """Redis-based distributed lock for sync operations."""

    def __init__(self, redis: Redis, address: str, ttl: int = SYNC_LOCK_TTL_SECONDS):
        self.redis = redis
        self.address = address.lower()
        self.key = f"{SYNC_LOCK_PREFIX}{self.address}"
        self.ttl = ttl
        self.lock_id = str(uuid.uuid4())

    def acquire(self) -> bool:
        """
        Attempt to acquire the lock using SET NX with TTL.

        Returns:
            True if lock acquired, False if already held by another process
        """
        # SET key value NX EX ttl - only sets if key doesn't exist
        result = self.redis.set(self.key, self.lock_id, nx=True, ex=self.ttl)
        return result is not None

    def release(self) -> bool:
        """
        Release the lock if we own it.

        Uses Lua script to atomically check and delete only if we own the lock.

        Returns:
            True if lock was released, False if we didn't own it
        """
        # Lua script to atomically check lock ownership and delete
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = self.redis.eval(lua_script, [self.key], [self.lock_id])
        return result == 1

    def extend(self, additional_seconds: int = None) -> bool:
        """
        Extend the lock TTL if we own it.

        Args:
            additional_seconds: Additional TTL to add. Defaults to original TTL.

        Returns:
            True if lock was extended, False if we didn't own it
        """
        if additional_seconds is None:
            additional_seconds = self.ttl

        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = self.redis.eval(
            lua_script,
            [self.key],
            [self.lock_id, additional_seconds]
        )
        return result == 1

    def is_locked(self) -> bool:
        """Check if the lock is currently held (by any process)."""
        return self.redis.exists(self.key) == 1


def acquire_sync_lock(address: str, ttl: int = SYNC_LOCK_TTL_SECONDS) -> Optional[SyncLock]:
    """
    Attempt to acquire a distributed sync lock for an address.

    Args:
        address: Wallet address to lock
        ttl: Lock TTL in seconds (default 5 minutes)

    Returns:
        SyncLock instance if acquired, None if lock is held by another process
    """
    redis = get_redis()
    sync_lock = SyncLock(redis, address, ttl)
    if sync_lock.acquire():
        return sync_lock
    return None


def release_sync_lock(address: str) -> bool:
    """
    Release a distributed sync lock for an address.

    Note: This only releases the lock if we own it. Uses a fresh lock instance
    to match the lock_id that was used when acquiring.

    Args:
        address: Wallet address to unlock

    Returns:
        True if lock was released, False otherwise
    """
    redis = get_redis()
    sync_lock = SyncLock(redis, address)
    return sync_lock.release()


# ========== Sync Status Tracking ==========

SYNC_STATUS_PREFIX = "sync:status:"
SYNC_STATUS_TTL_SECONDS = 3600  # 1 hour


def set_sync_status(
    address: str,
    status: str,
    progress_percent: int = 0,
    estimated_seconds_remaining: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """
    Store sync status in Redis for polling.

    Args:
        address: Wallet address
        status: One of "pending", "syncing", "completed", "failed"
        progress_percent: Progress from 0-100
        estimated_seconds_remaining: Estimated time until completion
        error: Error message if status is "failed"
    """
    redis = get_redis()
    key = f"{SYNC_STATUS_PREFIX}{address.lower()}"
    data = {
        "status": status,
        "progress_percent": progress_percent,
        "estimated_seconds_remaining": estimated_seconds_remaining,
        "error": error,
    }
    redis.set(key, json.dumps(data), ex=SYNC_STATUS_TTL_SECONDS)


def get_sync_status(address: str) -> Optional[dict]:
    """
    Get sync status from Redis.

    Args:
        address: Wallet address

    Returns:
        Dict with status info, or None if not found
    """
    redis = get_redis()
    key = f"{SYNC_STATUS_PREFIX}{address.lower()}"
    data = redis.get(key)
    if data:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None
    return None


SYNC_LAST_UPDATED_PREFIX = "sync:last_updated:"
SYNC_LAST_UPDATED_TTL_SECONDS = 86400  # 24 hours


def set_sync_last_updated(address: str) -> None:
    """
    Store the last updated timestamp for a sync in Redis.

    Args:
        address: Wallet address
    """
    redis = get_redis()

    redis = get_redis()
    key = f"{SYNC_LAST_UPDATED_PREFIX}{address.lower()}"
    data = {
        "last_updated": datetime.utcnow().isoformat(),
    }
    redis.set(key, json.dumps(data), ex=SYNC_LAST_UPDATED_TTL_SECONDS)


def get_sync_last_updated(address: str) -> Optional[str]:
    """
    Get the last updated timestamp for a sync from Redis.

    Args:
        address: Wallet address

    Returns:
        ISO timestamp string, or None if not found
    """
    redis = get_redis()
    key = f"{SYNC_LAST_UPDATED_PREFIX}{address.lower()}"
    data = redis.get(key)
    if data:
        try:
            parsed = json.loads(data)
            return parsed.get("last_updated")
        except json.JSONDecodeError:
            return None
    return None
