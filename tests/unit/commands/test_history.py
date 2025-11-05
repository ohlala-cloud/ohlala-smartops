"""Unit tests for History command.

This module tests the HistoryCommand class for viewing command execution history.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from ohlala_smartops.commands.history import HistoryCommand
from ohlala_smartops.models.command_history import CommandHistoryEntry


class TestHistoryCommand:
    """Test suite for HistoryCommand."""

    @pytest.fixture
    def command(self) -> HistoryCommand:
        """Provide a HistoryCommand instance."""
        return HistoryCommand()

    @pytest.fixture
    def mock_state_manager(self) -> Mock:
        """Provide a mock state manager."""
        manager = Mock()
        manager.get_user_command_history = AsyncMock()
        return manager

    def test_command_properties(self, command: HistoryCommand) -> None:
        """Test command basic properties."""
        assert command.name == "history"
        assert command.description == "Show detailed command execution history"
        assert command.usage == "/history [limit]"
        assert command.visible_to_users is True

    @pytest.mark.asyncio
    async def test_execute_with_empty_history(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test execute with no command history."""
        mock_state_manager.get_user_command_history.return_value = []

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute([], context)

        assert result["success"] is True
        assert "No Command History Found" in result["message"]
        mock_state_manager.get_user_command_history.assert_called_once_with(
            "user@example.com", limit=5
        )

    @pytest.mark.asyncio
    async def test_execute_with_command_history(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test execute with command history."""
        # Create test entries
        entry1 = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Start instance i-abc123",
            instance_ids=["i-abc123"],
        )
        entry1.mark_completed({"i-abc123": {"status": "Success", "output": "Started"}})

        entry2 = CommandHistoryEntry.create(
            command_id="cmd-456",
            user_id="user@example.com",
            description="List instances",
        )

        mock_state_manager.get_user_command_history.return_value = [entry1, entry2]

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute([], context)

        assert result["success"] is True
        assert "Command History (Last 2 commands)" in result["message"]
        assert "cmd-123" in result["message"]
        assert "cmd-456" in result["message"]
        assert "Start instance i-abc123" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_with_custom_limit(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test execute with custom limit parameter."""
        mock_state_manager.get_user_command_history.return_value = []

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute(["10"], context)

        assert result["success"] is True
        mock_state_manager.get_user_command_history.assert_called_once_with(
            "user@example.com", limit=10
        )

    @pytest.mark.asyncio
    async def test_execute_with_limit_capped_at_20(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test that limit is capped at 20."""
        mock_state_manager.get_user_command_history.return_value = []

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute(["100"], context)

        assert result["success"] is True
        # Should be capped at 20
        mock_state_manager.get_user_command_history.assert_called_once_with(
            "user@example.com", limit=20
        )

    @pytest.mark.asyncio
    async def test_execute_with_invalid_limit(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test execute with invalid limit falls back to default."""
        mock_state_manager.get_user_command_history.return_value = []

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute(["invalid"], context)

        assert result["success"] is True
        # Should use default limit of 5
        mock_state_manager.get_user_command_history.assert_called_once_with(
            "user@example.com", limit=5
        )

    @pytest.mark.asyncio
    async def test_execute_without_state_manager(self, command: HistoryCommand) -> None:
        """Test execute when state_manager is not available."""
        context = {
            "user_id": "user@example.com",
            # No state_manager
        }

        result = await command.execute([], context)

        assert result["success"] is False
        assert "State manager not available" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_with_exception(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test execute handles exceptions gracefully."""
        mock_state_manager.get_user_command_history.side_effect = Exception("DB error")

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute([], context)

        assert result["success"] is False
        assert "Failed to retrieve command history" in result["error"]

    @pytest.mark.asyncio
    async def test_message_includes_status_icons(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test that message includes appropriate status icons."""
        entries = [
            CommandHistoryEntry.create(
                command_id="cmd-1",
                user_id="user@example.com",
                description="Completed command",
            ),
            CommandHistoryEntry.create(
                command_id="cmd-2",
                user_id="user@example.com",
                description="Failed command",
            ),
        ]
        entries[0].mark_completed()
        entries[1].mark_failed("Error")

        mock_state_manager.get_user_command_history.return_value = entries

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute([], context)

        assert result["success"] is True
        # Check for status icons
        assert "✅" in result["message"]  # Completed icon
        assert "❌" in result["message"]  # Failed icon

    @pytest.mark.asyncio
    async def test_message_includes_results_summary(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test that message includes results summary."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Multi-instance command",
            instance_ids=["i-abc123", "i-def456"],
        )
        results = {
            "i-abc123": {"status": "Success", "output": "OK"},
            "i-def456": {"status": "Failed", "error": "Error"},
        }
        entry.mark_completed(results)

        mock_state_manager.get_user_command_history.return_value = [entry]

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute([], context)

        assert result["success"] is True
        assert "Results Summary" in result["message"]
        assert "Successful: 1" in result["message"]
        assert "Failed: 1" in result["message"]

    @pytest.mark.asyncio
    async def test_message_includes_aws_console_link(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test that message includes AWS Console link for SSM commands."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-abc123",  # SSM command ID format
            user_id="user@example.com",
            description="SSM command",
            aws_region="us-west-2",
        )

        mock_state_manager.get_user_command_history.return_value = [entry]

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute([], context)

        assert result["success"] is True
        assert "View in AWS Console" in result["message"]
        assert "us-west-2.console.aws.amazon.com" in result["message"]
        assert "cmd-abc123" in result["message"]

    @pytest.mark.asyncio
    async def test_message_includes_approved_by(
        self, command: HistoryCommand, mock_state_manager: Mock
    ) -> None:
        """Test that message includes approval information."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Dangerous command",
        )
        entry.set_approval("approver@example.com")

        mock_state_manager.get_user_command_history.return_value = [entry]

        context = {
            "user_id": "user@example.com",
            "state_manager": mock_state_manager,
        }

        result = await command.execute([], context)

        assert result["success"] is True
        assert "Approved by" in result["message"]
        assert "approver@example.com" in result["message"]

    def test_get_status_icon(self, command: HistoryCommand) -> None:
        """Test _get_status_icon helper method."""
        assert command._get_status_icon("pending") == "⏳"
        assert command._get_status_icon("completed") == "✅"
        assert command._get_status_icon("failed") == "❌"
        assert command._get_status_icon("cancelled") == "🚫"
        assert command._get_status_icon("unknown") == "❓"

    def test_get_elapsed_time_seconds(self, command: HistoryCommand) -> None:
        """Test _get_elapsed_time for seconds."""
        timestamp = datetime.now(UTC) - timedelta(seconds=30)
        result = command._get_elapsed_time(timestamp)
        assert "second(s)" in result

    def test_get_elapsed_time_minutes(self, command: HistoryCommand) -> None:
        """Test _get_elapsed_time for minutes."""
        timestamp = datetime.now(UTC) - timedelta(minutes=5)
        result = command._get_elapsed_time(timestamp)
        assert "minute(s)" in result

    def test_get_elapsed_time_hours(self, command: HistoryCommand) -> None:
        """Test _get_elapsed_time for hours."""
        timestamp = datetime.now(UTC) - timedelta(hours=2)
        result = command._get_elapsed_time(timestamp)
        assert "hour(s)" in result

    def test_get_elapsed_time_days(self, command: HistoryCommand) -> None:
        """Test _get_elapsed_time for days."""
        timestamp = datetime.now(UTC) - timedelta(days=3)
        result = command._get_elapsed_time(timestamp)
        assert "day(s)" in result

    def test_parse_limit_default(self, command: HistoryCommand) -> None:
        """Test _parse_limit with no args returns default."""
        assert command._parse_limit([]) == 5

    def test_parse_limit_valid(self, command: HistoryCommand) -> None:
        """Test _parse_limit with valid number."""
        assert command._parse_limit(["10"]) == 10

    def test_parse_limit_invalid(self, command: HistoryCommand) -> None:
        """Test _parse_limit with invalid input returns default."""
        assert command._parse_limit(["abc"]) == 5

    def test_parse_limit_capped(self, command: HistoryCommand) -> None:
        """Test _parse_limit caps at 20."""
        assert command._parse_limit(["100"]) == 20

    def test_build_empty_history_response(self, command: HistoryCommand) -> None:
        """Test _build_empty_history_response."""
        response = command._build_empty_history_response()

        assert response["success"] is True
        assert "No Command History Found" in response["message"]

    def test_format_command_details(self, command: HistoryCommand) -> None:
        """Test _format_command_details helper."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test",
            instance_ids=["i-abc123"],
            user_context="Team: Eng",
        )
        entry.set_approval("approver@example.com")

        details = command._format_command_details(entry, "5 minute(s)")

        assert "cmd-123" in details
        assert "5 minute(s)" in details
        assert "i-abc123" in details
        assert "Team: Eng" in details
        assert "approver@example.com" in details

    def test_format_results_summary_no_results(self, command: HistoryCommand) -> None:
        """Test _format_results_summary with no results."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test",
        )

        summary = command._format_results_summary(entry)

        assert summary == ""

    def test_format_console_link_ssm_command(self, command: HistoryCommand) -> None:
        """Test _format_console_link for SSM command."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-abc123",
            user_id="user@example.com",
            description="SSM command",
            aws_region="us-east-1",
        )

        link = command._format_console_link(entry)

        assert "View in AWS Console" in link
        assert "us-east-1.console.aws.amazon.com" in link
        assert "cmd-abc123" in link

    def test_format_console_link_non_ssm_command(self, command: HistoryCommand) -> None:
        """Test _format_console_link for non-SSM command."""
        entry = CommandHistoryEntry.create(
            command_id="local-123",
            user_id="user@example.com",
            description="Local command",
        )

        link = command._format_console_link(entry)

        assert link == ""

    def test_format_completion_time(self, command: HistoryCommand) -> None:
        """Test _format_completion_time with completion time."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test",
        )
        entry.mark_completed()

        completion = command._format_completion_time(entry)

        assert "**Completed**:" in completion
        assert "ago" in completion

    def test_format_completion_time_no_completion(self, command: HistoryCommand) -> None:
        """Test _format_completion_time without completion time."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test",
        )

        completion = command._format_completion_time(entry)

        assert completion == ""
