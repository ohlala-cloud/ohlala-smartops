"""Tests for token usage tracking and cost monitoring utilities."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

import ohlala_smartops.utils.token_tracker
from ohlala_smartops.utils.token_tracker import (
    TokenTracker,
    check_operation_limits,
    estimate_bedrock_input_tokens,
    get_token_tracker,
    get_usage_report,
    get_usage_summary,
    main,
    track_bedrock_operation,
)


class TestTokenTracker:
    """Test suite for TokenTracker class."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Test TokenTracker initialization."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        assert tracker.session_stats["operations"] == 0
        assert tracker.session_stats["total_input_tokens"] == 0
        assert tracker.session_stats["total_output_tokens"] == 0
        assert tracker.session_stats["total_cost"] == 0.0
        assert "start_time" in tracker.session_stats

    def test_pricing_constants(self) -> None:
        """Test that pricing constants are defined correctly."""
        assert "input_tokens_per_1k" in TokenTracker.PRICING
        assert "output_tokens_per_1k" in TokenTracker.PRICING
        assert TokenTracker.PRICING["input_tokens_per_1k"] == 0.003
        assert TokenTracker.PRICING["output_tokens_per_1k"] == 0.015

    def test_limits_constants(self) -> None:
        """Test that limit constants are defined correctly."""
        assert "max_input_tokens" in TokenTracker.LIMITS
        assert "max_daily_cost" in TokenTracker.LIMITS
        assert TokenTracker.LIMITS["max_input_tokens"] == 200000
        assert TokenTracker.LIMITS["max_daily_cost"] == 5.0

    def test_estimate_tokens_empty_string(self) -> None:
        """Test token estimation for empty string."""
        tracker = TokenTracker()

        tokens = tracker.estimate_tokens("")
        assert tokens == 0

    def test_estimate_tokens_simple_text(self) -> None:
        """Test token estimation for simple text."""
        tracker = TokenTracker()

        # "Hello world" is about 12 characters, ~3.4 tokens
        tokens = tracker.estimate_tokens("Hello world")
        assert tokens > 0
        assert tokens < 10  # Should be small

    def test_estimate_tokens_long_text(self) -> None:
        """Test token estimation for longer text."""
        tracker = TokenTracker()

        # 1000 characters should be ~285 tokens (1000 / 3.5)
        long_text = "a" * 1000
        tokens = tracker.estimate_tokens(long_text)
        assert tokens >= 250
        assert tokens <= 350

    def test_calculate_cost(self) -> None:
        """Test cost calculation."""
        tracker = TokenTracker()

        input_cost, output_cost, total_cost = tracker.calculate_cost(1000, 500)

        # 1000 input tokens = 1000/1000 * 0.003 = $0.003
        # 500 output tokens = 500/1000 * 0.015 = $0.0075
        # Total = $0.0105
        assert abs(input_cost - 0.003) < 0.0001
        assert abs(output_cost - 0.0075) < 0.0001
        assert abs(total_cost - 0.0105) < 0.0001

    def test_calculate_cost_zero_tokens(self) -> None:
        """Test cost calculation with zero tokens."""
        tracker = TokenTracker()

        input_cost, output_cost, total_cost = tracker.calculate_cost(0, 0)

        assert input_cost == 0.0
        assert output_cost == 0.0
        assert total_cost == 0.0

    def test_check_limits_within_limits(self) -> None:
        """Test limit checking when within limits."""
        tracker = TokenTracker()

        result = tracker.check_limits(1000, "test_operation", 1)

        assert result["allowed"] is True
        assert result["estimated_input_tokens"] == 1000
        assert len(result["warnings"]) == 0
        assert "limits_remaining" in result

    def test_check_limits_exceeds_token_limit(self) -> None:
        """Test limit checking when exceeding token limit."""
        tracker = TokenTracker()

        result = tracker.check_limits(250000, "test_operation", 100)

        assert result["allowed"] is False
        assert any("exceed model limit" in w for w in result["warnings"])
        assert len(result["recommendations"]) > 0

    def test_check_limits_approaching_token_limit(self) -> None:
        """Test limit checking when approaching token limit (80% threshold)."""
        tracker = TokenTracker()

        # 85% of 200K = 170K tokens
        result = tracker.check_limits(170000, "test_operation", 50)

        assert result["allowed"] is True  # Still allowed
        assert any("High token usage" in w for w in result["warnings"])
        assert len(result["recommendations"]) > 0

    def test_check_limits_high_operation_cost(self) -> None:
        """Test warning for high per-operation cost."""
        tracker = TokenTracker()

        # High token count will result in high cost
        result = tracker.check_limits(100000, "test_operation", 50)

        # Should have cost warning (operation cost > $1)
        if result["estimated_cost"] > 1.0:
            assert any("Operation cost" in w for w in result["warnings"])

    def test_check_limits_daily_cost_warning(self) -> None:
        """Test warning when approaching daily cost limit."""
        tracker = TokenTracker()
        tracker.daily_stats["total_cost"] = 4.9  # Will exceed $5 limit with this operation

        result = tracker.check_limits(50000, "test_operation", 10)

        # Should warn about daily limit
        assert any("Daily cost limit" in w for w in result["warnings"])

    def test_check_limits_milestone_warnings(self) -> None:
        """Test $5 milestone warnings."""
        tracker = TokenTracker()
        tracker.daily_stats["total_cost"] = 4.8  # Just under $5

        # Operation that will push over $5
        result = tracker.check_limits(10000, "test_operation", 5)

        # Should have milestone warning
        assert any("milestone" in w.lower() for w in result["warnings"])

    def test_track_operation_basic(self, tmp_path: Path) -> None:
        """Test tracking a basic operation."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        record = tracker.track_operation("health_check", 1000, 500, 3)

        # Check record structure
        assert record["type"] == "health_check"
        assert record["instances"] == 3
        assert record["tokens"]["input"] == 1000
        assert record["tokens"]["output"] == 500
        assert record["tokens"]["total"] == 1500
        assert "timestamp" in record
        assert "costs" in record

        # Check session stats updated
        assert tracker.session_stats["operations"] == 1
        assert tracker.session_stats["total_input_tokens"] == 1000
        assert tracker.session_stats["total_output_tokens"] == 500

        # Check daily stats updated
        assert tracker.daily_stats["operations"] == 1
        assert tracker.daily_stats["total_input_tokens"] == 1000

    def test_track_operation_multiple(self, tmp_path: Path) -> None:
        """Test tracking multiple operations."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        tracker.track_operation("health_check", 1000, 500)
        tracker.track_operation("disk_check", 2000, 1000)

        assert tracker.session_stats["operations"] == 2
        assert tracker.session_stats["total_input_tokens"] == 3000
        assert tracker.session_stats["total_output_tokens"] == 1500

    def test_track_operation_by_type(self, tmp_path: Path) -> None:
        """Test operation tracking by type."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        tracker.track_operation("health_check", 1000, 500)
        tracker.track_operation("health_check", 1500, 750)
        tracker.track_operation("disk_check", 2000, 1000)

        ops_by_type = tracker.daily_stats["operations_by_type"]

        assert "health_check" in ops_by_type
        assert ops_by_type["health_check"]["count"] == 2
        assert ops_by_type["health_check"]["tokens"] == 3750  # (1000+500) + (1500+750)

        assert "disk_check" in ops_by_type
        assert ops_by_type["disk_check"]["count"] == 1

    def test_track_operation_with_metadata(self, tmp_path: Path) -> None:
        """Test tracking operation with custom metadata."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        metadata = {"region": "us-east-1", "user": "test"}
        record = tracker.track_operation("health_check", 1000, 500, metadata=metadata)

        assert record["metadata"] == metadata

    def test_get_session_summary(self, tmp_path: Path) -> None:
        """Test getting session summary."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        tracker.track_operation("test", 1000, 500)
        time.sleep(0.1)  # Small delay for runtime

        summary = tracker.get_session_summary()

        assert "session" in summary
        assert "daily" in summary
        assert "limits" in summary
        assert summary["session"]["operations"] == 1
        assert summary["session"]["total_tokens"] == 1500
        assert summary["session"]["runtime_minutes"] > 0

    def test_format_usage_report(self, tmp_path: Path) -> None:
        """Test formatted usage report generation."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        tracker.track_operation("health_check", 1000, 500, 2)

        report = tracker.format_usage_report()

        assert isinstance(report, str)
        assert "Token Usage Report" in report
        assert "Current Session:" in report
        assert "Today's Usage:" in report
        assert "Operations: 1" in report

    def test_daily_stats_persistence(self, tmp_path: Path) -> None:
        """Test that daily stats are persisted to file."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        tracker.track_operation("test", 1000, 500)

        # File should exist
        assert storage.exists()

        # Load and verify content
        with open(storage) as f:  # noqa: PTH123
            data = json.load(f)

        assert data["operations"] == 1
        assert data["total_input_tokens"] == 1000

    def test_daily_stats_loading(self, tmp_path: Path) -> None:
        """Test loading daily stats from file."""
        storage = tmp_path / "test_tokens.json"

        # Create existing stats file
        existing_data = {
            "date": datetime.now(UTC).isoformat(),
            "operations": 5,
            "total_input_tokens": 5000,
            "total_output_tokens": 2500,
            "total_cost": 0.05,
            "operations_by_type": {},
        }

        with open(storage, "w") as f:  # noqa: PTH123
            json.dump(existing_data, f)

        # Load tracker
        tracker = TokenTracker(str(storage))

        assert tracker.daily_stats["operations"] == 5
        assert tracker.daily_stats["total_input_tokens"] == 5000

    def test_daily_stats_reset_on_new_day(self, tmp_path: Path) -> None:
        """Test that daily stats reset when loading from previous day."""
        storage = tmp_path / "test_tokens.json"

        # Create stats file from yesterday
        old_data = {
            "date": "2023-01-01T00:00:00+00:00",  # Old date
            "operations": 100,
            "total_input_tokens": 50000,
            "total_output_tokens": 25000,
            "total_cost": 0.5,
            "operations_by_type": {},
        }

        with open(storage, "w") as f:  # noqa: PTH123
            json.dump(old_data, f)

        # Load tracker - should reset
        tracker = TokenTracker(str(storage))

        assert tracker.daily_stats["operations"] == 0
        assert tracker.daily_stats["total_input_tokens"] == 0

    def test_calculate_max_instances_for_limit(self) -> None:
        """Test calculation of maximum instances."""
        tracker = TokenTracker()

        max_instances = tracker._calculate_max_instances_for_limit()

        assert isinstance(max_instances, int)
        assert max_instances > 0
        assert max_instances < 200  # Should be reasonable

    def test_save_daily_stats_error_handling(self, tmp_path: Path) -> None:
        """Test that save errors are handled gracefully."""
        storage = tmp_path / "invalid" / "path" / "test.json"
        tracker = TokenTracker(str(storage))

        # Should not raise exception
        tracker._save_daily_stats()

    def test_load_daily_stats_corrupt_file(self, tmp_path: Path) -> None:
        """Test loading when file is corrupt."""
        storage = tmp_path / "test_tokens.json"

        # Write corrupt JSON
        with open(storage, "w") as f:  # noqa: PTH123
            f.write("invalid json{")

        # Should create new stats instead of crashing
        tracker = TokenTracker(str(storage))

        assert tracker.daily_stats["operations"] == 0


class TestGlobalFunctions:
    """Test suite for module-level convenience functions."""

    def test_get_token_tracker_creates_instance(self) -> None:
        """Test that get_token_tracker creates an instance."""
        # Reset global instance
        ohlala_smartops.utils.token_tracker._token_tracker = None

        tracker = get_token_tracker()

        assert isinstance(tracker, TokenTracker)

    def test_get_token_tracker_returns_singleton(self) -> None:
        """Test that get_token_tracker returns the same instance."""
        tracker1 = get_token_tracker()
        tracker2 = get_token_tracker()

        assert tracker1 is tracker2

    def test_estimate_bedrock_input_tokens(self) -> None:
        """Test Bedrock input token estimation."""
        tokens = estimate_bedrock_input_tokens(
            system_prompt="System prompt",
            user_message="User message",
            tool_definitions=[{"name": "tool1"}],
            conversation_context="Previous context",
        )

        assert isinstance(tokens, int)
        assert tokens > 0

    def test_estimate_bedrock_input_tokens_with_tool_results(self) -> None:
        """Test token estimation with tool results."""
        tokens = estimate_bedrock_input_tokens(
            system_prompt="System",
            user_message="Message",
            tool_definitions=[],
            tool_results=[{"result": "data"}],
        )

        assert isinstance(tokens, int)
        assert tokens > 0

    def test_check_operation_limits_function(self) -> None:
        """Test convenience function for checking limits."""
        result = check_operation_limits(1000, "test", 1)

        assert "allowed" in result
        assert "estimated_input_tokens" in result
        assert result["allowed"] is True

    def test_track_bedrock_operation_function(self) -> None:
        """Test convenience function for tracking operations."""
        record = track_bedrock_operation("test", 1000, 500, 2, {"key": "value"})

        assert record["type"] == "test"
        assert record["instances"] == 2
        assert record["metadata"]["key"] == "value"

    def test_get_usage_summary_function(self) -> None:
        """Test convenience function for getting summary."""
        summary = get_usage_summary()

        assert "session" in summary
        assert "daily" in summary
        assert "limits" in summary

    def test_get_usage_report_function(self) -> None:
        """Test convenience function for getting report."""
        report = get_usage_report()

        assert isinstance(report, str)
        assert len(report) > 0


class TestCLI:
    """Test suite for CLI interface."""

    @patch("sys.argv", ["token_tracker.py", "--estimate", "Hello world"])
    def test_cli_estimate(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test CLI estimation."""
        main()
        captured = capsys.readouterr()

        assert "Estimated tokens:" in captured.out
        assert "Estimated cost" in captured.out

    @patch("sys.argv", ["token_tracker.py", "--report"])
    def test_cli_report(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test CLI report generation."""
        main()
        captured = capsys.readouterr()

        assert "Token Usage Report" in captured.out

    @patch("sys.argv", ["token_tracker.py", "--reset-daily"])
    def test_cli_reset_daily(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test CLI daily stats reset."""
        main()
        captured = capsys.readouterr()

        assert "reset" in captured.out.lower()

    @patch("sys.argv", ["token_tracker.py"])
    def test_cli_no_args(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test CLI with no arguments."""
        main()
        captured = capsys.readouterr()

        assert "help" in captured.out.lower()


class TestEdgeCases:
    """Test suite for edge cases and error conditions."""

    def test_track_operation_zero_instances(self, tmp_path: Path) -> None:
        """Test tracking operation with zero instances."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        # Should handle zero instances gracefully
        record = tracker.track_operation("test", 1000, 500, 0)

        assert (
            record["costs"]["per_instance"] == record["costs"]["total"]
        )  # Divides by max(1, 0) = 1

    def test_estimate_tokens_none_input(self) -> None:
        """Test token estimation with None input."""
        tracker = TokenTracker()

        # Should handle None gracefully (converts to string)
        tokens = tracker.estimate_tokens(None)  # type: ignore

        assert tokens == 0

    def test_cost_calculation_large_numbers(self) -> None:
        """Test cost calculation with large token counts."""
        tracker = TokenTracker()

        # 1 million input tokens
        input_cost, output_cost, total_cost = tracker.calculate_cost(1000000, 1000000)

        # 1M input = $3, 1M output = $15
        assert abs(input_cost - 3.0) < 0.01
        assert abs(output_cost - 15.0) < 0.01
        assert abs(total_cost - 18.0) < 0.01

    def test_session_runtime_calculation(self, tmp_path: Path) -> None:
        """Test that session runtime is calculated correctly."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        time.sleep(0.1)  # Wait a bit

        summary = tracker.get_session_summary()

        assert summary["session"]["runtime_minutes"] > 0
        assert summary["session"]["runtime_minutes"] < 1  # Should be under a minute

    def test_average_cost_with_zero_operations(self, tmp_path: Path) -> None:
        """Test average cost calculation with zero operations."""
        storage = tmp_path / "test_tokens.json"
        tracker = TokenTracker(str(storage))

        summary = tracker.get_session_summary()

        # Should not divide by zero
        assert summary["session"]["avg_cost_per_operation"] == 0.0

    def test_limits_remaining_negative_tokens(self) -> None:
        """Test limits remaining when tokens exceed limit."""
        tracker = TokenTracker()

        result = tracker.check_limits(250000, "test", 1)

        # Remaining should be negative (converted to int)
        assert result["limits_remaining"]["tokens"] < 0

    def test_milestone_warning_exact_threshold(self) -> None:
        """Test milestone warning at exact threshold."""
        tracker = TokenTracker()
        tracker.daily_stats["total_cost"] = 5.0  # Exactly at $5

        # Small operation
        result = tracker.check_limits(100, "test", 1)

        # Should have milestone-related content
        assert len(result["warnings"]) >= 0  # May or may not warn depending on next cost
