"""Tests for Bedrock API throttling utilities."""

import asyncio
import logging
import os
import time
from unittest.mock import patch

import pytest

from ohlala_smartops.utils.bedrock_throttler import (
    BedrockThrottler,
    get_bedrock_throttler,
    throttled_bedrock_call,
)


class TestBedrockThrottler:
    """Test suite for BedrockThrottler class."""

    def test_initialization_default(self) -> None:
        """Test BedrockThrottler initialization with default values."""
        throttler = BedrockThrottler()

        assert throttler.max_concurrent_calls == 2  # default
        assert throttler.tokens_per_second == 0.5  # default
        assert throttler.max_tokens == 5  # default
        assert throttler._tokens == 5.0
        assert throttler._total_requests == 0
        assert throttler._throttled_requests == 0

    @patch.dict(
        os.environ,
        {
            "MAX_CONCURRENT_BEDROCK_CALLS": "5",
            "BEDROCK_API_RATE_LIMIT": "2.0",
            "BEDROCK_API_MAX_TOKENS": "10",
        },
    )
    def test_initialization_custom_env(self) -> None:
        """Test BedrockThrottler initialization with environment variables."""
        throttler = BedrockThrottler()

        assert throttler.max_concurrent_calls == 5
        assert throttler.tokens_per_second == 2.0
        assert throttler.max_tokens == 10
        assert throttler._tokens == 10.0

    @pytest.mark.asyncio
    async def test_refill_tokens_immediate(self) -> None:
        """Test token refill immediately after initialization."""
        throttler = BedrockThrottler()
        initial_tokens = throttler._tokens

        await throttler._refill_tokens()

        # Tokens should not change significantly (minimal time elapsed)
        assert abs(throttler._tokens - initial_tokens) < 0.1

    @pytest.mark.asyncio
    async def test_refill_tokens_after_delay(self) -> None:
        """Test token refill after a delay."""
        throttler = BedrockThrottler()

        # Consume all tokens
        throttler._tokens = 0.0
        throttler._last_refill = time.time() - 2.0  # 2 seconds ago

        await throttler._refill_tokens()

        # Should have refilled: 2 seconds * 0.5 tokens/sec = 1.0 token
        assert throttler._tokens >= 0.9
        assert throttler._tokens <= 1.1

    @pytest.mark.asyncio
    async def test_refill_tokens_max_limit(self) -> None:
        """Test that token refill respects maximum limit."""
        throttler = BedrockThrottler()

        # Simulate long delay that would exceed max tokens
        throttler._tokens = 0.0
        throttler._last_refill = time.time() - 100.0  # 100 seconds ago

        await throttler._refill_tokens()

        # Should not exceed max_tokens
        assert throttler._tokens == float(throttler.max_tokens)

    @pytest.mark.asyncio
    async def test_wait_for_token_available(self) -> None:
        """Test waiting for a token when one is available."""
        throttler = BedrockThrottler()

        start_time = time.time()
        await throttler._wait_for_token()
        elapsed = time.time() - start_time

        # Should return immediately (< 0.1 seconds)
        assert elapsed < 0.1
        # Should have consumed one token
        assert throttler._tokens < float(throttler.max_tokens)

    @pytest.mark.asyncio
    async def test_wait_for_token_unavailable(self) -> None:
        """Test waiting for a token when none are available."""
        throttler = BedrockThrottler()

        # Consume all tokens
        throttler._tokens = 0.0

        start_time = time.time()
        await throttler._wait_for_token()
        elapsed = time.time() - start_time

        # Should have waited at least 1/tokens_per_second (2 seconds for 0.5 tps)
        expected_wait = 1.0 / throttler.tokens_per_second
        assert elapsed >= expected_wait * 0.9  # Allow 10% margin

    @pytest.mark.asyncio
    async def test_throttled_bedrock_request_success(self) -> None:
        """Test successful throttled request."""
        throttler = BedrockThrottler()
        initial_requests = throttler._total_requests

        async with throttler.throttled_bedrock_request("test_operation"):
            # Simulate some work
            await asyncio.sleep(0.01)

        # Should have incremented request counter
        assert throttler._total_requests == initial_requests + 1
        # No throttling should have occurred
        assert throttler._throttled_requests == 0

    @pytest.mark.asyncio
    async def test_throttled_bedrock_request_exception(self) -> None:
        """Test throttled request with exception."""
        throttler = BedrockThrottler()

        with pytest.raises(ValueError, match="Test error"):
            async with throttler.throttled_bedrock_request("test_operation"):
                raise ValueError("Test error")

        # Should have incremented request counter
        assert throttler._total_requests == 1

    @pytest.mark.asyncio
    async def test_throttled_bedrock_request_throttling_error(self) -> None:
        """Test handling of throttling errors."""
        throttler = BedrockThrottler()
        initial_throttled = throttler._throttled_requests

        start_time = time.time()

        with pytest.raises(Exception, match="Throttling"):
            async with throttler.throttled_bedrock_request("test_operation"):
                raise Exception("Throttling limit exceeded")

        elapsed = time.time() - start_time

        # Should have incremented throttled counter
        assert throttler._throttled_requests == initial_throttled + 1
        # Should have added 5-second recovery delay
        assert elapsed >= 4.9  # Allow small margin

    @pytest.mark.asyncio
    async def test_throttled_bedrock_request_too_many_error(self) -> None:
        """Test handling of 'too many requests' errors."""
        throttler = BedrockThrottler()
        initial_throttled = throttler._throttled_requests

        start_time = time.time()

        with pytest.raises(Exception, match=r"(?i)too many"):  # Case-insensitive
            async with throttler.throttled_bedrock_request("test_operation"):
                raise Exception("Too many requests")

        elapsed = time.time() - start_time

        # Should have incremented throttled counter
        assert throttler._throttled_requests == initial_throttled + 1
        # Should have added 5-second recovery delay
        assert elapsed >= 4.9

    @pytest.mark.asyncio
    async def test_concurrent_requests_limited(self) -> None:
        """Test that concurrent requests are limited by semaphore."""
        throttler = BedrockThrottler()
        throttler.max_concurrent_calls = 2

        concurrent_count = 0
        max_concurrent = 0

        async def test_operation() -> None:
            nonlocal concurrent_count, max_concurrent
            async with throttler.throttled_bedrock_request("test"):
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
                await asyncio.sleep(0.1)
                concurrent_count -= 1

        # Launch 5 concurrent operations
        await asyncio.gather(*[test_operation() for _ in range(5)])

        # Maximum concurrent should not exceed limit
        assert max_concurrent <= throttler.max_concurrent_calls

    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self) -> None:
        """Test that rate limiting is enforced."""
        throttler = BedrockThrottler()
        throttler.max_concurrent_calls = 10  # High limit to test rate limiting
        throttler.tokens_per_second = 2.0  # 2 requests per second
        throttler.max_tokens = 2

        start_time = time.time()

        # Make 4 requests (should take ~2 seconds due to rate limiting)
        for _ in range(4):
            async with throttler.throttled_bedrock_request("test"):
                pass

        elapsed = time.time() - start_time

        # Should have taken at least 1 second (4 requests / 2 per second = 2 seconds,
        # minus initial tokens)
        assert elapsed >= 0.9

    def test_get_stats_initial(self) -> None:
        """Test getting stats from a new throttler."""
        throttler = BedrockThrottler()
        stats = throttler.get_stats()

        assert stats["total_requests"] == 0
        assert stats["throttled_requests"] == 0
        assert stats["current_tokens"] == 5.0  # default max_tokens
        assert stats["max_concurrent_calls"] == 2
        assert stats["tokens_per_second"] == 0.5

    @pytest.mark.asyncio
    async def test_get_stats_after_requests(self) -> None:
        """Test getting stats after processing requests."""
        throttler = BedrockThrottler()

        # Make some requests
        for _ in range(3):
            async with throttler.throttled_bedrock_request("test"):
                pass

        stats = throttler.get_stats()

        assert stats["total_requests"] == 3
        assert stats["throttled_requests"] == 0
        assert isinstance(stats["current_tokens"], float)

    @pytest.mark.asyncio
    async def test_logging_debug_messages(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that debug logging occurs."""
        throttler = BedrockThrottler()

        with caplog.at_level(logging.DEBUG):
            async with throttler.throttled_bedrock_request("test_op"):
                pass

        # Should have debug logs
        assert any("allowing test_op" in record.message for record in caplog.records)
        assert any("completed" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logging_rate_limit_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that rate limit warnings are logged."""
        throttler = BedrockThrottler()
        throttler._tokens = 0.0  # No tokens available

        with caplog.at_level(logging.INFO):
            async with throttler.throttled_bedrock_request("test"):
                pass

        # Should have rate limiting warning
        assert any(
            "waiting" in record.message and "token" in record.message for record in caplog.records
        )


class TestGlobalSingleton:
    """Test suite for global singleton functions."""

    def test_get_bedrock_throttler_creates_instance(self) -> None:
        """Test that get_bedrock_throttler creates an instance."""
        # Reset global instance
        import ohlala_smartops.utils.bedrock_throttler as module  # noqa: PLC0415

        module._bedrock_throttler = None

        throttler = get_bedrock_throttler()

        assert isinstance(throttler, BedrockThrottler)

    def test_get_bedrock_throttler_returns_singleton(self) -> None:
        """Test that get_bedrock_throttler returns the same instance."""
        throttler1 = get_bedrock_throttler()
        throttler2 = get_bedrock_throttler()

        assert throttler1 is throttler2

    @pytest.mark.asyncio
    async def test_throttled_bedrock_call_convenience(self) -> None:
        """Test convenience function for throttled calls."""
        call_executed = False

        async with throttled_bedrock_call("test_operation"):
            call_executed = True

        assert call_executed is True

    @pytest.mark.asyncio
    async def test_throttled_bedrock_call_uses_singleton(self) -> None:
        """Test that convenience function uses the singleton."""
        throttler = get_bedrock_throttler()
        initial_requests = throttler._total_requests

        async with throttled_bedrock_call("test"):
            pass

        # Should have incremented the singleton's counter
        assert throttler._total_requests == initial_requests + 1


class TestEdgeCases:
    """Test suite for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_multiple_token_waits(self) -> None:
        """Test multiple waits for tokens."""
        throttler = BedrockThrottler()
        throttler._tokens = 0.0

        # First wait should work
        await throttler._wait_for_token()

        # Consume the token again
        throttler._tokens = 0.0

        # Second wait should also work
        await throttler._wait_for_token()

        assert True  # Successfully waited twice

    @pytest.mark.asyncio
    async def test_concurrent_token_waits(self) -> None:
        """Test concurrent waits for tokens with lock contention."""
        throttler = BedrockThrottler()
        throttler.tokens_per_second = 1.0  # Faster for testing

        # Launch multiple concurrent waits
        results = await asyncio.gather(
            *[throttler._wait_for_token() for _ in range(3)], return_exceptions=False
        )

        # All should complete without errors
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_refill_during_wait(self) -> None:
        """Test that tokens refill correctly during waits."""
        throttler = BedrockThrottler()
        throttler.tokens_per_second = 5.0  # Fast refill for testing
        throttler._tokens = 0.0

        # Wait for token
        start_time = time.time()
        await throttler._wait_for_token()
        elapsed = time.time() - start_time

        # Should have completed within reasonable time
        assert elapsed < 1.0  # Much less than default 2 seconds

    @pytest.mark.asyncio
    async def test_exception_in_context_manager(self) -> None:
        """Test that exceptions in context manager are properly propagated."""
        throttler = BedrockThrottler()

        class CustomException(Exception):  # noqa: N818
            pass

        with pytest.raises(CustomException):
            async with throttler.throttled_bedrock_request("test"):
                raise CustomException("Test error")

    @pytest.mark.asyncio
    async def test_stats_accuracy_after_many_requests(self) -> None:
        """Test that stats remain accurate after many requests."""
        throttler = BedrockThrottler()
        throttler.max_concurrent_calls = 10  # Allow more concurrency
        throttler.tokens_per_second = 10.0  # Fast rate

        num_requests = 20

        for _ in range(num_requests):
            async with throttler.throttled_bedrock_request("test"):
                pass

        stats = throttler.get_stats()

        assert stats["total_requests"] == num_requests
        assert stats["throttled_requests"] == 0
