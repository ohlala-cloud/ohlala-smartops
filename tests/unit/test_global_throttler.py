"""Tests for global AWS API throttling utilities with circuit breaker."""

import asyncio
import logging
import os
import time
from unittest.mock import patch

import pytest

from ohlala_smartops.utils.global_throttler import (
    CircuitBreakerOpenError,
    CircuitBreakerTrippedError,
    GlobalThrottler,
    get_global_throttler,
    throttled_aws_call,
)


class TestGlobalThrottler:
    """Test suite for GlobalThrottler class."""

    def test_initialization_default(self) -> None:
        """Test GlobalThrottler initialization with default values."""
        throttler = GlobalThrottler()

        assert throttler.max_concurrent_calls == 8  # default
        assert throttler.tokens_per_second == 15.0  # default
        assert throttler.max_tokens == 30  # default
        assert throttler.circuit_breaker_enabled is False  # default
        assert throttler.circuit_breaker_threshold == 100  # default
        assert throttler.circuit_breaker_timeout == 10.0  # default
        assert throttler._tokens == 30.0
        assert throttler._total_requests == 0
        assert throttler._throttled_requests == 0
        assert throttler._circuit_breaker_trips == 0
        assert throttler._consecutive_failures == 0

    @patch.dict(
        os.environ,
        {
            "MAX_CONCURRENT_AWS_CALLS": "20",
            "AWS_API_RATE_LIMIT": "50.0",
            "AWS_API_MAX_TOKENS": "100",
            "AWS_CIRCUIT_BREAKER_ENABLED": "true",
            "AWS_CIRCUIT_BREAKER_THRESHOLD": "5",
            "AWS_CIRCUIT_BREAKER_TIMEOUT": "30.0",
        },
    )
    def test_initialization_custom_env(self) -> None:
        """Test GlobalThrottler initialization with environment variables."""
        throttler = GlobalThrottler()

        assert throttler.max_concurrent_calls == 20
        assert throttler.tokens_per_second == 50.0
        assert throttler.max_tokens == 100
        assert throttler.circuit_breaker_enabled is True
        assert throttler.circuit_breaker_threshold == 5
        assert throttler.circuit_breaker_timeout == 30.0

    @pytest.mark.asyncio
    async def test_refill_tokens_after_delay(self) -> None:
        """Test token refill after a delay."""
        throttler = GlobalThrottler()

        # Consume all tokens
        throttler._tokens = 0.0
        throttler._last_refill = time.time() - 1.0  # 1 second ago

        await throttler._refill_tokens()

        # Should have refilled: 1 second * 15 tokens/sec = 15 tokens
        assert throttler._tokens >= 14.0
        assert throttler._tokens <= 16.0

    @pytest.mark.asyncio
    async def test_throttled_request_success(self) -> None:
        """Test successful throttled request."""
        throttler = GlobalThrottler()
        initial_requests = throttler._total_requests

        async with throttler.throttled_request("test_operation"):
            # Simulate some work
            await asyncio.sleep(0.01)

        # Should have incremented request counter
        assert throttler._total_requests == initial_requests + 1
        # No throttling should have occurred
        assert throttler._throttled_requests == 0

    @pytest.mark.asyncio
    async def test_throttled_request_rate_limit_error(self) -> None:
        """Test handling of rate limit errors."""
        throttler = GlobalThrottler()
        initial_throttled = throttler._throttled_requests

        start_time = time.time()

        with pytest.raises(Exception, match="(?i)rate limit"):
            async with throttler.throttled_request("test_operation"):
                raise Exception("Rate limit exceeded")

        elapsed = time.time() - start_time

        # Should have incremented throttled counter
        assert throttler._throttled_requests == initial_throttled + 1
        # Should have added 2-second recovery delay
        assert elapsed >= 1.9

    @pytest.mark.asyncio
    async def test_throttled_request_http_429_error(self) -> None:
        """Test handling of HTTP 429 errors."""
        throttler = GlobalThrottler()
        initial_throttled = throttler._throttled_requests

        with pytest.raises(Exception, match="429"):
            async with throttler.throttled_request("test_operation"):
                raise Exception("HTTP 429 Too Many Requests")

        # Should have incremented throttled counter
        assert throttler._throttled_requests == initial_throttled + 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_disabled_by_default(self) -> None:
        """Test that circuit breaker is disabled by default."""
        throttler = GlobalThrottler()

        # Circuit breaker should be disabled
        assert throttler.circuit_breaker_enabled is False

        # Should not raise even with many failures
        for _ in range(5):
            try:
                async with throttler.throttled_request("test"):
                    raise ValueError("Test error")
            except ValueError:
                pass

        # Circuit breaker should not have tripped
        assert throttler._circuit_breaker_trips == 0

    @pytest.mark.asyncio
    @patch.dict(
        os.environ, {"AWS_CIRCUIT_BREAKER_ENABLED": "true", "AWS_CIRCUIT_BREAKER_THRESHOLD": "3"}
    )
    async def test_circuit_breaker_trips_after_threshold(self) -> None:
        """Test that circuit breaker trips after reaching failure threshold."""
        throttler = GlobalThrottler()
        assert throttler.circuit_breaker_enabled is True

        # First 2 failures should not trip breaker
        for _ in range(2):
            try:
                async with throttler.throttled_request("test"):
                    raise ValueError("Test error")
            except ValueError:
                pass

        # 3rd failure should trip breaker
        with pytest.raises(CircuitBreakerTrippedError):
            async with throttler.throttled_request("test"):
                raise ValueError("Test error")

        # Should have recorded the trip
        assert throttler._circuit_breaker_trips == 1

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "AWS_CIRCUIT_BREAKER_ENABLED": "true",
            "AWS_CIRCUIT_BREAKER_THRESHOLD": "2",
            "AWS_CIRCUIT_BREAKER_TIMEOUT": "1.0",
        },
    )
    async def test_circuit_breaker_blocks_requests_when_open(self) -> None:
        """Test that circuit breaker blocks requests when open."""
        throttler = GlobalThrottler()

        # Trip the breaker
        for _ in range(2):
            try:
                async with throttler.throttled_request("test"):
                    raise ValueError("Test error")
            except (ValueError, CircuitBreakerTrippedError):
                pass

        # Next request should be blocked
        with pytest.raises(CircuitBreakerOpenError):
            async with throttler.throttled_request("test"):
                pass

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "AWS_CIRCUIT_BREAKER_ENABLED": "true",
            "AWS_CIRCUIT_BREAKER_THRESHOLD": "2",
            "AWS_CIRCUIT_BREAKER_TIMEOUT": "0.5",
        },
    )
    async def test_circuit_breaker_resets_after_timeout(self) -> None:
        """Test that circuit breaker resets after timeout."""
        throttler = GlobalThrottler()

        # Trip the breaker
        for _ in range(2):
            try:
                async with throttler.throttled_request("test"):
                    raise ValueError("Test error")
            except (ValueError, CircuitBreakerTrippedError):
                pass

        # Wait for timeout
        await asyncio.sleep(0.6)

        # Should allow requests again
        async with throttler.throttled_request("test"):
            pass  # Should succeed

    @pytest.mark.asyncio
    @patch.dict(
        os.environ, {"AWS_CIRCUIT_BREAKER_ENABLED": "true", "AWS_CIRCUIT_BREAKER_THRESHOLD": "3"}
    )
    async def test_circuit_breaker_rate_limit_doesnt_count_as_failure(self) -> None:
        """Test that rate limit errors don't count towards circuit breaker."""
        throttler = GlobalThrottler()

        # Rate limit errors should not trip circuit breaker
        for _ in range(5):
            try:
                async with throttler.throttled_request("test"):
                    raise Exception("Rate limit exceeded")
            except Exception:
                pass

        # Circuit breaker should not have tripped
        assert throttler._circuit_breaker_trips == 0
        assert throttler._consecutive_failures == 0

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"AWS_CIRCUIT_BREAKER_ENABLED": "true"})
    async def test_circuit_breaker_resets_on_success(self) -> None:
        """Test that successful requests reset the circuit breaker failure counter."""
        throttler = GlobalThrottler()

        # Record some failures
        throttler._consecutive_failures = 5

        # Successful request should reset counter
        async with throttler.throttled_request("test"):
            pass

        assert throttler._consecutive_failures == 0

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"AWS_CIRCUIT_BREAKER_ENABLED": "true"})
    async def test_manual_circuit_breaker_reset(self) -> None:
        """Test manual circuit breaker reset."""
        throttler = GlobalThrottler()

        # Set circuit breaker to open state
        throttler._circuit_open_until = time.time() + 100.0
        throttler._consecutive_failures = 10

        # Manually reset
        await throttler.reset_circuit_breaker()

        # Should be reset
        assert throttler._circuit_open_until == 0.0
        assert throttler._consecutive_failures == 0

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"MAX_CONCURRENT_AWS_CALLS": "3"})
    async def test_concurrent_requests_limited(self) -> None:
        """Test that concurrent requests are limited by semaphore."""
        throttler = GlobalThrottler()

        concurrent_count = 0
        max_concurrent = 0

        async def test_operation() -> None:
            nonlocal concurrent_count, max_concurrent
            async with throttler.throttled_request("test"):
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
                await asyncio.sleep(0.1)
                concurrent_count -= 1

        # Launch 6 concurrent operations
        await asyncio.gather(*[test_operation() for _ in range(6)])

        # Maximum concurrent should not exceed limit
        assert max_concurrent <= throttler.max_concurrent_calls

    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self) -> None:
        """Test that rate limiting is enforced."""
        throttler = GlobalThrottler()
        throttler.max_concurrent_calls = 20  # High limit to test rate limiting
        throttler.tokens_per_second = 5.0  # 5 requests per second
        throttler.max_tokens = 5

        start_time = time.time()

        # Make 8 requests (should take time due to rate limiting)
        for _ in range(8):
            async with throttler.throttled_request("test"):
                pass

        elapsed = time.time() - start_time

        # Should have taken at least some time (8 requests / 5 per second = 1.6 seconds,
        # minus initial tokens)
        assert elapsed >= 0.4

    def test_get_stats_initial(self) -> None:
        """Test getting stats from a new throttler."""
        throttler = GlobalThrottler()
        stats = throttler.get_stats()

        assert stats["total_requests"] == 0
        assert stats["throttled_requests"] == 0
        assert stats["circuit_breaker_trips"] == 0
        assert stats["current_tokens"] == 30.0  # default max_tokens
        assert stats["max_concurrent_calls"] == 8
        assert stats["tokens_per_second"] == 15.0
        assert stats["consecutive_failures"] == 0
        assert stats["circuit_open"] is False

    @pytest.mark.asyncio
    async def test_get_stats_after_requests(self) -> None:
        """Test getting stats after processing requests."""
        throttler = GlobalThrottler()

        # Make some requests
        for _ in range(3):
            async with throttler.throttled_request("test"):
                pass

        stats = throttler.get_stats()

        assert stats["total_requests"] == 3
        assert stats["throttled_requests"] == 0
        assert isinstance(stats["current_tokens"], float)

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"AWS_CIRCUIT_BREAKER_ENABLED": "true"})
    async def test_get_stats_with_circuit_breaker(self) -> None:
        """Test getting stats when circuit breaker is open."""
        throttler = GlobalThrottler()

        # Open circuit breaker
        throttler._circuit_open_until = time.time() + 10.0

        stats = throttler.get_stats()

        assert stats["circuit_open"] is True

    @pytest.mark.asyncio
    async def test_logging_occurs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that appropriate logging occurs."""
        with caplog.at_level(logging.INFO):
            throttler = GlobalThrottler()
            async with throttler.throttled_request("test_op"):
                pass

        # Should have initialization log
        assert any("Global throttler initialized" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"AWS_CIRCUIT_BREAKER_ENABLED": "true"})
    async def test_logging_circuit_breaker_events(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that circuit breaker events are logged."""
        with caplog.at_level(logging.WARNING):
            throttler = GlobalThrottler()
            throttler.circuit_breaker_threshold = 1

            try:
                async with throttler.throttled_request("test"):
                    raise ValueError("Test error")
            except (ValueError, CircuitBreakerTrippedError):
                pass

        # Should have circuit breaker warning
        assert any("TRIPPED" in record.message for record in caplog.records)


class TestGlobalSingleton:
    """Test suite for global singleton functions."""

    def test_get_global_throttler_creates_instance(self) -> None:
        """Test that get_global_throttler creates an instance."""
        # Reset global instance
        import ohlala_smartops.utils.global_throttler as module

        module._global_throttler = None

        throttler = get_global_throttler()

        assert isinstance(throttler, GlobalThrottler)

    def test_get_global_throttler_returns_singleton(self) -> None:
        """Test that get_global_throttler returns the same instance."""
        throttler1 = get_global_throttler()
        throttler2 = get_global_throttler()

        assert throttler1 is throttler2

    @pytest.mark.asyncio
    async def test_throttled_aws_call_convenience(self) -> None:
        """Test convenience function for throttled calls."""
        call_executed = False

        async with throttled_aws_call("test_operation"):
            call_executed = True

        assert call_executed is True

    @pytest.mark.asyncio
    async def test_throttled_aws_call_uses_singleton(self) -> None:
        """Test that convenience function uses the singleton."""
        throttler = get_global_throttler()
        initial_requests = throttler._total_requests

        async with throttled_aws_call("test"):
            pass

        # Should have incremented the singleton's counter
        assert throttler._total_requests == initial_requests + 1


class TestCircuitBreakerExceptions:
    """Test suite for circuit breaker exception classes."""

    def test_circuit_breaker_open_error(self) -> None:
        """Test CircuitBreakerOpenError exception."""
        error = CircuitBreakerOpenError("Circuit open")

        assert isinstance(error, Exception)
        assert str(error) == "Circuit open"

    def test_circuit_breaker_tripped_error(self) -> None:
        """Test CircuitBreakerTrippedError exception."""
        error = CircuitBreakerTrippedError("Circuit tripped")

        assert isinstance(error, Exception)
        assert str(error) == "Circuit tripped"

    @pytest.mark.asyncio
    async def test_circuit_breaker_exceptions_propagate(self) -> None:
        """Test that circuit breaker exceptions propagate correctly."""
        throttler = GlobalThrottler()
        throttler.circuit_breaker_enabled = True
        throttler._circuit_open_until = time.time() + 10.0

        try:
            async with throttler.throttled_request("test"):
                pass
        except CircuitBreakerOpenError as e:
            assert "Circuit breaker open" in str(e)  # noqa: PT017
        else:
            pytest.fail("Expected CircuitBreakerOpenError")


class TestEdgeCases:
    """Test suite for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_exception_propagation(self) -> None:
        """Test that exceptions are properly propagated."""
        throttler = GlobalThrottler()

        class CustomException(Exception):  # noqa: N818
            pass

        with pytest.raises(CustomException):
            async with throttler.throttled_request("test"):
                raise CustomException("Test error")

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"AWS_CIRCUIT_BREAKER_ENABLED": "true"})
    async def test_circuit_breaker_with_mixed_errors(self) -> None:
        """Test circuit breaker with mix of rate limit and other errors."""
        throttler = GlobalThrottler()
        throttler.circuit_breaker_threshold = 3

        # Rate limit errors should not count
        try:
            async with throttler.throttled_request("test"):
                raise Exception("Rate limit exceeded")
        except Exception:
            pass

        assert throttler._consecutive_failures == 0

        # Regular errors should count
        try:
            async with throttler.throttled_request("test"):
                raise ValueError("Other error")
        except ValueError:
            pass

        assert throttler._consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_concurrent_circuit_breaker_checks(self) -> None:
        """Test concurrent circuit breaker checks with lock contention."""
        throttler = GlobalThrottler()
        throttler.circuit_breaker_enabled = True

        # Launch multiple concurrent checks
        results = await asyncio.gather(
            *[throttler._check_circuit_breaker() for _ in range(5)], return_exceptions=False
        )

        # All should complete without errors (circuit is not open)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_stats_accuracy_after_many_requests(self) -> None:
        """Test that stats remain accurate after many requests."""
        throttler = GlobalThrottler()
        throttler.max_concurrent_calls = 20
        throttler.tokens_per_second = 50.0

        num_requests = 30

        for _ in range(num_requests):
            async with throttler.throttled_request("test"):
                pass

        stats = throttler.get_stats()

        assert stats["total_requests"] == num_requests
        assert stats["throttled_requests"] == 0
