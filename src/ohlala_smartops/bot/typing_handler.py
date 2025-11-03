"""Typing indicator management for Microsoft Teams bot.

This module provides typing indicator functionality to improve user experience
by showing that the bot is actively processing requests.

Phase 4A: Simple typing indicator support. Enhanced coordination with
async operations will be added in Phase 4B.
"""

import asyncio
import contextlib
import logging
from typing import Final

from botbuilder.core import TurnContext
from botbuilder.schema import Activity

logger: Final = logging.getLogger(__name__)


class TypingHandler:
    """Manages typing indicators for bot activities.

    This handler provides methods to send typing indicators during long-running
    operations to improve user experience in Microsoft Teams.

    Attributes:
        _active_typing_tasks: Dict tracking active typing tasks per user.

    Example:
        >>> handler = TypingHandler()
        >>> stop_event = await handler.start_typing(turn_context)
        >>> # ... perform long operation ...
        >>> await handler.stop_typing(turn_context)

    Note:
        Phase 4A focuses on basic typing indicator support.
        Enhanced features will be added in subsequent phases.
    """

    def __init__(self) -> None:
        """Initialize typing handler."""
        self._active_typing_tasks: dict[str, dict[str, asyncio.Event | asyncio.Task[None]]] = {}
        logger.info("TypingHandler initialized")

    async def send_typing_indicator(self, turn_context: TurnContext) -> None:
        """Send a single typing indicator to Teams.

        Args:
            turn_context: Bot Framework turn context.

        Example:
            >>> await handler.send_typing_indicator(turn_context)
        """
        typing_activity = Activity(type="typing")
        await turn_context.send_activity(typing_activity)

    async def send_periodic_typing(
        self,
        turn_context: TurnContext,
        stop_event: asyncio.Event,
    ) -> None:
        """Send typing indicators periodically until stopped.

        Sends a typing indicator every 3 seconds until stop_event is set.

        Args:
            turn_context: Bot Framework turn context.
            stop_event: Event to signal when to stop sending indicators.

        Example:
            >>> stop_event = asyncio.Event()
            >>> task = asyncio.create_task(
            ...     handler.send_periodic_typing(turn_context, stop_event)
            ... )
            >>> # ... later ...
            >>> stop_event.set()
            >>> await task
        """
        user_id = self._get_user_id(turn_context)

        try:
            while not stop_event.is_set():
                await self.send_typing_indicator(turn_context)
                # Wait 3 seconds or until stop event
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=3.0)
        except Exception as e:
            logger.debug(f"Periodic typing stopped for user {user_id}: {e}")
        finally:
            # Clean up tracking when typing stops
            self._active_typing_tasks.pop(user_id, None)

    async def with_typing_indicator(
        self,
        turn_context: TurnContext,
        operation: asyncio.Task[str] | asyncio.Task[None],
    ) -> str | None:
        """Execute an async operation while showing typing indicator.

        Args:
            turn_context: Bot Framework turn context.
            operation: Async operation to execute.

        Returns:
            Result of the operation.

        Example:
            >>> result = await handler.with_typing_indicator(
            ...     turn_context,
            ...     some_async_operation()
            ... )
        """
        stop_event = asyncio.Event()

        # Start periodic typing
        typing_task = asyncio.create_task(self.send_periodic_typing(turn_context, stop_event))

        try:
            # Execute the main operation
            return await operation
        finally:
            # Stop typing indicator
            stop_event.set()
            try:
                await asyncio.wait_for(typing_task, timeout=2.0)
            except TimeoutError:
                logger.debug("Typing task cleanup timed out, cancelling")
                typing_task.cancel()
            except Exception as e:
                logger.debug(f"Error during typing task cleanup: {e}")
                if not typing_task.done():
                    typing_task.cancel()

    async def start_typing(self, turn_context: TurnContext) -> asyncio.Event:
        """Start typing indicator for a user.

        Starts a periodic typing indicator and returns a stop event that
        can be used to stop it later.

        Args:
            turn_context: Bot Framework turn context.

        Returns:
            Stop event to signal when to stop typing.

        Example:
            >>> stop_event = await handler.start_typing(turn_context)
            >>> # ... perform operation ...
            >>> stop_event.set()
        """
        user_id = self._get_user_id(turn_context)

        # Stop any existing typing for this user first
        await self.stop_typing_for_user(user_id)

        # Create new stop event and start typing
        stop_event = asyncio.Event()
        typing_task = asyncio.create_task(self.send_periodic_typing(turn_context, stop_event))

        self._active_typing_tasks[user_id] = {
            "stop_event": stop_event,
            "task": typing_task,
        }

        logger.debug(f"Started typing indicator for user {user_id}")
        return stop_event

    async def stop_typing_for_user(self, user_id: str) -> None:
        """Stop typing indicator for a specific user.

        Args:
            user_id: User identifier.

        Example:
            >>> await handler.stop_typing_for_user("user-123")
        """
        if user_id not in self._active_typing_tasks:
            logger.debug(
                f"No active typing task found for user {user_id} "
                "(already stopped or never started)"
            )
            return

        task_info = self._active_typing_tasks[user_id]
        stop_event: asyncio.Event = task_info["stop_event"]  # type: ignore[assignment]
        typing_task: asyncio.Task[None] = task_info["task"]  # type: ignore[assignment]

        # Signal stop
        stop_event.set()

        # Clean up task
        try:
            await asyncio.wait_for(typing_task, timeout=1.0)
        except TimeoutError:
            logger.debug(f"Typing task cleanup timed out for user {user_id}, cancelling")
            typing_task.cancel()
        except Exception as e:
            logger.debug(f"Error during typing task cleanup for user {user_id}: {e}")
            if not typing_task.done():
                typing_task.cancel()

        # Remove from tracking
        self._active_typing_tasks.pop(user_id, None)
        logger.debug(f"Stopped typing indicator for user {user_id}")

    async def stop_typing(self, turn_context: TurnContext) -> None:
        """Stop typing indicator for the user in the turn context.

        Args:
            turn_context: Bot Framework turn context.

        Example:
            >>> await handler.stop_typing(turn_context)
        """
        user_id = self._get_user_id(turn_context)
        await self.stop_typing_for_user(user_id)

    def is_typing(self, turn_context: TurnContext) -> bool:
        """Check if typing indicator is active for the user.

        Args:
            turn_context: Bot Framework turn context.

        Returns:
            True if typing indicator is active, False otherwise.

        Example:
            >>> if handler.is_typing(turn_context):
            ...     print("Bot is currently typing")
        """
        user_id = self._get_user_id(turn_context)
        return user_id in self._active_typing_tasks

    def should_show_typing(self, context: str = "processing") -> bool:
        """Determine if typing should be shown based on context.

        Args:
            context: Context string describing the current operation.

        Returns:
            True if typing should be shown, False otherwise.

        Example:
            >>> if handler.should_show_typing("llm_thinking"):
            ...     await handler.start_typing(turn_context)
        """
        # Contexts where typing should be shown
        show_typing_contexts = {
            "processing",  # General processing
            "llm_thinking",  # LLM is processing
            "api_call",  # Making API calls
            "analysis",  # Analyzing data
        }

        # Contexts where typing should NOT be shown
        hide_typing_contexts = {
            "approval_sent",  # Approval card sent, waiting for user
            "user_input",  # Waiting for user input
            "card_response",  # Responding to card click
            "final_response",  # Sending final response
            "error",  # Error occurred
        }

        if context in hide_typing_contexts:
            return False

        return context in show_typing_contexts

    def _get_user_id(self, turn_context: TurnContext) -> str:
        """Extract user ID from turn context.

        Args:
            turn_context: Bot Framework turn context.

        Returns:
            User ID string, or "unknown" if not available.
        """
        if not turn_context.activity or not turn_context.activity.from_property:
            return "unknown"

        return getattr(turn_context.activity.from_property, "id", "unknown")
