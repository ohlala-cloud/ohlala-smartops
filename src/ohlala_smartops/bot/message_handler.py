"""Message handling for Microsoft Teams bot interactions.

This module provides message processing, command routing, and natural language
understanding capabilities for the Ohlala SmartOps bot.
"""

import logging
import re
from typing import Any, Protocol

from botbuilder.core import MessageFactory, TurnContext
from botbuilder.schema import Activity

from ohlala_smartops.ai.bedrock_client import BedrockClient
from ohlala_smartops.bot.state import ConversationStateManager
from ohlala_smartops.mcp.manager import MCPManager
from ohlala_smartops.workflow.command_tracker import AsyncCommandTracker

logger = logging.getLogger(__name__)


class CommandHandler(Protocol):
    """Protocol for command handlers.

    Command handlers process specific slash commands and return responses.
    """

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the command.

        Args:
            args: Command arguments.
            context: Execution context with turn_context, bot services, etc.

        Returns:
            Command result with success, message, and optional card.
        """
        ...


class MessageHandler:
    """Handles incoming message activities from Microsoft Teams.

    This handler processes user messages, routes commands, integrates with
    Bedrock AI for natural language understanding, and tracks command execution.

    Attributes:
        bedrock_client: Client for Claude AI interactions.
        mcp_manager: Manager for MCP tool orchestration.
        state_manager: Manager for conversation state.
        command_tracker: Manager for tracking async SSM commands.

    Example:
        >>> handler = MessageHandler(
        ...     bedrock_client=bedrock_client,
        ...     mcp_manager=mcp_manager,
        ... )
        >>> await handler.on_message_activity(turn_context)
    """

    def __init__(
        self,
        bedrock_client: BedrockClient | None = None,
        mcp_manager: MCPManager | None = None,
        state_manager: ConversationStateManager | None = None,
        command_tracker: AsyncCommandTracker | None = None,
    ) -> None:
        """Initialize message handler.

        Args:
            bedrock_client: Bedrock client for AI interactions. Creates default if None.
            mcp_manager: MCP manager for tool calls. Creates default if None.
            state_manager: State manager for conversation context. Uses memory if None.
            command_tracker: Tracker for async commands. Optional, can be None.
        """
        # Initialize or use provided services
        self.bedrock_client = bedrock_client or BedrockClient(mcp_manager=mcp_manager)
        self.mcp_manager = mcp_manager
        self.state_manager = state_manager
        self.command_tracker = command_tracker  # Optional - may be None

        # Command registry (will be populated when commands are migrated in Phase 4B)
        self._command_registry: dict[str, type[CommandHandler]] = {}

        logger.info("MessageHandler initialized")

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Handle incoming message activities.

        This method processes user messages by:
        1. Removing @mentions
        2. Checking for slash commands
        3. Checking for command ID status requests
        4. Routing to Bedrock AI for natural language processing

        Args:
            turn_context: Bot Framework turn context.

        Raises:
            Exception: Re-raises exceptions after logging and sending error message.
        """
        try:
            # Get message text and user info
            text = turn_context.activity.text or ""
            user_id = turn_context.activity.from_property.id
            user_name = turn_context.activity.from_property.name or "User"

            logger.info(f"Received message from {user_name} ({user_id}): {text[:100]}")

            # Remove bot mentions
            clean_text = self._remove_mentions(turn_context.activity)

            # Store user message in conversation state
            if self.state_manager and clean_text:
                await self._store_user_message(
                    conversation_id=turn_context.activity.conversation.id,
                    user_id=user_id,
                    message=clean_text,
                )

            # Check if this is a slash command
            if clean_text.startswith("/"):
                handled = await self._handle_command(turn_context, clean_text)
                if handled:
                    return

            # Check if user is asking about a command ID
            if await self._check_for_command_id_request(turn_context, clean_text, user_id):
                return

            # Route to Bedrock AI for natural language processing
            if clean_text:
                await self._handle_natural_language(turn_context, clean_text, user_id)

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(
                    "Sorry, I encountered an error processing your message. "
                    "Please try again or contact support if the issue persists."
                )
            )

    async def _handle_command(self, turn_context: TurnContext, text: str) -> bool:
        """Handle slash commands.

        Args:
            turn_context: Bot Framework turn context.
            text: Message text starting with '/'.

        Returns:
            True if command was handled, False otherwise.
        """
        # Parse command and arguments
        parts = text.strip().split()
        if not parts:
            return False

        command_name = parts[0][1:].lower()  # Remove '/' prefix
        args = parts[1:] if len(parts) > 1 else []

        logger.info(f"Processing slash command: /{command_name}")

        # Check command registry (will be populated in Phase 4B)
        command_class = self._command_registry.get(command_name)
        if not command_class:
            logger.info(
                f"Command '/{command_name}' not found in registry. "
                f"Available: {list(self._command_registry.keys())}"
            )
            return False

        try:
            # Create command instance and execute
            command_instance = command_class()
            result = await command_instance.execute(
                args=args,
                context={
                    "turn_context": turn_context,
                    "mcp_manager": self.mcp_manager,
                    "state_manager": self.state_manager,
                },
            )

            # Send response based on result
            if result.get("success"):
                if result.get("adaptive_card"):
                    # Send adaptive card (will be implemented with card handler)
                    await turn_context.send_activity(
                        MessageFactory.text("Command executed successfully.")
                    )
                elif result.get("text_message"):
                    await turn_context.send_activity(MessageFactory.text(result["text_message"]))
            elif result.get("error_message"):
                await turn_context.send_activity(
                    MessageFactory.text(f"❌ {result['error_message']}")
                )

            return True

        except Exception as e:
            logger.error(f"Error executing command '/{command_name}': {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(f"❌ Error executing command '/{command_name}': {e!s}")
            )
            return True  # Still handled, just with error

    async def _handle_natural_language(
        self,
        turn_context: TurnContext,
        text: str,
        user_id: str,
    ) -> None:
        """Handle natural language queries using Bedrock AI.

        Args:
            turn_context: Bot Framework turn context.
            text: User message text.
            user_id: User identifier.
        """
        try:
            logger.info("Processing natural language query with Bedrock")

            # Call Bedrock AI
            response = await self.bedrock_client.call_bedrock(
                prompt=text,
                user_id=user_id,
            )

            # Store assistant response
            if self.state_manager:
                await self._store_assistant_message(
                    conversation_id=turn_context.activity.conversation.id,
                    message=response[:500],  # Limit stored length
                )

            # Send response to user
            await turn_context.send_activity(MessageFactory.text(response))

            logger.info("Successfully processed natural language query")

        except Exception as e:
            logger.error(f"Error processing natural language query: {e}", exc_info=True)
            await turn_context.send_activity(
                MessageFactory.text(
                    "I'm having trouble processing your request right now. "
                    "Please try again in a moment."
                )
            )

    async def _check_for_command_id_request(
        self,
        turn_context: TurnContext,
        text: str,
        user_id: str,  # noqa: ARG002 - Reserved for future use
    ) -> bool:
        """Check if user is requesting status of a command ID.

        Patterns matched:
        - "command 12345"
        - "cmd abc-123"
        - "show command abc123"
        - "abc123 status"
        - "status of command abc123"

        Args:
            turn_context: Bot Framework turn context.
            text: User message text.
            user_id: User identifier (reserved for future use).

        Returns:
            True if command ID request was handled, False otherwise.

        Note:
            Phase 4A: Simplified implementation. Full command tracking integration
            will be enhanced when command system is migrated in Phase 4B/4C.
        """
        # Skip if no command tracker or MCP manager available
        if not self.command_tracker or not self.mcp_manager:
            return False

        # Pattern to match command ID requests
        command_id_patterns = [
            r"\b(?:command|cmd)\s+([a-f0-9\-]{8,})\b",
            r"\b([a-f0-9\-]{8,})\s+(?:status|result|output)\b",
            r"\bshow\s+(?:command|cmd)?\s*([a-f0-9\-]{8,})\b",
            r"\bcheck\s+(?:command|cmd)?\s*([a-f0-9\-]{8,})\b",
            r"\bstatus\s+(?:of\s+)?(?:command|cmd)?\s*([a-f0-9\-]{8,})\b",
        ]

        for pattern in command_id_patterns:
            match = re.search(pattern, text.lower())
            if match:
                command_id = match.group(1)
                logger.info(f"User requesting status of command ID: {command_id}")

                try:
                    # Check if command is tracked
                    tracking_info = self.command_tracker.get_command_status(command_id)

                    if tracking_info and self.mcp_manager:
                        # Get status via MCP
                        response_text = f"**Command ID: {command_id}**\n\n"

                        try:
                            # Get command invocation status via MCP
                            # Note: In Phase 4B/4C, this will be enhanced with proper
                            # instance tracking from the command tracker
                            status_result = await self.mcp_manager.call_aws_api_tool(
                                "get-command-invocation",
                                {
                                    "CommandId": command_id,
                                    "InstanceId": tracking_info.instance_id,
                                },
                            )

                            if status_result and not status_result.get("error"):
                                status = status_result.get("Status", "Unknown")
                                response_text += f"• **{tracking_info.instance_id}**: {status}\n"

                                # Show output preview if completed
                                if status in ["Success", "Failed"]:
                                    output = status_result.get("StandardOutputContent", "")
                                    if output:
                                        preview = output[:200] + (
                                            "..." if len(output) > 200 else ""
                                        )
                                        response_text += f"  Output: ```{preview}```\n"

                                    error = status_result.get("StandardErrorContent", "")
                                    if error:
                                        error_preview = error[:200] + (
                                            "..." if len(error) > 200 else ""
                                        )
                                        response_text += f"  Error: ```{error_preview}```\n"
                            else:
                                error_msg = status_result.get("error", "Unknown")
                                response_text += f"• Error: {error_msg}\n"

                        except Exception as e:
                            logger.warning(f"Failed to get status for {command_id}: {e}")
                            response_text += f"• Error checking status: {e!s}\n"

                        await turn_context.send_activity(MessageFactory.text(response_text))
                        return True

                    # Command ID not found
                    response_text = (
                        f"❌ Command ID `{command_id}` not found or no longer available.\n\n"
                    )
                    response_text += "This could mean:\n"
                    response_text += (
                        "• The command has expired (SSM commands expire after 30 days)\n"
                    )
                    response_text += "• The command ID is incorrect\n"
                    response_text += "• The command was executed in a different session"

                    await turn_context.send_activity(MessageFactory.text(response_text))
                    return True

                except Exception as e:
                    logger.error(f"Error checking command ID {command_id}: {e}", exc_info=True)
                    await turn_context.send_activity(
                        MessageFactory.text(f"❌ Error checking command ID `{command_id}`: {e!s}")
                    )
                    return True

        return False  # No command ID pattern matched

    def _remove_mentions(self, activity: Activity) -> str:
        """Remove bot mentions from message text.

        Args:
            activity: Bot Framework activity.

        Returns:
            Text with mentions removed.
        """
        text = activity.text or ""

        # Remove HTML mentions
        text = re.sub(r"<at>.*?</at>", "", text).strip()

        # Remove @mentions at beginning
        text = re.sub(r"^@\w+\s+", "", text)

        # Remove generic @bot mentions
        text = re.sub(r"@bot\s+", "", text, flags=re.IGNORECASE)

        # Remove whitespace
        text = text.strip()

        # Use entities for precise mention removal if available
        if hasattr(activity, "entities") and activity.entities:
            for entity in activity.entities:
                if hasattr(entity, "type") and entity.type == "mention" and hasattr(entity, "text"):
                    mention_text = entity.text
                    text = text.replace(mention_text, "", 1).strip()

        logger.debug(f"Text after mention removal: '{text}'")
        return text

    async def _store_user_message(
        self,
        conversation_id: str,
        user_id: str,  # noqa: ARG002 - Reserved for future use
        message: str,
    ) -> None:
        """Store user message in conversation state.

        Args:
            conversation_id: Conversation identifier.
            user_id: User identifier (reserved for future use).
            message: User message text.
        """
        if not self.state_manager:
            return

        try:
            state = await self.state_manager.get_state(conversation_id)
            if state:
                # Append to existing conversation history
                state.history.append(
                    {
                        "role": "user",
                        "content": message,
                        "timestamp": "now",  # TODO: Use datetime
                    }
                )
                await self.state_manager.save_state(state)
        except Exception as e:
            logger.warning(f"Failed to store user message: {e}")

    async def _store_assistant_message(
        self,
        conversation_id: str,
        message: str,
    ) -> None:
        """Store assistant message in conversation state.

        Args:
            conversation_id: Conversation identifier.
            message: Assistant message text.
        """
        if not self.state_manager:
            return

        try:
            state = await self.state_manager.get_state(conversation_id)
            if state:
                # Append to existing conversation history
                state.history.append(
                    {
                        "role": "assistant",
                        "content": message,
                        "timestamp": "now",  # TODO: Use datetime
                    }
                )
                await self.state_manager.save_state(state)
        except Exception as e:
            logger.warning(f"Failed to store assistant message: {e}")

    def register_command(
        self,
        command_name: str,
        command_class: type[CommandHandler],
    ) -> None:
        """Register a slash command handler.

        This method will be used in Phase 4B when commands are migrated.

        Args:
            command_name: Command name (without '/' prefix).
            command_class: Command handler class.

        Example:
            >>> handler.register_command("help", HelpCommand)
            >>> # Now '/help' will route to HelpCommand
        """
        self._command_registry[command_name.lower()] = command_class
        logger.info(f"Registered command: /{command_name}")
