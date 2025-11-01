"""Message routing and Bot Framework endpoints for Ohlala SmartOps.

This module provides the FastAPI endpoints for receiving Bot Framework
activities from Microsoft Teams, routing them to appropriate handlers,
and managing conversation state.
"""

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from ohlala_smartops.bot.adapter import create_adapter
from ohlala_smartops.bot.handlers import OhlalaActivityHandler
from ohlala_smartops.bot.state import create_state_manager
from ohlala_smartops.config.settings import Settings

logger = logging.getLogger(__name__)

# Create router for message endpoints
router = APIRouter()

# Initialize global instances
# These will be replaced with proper dependency injection in production
# Use lazy initialization to avoid issues during testing
_adapter: Any | None = None
_handler: Any | None = None
_state_manager: Any | None = None


def _ensure_initialized() -> None:
    """Ensure bot services are initialized."""
    global _adapter, _handler, _state_manager
    if _adapter is None:
        _adapter = create_adapter()
    if _handler is None:
        _handler = OhlalaActivityHandler()
    if _state_manager is None:
        _state_manager = create_state_manager("memory")


@router.post("/messages", status_code=status.HTTP_200_OK)
async def handle_messages(
    request: Request,
    authorization: str = Header(..., description="Authorization header from Bot Framework"),
) -> Response:
    """Handle incoming activities from Microsoft Teams.

    This endpoint receives Bot Framework activities (messages, events, etc.)
    from Microsoft Teams, authenticates the request, and routes it to the
    appropriate handler.

    Args:
        request: FastAPI request object containing the activity.
        authorization: Authorization header for Bot Framework authentication.

    Returns:
        Response from the bot handler.

    Raises:
        HTTPException: If authentication fails or request is invalid.

    Example:
        POST /api/messages
        Authorization: Bearer <token>
        Content-Type: application/json

        {
            "type": "message",
            "text": "Hello bot",
            "from": {...},
            "conversation": {...}
        }
    """
    _ensure_initialized()
    try:
        # Get the request body as JSON
        body = await request.json()

        logger.info(
            f"Received activity: type={body.get('type')}, "
            f"from={body.get('from', {}).get('name')}"
        )

        # Process the activity using the Bot Framework adapter
        # The adapter will handle authentication and call our handler
        async def bot_logic(turn_context: Any) -> None:
            """Bot logic callback for processing the activity.

            Args:
                turn_context: Turn context from Bot Framework.
            """
            await _handler.on_turn(turn_context)

        # Process activity with authentication
        response = await _adapter.process_activity(
            activity=body,
            auth_header=authorization,
            logic=bot_logic,
        )

        # Return the response
        if response:
            return Response(
                content=response.body if hasattr(response, "body") else "",
                status_code=response.status if hasattr(response, "status") else 200,
                media_type="application/json",
            )

        return Response(status_code=status.HTTP_200_OK)

    except ValueError as e:
        logger.error(f"Invalid request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request: {e!s}",
        ) from e
    except PermissionError as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        ) from e
    except Exception as e:
        logger.error(f"Error processing activity: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from e


@router.get("/messages/test", status_code=status.HTTP_200_OK)
async def test_endpoint() -> dict[str, str]:
    """Test endpoint to verify the bot is reachable.

    This endpoint is useful for health checks and verifying the bot
    is properly deployed and accessible.

    Returns:
        Simple test response.

    Example:
        GET /api/messages/test
        Response: {"status": "ok", "message": "Bot is reachable"}
    """
    return {
        "status": "ok",
        "message": "Ohlala SmartOps bot is reachable",
    }


@router.post("/messages/proactive", status_code=status.HTTP_200_OK)
async def send_proactive_message(request: Request) -> dict[str, str]:
    """Send a proactive message to a conversation.

    This endpoint allows sending messages to users without them initiating
    the conversation. Requires a conversation reference.

    Args:
        request: FastAPI request with conversation reference and message.

    Returns:
        Status of the proactive message.

    Raises:
        HTTPException: If the request is invalid or sending fails.

    Example:
        POST /api/messages/proactive
        Content-Type: application/json

        {
            "conversation_reference": {...},
            "message": "Hello from bot!"
        }
    """
    try:
        body = await request.json()

        conversation_reference = body.get("conversation_reference")
        message = body.get("message")

        if not conversation_reference or not message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="conversation_reference and message are required",
            )

        # Send proactive message
        await _adapter.send_proactive_message(conversation_reference, message)

        logger.info("Sent proactive message to conversation")

        return {
            "status": "success",
            "message": "Proactive message sent",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending proactive message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send proactive message: {e!s}",
        ) from e


def get_adapter() -> Any:
    """Get the global Bot Framework adapter instance.

    Returns:
        Bot Framework adapter.

    Example:
        >>> adapter = get_adapter()
        >>> await adapter.process_activity(...)
    """
    _ensure_initialized()
    return _adapter


def get_handler() -> OhlalaActivityHandler:
    """Get the global activity handler instance.

    Returns:
        Activity handler.

    Example:
        >>> handler = get_handler()
        >>> await handler.on_message_activity(turn_context)
    """
    _ensure_initialized()
    return _handler


def get_state_manager() -> Any:
    """Get the global state manager instance.

    Returns:
        Conversation state manager.

    Example:
        >>> state_manager = get_state_manager()
        >>> state = await state_manager.get_state(conversation_id)
    """
    _ensure_initialized()
    return _state_manager


def initialize_bot_services(settings: Settings | None = None) -> None:
    """Initialize or reinitialize bot services.

    This function allows updating the global adapter, handler, and state
    manager instances with new settings or configuration.

    Args:
        settings: Application settings. If None, loads from environment.

    Example:
        >>> initialize_bot_services(custom_settings)
    """
    global _adapter, _handler, _state_manager  # noqa: PLW0603

    _adapter = create_adapter(settings)
    _handler = OhlalaActivityHandler()
    _state_manager = create_state_manager("memory")

    logger.info("Bot services initialized")


# Ensure services are initialized on module import (but lazily)
# This allows tests to mock before initialization
try:
    _ensure_initialized()
except Exception:
    # Initialization may fail in test environment - that's OK
    pass
