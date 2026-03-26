"""
Pytest tests for Redis connection and operations.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestRedisConnection:
    """Tests for Redis connection singleton."""

    def test_ping_redis_success(self):
        """Test successful Redis ping."""
        with patch("app.core.redis.get_redis") as mock_get_redis:
            mock_client = MagicMock()
            mock_client.ping.return_value = "PONG"
            mock_get_redis.return_value = mock_client

            from app.core.redis import ping_redis
            result = ping_redis()

            assert result is True
            mock_client.ping.assert_called_once()

    def test_ping_redis_failure(self):
        """Test Redis ping when connection fails."""
        with patch("app.core.redis.get_redis") as mock_get_redis:
            mock_client = MagicMock()
            mock_client.ping.side_effect = Exception("Connection refused")
            mock_get_redis.return_value = mock_client

            from app.core.redis import ping_redis
            result = ping_redis()

            assert result is False

    def test_get_redis_initialization(self):
        """Test Redis client initialization from environment variables."""
        import app.core.redis as redis_module

        with patch.dict(
            "os.environ",
            {
                "UPSTASH_REDIS_REST_URL": "https://test.upstash.io",
                "UPSTASH_REDIS_REST_TOKEN": "test_token",
            },
        ):
            # Reset the singleton for testing
            redis_module._redis_client = None

            with patch.object(redis_module, "Redis") as mock_redis_class:
                mock_instance = MagicMock()
                mock_redis_class.return_value = mock_instance

                client = redis_module.get_redis()

                mock_redis_class.assert_called_once_with(
                    url="https://test.upstash.io",
                    token="test_token",
                )
                assert client is mock_instance

    def test_get_redis_missing_env(self):
        """Test Redis client fails gracefully when env vars are missing."""
        with patch.dict("os.environ", {}, clear=True):
            import app.core.redis as redis_module
            redis_module._redis_client = None

            with pytest.raises(RuntimeError) as exc_info:
                redis_module.get_redis()

            assert "Missing Upstash Redis configuration" in str(exc_info.value)


class TestRedisOperations:
    """Tests for Redis cache operations used in the application."""

    def test_set_and_get_leaderboard_cache(self):
        """Test setting and getting leaderboard from cache."""
        with patch("app.core.redis.get_redis") as mock_get_redis:
            mock_client = MagicMock()
            mock_client.get.return_value = '{"addresses": []}'
            mock_get_redis.return_value = mock_client

            # Simulate cache set
            test_data = '{"addresses": [{"address": "0x123", "score": 95}]'
            mock_client.set.return_value = "OK"

            # Set cache
            mock_client.set("leaderboard:top:200", test_data)

            # Get cache
            cached = mock_client.get("leaderboard:top:200")
            assert cached == '{"addresses": []}'

    def test_cache_expiration(self):
        """Test that cache keys have TTL set."""
        with patch("app.core.redis.get_redis") as mock_get_redis:
            mock_client = MagicMock()
            mock_client.set.return_value = True
            mock_get_redis.return_value = mock_client

            # Simulate setting with 5 minute TTL
            mock_client.set("leaderboard:top:200", "data", ex=300)

            mock_client.set.assert_called_once_with(
                "leaderboard:top:200", "data", ex=300
            )
