"""Global rate limiting and throttling for AWS API calls.

This module provides global rate limiting with circuit breaker pattern for all AWS API
calls across the application. It uses a token bucket algorithm for rate limiting and
semaphores for concurrency control, combined with a circuit breaker to prevent
cascade failures.
"""

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Final

logger: Final = logging.getLogger(__name__)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests.

    This exception indicates that the circuit breaker is currently open
    due to a recent trip, and requests are being blocked until the timeout expires.
    """


class CircuitBreakerTrippedError(Exception):
    """Raised when circuit breaker trips due to too many failures.

    This exception is raised when the consecutive failure count reaches
    the configured threshold, triggering the circuit breaker.
    """


class GlobalThrottler:
    """Global rate limiter with token bucket algorithm and circuit breaker.

    This ensures all AWS API calls across the entire application respect rate limits,
    preventing 429 errors and providing coordinated backoff with circuit breaker
    protection against cascade failures.

    Configuration via environment variables:
    - MAX_CONCURRENT_AWS_CALLS: Maximum concurrent calls (default: 8)
    - AWS_API_RATE_LIMIT: Tokens per second (default: 15.0)
    - AWS_API_MAX_TOKENS: Maximum token bucket size (default: 30)
    - AWS_CIRCUIT_BREAKER_ENABLED: Enable circuit breaker (default: false)
    - AWS_CIRCUIT_BREAKER_THRESHOLD: Failure threshold (default: 100)
    - AWS_CIRCUIT_BREAKER_TIMEOUT: Circuit open timeout in seconds (default: 10.0)
    """

    def __init__(self) -> None:
        """Initialize the global throttler with configuration from environment variables."""
        # Rate limiting configuration
        self.max_concurrent_calls = int(os.getenv("MAX_CONCURRENT_AWS_CALLS", "8"))
        self.tokens_per_second = float(os.getenv("AWS_API_RATE_LIMIT", "15.0"))
        self.max_tokens = int(os.getenv("AWS_API_MAX_TOKENS", "30"))

        # Circuit breaker configuration
        self.circuit_breaker_enabled = (
            os.getenv("AWS_CIRCUIT_BREAKER_ENABLED", "false").lower() == "true"
        )
        self.circuit_breaker_threshold = int(os.getenv("AWS_CIRCUIT_BREAKER_THRESHOLD", "100"))
        self.circuit_breaker_timeout = float(os.getenv("AWS_CIRCUIT_BREAKER_TIMEOUT", "10.0"))

        # Internal state
        self._semaphore = asyncio.Semaphore(self.max_concurrent_calls)
        self._tokens = float(self.max_tokens)
        self._last_refill = time.time()
        self._token_lock = asyncio.Lock()

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._circuit_lock = asyncio.Lock()

        # Metrics
        self._total_requests = 0
        self._throttled_requests = 0
        self._circuit_breaker_trips = 0

        logger.info(
            f"Global throttler initialized: {self.max_concurrent_calls} concurrent, "
            f"{self.tokens_per_second} tokens/sec, circuit breaker: {self.circuit_breaker_enabled}"
        )

    async def _refill_tokens(self) -> None:
        """Refill token bucket based on elapsed time.

        Implements the token bucket refill logic, adding tokens proportional
        to the time elapsed since the last refill.
        """
        now = time.time()
        elapsed = now - self._last_refill

        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.tokens_per_second
        self._tokens = min(float(self.max_tokens), self._tokens + tokens_to_add)
        self._last_refill = now

    async def _wait_for_token(self) -> None:
        """Wait for an available token, implementing token bucket algorithm.

        This method checks if a token is available in the bucket. If not,
        it calculates the wait time and sleeps before trying again.
        """
        async with self._token_lock:
            await self._refill_tokens()

            if self._tokens >= 1:
                self._tokens -= 1
                return

            # Calculate how long to wait for next token
            wait_time = 1.0 / self.tokens_per_second
            logger.info(f"Rate limiting: waiting {wait_time:.2f}s for token (scaling gracefully)")

        # Wait outside the lock to avoid blocking other operations
        await asyncio.sleep(wait_time)

        # Try again after waiting
        async with self._token_lock:
            await self._refill_tokens()
            if self._tokens >= 1:
                self._tokens -= 1
            else:
                # This shouldn't happen, but be defensive
                logger.warning("Token still not available after waiting")

    async def _check_circuit_breaker(self) -> None:
        """Check if circuit breaker is open and should block requests.

        Raises:
            CircuitBreakerOpenError: If circuit breaker is currently open.
        """
        if not self.circuit_breaker_enabled:
            return

        async with self._circuit_lock:
            now = time.time()

            # Check if circuit breaker timeout has expired
            if self._circuit_open_until > now:
                remaining = self._circuit_open_until - now
                raise CircuitBreakerOpenError(f"Circuit breaker open for {remaining:.1f}s more")

            # Reset circuit breaker if timeout expired
            if self._circuit_open_until > 0 and now >= self._circuit_open_until:
                logger.info("Circuit breaker reset - allowing requests")
                self._circuit_open_until = 0.0
                self._consecutive_failures = 0

    async def _record_failure(self) -> None:
        """Record a failure and potentially trip circuit breaker.

        Raises:
            CircuitBreakerTrippedError: If consecutive failures reach threshold.
        """
        if not self.circuit_breaker_enabled:
            return

        async with self._circuit_lock:
            self._consecutive_failures += 1

            if self._consecutive_failures >= self.circuit_breaker_threshold:
                self._circuit_open_until = time.time() + self.circuit_breaker_timeout
                self._circuit_breaker_trips += 1
                logger.warning(
                    f"Circuit breaker TRIPPED after {self._consecutive_failures} failures. "
                    f"Blocking requests for {self.circuit_breaker_timeout}s"
                )
                raise CircuitBreakerTrippedError(
                    f"Circuit breaker tripped after {self._consecutive_failures} "
                    "consecutive failures"
                )

    async def _record_success(self) -> None:
        """Record a successful request and reset failure counter."""
        if not self.circuit_breaker_enabled:
            return

        async with self._circuit_lock:
            self._consecutive_failures = 0

    @asynccontextmanager
    async def throttled_request(self, operation_name: str = "aws_api_call") -> AsyncGenerator[None]:
        """Context manager for throttled AWS API requests with circuit breaker.

        This async context manager handles concurrency limiting, rate limiting,
        and circuit breaker logic. It detects rate limit errors and adds recovery
        delays, while other errors contribute to the circuit breaker failure count.

        Args:
            operation_name: Name of the operation for logging purposes.
                Defaults to "aws_api_call".

        Yields:
            None. The context manager handles throttling transparently.

        Raises:
            CircuitBreakerOpenError: If circuit breaker is currently open.
            CircuitBreakerTrippedError: If this request trips the circuit breaker.
            Exception: Re-raises any exceptions from the wrapped code.

        Example:
            >>> throttler = GlobalThrottler()
            >>> async with throttler.throttled_request("get-instances"):
            ...     result = await make_aws_call()
        """
        self._total_requests += 1

        try:
            # Check circuit breaker first
            await self._check_circuit_breaker()

            # Acquire semaphore for concurrency limiting
            async with self._semaphore:
                # Wait for token bucket
                await self._wait_for_token()

                logger.debug(f"Throttler: allowing {operation_name} (tokens: {self._tokens:.1f})")

                start_time = time.time()
                try:
                    yield

                    # Record success
                    await self._record_success()

                    duration = time.time() - start_time
                    logger.debug(f"Throttler: {operation_name} completed in {duration:.2f}s")

                except Exception as e:
                    # Check if this is a rate limiting error - delay instead of failing
                    if "rate limit" in str(e).lower() or "429" in str(e):
                        logger.warning(f"Rate limit detected, applying additional delay: {e}")
                        self._throttled_requests += 1
                        # Don't record as failure for circuit breaker - just add delay
                        await asyncio.sleep(2.0)  # Additional delay for rate limit recovery
                    else:
                        # Only record non-rate-limit errors as failures
                        await self._record_failure()
                    raise

        except (CircuitBreakerOpenError, CircuitBreakerTrippedError):
            # Circuit breaker errors - don't retry
            raise
        except Exception as e:
            logger.error(f"Throttler error for {operation_name}: {e}")
            raise

    def get_stats(self) -> dict[str, Any]:
        """Get throttling statistics for monitoring.

        Returns:
            Dictionary containing throttling metrics:
            - total_requests: Total number of requests processed
            - throttled_requests: Number of requests that hit rate limits
            - circuit_breaker_trips: Number of times circuit breaker tripped
            - current_tokens: Current number of tokens in the bucket
            - max_concurrent_calls: Maximum concurrent calls allowed
            - tokens_per_second: Rate of token refill
            - consecutive_failures: Current consecutive failure count
            - circuit_open: Whether circuit breaker is currently open

        Example:
            >>> throttler = GlobalThrottler()
            >>> stats = throttler.get_stats()
            >>> print(f"Total requests: {stats['total_requests']}")
        """
        return {
            "total_requests": self._total_requests,
            "throttled_requests": self._throttled_requests,
            "circuit_breaker_trips": self._circuit_breaker_trips,
            "current_tokens": round(self._tokens, 2),
            "max_concurrent_calls": self.max_concurrent_calls,
            "tokens_per_second": self.tokens_per_second,
            "consecutive_failures": self._consecutive_failures,
            "circuit_open": (
                self._circuit_open_until > time.time() if self.circuit_breaker_enabled else False
            ),
        }

    async def reset_circuit_breaker(self) -> None:
        """Manually reset circuit breaker (for admin use).

        Resets the circuit breaker state, clearing the failure counter
        and reopening the circuit. Useful for manual intervention after
        resolving underlying issues.

        Example:
            >>> throttler = GlobalThrottler()
            >>> await throttler.reset_circuit_breaker()
        """
        async with self._circuit_lock:
            self._circuit_open_until = 0.0
            self._consecutive_failures = 0
            logger.info("Circuit breaker manually reset")


# Global singleton instance
_global_throttler: GlobalThrottler | None = None


def get_global_throttler() -> GlobalThrottler:
    """Get the global throttler singleton instance.

    Returns:
        The global GlobalThrottler instance, creating it if necessary.

    Example:
        >>> throttler = get_global_throttler()
        >>> stats = throttler.get_stats()
    """
    global _global_throttler  # noqa: PLW0603
    if _global_throttler is None:
        _global_throttler = GlobalThrottler()
    return _global_throttler


def throttled_aws_call(operation_name: str = "aws_api_call") -> AbstractAsyncContextManager[None]:
    """Convenience context manager for throttled AWS API calls.

    Args:
        operation_name: Name of the operation for logging. Defaults to "aws_api_call".

    Returns:
        Async context manager for throttled AWS requests with circuit breaker.

    Example:
        >>> async with throttled_aws_call("list-instances"):
        ...     result = await mcp_call()
    """
    throttler = get_global_throttler()
    return throttler.throttled_request(operation_name)
