"""Tests for instance management commands.

This test suite covers Phase 5B instance management commands and supporting
infrastructure including adaptive cards, confirmation system, and command
implementations (list, start, stop, reboot).
"""

from unittest.mock import AsyncMock

import pytest

from ohlala_smartops.commands import (
    ListInstancesCommand,
    RebootInstanceCommand,
    StartInstanceCommand,
    StopInstanceCommand,
)
from ohlala_smartops.commands.adaptive_cards import (
    COLORS,
    CardTemplates,
    get_metric_color,
    get_platform_icon,
    get_status_color,
)
from ohlala_smartops.commands.confirmation import ConfirmationManager, PendingOperation


# Tests for adaptive cards styles
class TestAdaptiveCardsStyles:
    """Test suite for adaptive cards styles module."""

    def test_colors_defined(self) -> None:
        """Test color constants are defined."""
        assert "primary" in COLORS
        assert "success" in COLORS
        assert "warning" in COLORS
        assert "error" in COLORS

    def test_get_status_color_running(self) -> None:
        """Test status color for running state."""
        assert get_status_color("running") == "Good"
        assert get_status_color("healthy") == "Good"
        assert get_status_color("success") == "Good"

    def test_get_status_color_stopped(self) -> None:
        """Test status color for stopped state."""
        assert get_status_color("stopped") == "Attention"
        assert get_status_color("error") == "Attention"
        assert get_status_color("failed") == "Attention"

    def test_get_status_color_warning(self) -> None:
        """Test status color for warning state."""
        assert get_status_color("pending") == "Warning"
        assert get_status_color("warning") == "Warning"
        assert get_status_color("degraded") == "Warning"

    def test_get_status_color_unknown(self) -> None:
        """Test status color for unknown state."""
        assert get_status_color("unknown") == "Default"
        assert get_status_color("something_random") == "Default"

    def test_get_metric_color_good(self) -> None:
        """Test metric color for good values."""
        assert get_metric_color(45.0) == "Good"
        assert get_metric_color(59.9) == "Good"

    def test_get_metric_color_warning(self) -> None:
        """Test metric color for warning values."""
        assert get_metric_color(65.0) == "Warning"
        assert get_metric_color(79.9) == "Warning"

    def test_get_metric_color_critical(self) -> None:
        """Test metric color for critical values."""
        assert get_metric_color(85.0) == "Attention"
        assert get_metric_color(95.0) == "Attention"

    def test_get_metric_color_custom_thresholds(self) -> None:
        """Test metric color with custom thresholds."""
        thresholds = {"good": 50.0, "warning": 70.0, "critical": 90.0}
        assert get_metric_color(45.0, thresholds) == "Good"
        assert get_metric_color(65.0, thresholds) == "Warning"
        assert get_metric_color(95.0, thresholds) == "Attention"

    def test_get_platform_icon_linux(self) -> None:
        """Test platform icon for Linux."""
        assert get_platform_icon("Linux") == "🐧"
        assert get_platform_icon("linux") == "🐧"

    def test_get_platform_icon_windows(self) -> None:
        """Test platform icon for Windows."""
        assert get_platform_icon("Windows") == "🪟"
        assert get_platform_icon("windows") == "🪟"

    def test_get_platform_icon_unknown(self) -> None:
        """Test platform icon for unknown platform."""
        assert get_platform_icon("Unknown") == "💻"


# Tests for adaptive cards templates
class TestCardTemplates:
    """Test suite for adaptive cards templates."""

    def test_create_instance_card(self) -> None:
        """Test creating instance card."""
        card = CardTemplates.create_instance_card(
            "i-1234567890abcdef04567890abcdef0",
            "web-server-01",
            "t3.micro",
            "running",
            "Linux",
            "10.0.1.50",
        )

        assert card["type"] == "Container"
        assert card["style"] == "emphasis"  # running instances use emphasis
        assert len(card["items"]) >= 1

    def test_create_instance_card_stopped(self) -> None:
        """Test creating card for stopped instance."""
        card = CardTemplates.create_instance_card(
            "i-1234567890abcdef04567890abcdef0",
            "web-server-01",
            "t3.micro",
            "stopped",
            "Linux",
        )

        assert card["type"] == "Container"
        assert card["style"] == "default"  # stopped instances use default

    def test_create_action_button(self) -> None:
        """Test creating action button."""
        button = CardTemplates.create_action_button(
            "Start", "start_instance", "i-1234567890abcdef0", style="positive", icon="▶️"
        )

        assert button["type"] == "Action.Submit"
        assert button["title"] == "▶️ Start"
        assert button["data"]["action"] == "start_instance"
        assert button["data"]["instanceId"] == "i-1234567890abcdef0"
        assert button["style"] == "positive"

    def test_create_action_button_destructive(self) -> None:
        """Test creating destructive action button."""
        button = CardTemplates.create_action_button(
            "Delete", "delete_instance", "i-1234567890abcdef0", style="destructive"
        )

        assert button["style"] == "destructive"

    def test_create_fact_set(self) -> None:
        """Test creating fact set."""
        facts = CardTemplates.create_fact_set(
            {"Instance ID": "i-1234567890abcdef0", "Type": "t3.micro", "CPU": 45.5}
        )

        assert facts["type"] == "FactSet"
        assert len(facts["facts"]) == 3
        assert facts["facts"][0]["title"] == "Instance ID"
        assert facts["facts"][0]["value"] == "i-1234567890abcdef0"

    def test_create_metric_gauge(self) -> None:
        """Test creating metric gauge."""
        gauge = CardTemplates.create_metric_gauge("CPU", 45.5)

        assert gauge["type"] == "Column"
        assert len(gauge["items"]) == 3  # title, bar, value

    def test_create_state_summary(self) -> None:
        """Test creating state summary."""
        state_counts = {"running": 5, "stopped": 2, "pending": 1}
        summary = CardTemplates.create_state_summary(state_counts)

        assert summary["type"] == "Container"
        assert "items" in summary


# Tests for confirmation system
class TestConfirmationManager:
    """Test suite for confirmation manager."""

    @pytest.fixture
    def manager(self) -> ConfirmationManager:
        """Create confirmation manager instance."""
        return ConfirmationManager()

    def test_create_confirmation_request(self, manager: ConfirmationManager) -> None:
        """Test creating confirmation request."""
        operation = manager.create_confirmation_request(
            operation_type="start-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Start 1 instance",
        )

        assert isinstance(operation, PendingOperation)
        assert operation.operation_type == "start-instances"
        assert operation.resource_ids == ["i-1234567890abcdef0"]
        assert operation.user_id == "user-123"
        assert operation.id in manager.pending_operations

    def test_get_pending_operation(self, manager: ConfirmationManager) -> None:
        """Test getting pending operation."""
        operation = manager.create_confirmation_request(
            operation_type="start-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Start 1 instance",
        )

        retrieved = manager.get_pending_operation(operation.id)
        assert retrieved is not None
        assert retrieved.id == operation.id

    def test_get_pending_operation_not_found(self, manager: ConfirmationManager) -> None:
        """Test getting non-existent operation."""
        result = manager.get_pending_operation("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_confirm_operation_success(self, manager: ConfirmationManager) -> None:
        """Test confirming operation successfully."""
        executed = False

        async def callback(op: PendingOperation) -> dict:
            nonlocal executed
            executed = True
            return {"status": "success"}

        operation = manager.create_confirmation_request(
            operation_type="start-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Start 1 instance",
            callback=callback,
        )

        result = await manager.confirm_operation(operation.id, "user-123")

        assert result["success"] is True
        assert executed is True
        assert operation.id not in manager.pending_operations

    @pytest.mark.asyncio
    async def test_confirm_operation_wrong_user(self, manager: ConfirmationManager) -> None:
        """Test confirming operation as wrong user."""
        operation = manager.create_confirmation_request(
            operation_type="start-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Start 1 instance",
        )

        result = await manager.confirm_operation(operation.id, "user-456")

        assert result["success"] is False
        assert "only confirm your own" in result["error"]

    def test_cancel_operation(self, manager: ConfirmationManager) -> None:
        """Test cancelling operation."""
        operation = manager.create_confirmation_request(
            operation_type="start-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Start 1 instance",
        )

        result = manager.cancel_operation(operation.id, "user-123")

        assert result is True
        assert operation.id not in manager.pending_operations

    def test_get_user_pending_operations(self, manager: ConfirmationManager) -> None:
        """Test getting user's pending operations."""
        manager.create_confirmation_request(
            operation_type="start-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Start 1 instance",
        )
        manager.create_confirmation_request(
            operation_type="stop-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-0987654321fedcba9"],
            user_id="user-123",
            user_name="Alice",
            description="Stop 1 instance",
        )
        manager.create_confirmation_request(
            operation_type="reboot-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-abcdef1234567890a"],
            user_id="user-456",
            user_name="Bob",
            description="Reboot 1 instance",
        )

        operations = manager.get_user_pending_operations("user-123")

        assert len(operations) == 2
        assert all(op.user_id == "user-123" for op in operations)

    def test_create_confirmation_card(self, manager: ConfirmationManager) -> None:
        """Test creating confirmation card."""
        operation = manager.create_confirmation_request(
            operation_type="start-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Start 1 instance",
        )

        card = manager.create_confirmation_card(operation)

        assert card["type"] == "AdaptiveCard"
        assert len(card["actions"]) == 2  # Confirm and Cancel
        assert card["actions"][0]["title"] == "✅ Confirm"
        assert card["actions"][1]["title"] == "❌ Cancel"


# Tests for list instances command
class TestListInstancesCommand:
    """Test suite for ListInstancesCommand."""

    @pytest.fixture
    def command(self) -> ListInstancesCommand:
        """Create list instances command instance."""
        return ListInstancesCommand()

    @pytest.fixture
    def mock_context(self) -> dict:
        """Create mock context."""
        mock_mcp = AsyncMock()
        return {"mcp_manager": mock_mcp}

    def test_name_property(self, command: ListInstancesCommand) -> None:
        """Test name property."""
        assert command.name == "list"

    def test_description_property(self, command: ListInstancesCommand) -> None:
        """Test description property."""
        assert "list" in command.description.lower()
        assert "instances" in command.description.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, command: ListInstancesCommand, mock_context: dict) -> None:
        """Test executing list command successfully."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "Name": "web-01",
                    "InstanceType": "t3.micro",
                    "State": "running",
                    "Platform": "Linux",
                }
            ]
        }

        result = await command.execute([], mock_context)

        assert result["success"] is True
        assert "card" in result
        assert "1" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_no_instances(
        self, command: ListInstancesCommand, mock_context: dict
    ) -> None:
        """Test executing list with no instances."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {"instances": []}

        result = await command.execute([], mock_context)

        assert result["success"] is True
        assert "No EC2 instances" in result["message"]


# Tests for start instances command
class TestStartInstanceCommand:
    """Test suite for StartInstanceCommand."""

    @pytest.fixture
    def command(self) -> StartInstanceCommand:
        """Create start instances command instance."""
        return StartInstanceCommand()

    @pytest.fixture
    def mock_context(self) -> dict:
        """Create mock context."""
        mock_mcp = AsyncMock()
        return {
            "mcp_manager": mock_mcp,
            "user_id": "user-123",
            "user_name": "Alice",
        }

    def test_name_property(self, command: StartInstanceCommand) -> None:
        """Test name property."""
        assert command.name == "start"

    @pytest.mark.asyncio
    async def test_execute_no_user_id(
        self, command: StartInstanceCommand, mock_context: dict
    ) -> None:
        """Test executing without user ID."""
        del mock_context["user_id"]
        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False
        assert "Unable to identify user" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_no_instance_ids(
        self, command: StartInstanceCommand, mock_context: dict
    ) -> None:
        """Test executing without instance IDs."""
        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "provide instance ID" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_invalid_state(
        self, command: StartInstanceCommand, mock_context: dict
    ) -> None:
        """Test executing on running instance."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "running"}]
        }

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False
        assert "cannot be started" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_success(self, command: StartInstanceCommand, mock_context: dict) -> None:
        """Test executing start command successfully."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "stopped"}]
        }

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is True
        assert "card" in result


# Tests for stop instances command
class TestStopInstanceCommand:
    """Test suite for StopInstanceCommand."""

    @pytest.fixture
    def command(self) -> StopInstanceCommand:
        """Create stop instances command instance."""
        return StopInstanceCommand()

    @pytest.fixture
    def mock_context(self) -> dict:
        """Create mock context."""
        mock_mcp = AsyncMock()
        return {
            "mcp_manager": mock_mcp,
            "user_id": "user-123",
            "user_name": "Alice",
        }

    def test_name_property(self, command: StopInstanceCommand) -> None:
        """Test name property."""
        assert command.name == "stop"

    @pytest.mark.asyncio
    async def test_execute_invalid_state(
        self, command: StopInstanceCommand, mock_context: dict
    ) -> None:
        """Test executing on stopped instance."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "stopped"}]
        }

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False
        assert "cannot be stopped" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_success(self, command: StopInstanceCommand, mock_context: dict) -> None:
        """Test executing stop command successfully."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "running"}]
        }

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is True
        assert "card" in result


# Tests for reboot instances command
class TestRebootInstanceCommand:
    """Test suite for RebootInstanceCommand."""

    @pytest.fixture
    def command(self) -> RebootInstanceCommand:
        """Create reboot instances command instance."""
        return RebootInstanceCommand()

    @pytest.fixture
    def mock_context(self) -> dict:
        """Create mock context."""
        mock_mcp = AsyncMock()
        return {
            "mcp_manager": mock_mcp,
            "user_id": "user-123",
            "user_name": "Alice",
        }

    def test_name_property(self, command: RebootInstanceCommand) -> None:
        """Test name property."""
        assert command.name == "reboot"

    @pytest.mark.asyncio
    async def test_execute_stopped_instance(
        self, command: RebootInstanceCommand, mock_context: dict
    ) -> None:
        """Test executing on stopped instance."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "stopped"}]
        }

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False
        assert "Cannot reboot stopped" in result["message"]
        assert "start them first" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_success(
        self, command: RebootInstanceCommand, mock_context: dict
    ) -> None:
        """Test executing reboot command successfully."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "running"}]
        }

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is True
        assert "card" in result
