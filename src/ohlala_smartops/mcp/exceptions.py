"""MCP-specific exceptions.

This module defines exception classes for Model Context Protocol (MCP) operations,
including connection errors, timeouts, tool availability, and authentication failures.

Example:
    Handle MCP connection errors::

        from ohlala_smartops.mcp.exceptions import MCPConnectionError, MCPTimeoutError

        try:
            await mcp_client.call_tool("list-instances", {})
        except MCPConnectionError as e:
            logger.error(f"Failed to connect to MCP server: {e}")
        except MCPTimeoutError as e:
            logger.error(f"MCP operation timed out: {e}")
"""


class MCPError(Exception):
    """Base exception for MCP-related errors.

    All MCP-specific exceptions inherit from this base class, allowing
    for broad exception handling when needed.

    Example:
        >>> try:
        ...     raise MCPError("Something went wrong with MCP")
        ... except MCPError as e:
        ...     print(f"MCP error occurred: {e}")
        MCP error occurred: Something went wrong with MCP
    """


class MCPConnectionError(MCPError):
    """Raised when MCP server connection fails.

    This exception indicates that the MCP HTTP client could not establish
    or maintain a connection to the MCP server endpoint.

    Example:
        >>> raise MCPConnectionError("Cannot reach MCP server at http://localhost:8000")
        Traceback (most recent call last):
        ...
        MCPConnectionError: Cannot reach MCP server at http://localhost:8000
    """


class MCPTimeoutError(MCPError):
    """Raised when MCP operation times out.

    This exception indicates that an MCP operation (tool call, listing tools, etc.)
    exceeded the configured timeout duration.

    Example:
        >>> raise MCPTimeoutError("Tool call timed out after 30 seconds")
        Traceback (most recent call last):
        ...
        MCPTimeoutError: Tool call timed out after 30 seconds
    """


class MCPToolNotFoundError(MCPError):
    """Raised when requested MCP tool is not available.

    This exception indicates that the requested tool name is not available
    in the MCP server's tool registry.

    Example:
        >>> raise MCPToolNotFoundError("Tool 'invalid-tool' not found in MCP server")
        Traceback (most recent call last):
        ...
        MCPToolNotFoundError: Tool 'invalid-tool' not found in MCP server
    """


class MCPAuthenticationError(MCPError):
    """Raised when MCP authentication fails.

    This exception indicates that authentication with the MCP server failed,
    typically due to invalid or missing authentication tokens.

    Example:
        >>> raise MCPAuthenticationError("Invalid API key for MCP server")
        Traceback (most recent call last):
        ...
        MCPAuthenticationError: Invalid API key for MCP server
    """
