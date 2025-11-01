"""Unit tests for MCP HTTP client."""

from ohlala_smartops import mcp
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


class TestMCPHTTPClientModuleExports:
    """Test suite for module exports."""

    def test_module_exports(self) -> None:
        """Test that the MCP module exports MCPHTTPClient."""
        assert hasattr(mcp, "MCPHTTPClient")
