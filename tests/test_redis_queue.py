"""
Pytest tests for Redis queue operations (Follow-Alpha).
"""
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock

from app.schemas.task import TradeTask


class TestTradeTaskSchema:
    """Tests for TradeTask Pydantic model."""

    def test_trade_task_creation(self):
        """Test TradeTask can be created with required fields."""
        task = TradeTask(
            user_id="user_123",
            target_address="0x742d35Cc6634C0532925a3b844Bc9e7595f",
            market_id="abc123_condition_id",
            outcome="Yes",
            amount_usdc="10.5",
        )

        assert task.user_id == "user_123"
        assert task.target_address == "0x742d35Cc6634C0532925a3b844Bc9e7595f"
        assert task.market_id == "abc123_condition_id"
        assert task.outcome == "Yes"
        assert task.amount_usdc == "10.5"
        assert task.task_id is not None
        assert task.created_at is not None

    def test_trade_task_outcome_pattern(self):
        """Test TradeTask outcome must be 'Yes' or 'No'."""
        task_yes = TradeTask(
            user_id="user_1",
            target_address="0x123",
            market_id="market_1",
            outcome="Yes",
            amount_usdc="10",
        )
        assert task_yes.outcome == "Yes"

        task_no = TradeTask(
            user_id="user_1",
            target_address="0x123",
            market_id="market_1",
            outcome="No",
            amount_usdc="10",
        )
        assert task_no.outcome == "No"

    def test_trade_task_invalid_outcome(self):
        """Test TradeTask rejects invalid outcome values."""
        with pytest.raises(ValueError):
            TradeTask(
                user_id="user_1",
                target_address="0x123",
                market_id="market_1",
                outcome="Invalid",
                amount_usdc="10",
            )

    def test_trade_task_json_serialization(self):
        """Test TradeTask JSON serialization/deserialization."""
        task = TradeTask(
            task_id="fixed-task-id",
            user_id="user_123",
            target_address="0x742d35Cc6634C0532925a3b844Bc9e7595f",
            market_id="abc123_condition_id",
            outcome="Yes",
            amount_usdc="10.5",
            price_limit="0.6",
            created_at="2026-03-26T10:00:00Z",
        )

        json_str = task.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["task_id"] == "fixed-task-id"
        assert parsed["user_id"] == "user_123"
        assert parsed["outcome"] == "Yes"
        assert parsed["price_limit"] == "0.6"

    def test_trade_task_default_values(self):
        """Test TradeTask default values are generated."""
        task = TradeTask(
            user_id="user_1",
            target_address="0x123",
            market_id="market_1",
            outcome="No",
            amount_usdc="5",
        )

        assert task.task_id is not None
        assert len(task.task_id) == 36  # UUID format
        assert task.created_at is not None
        assert task.price_limit is None


class TestRedisQueueOperations:
    """Tests for Redis queue operations with mocked Redis client."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mocked async Redis client."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_push_task_success(self, mock_redis):
        """Test successfully pushing a task to the queue."""
        mock_redis.lpush = AsyncMock(return_value=1)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import push_task

            task = TradeTask(
                user_id="user_1",
                target_address="0x123",
                market_id="market_1",
                outcome="Yes",
                amount_usdc="10",
            )

            result = await push_task("ORDER_QUEUE", task)

            assert result is True
            mock_redis.lpush.assert_called_once()
            call_args = mock_redis.lpush.call_args
            assert call_args[0][0] == "ORDER_QUEUE"
            # Verify the second arg is a JSON string
            json_data = call_args[0][1]
            parsed = json.loads(json_data)
            assert parsed["user_id"] == "user_1"

    @pytest.mark.asyncio
    async def test_push_task_failure(self, mock_redis):
        """Test push_task returns False on Redis error."""
        mock_redis.lpush = AsyncMock(side_effect=Exception("Redis error"))

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import push_task

            task = TradeTask(
                user_id="user_1",
                target_address="0x123",
                market_id="market_1",
                outcome="Yes",
                amount_usdc="10",
            )

            result = await push_task("ORDER_QUEUE", task)

            assert result is False

    @pytest.mark.asyncio
    async def test_is_task_processed_exists(self, mock_redis):
        """Test is_task_processed returns True when task exists."""
        mock_redis.hexists = AsyncMock(return_value=True)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import is_task_processed

            result = await is_task_processed("task-123")
            assert result is True
            mock_redis.hexists.assert_called_with("TASK_CACHE", "task-123")

    @pytest.mark.asyncio
    async def test_is_task_processed_not_exists(self, mock_redis):
        """Test is_task_processed returns False when task does not exist."""
        mock_redis.hexists = AsyncMock(return_value=False)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import is_task_processed

            result = await is_task_processed("task-123")
            assert result is False

    @pytest.mark.asyncio
    async def test_ack_task_success(self, mock_redis):
        """Test ack_task successfully marks task as completed."""
        mock_redis.hset = AsyncMock(return_value=True)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import ack_task

            result = await ack_task("task-123")
            assert result is True
            mock_redis.hset.assert_called_with("TASK_CACHE", "task-123", "completed")

    @pytest.mark.asyncio
    async def test_get_task_success(self, mock_redis):
        """Test get_task retrieves a stored task."""
        task_json = json.dumps({
            "task_id": "task-123",
            "user_id": "user_1",
            "target_address": "0x123",
            "market_id": "market_1",
            "outcome": "Yes",
            "amount_usdc": "10",
            "created_at": "2026-03-26T10:00:00Z",
        })
        mock_redis.hget = AsyncMock(return_value=task_json)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import get_task

            result = await get_task("task-123")

            assert result is not None
            assert result.task_id == "task-123"
            assert result.user_id == "user_1"
            assert result.outcome == "Yes"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, mock_redis):
        """Test get_task returns None when task not in cache."""
        mock_redis.hget = AsyncMock(return_value=None)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import get_task

            result = await get_task("nonexistent-task")
            assert result is None

    @pytest.mark.asyncio
    async def test_pop_task_success(self, mock_redis):
        """Test pop_task retrieves a task from queue."""
        task_json = json.dumps({
            "task_id": "task-456",
            "user_id": "user_2",
            "target_address": "0x456",
            "market_id": "market_2",
            "outcome": "No",
            "amount_usdc": "20",
            "created_at": "2026-03-26T11:00:00Z",
        })
        mock_redis.brpop = AsyncMock(return_value=("ORDER_QUEUE", task_json))
        mock_redis.hexists = AsyncMock(return_value=False)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import pop_task

            result = await pop_task("ORDER_QUEUE", timeout=5)

            assert result is not None
            assert result.task_id == "task-456"
            assert result.user_id == "user_2"
            assert result.outcome == "No"

    @pytest.mark.asyncio
    async def test_pop_task_empty_queue(self, mock_redis):
        """Test pop_task returns None when queue is empty."""
        mock_redis.brpop = AsyncMock(return_value=None)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import pop_task

            result = await pop_task("ORDER_QUEUE", timeout=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_pop_task_skips_processed(self, mock_redis):
        """Test pop_task skips tasks already in TASK_CACHE (idempotency)."""
        task_json = json.dumps({
            "task_id": "task-already-done",
            "user_id": "user_1",
            "target_address": "0x123",
            "market_id": "market_1",
            "outcome": "Yes",
            "amount_usdc": "10",
            "created_at": "2026-03-26T10:00:00Z",
        })
        mock_redis.brpop = AsyncMock(return_value=("ORDER_QUEUE", task_json))
        mock_redis.hexists = AsyncMock(return_value=True)  # Task already processed

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import pop_task

            result = await pop_task("ORDER_QUEUE", timeout=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_pop_task_invalid_json(self, mock_redis):
        """Test pop_task returns None for invalid JSON data."""
        mock_redis.brpop = AsyncMock(return_value=("ORDER_QUEUE", "not valid json"))
        mock_redis.hexists = AsyncMock(return_value=False)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import pop_task

            result = await pop_task("ORDER_QUEUE", timeout=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_store_task_result_success(self, mock_redis):
        """Test store_task_result stores execution result."""
        mock_redis.hset = AsyncMock(return_value=True)

        with patch("app.core.redis_queue._get_async_redis", return_value=mock_redis):
            from app.core.redis_queue import store_task_result

            result_json = json.dumps({"status": "success", "order_id": "order-123"})
            result = await store_task_result("task-789", result_json)

            assert result is True
            mock_redis.hset.assert_called_with("TASK_CACHE", "task-789", result_json)
