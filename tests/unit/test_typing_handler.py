"""Tests for typing handler functionality.

This test suite covers typing indicator management, including starting,
stopping, and context-based decisions for showing typing indicators.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ChannelAccount, ConversationAccount

from ohlala_smartops.bot.typing_handler import TypingHandler


class TestTypingHandler:
    """Test suite for TypingHandler class."""

    @pytest.fixture
    def typing_handler(self) -> TypingHandler:
        """Create typing handler instance."""
        return TypingHandler()

    @pytest.fixture
    def mock_turn_context(self) -> Mock:
        """Create mock turn context."""
        context = Mock(spec=TurnContext)
        context.activity = Activity(
            type="message",
            from_property=ChannelAccount(id="user123", name="Test User"),
            conversation=ConversationAccount(id="conv123"),
        )
        context.send_activity = AsyncMock()
        return context

    # Initialization tests

    def test_initialization(self) -> None:
        """Test typing handler initialization."""
        handler = TypingHandler()

        assert handler._active_typing_tasks == {}

    # Send typing indicator tests

    @pytest.mark.asyncio
    async def test_send_typing_indicator(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test sending a single typing indicator."""
        await typing_handler.send_typing_indicator(mock_turn_context)

        # Should send typing activity
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert call_args.type == "typing"

    # Start/stop typing tests

    @pytest.mark.asyncio
    async def test_start_typing(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test starting typing indicator."""
        stop_event = await typing_handler.start_typing(mock_turn_context)

        # Should return stop event
        assert isinstance(stop_event, asyncio.Event)
        assert not stop_event.is_set()

        # Should have active task for user
        assert "user123" in typing_handler._active_typing_tasks

        # Clean up
        await typing_handler.stop_typing(mock_turn_context)

    @pytest.mark.asyncio
    async def test_stop_typing(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test stopping typing indicator."""
        # Start typing first
        await typing_handler.start_typing(mock_turn_context)
        assert "user123" in typing_handler._active_typing_tasks

        # Stop typing
        await typing_handler.stop_typing(mock_turn_context)

        # Should not have active task
        assert "user123" not in typing_handler._active_typing_tasks

    @pytest.mark.asyncio
    async def test_stop_typing_when_not_active(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test stopping typing when no typing is active."""
        # Should not raise error
        await typing_handler.stop_typing(mock_turn_context)

        # Should still have no active tasks
        assert "user123" not in typing_handler._active_typing_tasks

    @pytest.mark.asyncio
    async def test_start_typing_replaces_existing(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test starting typing when already active replaces existing task."""
        # Start typing first time
        await typing_handler.start_typing(mock_turn_context)
        first_task_info = typing_handler._active_typing_tasks["user123"]

        # Start typing again
        await typing_handler.start_typing(mock_turn_context)
        second_task_info = typing_handler._active_typing_tasks["user123"]

        # Should have replaced the task
        assert first_task_info is not second_task_info

        # Clean up
        await typing_handler.stop_typing(mock_turn_context)

    # is_typing tests

    def test_is_typing_when_active(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test is_typing returns True when typing is active."""
        # Manually set active typing (to avoid async)
        typing_handler._active_typing_tasks["user123"] = {
            "stop_event": asyncio.Event(),
            "task": Mock(),
        }

        assert typing_handler.is_typing(mock_turn_context) is True

    def test_is_typing_when_not_active(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test is_typing returns False when typing is not active."""
        assert typing_handler.is_typing(mock_turn_context) is False

    # should_show_typing tests

    def test_should_show_typing_for_processing(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns True for processing context."""
        assert typing_handler.should_show_typing("processing") is True

    def test_should_show_typing_for_llm_thinking(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns True for LLM thinking."""
        assert typing_handler.should_show_typing("llm_thinking") is True

    def test_should_show_typing_for_api_call(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns True for API calls."""
        assert typing_handler.should_show_typing("api_call") is True

    def test_should_show_typing_for_analysis(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns True for analysis."""
        assert typing_handler.should_show_typing("analysis") is True

    def test_should_not_show_typing_for_approval_sent(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns False when approval sent."""
        assert typing_handler.should_show_typing("approval_sent") is False

    def test_should_not_show_typing_for_user_input(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns False when waiting for user input."""
        assert typing_handler.should_show_typing("user_input") is False

    def test_should_not_show_typing_for_card_response(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns False for card responses."""
        assert typing_handler.should_show_typing("card_response") is False

    def test_should_not_show_typing_for_final_response(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns False for final response."""
        assert typing_handler.should_show_typing("final_response") is False

    def test_should_not_show_typing_for_error(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns False for errors."""
        assert typing_handler.should_show_typing("error") is False

    def test_should_not_show_typing_for_unknown_context(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test should_show_typing returns False for unknown contexts."""
        assert typing_handler.should_show_typing("unknown_context") is False

    # Periodic typing tests

    @pytest.mark.asyncio
    async def test_send_periodic_typing_stops_on_event(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test periodic typing stops when event is set."""
        stop_event = asyncio.Event()

        # Start periodic typing
        task = asyncio.create_task(
            typing_handler.send_periodic_typing(mock_turn_context, stop_event)
        )

        # Let it send a few typing indicators
        await asyncio.sleep(0.1)

        # Stop it
        stop_event.set()
        await task

        # Should have sent at least one typing indicator
        assert mock_turn_context.send_activity.call_count >= 1

    # with_typing_indicator tests

    @pytest.mark.asyncio
    async def test_with_typing_indicator_executes_operation(
        self,
        typing_handler: TypingHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test with_typing_indicator executes the operation."""

        async def test_operation() -> str:
            await asyncio.sleep(0.05)
            return "completed"

        result = await typing_handler.with_typing_indicator(
            mock_turn_context,
            asyncio.create_task(test_operation()),
        )

        assert result == "completed"
        # Should have sent typing indicators
        assert mock_turn_context.send_activity.call_count >= 1

    # Edge cases

    def test_get_user_id_with_no_activity(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test _get_user_id returns 'unknown' when activity is None."""
        context = Mock(spec=TurnContext)
        context.activity = None

        user_id = typing_handler._get_user_id(context)
        assert user_id == "unknown"

    def test_get_user_id_with_no_from_property(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test _get_user_id returns 'unknown' when from_property is None."""
        context = Mock(spec=TurnContext)
        context.activity = Activity(type="message")
        context.activity.from_property = None

        user_id = typing_handler._get_user_id(context)
        assert user_id == "unknown"

    @pytest.mark.asyncio
    async def test_stop_typing_for_user_directly(
        self,
        typing_handler: TypingHandler,
    ) -> None:
        """Test stop_typing_for_user can be called directly with user_id."""
        # Should not raise error even if user has no active typing
        await typing_handler.stop_typing_for_user("nonexistent-user")
