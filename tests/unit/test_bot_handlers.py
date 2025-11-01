"""Tests for bot activity handlers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ohlala_smartops.bot.handlers import OhlalaActivityHandler
from ohlala_smartops.models import ConversationType, UserRole


@pytest.fixture
def handler() -> OhlalaActivityHandler:
    """Create a handler instance."""
    return OhlalaActivityHandler()


@pytest.fixture
def mock_turn_context() -> MagicMock:
    """Create a mock TurnContext."""
    context = MagicMock()
    context.send_activity = AsyncMock()

    # Mock activity
    context.activity = MagicMock()
    context.activity.text = "test message"
    context.activity.conversation = MagicMock()
    context.activity.conversation.id = "conv123"
    context.activity.conversation.tenant_id = "tenant123"
    context.activity.conversation.is_group = False
    context.activity.service_url = "https://smba.trafficmanager.net/amer/"
    context.activity.recipient = MagicMock()
    context.activity.recipient.id = "bot123"
    context.activity.channel_data = None
    context.activity.entities = None

    # Mock user
    context.activity.from_property = MagicMock()
    context.activity.from_property.id = "user123"
    context.activity.from_property.aad_object_id = "aad-user-123"
    context.activity.from_property.name = "Test User"

    return context


class TestOnMessageActivity:
    """Test suite for on_message_activity handler."""

    @pytest.mark.asyncio
    async def test_handle_help_command(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling help command."""
        mock_turn_context.activity.text = "help"

        await handler.on_message_activity(mock_turn_context)

        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "Ohlala SmartOps - Help" in call_args
        assert "EC2 Commands" in call_args

    @pytest.mark.asyncio
    async def test_handle_help_command_with_slash(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling /help command."""
        mock_turn_context.activity.text = "/help"

        await handler.on_message_activity(mock_turn_context)

        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "Help" in call_args

    @pytest.mark.asyncio
    async def test_handle_health_command(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling health command."""
        mock_turn_context.activity.text = "health"

        await handler.on_message_activity(mock_turn_context)

        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "Bot Health Status" in call_args
        assert "systems operational" in call_args

    @pytest.mark.asyncio
    async def test_handle_status_command(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling status command."""
        mock_turn_context.activity.text = "status"

        await handler.on_message_activity(mock_turn_context)

        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "Bot Health Status" in call_args

    @pytest.mark.asyncio
    async def test_handle_regular_message(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling regular message."""
        mock_turn_context.activity.text = "list instances"

        await handler.on_message_activity(mock_turn_context)

        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "processing your request" in call_args.lower()

    @pytest.mark.asyncio
    async def test_handle_message_with_mentions(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling message with @mentions."""
        mock_turn_context.activity.text = "@bot list instances"
        mock_turn_context.activity.entities = [
            MagicMock(type="mention", properties={"text": "@bot"})
        ]

        await handler.on_message_activity(mock_turn_context)

        # Should still process the message
        assert mock_turn_context.send_activity.called

    @pytest.mark.asyncio
    async def test_handle_empty_message(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling empty message."""
        mock_turn_context.activity.text = None

        await handler.on_message_activity(mock_turn_context)

        # Should still respond
        assert mock_turn_context.send_activity.called

    @pytest.mark.asyncio
    async def test_handle_message_error(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test error handling in message processing."""
        mock_turn_context.send_activity.side_effect = [
            Exception("Send failed"),
            None,  # Second call should succeed for error message
        ]

        await handler.on_message_activity(mock_turn_context)

        # Should send error message
        assert mock_turn_context.send_activity.call_count == 2
        error_call = mock_turn_context.send_activity.call_args_list[1][0][0]
        assert "error" in error_call.lower()


class TestOnConversationUpdateActivity:
    """Test suite for on_conversation_update_activity handler."""

    @pytest.mark.asyncio
    async def test_handle_member_added(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling member added to conversation."""
        new_member = MagicMock()
        new_member.id = "new-user-123"
        new_member.name = "New User"

        mock_turn_context.activity.members_added = [new_member]
        mock_turn_context.activity.members_removed = None

        await handler.on_conversation_update_activity(mock_turn_context)

        # Should send welcome message
        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "Hello New User" in call_args
        assert "Ohlala SmartOps" in call_args

    @pytest.mark.asyncio
    async def test_handle_bot_added_to_conversation(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test bot being added (should not greet itself)."""
        bot_member = MagicMock()
        bot_member.id = "bot123"  # Same as recipient.id
        bot_member.name = "Ohlala Bot"

        mock_turn_context.activity.members_added = [bot_member]
        mock_turn_context.activity.members_removed = None

        await handler.on_conversation_update_activity(mock_turn_context)

        # Should not send welcome message to itself
        mock_turn_context.send_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_member_removed(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling member removed from conversation."""
        removed_member = MagicMock()
        removed_member.id = "removed-user-123"
        removed_member.name = "Removed User"

        mock_turn_context.activity.members_added = None
        mock_turn_context.activity.members_removed = [removed_member]

        # Should handle without error (just logs)
        await handler.on_conversation_update_activity(mock_turn_context)

        mock_turn_context.send_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_conversation_update_error(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test error handling in conversation update."""
        mock_turn_context.activity.members_added = None
        mock_turn_context.activity.members_removed = None
        # Force an error
        mock_turn_context.activity.recipient = None

        # Should handle error gracefully
        await handler.on_conversation_update_activity(mock_turn_context)


class TestOnInvokeActivity:
    """Test suite for on_invoke_activity handler."""

    @pytest.mark.asyncio
    async def test_handle_adaptive_card_action(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling adaptive card action."""
        mock_turn_context.activity.name = "adaptiveCard/action"
        mock_turn_context.activity.value = {"action": "approve", "id": "req123"}

        result = await handler.on_invoke_activity(mock_turn_context)

        assert result["status"] == 200
        assert "message" in result["body"]
        mock_turn_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_unknown_invoke(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling unknown invoke activity."""
        mock_turn_context.activity.name = "unknown/action"
        mock_turn_context.activity.value = {}

        result = await handler.on_invoke_activity(mock_turn_context)

        assert result["status"] == 200
        assert "message" in result["body"]

    @pytest.mark.asyncio
    async def test_handle_invoke_error(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test error handling in invoke activity."""
        mock_turn_context.activity.name = "adaptiveCard/action"
        mock_turn_context.activity.value = None  # Will cause error
        mock_turn_context.send_activity.side_effect = Exception("Send failed")

        result = await handler.on_invoke_activity(mock_turn_context)

        assert result["status"] == 500
        assert "error" in result["body"]


class TestOtherHandlers:
    """Test suite for other activity handlers."""

    @pytest.mark.asyncio
    async def test_on_teams_signin_verify_state(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test Teams signin verification handler."""
        # Should complete without error
        await handler.on_teams_signin_verify_state(mock_turn_context)

    @pytest.mark.asyncio
    async def test_on_message_reaction_activity(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test message reaction handler."""
        # Should complete without error
        await handler.on_message_reaction_activity(mock_turn_context)


class TestHelperMethods:
    """Test suite for helper methods."""

    @pytest.mark.asyncio
    async def test_create_conversation_context_personal(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test creating conversation context for personal chat."""
        context = await handler._create_conversation_context(mock_turn_context)

        assert context.conversation_id == "conv123"
        assert context.conversation_type == ConversationType.PERSONAL
        assert context.user.id == "aad-user-123"
        assert context.user.name == "Test User"
        assert context.user.role == UserRole.OPERATOR
        assert context.service_url == "https://smba.trafficmanager.net/amer/"

    @pytest.mark.asyncio
    async def test_create_conversation_context_channel(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test creating conversation context for channel."""
        mock_turn_context.activity.channel_data = {"team": {"id": "team123"}}

        context = await handler._create_conversation_context(mock_turn_context)

        assert context.conversation_type == ConversationType.CHANNEL

    @pytest.mark.asyncio
    async def test_create_conversation_context_group(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test creating conversation context for group chat."""
        # Set channel_data without team key to trigger group logic
        mock_turn_context.activity.channel_data = {"otherData": "value"}
        mock_turn_context.activity.conversation.is_group = True

        context = await handler._create_conversation_context(mock_turn_context)

        # The implementation checks for team first, then is_group
        # With no team key and is_group=True, it should be GROUP
        assert context.conversation_type == ConversationType.GROUP

    @pytest.mark.asyncio
    async def test_create_conversation_context_no_aad_id(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test creating context when AAD object ID is not available."""
        mock_turn_context.activity.from_property.aad_object_id = None

        context = await handler._create_conversation_context(mock_turn_context)

        # Should fall back to regular user ID
        assert context.user.id == "user123"

    def test_remove_mentions_no_entities(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test removing mentions when no entities present."""
        text = "list instances"
        mock_turn_context.activity.entities = None

        result = handler._remove_mentions(text, mock_turn_context.activity)

        assert result == "list instances"

    def test_remove_mentions_with_entities(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test removing mentions from text."""
        text = "@bot list instances"
        mock_turn_context.activity.entities = [
            MagicMock(type="mention", properties={"text": "@bot"})
        ]

        result = handler._remove_mentions(text, mock_turn_context.activity)

        assert result == "list instances"

    def test_remove_mentions_non_mention_entity(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test with non-mention entities."""
        text = "list instances"
        mock_turn_context.activity.entities = [MagicMock(type="clientInfo", properties={})]

        result = handler._remove_mentions(text, mock_turn_context.activity)

        assert result == "list instances"

    @pytest.mark.asyncio
    async def test_send_welcome_message(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test sending welcome message."""
        member = MagicMock()
        member.name = "New User"

        await handler._send_welcome_message(mock_turn_context, member)

        mock_turn_context.send_activity.assert_called_once()
        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "Hello New User" in call_args
        assert "Ohlala SmartOps" in call_args
        assert "What I can do" in call_args

    @pytest.mark.asyncio
    async def test_handle_help_command_content(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test help command message content."""
        await handler._handle_help_command(mock_turn_context)

        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "EC2 Commands" in call_args
        assert "Monitoring" in call_args
        assert "Cost Management" in call_args
        assert "SSM" in call_args

    @pytest.mark.asyncio
    async def test_handle_health_command_content(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test health command message content."""
        await handler._handle_health_command(mock_turn_context)

        call_args = mock_turn_context.send_activity.call_args[0][0]
        assert "Bot Health Status" in call_args
        assert "Bot Framework" in call_args
        assert "AWS Connection" in call_args

    @pytest.mark.asyncio
    async def test_handle_card_action(
        self, handler: OhlalaActivityHandler, mock_turn_context: MagicMock
    ) -> None:
        """Test handling card action."""
        mock_turn_context.activity.value = {"action": "approve", "id": "123"}

        result = await handler._handle_card_action(mock_turn_context)

        assert result["status"] == 200
        assert "message" in result["body"]
        mock_turn_context.send_activity.assert_called_once()
