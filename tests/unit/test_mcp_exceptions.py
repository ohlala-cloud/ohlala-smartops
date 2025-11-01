"""Unit tests for MCP exceptions."""

from ohlala_smartops.mcp.exceptions import (
    MCPAuthenticationError,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)


def test_exception_hierarchy() -> None:
    """Test that all MCP exceptions inherit from MCPError."""
    assert issubclass(MCPConnectionError, MCPError)
    assert issubclass(MCPTimeoutError, MCPError)
    assert issubclass(MCPAuthenticationError, MCPError)
    assert issubclass(MCPToolNotFoundError, MCPError)


def test_mcp_error() -> None:
    """Test MCPError can be raised with message."""
    error = MCPError("Test error")
    assert str(error) == "Test error"
    assert isinstance(error, Exception)


def test_mcp_connection_error() -> None:
    """Test MCPConnectionError can be raised."""
    error = MCPConnectionError("Connection failed")
    assert str(error) == "Connection failed"
    assert isinstance(error, MCPError)


def test_mcp_timeout_error() -> None:
    """Test MCPTimeoutError can be raised."""
    error = MCPTimeoutError("Operation timed out")
    assert str(error) == "Operation timed out"
    assert isinstance(error, MCPError)


def test_mcp_authentication_error() -> None:
    """Test MCPAuthenticationError can be raised."""
    error = MCPAuthenticationError("Invalid credentials")
    assert str(error) == "Invalid credentials"
    assert isinstance(error, MCPError)


def test_mcp_tool_not_found_error() -> None:
    """Test MCPToolNotFoundError can be raised."""
    error = MCPToolNotFoundError("Tool not found")
    assert str(error) == "Tool not found"
    assert isinstance(error, MCPError)


def test_module_exports() -> None:
    """Test that the MCP module exports all exception classes."""
    from ohlala_smartops import mcp

    assert hasattr(mcp, "MCPError")
    assert hasattr(mcp, "MCPConnectionError")
    assert hasattr(mcp, "MCPTimeoutError")
    assert hasattr(mcp, "MCPAuthenticationError")
    assert hasattr(mcp, "MCPToolNotFoundError")
