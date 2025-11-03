"""Main bot orchestrator for Microsoft Teams integration.

This module provides the OhlalaBot class, which coordinates all bot handlers
and manages the bot lifecycle for Microsoft Teams interactions.

Phase 4B: Core bot orchestration with handler integration. Additional features
(task modules, advanced dialogs) will be added in future phases as needed.
"""

import logging
from typing import Any, Final, cast

from botbuilder.core import CardFactory, MessageFactory, TurnContext
from botbuilder.core.teams import TeamsActivityHandler
from botbuilder.schema import Attachment

from ohlala_smartops.ai.bedrock_client import BedrockClient
from ohlala_smartops.bot.card_handler import CardHandler
from ohlala_smartops.bot.message_handler import MessageHandler
from ohlala_smartops.bot.state import ConversationStateManager, InMemoryStateStorage
from ohlala_smartops.bot.typing_handler import TypingHandler
from ohlala_smartops.commands.registry import register_commands
from ohlala_smartops.mcp.manager import MCPManager
from ohlala_smartops.workflow.command_tracker import AsyncCommandTracker
from ohlala_smartops.workflow.write_operations import WriteOperationManager

logger: Final = logging.getLogger(__name__)


class OhlalaBot(TeamsActivityHandler):  # type: ignore[misc]
    """Main bot orchestrator for Ohlala SmartOps Teams integration.

    This class coordinates all bot handlers and manages the bot lifecycle,
    delegating to specialized handlers for different activity types.

    Attributes:
        message_handler: Handles incoming message activities.
        card_handler: Handles adaptive card action submissions.
        typing_handler: Manages typing indicators.
        bedrock_client: Client for AI interactions.
        mcp_manager: Manager for MCP tool orchestration.
        state_manager: Manager for conversation state persistence.
        write_op_manager: Manager for write operation approvals.
        command_tracker: Tracker for async SSM commands.

    Example:
        >>> bot = OhlalaBot(
        ...     bedrock_client=bedrock_client,
        ...     mcp_manager=mcp_manager,
        ... )
        >>> # Bot is ready to handle Teams activities

    Note:
        Phase 4B focuses on core orchestration. Task modules and advanced
        dialog features will be added in future phases as needed.
    """

    def __init__(
        self,
        bedrock_client: BedrockClient | None = None,
        mcp_manager: MCPManager | None = None,
        state_manager: ConversationStateManager | None = None,
        write_op_manager: WriteOperationManager | None = None,
        command_tracker: AsyncCommandTracker | None = None,
    ) -> None:
        """Initialize the Ohlala SmartOps bot.

        Args:
            bedrock_client: Bedrock client for AI interactions. Creates default if None.
            mcp_manager: MCP manager for tool calls. Creates default if None.
            state_manager: State manager for conversation context. Creates default if None.
            write_op_manager: Write operation manager for approvals. Creates default if None.
            command_tracker: Tracker for async commands. Optional, can be None.
        """
        super().__init__()

        # Initialize or use provided services
        self.mcp_manager = mcp_manager or MCPManager()
        self.bedrock_client = bedrock_client or BedrockClient(mcp_manager=self.mcp_manager)
        self.state_manager = state_manager or ConversationStateManager(
            storage=InMemoryStateStorage()
        )
        self.write_op_manager = write_op_manager or WriteOperationManager()
        self.command_tracker = command_tracker

        # Initialize handlers with dependencies
        self.message_handler = MessageHandler(
            bedrock_client=self.bedrock_client,
            mcp_manager=self.mcp_manager,
            state_manager=self.state_manager,
            command_tracker=self.command_tracker,
        )
        self.card_handler = CardHandler(write_op_manager=self.write_op_manager)
        self.typing_handler = TypingHandler()

        # Register all commands with the message handler (Phase 6)
        register_commands(self.message_handler)

        logger.info("OhlalaBot initialized with all handlers and commands registered")

    # Core Teams activity handlers

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Handle incoming message activities.

        Delegates to MessageHandler for processing user messages.

        Args:
            turn_context: Bot Framework turn context.

        Example:
            >>> await bot.on_message_activity(turn_context)
        """
        try:
            await self.message_handler.on_message_activity(turn_context)
        except Exception as e:
            logger.error(f"Error handling message activity: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(
                    "Sorry, I encountered an error processing your message. " "Please try again."
                )
            )

    async def on_invoke_activity(self, turn_context: TurnContext) -> dict[str, Any]:
        """Handle invoke activities.

        Delegates to CardHandler for card actions, or parent class for other invokes.

        Args:
            turn_context: Bot Framework turn context.

        Returns:
            Invoke response dict for Teams.

        Example:
            >>> response = await bot.on_invoke_activity(turn_context)
        """
        try:
            # Check if it's a card action (has value data)
            if turn_context.activity.value:
                result = await self.card_handler.handle_card_action(turn_context)
                if result:
                    return result

            # Let parent class handle other Teams-specific invokes
            return cast(dict[str, Any], await super().on_invoke_activity(turn_context))

        except Exception as e:
            logger.error(f"Error in on_invoke_activity: {e}", exc_info=True)
            return await self._create_invoke_response(success=False)

    async def on_conversation_update_activity(self, turn_context: TurnContext) -> None:
        """Handle conversation update activities.

        Called when bot is added/removed or when members join/leave.

        Args:
            turn_context: Bot Framework turn context.

        Example:
            >>> await bot.on_conversation_update_activity(turn_context)
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
                    # Log member removal
                    logger.info(
                        f"Member removed: {member.name} ({member.id}) "
                        f"from conversation {turn_context.activity.conversation.id}"
                    )

        except Exception as e:
            logger.error(f"Error handling conversation update: {e}", exc_info=True)

    # Helper methods for handlers

    async def send_response(
        self,
        turn_context: TurnContext,
        response: str | dict[str, Any],
    ) -> None:
        """Send response, handling both text and adaptive cards.

        Args:
            turn_context: Bot Framework turn context.
            response: Response to send (text string or dict with card).

        Example:
            >>> await bot.send_response(turn_context, "Hello!")
            >>> await bot.send_response(turn_context, {"adaptive_card": True, "card": {...}})
        """
        try:
            if isinstance(response, dict):
                # Check for adaptive card
                if response.get("adaptive_card") and response.get("card"):
                    card = response["card"]
                    attachment = self._create_adaptive_card_attachment(card)
                    await turn_context.send_activity(MessageFactory.attachment(attachment))
                elif response.get("text_message"):
                    await turn_context.send_activity(MessageFactory.text(response["text_message"]))
                else:
                    # Unknown format
                    logger.warning(f"Unknown response format: {response}")
                    await turn_context.send_activity(MessageFactory.text(str(response)))

            elif isinstance(response, str):
                # Simple text response
                await turn_context.send_activity(MessageFactory.text(response))

            else:
                # Unknown type
                logger.warning(f"Unknown response type: {type(response)}")
                await turn_context.send_activity(MessageFactory.text(str(response)))

        except Exception as e:
            logger.error(f"Error sending response: {e}", exc_info=True)
            await turn_context.send_activity(MessageFactory.text("Error sending response."))

    # Private helper methods

    async def _send_welcome_message(
        self,
        turn_context: TurnContext,
        member: Any,
    ) -> None:
        """Send welcome message to new conversation member.

        Args:
            turn_context: Bot Framework turn context.
            member: New member who joined.
        """
        welcome_text = (
            f"Welcome to Ohlala SmartOps, {member.name}! 👋\n\n"
            "I'm your AI-powered AWS operations assistant. I can help you:\n\n"
            "• Monitor and manage EC2 instances\n"
            "• Check instance health and metrics\n"
            "• Execute commands via SSM\n"
            "• Provide optimization recommendations\n\n"
            "Just ask me in natural language, or type `/help` for commands!"
        )

        await turn_context.send_activity(MessageFactory.text(welcome_text))
        logger.info(f"Sent welcome message to {member.name} ({member.id})")

    def _create_adaptive_card_attachment(self, card_content: dict[str, Any]) -> Attachment:
        """Create an Adaptive Card attachment.

        Args:
            card_content: Adaptive card JSON content.

        Returns:
            Attachment object for the card.

        Example:
            >>> attachment = bot._create_adaptive_card_attachment(card_dict)
        """
        try:
            # Apply brand colors to the card
            self._apply_brand_colors(card_content)

            # Validate card structure
            if not isinstance(card_content, dict):
                logger.error(f"Card content is not a dict: {type(card_content)}")
                raise ValueError("Card content must be a dictionary")

            if "type" not in card_content:
                logger.error("Card missing 'type' field")
                card_content["type"] = "AdaptiveCard"

            if "version" not in card_content:
                logger.error("Card missing 'version' field")
                card_content["version"] = "1.5"

            return CardFactory.adaptive_card(card_content)

        except Exception as e:
            logger.error(f"Error creating adaptive card attachment: {e}", exc_info=True)
            # Return a simple error card
            error_card = {
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": [
                    {
                        "type": "TextBlock",
                        "text": f"Error creating card: {e!s}",
                        "color": "Attention",
                        "wrap": True,
                    }
                ],
            }
            return CardFactory.adaptive_card(error_card)

    def _apply_brand_colors(self, card: dict[str, Any]) -> None:
        """Apply brand colors to an adaptive card.

        Recursively updates colors in card elements where supported.

        Args:
            card: Adaptive card JSON to modify in-place.
        """

        def update_colors(obj: Any) -> None:
            """Recursively update colors in card structure."""
            if isinstance(obj, dict):
                # Special handling for Chart elements
                if (
                    obj.get("type") in ["Chart.Line", "Chart.Pie", "Chart.Donut", "Chart.Bar"]
                    and "data" in obj
                    and isinstance(obj["data"], list)
                ):
                    # Update chart data colors
                    colors = [
                        "#FF9900",  # AWS Orange
                        "#232F3E",  # AWS Dark Blue
                        "#146EB4",  # AWS Blue
                        "#FF6600",  # AWS Red-Orange
                        "#00A1C9",  # AWS Light Blue
                    ]
                    for i, data_item in enumerate(obj["data"]):
                        if isinstance(data_item, dict) and "color" not in data_item:
                            data_item["color"] = colors[i % len(colors)]

                # Recurse through all values
                for value in obj.values():
                    update_colors(value)

            elif isinstance(obj, list):
                for item in obj:
                    update_colors(item)

        update_colors(card)

    async def _create_invoke_response(
        self,
        success: bool = True,
    ) -> dict[str, Any]:
        """Create an invoke response for Teams.

        Args:
            success: Whether the invoke was successful.

        Returns:
            Invoke response dictionary.

        Example:
            >>> response = await bot._create_invoke_response(success=True)
        """
        return {
            "status": 200 if success else 500,
            "body": {"message": "Action processed successfully" if success else "Action failed"},
        }
