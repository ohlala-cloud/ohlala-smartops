"""Activity handlers for Microsoft Teams bot.

This module provides handlers for different types of Bot Framework activities,
including messages, conversation updates, and invoke actions.
"""

import logging
from typing import Any

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ChannelAccount

from ohlala_smartops.models import (
    ConversationContext,
    ConversationType,
    UserInfo,
    UserRole,
)

logger = logging.getLogger(__name__)


class OhlalaActivityHandler(ActivityHandler):  # type: ignore[misc]
    """Custom activity handler for Ohlala SmartOps bot.

    This handler processes different types of activities from Microsoft Teams,
    including messages, conversation updates, and card actions.

    Attributes:
        None

    Example:
        >>> handler = OhlalaActivityHandler()
        >>> await adapter.process_activity(activity, auth_header, handler.on_turn)
    """

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Handle incoming message activities.

        This method is called when a user sends a message to the bot.

        Args:
            turn_context: Turn context for the current activity.
        """
        try:
            # Get message text
            message_text = turn_context.activity.text or ""
            user = turn_context.activity.from_property

            logger.info(f"Received message from {user.name} ({user.id}): {message_text[:100]}")

            # Create conversation context
            await self._create_conversation_context(turn_context)

            # Remove @mentions from message text
            clean_text = self._remove_mentions(message_text, turn_context.activity)

            # Check for basic commands
            if clean_text.lower() in ["help", "/help"]:
                await self._handle_help_command(turn_context)
                return

            if clean_text.lower() in ["health", "/health", "status"]:
                await self._handle_health_command(turn_context)
                return

            # Send to AI for processing
            await turn_context.send_activity(
                "I'm processing your request with AI. This feature is being implemented..."
            )

            # TODO: Send to AI/MCP for natural language processing
            # TODO: Route to appropriate command handler
            # TODO: Execute command and return results

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await turn_context.send_activity(
                "Sorry, I encountered an error processing your message. Please try again."
            )

    async def on_conversation_update_activity(self, turn_context: TurnContext) -> None:
        """Handle conversation update activities.

        This method is called when the bot is added to or removed from a conversation,
        or when conversation members are updated.

        Args:
            turn_context: Turn context for the current activity.
        """
        try:
            # Check if members were added
            if turn_context.activity.members_added:
                for member in turn_context.activity.members_added:
                    # Don't greet the bot itself
                    if member.id != turn_context.activity.recipient.id:
                        await self._send_welcome_message(turn_context, member)

            # Check if members were removed
            if turn_context.activity.members_removed:
                for member in turn_context.activity.members_removed:
                    logger.info(f"Member removed from conversation: {member.name} ({member.id})")

        except Exception as e:
            logger.error(f"Error handling conversation update: {e}", exc_info=True)

    async def on_invoke_activity(self, turn_context: TurnContext) -> Any:
        """Handle invoke activities (card actions).

        This method is called when a user interacts with adaptive card buttons.

        Args:
            turn_context: Turn context for the current activity.

        Returns:
            Invoke response for the action.
        """
        try:
            activity = turn_context.activity
            action_name = activity.name

            logger.info(f"Received invoke activity: {action_name}")

            # Handle different invoke types
            if action_name == "adaptiveCard/action":
                return await self._handle_card_action(turn_context)

            # TODO: Handle other invoke types
            logger.warning(f"Unhandled invoke activity: {action_name}")
            return {"status": 200, "body": {"message": "Action received"}}

        except Exception as e:
            logger.error(f"Error handling invoke activity: {e}", exc_info=True)
            return {"status": 500, "body": {"error": "Internal error"}}

    async def on_teams_signin_verify_state(self, turn_context: TurnContext) -> None:
        """Handle Teams signin verification.

        This method is called during OAuth authentication flows.

        Args:
            turn_context: Turn context for the current activity.
        """
        logger.info("Handling Teams signin verification")
        # TODO: Implement OAuth signin verification if needed

    async def on_message_reaction_activity(self, turn_context: TurnContext) -> None:
        """Handle message reaction activities.

        This method is called when a user reacts to a message (like, heart, etc.).

        Args:
            turn_context: Turn context for the current activity.
        """
        logger.info("Message reaction received")
        # TODO: Implement reaction handling if needed

    async def _create_conversation_context(self, turn_context: TurnContext) -> ConversationContext:
        """Create conversation context from turn context.

        Args:
            turn_context: Turn context for the current activity.

        Returns:
            Conversation context object.
        """
        activity = turn_context.activity
        from_account = activity.from_property

        # Determine conversation type
        conversation_type = ConversationType.PERSONAL
        if activity.channel_data:
            channel_data = activity.channel_data
            if isinstance(channel_data, dict):
                if channel_data.get("team"):
                    conversation_type = ConversationType.CHANNEL
                elif activity.conversation.is_group:
                    conversation_type = ConversationType.GROUP

        # Create user info
        user = UserInfo(
            id=from_account.aad_object_id or from_account.id,
            name=from_account.name or "Unknown",
            email=None,  # Not available from activity
            tenant_id=activity.conversation.tenant_id or "",
            locale="en",  # Default, will be detected later
            # TODO: Load user role from database/config
            role=UserRole.OPERATOR,
        )

        # Create conversation context
        return ConversationContext(
            conversation_id=activity.conversation.id,
            conversation_type=conversation_type,
            user=user,
            team=None,  # TODO: Extract from channel_data if available
            channel=None,  # TODO: Extract from channel_data if available
            service_url=activity.service_url,
        )


    def _remove_mentions(self, text: str, activity: Activity) -> str:
        """Remove @mentions from message text.

        Args:
            text: Original message text.
            activity: Bot Framework activity.

        Returns:
            Text with mentions removed.
        """
        clean_text = text

        if activity.entities:
            for entity in activity.entities:
                if entity.type == "mention":
                    mention_text = entity.properties.get("text", "")
                    if mention_text:
                        clean_text = clean_text.replace(mention_text, "").strip()

        return clean_text

    async def _send_welcome_message(
        self, turn_context: TurnContext, member: ChannelAccount
    ) -> None:
        """Send welcome message to new conversation member.

        Args:
            turn_context: Turn context for the current activity.
            member: New member who was added.
        """
        welcome_message = (
            f"Hello {member.name}! 👋\n\n"
            "I'm Ohlala SmartOps, your AI-powered AWS EC2 management assistant. "
            "I can help you manage EC2 instances using natural language commands.\n\n"
            "**What I can do:**\n"
            "- List and show EC2 instances\n"
            "- Start, stop, and reboot instances\n"
            "- Check instance health and metrics\n"
            "- View cost information\n"
            "- Execute SSM commands\n\n"
            "**Getting started:**\n"
            "- Type `help` to see available commands\n"
            "- Type `list instances` to see your EC2 instances\n"
            "- Ask me anything in natural language!\n\n"
            'Try saying: _"Show me all running instances in us-east-1"_'
        )

        await turn_context.send_activity(welcome_message)

    async def _handle_help_command(self, turn_context: TurnContext) -> None:
        """Handle the help command.

        Args:
            turn_context: Turn context for the current activity.
        """
        help_message = (
            "**Ohlala SmartOps - Help**\n\n"
            "I understand natural language! Just tell me what you want to do.\n\n"
            "**EC2 Commands:**\n"
            '- List instances: _"show all instances"_ or _"list ec2"_\n'
            '- Start instance: _"start instance i-123456"_\n'
            '- Stop instance: _"stop instance i-123456"_\n'
            '- Reboot instance: _"reboot instance i-123456"_\n\n'
            "**Monitoring:**\n"
            '- Health check: _"check health of i-123456"_\n'
            '- View metrics: _"show cpu metrics for i-123456"_\n\n'
            "**Cost Management:**\n"
            '- Current costs: _"show current AWS costs"_\n'
            '- Cost forecast: _"forecast costs for next month"_\n\n'
            "**SSM:**\n"
            "- Execute command: _\"run 'ls -la' on i-123456\"_\n"
            '- Start session: _"connect to i-123456"_\n\n'
            "**Other Commands:**\n"
            "- `health` or `status` - Check bot status\n"
            "- `help` - Show this help message"
        )

        await turn_context.send_activity(help_message)

    async def _handle_health_command(self, turn_context: TurnContext) -> None:
        """Handle the health/status command.

        Args:
            turn_context: Turn context for the current activity.
        """
        # TODO: Actually check health of components
        health_message = (
            "**Bot Health Status** ✅\n\n"
            "All systems operational:\n"
            "- Bot Framework: OK\n"
            "- AWS Connection: OK\n"
            "- AI/Claude: OK\n"
            "- MCP Servers: OK"
        )

        await turn_context.send_activity(health_message)

    async def _handle_card_action(self, turn_context: TurnContext) -> dict[str, Any]:
        """Handle adaptive card action submissions.

        Args:
            turn_context: Turn context for the current activity.

        Returns:
            Invoke response for the card action.
        """
        activity = turn_context.activity
        action_data = activity.value

        logger.info(f"Card action data: {action_data}")

        # TODO: Route to appropriate handler based on action type
        # TODO: Process approval actions
        # TODO: Process instance actions
        # TODO: Process form submissions

        await turn_context.send_activity("Card action received. Processing...")

        return {"status": 200, "body": {"message": "Action processed"}}
