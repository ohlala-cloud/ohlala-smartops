"""MCP Manager for handling Model Context Protocol server connections.

This module provides the MCPManager class for managing MCP server connections
and orchestrating tool calls to AWS API and AWS Knowledge servers.

Phase 3A: Core MCP functionality with simplified workflows.
Phase 3B: Will add write operation approval workflows.
Phase 3C: Will add async command tracking and SSM validation.

Example:
    Basic usage::

        from ohlala_smartops.mcp.manager import MCPManager

        # Initialize manager
        manager = MCPManager()
        await manager.initialize()

        # List available tools
        tools = await manager.list_available_tools()

        # Call a tool
        result = await manager.call_aws_api_tool(
            tool_name="list-instances",
            arguments={}
        )

Note:
    This is Phase 3A implementation focusing on core MCP functionality.
    Approval workflows and command tracking will be added in Phase 3B/3C.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any, Final, cast

from ohlala_smartops.config import get_settings
from ohlala_smartops.constants import DEFAULT_MCP_AWS_API_URL, DEFAULT_MCP_AWS_KNOWLEDGE_URL
from ohlala_smartops.mcp.exceptions import MCPConnectionError, MCPError
from ohlala_smartops.mcp.http_client import MCPHTTPClient
from ohlala_smartops.utils.audit_logger import AuditLogger
from ohlala_smartops.utils.global_throttler import (
    CircuitBreakerOpenError,
    CircuitBreakerTrippedError,
    throttled_aws_call,
)

logger: Final = logging.getLogger(__name__)


class MCPManager:
    """Manager for MCP server connections via HTTP.

    This manager handles connections to MCP servers (AWS API and AWS Knowledge),
    provides tool discovery and schema caching, and orchestrates tool execution
    with throttling and error handling.

    Attributes:
        mcp_aws_api_url: URL for AWS API MCP server.
        mcp_aws_knowledge_url: URL for AWS Knowledge MCP server.
        mcp_api_key: API key for MCP authentication.
        aws_api_client: HTTP client for AWS API server.
        aws_knowledge_client: HTTP client for AWS Knowledge server.

    Example:
        >>> manager = MCPManager()
        >>> await manager.initialize()
        >>> tools = await manager.list_available_tools()
        >>> result = await manager.call_aws_api_tool("list-instances", {})

    Note:
        Phase 3A: Core functionality. Approval workflows in Phase 3B.
    """

    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        """Initialize MCP Manager.

        Args:
            audit_logger: Optional custom audit logger. If None, creates default.
        """
        self.settings = get_settings()

        # MCP server URLs
        self.mcp_aws_api_url = self.settings.mcp_aws_api_url or DEFAULT_MCP_AWS_API_URL
        self.mcp_aws_knowledge_url = (
            self.settings.mcp_aws_knowledge_url or DEFAULT_MCP_AWS_KNOWLEDGE_URL
        )
        self.mcp_api_key = self.settings.mcp_internal_api_key

        # MCP HTTP clients
        self.aws_api_client: MCPHTTPClient | None = None
        self.aws_knowledge_client: MCPHTTPClient | None = None

        # State tracking
        self._initialized = False
        self._last_health_check: float = 0
        self._tool_schemas_cache: dict[str, Any] = {}

        # Components
        self.audit_logger = audit_logger or AuditLogger()

        logger.info(
            "MCPManager initialized with AWS API URL: %s",
            self.mcp_aws_api_url,
        )

    async def initialize(self) -> None:
        """Initialize MCP server connections.

        Connects to AWS API MCP server (required) and AWS Knowledge MCP server
        (optional). Performs health checks and tool discovery.

        Raises:
            MCPConnectionError: If AWS API MCP server connection fails.

        Note:
            Uses caching to avoid redundant initializations within 30 seconds.
        """
        # Avoid redundant initializations within 30 seconds
        current_time = time.time()
        if self._initialized and (current_time - self._last_health_check) < 30:
            return

        if self._initialized:
            # Already initialized recently, skip
            return

        logger.info("Starting MCP HTTP server initialization...")
        try:
            # Initialize HTTP client for AWS API MCP server
            self.aws_api_client = MCPHTTPClient(
                self.mcp_aws_api_url,
                api_key=self.mcp_api_key,
            )
            await self.aws_api_client.__aenter__()

            # Check health
            if await self.aws_api_client.health_check():
                logger.info("AWS API MCP server initialized and healthy")

                # List available tools
                tools = await self.aws_api_client.list_tools()
                logger.info("AWS API MCP initialized with %d tools available", len(tools))
                self._initialized = True
                self._last_health_check = current_time
            else:
                logger.warning("AWS API MCP server health check failed")
                self._initialized = False
                raise MCPConnectionError("AWS API MCP server health check failed")

            # Initialize AWS Knowledge MCP server (optional - don't fail if not available)
            try:
                logger.info(
                    "Attempting to connect to AWS Knowledge MCP server at %s",
                    self.mcp_aws_knowledge_url,
                )
                self.aws_knowledge_client = MCPHTTPClient(self.mcp_aws_knowledge_url)
                await self.aws_knowledge_client.__aenter__()

                # Check if we can list tools
                knowledge_tools = await self.aws_knowledge_client.list_tools()
                logger.info(
                    "AWS Knowledge MCP initialized with %d tools available",
                    len(knowledge_tools),
                )
            except Exception as ke:
                logger.warning("Failed to initialize AWS Knowledge MCP server: %s", ke)
                logger.info(
                    "Continuing without AWS Knowledge server - "
                    "rightsizing recommendations will be limited"
                )
                self.aws_knowledge_client = None

        except Exception as e:
            logger.error("Failed to initialize MCP servers: %s", e, exc_info=True)
            self._initialized = False
            raise MCPConnectionError(f"Failed to initialize MCP servers: {e}") from e

    async def call_aws_api_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool on the AWS API MCP server.

        Executes a tool call on the AWS API MCP server with throttling,
        error handling, and basic validation.

        Args:
            tool_name: Name of the tool to call.
            arguments: Tool arguments as a dictionary.

        Returns:
            Tool execution result as a dictionary.

        Raises:
            MCPError: If tool execution fails.

        Example:
            >>> result = await manager.call_aws_api_tool(
            ...     "list-instances",
            ...     {"MaxResults": 10}
            ... )

        Note:
            Phase 3A: Basic tool execution. Approval workflows in Phase 3B.
        """
        logger.debug("Calling AWS API tool: %s", tool_name)

        # Track execution time
        start_time = datetime.now(UTC)

        try:
            if not self._initialized or not self.aws_api_client:
                logger.debug("MCP not initialized, initializing now...")
                await self.initialize()

            # Phase 3B TODO: Add write operation approval workflow
            # For now, all operations execute directly

            # Phase 3B TODO: Add instance ID validation via AWS API
            # For now, only basic format validation

            # Execute the tool call with throttling
            actual_tool_name = tool_name.removeprefix("aws___")

            logger.info("Calling MCP tool: %s with arguments: %s", actual_tool_name, arguments)

            # Apply global throttling to all AWS API calls
            # At this point, aws_api_client is guaranteed to be non-None due to initialization check
            assert self.aws_api_client is not None
            try:
                async with throttled_aws_call(actual_tool_name):
                    result = await self.aws_api_client.call_tool(actual_tool_name, arguments)
            except (CircuitBreakerOpenError, CircuitBreakerTrippedError) as circuit_error:
                logger.warning("Circuit breaker blocked %s: %s", actual_tool_name, circuit_error)
                return {
                    "error": "Rate limiting in effect",
                    "message": "AWS API rate limiting is currently active. "
                    "Please wait a moment and try again.",
                    "circuit_breaker": True,
                    "retry_after": 30,
                }

            # Calculate execution time
            execution_time = (datetime.now(UTC) - start_time).total_seconds()
            logger.info("AWS API tool %s completed in %.2fs", actual_tool_name, execution_time)

            # Phase 3B TODO: Emit CloudWatch metrics for tool usage
            # Phase 3C TODO: Auto-track SSM commands for async monitoring

            return cast(dict[str, Any], result)

        except Exception as e:
            execution_time = (datetime.now(UTC) - start_time).total_seconds()
            logger.error("Error calling AWS API tool %s: %s", tool_name, e)

            # Phase 3B TODO: Emit failure metrics
            raise MCPError(f"Failed to call AWS API tool: {e}") from e

    async def call_aws_knowledge_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool on the AWS Knowledge MCP server.

        Executes a tool call on the AWS Knowledge MCP server for documentation
        and knowledge queries.

        Args:
            tool_name: Name of the knowledge tool to call.
            arguments: Tool arguments as a dictionary.

        Returns:
            Tool execution result as a dictionary.

        Example:
            >>> result = await manager.call_aws_knowledge_tool(
            ...     "get-ec2-documentation",
            ...     {"topic": "instance-types"}
            ... )
        """
        logger.info("Calling AWS Knowledge tool: %s with arguments: %s", tool_name, arguments)

        try:
            if not self.aws_knowledge_client:
                logger.warning("AWS Knowledge MCP server not available")
                return {"error": "AWS Knowledge MCP server not available"}

            # Apply global throttling to AWS Knowledge calls
            try:
                async with throttled_aws_call(f"knowledge_{tool_name}"):
                    result = await self.aws_knowledge_client.call_tool(tool_name, arguments)
                return cast(dict[str, Any], result)
            except (CircuitBreakerOpenError, CircuitBreakerTrippedError) as circuit_error:
                logger.warning(
                    "Circuit breaker blocked knowledge tool %s: %s", tool_name, circuit_error
                )
                return {
                    "error": "Rate limiting in effect",
                    "message": "AWS Knowledge service rate limiting is currently active. "
                    "Please wait a moment and try again.",
                    "circuit_breaker": True,
                    "retry_after": 30,
                }

        except Exception as e:
            logger.error("Error calling AWS Knowledge tool %s: %s", tool_name, e)
            return {"error": f"Failed to call AWS Knowledge tool: {e}"}

    async def list_available_tools(self, verbose: bool = True) -> list[str]:
        """Get list of available tools from MCP servers.

        Retrieves tool lists from both AWS API and AWS Knowledge MCP servers.

        Args:
            verbose: If True, log detailed information. Defaults to True.

        Returns:
            List of tool names with server prefixes (aws___ or knowledge___).

        Example:
            >>> tools = await manager.list_available_tools()
            >>> print(tools)
            ['aws___list-instances', 'aws___start-instances', ...]

        Note:
            Tool names are prefixed with server identifier for routing.
        """

        # Helper for conditional logging
        def log_verbose(msg: str, *args: Any) -> None:
            if verbose:
                logger.info(msg, *args)

        log_verbose("Listing available tools. Initialized: %s", self._initialized)

        try:
            if not self._initialized or not self.aws_api_client:
                log_verbose("MCP not initialized, initializing now...")
                await self.initialize()

            tools: list[str] = []

            # Get AWS API tools
            if self.aws_api_client:
                log_verbose("Getting tools from AWS API MCP server...")
                try:
                    aws_tools = await self.aws_api_client.list_tools()
                    log_verbose("Retrieved %d tools from AWS API MCP server", len(aws_tools))
                    tools.extend([f"aws___{tool['name']}" for tool in aws_tools])
                except Exception as e:
                    logger.error("Failed to get AWS API tools: %s", e)

            # Add AWS Knowledge tools if available
            if self.aws_knowledge_client:
                log_verbose("Getting tools from AWS Knowledge MCP server...")
                try:
                    knowledge_tools = await self.aws_knowledge_client.list_tools()
                    log_verbose(
                        "Retrieved %d tools from AWS Knowledge MCP server",
                        len(knowledge_tools),
                    )
                    tools.extend([f"knowledge___{tool['name']}" for tool in knowledge_tools])
                except Exception as e:
                    logger.error("Failed to get AWS Knowledge tools: %s", e)
                    log_verbose("Continuing without AWS Knowledge tools")

            log_verbose("Total tools available: %d", len(tools))
            return tools

        except Exception as e:
            logger.error("Error listing available tools: %s", e)
            return []

    async def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """Get the complete schema for a specific tool.

        This method caches tool schemas to ensure consistency across
        original requests and retry attempts.

        Args:
            tool_name: Name of the tool (without server prefix).

        Returns:
            Tool schema dictionary, or None if not found.

        Example:
            >>> schema = await manager.get_tool_schema("list-instances")
            >>> print(schema['inputSchema'])

        Note:
            Schemas are cached for performance and consistency.
        """
        # Check cache first
        if tool_name in self._tool_schemas_cache:
            cached_schema = self._tool_schemas_cache[tool_name]
            logger.info("Retrieved cached schema for tool: %s", tool_name)
            return cast(dict[str, Any], cached_schema)

        try:
            if not self._initialized:
                await self.initialize()

            if not self.aws_api_client:
                logger.error("AWS API client not available for tool schema retrieval")
                return None

            # Get full tool list with schemas
            tools = await self.aws_api_client.list_tools()

            # Find the specific tool
            for tool in tools:
                if tool.get("name") == tool_name:
                    # Cache the schema
                    self._tool_schemas_cache[tool_name] = tool
                    logger.info("Cached schema for tool: %s", tool_name)
                    return tool

            logger.warning("Tool schema not found: %s", tool_name)
            return None

        except Exception as e:
            logger.error("Error getting tool schema for %s: %s", tool_name, e)
            return None

    def cache_tool_schemas_for_conversation(
        self,
        conversation_id: str,
        tools: list[dict[str, Any]],
    ) -> None:
        """Cache tool schemas specifically for a conversation to ensure retry consistency.

        Args:
            conversation_id: Unique conversation identifier.
            tools: List of tool schemas to cache.

        Note:
            Used to maintain consistent tool schemas across Bedrock retries.
        """
        cache_key = f"conversation_{conversation_id}"
        self._tool_schemas_cache[cache_key] = {
            "tools": tools,
            "timestamp": datetime.now(UTC),
            "conversation_id": conversation_id,
        }
        logger.info("Cached %d tool schemas for conversation %s", len(tools), conversation_id)

    def get_cached_conversation_tools(self, conversation_id: str) -> list[dict[str, Any]] | None:
        """Retrieve cached tool schemas for a specific conversation.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            List of cached tool schemas, or None if not found.

        Example:
            >>> tools = manager.get_cached_conversation_tools("conv-123")
            >>> if tools:
            ...     print(f"Found {len(tools)} cached tools")
        """
        cache_key = f"conversation_{conversation_id}"
        cache_entry = self._tool_schemas_cache.get(cache_key)

        if cache_entry:
            tools = cache_entry["tools"]
            timestamp = cache_entry["timestamp"]
            logger.info(
                "Retrieved %d cached tools for conversation %s (cached at %s)",
                len(tools),
                conversation_id,
                timestamp,
            )
            return cast(list[dict[str, Any]], tools)

        return None

    async def close(self) -> None:
        """Close MCP server connections.

        Properly closes HTTP clients and cleans up resources.

        Example:
            >>> manager = MCPManager()
            >>> await manager.initialize()
            >>> # ... use manager ...
            >>> await manager.close()
        """
        # Close AWS API client
        if self.aws_api_client:
            try:
                await self.aws_api_client.__aexit__(None, None, None)
            except Exception as e:
                logger.error("Error closing AWS API client: %s", e)
            finally:
                self.aws_api_client = None

        # Close AWS Knowledge client
        if self.aws_knowledge_client:
            try:
                await self.aws_knowledge_client.__aexit__(None, None, None)
            except Exception as e:
                logger.error("Error closing AWS Knowledge client: %s", e)
            finally:
                self.aws_knowledge_client = None

        self._initialized = False
        logger.info("MCP connections closed")
