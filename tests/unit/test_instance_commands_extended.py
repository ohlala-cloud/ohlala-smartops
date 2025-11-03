"""Extended tests for instance management commands to improve coverage.

This test suite adds additional tests to achieve higher coverage for Phase 5B
instance management commands, focusing on error paths, edge cases, and
lifecycle management.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ohlala_smartops.commands import (
    ListInstancesCommand,
    RebootInstanceCommand,
    StartInstanceCommand,
    StopInstanceCommand,
)
from ohlala_smartops.commands.adaptive_cards import CardTemplates
from ohlala_smartops.commands.confirmation import ConfirmationManager


class TestConfirmationManagerLifecycle:
    """Test suite for ConfirmationManager lifecycle methods."""

    @pytest.fixture
    def manager(self) -> ConfirmationManager:
        """Create confirmation manager instance."""
        return ConfirmationManager()

    @pytest.mark.asyncio
    async def test_start_manager(self, manager: ConfirmationManager) -> None:
        """Test starting confirmation manager."""
        await manager.start()
        assert manager._cleanup_task is not None
        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_manager_with_task(self, manager: ConfirmationManager) -> None:
        """Test stopping manager with active cleanup task."""
        await manager.start()
        await manager.stop()
        assert manager._cleanup_task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_manager_without_task(self, manager: ConfirmationManager) -> None:
        """Test stopping manager without active task."""
        await manager.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_cleanup_expired_operations(self, manager: ConfirmationManager) -> None:
        """Test cleanup of expired operations."""
        # Create an operation that's already expired
        operation = manager.create_confirmation_request(
            operation_type="test-op",
            resource_type="Test",
            resource_ids=["test-1"],
            user_id="user-123",
            user_name="Alice",
            description="Test operation",
        )

        # Manually expire it
        manager.pending_operations[operation.id].expires_at = datetime.now(UTC) - timedelta(
            minutes=1
        )

        # Call get_pending_operation which triggers cleanup
        result = manager.get_pending_operation(operation.id)

        # Operation should have been cleaned up and return None
        assert result is None
        assert operation.id not in manager.pending_operations

    @pytest.mark.asyncio
    async def test_confirm_operation_callback_error(self, manager: ConfirmationManager) -> None:
        """Test confirming operation when callback raises error."""

        async def failing_callback(op: Any) -> None:
            raise Exception("Callback failed")

        operation = manager.create_confirmation_request(
            operation_type="test-op",
            resource_type="Test",
            resource_ids=["test-1"],
            user_id="user-123",
            user_name="Alice",
            description="Test operation",
            callback=failing_callback,
        )

        result = await manager.confirm_operation(operation.id, "user-123")

        assert result["success"] is False
        assert "failed" in result["error"].lower()

    def test_get_user_pending_operations_with_expired(self, manager: ConfirmationManager) -> None:
        """Test getting user operations when some are expired."""
        # Create active operation
        op1 = manager.create_confirmation_request(
            operation_type="test-op-1",
            resource_type="Test",
            resource_ids=["test-1"],
            user_id="user-123",
            user_name="Alice",
            description="Active operation",
        )

        # Create expired operation
        op2 = manager.create_confirmation_request(
            operation_type="test-op-2",
            resource_type="Test",
            resource_ids=["test-2"],
            user_id="user-123",
            user_name="Alice",
            description="Expired operation",
        )

        # Manually expire the second one
        manager.pending_operations[op2.id].expires_at = datetime.now(UTC) - timedelta(minutes=1)

        # Get user operations (should only return active)
        operations = manager.get_user_pending_operations("user-123")

        assert len(operations) == 1
        assert operations[0].id == op1.id
        assert op2.id not in manager.pending_operations


class TestCardTemplatesEdgeCases:
    """Test suite for edge cases in card templates."""

    def test_create_instance_card_no_ip(self) -> None:
        """Test creating instance card without IP address."""
        card = CardTemplates.create_instance_card(
            "i-1234567890abcdef0", "test", "t3.micro", "running", "Linux", None
        )

        assert card["type"] == "Container"
        # Should not have IP address text block
        assert len(card["items"]) == 1  # Only columnset, no IP

    def test_create_action_button_without_icon(self) -> None:
        """Test creating action button without icon."""
        button = CardTemplates.create_action_button("Test", "test_action", "i-1234567890abcdef0")

        assert button["title"] == "Test"
        assert "data" in button

    def test_create_action_button_with_extra_data(self) -> None:
        """Test creating action button with extra kwargs."""
        button = CardTemplates.create_action_button(
            "Test",
            "test_action",
            "i-1234567890abcdef0",
            extra_field="value",
            another="data",
        )

        assert button["data"]["extra_field"] == "value"
        assert button["data"]["another"] == "data"

    def test_create_metric_gauge_high_value(self) -> None:
        """Test metric gauge with high value."""
        gauge = CardTemplates.create_metric_gauge("CPU", 95.0)

        # Should be in Attention color
        items = gauge["items"]
        assert any(item.get("color") == "Attention" for item in items if "color" in item)


class TestListInstancesCommandEdgeCases:
    """Test suite for list instances edge cases."""

    @pytest.fixture
    def command(self) -> ListInstancesCommand:
        """Create list instances command instance."""
        return ListInstancesCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        mock_mcp = AsyncMock()
        return {"mcp_manager": mock_mcp}

    @pytest.mark.asyncio
    async def test_execute_with_turn_context(
        self, command: ListInstancesCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test executing with turn context provided."""
        mock_context["turn_context"] = Mock()
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "Name": "test",
                    "InstanceType": "t3.micro",
                    "State": "running",
                    "Platform": "Linux",
                }
            ]
        }

        result = await command.execute([], mock_context)

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_mcp_error(
        self, command: ListInstancesCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test executing when MCP raises error."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("MCP error")

        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "error" in result
        assert "card" in result

    def test_build_instances_card_mixed_states(self, command: ListInstancesCommand) -> None:
        """Test building card with mixed instance states."""
        instances = [
            {
                "InstanceId": "i-1234567890abcdef0",
                "Name": "running-1",
                "InstanceType": "t3.micro",
                "State": "running",
                "Platform": "Linux",
            },
            {
                "InstanceId": "i-0987654321fedcba9",
                "Name": "stopped-1",
                "InstanceType": "t3.small",
                "State": "stopped",
                "Platform": "Windows",
            },
            {
                "InstanceId": "i-abcdef1234567890a",
                "Name": "pending-1",
                "InstanceType": "t3.medium",
                "State": "pending",
                "Platform": "Linux",
            },
        ]

        card = command._build_instances_card(instances)

        assert card["type"] == "AdaptiveCard"
        assert len(card["body"]) > 3  # Should have summary + instances


class TestStartInstanceCommandEdgeCases:
    """Test suite for start instance edge cases."""

    @pytest.fixture
    def command(self) -> StartInstanceCommand:
        """Create start instance command instance."""
        return StartInstanceCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        mock_mcp = AsyncMock()
        return {
            "mcp_manager": mock_mcp,
            "user_id": "user-123",
            "user_name": "Alice",
        }

    @pytest.mark.asyncio
    async def test_execute_validation_error(
        self, command: StartInstanceCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test executing when validation fails."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("Validation error")

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_command_error(
        self, command: StartInstanceCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test executing when command raises unexpected error."""
        # Mock to raise error after validation
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "stopped"}]
        }

        # Patch confirmation manager to raise error
        with patch("ohlala_smartops.commands.start.confirmation_manager") as mock_cm:
            mock_cm.create_confirmation_request.side_effect = Exception("Unexpected error")

            result = await command.execute(["i-1234567890abcdef0"], mock_context)

            assert result["success"] is False
            assert "card" in result


class TestStopInstanceCommandEdgeCases:
    """Test suite for stop instance edge cases."""

    @pytest.fixture
    def command(self) -> StopInstanceCommand:
        """Create stop instance command instance."""
        return StopInstanceCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        mock_mcp = AsyncMock()
        return {
            "mcp_manager": mock_mcp,
            "user_id": "user-123",
            "user_name": "Alice",
        }

    @pytest.mark.asyncio
    async def test_execute_command_error(
        self, command: StopInstanceCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test executing when command raises unexpected error."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "running"}]
        }

        with patch("ohlala_smartops.commands.stop.confirmation_manager") as mock_cm:
            mock_cm.create_confirmation_request.side_effect = Exception("Unexpected error")

            result = await command.execute(["i-1234567890abcdef0"], mock_context)

            assert result["success"] is False


class TestRebootInstanceCommandEdgeCases:
    """Test suite for reboot instance edge cases."""

    @pytest.fixture
    def command(self) -> RebootInstanceCommand:
        """Create reboot instance command instance."""
        return RebootInstanceCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        mock_mcp = AsyncMock()
        return {
            "mcp_manager": mock_mcp,
            "user_id": "user-123",
            "user_name": "Alice",
        }

    @pytest.mark.asyncio
    async def test_execute_mixed_states(
        self, command: RebootInstanceCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test executing on instances with mixed states."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {"InstanceId": "i-1234567890abcdef0", "State": "running"},
                {"InstanceId": "i-0987654321fedcba9", "State": "pending"},
            ]
        }

        result = await command.execute(["i-1234567890abcdef0", "i-0987654321fedcba9"], mock_context)

        assert result["success"] is False
        assert "cannot be rebooted" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_command_error(
        self, command: RebootInstanceCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test executing when command raises unexpected error."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [{"InstanceId": "i-1234567890abcdef0", "State": "running"}]
        }

        with patch("ohlala_smartops.commands.reboot.confirmation_manager") as mock_cm:
            mock_cm.create_confirmation_request.side_effect = Exception("Unexpected error")

            result = await command.execute(["i-1234567890abcdef0"], mock_context)

            assert result["success"] is False


class TestConfirmationCallbacks:
    """Test suite for confirmation callback execution."""

    @pytest.fixture
    def manager(self) -> ConfirmationManager:
        """Create confirmation manager instance."""
        return ConfirmationManager()

    @pytest.mark.asyncio
    async def test_confirm_without_callback(self, manager: ConfirmationManager) -> None:
        """Test confirming operation without callback."""
        operation = manager.create_confirmation_request(
            operation_type="test-op",
            resource_type="Test",
            resource_ids=["test-1"],
            user_id="user-123",
            user_name="Alice",
            description="Test operation",
            callback=None,
        )

        result = await manager.confirm_operation(operation.id, "user-123")

        assert result["success"] is True
        assert "operation" in result

    def test_cancel_wrong_user(self, manager: ConfirmationManager) -> None:
        """Test cancelling operation as wrong user."""
        operation = manager.create_confirmation_request(
            operation_type="test-op",
            resource_type="Test",
            resource_ids=["test-1"],
            user_id="user-123",
            user_name="Alice",
            description="Test operation",
        )

        result = manager.cancel_operation(operation.id, "user-456")

        assert result is False
        assert operation.id in manager.pending_operations

    def test_cancel_nonexistent(self, manager: ConfirmationManager) -> None:
        """Test cancelling non-existent operation."""
        result = manager.cancel_operation("nonexistent", "user-123")
        assert result is False

    def test_create_confirmation_card_start(self, manager: ConfirmationManager) -> None:
        """Test creating confirmation card for start operation."""
        operation = manager.create_confirmation_request(
            operation_type="start-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Start 1 instance",
        )

        card = manager.create_confirmation_card(operation)

        assert "Start Instances" in card["body"][0]["text"]
        # Verify that start operation shows as informational with INFO text
        assert any("INFO" in str(item.get("text", "")) for item in card["body"])

    def test_create_confirmation_card_reboot(self, manager: ConfirmationManager) -> None:
        """Test creating confirmation card for reboot operation."""
        operation = manager.create_confirmation_request(
            operation_type="reboot-instances",
            resource_type="EC2 Instance",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="Alice",
            description="Reboot 1 instance",
        )

        card = manager.create_confirmation_card(operation)

        assert "Reboot Instances" in card["body"][0]["text"]
        # Verify that reboot operation shows as disruptive with WARNING text
        assert any("WARNING" in str(item.get("text", "")) for item in card["body"])

    def test_create_confirmation_card_multiple_resources(
        self, manager: ConfirmationManager
    ) -> None:
        """Test creating confirmation card with many resources."""
        # Create operation with more than 3 resources
        resource_ids = [f"i-{i:017x}" for i in range(5)]

        operation = manager.create_confirmation_request(
            operation_type="stop-instances",
            resource_type="EC2 Instance",
            resource_ids=resource_ids,
            user_id="user-123",
            user_name="Alice",
            description="Stop 5 instances",
        )

        card = manager.create_confirmation_card(operation)

        # Should show first 3 with "..."
        fact_set = next(item for item in card["body"] if item.get("type") == "FactSet")
        resource_fact = next(fact for fact in fact_set["facts"] if fact["title"] == "Resource IDs:")

        assert "..." in resource_fact["value"]
