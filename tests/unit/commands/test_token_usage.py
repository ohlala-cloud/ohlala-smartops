"""Unit tests for TokenUsage command.

This module tests the TokenUsageCommand class for viewing token consumption
statistics and costs.
"""

import time
from unittest.mock import Mock, patch

import pytest

from ohlala_smartops.commands.token_usage import TokenUsageCommand


class TestTokenUsageCommand:
    """Test suite for TokenUsageCommand."""

    @pytest.fixture
    def command(self) -> TokenUsageCommand:
        """Provide a TokenUsageCommand instance."""
        return TokenUsageCommand()

    def test_command_properties(self, command: TokenUsageCommand) -> None:
        """Test command basic properties."""
        assert command.name == "token-usage"
        assert command.description == "Show token usage statistics and costs"
        assert command.usage == "/token-usage [--detailed] [--reset-daily]"
        assert command.visible_to_users is True

    @pytest.mark.asyncio
    async def test_execute_brief_report(self, command: TokenUsageCommand) -> None:
        """Test execute with brief report (default)."""
        # Mock token_tracker
        with patch("ohlala_smartops.commands.token_usage.get_token_tracker") as mock_get_tracker:
            mock_tracker = Mock()
            mock_tracker.get_session_summary.return_value = {
                "operations": 5,
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
                "total_cost": 0.0105,
                "start_time": 1234567890.0,
            }
            mock_tracker.daily_stats = {
                "operations": 10,
                "total_input_tokens": 5000,
                "total_output_tokens": 2000,
                "total_cost": 0.045,
                "operations_by_type": {},
            }
            mock_tracker.LIMITS = {
                "max_daily_cost": 5.0,
                "max_operation_cost": 1.0,
            }
            mock_get_tracker.return_value = mock_tracker

            context = {"user_id": "user@example.com"}
            result = await command.execute([], context)

            assert result["success"] is True
            assert "Token Usage Summary" in result["message"]
            assert "Today's Usage" in result["message"]
            assert "Current Session" in result["message"]
            assert "10" in result["message"]  # Operations count
            assert "$0.045" in result["message"]  # Daily cost

    @pytest.mark.asyncio
    async def test_execute_detailed_report(self, command: TokenUsageCommand) -> None:
        """Test execute with detailed report flag."""
        with patch("ohlala_smartops.commands.token_usage.get_token_tracker") as mock_get_tracker:
            mock_tracker = Mock()
            mock_tracker.get_session_summary.return_value = {
                "operations": 5,
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
                "total_cost": 0.0105,
                "start_time": 1234567890.0,
            }
            mock_tracker.daily_stats = {
                "operations": 10,
                "total_input_tokens": 5000,
                "total_output_tokens": 2000,
                "total_cost": 0.045,
                "operations_by_type": {
                    "bedrock_call": {
                        "count": 10,
                        "tokens": 7000,
                        "cost": 0.045,
                    }
                },
            }
            mock_tracker.LIMITS = {
                "max_daily_cost": 5.0,
                "max_operation_cost": 1.0,
            }
            mock_get_tracker.return_value = mock_tracker

            context = {"user_id": "user@example.com"}
            result = await command.execute(["--detailed"], context)

            assert result["success"] is True
            assert "Detailed Token Usage Report" in result["message"]
            assert "Operations Breakdown" in result["message"]
            assert "bedrock_call" in result["message"]
            assert "Recommendations" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_reset_daily(self, command: TokenUsageCommand) -> None:
        """Test execute with reset daily flag."""
        with patch("ohlala_smartops.commands.token_usage.get_token_tracker") as mock_get_tracker:
            mock_tracker = Mock()
            mock_tracker._create_daily_stats = Mock(return_value={"operations": 0})
            mock_tracker._save_daily_stats = Mock()
            mock_get_tracker.return_value = mock_tracker

            context = {"user_id": "user@example.com"}
            result = await command.execute(["--reset-daily"], context)

            assert result["success"] is True
            assert "Daily Statistics Reset" in result["message"]
            mock_tracker._create_daily_stats.assert_called_once()
            mock_tracker._save_daily_stats.assert_called_once()

    def test_format_brief_report(self, command: TokenUsageCommand) -> None:
        """Test _format_brief_report method."""
        with patch("ohlala_smartops.commands.token_usage.get_token_tracker") as mock_get_tracker:
            mock_tracker = mock_get_tracker.return_value
            mock_tracker.LIMITS = {
                "max_daily_cost": 5.0,
                "max_operation_cost": 1.0,
            }

            session_stats = {
                "operations": 5,
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
                "total_cost": 0.0105,
                "start_time": 1234567890.0,
            }
            daily_stats = {
                "operations": 10,
                "total_input_tokens": 5000,
                "total_output_tokens": 2000,
                "total_cost": 0.045,
                "operations_by_type": {},
            }

            result = command._format_brief_report(session_stats, daily_stats)

            assert "Token Usage Summary" in result
            assert "10" in result  # Operations
            assert "$0.045" in result  # Cost

    def test_format_detailed_report(self, command: TokenUsageCommand) -> None:
        """Test _format_detailed_report method."""
        with patch("ohlala_smartops.commands.token_usage.get_token_tracker") as mock_get_tracker:
            mock_tracker = mock_get_tracker.return_value
            mock_tracker.LIMITS = {
                "max_daily_cost": 5.0,
                "max_operation_cost": 1.0,
            }

            session_stats = {
                "operations": 5,
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
                "total_cost": 0.0105,
                "start_time": 1234567890.0,
            }
            daily_stats = {
                "operations": 10,
                "total_input_tokens": 5000,
                "total_output_tokens": 2000,
                "total_cost": 0.045,
                "operations_by_type": {
                    "bedrock_call": {
                        "count": 10,
                        "tokens": 7000,
                        "cost": 0.045,
                    }
                },
            }

            result = command._format_detailed_report(session_stats, daily_stats)

            assert "Detailed Token Usage Report" in result
            assert "Input Tokens: 5,000" in result
            assert "Output Tokens: 2,000" in result
            assert "bedrock_call" in result
            assert "Recommendations" in result

    def test_format_runtime_zero(self, command: TokenUsageCommand) -> None:
        """Test _format_runtime with zero start time."""
        result = command._format_runtime(0)
        assert result == "N/A"

    def test_format_runtime_less_than_minute(self, command: TokenUsageCommand) -> None:
        """Test _format_runtime with less than one minute."""
        start_time = time.time() - 30  # 30 seconds ago
        result = command._format_runtime(start_time)
        assert result == "< 1 minute"

    def test_format_runtime_one_minute(self, command: TokenUsageCommand) -> None:
        """Test _format_runtime with exactly one minute."""
        start_time = time.time() - 60  # 60 seconds ago
        result = command._format_runtime(start_time)
        assert result == "1 minute"

    def test_format_runtime_multiple_minutes(self, command: TokenUsageCommand) -> None:
        """Test _format_runtime with multiple minutes."""
        start_time = time.time() - 300  # 5 minutes ago
        result = command._format_runtime(start_time)
        assert "5 minutes" in result

    def test_generate_recommendations_exceeded_budget(self, command: TokenUsageCommand) -> None:
        """Test recommendations when budget is exceeded."""
        daily_cost = 6.0
        daily_limit = 5.0
        daily_stats = {"operations": 10, "total_input_tokens": 5000, "total_output_tokens": 2000}

        result = command._generate_recommendations(daily_cost, daily_limit, daily_stats)

        assert len(result) > 0
        assert any("exceeded" in rec.lower() for rec in result)

    def test_generate_recommendations_80_percent_budget(self, command: TokenUsageCommand) -> None:
        """Test recommendations at 80% budget usage."""
        daily_cost = 4.0
        daily_limit = 5.0
        daily_stats = {"operations": 10, "total_input_tokens": 5000, "total_output_tokens": 2000}

        result = command._generate_recommendations(daily_cost, daily_limit, daily_stats)

        assert len(result) > 0
        assert any("80" in rec or "reduce" in rec.lower() for rec in result)

    def test_generate_recommendations_50_percent_budget(self, command: TokenUsageCommand) -> None:
        """Test recommendations at 50% budget usage."""
        daily_cost = 2.5
        daily_limit = 5.0
        daily_stats = {"operations": 10, "total_input_tokens": 5000, "total_output_tokens": 2000}

        result = command._generate_recommendations(daily_cost, daily_limit, daily_stats)

        assert len(result) > 0
        assert any("50" in rec or "monitor" in rec.lower() for rec in result)

    def test_generate_recommendations_high_operations(self, command: TokenUsageCommand) -> None:
        """Test recommendations with high operation count."""
        daily_cost = 1.0
        daily_limit = 5.0
        daily_stats = {"operations": 60, "total_input_tokens": 5000, "total_output_tokens": 2000}

        result = command._generate_recommendations(daily_cost, daily_limit, daily_stats)

        assert len(result) > 0
        assert any("operation" in rec.lower() or "batch" in rec.lower() for rec in result)

    def test_generate_recommendations_high_output_tokens(self, command: TokenUsageCommand) -> None:
        """Test recommendations with high output token ratio."""
        daily_cost = 1.0
        daily_limit = 5.0
        daily_stats = {"operations": 10, "total_input_tokens": 1000, "total_output_tokens": 5000}

        result = command._generate_recommendations(daily_cost, daily_limit, daily_stats)

        assert len(result) > 0
        assert any("output" in rec.lower() or "concise" in rec.lower() for rec in result)

    def test_generate_recommendations_normal_usage(self, command: TokenUsageCommand) -> None:
        """Test recommendations with normal usage."""
        daily_cost = 1.0
        daily_limit = 5.0
        daily_stats = {"operations": 10, "total_input_tokens": 5000, "total_output_tokens": 2000}

        result = command._generate_recommendations(daily_cost, daily_limit, daily_stats)

        assert len(result) > 0
        assert any("normal" in rec.lower() for rec in result)

    @pytest.mark.asyncio
    async def test_brief_report_with_budget_warning(self, command: TokenUsageCommand) -> None:
        """Test brief report includes budget warning at 80%."""
        with patch("ohlala_smartops.commands.token_usage.get_token_tracker") as mock_get_tracker:
            mock_tracker = mock_get_tracker.return_value
            mock_tracker.get_session_summary.return_value = {
                "operations": 5,
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
                "total_cost": 0.0105,
                "start_time": 1234567890.0,
            }
            mock_tracker.daily_stats = {
                "operations": 100,
                "total_input_tokens": 50000,
                "total_output_tokens": 20000,
                "total_cost": 4.5,  # 90% of $5 limit
                "operations_by_type": {},
            }
            mock_tracker.LIMITS = {
                "max_daily_cost": 5.0,
                "max_operation_cost": 1.0,
            }

            context = {"user_id": "user@example.com"}
            result = await command.execute([], context)

            assert result["success"] is True
            assert "⚠️" in result["message"]
            assert "Warning" in result["message"]

    @pytest.mark.asyncio
    async def test_empty_operations_breakdown(self, command: TokenUsageCommand) -> None:
        """Test detailed report with no operations breakdown."""
        with patch("ohlala_smartops.commands.token_usage.get_token_tracker") as mock_get_tracker:
            mock_tracker = mock_get_tracker.return_value
            mock_tracker.get_session_summary.return_value = {
                "operations": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost": 0.0,
                "start_time": 0,
            }
            mock_tracker.daily_stats = {
                "operations": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost": 0.0,
                "operations_by_type": {},
            }
            mock_tracker.LIMITS = {
                "max_daily_cost": 5.0,
                "max_operation_cost": 1.0,
            }

            context = {"user_id": "user@example.com"}
            result = await command.execute(["--detailed"], context)

            assert result["success"] is True
            assert "Detailed Token Usage Report" in result["message"]
            # No "Operations Breakdown" section when empty
            lines = result["message"].split("\n")
            breakdown_section = any("Operations Breakdown" in line for line in lines)
            # Should not appear or appear without entries
            if breakdown_section:
                # Should have no actual breakdown entries after the header
                assert result["message"].count("•") <= 10  # Only bullets from main stats

    @pytest.mark.asyncio
    async def test_multiple_operation_types_in_breakdown(self, command: TokenUsageCommand) -> None:
        """Test detailed report with multiple operation types."""
        with patch("ohlala_smartops.commands.token_usage.get_token_tracker") as mock_get_tracker:
            mock_tracker = mock_get_tracker.return_value
            mock_tracker.get_session_summary.return_value = {
                "operations": 15,
                "total_input_tokens": 3000,
                "total_output_tokens": 1500,
                "total_cost": 0.0315,
                "start_time": 1234567890.0,
            }
            mock_tracker.daily_stats = {
                "operations": 25,
                "total_input_tokens": 10000,
                "total_output_tokens": 5000,
                "total_cost": 0.105,
                "operations_by_type": {
                    "bedrock_call": {
                        "count": 15,
                        "tokens": 10000,
                        "cost": 0.06,
                    },
                    "tool_execution": {
                        "count": 10,
                        "tokens": 5000,
                        "cost": 0.045,
                    },
                },
            }
            mock_tracker.LIMITS = {
                "max_daily_cost": 5.0,
                "max_operation_cost": 1.0,
            }

            context = {"user_id": "user@example.com"}
            result = await command.execute(["--detailed"], context)

            assert result["success"] is True
            assert "bedrock_call" in result["message"]
            assert "tool_execution" in result["message"]
            assert "$0.06" in result["message"]
            assert "$0.045" in result["message"]
