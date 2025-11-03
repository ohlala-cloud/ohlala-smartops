"""Tests for slash command implementations.

This test suite covers the command infrastructure including BaseCommand,
HelpCommand, and StatusCommand.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from ohlala_smartops.commands import BaseCommand, HelpCommand, StatusCommand


# Concrete command for testing BaseCommand
class TestCommand(BaseCommand):
    """Test command implementation for BaseCommand testing."""

    @property
    def name(self) -> str:
        """Command name."""
        return "test"

    @property
    def description(self) -> str:
        """Command description."""
        return "Test command"

    async def execute(self, args: list[str], context: dict) -> dict:
        """Execute test command."""
        return {"success": True, "message": "Test executed"}


class TestBaseCommand:
    """Test suite for BaseCommand class."""

    @pytest.fixture
    def command(self) -> TestCommand:
        """Create test command instance."""
        return TestCommand()

    # Property tests

    def test_name_property(self, command: TestCommand) -> None:
        """Test name property."""
        assert command.name == "test"

    def test_description_property(self, command: TestCommand) -> None:
        """Test description property."""
        assert command.description == "Test command"

    def test_usage_property(self, command: TestCommand) -> None:
        """Test usage property default."""
        assert command.usage == "/test"

    def test_visible_to_users_default(self, command: TestCommand) -> None:
        """Test visible_to_users defaults to True."""
        assert command.visible_to_users is True

    # Instance ID parsing tests

    def test_parse_instance_id_valid(self, command: TestCommand) -> None:
        """Test parsing valid instance ID."""
        result = command.parse_instance_id(["i-1234567890abcdef0", "other"])
        assert result == "i-1234567890abcdef0"

    def test_parse_instance_id_no_args(self, command: TestCommand) -> None:
        """Test parsing with no arguments."""
        result = command.parse_instance_id([])
        assert result is None

    def test_parse_instance_id_fallback(self, command: TestCommand) -> None:
        """Test parsing falls back to first arg."""
        result = command.parse_instance_id(["not-valid-id"])
        assert result == "not-valid-id"

    def test_parse_instance_ids_multiple(self, command: TestCommand) -> None:
        """Test parsing multiple instance IDs."""
        result = command.parse_instance_ids(["i-1234567890abcdef0", "i-0987654321fedcba9"])
        assert len(result) == 2
        assert "i-1234567890abcdef0" in result
        assert "i-0987654321fedcba9" in result

    def test_parse_instance_ids_comma_separated(self, command: TestCommand) -> None:
        """Test parsing comma-separated instance IDs."""
        result = command.parse_instance_ids(["i-1234567890abcdef0,i-0987654321fedcba9"])
        assert len(result) == 2

    def test_parse_instance_ids_empty(self, command: TestCommand) -> None:
        """Test parsing with no valid IDs."""
        result = command.parse_instance_ids(["not-valid", "also-invalid"])
        assert result == []

    # Card creation tests

    def test_create_error_card(self, command: TestCommand) -> None:
        """Test creating error card."""
        card = command.create_error_card("Error Title", "Error message")

        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.5"
        assert len(card["body"]) == 1
        assert card["body"][0]["type"] == "Container"
        assert card["body"][0]["style"] == "attention"

    def test_create_success_card(self, command: TestCommand) -> None:
        """Test creating success card."""
        card = command.create_success_card("Success Title", "Success message")

        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.5"
        assert len(card["body"]) == 1
        assert card["body"][0]["type"] == "Container"
        assert card["body"][0]["style"] == "good"

    def test_apply_brand_colors(self, command: TestCommand) -> None:
        """Test applying brand colors to card."""
        card = {
            "type": "AdaptiveCard",
            "body": [
                {
                    "type": "Chart.Line",
                    "data": [
                        {"name": "Series1"},
                        {"name": "Series2"},
                    ],
                }
            ],
        }

        result = command.apply_brand_colors(card)

        # Should add colors to chart data
        assert "color" in result["body"][0]["data"][0]
        assert "color" in result["body"][0]["data"][1]
        assert result["body"][0]["data"][0]["color"] == "#FF9900"  # AWS Orange

    def test_apply_brand_colors_no_charts(self, command: TestCommand) -> None:
        """Test applying brand colors with no charts."""
        card = {
            "type": "AdaptiveCard",
            "body": [{"type": "TextBlock", "text": "No charts"}],
        }

        result = command.apply_brand_colors(card)
        assert result == card  # Should return unchanged

    # MCP tool call tests

    @pytest.mark.asyncio
    async def test_call_mcp_tool_success(self, command: TestCommand) -> None:
        """Test calling MCP tool successfully."""
        mock_mcp = AsyncMock()
        mock_mcp.call_aws_api_tool.return_value = {"status": "success"}

        context = {"mcp_manager": mock_mcp}

        result = await command.call_mcp_tool("test-tool", {"arg": "value"}, context)

        assert result == {"status": "success"}
        mock_mcp.call_aws_api_tool.assert_called_once_with(
            "test-tool", {"arg": "value"}, turn_context=None
        )

    @pytest.mark.asyncio
    async def test_call_mcp_tool_no_manager(self, command: TestCommand) -> None:
        """Test calling MCP tool without manager."""
        context = {}

        with pytest.raises(ValueError, match="MCP manager not available"):
            await command.call_mcp_tool("test-tool", {}, context)

    # Instance validation tests

    @pytest.mark.asyncio
    async def test_validate_instances_exist_success(self, command: TestCommand) -> None:
        """Test validating instances successfully."""
        mock_mcp = AsyncMock()
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "running"}]
        }

        context = {"mcp_manager": mock_mcp}

        result = await command.validate_instances_exist(["i-1234567890abcdef0"], context)

        assert result["success"] is True
        assert len(result["instances"]) == 1

    @pytest.mark.asyncio
    async def test_validate_instances_no_ids(self, command: TestCommand) -> None:
        """Test validating with no instance IDs."""
        result = await command.validate_instances_exist([], {})

        assert result["success"] is False
        assert "No instance IDs" in result["error"]

    @pytest.mark.asyncio
    async def test_validate_instances_missing(self, command: TestCommand) -> None:
        """Test validating with missing instances."""
        mock_mcp = AsyncMock()
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0"}]
        }

        context = {"mcp_manager": mock_mcp}

        result = await command.validate_instances_exist(
            ["i-1234567890abcdef0", "i-missing"], context
        )

        assert result["success"] is False
        assert "i-missing" in result["error"]

    # Filter instances tests

    def test_filter_instances_by_state_valid(self, command: TestCommand) -> None:
        """Test filtering instances by state."""
        instances = [
            {"InstanceId": "i-123", "State": "running", "Name": "Instance1"},
            {"InstanceId": "i-456", "State": "stopped", "Name": "Instance2"},
        ]

        result = command.filter_instances_by_state(instances, ["running"])

        assert len(result["valid_instances"]) == 1
        assert len(result["invalid_instances"]) == 1
        assert result["error_message"] is not None

    def test_filter_instances_by_state_all_valid(self, command: TestCommand) -> None:
        """Test filtering with all instances valid."""
        instances = [
            {"InstanceId": "i-123", "State": "running", "Name": "Instance1"},
            {"InstanceId": "i-456", "State": "running", "Name": "Instance2"},
        ]

        result = command.filter_instances_by_state(instances, ["running"])

        assert len(result["valid_instances"]) == 2
        assert len(result["invalid_instances"]) == 0
        assert result["error_message"] is None


class TestHelpCommand:
    """Test suite for HelpCommand class."""

    @pytest.fixture
    def command(self) -> HelpCommand:
        """Create help command instance."""
        return HelpCommand()

    # Property tests

    def test_name_property(self, command: HelpCommand) -> None:
        """Test name property."""
        assert command.name == "help"

    def test_description_property(self, command: HelpCommand) -> None:
        """Test description property."""
        assert "available commands" in command.description.lower()

    def test_usage_property(self, command: HelpCommand) -> None:
        """Test usage property."""
        assert "/help" in command.usage

    # Execute tests

    @pytest.mark.asyncio
    async def test_execute_general_help(self, command: HelpCommand) -> None:
        """Test executing general help."""
        result = await command.execute([], {})

        assert result["success"] is True
        assert "card" in result
        assert result["card"]["type"] == "AdaptiveCard"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_execute_specific_help_exists(self, command: HelpCommand) -> None:
        """Test getting help for specific command."""
        result = await command.execute(["status"], {})

        assert result["success"] is True
        assert "card" in result
        assert "Status Command" in str(result["card"])

    @pytest.mark.asyncio
    async def test_execute_specific_help_not_found(self, command: HelpCommand) -> None:
        """Test getting help for non-existent command."""
        result = await command.execute(["nonexistent"], {})

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_error_handling(self, command: HelpCommand) -> None:
        """Test error handling in execute."""

        # Patch _show_general_help to raise exception
        async def raise_error() -> dict:
            raise Exception("Test error")

        command._show_general_help = raise_error  # type: ignore[method-assign]

        result = await command.execute([], {})

        assert result["success"] is False
        assert "error" in result


class TestStatusCommand:
    """Test suite for StatusCommand class."""

    @pytest.fixture
    def command(self) -> StatusCommand:
        """Create status command instance."""
        return StatusCommand()

    @pytest.fixture
    def mock_tracker(self) -> Mock:
        """Create mock command tracker."""
        tracker = Mock()
        tracker.get_active_command_count.return_value = 0
        tracker.get_active_workflow_count.return_value = 0
        tracker.active_commands = {}
        tracker.active_workflows = {}
        return tracker

    # Property tests

    def test_name_property(self, command: StatusCommand) -> None:
        """Test name property."""
        assert command.name == "status"

    def test_description_property(self, command: StatusCommand) -> None:
        """Test description property."""
        assert "pending" in command.description.lower()

    def test_usage_property(self, command: StatusCommand) -> None:
        """Test usage property."""
        assert command.usage == "/status"

    # Execute tests

    @pytest.mark.asyncio
    async def test_execute_no_tracker(self, command: StatusCommand) -> None:
        """Test execute without command tracker."""
        result = await command.execute([], {})

        assert result["success"] is True
        assert "No Active Commands" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_no_active_commands(
        self, command: StatusCommand, mock_tracker: Mock
    ) -> None:
        """Test execute with no active commands."""
        context = {"command_tracker": mock_tracker}

        result = await command.execute([], context)

        assert result["success"] is True
        assert "No Active Commands" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_with_active_commands(
        self, command: StatusCommand, mock_tracker: Mock
    ) -> None:
        """Test execute with active commands."""
        # Set up active commands
        mock_tracker.get_active_command_count.return_value = 2
        mock_tracker.get_active_workflow_count.return_value = 1

        # Create mock tracking info
        mock_tracking = Mock()
        mock_tracking.instance_id = "i-1234567890abcdef0"
        mock_tracking.status = Mock(value="InProgress")
        mock_tracking.submitted_at = datetime.now(UTC)

        mock_tracker.active_commands = {"cmd-123": mock_tracking}

        # Create mock workflow
        mock_workflow = Mock()
        mock_workflow.operation_type = "start-instances"
        mock_workflow.completed_count = 1
        mock_workflow.expected_count = 2
        mock_workflow.success_count = 1

        mock_tracker.active_workflows = {"wf-123": mock_workflow}

        context = {"command_tracker": mock_tracker}

        result = await command.execute([], context)

        assert result["success"] is True
        assert "card" in result
        assert result["card"]["type"] == "AdaptiveCard"
        assert "2 active commands" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_error_handling(self, command: StatusCommand, mock_tracker: Mock) -> None:
        """Test error handling in execute."""
        # Make tracker raise exception
        mock_tracker.get_active_command_count.side_effect = Exception("Test error")

        context = {"command_tracker": mock_tracker}

        result = await command.execute([], context)

        assert result["success"] is False
        assert "error" in result

    # Helper method tests

    def test_get_elapsed_time_seconds(self, command: StatusCommand) -> None:
        """Test elapsed time for seconds."""
        timestamp = datetime.now(UTC)
        result = command._get_elapsed_time(timestamp)

        assert "second" in result.lower()

    def test_get_elapsed_time_minutes(self, command: StatusCommand) -> None:
        """Test elapsed time for minutes."""
        timestamp = datetime.now(UTC) - timedelta(minutes=5)
        result = command._get_elapsed_time(timestamp)

        assert "minute" in result.lower()
        assert "5" in result

    def test_get_elapsed_time_hours(self, command: StatusCommand) -> None:
        """Test elapsed time for hours."""
        timestamp = datetime.now(UTC) - timedelta(hours=2)
        result = command._get_elapsed_time(timestamp)

        assert "hour" in result.lower()
        assert "2" in result

    def test_get_elapsed_time_days(self, command: StatusCommand) -> None:
        """Test elapsed time for days."""
        timestamp = datetime.now(UTC) - timedelta(days=3)
        result = command._get_elapsed_time(timestamp)

        assert "day" in result.lower()
        assert "3" in result
