"""Tests for Teams bot orchestrator.

This test suite covers bot initialization, activity routing, handler integration,
and helper methods for the main OhlalaBot class.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ChannelAccount, ConversationAccount

from ohlala_smartops.bot.teams_bot import OhlalaBot


class TestOhlalaBot:
    """Test suite for OhlalaBot class."""

    @pytest.fixture
    def mock_turn_context(self) -> Mock:
        """Create mock turn context."""
        context = Mock(spec=TurnContext)
        context.activity = Activity(
            type="message",
            from_property=ChannelAccount(id="user123", name="Test User"),
            recipient=ChannelAccount(id="bot123", name="Bot"),
            conversation=ConversationAccount(id="conv123"),
            text="test message",
            value=None,
        )
        context.send_activity = AsyncMock()
        return context

    # Initialization tests

    def test_initialization_default(self) -> None:
        """Test bot initialization with default dependencies."""
        bot = OhlalaBot()

        assert bot.mcp_manager is not None
        assert bot.bedrock_client is not None
        assert bot.state_manager is not None
        assert bot.write_op_manager is not None
        assert bot.message_handler is not None
        assert bot.card_handler is not None
        assert bot.typing_handler is not None

    def test_initialization_with_dependencies(self) -> None:
        """Test bot initialization with provided dependencies."""
        mock_bedrock = Mock()
        mock_mcp = Mock()
        mock_state = Mock()
        mock_write_op = Mock()
        mock_tracker = Mock()

        bot = OhlalaBot(
            bedrock_client=mock_bedrock,
            mcp_manager=mock_mcp,
            state_manager=mock_state,
            write_op_manager=mock_write_op,
            command_tracker=mock_tracker,
        )

        assert bot.bedrock_client is mock_bedrock
        assert bot.mcp_manager is mock_mcp
        assert bot.state_manager is mock_state
        assert bot.write_op_manager is mock_write_op
        assert bot.command_tracker is mock_tracker

    # Message activity tests

    @pytest.mark.asyncio
    async def test_on_message_activity_success(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test successful message activity handling."""
        bot = OhlalaBot()

        with patch.object(
            bot.message_handler, "on_message_activity", new=AsyncMock()
        ) as mock_handler:
            await bot.on_message_activity(mock_turn_context)

            mock_handler.assert_called_once_with(mock_turn_context)

    @pytest.mark.asyncio
    async def test_on_message_activity_error(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test message activity handling with error."""
        bot = OhlalaBot()

        with patch.object(
            bot.message_handler,
            "on_message_activity",
            side_effect=Exception("Test error"),
        ):
            await bot.on_message_activity(mock_turn_context)

            # Should send error message to user
            mock_turn_context.send_activity.assert_called_once()
            call_args = mock_turn_context.send_activity.call_args[0][0]
            assert "error" in call_args.text.lower()

    # Invoke activity tests

    @pytest.mark.asyncio
    async def test_on_invoke_activity_card_action(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test invoke activity with card action."""
        bot = OhlalaBot()
        mock_turn_context.activity.value = {"action": "test_action"}

        with patch.object(
            bot.card_handler,
            "handle_card_action",
            new=AsyncMock(return_value={"status": 200}),
        ) as mock_handler:
            result = await bot.on_invoke_activity(mock_turn_context)

            mock_handler.assert_called_once_with(mock_turn_context)
            assert result == {"status": 200}

    @pytest.mark.asyncio
    async def test_on_invoke_activity_no_value(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test invoke activity without value data."""
        bot = OhlalaBot()
        mock_turn_context.activity.value = None

        with patch.object(
            bot.__class__.__bases__[0],
            "on_invoke_activity",
            new=AsyncMock(return_value={"status": 200}),
        ):
            result = await bot.on_invoke_activity(mock_turn_context)

            # Should call parent class handler
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_on_invoke_activity_error(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test invoke activity with error."""
        bot = OhlalaBot()
        mock_turn_context.activity.value = {"action": "test"}

        with patch.object(
            bot.card_handler,
            "handle_card_action",
            side_effect=Exception("Test error"),
        ):
            result = await bot.on_invoke_activity(mock_turn_context)

            # Should return error invoke response
            assert result["status"] == 500

    # Conversation update activity tests

    @pytest.mark.asyncio
    async def test_on_conversation_update_member_added(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test conversation update when member is added."""
        bot = OhlalaBot()
        new_member = ChannelAccount(id="newuser123", name="New User")
        mock_turn_context.activity.members_added = [new_member]
        mock_turn_context.activity.members_removed = None

        await bot.on_conversation_update_activity(mock_turn_context)

        # Should send welcome message
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "welcome" in call_args.text.lower()
        assert "New User" in call_args.text

    @pytest.mark.asyncio
    async def test_on_conversation_update_bot_added(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test conversation update when bot itself is added."""
        bot = OhlalaBot()
        # Bot is the new member
        bot_member = ChannelAccount(id="bot123", name="Bot")
        mock_turn_context.activity.members_added = [bot_member]
        mock_turn_context.activity.members_removed = None

        await bot.on_conversation_update_activity(mock_turn_context)

        # Should not send welcome message to itself
        mock_turn_context.send_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_conversation_update_member_removed(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test conversation update when member is removed."""
        bot = OhlalaBot()
        removed_member = ChannelAccount(id="olduser123", name="Old User")
        mock_turn_context.activity.members_added = None
        mock_turn_context.activity.members_removed = [removed_member]

        await bot.on_conversation_update_activity(mock_turn_context)

        # Should log but not send message
        mock_turn_context.send_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_conversation_update_error(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test conversation update with error."""
        bot = OhlalaBot()
        mock_turn_context.activity.members_added = [ChannelAccount(id="user123", name="Test")]
        mock_turn_context.send_activity = AsyncMock(side_effect=Exception("Test error"))

        # Should not raise exception
        await bot.on_conversation_update_activity(mock_turn_context)

    # Helper method tests

    @pytest.mark.asyncio
    async def test_send_response_text(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test sending text response."""
        bot = OhlalaBot()

        await bot.send_response(mock_turn_context, "Test message")

        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert call_args.text == "Test message"

    @pytest.mark.asyncio
    async def test_send_response_adaptive_card(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test sending adaptive card response."""
        bot = OhlalaBot()
        card_response = {
            "adaptive_card": True,
            "card": {
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": [{"type": "TextBlock", "text": "Test card"}],
            },
        }

        await bot.send_response(mock_turn_context, card_response)

        mock_turn_context.send_activity.assert_called_once()
        # Verify it's an attachment (adaptive card)
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert hasattr(call_args, "attachments")

    @pytest.mark.asyncio
    async def test_send_response_dict_with_text(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test sending dict response with text_message."""
        bot = OhlalaBot()
        response = {"text_message": "Test message from dict"}

        await bot.send_response(mock_turn_context, response)

        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert call_args.text == "Test message from dict"

    @pytest.mark.asyncio
    async def test_send_response_unknown_format(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test sending response with unknown format."""
        bot = OhlalaBot()
        response = {"unknown_key": "value"}

        await bot.send_response(mock_turn_context, response)

        mock_turn_context.send_activity.assert_called_once()
        # Should convert to string
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert isinstance(call_args.text, str)

    @pytest.mark.asyncio
    async def test_send_response_error(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test send_response with error."""
        bot = OhlalaBot()

        # First call raises error, second call (error message) succeeds
        mock_turn_context.send_activity = AsyncMock(side_effect=[Exception("Send error"), None])

        # Should not raise exception - handles error gracefully
        await bot.send_response(mock_turn_context, "Test")

        # Should attempt to send twice (original + error message)
        assert mock_turn_context.send_activity.call_count == 2

    def test_create_adaptive_card_attachment_valid(self) -> None:
        """Test creating adaptive card attachment with valid card."""
        bot = OhlalaBot()
        card = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [{"type": "TextBlock", "text": "Test"}],
        }

        attachment = bot._create_adaptive_card_attachment(card)

        assert attachment is not None
        assert attachment.content_type == "application/vnd.microsoft.card.adaptive"

    def test_create_adaptive_card_attachment_missing_fields(self) -> None:
        """Test creating adaptive card with missing required fields."""
        bot = OhlalaBot()
        card = {"body": [{"type": "TextBlock", "text": "Test"}]}

        # Should add missing fields
        attachment = bot._create_adaptive_card_attachment(card)

        assert attachment is not None
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.5"

    def test_create_adaptive_card_attachment_invalid(self) -> None:
        """Test creating adaptive card with invalid content."""
        bot = OhlalaBot()
        invalid_card = "not a dict"

        # Should return error card
        attachment = bot._create_adaptive_card_attachment(invalid_card)  # type: ignore[arg-type]

        assert attachment is not None
        # Should be an error card
        assert "Error creating card" in str(attachment.content)

    def test_apply_brand_colors(self) -> None:
        """Test applying brand colors to card."""
        bot = OhlalaBot()
        card = {
            "type": "AdaptiveCard",
            "body": [
                {
                    "type": "Chart.Line",
                    "data": [
                        {"name": "Series1"},
                        {"name": "Series2"},
                    ],
                }
            ],
        }

        bot._apply_brand_colors(card)

        # Should add colors to chart data
        data = card["body"][0]["data"]
        assert "color" in data[0]
        assert "color" in data[1]
        assert data[0]["color"] == "#FF9900"  # AWS Orange
        assert data[1]["color"] == "#232F3E"  # AWS Dark Blue

    def test_apply_brand_colors_no_data(self) -> None:
        """Test applying brand colors to card without chart data."""
        bot = OhlalaBot()
        card = {
            "type": "AdaptiveCard",
            "body": [{"type": "TextBlock", "text": "No charts"}],
        }

        # Should not raise error
        bot._apply_brand_colors(card)

    @pytest.mark.asyncio
    async def test_create_invoke_response_success(self) -> None:
        """Test creating successful invoke response."""
        bot = OhlalaBot()

        response = await bot._create_invoke_response(success=True)

        assert response["status"] == 200
        assert "message" in response["body"]
        assert "success" in response["body"]["message"].lower()

    @pytest.mark.asyncio
    async def test_create_invoke_response_failure(self) -> None:
        """Test creating failure invoke response."""
        bot = OhlalaBot()

        response = await bot._create_invoke_response(success=False)

        assert response["status"] == 500
        assert "message" in response["body"]
        assert "failed" in response["body"]["message"].lower()

    # Integration tests

    @pytest.mark.asyncio
    async def test_full_message_flow(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test complete message handling flow."""
        bot = OhlalaBot()

        with patch.object(
            bot.message_handler, "on_message_activity", new=AsyncMock()
        ) as mock_handler:
            await bot.on_message_activity(mock_turn_context)

            # Verify handler was called with correct context
            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0][0]
            assert call_args == mock_turn_context

    @pytest.mark.asyncio
    async def test_full_card_action_flow(
        self,
        mock_turn_context: Mock,
    ) -> None:
        """Test complete card action handling flow."""
        bot = OhlalaBot()
        mock_turn_context.activity.value = {"action": "approve"}

        with patch.object(
            bot.card_handler,
            "handle_card_action",
            new=AsyncMock(return_value={"status": 200}),
        ) as mock_handler:
            result = await bot.on_invoke_activity(mock_turn_context)

            # Verify handler was called and returned result
            mock_handler.assert_called_once_with(mock_turn_context)
            assert result["status"] == 200
