"""Unit tests for MCP HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from ohlala_smartops import mcp
from ohlala_smartops.mcp.exceptions import (
    MCPAuthenticationError,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)
from ohlala_smartops.mcp.http_client import MCPHTTPClient


class TestMCPHTTPClientInit:
    """Test suite for MCPHTTPClient initialization."""

    def test_init_with_api_key(self) -> None:
        """Test client initialization with API key."""
        client = MCPHTTPClient(
            base_url="https://mcp.example.com",
            api_key="test-api-key",
        )
        assert client.base_url == "https://mcp.example.com"
        assert client.api_key == "test-api-key"
        assert client.session is None  # Not initialized until async context
        assert client.max_retries >= 0
        assert client.base_delay > 0
        assert client.max_delay > 0
        assert client.backoff_multiplier > 0

    def test_init_without_api_key(self) -> None:
        """Test client initialization without API key."""
        client = MCPHTTPClient(base_url="https://mcp.example.com")
        assert client.base_url == "https://mcp.example.com"
        assert client.api_key is None


class TestMCPHTTPClientHelperMethods:
    """Test suite for helper methods."""

    def test_next_request_id(self) -> None:
        """Test request ID generation is monotonically increasing."""
        client = MCPHTTPClient(base_url="https://mcp.example.com")
        id1 = client._next_request_id()
        id2 = client._next_request_id()
        id3 = client._next_request_id()
        assert id2 > id1
        assert id3 > id2

    def test_is_retryable_error(self) -> None:
        """Test retryable error detection."""
        client = MCPHTTPClient(base_url="https://mcp.example.com")
        # Retryable errors
        assert client._is_retryable_error(429) is True  # Rate limit
        assert client._is_retryable_error(500) is True  # Server error
        assert client._is_retryable_error(502) is True  # Bad gateway
        assert client._is_retryable_error(503) is True  # Service unavailable
        assert client._is_retryable_error(504) is True  # Gateway timeout

        # Non-retryable errors
        assert client._is_retryable_error(400) is False  # Bad request
        assert client._is_retryable_error(401) is False  # Unauthorized
        assert client._is_retryable_error(404) is False  # Not found

    def test_calculate_backoff_delay(self) -> None:
        """Test backoff delay calculation."""
        client = MCPHTTPClient(base_url="https://mcp.example.com")
        # First attempt should be close to base_delay
        delay0 = client._calculate_backoff_delay(0)
        assert 0.5 * client.base_delay <= delay0 <= 2.0 * client.base_delay

        # Later attempts should increase
        delay1 = client._calculate_backoff_delay(1)
        delay2 = client._calculate_backoff_delay(2)
        # Due to jitter, we just check they're positive
        assert delay1 > 0
        assert delay2 > 0


class TestMCPHTTPClientContextManager:
    """Test suite for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager_creates_session(self) -> None:
        """Test that context manager creates and closes session."""
        client = MCPHTTPClient(base_url="https://mcp.example.com")
        assert client.session is None

        async with client:
            assert client.session is not None
            assert isinstance(client.session, aiohttp.ClientSession)

        # Session should be closed after exiting context
        assert client.session.closed is True

    @pytest.mark.asyncio
    async def test_context_manager_handles_exceptions(self) -> None:
        """Test that context manager properly closes session on exceptions."""
        client = MCPHTTPClient(base_url="https://mcp.example.com")

        try:
            async with client:
                assert client.session is not None
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Session should still be closed even after exception
        assert client.session.closed is True


class TestMCPHTTPClientSuccessfulCalls:
    """Test suite for successful API calls."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self) -> None:
        """Test successful tool call."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": "i-1234567890"}]},
            }
        )

        async with client:
            with patch.object(client.session, "post") as mock_post:
                # Mock the async context manager
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await client.call_tool(
                    name="list-instances", arguments={"region": "us-east-1"}
                )

                assert result == {"content": [{"type": "text", "text": "i-1234567890"}]}
                assert mock_post.called

    @pytest.mark.asyncio
    async def test_list_tools_success(self) -> None:
        """Test successful list_tools call."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "tools": [
                        {"name": "list-instances", "description": "List EC2 instances"},
                        {"name": "send-command", "description": "Send SSM command"},
                    ]
                },
            }
        )

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                tools = await client.list_tools()

                assert len(tools) == 2
                assert tools[0]["name"] == "list-instances"
                assert tools[1]["name"] == "send-command"

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """Test successful health check."""
        client = MCPHTTPClient(base_url="https://mcp.example.com/rpc", api_key="test-key")

        mock_response = AsyncMock()
        mock_response.status = 200

        async with client:
            with patch.object(client.session, "get") as mock_get:
                mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_get.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await client.health_check()

                assert result is True
                mock_get.assert_called_once()
                # Should call /health on the base domain
                call_args = mock_get.call_args[0][0]
                assert call_args.endswith("/health")

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        """Test health check with unhealthy server."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response = AsyncMock()
        mock_response.status = 503

        async with client:
            with patch.object(client.session, "get") as mock_get:
                mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_get.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await client.health_check()

                assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self) -> None:
        """Test health check handles exceptions."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        async with client:
            with patch.object(client.session, "get") as mock_get:
                mock_get.side_effect = aiohttp.ClientError("Connection error")

                result = await client.health_check()

                assert result is False


class TestMCPHTTPClientErrors:
    """Test suite for error handling."""

    @pytest.mark.asyncio
    async def test_session_not_initialized_error(self) -> None:
        """Test error when session is not initialized."""
        client = MCPHTTPClient(base_url="https://mcp.example.com")

        with pytest.raises(MCPError) as exc_info:
            await client.call_tool(name="test", arguments={})

        assert "Session not initialized" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_http_401_authentication_error(self) -> None:
        """Test HTTP 401 raises authentication error."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="wrong-key")

        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")
        mock_response.json = AsyncMock(side_effect=aiohttp.ContentTypeError(MagicMock(), ()))

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(MCPAuthenticationError) as exc_info:
                    await client.call_tool(name="test", arguments={})

                assert "401" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_http_403_authentication_error(self) -> None:
        """Test HTTP 403 raises authentication error."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.text = AsyncMock(return_value="Forbidden")
        mock_response.json = AsyncMock(side_effect=aiohttp.ContentTypeError(MagicMock(), ()))

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(MCPAuthenticationError):
                    await client.call_tool(name="test", arguments={})

    @pytest.mark.asyncio
    async def test_jsonrpc_authentication_error(self) -> None:
        """Test JSON-RPC -32003 authentication error."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="wrong-key")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32003, "message": "Invalid API key"},
            }
        )

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(MCPAuthenticationError) as exc_info:
                    await client.call_tool(name="test", arguments={})

                assert "Invalid API key" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_jsonrpc_tool_not_found_error(self) -> None:
        """Test JSON-RPC -32601 tool not found error."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "Tool 'invalid-tool' not found"},
            }
        )

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(MCPToolNotFoundError) as exc_info:
                    await client.call_tool(name="invalid-tool", arguments={})

                assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_jsonrpc_generic_error(self) -> None:
        """Test generic JSON-RPC error."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32000, "message": "Generic error"},
            }
        )

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(MCPError) as exc_info:
                    await client.call_tool(name="test", arguments={})

                assert "Generic error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error(self) -> None:
        """Test timeout raises MCPTimeoutError."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.side_effect = TimeoutError()

                with pytest.raises(MCPTimeoutError):
                    await client.call_tool(name="test", arguments={})

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        """Test connection error raises MCPConnectionError."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.side_effect = aiohttp.ClientError("Connection refused")

                with pytest.raises(MCPConnectionError) as exc_info:
                    await client.call_tool(name="test", arguments={})

                assert "Connection refused" in str(exc_info.value)


class TestMCPHTTPClientRetryLogic:
    """Test suite for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_http_429(self) -> None:
        """Test retry on HTTP 429 rate limit."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response_429 = AsyncMock()
        mock_response_429.status = 429
        mock_response_429.text = AsyncMock(return_value="Rate limit exceeded")
        mock_response_429.json = AsyncMock(side_effect=aiohttp.ContentTypeError(MagicMock(), ()))

        mock_response_200 = AsyncMock()
        mock_response_200.status = 200
        mock_response_200.json = AsyncMock(
            return_value={"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}
        )

        async with client:
            with (
                patch.object(client.session, "post") as mock_post,
                patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            ):
                mock_post.return_value.__aenter__ = AsyncMock(
                    side_effect=[mock_response_429, mock_response_200]
                )
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await client.call_tool(name="test", arguments={})

                assert result == {"status": "ok"}
                assert mock_post.call_count == 2
                assert mock_sleep.called

    @pytest.mark.asyncio
    async def test_retry_on_http_500(self) -> None:
        """Test retry on HTTP 500 server error."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response_500 = AsyncMock()
        mock_response_500.status = 500
        mock_response_500.text = AsyncMock(return_value="Internal server error")
        mock_response_500.json = AsyncMock(side_effect=aiohttp.ContentTypeError(MagicMock(), ()))

        mock_response_200 = AsyncMock()
        mock_response_200.status = 200
        mock_response_200.json = AsyncMock(
            return_value={"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}
        )

        async with client:
            with (
                patch.object(client.session, "post") as mock_post,
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                mock_post.return_value.__aenter__ = AsyncMock(
                    side_effect=[mock_response_500, mock_response_200]
                )
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await client.call_tool(name="test", arguments={})

                assert result == {"status": "ok"}
                assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_jsonrpc_rate_limit(self) -> None:
        """Test retry on JSON-RPC rate limit error."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response_limit = AsyncMock()
        mock_response_limit.status = 200
        mock_response_limit.json = AsyncMock(
            return_value={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32002, "message": "Rate limit exceeded"},
            }
        )

        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        mock_response_success.json = AsyncMock(
            return_value={"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}
        )

        async with client:
            with (
                patch.object(client.session, "post") as mock_post,
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                mock_post.return_value.__aenter__ = AsyncMock(
                    side_effect=[mock_response_limit, mock_response_success]
                )
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                result = await client.call_tool(name="test", arguments={})

                assert result == {"status": "ok"}
                assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self) -> None:
        """Test that max retries is respected."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="test-key")

        mock_response_429 = AsyncMock()
        mock_response_429.status = 429
        mock_response_429.text = AsyncMock(return_value="Rate limit exceeded")
        mock_response_429.json = AsyncMock(side_effect=aiohttp.ContentTypeError(MagicMock(), ()))

        async with client:
            with (
                patch.object(client.session, "post") as mock_post,
                patch("asyncio.sleep", new_callable=AsyncMock),
            ):
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response_429)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(MCPError):
                    await client.call_tool(name="test", arguments={})

                # Should try initial + max_retries attempts
                assert mock_post.call_count == client.max_retries + 1

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self) -> None:
        """Test that authentication errors are not retried."""
        client = MCPHTTPClient(base_url="https://mcp.example.com", api_key="wrong-key")

        mock_response_401 = AsyncMock()
        mock_response_401.status = 401
        mock_response_401.text = AsyncMock(return_value="Unauthorized")
        mock_response_401.json = AsyncMock(side_effect=aiohttp.ContentTypeError(MagicMock(), ()))

        async with client:
            with patch.object(client.session, "post") as mock_post:
                mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response_401)
                mock_post.return_value.__aexit__ = AsyncMock(return_value=None)

                with pytest.raises(MCPAuthenticationError):
                    await client.call_tool(name="test", arguments={})

                # Should only try once, no retries
                assert mock_post.call_count == 1


class TestMCPHTTPClientModuleExports:
    """Test suite for module exports."""

    def test_module_exports(self) -> None:
        """Test that the MCP module exports MCPHTTPClient."""
        assert hasattr(mcp, "MCPHTTPClient")
