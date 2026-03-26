"""
Redis queue operations for Follow-Alpha order processing.

Uses Upstash Redis for:
- ORDER_QUEUE (List): task queue with LPUSH/BRPOP
- TASK_CACHE (Hash): task deduplication and status tracking
"""
from upstash_redis.asyncio import Redis
from typing import Optional
import json
import os

from app.schemas.task import TradeTask

# Redis key constants
ORDER_QUEUE = "ORDER_QUEUE"
TASK_CACHE = "TASK_CACHE"

# Async Redis client singleton
_async_redis_client: Optional[Redis] = None


def _get_async_redis() -> Redis:
    """
    Returns the singleton async Redis client instance.
    """
    global _async_redis_client

    if _async_redis_client is None:
        url = os.getenv("UPSTASH_REDIS_REST_URL", "")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

        if not url or not token:
            raise RuntimeError(
                "Missing Upstash Redis configuration. "
                "Please set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN in .env"
            )

        _async_redis_client = Redis(url=url, token=token)

    return _async_redis_client


async def push_task(queue_name: str, task: TradeTask) -> bool:
    """
    Push a TradeTask to the specified Redis queue.

    Args:
        queue_name: Name of the queue (e.g., ORDER_QUEUE)
        task: TradeTask to enqueue

    Returns:
        True if successfully pushed, False otherwise
    """
    try:
        redis = _get_async_redis()
        json_data = task.model_dump_json()
        # LPUSH returns the new length of the queue
        await redis.lpush(queue_name, json_data)
        return True
    except Exception:
        return False


async def pop_task(queue_name: str, timeout: int = 0) -> Optional[TradeTask]:
    """
    Blocking pop a TradeTask from the specified Redis queue.
    Checks TASK_CACHE for idempotency before returning.

    Args:
        queue_name: Name of the queue to pop from
        timeout: Blocking timeout in seconds (0 = block indefinitely)

    Returns:
        TradeTask if available, None if empty or already processed
    """
    redis = _get_async_redis()

    # BRPOP returns (key, value) tuple or None if timeout
    result = await redis.brpop(queue_name, timeout=timeout)
    if result is None:
        return None

    _, json_data = result

    try:
        task_dict = json.loads(json_data)
    except (json.JSONDecodeError, TypeError):
        return None

    # Idempotency check: skip if already processed
    task_id = task_dict.get("task_id")
    if task_id and await is_task_processed(task_id):
        return None

    try:
        return TradeTask(**task_dict)
    except Exception:
        return None


async def get_task(task_id: str) -> Optional[TradeTask]:
    """
    Retrieve a task from TASK_CACHE by task_id.

    Args:
        task_id: The unique task identifier

    Returns:
        TradeTask if found in cache, None otherwise
    """
    redis = _get_async_redis()
    try:
        json_data = await redis.hget(TASK_CACHE, task_id)
        if json_data is None:
            return None
        task_dict = json.loads(json_data)
        return TradeTask(**task_dict)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


async def ack_task(task_id: str) -> bool:
    """
    Mark a task as completed by storing it in TASK_CACHE.
    Uses HSET to store the task data with its task_id as key.

    Args:
        task_id: The unique task identifier

    Returns:
        True if successfully acknowledged, False otherwise
    """
    redis = _get_async_redis()
    try:
        # Store task status as "completed" in the hash
        await redis.hset(TASK_CACHE, task_id, "completed")
        return True
    except Exception:
        return False


async def is_task_processed(task_id: str) -> bool:
    """
    Check if a task has already been processed.
    Looks up task_id in TASK_CACHE hash.

    Args:
        task_id: The unique task identifier

    Returns:
        True if task exists in TASK_CACHE (already processed), False otherwise
    """
    redis = _get_async_redis()
    try:
        exists = await redis.hexists(TASK_CACHE, task_id)
        return bool(exists)
    except Exception:
        return False


async def store_task_result(task_id: str, result: str) -> bool:
    """
    Store a task execution result in TASK_CACHE.

    Args:
        task_id: The unique task identifier
        result: JSON string with execution result

    Returns:
        True if successfully stored, False otherwise
    """
    redis = _get_async_redis()
    try:
        await redis.hset(TASK_CACHE, task_id, result)
        return True
    except Exception:
        return False
