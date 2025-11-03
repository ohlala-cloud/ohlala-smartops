"""Tests for message handler functionality.

This test suite covers message processing, command routing, natural language
handling, and command ID tracking.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ChannelAccount, ConversationAccount, Entity

from ohlala_smartops.bot.message_handler import MessageHandler


class TestMessageHandler:
    """Test suite for MessageHandler class."""

    @pytest.fixture
    def mock_bedrock_client(self) -> Mock:
        """Create mock Bedrock client."""
        client = Mock()
        client.call_bedrock = AsyncMock(return_value="AI response")
        return client

    @pytest.fixture
    def mock_mcp_manager(self) -> Mock:
        """Create mock MCP manager."""
        manager = Mock()
        manager.call_aws_api_tool = AsyncMock(
            return_value={"Status": "Success", "StandardOutputContent": "Command output"}
        )
        return manager

    @pytest.fixture
    def mock_state_manager(self) -> Mock:
        """Create mock state manager."""
        manager = Mock()
        manager.get_state = AsyncMock(return_value=None)
        manager.save_state = AsyncMock()
        return manager

    @pytest.fixture
    def mock_command_tracker(self) -> Mock:
        """Create mock command tracker."""
        tracker = Mock()
        tracker.get_command_status = Mock(return_value=None)
        return tracker

    @pytest.fixture
    def message_handler(
        self,
        mock_bedrock_client: Mock,
        mock_mcp_manager: Mock,
        mock_state_manager: Mock,
        mock_command_tracker: Mock,
    ) -> MessageHandler:
        """Create message handler instance with mocked dependencies."""
        return MessageHandler(
            bedrock_client=mock_bedrock_client,
            mcp_manager=mock_mcp_manager,
            state_manager=mock_state_manager,
            command_tracker=mock_command_tracker,
        )

    @pytest.fixture
    def mock_turn_context(self) -> Mock:
        """Create mock turn context."""
        context = Mock(spec=TurnContext)
        context.activity = Activity(
            type="message",
            text="Hello bot",
            from_property=ChannelAccount(id="user123", name="Test User"),
            conversation=ConversationAccount(id="conv123"),
        )
        context.send_activity = AsyncMock()
        return context

    # Initialization tests

    def test_initialization_default(self) -> None:
        """Test message handler initialization with default dependencies."""
        handler = MessageHandler()

        assert handler.bedrock_client is not None
        # command_tracker is optional and may be None
        assert isinstance(handler._command_registry, dict)
        assert len(handler._command_registry) == 0

    def test_initialization_with_dependencies(
        self,
        mock_bedrock_client: Mock,
        mock_mcp_manager: Mock,
        mock_state_manager: Mock,
        mock_command_tracker: Mock,
    ) -> None:
        """Test message handler initialization with provided dependencies."""
        handler = MessageHandler(
            bedrock_client=mock_bedrock_client,
            mcp_manager=mock_mcp_manager,
            state_manager=mock_state_manager,
            command_tracker=mock_command_tracker,
        )

        assert handler.bedrock_client is mock_bedrock_client
        assert handler.mcp_manager is mock_mcp_manager
        assert handler.state_manager is mock_state_manager
        assert handler.command_tracker is mock_command_tracker

    # Message processing tests

    @pytest.mark.asyncio
    async def test_on_message_activity_simple_message(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test processing simple message routes to Bedrock AI."""
        await message_handler.on_message_activity(mock_turn_context)

        # Should call Bedrock with the message
        mock_bedrock_client.call_bedrock.assert_called_once()
        call_args = mock_bedrock_client.call_bedrock.call_args
        assert call_args.kwargs["prompt"] == "Hello bot"
        assert call_args.kwargs["user_id"] == "user123"

        # Should send response
        mock_turn_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_message_activity_with_mentions(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test message processing removes @mentions."""
        mock_turn_context.activity.text = "<at>Bot</at> Hello there"
        mock_turn_context.activity.entities = []

        await message_handler.on_message_activity(mock_turn_context)

        # Should call Bedrock with mention removed
        mock_bedrock_client.call_bedrock.assert_called_once()
        call_args = mock_bedrock_client.call_bedrock.call_args
        assert call_args.kwargs["prompt"] == "Hello there"

    @pytest.mark.asyncio
    async def test_on_message_activity_empty_text(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test handling empty message text."""
        mock_turn_context.activity.text = ""

        await message_handler.on_message_activity(mock_turn_context)

        # Should not call Bedrock for empty message
        mock_bedrock_client.call_bedrock.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_activity_error_handling(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test error handling during message processing."""
        mock_bedrock_client.call_bedrock.side_effect = Exception("Bedrock error")

        await message_handler.on_message_activity(mock_turn_context)

        # Should send error message
        mock_turn_context.send_activity.assert_called_once()
        # Extract the activity text from the call
        activity = mock_turn_context.send_activity.call_args[0][0]
        assert hasattr(activity, "text")
        assert "trouble" in activity.text.lower() or "error" in activity.text.lower()

    # Command handling tests

    @pytest.mark.asyncio
    async def test_handle_command_not_found(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test handling unknown slash command routes to AI."""
        mock_turn_context.activity.text = "/unknown command"

        await message_handler.on_message_activity(mock_turn_context)

        # Should call Bedrock since command not found
        mock_bedrock_client.call_bedrock.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_command_registered(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test handling registered slash command."""
        # Create mock command class
        mock_command = Mock()
        mock_command_instance = Mock()
        mock_command_instance.execute = AsyncMock(
            return_value={"success": True, "text_message": "Command executed"}
        )
        mock_command.return_value = mock_command_instance

        # Register command
        message_handler.register_command("test", mock_command)

        # Execute command
        mock_turn_context.activity.text = "/test arg1 arg2"
        await message_handler.on_message_activity(mock_turn_context)

        # Should execute registered command
        mock_command.assert_called_once()
        mock_command_instance.execute.assert_called_once()

        # Should not call Bedrock
        mock_bedrock_client.call_bedrock.assert_not_called()

        # Should send success message
        mock_turn_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_command_with_error(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test handling command execution error."""
        # Create mock command that raises error
        mock_command = Mock()
        mock_command_instance = Mock()
        mock_command_instance.execute = AsyncMock(side_effect=Exception("Command error"))
        mock_command.return_value = mock_command_instance

        # Register command
        message_handler.register_command("error", mock_command)

        # Execute command
        mock_turn_context.activity.text = "/error"
        await message_handler.on_message_activity(mock_turn_context)

        # Should send error message
        mock_turn_context.send_activity.assert_called_once()
        activity = mock_turn_context.send_activity.call_args[0][0]
        assert hasattr(activity, "text")
        assert "❌" in activity.text

    @pytest.mark.asyncio
    async def test_handle_command_result_with_error_message(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
    ) -> None:
        """Test handling command result with error message."""
        # Create mock command that returns error
        mock_command = Mock()
        mock_command_instance = Mock()
        mock_command_instance.execute = AsyncMock(
            return_value={"success": False, "error_message": "Command failed"}
        )
        mock_command.return_value = mock_command_instance

        # Register command
        message_handler.register_command("fail", mock_command)

        # Execute command
        mock_turn_context.activity.text = "/fail"
        await message_handler.on_message_activity(mock_turn_context)

        # Should send error message
        mock_turn_context.send_activity.assert_called_once()
        activity = mock_turn_context.send_activity.call_args[0][0]
        assert hasattr(activity, "text")
        assert "❌" in activity.text

    # Command ID tracking tests

    @pytest.mark.asyncio
    async def test_check_for_command_id_request_matched(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_command_tracker: Mock,
        mock_mcp_manager: Mock,
    ) -> None:
        """Test checking for command ID request matches pattern."""
        # Setup tracked command
        mock_tracking_info = Mock()
        mock_tracking_info.instance_id = "i-123456"
        mock_tracking_info.command_id = "abc123def"
        mock_command_tracker.get_command_status.return_value = mock_tracking_info

        # Setup MCP response
        mock_mcp_manager.call_aws_api_tool.return_value = {
            "Status": "Success",
            "StandardOutputContent": "Command completed",
        }

        # Test various patterns
        patterns = [
            "command abc123def",
            "cmd abc123def",
            "show command abc123def",
            "check cmd abc123def",
            "status of command abc123def",
        ]

        for pattern in patterns:
            mock_turn_context.send_activity.reset_mock()
            mock_turn_context.activity.text = pattern

            await message_handler.on_message_activity(mock_turn_context)

            # Should send status response
            mock_turn_context.send_activity.assert_called_once()
            activity = mock_turn_context.send_activity.call_args[0][0]
            assert hasattr(activity, "text")
            assert "abc123def" in activity.text
            assert "i-123456" in activity.text

    @pytest.mark.asyncio
    async def test_check_for_command_id_request_not_found(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_command_tracker: Mock,
    ) -> None:
        """Test checking for command ID that doesn't exist."""
        # No tracked command
        mock_command_tracker.get_command_status.return_value = None

        mock_turn_context.activity.text = "command abc123def"

        await message_handler.on_message_activity(mock_turn_context)

        # Should send "not found" message
        mock_turn_context.send_activity.assert_called_once()
        activity = mock_turn_context.send_activity.call_args[0][0]
        assert hasattr(activity, "text")
        assert "not found" in activity.text.lower()

    @pytest.mark.asyncio
    async def test_check_for_command_id_request_mcp_error(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_command_tracker: Mock,
        mock_mcp_manager: Mock,
    ) -> None:
        """Test checking command ID when MCP returns error."""
        # Setup tracked command
        mock_tracking_info = Mock()
        mock_tracking_info.instance_id = "i-123456"
        mock_tracking_info.command_id = "abc123def"
        mock_command_tracker.get_command_status.return_value = mock_tracking_info

        # Setup MCP error response
        mock_mcp_manager.call_aws_api_tool.return_value = {"error": "MCP error"}

        mock_turn_context.activity.text = "command abc123def"

        await message_handler.on_message_activity(mock_turn_context)

        # Should send response with error info
        mock_turn_context.send_activity.assert_called_once()
        activity = mock_turn_context.send_activity.call_args[0][0]
        assert hasattr(activity, "text")
        assert "Error" in activity.text or "error" in activity.text

    # Natural language handling tests

    @pytest.mark.asyncio
    async def test_handle_natural_language_success(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test successful natural language processing."""
        mock_bedrock_client.call_bedrock.return_value = "Here are your instances..."

        await message_handler._handle_natural_language(
            mock_turn_context,
            "Show me my instances",
            "user123",
        )

        # Should call Bedrock
        mock_bedrock_client.call_bedrock.assert_called_once()

        # Should send response
        mock_turn_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_natural_language_error(
        self,
        message_handler: MessageHandler,
        mock_turn_context: Mock,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test natural language processing with Bedrock error."""
        mock_bedrock_client.call_bedrock.side_effect = Exception("Bedrock error")

        await message_handler._handle_natural_language(
            mock_turn_context,
            "Show me my instances",
            "user123",
        )

        # Should send error message
        mock_turn_context.send_activity.assert_called_once()
        activity = mock_turn_context.send_activity.call_args[0][0]
        assert hasattr(activity, "text")
        assert "trouble" in activity.text.lower()

    # Mention removal tests

    def test_remove_mentions_html_tags(
        self,
        message_handler: MessageHandler,
    ) -> None:
        """Test removing HTML mention tags."""
        activity = Activity(
            text="<at>Bot</at> hello there",
            entities=[],
        )

        result = message_handler._remove_mentions(activity)

        assert result == "hello there"
        assert "<at>" not in result

    def test_remove_mentions_at_prefix(
        self,
        message_handler: MessageHandler,
    ) -> None:
        """Test removing @ prefix mentions."""
        activity = Activity(
            text="@BotName hello there",
            entities=[],
        )

        result = message_handler._remove_mentions(activity)

        assert result == "hello there"
        assert "@" not in result

    def test_remove_mentions_bot_mention(
        self,
        message_handler: MessageHandler,
    ) -> None:
        """Test removing @bot mentions."""
        activity = Activity(
            text="@bot show instances",
            entities=[],
        )

        result = message_handler._remove_mentions(activity)

        assert result == "show instances"
        assert "@bot" not in result.lower()

    def test_remove_mentions_with_entities(
        self,
        message_handler: MessageHandler,
    ) -> None:
        """Test removing mentions using entities."""
        entity = Entity(type="mention")
        entity.text = "Bot Name"

        activity = Activity(
            text="Bot Name hello there",
            entities=[entity],
        )

        result = message_handler._remove_mentions(activity)

        assert result == "hello there"

    def test_remove_mentions_empty_text(
        self,
        message_handler: MessageHandler,
    ) -> None:
        """Test removing mentions from empty text."""
        activity = Activity(
            text="",
            entities=[],
        )

        result = message_handler._remove_mentions(activity)

        assert result == ""

    def test_remove_mentions_no_mentions(
        self,
        message_handler: MessageHandler,
    ) -> None:
        """Test text without mentions remains unchanged."""
        activity = Activity(
            text="hello there",
            entities=[],
        )

        result = message_handler._remove_mentions(activity)

        assert result == "hello there"

    # Command registration tests

    def test_register_command(
        self,
        message_handler: MessageHandler,
    ) -> None:
        """Test registering a command handler."""
        mock_command = Mock()

        message_handler.register_command("test", mock_command)

        assert "test" in message_handler._command_registry
        assert message_handler._command_registry["test"] is mock_command

    def test_register_command_case_insensitive(
        self,
        message_handler: MessageHandler,
    ) -> None:
        """Test command registration is case-insensitive."""
        mock_command = Mock()

        message_handler.register_command("TEST", mock_command)

        assert "test" in message_handler._command_registry
        assert "TEST" not in message_handler._command_registry

    # State management tests

    @pytest.mark.asyncio
    async def test_store_user_message_no_state_manager(
        self,
        mock_bedrock_client: Mock,
    ) -> None:
        """Test storing user message when state manager is None."""
        handler = MessageHandler(
            bedrock_client=mock_bedrock_client,
            state_manager=None,
        )

        # Should not raise error
        await handler._store_user_message("conv123", "user123", "Hello")

    @pytest.mark.asyncio
    async def test_store_user_message_with_state(
        self,
        message_handler: MessageHandler,
        mock_state_manager: Mock,
    ) -> None:
        """Test storing user message in state."""
        mock_state = Mock()
        mock_state.history = []
        mock_state_manager.get_state.return_value = mock_state

        await message_handler._store_user_message("conv123", "user123", "Hello")

        # Should get and save state
        mock_state_manager.get_state.assert_called_once_with("conv123")
        mock_state_manager.save_state.assert_called_once()

        # Should append to history
        assert len(mock_state.history) == 1
        assert mock_state.history[0]["role"] == "user"
        assert mock_state.history[0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_store_assistant_message_with_state(
        self,
        message_handler: MessageHandler,
        mock_state_manager: Mock,
    ) -> None:
        """Test storing assistant message in state."""
        mock_state = Mock()
        mock_state.history = []
        mock_state_manager.get_state.return_value = mock_state

        await message_handler._store_assistant_message("conv123", "AI response")

        # Should get and save state
        mock_state_manager.get_state.assert_called_once_with("conv123")
        mock_state_manager.save_state.assert_called_once()

        # Should append to history
        assert len(mock_state.history) == 1
        assert mock_state.history[0]["role"] == "assistant"
        assert mock_state.history[0]["content"] == "AI response"

    @pytest.mark.asyncio
    async def test_store_message_state_error(
        self,
        message_handler: MessageHandler,
        mock_state_manager: Mock,
    ) -> None:
        """Test storing message when state manager raises error."""
        mock_state_manager.get_state.side_effect = Exception("State error")

        # Should not raise error (logs warning instead)
        await message_handler._store_user_message("conv123", "user123", "Hello")
