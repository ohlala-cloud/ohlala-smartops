"""Model Context Protocol (MCP) integration.

This package provides MCP client functionality for communicating with MCP servers:
- MCP Manager for server orchestration and tool execution
- HTTP client with retry logic and error handling
- Exception hierarchy for MCP-specific errors
- JSON-RPC 2.0 protocol implementation
"""

from ohlala_smartops.mcp.exceptions import (
    MCPAuthenticationError,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)
from ohlala_smartops.mcp.http_client import MCPHTTPClient
from ohlala_smartops.mcp.manager import MCPManager

__all__ = [
    "MCPAuthenticationError",
    "MCPConnectionError",
    "MCPError",
    "MCPHTTPClient",
    "MCPManager",
    "MCPTimeoutError",
    "MCPToolNotFoundError",
]
