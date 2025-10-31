"""Bot Framework adapter for Microsoft Teams integration.

This module provides the adapter for handling Bot Framework activities,
authentication, and error handling for Microsoft Teams.
"""

import logging

from botbuilder.core import TurnContext
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.schema import Activity, ConversationReference
from botframework.connector.auth import (
    AuthenticationConfiguration,
    SimpleCredentialProvider,
)

from ohlala_smartops.config.settings import Settings

logger = logging.getLogger(__name__)


class OhlalaAdapter(CloudAdapter):  # type: ignore[misc]
    """Custom Bot Framework adapter for Ohlala SmartOps.

    This adapter handles authentication, error handling, and activity processing
    for Microsoft Teams conversations.

    Attributes:
        settings: Application settings for authentication.

    Example:
        >>> settings = Settings()
        >>> adapter = OhlalaAdapter(settings)
        >>> await adapter.process_activity(activity, auth_header, bot_logic)
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the Bot Framework adapter.

        Args:
            settings: Application settings with Teams credentials.
        """
        self.settings = settings

        # Create credential provider
        credential_provider = SimpleCredentialProvider(
            app_id=settings.microsoft_app_id,
            app_password=settings.microsoft_app_password,
        )

        # Create authentication configuration
        auth_config = AuthenticationConfiguration()

        # Create authentication
        bot_framework_authentication = ConfigurationBotFrameworkAuthentication(
            settings=None,  # Use environment variables
            auth_configuration=auth_config,
            credential_provider=credential_provider,
            channel_provider=None,
        )

        # Initialize CloudAdapter
        super().__init__(bot_framework_authentication)

        # Set up error handler
        self.on_turn_error = self._on_error

        logger.info("Bot Framework adapter initialized")

    async def _on_error(self, context: TurnContext, error: Exception) -> None:
        """Handle errors that occur during activity processing.

        This method is called when an uncaught exception occurs during
        the processing of an activity.

        Args:
            context: Turn context for the current activity.
            error: Exception that was raised.
        """
        logger.error(f"Error processing activity: {error}", exc_info=True)

        # Send a message to the user
        error_message = (
            "Sorry, an error occurred while processing your request. "
            "Please try again or contact support if the issue persists."
        )

        try:
            await context.send_activity(error_message)
        except Exception as send_error:
            logger.error(f"Error sending error message: {send_error}", exc_info=True)

        # Log activity details for debugging
        if context.activity:
            logger.error(
                f"Activity details - Type: {context.activity.type}, "
                f"From: {context.activity.from_property.id if context.activity.from_property else 'Unknown'}, "
                f"Text: {context.activity.text[:100] if context.activity.text else 'N/A'}"
            )

    async def send_proactive_message(
        self,
        conversation_reference: ConversationReference,
        message: str | Activity,
    ) -> None:
        """Send a proactive message to a conversation.

        This method allows the bot to send messages to users without
        them having to initiate the conversation first.

        Args:
            conversation_reference: Reference to the conversation.
            message: Message text or Activity to send.

        Example:
            >>> ref = ConversationReference(...)
            >>> await adapter.send_proactive_message(ref, "Hello from bot!")
        """

        async def callback(turn_context: TurnContext) -> None:
            """Callback to send the message.

            Args:
                turn_context: Turn context for the conversation.
            """
            if isinstance(message, str):
                await turn_context.send_activity(message)
            else:
                await turn_context.send_activity(message)

        try:
            await self.continue_conversation(
                reference=conversation_reference,
                callback=callback,
                bot_app_id=self.settings.microsoft_app_id,
            )
            logger.info(
                f"Proactive message sent to conversation {conversation_reference.conversation.id}"
            )
        except Exception as e:
            logger.error(f"Error sending proactive message: {e}", exc_info=True)
            raise


def create_adapter(settings: Settings | None = None) -> OhlalaAdapter:
    """Create and configure a Bot Framework adapter.

    Args:
        settings: Application settings. If None, loads from environment.

    Returns:
        Configured OhlalaAdapter instance.

    Example:
        >>> adapter = create_adapter()
        >>> # Use adapter to process activities
    """
    if settings is None:
        settings = Settings()

    return OhlalaAdapter(settings)
