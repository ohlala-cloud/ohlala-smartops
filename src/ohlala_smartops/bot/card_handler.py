"""Adaptive card action handling for Microsoft Teams bot.

This module handles user interactions with adaptive cards, including approval
workflows, command execution confirmations, and interactive UI elements.

Phase 4A: Core approval workflow actions. Additional action types will be added
in Phase 4B when the command system is fully migrated.
"""

import logging
from typing import Any

from botbuilder.core import MessageFactory, TurnContext

from ohlala_smartops.workflow.write_operations import WriteOperationManager

logger = logging.getLogger(__name__)


class CardHandler:
    """Handles adaptive card action submissions from Microsoft Teams.

    This handler processes user interactions with adaptive cards, primarily
    focusing on approval workflows for write operations and command execution.

    Attributes:
        write_op_manager: Manager for handling write operation approvals.

    Example:
        >>> handler = CardHandler(write_op_manager=write_op_manager)
        >>> await handler.handle_card_action(turn_context)

    Note:
        Phase 4A implementation focuses on core approval workflows.
        Additional action types will be added in subsequent phases.
    """

    def __init__(
        self,
        write_op_manager: WriteOperationManager | None = None,
    ) -> None:
        """Initialize card handler.

        Args:
            write_op_manager: Write operation manager for approvals. Creates default if None.
        """
        self.write_op_manager = write_op_manager or WriteOperationManager()
        logger.info("CardHandler initialized")

    async def handle_card_action(self, turn_context: TurnContext) -> dict[str, Any] | None:
        """Handle adaptive card action submissions.

        This method routes card actions to appropriate handlers based on
        the action type specified in the card data.

        Args:
            turn_context: Bot Framework turn context.

        Returns:
            Invoke response dict for Teams, or None for regular messages.

        Raises:
            Exception: Re-raises exceptions after logging.
        """
        try:
            # Get action data from card submission
            action_data = turn_context.activity.value
            if not action_data:
                logger.warning("Received card action with no data")
                return await self._create_invoke_response(success=False)

            action_type = action_data.get("action")
            logger.info(f"Processing card action: {action_type}")

            # Check if this is an invoke activity (requires response)
            is_invoke = turn_context.activity.type == "invoke"

            # Route to appropriate handler
            if action_type == "ssm_command_approve":
                await self._handle_ssm_command_approve(turn_context, action_data)
            elif action_type == "ssm_command_deny":
                await self._handle_ssm_command_deny(turn_context, action_data)
            elif action_type == "batch_ssm_approve":
                await self._handle_batch_ssm_approve(turn_context, action_data)
            elif action_type == "batch_ssm_deny":
                await self._handle_batch_ssm_deny(turn_context, action_data)
            elif action_type == "review_individual":
                await self._handle_review_individual(turn_context, action_data)
            elif action_type == "cancel":
                await self._handle_cancel(turn_context)
            else:
                # Unknown action type - log and inform user
                logger.warning(f"Unknown card action type: {action_type}")
                await turn_context.send_activity(
                    MessageFactory.text(
                        f"⚠️ Action '{action_type}' is not yet implemented. "
                        "This feature will be available in a future update."
                    )
                )

            # Send invoke response if needed
            if is_invoke:
                return await self._create_invoke_response(success=True)

            return None

        except Exception as e:
            logger.error(f"Error handling card action: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(f"❌ Error processing action: {e!s}")
            )
            return await self._create_invoke_response(success=False)

    async def _handle_ssm_command_approve(
        self,
        turn_context: TurnContext,
        action_data: dict[str, Any],
    ) -> None:
        """Handle SSM command approval action.

        Approves a single SSM command for execution after user confirmation.

        Args:
            turn_context: Bot Framework turn context.
            action_data: Action data from the card submission.
        """
        approval_id = action_data.get("approval_id")
        if not approval_id:
            logger.error("Missing approval_id in SSM approval action")
            await turn_context.send_activity(
                MessageFactory.text("❌ Error: Missing approval information. Please try again.")
            )
            return

        # Get user information for audit trail
        user_name = getattr(turn_context.activity.from_property, "name", "Unknown")
        user_id = turn_context.activity.from_property.id

        logger.info(f"User {user_name} ({user_id}) approving command: {approval_id}")

        try:
            # Process approval through write operation manager
            result = await self.write_op_manager.confirm_operation(
                operation_id=approval_id,
                confirmed_by=user_id,
            )

            if result.get("success"):
                # Send approval confirmation
                await turn_context.send_activity(
                    MessageFactory.text(
                        f"✅ **Command Approved by {user_name}**\n\n"
                        "The command has been approved and is now executing..."
                    )
                )
                logger.info(f"Command {approval_id} approved successfully")
            else:
                error_msg = result.get("error", "Unknown error")
                await turn_context.send_activity(MessageFactory.text(f"❌ {error_msg}"))
                logger.error(f"Failed to approve command {approval_id}: {error_msg}")

        except Exception as e:
            logger.error(f"Error approving command {approval_id}: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(f"❌ Error approving command: {e!s}")
            )

    async def _handle_ssm_command_deny(
        self,
        turn_context: TurnContext,
        action_data: dict[str, Any],
    ) -> None:
        """Handle SSM command denial action.

        Denies a single SSM command and cancels execution.

        Args:
            turn_context: Bot Framework turn context.
            action_data: Action data from the card submission.
        """
        approval_id = action_data.get("approval_id")
        if not approval_id:
            logger.error("Missing approval_id in SSM denial action")
            await turn_context.send_activity(
                MessageFactory.text("❌ Error: Missing approval information. Please try again.")
            )
            return

        # Get user information for audit trail
        user_name = getattr(turn_context.activity.from_property, "name", "Unknown")
        user_id = turn_context.activity.from_property.id

        logger.info(f"User {user_name} ({user_id}) denying command: {approval_id}")

        try:
            # Process denial through write operation manager
            success = self.write_op_manager.cancel_operation(
                operation_id=approval_id,
                cancelled_by=user_id,
            )

            if success:
                # Send denial confirmation
                await turn_context.send_activity(
                    MessageFactory.text(
                        f"❌ **Command Denied by {user_name}**\n\n"
                        "The operation has been cancelled. What would you like me to help you with?"
                    )
                )
                logger.info(f"Command {approval_id} denied successfully")
            else:
                await turn_context.send_activity(
                    MessageFactory.text(
                        "❌ Could not cancel operation. "
                        "It may have expired or already been processed."
                    )
                )
                logger.error(f"Failed to deny command {approval_id}")

        except Exception as e:
            logger.error(f"Error denying command {approval_id}: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(f"❌ Error denying command: {e!s}")
            )

    async def _handle_batch_ssm_approve(
        self,
        turn_context: TurnContext,
        action_data: dict[str, Any],
    ) -> None:
        """Handle batch SSM command approval.

        Approves multiple SSM commands at once for execution.

        Args:
            turn_context: Bot Framework turn context.
            action_data: Action data from the card submission.
        """
        approval_ids = action_data.get("approval_ids", [])
        if not approval_ids:
            logger.error("Missing approval_ids in batch approval action")
            await turn_context.send_activity(
                MessageFactory.text("❌ Error: Missing approval information. Please try again.")
            )
            return

        # Get user information
        user_name = getattr(turn_context.activity.from_property, "name", "Unknown")
        user_id = turn_context.activity.from_property.id

        logger.info(f"User {user_name} ({user_id}) batch approving {len(approval_ids)} commands")

        try:
            # Approve all commands
            success_count = 0
            for approval_id in approval_ids:
                result = await self.write_op_manager.confirm_operation(
                    operation_id=approval_id,
                    confirmed_by=user_id,
                )
                if result.get("success"):
                    success_count += 1

            if success_count == len(approval_ids):
                await turn_context.send_activity(
                    MessageFactory.text(
                        f"✅ All {len(approval_ids)} commands approved. Executing..."
                    )
                )
                logger.info(f"Batch approved {len(approval_ids)} commands successfully")
            else:
                await turn_context.send_activity(
                    MessageFactory.text(
                        f"⚠️ {success_count}/{len(approval_ids)} commands approved. "
                        "Some operations may have expired or already been processed."
                    )
                )
                logger.warning(
                    f"Batch approval partial success: {success_count}/{len(approval_ids)}"
                )

        except Exception as e:
            logger.error(f"Error batch approving commands: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(f"❌ Error approving commands: {e!s}")
            )

    async def _handle_batch_ssm_deny(
        self,
        turn_context: TurnContext,
        action_data: dict[str, Any],
    ) -> None:
        """Handle batch SSM command denial.

        Denies multiple SSM commands and cancels their execution.

        Args:
            turn_context: Bot Framework turn context.
            action_data: Action data from the card submission.
        """
        approval_ids = action_data.get("approval_ids", [])
        if not approval_ids:
            logger.error("Missing approval_ids in batch denial action")
            await turn_context.send_activity(
                MessageFactory.text("❌ Error: Missing approval information. Please try again.")
            )
            return

        # Get user information
        user_name = getattr(turn_context.activity.from_property, "name", "Unknown")
        user_id = turn_context.activity.from_property.id

        logger.info(f"User {user_name} ({user_id}) batch denying {len(approval_ids)} commands")

        try:
            # Deny all commands
            success_count = 0
            for approval_id in approval_ids:
                success = self.write_op_manager.cancel_operation(
                    operation_id=approval_id,
                    cancelled_by=user_id,
                )
                if success:
                    success_count += 1

            if success_count == len(approval_ids):
                await turn_context.send_activity(
                    MessageFactory.text(
                        f"❌ **All {len(approval_ids)} commands denied - Execution cancelled**\n\n"
                        "All pending operations have been cancelled. "
                        "What would you like me to help you with?"
                    )
                )
                logger.info(f"Batch denied {len(approval_ids)} commands successfully")
            else:
                await turn_context.send_activity(
                    MessageFactory.text(
                        f"⚠️ {success_count}/{len(approval_ids)} commands denied. "
                        "Some operations may have expired or already been processed."
                    )
                )
                logger.warning(f"Batch denial partial success: {success_count}/{len(approval_ids)}")

        except Exception as e:
            logger.error(f"Error batch denying commands: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(f"❌ Error denying commands: {e!s}")
            )

    async def _handle_review_individual(
        self,
        turn_context: TurnContext,
        action_data: dict[str, Any],
    ) -> None:
        """Handle request to review individual commands.

        When user chooses to review commands individually instead of
        batch approval/denial.

        Args:
            turn_context: Bot Framework turn context.
            action_data: Action data from the card submission.
        """
        approval_ids = action_data.get("approval_ids", [])

        if not approval_ids:
            await turn_context.send_activity(
                MessageFactory.text("❌ No commands found for individual review.")
            )
            return

        await turn_context.send_activity(
            MessageFactory.text(
                f"📋 **Reviewing {len(approval_ids)} commands individually**\n\n"
                "I'll send approval cards for each command separately. "
                "This feature will be fully implemented in Phase 4B."
            )
        )

        logger.info(f"Individual review requested for {len(approval_ids)} commands")

    async def _handle_cancel(self, turn_context: TurnContext) -> None:
        """Handle cancel action.

        Cancels the current operation or dismisses the card.

        Args:
            turn_context: Bot Framework turn context.
        """
        await turn_context.send_activity(
            MessageFactory.text("Operation cancelled. How can I help you?")
        )

        logger.info("User cancelled operation")

    async def _create_invoke_response(self, success: bool = True) -> dict[str, Any]:
        """Create an invoke response for Teams.

        Teams invoke activities require an invoke response to prevent
        the "Sorry, there was a problem" error message.

        Args:
            success: Whether the action was successful.

        Returns:
            Invoke response dictionary.
        """
        return {
            "status": 200 if success else 500,
            "body": {"message": "Action processed successfully" if success else "Action failed"},
        }
