"""Tests for conversation context models."""

import pytest
from pydantic import ValidationError

from ohlala_smartops.models.conversation import (
    ChannelInfo,
    ConversationContext,
    ConversationState,
    ConversationType,
    TeamInfo,
    UserInfo,
    UserRole,
)


class TestUserInfo:
    """Test suite for UserInfo model."""

    def test_user_info_creation(self) -> None:
        """Test creating a UserInfo instance."""
        user = UserInfo(
            id="user123",
            name="John Doe",
            email="john@example.com",
            role=UserRole.OPERATOR,
            locale="en",
            tenant_id="tenant123",
        )

        assert user.id == "user123"
        assert user.name == "John Doe"
        assert user.email == "john@example.com"
        assert user.role == UserRole.OPERATOR
        assert user.locale == "en"
        assert user.tenant_id == "tenant123"

    def test_user_info_default_role(self) -> None:
        """Test UserInfo with default role."""
        user = UserInfo(
            id="user123",
            name="Jane Doe",
            tenant_id="tenant123",
        )

        assert user.role == UserRole.VIEWER

    def test_user_info_locale_validation(self) -> None:
        """Test locale validation and normalization."""
        user = UserInfo(
            id="user123",
            name="User",
            tenant_id="tenant123",
            locale="fr-FR",
        )
        assert user.locale == "fr"

        # Unsupported locale defaults to en
        user2 = UserInfo(
            id="user123",
            name="User",
            tenant_id="tenant123",
            locale="ja",
        )
        assert user2.locale == "en"

    def test_user_info_validation_errors(self) -> None:
        """Test UserInfo validation errors."""
        with pytest.raises(ValidationError):
            UserInfo(id="", name="User", tenant_id="tenant123")

        with pytest.raises(ValidationError):
            UserInfo(id="user123", name="", tenant_id="tenant123")


class TestTeamInfo:
    """Test suite for TeamInfo model."""

    def test_team_info_creation(self) -> None:
        """Test creating a TeamInfo instance."""
        team = TeamInfo(
            id="team123",
            name="Engineering Team",
            tenant_id="tenant123",
        )

        assert team.id == "team123"
        assert team.name == "Engineering Team"
        assert team.tenant_id == "tenant123"


class TestChannelInfo:
    """Test suite for ChannelInfo model."""

    def test_channel_info_creation(self) -> None:
        """Test creating a ChannelInfo instance."""
        channel = ChannelInfo(
            id="channel123",
            name="General",
        )

        assert channel.id == "channel123"
        assert channel.name == "General"


class TestConversationContext:
    """Test suite for ConversationContext model."""

    @pytest.fixture
    def user_info(self) -> UserInfo:
        """Provide a sample UserInfo for testing."""
        return UserInfo(
            id="user123",
            name="Test User",
            tenant_id="tenant123",
        )

    def test_conversation_context_personal(self, user_info: UserInfo) -> None:
        """Test creating a personal conversation context."""
        context = ConversationContext(
            conversation_id="conv123",
            conversation_type=ConversationType.PERSONAL,
            user=user_info,
            service_url="https://smba.trafficmanager.net/amer/",
        )

        assert context.conversation_id == "conv123"
        assert context.conversation_type == ConversationType.PERSONAL
        assert context.user == user_info
        assert context.team is None
        assert context.channel is None

    def test_conversation_context_channel(self, user_info: UserInfo) -> None:
        """Test creating a channel conversation context."""
        team = TeamInfo(id="team123", name="Team", tenant_id="tenant123")
        channel = ChannelInfo(id="channel123", name="General")

        context = ConversationContext(
            conversation_id="conv123",
            conversation_type=ConversationType.CHANNEL,
            user=user_info,
            team=team,
            channel=channel,
            service_url="https://smba.trafficmanager.net/amer/",
        )

        assert context.team == team
        assert context.channel == channel

    def test_update_timestamp(self, user_info: UserInfo) -> None:
        """Test updating the timestamp."""
        context = ConversationContext(
            conversation_id="conv123",
            conversation_type=ConversationType.PERSONAL,
            user=user_info,
            service_url="https://example.com",
        )

        original_timestamp = context.updated_at
        context.update_timestamp()

        assert context.updated_at > original_timestamp


class TestConversationState:
    """Test suite for ConversationState model."""

    def test_conversation_state_creation(self) -> None:
        """Test creating a ConversationState instance."""
        state = ConversationState(
            conversation_id="conv123",
        )

        assert state.conversation_id == "conv123"
        assert state.pending_command is None
        assert state.pending_approval_id is None
        assert state.turn_count == 0
        assert len(state.history) == 0

    def test_add_to_history(self) -> None:
        """Test adding messages to conversation history."""
        state = ConversationState(conversation_id="conv123")

        state.add_to_history("user", "Hello")
        assert len(state.history) == 1
        assert state.history[0]["role"] == "user"
        assert state.history[0]["content"] == "Hello"
        assert state.turn_count == 1

        state.add_to_history("assistant", "Hi there!")
        assert len(state.history) == 2
        assert state.turn_count == 2

    def test_history_limit(self) -> None:
        """Test that history is limited to 10 turns."""
        state = ConversationState(conversation_id="conv123")

        # Add 15 messages
        for i in range(15):
            state.add_to_history("user", f"Message {i}")

        # Only last 10 should remain
        assert len(state.history) == 10
        assert state.history[0]["content"] == "Message 5"
        assert state.history[-1]["content"] == "Message 14"

    def test_clear_pending(self) -> None:
        """Test clearing pending command and approval."""
        state = ConversationState(
            conversation_id="conv123",
            pending_command="start instance",
            pending_approval_id="approval123",
        )

        assert state.pending_command is not None
        assert state.pending_approval_id is not None

        state.clear_pending()

        assert state.pending_command is None
        assert state.pending_approval_id is None
