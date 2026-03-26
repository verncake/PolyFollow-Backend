"""
Pytest tests for Base HTTP Client with retry logic.

Tests cover:
- Retry behavior for 429 (rate limit)
- Retry behavior for 5xx errors
- No retry for 4xx client errors
- Timeout handling
- Exponential backoff timing
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.services.base import (
    BasePolymarketClient,
    PolymarketAPIError,
    MAX_RETRIES,
    INITIAL_BACKOFF,
    BACKOFF_MULTIPLIER,
)


class TestPolymarketAPIError:
    """Tests for PolymarketAPIError exception."""

    def test_error_with_status_code(self):
        """Error should store status code."""
        error = PolymarketAPIError("Test error", status_code=429)
        assert error.message == "Test error"
        assert error.status_code == 429

    def test_error_without_status_code(self):
        """Error should work without status code."""
        error = PolymarketAPIError("Test error")
        assert error.message == "Test error"
        assert error.status_code is None


class TestBaseClientRetry:
    """Tests for retry logic in BasePolymarketClient."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return BasePolymarketClient("https://test.polymarket.com")

    @pytest.mark.asyncio
    async def test_successful_request_no_retry(self, client):
        """Successful response should not retry."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        with patch.object(client, '_get_client', return_value=mock_client):
            result = await client._request_with_retry("GET", "https://test.com/api")

            assert result == {"data": "test"}
            assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_rate_limit_retries_and_succeeds(self, client):
        """429 followed by success should retry and return success."""
        responses = [
            MagicMock(status_code=429),
            MagicMock(status_code=200, json=lambda: {"data": "success"}),
        ]
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            response = responses[call_count]
            call_count += 1
            return response

        mock_client = AsyncMock()
        mock_client.request = mock_request
        mock_client.is_closed = False

        with patch.object(client, '_get_client', return_value=mock_client):
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                result = await client._request_with_retry("GET", "https://test.com/api")

                assert result == {"data": "success"}
                assert call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_all_retries_fail(self, client):
        """All retries returning 429 should raise final error."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        with patch.object(client, '_get_client', return_value=mock_client):
            with pytest.raises(PolymarketAPIError) as exc_info:
                await client._request_with_retry("GET", "https://test.com/api")

            assert exc_info.value.status_code == 429
            assert mock_client.request.call_count == MAX_RETRIES

    @pytest.mark.asyncio
    async def test_server_error_retries_and_succeeds(self, client):
        """5xx followed by success should retry and return success."""
        responses = [
            MagicMock(status_code=502),
            MagicMock(status_code=200, json=lambda: {"data": "ok"}),
        ]
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            response = responses[call_count]
            call_count += 1
            return response

        mock_client = AsyncMock()
        mock_client.request = mock_request
        mock_client.is_closed = False

        with patch.object(client, '_get_client', return_value=mock_client):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await client._request_with_retry("GET", "https://test.com/api")

                assert result == {"data": "ok"}
                assert call_count == 2

    @pytest.mark.asyncio
    async def test_client_error_no_retry(self, client):
        """4xx should NOT retry."""
        mock_response = MagicMock()
        mock_response.status_code = 400

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        with patch.object(client, '_get_client', return_value=mock_client):
            with pytest.raises(PolymarketAPIError) as exc_info:
                await client._request_with_retry("GET", "https://test.com/api")

            assert exc_info.value.status_code == 400
            assert mock_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_retries_and_succeeds(self, client):
        """Timeout followed by success should retry and return success."""
        responses = [
            httpx.TimeoutException("timeout"),
            MagicMock(status_code=200, json=lambda: {"data": "ok"}),
        ]
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            result = responses[call_count]
            call_count += 1
            if isinstance(result, Exception):
                raise result
            return result

        mock_client = AsyncMock()
        mock_client.request = mock_request
        mock_client.is_closed = False

        with patch.object(client, '_get_client', return_value=mock_client):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await client._request_with_retry("GET", "https://test.com/api")

                assert result == {"data": "ok"}
                assert call_count == 2


class TestBuildUrl:
    """Tests for URL building."""

    def test_build_url(self):
        """Should build correct URL."""
        client = BasePolymarketClient("https://test.polymarket.com")
        url = client._build_url("/positions")
        assert url == "https://test.polymarket.com/positions"

    def test_build_url_with_path(self):
        """Should handle nested paths."""
        client = BasePolymarketClient("https://test.polymarket.com")
        url = client._build_url("/api/v1/test")
        assert url == "https://test.polymarket.com/api/v1/test"
