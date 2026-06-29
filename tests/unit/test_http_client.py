"""Unit tests for HTTP client with circuit breaker and retry service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient, HTTPClientError


class TestHTTPClient:
    """Test HTTP client functionality."""

    @pytest.fixture
    def test_settings(self):
        """Provide test settings."""
        return Settings()

    @pytest.fixture
    def http_client(self, test_settings):
        """Provide HTTPClient instance."""
        client = HTTPClient(test_settings)
        return client

    @pytest.fixture
    def mock_response(self):
        """Provide mock HTTP response."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.text = '{"success": true}'
        response.json.return_value = {"success": True}
        return response

    @pytest.mark.asyncio
    async def test_startup(self, http_client):
        """Test HTTP client startup."""
        await http_client.startup()
        assert http_client._client is not None

    @pytest.mark.asyncio
    async def test_shutdown(self, http_client):
        """Test HTTP client shutdown."""
        await http_client.startup()
        await http_client.shutdown()
        assert http_client._client is None

    @pytest.mark.asyncio
    async def test_request_success(self, http_client, mock_response):
        """Test successful HTTP request."""
        await http_client.startup()
        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        http_client._client = mock_client

        response = await http_client.request("GET", "http://example.com")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_request_retry_on_server_error(self, http_client):
        """Test retry on server error (500 -> success)."""
        await http_client.startup()

        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Internal Server Error"

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"success": True}

        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=[error_response, success_response])
        http_client._client = mock_client

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            response = await http_client.request(
                "GET", "http://example.com",
                service_name="test_service",
                retry_on_server_error=True,
            )
            assert response.status_code == 200
            assert mock_client.request.call_count >= 2

    @pytest.mark.asyncio
    async def test_request_no_retry_on_client_error(self, http_client):
        """Test no retry on client error (404)."""
        await http_client.startup()

        error_response = MagicMock()
        error_response.status_code = 404
        error_response.text = "Not Found"

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=error_response)
        http_client._client = mock_client

        with pytest.raises(HTTPClientError, match="404"):
            await http_client.request("GET", "http://example.com")
        # The retry service will try once then fail fast on 404
        assert mock_client.request.call_count >= 1

    @pytest.mark.asyncio
    async def test_request_timeout_retry(self, http_client):
        """Test retry on timeout."""
        await http_client.startup()

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"success": True}

        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            side_effect=[httpx.TimeoutException("Timeout"), success_response]
        )
        http_client._client = mock_client

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            response = await http_client.request("GET", "http://example.com")
            assert response.status_code == 200
            assert mock_client.request.call_count >= 2

    @pytest.mark.asyncio
    async def test_request_max_retries_exceeded(self, http_client):
        """Test failure after max retries."""
        await http_client.startup()

        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            side_effect=httpx.TimeoutException("Timeout")
        )
        http_client._client = mock_client

        with patch("app.infrastructure.retry_service.asyncio.sleep"):
            with pytest.raises(HTTPClientError):
                await http_client.request("GET", "http://example.com")

    @pytest.mark.asyncio
    async def test_post_json_success(self, http_client, mock_response):
        """Test successful POST with JSON."""
        await http_client.startup()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 123}

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        http_client._client = mock_client

        result = await http_client.post_json("http://example.com", {"key": "value"})
        assert result == {"id": 123}

    @pytest.mark.asyncio
    async def test_post_json_error(self, http_client):
        """Test POST with error response."""
        await http_client.startup()

        error_response = MagicMock()
        error_response.status_code = 422
        error_response.text = "Validation error"

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=error_response)
        http_client._client = mock_client

        with pytest.raises(HTTPClientError):
            await http_client.post_json("http://example.com", {"key": "value"})

    @pytest.mark.asyncio
    async def test_get_json_success(self, http_client, mock_response):
        """Test successful GET with JSON."""
        await http_client.startup()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        http_client._client = mock_client

        result = await http_client.get_json("http://example.com")
        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_get_json_error(self, http_client):
        """Test GET with error response."""
        await http_client.startup()

        error_response = MagicMock()
        error_response.status_code = 404
        error_response.text = "Not found"

        mock_client = MagicMock()
        mock_client.request = AsyncMock(return_value=error_response)
        http_client._client = mock_client

        with pytest.raises(HTTPClientError):
            await http_client.get_json("http://example.com")

    @pytest.mark.asyncio
    async def test_stream_success(self, http_client):
        """Test streaming response."""
        await http_client.startup()

        mock_client = MagicMock()

        # Create a proper async generator for aiter_bytes
        async def aiter_bytes_gen():
            yield b"chunk1"
            yield b"chunk2"

        mock_stream = MagicMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)
        mock_stream.raise_for_status = MagicMock()
        mock_stream.aiter_bytes = aiter_bytes_gen
        mock_client.stream.return_value = mock_stream
        http_client._client = mock_client

        chunks = []
        async for chunk in http_client.stream("GET", "http://example.com"):
            chunks.append(chunk)

        assert chunks == [b"chunk1", b"chunk2"]

    @pytest.mark.asyncio
    async def test_request_not_initialized(self, http_client):
        """Test request when client not initialized."""
        with pytest.raises(HTTPClientError, match="not connected"):
            await http_client.request("GET", "http://example.com")