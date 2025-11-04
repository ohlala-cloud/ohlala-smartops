"""Unit tests for conversation models.

This module tests the Pydantic models for conversation state management.
"""

from datetime import UTC, datetime

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
    """Test UserInfo model."""

    def test_create_valid_user(self):
        """Test creating a valid user."""
        user = UserInfo(
            id="user123",
            name="Test User",
            email="test@example.com",
            role=UserRole.VIEWER,
            locale="en",
            tenant_id="tenant123",
        )

        assert user.id == "user123"
        assert user.name == "Test User"
        assert user.email == "test@example.com"
        assert user.role == UserRole.VIEWER
        assert user.locale == "en"
        assert user.tenant_id == "tenant123"

    def test_locale_normalization(self):
        """Test locale is normalized to lowercase 2-letter code."""
        user = UserInfo(
            id="user123",
            name="Test User",
            tenant_id="tenant123",
            locale="en-US",
        )

        assert user.locale == "en"

    def test_unsupported_locale_defaults_to_en(self):
        """Test unsupported locale defaults to English."""
        user = UserInfo(
            id="user123",
            name="Test User",
            tenant_id="tenant123",
            locale="ja",  # Japanese not supported
        )

        assert user.locale == "en"

    def test_supported_locales(self):
        """Test all supported locales."""
        for locale in ["en", "fr", "de", "es"]:
            user = UserInfo(
                id="user123",
                name="Test User",
                tenant_id="tenant123",
                locale=locale,
            )
            assert user.locale == locale

    def test_missing_required_fields(self):
        """Test validation error when required fields are missing."""
        with pytest.raises(ValidationError):
            UserInfo(name="Test User")


class TestTeamInfo:
    """Test TeamInfo model."""

    def test_create_valid_team(self):
        """Test creating a valid team."""
        team = TeamInfo(
            id="team123",
            name="Test Team",
            tenant_id="tenant123",
        )

        assert team.id == "team123"
        assert team.name == "Test Team"
        assert team.tenant_id == "tenant123"


class TestChannelInfo:
    """Test ChannelInfo model."""

    def test_create_valid_channel(self):
        """Test creating a valid channel."""
        channel = ChannelInfo(
            id="channel123",
            name="Test Channel",
        )

        assert channel.id == "channel123"
        assert channel.name == "Test Channel"


class TestConversationContext:
    """Test ConversationContext model."""

    def test_create_personal_conversation(self):
        """Test creating a personal conversation context."""
        user = UserInfo(
            id="user123",
            name="Test User",
            tenant_id="tenant123",
        )

        context = ConversationContext(
            conversation_id="conv123",
            conversation_type=ConversationType.PERSONAL,
            user=user,
            service_url="https://teams.microsoft.com",
        )

        assert context.conversation_id == "conv123"
        assert context.conversation_type == ConversationType.PERSONAL
        assert context.user == user
        assert context.team is None
        assert context.channel is None

    def test_create_channel_conversation(self):
        """Test creating a channel conversation context."""
        user = UserInfo(
            id="user123",
            name="Test User",
            tenant_id="tenant123",
        )
        team = TeamInfo(
            id="team123",
            name="Test Team",
            tenant_id="tenant123",
        )
        channel = ChannelInfo(
            id="channel123",
            name="Test Channel",
        )

        context = ConversationContext(
            conversation_id="conv123",
            conversation_type=ConversationType.CHANNEL,
            user=user,
            team=team,
            channel=channel,
            service_url="https://teams.microsoft.com",
        )

        assert context.team == team
        assert context.channel == channel

    def test_update_timestamp(self):
        """Test updating the conversation timestamp."""
        user = UserInfo(
            id="user123",
            name="Test User",
            tenant_id="tenant123",
        )
        context = ConversationContext(
            conversation_id="conv123",
            conversation_type=ConversationType.PERSONAL,
            user=user,
            service_url="https://teams.microsoft.com",
        )

        original_time = context.updated_at
        context.update_timestamp()

        assert context.updated_at > original_time


class TestConversationState:
    """Test ConversationState model."""

    def test_create_basic_state(self):
        """Test creating a basic conversation state."""
        state = ConversationState(
            conversation_id="conv123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        assert state.conversation_id == "conv123"
        assert state.pending_command is None
        assert state.turn_count == 0
        assert len(state.history) == 0
        assert len(state.messages) == 0
        assert state.iteration == 0

    def test_add_to_history(self):
        """Test adding messages to history."""
        state = ConversationState(
            conversation_id="conv123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        state.add_to_history("user", "Hello")
        state.add_to_history("assistant", "Hi there")

        assert len(state.history) == 2
        assert state.history[0]["role"] == "user"
        assert state.history[0]["content"] == "Hello"
        assert state.history[1]["role"] == "assistant"
        assert state.history[1]["content"] == "Hi there"
        assert state.turn_count == 2

    def test_history_limited_to_10(self):
        """Test history is limited to last 10 turns."""
        state = ConversationState(
            conversation_id="conv123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        # Add 15 messages
        for i in range(15):
            state.add_to_history("user", f"Message {i}")

        assert len(state.history) == 10
        # Should keep the last 10 messages
        assert state.history[0]["content"] == "Message 5"
        assert state.history[-1]["content"] == "Message 14"

    def test_clear_pending(self):
        """Test clearing pending command and approval."""
        state = ConversationState(
            conversation_id="conv123",
            pending_command="test command",
            pending_approval_id="approval123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        state.clear_pending()

        assert state.pending_command is None
        assert state.pending_approval_id is None

    def test_store_conversation_for_resume(self):
        """Test storing conversation for resume."""
        state = ConversationState(
            conversation_id="conv123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        messages = [{"role": "user", "content": "test"}]
        available_tools = ["list-instances", "send-command"]
        pending_tool_uses = [{"id": "tool1", "name": "list-instances"}]
        instance_platforms = {"i-123": "linux", "i-456": "windows"}

        state.store_conversation_for_resume(
            messages=messages,
            iteration=3,
            available_tools=available_tools,
            pending_tool_uses=pending_tool_uses,
            original_prompt="Original user prompt",
            instance_platforms=instance_platforms,
        )

        assert state.messages == messages
        assert state.iteration == 3
        assert state.available_tools == available_tools
        assert state.pending_tool_uses == pending_tool_uses
        assert state.original_prompt == "Original user prompt"
        assert state.instance_platforms == instance_platforms

    def test_store_conversation_infers_prompt(self):
        """Test storing conversation infers original prompt from messages."""
        state = ConversationState(
            conversation_id="conv123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        messages = [{"role": "user", "content": "Inferred prompt"}]

        state.store_conversation_for_resume(
            messages=messages,
            iteration=1,
            available_tools=[],
            pending_tool_uses=[],
        )

        assert state.original_prompt == "Inferred prompt"

    def test_store_conversation_with_empty_messages(self):
        """Test storing conversation with empty messages."""
        state = ConversationState(
            conversation_id="conv123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        state.store_conversation_for_resume(
            messages=[],
            iteration=1,
            available_tools=[],
            pending_tool_uses=[],
        )

        assert state.original_prompt == ""
        assert state.messages == []

    def test_default_values(self):
        """Test default values are set correctly."""
        state = ConversationState(
            conversation_id="conv123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        assert isinstance(state.history, list)
        assert isinstance(state.messages, list)
        assert isinstance(state.available_tools, list)
        assert isinstance(state.pending_tool_uses, list)
        assert isinstance(state.pending_tool_inputs, dict)
        assert isinstance(state.instance_platforms, dict)
        assert isinstance(state.created_at, datetime)
        assert isinstance(state.updated_at, datetime)
        assert state.created_at.tzinfo == UTC
        assert state.updated_at.tzinfo == UTC

    def test_pending_tool_inputs_storage(self):
        """Test storing and retrieving pending tool inputs."""
        state = ConversationState(
            conversation_id="conv123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        # Store tool inputs
        state.pending_tool_inputs["tool1"] = {"InstanceIds": ["i-123"]}
        state.pending_tool_inputs["tool2"] = {"Commands": ["echo test"]}

        assert "tool1" in state.pending_tool_inputs
        assert state.pending_tool_inputs["tool1"]["InstanceIds"] == ["i-123"]
        assert "tool2" in state.pending_tool_inputs

    def test_iteration_validation(self):
        """Test iteration must be non-negative."""
        with pytest.raises(ValidationError):
            ConversationState(
                conversation_id="conv123",
                iteration=-1,
                original_prompt=None,
                handled_by_ssm_tracker=False,
            )

    def test_turn_count_validation(self):
        """Test turn_count must be non-negative."""
        with pytest.raises(ValidationError):
            ConversationState(
                conversation_id="conv123",
                turn_count=-1,
                iteration=0,
                original_prompt=None,
                handled_by_ssm_tracker=False,
            )
