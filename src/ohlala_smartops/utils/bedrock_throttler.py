"""Global Bedrock throttling to prevent AI rate limits.

This module provides rate limiting and concurrency control for AWS Bedrock API calls
to prevent throttling errors. It implements a token bucket algorithm combined with
semaphore-based concurrency limiting.
"""

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Final

logger: Final = logging.getLogger(__name__)


class BedrockThrottler:
    """Global rate limiter specifically for Bedrock API calls.

    Prevents overwhelming Bedrock with too many concurrent AI requests,
    especially when processing multiple instances. Uses a token bucket
    algorithm for rate limiting and semaphores for concurrency control.

    The throttler is configured via environment variables:
    - MAX_CONCURRENT_BEDROCK_CALLS: Maximum concurrent API calls (default: 2)
    - BEDROCK_API_RATE_LIMIT: Tokens per second (default: 0.5)
    - BEDROCK_API_MAX_TOKENS: Maximum token bucket size (default: 5)
    """

    def __init__(self) -> None:
        """Initialize the Bedrock throttler with conservative limits."""
        # Bedrock rate limiting configuration - very conservative for stability
        self.max_concurrent_calls = int(os.getenv("MAX_CONCURRENT_BEDROCK_CALLS", "2"))
        self.tokens_per_second = float(os.getenv("BEDROCK_API_RATE_LIMIT", "0.5"))
        self.max_tokens = int(os.getenv("BEDROCK_API_MAX_TOKENS", "5"))

        # Internal state
        self._semaphore = asyncio.Semaphore(self.max_concurrent_calls)
        self._tokens = float(self.max_tokens)
        self._last_refill = time.time()
        self._token_lock = asyncio.Lock()

        # Metrics
        self._total_requests = 0
        self._throttled_requests = 0

        logger.info(
            f"Bedrock throttler initialized: {self.max_concurrent_calls} concurrent, "
            f"{self.tokens_per_second} tokens/sec"
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
            logger.info(
                f"Bedrock rate limiting: waiting {wait_time:.2f}s for token "
                "(preventing AI throttling)"
            )

        # Wait outside the lock to avoid blocking other operations
        await asyncio.sleep(wait_time)

        # Try again after waiting
        async with self._token_lock:
            await self._refill_tokens()
            if self._tokens >= 1:
                self._tokens -= 1
            else:
                # This shouldn't happen, but be defensive
                logger.warning("Bedrock token still not available after waiting")

    @asynccontextmanager
    async def throttled_bedrock_request(
        self, operation_name: str = "bedrock_call"
    ) -> AsyncGenerator[None]:
        """Context manager for throttled Bedrock API requests.

        This async context manager handles both concurrency limiting (via semaphore)
        and rate limiting (via token bucket). It also detects throttling errors
        and adds recovery delays.

        Args:
            operation_name: Name of the operation for logging purposes. Defaults to "bedrock_call".

        Yields:
            None. The context manager handles throttling transparently.

        Raises:
            Exception: Re-raises any exceptions from the wrapped code, but adds
                recovery delays for throttling errors.

        Example:
            >>> throttler = BedrockThrottler()
            >>> async with throttler.throttled_bedrock_request("generate_response"):
            ...     result = await bedrock_client.call()
        """
        self._total_requests += 1

        try:
            # Acquire semaphore for concurrency limiting
            async with self._semaphore:
                # Wait for token bucket
                await self._wait_for_token()

                logger.debug(
                    f"Bedrock throttler: allowing {operation_name} (tokens: {self._tokens:.1f})"
                )

                start_time = time.time()
                try:
                    yield

                    duration = time.time() - start_time
                    logger.debug(
                        f"Bedrock throttler: {operation_name} completed in {duration:.2f}s"
                    )

                except Exception as e:
                    # Check if this is a throttling error
                    if "throttling" in str(e).lower() or "too many" in str(e).lower():
                        logger.warning(f"Bedrock throttling detected despite throttling: {e}")
                        self._throttled_requests += 1
                        # Add additional delay for recovery
                        await asyncio.sleep(5.0)
                    raise

        except Exception as e:
            logger.error(f"Bedrock throttler error for {operation_name}: {e}")
            raise

    def get_stats(self) -> dict[str, Any]:
        """Get throttling statistics for monitoring.

        Returns:
            Dictionary containing throttling metrics:
            - total_requests: Total number of requests processed
            - throttled_requests: Number of requests that encountered throttling
            - current_tokens: Current number of tokens in the bucket
            - max_concurrent_calls: Maximum concurrent calls allowed
            - tokens_per_second: Rate of token refill

        Example:
            >>> throttler = BedrockThrottler()
            >>> stats = throttler.get_stats()
            >>> print(f"Total requests: {stats['total_requests']}")
        """
        return {
            "total_requests": self._total_requests,
            "throttled_requests": self._throttled_requests,
            "current_tokens": round(self._tokens, 2),
            "max_concurrent_calls": self.max_concurrent_calls,
            "tokens_per_second": self.tokens_per_second,
        }


# Global singleton instance
_bedrock_throttler: BedrockThrottler | None = None


def get_bedrock_throttler() -> BedrockThrottler:
    """Get the global Bedrock throttler singleton instance.

    Returns:
        The global BedrockThrottler instance, creating it if necessary.

    Example:
        >>> throttler = get_bedrock_throttler()
        >>> stats = throttler.get_stats()
    """
    global _bedrock_throttler  # noqa: PLW0603
    if _bedrock_throttler is None:
        _bedrock_throttler = BedrockThrottler()
    return _bedrock_throttler


def throttled_bedrock_call(
    operation_name: str = "bedrock_call",
) -> AbstractAsyncContextManager[None]:
    """Convenience context manager for throttled Bedrock API calls.

    Args:
        operation_name: Name of the operation for logging. Defaults to "bedrock_call".

    Returns:
        Async context manager for throttled Bedrock requests.

    Example:
        >>> async with throttled_bedrock_call("generate_response"):
        ...     result = await bedrock_client.call()
    """
    throttler = get_bedrock_throttler()
    return throttler.throttled_bedrock_request(operation_name)
