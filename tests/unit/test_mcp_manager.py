"""Unit tests for MCP Manager.

This module contains comprehensive tests for the MCPManager class, covering:
- Initialization and configuration
- Server connections and health checking
- Tool discovery and listing
- Tool schema caching
- Tool execution with throttling
- Error handling and circuit breakers
- Connection management
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ohlala_smartops.mcp.exceptions import MCPConnectionError, MCPError
from ohlala_smartops.mcp.manager import MCPManager
from ohlala_smartops.utils.global_throttler import CircuitBreakerOpenError


@pytest.fixture
def mock_settings():
    """Mock settings for MCP Manager."""
    settings = Mock()
    settings.mcp_aws_api_url = "http://mcp-api.test"
    settings.mcp_aws_knowledge_url = "http://mcp-knowledge.test"
    settings.mcp_internal_api_key = "test-api-key"
    return settings


@pytest.fixture
def mock_audit_logger():
    """Mock audit logger."""
    return Mock()


@pytest.fixture
def mcp_manager(mock_settings, mock_audit_logger):
    """Create MCP Manager instance with mocked dependencies."""
    with patch("ohlala_smartops.mcp.manager.get_settings", return_value=mock_settings):
        return MCPManager(audit_logger=mock_audit_logger)


@pytest.fixture
def mock_http_client():
    """Mock MCP HTTP Client."""
    client = Mock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.health_check = AsyncMock(return_value=True)
    client.list_tools = AsyncMock(
        return_value=[
            {"name": "list-instances", "description": "List EC2 instances"},
            {"name": "start-instances", "description": "Start EC2 instances"},
        ]
    )
    client.call_tool = AsyncMock(return_value={"success": True, "data": []})
    return client


class TestMCPManagerInit:
    """Test MCPManager initialization."""

    def test_init_with_defaults(self, mock_settings):
        """Test initialization with default parameters."""
        with patch("ohlala_smartops.mcp.manager.get_settings", return_value=mock_settings):
            manager = MCPManager()

            assert manager.mcp_aws_api_url == "http://mcp-api.test"
            assert manager.mcp_aws_knowledge_url == "http://mcp-knowledge.test"
            assert manager.mcp_api_key == "test-api-key"
            assert manager.aws_api_client is None
            assert manager.aws_knowledge_client is None
            assert not manager._initialized
            assert manager._last_health_check == 0
            assert len(manager._tool_schemas_cache) == 0

    def test_init_with_custom_audit_logger(self, mock_settings, mock_audit_logger):
        """Test initialization with custom audit logger."""
        with patch("ohlala_smartops.mcp.manager.get_settings", return_value=mock_settings):
            manager = MCPManager(audit_logger=mock_audit_logger)

            assert manager.audit_logger is mock_audit_logger


class TestServerInitialization:
    """Test MCP server initialization."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, mcp_manager, mock_http_client):
        """Test successful server initialization."""
        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            await mcp_manager.initialize()

            assert mcp_manager._initialized
            assert mcp_manager.aws_api_client is not None
            assert mcp_manager._last_health_check > 0
            mock_http_client.health_check.assert_called_once()
            mock_http_client.list_tools.assert_called()

    @pytest.mark.asyncio
    async def test_initialize_health_check_failure(self, mcp_manager, mock_http_client):
        """Test initialization with health check failure."""
        mock_http_client.health_check = AsyncMock(return_value=False)

        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            with pytest.raises(MCPConnectionError, match="health check failed"):
                await mcp_manager.initialize()

            assert not mcp_manager._initialized

    @pytest.mark.asyncio
    async def test_initialize_knowledge_server_optional(self, mcp_manager):
        """Test that AWS Knowledge server failure doesn't block initialization."""
        api_client = Mock()
        api_client.__aenter__ = AsyncMock(return_value=api_client)
        api_client.__aexit__ = AsyncMock(return_value=None)
        api_client.health_check = AsyncMock(return_value=True)
        api_client.list_tools = AsyncMock(return_value=[])

        knowledge_client = Mock()
        knowledge_client.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))

        with patch(
            "ohlala_smartops.mcp.manager.MCPHTTPClient",
            side_effect=[api_client, knowledge_client],
        ):
            await mcp_manager.initialize()

            assert mcp_manager._initialized
            assert mcp_manager.aws_api_client is not None
            assert mcp_manager.aws_knowledge_client is None

    @pytest.mark.asyncio
    async def test_initialize_caching_avoids_redundant_calls(self, mcp_manager, mock_http_client):
        """Test that initialization is cached to avoid redundant calls."""
        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            # First initialization
            await mcp_manager.initialize()
            first_health_check_count = mock_http_client.health_check.call_count

            # Second initialization within 30 seconds should be skipped
            await mcp_manager.initialize()
            assert mock_http_client.health_check.call_count == first_health_check_count

    @pytest.mark.asyncio
    async def test_initialize_connection_error(self, mcp_manager, mock_http_client):
        """Test initialization with connection error."""
        mock_http_client.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            with pytest.raises(MCPConnectionError, match="Failed to initialize MCP servers"):
                await mcp_manager.initialize()

            assert not mcp_manager._initialized


class TestToolListing:
    """Test tool discovery and listing."""

    @pytest.mark.asyncio
    async def test_list_available_tools_success(self, mcp_manager, mock_http_client):
        """Test successful tool listing."""
        # Configure mock to return specific tools for AWS API server only
        mock_http_client.list_tools = AsyncMock(
            return_value=[
                {"name": "list-instances"},
                {"name": "start-instances"},
                {"name": "stop-instances"},
            ]
        )

        # Create a knowledge client that fails to initialize
        knowledge_client = Mock()
        knowledge_client.__aenter__ = AsyncMock(side_effect=Exception("Not available"))

        with patch(
            "ohlala_smartops.mcp.manager.MCPHTTPClient",
            side_effect=[mock_http_client, knowledge_client],
        ):
            await mcp_manager.initialize()
            tools = await mcp_manager.list_available_tools()

            assert len(tools) == 3
            assert "aws___list-instances" in tools
            assert "aws___start-instances" in tools
            assert "aws___stop-instances" in tools

    @pytest.mark.asyncio
    async def test_list_tools_with_knowledge_server(self, mcp_manager):
        """Test tool listing with both AWS API and Knowledge servers."""
        api_client = Mock()
        api_client.__aenter__ = AsyncMock(return_value=api_client)
        api_client.__aexit__ = AsyncMock(return_value=None)
        api_client.health_check = AsyncMock(return_value=True)
        api_client.list_tools = AsyncMock(
            return_value=[
                {"name": "list-instances"},
                {"name": "start-instances"},
            ]
        )

        knowledge_client = Mock()
        knowledge_client.__aenter__ = AsyncMock(return_value=knowledge_client)
        knowledge_client.__aexit__ = AsyncMock(return_value=None)
        knowledge_client.list_tools = AsyncMock(
            return_value=[
                {"name": "get-ec2-docs"},
                {"name": "get-pricing-info"},
            ]
        )

        with patch(
            "ohlala_smartops.mcp.manager.MCPHTTPClient",
            side_effect=[api_client, knowledge_client],
        ):
            await mcp_manager.initialize()
            tools = await mcp_manager.list_available_tools()

            assert len(tools) == 4
            assert "aws___list-instances" in tools
            assert "aws___start-instances" in tools
            assert "knowledge___get-ec2-docs" in tools
            assert "knowledge___get-pricing-info" in tools

    @pytest.mark.asyncio
    async def test_list_tools_handles_api_failure(self, mcp_manager, mock_http_client):
        """Test tool listing gracefully handles API failures."""
        # First, initialize successfully
        mock_http_client.list_tools = AsyncMock(return_value=[])

        # Create a knowledge client that fails
        knowledge_client = Mock()
        knowledge_client.__aenter__ = AsyncMock(side_effect=Exception("Not available"))

        with patch(
            "ohlala_smartops.mcp.manager.MCPHTTPClient",
            side_effect=[mock_http_client, knowledge_client],
        ):
            await mcp_manager.initialize()

            # Now make list_tools fail for subsequent calls
            mock_http_client.list_tools = AsyncMock(side_effect=Exception("API error"))

            tools = await mcp_manager.list_available_tools()

            # Should return empty list on error, not raise exception
            assert tools == []

    @pytest.mark.asyncio
    async def test_list_tools_auto_initializes(self, mcp_manager, mock_http_client):
        """Test that list_available_tools auto-initializes if needed."""
        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            # Don't manually initialize
            tools = await mcp_manager.list_available_tools()

            # Should have initialized automatically
            assert mcp_manager._initialized
            assert len(tools) > 0


class TestToolSchemas:
    """Test tool schema retrieval and caching."""

    @pytest.mark.asyncio
    async def test_get_tool_schema_success(self, mcp_manager, mock_http_client):
        """Test successful tool schema retrieval."""
        mock_http_client.list_tools = AsyncMock(
            return_value=[
                {
                    "name": "list-instances",
                    "description": "List EC2 instances",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]
        )

        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            await mcp_manager.initialize()
            schema = await mcp_manager.get_tool_schema("list-instances")

            assert schema is not None
            assert schema["name"] == "list-instances"
            assert "inputSchema" in schema

    @pytest.mark.asyncio
    async def test_get_tool_schema_caching(self, mcp_manager, mock_http_client):
        """Test that tool schemas are cached."""
        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            await mcp_manager.initialize()

            # First call should hit MCP server
            schema1 = await mcp_manager.get_tool_schema("list-instances")
            list_tools_call_count = mock_http_client.list_tools.call_count

            # Second call should use cache
            schema2 = await mcp_manager.get_tool_schema("list-instances")

            assert schema1 == schema2
            assert mock_http_client.list_tools.call_count == list_tools_call_count

    @pytest.mark.asyncio
    async def test_get_tool_schema_not_found(self, mcp_manager, mock_http_client):
        """Test tool schema retrieval for non-existent tool."""
        mock_http_client.list_tools = AsyncMock(return_value=[{"name": "list-instances"}])

        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            await mcp_manager.initialize()
            schema = await mcp_manager.get_tool_schema("non-existent-tool")

            assert schema is None

    def test_cache_tool_schemas_for_conversation(self, mcp_manager):
        """Test conversation-specific tool schema caching."""
        tools = [
            {"name": "tool1", "description": "Tool 1"},
            {"name": "tool2", "description": "Tool 2"},
        ]

        mcp_manager.cache_tool_schemas_for_conversation("conv-123", tools)

        cached = mcp_manager.get_cached_conversation_tools("conv-123")
        assert cached == tools

    def test_get_cached_conversation_tools_not_found(self, mcp_manager):
        """Test retrieving non-existent conversation cache."""
        cached = mcp_manager.get_cached_conversation_tools("non-existent")
        assert cached is None


class TestAWSAPIToolExecution:
    """Test AWS API tool execution."""

    @pytest.mark.asyncio
    async def test_call_aws_api_tool_success(self, mcp_manager, mock_http_client):
        """Test successful AWS API tool call."""
        mock_http_client.call_tool = AsyncMock(return_value={"success": True, "instances": []})

        with (
            patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client),
            patch("ohlala_smartops.mcp.manager.throttled_aws_call") as mock_throttle,
        ):
            mock_throttle.return_value.__aenter__ = AsyncMock()
            mock_throttle.return_value.__aexit__ = AsyncMock()

            await mcp_manager.initialize()
            result = await mcp_manager.call_aws_api_tool("list-instances", {})

            assert result["success"] is True
            mock_http_client.call_tool.assert_called_once_with("list-instances", {})

    @pytest.mark.asyncio
    async def test_call_aws_api_tool_with_prefix(self, mcp_manager, mock_http_client):
        """Test AWS API tool call with aws___ prefix removal."""
        mock_http_client.call_tool = AsyncMock(return_value={"success": True})

        with (
            patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client),
            patch("ohlala_smartops.mcp.manager.throttled_aws_call") as mock_throttle,
        ):
            mock_throttle.return_value.__aenter__ = AsyncMock()
            mock_throttle.return_value.__aexit__ = AsyncMock()

            await mcp_manager.initialize()
            await mcp_manager.call_aws_api_tool("aws___list-instances", {})

            # Prefix should be removed
            mock_http_client.call_tool.assert_called_once_with("list-instances", {})

    @pytest.mark.asyncio
    async def test_call_aws_api_tool_circuit_breaker_open(self, mcp_manager, mock_http_client):
        """Test AWS API tool call with circuit breaker open."""
        with (
            patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client),
            patch("ohlala_smartops.mcp.manager.throttled_aws_call") as mock_throttle,
        ):
            mock_throttle.return_value.__aenter__ = AsyncMock(
                side_effect=CircuitBreakerOpenError("Circuit breaker open")
            )

            await mcp_manager.initialize()
            result = await mcp_manager.call_aws_api_tool("list-instances", {})

            assert "error" in result
            assert "Rate limiting in effect" in result["error"]
            assert result.get("circuit_breaker") is True
            assert result.get("retry_after") == 30

    @pytest.mark.asyncio
    async def test_call_aws_api_tool_auto_initializes(self, mcp_manager, mock_http_client):
        """Test that tool call auto-initializes if needed."""
        mock_http_client.call_tool = AsyncMock(return_value={"success": True})

        with (
            patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client),
            patch("ohlala_smartops.mcp.manager.throttled_aws_call") as mock_throttle,
        ):
            mock_throttle.return_value.__aenter__ = AsyncMock()
            mock_throttle.return_value.__aexit__ = AsyncMock()

            # Don't manually initialize
            result = await mcp_manager.call_aws_api_tool("list-instances", {})

            # Should have initialized automatically
            assert mcp_manager._initialized
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_call_aws_api_tool_error_handling(self, mcp_manager, mock_http_client):
        """Test error handling in AWS API tool call."""
        mock_http_client.call_tool = AsyncMock(side_effect=Exception("Tool execution failed"))

        with (
            patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client),
            patch("ohlala_smartops.mcp.manager.throttled_aws_call") as mock_throttle,
        ):
            mock_throttle.return_value.__aenter__ = AsyncMock()
            mock_throttle.return_value.__aexit__ = AsyncMock()

            await mcp_manager.initialize()

            with pytest.raises(MCPError, match="Failed to call AWS API tool"):
                await mcp_manager.call_aws_api_tool("list-instances", {})


class TestAWSKnowledgeToolExecution:
    """Test AWS Knowledge tool execution."""

    @pytest.mark.asyncio
    async def test_call_aws_knowledge_tool_success(self, mcp_manager):
        """Test successful AWS Knowledge tool call."""
        knowledge_client = Mock()
        knowledge_client.call_tool = AsyncMock(
            return_value={"success": True, "documentation": "EC2 docs"}
        )

        mcp_manager.aws_knowledge_client = knowledge_client

        with patch("ohlala_smartops.mcp.manager.throttled_aws_call") as mock_throttle:
            mock_throttle.return_value.__aenter__ = AsyncMock()
            mock_throttle.return_value.__aexit__ = AsyncMock()

            result = await mcp_manager.call_aws_knowledge_tool("get-ec2-docs", {})

            assert result["success"] is True
            assert "documentation" in result
            knowledge_client.call_tool.assert_called_once_with("get-ec2-docs", {})

    @pytest.mark.asyncio
    async def test_call_aws_knowledge_tool_not_available(self, mcp_manager):
        """Test AWS Knowledge tool call when server not available."""
        mcp_manager.aws_knowledge_client = None

        result = await mcp_manager.call_aws_knowledge_tool("get-ec2-docs", {})

        assert "error" in result
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_call_aws_knowledge_tool_circuit_breaker(self, mcp_manager):
        """Test AWS Knowledge tool call with circuit breaker."""
        knowledge_client = Mock()
        mcp_manager.aws_knowledge_client = knowledge_client

        with patch("ohlala_smartops.mcp.manager.throttled_aws_call") as mock_throttle:
            mock_throttle.return_value.__aenter__ = AsyncMock(
                side_effect=CircuitBreakerOpenError("Circuit breaker open")
            )

            result = await mcp_manager.call_aws_knowledge_tool("get-ec2-docs", {})

            assert "error" in result
            assert "Rate limiting in effect" in result["error"]
            assert result.get("circuit_breaker") is True

    @pytest.mark.asyncio
    async def test_call_aws_knowledge_tool_error_handling(self, mcp_manager):
        """Test error handling in AWS Knowledge tool call."""
        knowledge_client = Mock()
        knowledge_client.call_tool = AsyncMock(side_effect=Exception("Tool failed"))
        mcp_manager.aws_knowledge_client = knowledge_client

        with patch("ohlala_smartops.mcp.manager.throttled_aws_call") as mock_throttle:
            mock_throttle.return_value.__aenter__ = AsyncMock()
            mock_throttle.return_value.__aexit__ = AsyncMock()

            result = await mcp_manager.call_aws_knowledge_tool("get-ec2-docs", {})

            assert "error" in result
            assert "Failed to call AWS Knowledge tool" in result["error"]


class TestConnectionManagement:
    """Test MCP connection management."""

    @pytest.mark.asyncio
    async def test_close_connections(self, mcp_manager, mock_http_client):
        """Test closing MCP connections."""
        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            await mcp_manager.initialize()
            await mcp_manager.close()

            assert mcp_manager.aws_api_client is None
            assert mcp_manager.aws_knowledge_client is None
            assert not mcp_manager._initialized
            mock_http_client.__aexit__.assert_called()

    @pytest.mark.asyncio
    async def test_close_with_knowledge_server(self, mcp_manager):
        """Test closing connections with both servers initialized."""
        api_client = Mock()
        api_client.__aenter__ = AsyncMock(return_value=api_client)
        api_client.__aexit__ = AsyncMock(return_value=None)
        api_client.health_check = AsyncMock(return_value=True)
        api_client.list_tools = AsyncMock(return_value=[])

        knowledge_client = Mock()
        knowledge_client.__aenter__ = AsyncMock(return_value=knowledge_client)
        knowledge_client.__aexit__ = AsyncMock(return_value=None)
        knowledge_client.list_tools = AsyncMock(return_value=[])

        with patch(
            "ohlala_smartops.mcp.manager.MCPHTTPClient",
            side_effect=[api_client, knowledge_client],
        ):
            await mcp_manager.initialize()
            await mcp_manager.close()

            api_client.__aexit__.assert_called_once()
            knowledge_client.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_errors(self, mcp_manager, mock_http_client):
        """Test that close() handles errors gracefully."""
        mock_http_client.__aexit__ = AsyncMock(side_effect=Exception("Close failed"))

        with patch("ohlala_smartops.mcp.manager.MCPHTTPClient", return_value=mock_http_client):
            await mcp_manager.initialize()

            # Should not raise exception
            await mcp_manager.close()

            # Connections should still be cleaned up
            assert mcp_manager.aws_api_client is None
