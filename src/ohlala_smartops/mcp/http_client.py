"""HTTP client for MCP servers using JSON-RPC protocol.

This module provides an async HTTP client for communicating with Model Context Protocol
(MCP) servers using JSON-RPC 2.0 over HTTP. It includes exponential backoff retry logic,
rate limit handling, and comprehensive error handling.

Example:
    Basic usage with context manager::

        async with MCPHTTPClient("http://localhost:8000/rpc", api_key="secret") as client:
            # List available tools
            tools = await client.list_tools()

            # Call a specific tool
            result = await client.call_tool("list-instances", {})

            # Health check
            is_healthy = await client.health_check()
"""

import asyncio
import logging
import random
from typing import Any, Final

import aiohttp

from ohlala_smartops.config import get_settings
from ohlala_smartops.mcp.exceptions import (
    MCPAuthenticationError,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
)

logger: Final = logging.getLogger(__name__)

# JSON-RPC error codes
_JSONRPC_RATE_LIMIT_ERROR: Final[int] = -32002
_JSONRPC_AUTH_ERROR: Final[int] = -32003

# HTTP status codes that should trigger retries
_RETRYABLE_HTTP_CODES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})


class MCPHTTPClient:
    """HTTP client for MCP servers.

    Provides async communication with MCP servers using JSON-RPC 2.0 protocol
    over HTTP. Includes automatic retry logic with exponential backoff for
    transient failures, rate limiting, and network errors.

    Attributes:
        base_url: Base URL of the MCP server (e.g., "http://localhost:8000/rpc").
        api_key: Optional API key for authentication.
        session: aiohttp client session (initialized via context manager).
        max_retries: Maximum number of retry attempts for failed requests.
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay in seconds between retries.
        backoff_multiplier: Multiplier for exponential backoff calculation.

    Example:
        >>> async with MCPHTTPClient("http://localhost:8000/rpc") as client:
        ...     tools = await client.list_tools()
        ...     print(f"Found {len(tools)} tools")
        Found 15 tools
    """

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        """Initialize MCP HTTP client.

        Args:
            base_url: Base URL of the MCP server JSON-RPC endpoint.
            api_key: Optional API key for server authentication.
        """
        self.base_url = base_url
        self.api_key = api_key
        self.session: aiohttp.ClientSession | None = None
        self._request_id = 0

        # Retry configuration from settings
        settings = get_settings()
        self.max_retries = settings.mcp_max_retries
        self.base_delay = settings.mcp_base_delay
        self.max_delay = settings.mcp_max_delay
        self.backoff_multiplier = settings.mcp_backoff_multiplier

    async def __aenter__(self) -> "MCPHTTPClient":
        """Enter async context manager, creating HTTP session.

        Returns:
            Self for use in async with statement.
        """
        # Aggressive timeout to prevent hung operations during overload
        timeout = aiohttp.ClientTimeout(
            total=30,  # Total request timeout
            connect=5,  # Connection timeout
            sock_read=10,  # Socket read timeout
        )
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async context manager, closing HTTP session.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        """
        if self.session:
            await self.session.close()

    def _next_request_id(self) -> int:
        """Get next request ID for JSON-RPC.

        Returns:
            Monotonically increasing request ID.
        """
        self._request_id += 1
        return self._request_id

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter.

        Implements exponential backoff with jitter to prevent thundering herd
        problem when multiple clients retry simultaneously.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Delay in seconds before next retry attempt.

        Example:
            >>> client = MCPHTTPClient("http://localhost:8000")
            >>> client._calculate_backoff_delay(0)  # First retry
            # Returns ~1.0 seconds ± 25% jitter
            >>> client._calculate_backoff_delay(3)  # Fourth retry
            # Returns ~8.0 seconds ± 25% jitter (capped at max_delay)
        """
        delay = self.base_delay * (self.backoff_multiplier**attempt)
        delay = min(delay, self.max_delay)
        # Add jitter (±25% of the delay) to prevent thundering herd
        jitter = delay * 0.25 * (2 * random.random() - 1)  # nosec B311
        return max(0.1, delay + jitter)

    def _is_retryable_error(self, status_code: int) -> bool:
        """Check if HTTP status code indicates a retryable error.

        Args:
            status_code: HTTP status code.

        Returns:
            True if the error should trigger a retry.

        Example:
            >>> client = MCPHTTPClient("http://localhost:8000")
            >>> client._is_retryable_error(429)  # Rate limit
            True
            >>> client._is_retryable_error(503)  # Service unavailable
            True
            >>> client._is_retryable_error(400)  # Bad request
            False
        """
        return status_code in _RETRYABLE_HTTP_CODES

    async def _send_request(  # noqa: PLR0912, PLR0915
        self,
        method: str,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """Send JSON-RPC request to MCP server with exponential backoff retry.

        Args:
            method: JSON-RPC method name (e.g., "tools/list").
            params: Optional parameters for the RPC method.
            extra_headers: Optional additional HTTP headers.

        Returns:
            Result from JSON-RPC response.

        Raises:
            MCPConnectionError: If connection to server fails after all retries.
            MCPTimeoutError: If request times out after all retries.
            MCPAuthenticationError: If authentication fails (non-retryable).
            MCPError: For other JSON-RPC or protocol errors.

        Example:
            >>> async with MCPHTTPClient("http://localhost:8000/rpc") as client:
            ...     result = await client._send_request("tools/list")
        """
        if not self.session:
            raise MCPError("Session not initialized - use async with context manager")

        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "id": self._next_request_id(),
        }
        if params:
            request["params"] = params

        logger.debug(f"Sending JSON-RPC request: {method}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"MCP HTTP Client retry config: max_retries={self.max_retries}, "
                f"base_delay={self.base_delay}s"
            )

        logger.debug(f"🌐 HTTP CLIENT: Starting {method} (max_retries={self.max_retries})")

        # Add authentication header if API key is provided
        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        # Add any extra headers
        if extra_headers:
            headers.update(extra_headers)

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with self.session.post(self.base_url, json=request, headers=headers) as resp:
                    # Always try to parse JSON first, regardless of HTTP status
                    # The MCP server might return HTTP 429 with JSON-RPC error details
                    try:
                        response = await resp.json()

                        # Check for JSON-RPC error first
                        if "error" in response:
                            error = response["error"]
                            error_code = error.get("code", "unknown")
                            error_message = error.get("message", "unknown error")

                            # Check if this is a rate limit error - retry these
                            if (
                                error_code == _JSONRPC_RATE_LIMIT_ERROR
                                and attempt < self.max_retries
                            ):
                                delay = self._calculate_backoff_delay(attempt)
                                logger.warning(
                                    f"Rate limit error (JSON-RPC {error_code}) on attempt "
                                    f"{attempt + 1}/{self.max_retries + 1} for {method}, "
                                    f"retrying in {delay:.2f}s"
                                )
                                await asyncio.sleep(delay)
                                continue

                            # Check if this is an authorization error - don't retry these
                            if error_code == _JSONRPC_AUTH_ERROR:
                                logger.error(
                                    f"Authorization error (JSON-RPC {error_code}) for "
                                    f"{method}: {error_message}"
                                )
                                raise MCPAuthenticationError(
                                    f"JSON-RPC authorization error {error_code}: {error_message}"
                                ) from None

                            # Non-retryable JSON-RPC error or max retries exceeded
                            raise MCPError(
                                f"JSON-RPC error {error_code}: {error_message}"
                            ) from None

                        # Success - HTTP 200 with valid JSON-RPC response
                        if attempt > 0:
                            logger.info(
                                f"🌐 HTTP CLIENT: {method} succeeded after {attempt + 1} attempts"
                            )
                        else:
                            logger.debug(f"🌐 HTTP CLIENT: {method} succeeded on first attempt")
                        return response.get("result")

                    except (MCPError, MCPAuthenticationError):
                        # Re-raise our custom exceptions
                        raise
                    except Exception as json_error:
                        # JSON parsing failed - check HTTP status and handle accordingly
                        if resp.status != 200:
                            error_text = await resp.text()

                            # Check if this is a retryable HTTP error
                            if self._is_retryable_error(resp.status) and attempt < self.max_retries:
                                delay = self._calculate_backoff_delay(attempt)
                                logger.warning(
                                    f"HTTP {resp.status} error on attempt "
                                    f"{attempt + 1}/{self.max_retries + 1} for {method}, "
                                    f"retrying in {delay:.2f}s: {error_text[:100]}"
                                )
                                await asyncio.sleep(delay)
                                continue

                            # Non-retryable error or max retries exceeded
                            if resp.status in {401, 403}:
                                raise MCPAuthenticationError(
                                    f"HTTP authentication error {resp.status}: {error_text}"
                                ) from json_error

                            raise MCPConnectionError(
                                f"HTTP error {resp.status}: {error_text}"
                            ) from json_error

                        # HTTP 200 but JSON parsing failed - retry if possible
                        if attempt < self.max_retries:
                            delay = self._calculate_backoff_delay(attempt)
                            logger.warning(
                                f"JSON parse error on attempt {attempt + 1}/{self.max_retries + 1} "
                                f"for {method}, retrying in {delay:.2f}s: {json_error}"
                            )
                            await asyncio.sleep(delay)
                            continue

                        raise MCPError(f"JSON parse error: {json_error}") from json_error

            except (MCPError, MCPAuthenticationError):
                # Re-raise our custom exceptions
                raise
            except Exception as e:
                last_exception = e

                # Check if this is a network error that should be retried
                if attempt < self.max_retries and isinstance(
                    e, aiohttp.ClientError | asyncio.TimeoutError
                ):
                    delay = self._calculate_backoff_delay(attempt)
                    error_type = "Timeout" if isinstance(e, asyncio.TimeoutError) else "Network"
                    logger.warning(
                        f"{error_type} error on attempt {attempt + 1}/{self.max_retries + 1} "
                        f"for {method}, retrying in {delay:.2f}s: {str(e)[:100]}"
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable error or max retries exceeded
                if isinstance(e, asyncio.TimeoutError):
                    raise MCPTimeoutError(f"Request timed out after {attempt + 1} attempts") from e
                raise MCPConnectionError(f"Connection error: {e}") from e

        # If we get here, all retries were exhausted
        logger.error(f"🌐 HTTP CLIENT: All {self.max_retries + 1} attempts failed for {method}")
        if last_exception:
            logger.error(f"🌐 HTTP CLIENT: Final error: {last_exception}")
            if isinstance(last_exception, asyncio.TimeoutError):
                raise MCPTimeoutError(
                    f"Request timed out after {self.max_retries + 1} attempts"
                ) from last_exception
            raise MCPConnectionError(
                f"All retry attempts failed: {last_exception}"
            ) from last_exception

        raise MCPError(f"All {self.max_retries + 1} attempts failed")

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from MCP server.

        Returns:
            List of tool definitions with name, description, and input schema.

        Raises:
            MCPError: If listing tools fails.

        Example:
            >>> async with MCPHTTPClient("http://localhost:8000/rpc") as client:
            ...     tools = await client.list_tools()
            ...     for tool in tools:
            ...         print(f"- {tool['name']}: {tool.get('description', 'No description')}")
        """
        result = await self._send_request("tools/list")
        tools: list[dict[str, Any]] = result.get("tools", [])
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """Call a specific tool on the MCP server.

        Args:
            name: Name of the tool to call.
            arguments: Arguments to pass to the tool.
            extra_headers: Optional additional HTTP headers for this specific call.

        Returns:
            Result from the tool execution.

        Raises:
            MCPError: If tool execution fails.

        Example:
            >>> async with MCPHTTPClient("http://localhost:8000/rpc") as client:
            ...     result = await client.call_tool("list-instances", {"region": "us-east-1"})
            ...     print(f"Found {len(result['instances'])} instances")
        """
        params = {"name": name, "arguments": arguments}
        return await self._send_request("tools/call", params, extra_headers)

    async def health_check(self) -> bool:
        """Check if MCP server is healthy.

        Returns:
            True if server responds with HTTP 200 to /health endpoint.

        Example:
            >>> async with MCPHTTPClient("http://localhost:8000/rpc") as client:
            ...     if await client.health_check():
            ...         print("Server is healthy")
            ...     else:
            ...         print("Server is down")
        """
        try:
            # Extract base URL without trailing path
            health_url = self.base_url
            if health_url.endswith("/"):
                health_url = health_url[:-1]
            # If base_url has a path component, remove it
            if "://" in health_url:
                proto, rest = health_url.split("://", 1)
                if "/" in rest:
                    host = rest.split("/", 1)[0]
                    health_url = f"{proto}://{host}"

            health_url = f"{health_url}/health"

            # Use session if available, otherwise create temporary one
            if self.session:
                async with self.session.get(health_url) as resp:
                    status: int = resp.status
                    return status == 200
            else:
                async with (
                    aiohttp.ClientSession() as temp_session,
                    temp_session.get(health_url) as resp,
                ):
                    status = resp.status
                    return status == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
