"""Tests for card handler functionality.

This test suite covers adaptive card action handling, including approval
workflows, denial workflows, and batch operations.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ChannelAccount, ConversationAccount

from ohlala_smartops.bot.card_handler import CardHandler


class TestCardHandler:
    """Test suite for CardHandler class."""

    @pytest.fixture
    def mock_write_op_manager(self) -> Mock:
        """Create mock write operation manager."""
        manager = Mock()
        manager.confirm_operation = AsyncMock(return_value={"success": True})
        manager.cancel_operation = Mock(return_value=True)
        return manager

    @pytest.fixture
    def card_handler(self, mock_write_op_manager: Mock) -> CardHandler:
        """Create card handler instance with mocked dependencies."""
        return CardHandler(write_op_manager=mock_write_op_manager)

    @pytest.fixture
    def mock_turn_context(self) -> Mock:
        """Create mock turn context."""
        context = Mock(spec=TurnContext)
        context.activity = Activity(
            type="message",
            from_property=ChannelAccount(id="user123", name="Test User"),
            conversation=ConversationAccount(id="conv123"),
            value={},  # Will be set by individual tests
        )
        context.send_activity = AsyncMock()
        return context

    # Initialization tests

    def test_initialization_default(self) -> None:
        """Test card handler initialization with default dependencies."""
        handler = CardHandler()

        assert handler.write_op_manager is not None

    def test_initialization_with_dependencies(
        self,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test card handler initialization with provided dependencies."""
        handler = CardHandler(write_op_manager=mock_write_op_manager)

        assert handler.write_op_manager is mock_write_op_manager

    # Card action handling tests

    @pytest.mark.asyncio
    async def test_handle_card_action_no_data(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test handling card action with no data."""
        mock_turn_context.activity.value = None

        result = await card_handler.handle_card_action(mock_turn_context)

        # Should return error invoke response
        assert result is not None
        assert result["status"] == 500

    @pytest.mark.asyncio
    async def test_handle_card_action_unknown_action(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test handling unknown card action type."""
        mock_turn_context.activity.value = {"action": "unknown_action"}
        mock_turn_context.activity.type = "message"

        result = await card_handler.handle_card_action(mock_turn_context)

        # Should send warning message
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "not yet implemented" in call_args.text.lower()

        # Should return None for non-invoke
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_card_action_invoke_type(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test handling card action with invoke type."""
        mock_turn_context.activity.value = {"action": "cancel"}
        mock_turn_context.activity.type = "invoke"

        result = await card_handler.handle_card_action(mock_turn_context)

        # Should return invoke response
        assert result is not None
        assert result["status"] == 200
        assert "message" in result["body"]

    @pytest.mark.asyncio
    async def test_handle_card_action_error(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test error handling during card action processing."""
        mock_turn_context.activity.value = {
            "action": "ssm_command_approve",
            "approval_id": "test123",
        }
        mock_turn_context.activity.type = "invoke"  # Set to invoke to get response
        mock_write_op_manager.confirm_operation.side_effect = Exception("Test error")

        result = await card_handler.handle_card_action(mock_turn_context)

        # Should send error message to user
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "error" in call_args.text.lower()

        # Should return success invoke response (error was handled gracefully)
        assert result is not None
        assert result["status"] == 200

    # SSM command approve tests

    @pytest.mark.asyncio
    async def test_handle_ssm_command_approve_success(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test successful SSM command approval."""
        approval_id = "test-approval-123"
        mock_turn_context.activity.value = {
            "action": "ssm_command_approve",
            "approval_id": approval_id,
        }

        await card_handler.handle_card_action(mock_turn_context)

        # Should call confirm operation
        mock_write_op_manager.confirm_operation.assert_called_once_with(
            operation_id=approval_id,
            confirmed_by="user123",
        )

        # Should send confirmation message
        assert mock_turn_context.send_activity.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_ssm_command_approve_missing_id(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test SSM command approval with missing approval ID."""
        mock_turn_context.activity.value = {"action": "ssm_command_approve"}

        await card_handler.handle_card_action(mock_turn_context)

        # Should not call confirm operation
        mock_write_op_manager.confirm_operation.assert_not_called()

        # Should send error message
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "error" in call_args.text.lower()

    @pytest.mark.asyncio
    async def test_handle_ssm_command_approve_error(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test SSM command approval with operation error."""
        approval_id = "test-approval-123"
        mock_turn_context.activity.value = {
            "action": "ssm_command_approve",
            "approval_id": approval_id,
        }
        mock_write_op_manager.confirm_operation.side_effect = Exception("Approval failed")

        await card_handler.handle_card_action(mock_turn_context)

        # Should send error message
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "error" in call_args.text.lower()

    # SSM command deny tests

    @pytest.mark.asyncio
    async def test_handle_ssm_command_deny_success(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test successful SSM command denial."""
        approval_id = "test-approval-123"
        mock_turn_context.activity.value = {
            "action": "ssm_command_deny",
            "approval_id": approval_id,
        }

        await card_handler.handle_card_action(mock_turn_context)

        # Should call cancel operation
        mock_write_op_manager.cancel_operation.assert_called_once_with(
            operation_id=approval_id,
            cancelled_by="user123",
        )

        # Should send confirmation message
        assert mock_turn_context.send_activity.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_ssm_command_deny_missing_id(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test SSM command denial with missing approval ID."""
        mock_turn_context.activity.value = {"action": "ssm_command_deny"}

        await card_handler.handle_card_action(mock_turn_context)

        # Should not call cancel operation
        mock_write_op_manager.cancel_operation.assert_not_called()

        # Should send error message
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "error" in call_args.text.lower()

    # Batch approve tests

    @pytest.mark.asyncio
    async def test_handle_batch_ssm_approve_success(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test successful batch SSM command approval."""
        approval_ids = ["approval-1", "approval-2", "approval-3"]
        mock_turn_context.activity.value = {
            "action": "batch_ssm_approve",
            "approval_ids": approval_ids,
        }

        await card_handler.handle_card_action(mock_turn_context)

        # Should call confirm for each ID
        assert mock_write_op_manager.confirm_operation.call_count == 3

        # Should send confirmation
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "3 commands approved" in call_args.text.lower()

    @pytest.mark.asyncio
    async def test_handle_batch_ssm_approve_empty_list(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test batch SSM approval with empty approval list."""
        mock_turn_context.activity.value = {"action": "batch_ssm_approve", "approval_ids": []}

        await card_handler.handle_card_action(mock_turn_context)

        # Should not call confirm
        mock_write_op_manager.confirm_operation.assert_not_called()

        # Should send error
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "error" in call_args.text.lower()

    # Batch deny tests

    @pytest.mark.asyncio
    async def test_handle_batch_ssm_deny_success(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test successful batch SSM command denial."""
        approval_ids = ["approval-1", "approval-2"]
        mock_turn_context.activity.value = {
            "action": "batch_ssm_deny",
            "approval_ids": approval_ids,
        }

        await card_handler.handle_card_action(mock_turn_context)

        # Should call cancel for each ID
        assert mock_write_op_manager.cancel_operation.call_count == 2

        # Should send confirmation
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "2 commands denied" in call_args.text.lower()

    @pytest.mark.asyncio
    async def test_handle_batch_ssm_deny_empty_list(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
        mock_write_op_manager: Mock,
    ) -> None:
        """Test batch SSM denial with empty approval list."""
        mock_turn_context.activity.value = {"action": "batch_ssm_deny", "approval_ids": []}

        await card_handler.handle_card_action(mock_turn_context)

        # Should not call cancel
        mock_write_op_manager.cancel_operation.assert_not_called()

        # Should send error
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "error" in call_args.text.lower()

    # Review individual tests

    @pytest.mark.asyncio
    async def test_handle_review_individual(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test review individual commands action."""
        approval_ids = ["approval-1", "approval-2", "approval-3"]
        mock_turn_context.activity.value = {
            "action": "review_individual",
            "approval_ids": approval_ids,
        }

        await card_handler.handle_card_action(mock_turn_context)

        # Should send confirmation
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "reviewing" in call_args.text.lower()
        assert "3 commands" in call_args.text.lower()

    @pytest.mark.asyncio
    async def test_handle_review_individual_empty(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test review individual with no approval IDs."""
        mock_turn_context.activity.value = {"action": "review_individual", "approval_ids": []}

        await card_handler.handle_card_action(mock_turn_context)

        # Should send error
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "no commands" in call_args.text.lower()

    # Cancel action tests

    @pytest.mark.asyncio
    async def test_handle_cancel(
        self,
        card_handler: CardHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test cancel action."""
        mock_turn_context.activity.value = {"action": "cancel"}

        await card_handler.handle_card_action(mock_turn_context)

        # Should send cancellation message
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "cancelled" in call_args.text.lower()

    # Invoke response tests

    @pytest.mark.asyncio
    async def test_create_invoke_response_success(
        self,
        card_handler: CardHandler,
    ) -> None:
        """Test creating successful invoke response."""
        response = await card_handler._create_invoke_response(success=True)

        assert response["status"] == 200
        assert "message" in response["body"]
        assert "success" in response["body"]["message"].lower()

    @pytest.mark.asyncio
    async def test_create_invoke_response_failure(
        self,
        card_handler: CardHandler,
    ) -> None:
        """Test creating failure invoke response."""
        response = await card_handler._create_invoke_response(success=False)

        assert response["status"] == 500
        assert "message" in response["body"]
        assert "failed" in response["body"]["message"].lower()
