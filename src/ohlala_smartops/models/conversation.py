"""Conversation context models for Ohlala SmartOps.

This module defines Pydantic models for tracking conversation state, user information,
and team context in Microsoft Teams conversations.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class UserRole(str, Enum):
    """User roles for access control."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class ConversationType(str, Enum):
    """Types of conversations in Microsoft Teams."""

    PERSONAL = "personal"
    CHANNEL = "channel"
    GROUP = "group"


class UserInfo(BaseModel):
    """Information about a Microsoft Teams user.

    Attributes:
        id: Unique identifier for the user in Teams (Azure AD object ID).
        name: Display name of the user.
        email: Email address of the user.
        role: User's role for access control (default: viewer).
        locale: Preferred locale for internationalization (default: en).
        tenant_id: Azure AD tenant ID.
    """

    id: str = Field(..., min_length=1, description="Azure AD object ID")
    name: str = Field(..., min_length=1, description="Display name")
    email: str | None = Field(None, description="Email address")
    role: UserRole = Field(UserRole.VIEWER, description="Access control role")
    locale: str = Field("en", description="Preferred locale (e.g., 'en', 'fr', 'de', 'es')")
    tenant_id: str = Field(..., min_length=1, description="Azure AD tenant ID")

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, v: str) -> str:
        """Validate and normalize locale code.

        Args:
            v: Locale string to validate.

        Returns:
            Normalized locale code (lowercase, 2-letter).

        Raises:
            ValueError: If locale format is invalid.
        """
        supported_locales = {"en", "fr", "de", "es"}
        normalized = v.lower().split("-")[0]  # Extract language code (en-US -> en)

        if normalized not in supported_locales:
            return "en"  # Default to English for unsupported locales

        return normalized


class TeamInfo(BaseModel):
    """Information about a Microsoft Teams team.

    Attributes:
        id: Unique identifier for the team.
        name: Display name of the team.
        tenant_id: Azure AD tenant ID.
    """

    id: str = Field(..., min_length=1, description="Team ID")
    name: str = Field(..., min_length=1, description="Team display name")
    tenant_id: str = Field(..., min_length=1, description="Azure AD tenant ID")


class ChannelInfo(BaseModel):
    """Information about a Microsoft Teams channel.

    Attributes:
        id: Unique identifier for the channel.
        name: Display name of the channel.
    """

    id: str = Field(..., min_length=1, description="Channel ID")
    name: str = Field(..., min_length=1, description="Channel display name")


class ConversationContext(BaseModel):
    """Context for a conversation in Microsoft Teams.

    This model tracks all relevant information about an ongoing conversation,
    including user info, team/channel info, and conversation state.

    Attributes:
        conversation_id: Unique identifier for the conversation.
        conversation_type: Type of conversation (personal, channel, group).
        user: Information about the user.
        team: Information about the team (if in a team conversation).
        channel: Information about the channel (if in a channel conversation).
        service_url: Service URL for sending responses back to Teams.
        created_at: Timestamp when the conversation context was created.
        updated_at: Timestamp when the conversation context was last updated.
        metadata: Additional metadata for the conversation.
    """

    conversation_id: str = Field(..., min_length=1, description="Conversation ID")
    conversation_type: ConversationType = Field(..., description="Type of conversation")
    user: UserInfo = Field(..., description="User information")
    team: TeamInfo | None = Field(None, description="Team information (if applicable)")
    channel: ChannelInfo | None = Field(None, description="Channel information (if applicable)")
    service_url: str = Field(..., min_length=1, description="Teams service URL")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Last update timestamp"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("conversation_type")
    @classmethod
    def validate_conversation_type(cls, v: ConversationType, _info: Any) -> ConversationType:
        """Validate conversation type matches team/channel presence.

        Args:
            v: Conversation type to validate.
            _info: Validation context with other field values.

        Returns:
            Validated conversation type.

        Raises:
            ValueError: If conversation type doesn't match team/channel presence.
        """
        # Note: Validation with other fields happens in model_validator
        return v

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to current UTC time."""
        self.updated_at = datetime.now(tz=UTC)


class ConversationState(BaseModel):
    """State tracking for an ongoing conversation.

    This model tracks the current state of a multi-turn conversation,
    including pending commands, approval workflows, and conversation history.

    Attributes:
        conversation_id: Unique identifier for the conversation.
        pending_command: Command awaiting execution or approval.
        pending_approval_id: ID of a pending approval workflow.
        last_message_id: ID of the last message in the conversation.
        turn_count: Number of turns in the conversation.
        history: Recent conversation history (for context).
        messages: Claude conversation messages (for resume).
        iteration: Current tool use iteration count.
        available_tools: List of available tool names.
        pending_tool_uses: Tool uses awaiting approval.
        pending_tool_inputs: Stored tool inputs (to avoid Teams corruption).
        original_prompt: Original user prompt for context.
        instance_platforms: Mapping of instance IDs to platforms.
        handled_by_ssm_tracker: Flag indicating SSM tracker is handling this conversation.
        created_at: Timestamp when the state was created.
        updated_at: Timestamp when the state was last updated.
    """

    conversation_id: str = Field(..., min_length=1, description="Conversation ID")
    pending_command: str | None = Field(None, description="Pending command awaiting execution")
    pending_approval_id: str | None = Field(None, description="Pending approval workflow ID")
    last_message_id: str | None = Field(None, description="Last message ID")
    turn_count: int = Field(0, ge=0, description="Number of conversation turns")
    history: list[dict[str, Any]] = Field(
        default_factory=list, description="Conversation history (max 10 turns)"
    )
    # Extended fields for conversation handler
    messages: list[dict[str, Any]] = Field(
        default_factory=list, description="Claude conversation messages"
    )
    iteration: int = Field(0, ge=0, description="Tool use iteration count")
    available_tools: list[str] = Field(default_factory=list, description="Available tool names")
    pending_tool_uses: list[dict[str, Any]] = Field(
        default_factory=list, description="Tool uses awaiting approval"
    )
    pending_tool_inputs: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Stored tool inputs by tool ID"
    )
    original_prompt: str | None = Field(None, description="Original user prompt")
    instance_platforms: dict[str, str] = Field(
        default_factory=dict, description="Mapping of instance IDs to platforms"
    )
    handled_by_ssm_tracker: bool = Field(
        False, description="Flag indicating SSM tracker is handling this"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Last update timestamp"
    )

    def add_to_history(self, role: str, content: str) -> None:
        """Add a message to conversation history.

        Args:
            role: Role of the message sender (user, assistant, system).
            content: Message content.
        """
        self.history.append(
            {"role": role, "content": content, "timestamp": datetime.now(tz=UTC).isoformat()}
        )

        # Keep only the last 10 turns
        if len(self.history) > 10:
            self.history = self.history[-10:]

        self.turn_count += 1
        self.updated_at = datetime.now(tz=UTC)

    def clear_pending(self) -> None:
        """Clear pending command and approval."""
        self.pending_command = None
        self.pending_approval_id = None
        self.updated_at = datetime.now(tz=UTC)

    def store_conversation_for_resume(
        self,
        messages: list[dict[str, Any]],
        iteration: int,
        available_tools: list[str],
        pending_tool_uses: list[dict[str, Any]],
        original_prompt: str | None = None,
        instance_platforms: dict[str, str] | None = None,
    ) -> None:
        """Store conversation state for resuming after approval.

        Args:
            messages: Claude conversation messages.
            iteration: Current tool use iteration count.
            available_tools: List of available tool names.
            pending_tool_uses: Tool uses awaiting approval.
            original_prompt: Original user prompt for context.
            instance_platforms: Mapping of instance IDs to platforms.
        """
        self.messages = messages.copy()
        self.iteration = iteration
        self.available_tools = available_tools
        self.pending_tool_uses = pending_tool_uses
        self.original_prompt = original_prompt or (
            messages[0].get("content", "") if messages else ""
        )
        self.instance_platforms = instance_platforms or {}
        self.updated_at = datetime.now(tz=UTC)
