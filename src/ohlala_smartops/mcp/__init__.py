"""Model Context Protocol (MCP) integration.

This package provides MCP client functionality for communicating with MCP servers:
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

__all__ = [
    "MCPAuthenticationError",
    "MCPConnectionError",
    "MCPError",
    "MCPHTTPClient",
    "MCPTimeoutError",
    "MCPToolNotFoundError",
]
