"""Bot Framework message models for Ohlala SmartOps.

This module defines Pydantic models for Microsoft Teams Bot Framework messages,
including Activity, ChannelData, and related schemas.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ActivityType(str, Enum):
    """Types of Bot Framework activities."""

    MESSAGE = "message"
    CONVERSATION_UPDATE = "conversationUpdate"
    INVOKE = "invoke"
    EVENT = "event"
    MESSAGE_REACTION = "messageReaction"


class AttachmentType(str, Enum):
    """Types of attachments in Bot Framework messages."""

    ADAPTIVE_CARD = "application/vnd.microsoft.card.adaptive"
    HERO_CARD = "application/vnd.microsoft.card.hero"
    THUMBNAIL_CARD = "application/vnd.microsoft.card.thumbnail"


class ChannelAccount(BaseModel):
    """Represents a channel account (user or bot).

    Attributes:
        id: Unique identifier for the account.
        name: Display name of the account.
        aad_object_id: Azure AD object ID (for users).
        role: Role of the account (e.g., 'user', 'bot').
    """

    id: str = Field(..., min_length=1, description="Account ID")
    name: str | None = Field(None, description="Display name")
    aad_object_id: str | None = Field(None, alias="aadObjectId", description="Azure AD object ID")
    role: str | None = Field(None, description="Account role")


class ConversationAccount(BaseModel):
    """Represents a conversation.

    Attributes:
        id: Unique identifier for the conversation.
        name: Display name of the conversation.
        conversation_type: Type of conversation (e.g., 'personal', 'channel').
        tenant_id: Azure AD tenant ID.
        is_group: Whether this is a group conversation.
    """

    id: str = Field(..., min_length=1, description="Conversation ID")
    name: str | None = Field(None, description="Conversation name")
    conversation_type: str | None = Field(
        None, alias="conversationType", description="Conversation type"
    )
    tenant_id: str | None = Field(None, alias="tenantId", description="Azure AD tenant ID")
    is_group: bool | None = Field(None, alias="isGroup", description="Is group conversation")


class TeamsChannelData(BaseModel):
    """Teams-specific channel data.

    Attributes:
        team: Team information.
        channel: Channel information.
        tenant: Tenant information.
        meeting: Meeting information (if in a meeting context).
    """

    team: dict[str, Any] | None = Field(None, description="Team information")
    channel: dict[str, Any] | None = Field(None, description="Channel information")
    tenant: dict[str, Any] | None = Field(None, description="Tenant information")
    meeting: dict[str, Any] | None = Field(None, description="Meeting information")


class Attachment(BaseModel):
    """Represents an attachment in a message.

    Attributes:
        content_type: MIME type of the attachment.
        content: Attachment content (card JSON, file data, etc.).
        content_url: URL to the attachment content.
        name: Name of the attachment.
    """

    content_type: str = Field(..., alias="contentType", description="MIME type")
    content: dict[str, Any] | None = Field(None, description="Attachment content")
    content_url: str | None = Field(None, alias="contentUrl", description="Content URL")
    name: str | None = Field(None, description="Attachment name")


class Entity(BaseModel):
    """Represents an entity mentioned in a message.

    Attributes:
        type: Type of entity (e.g., 'mention', 'clientInfo').
        mentioned: Information about the mentioned entity.
        text: Text representation of the entity.
    """

    type: str = Field(..., description="Entity type")
    mentioned: ChannelAccount | None = Field(None, description="Mentioned account")
    text: str | None = Field(None, description="Text representation")


class Activity(BaseModel):
    """Represents a Bot Framework activity (message, event, etc.).

    This is the core model for all Bot Framework interactions.

    Attributes:
        id: Unique identifier for the activity.
        type: Type of activity.
        timestamp: When the activity was sent.
        local_timestamp: Local timestamp at the client.
        service_url: Service URL for sending responses.
        channel_id: Channel where the activity occurred (e.g., 'msteams').
        from_account: Account that sent the activity.
        conversation: Conversation the activity belongs to.
        recipient: Account that received the activity (usually the bot).
        text: Text content of the activity.
        text_format: Format of the text (plain, markdown, xml).
        attachments: Attachments included with the activity.
        entities: Entities mentioned in the activity.
        channel_data: Channel-specific data.
        action: Action being invoked (for invoke activities).
        reply_to_id: ID of the activity this is a reply to.
        value: Value data for invoke activities.
    """

    id: str | None = Field(None, description="Activity ID")
    type: ActivityType = Field(..., description="Activity type")
    timestamp: datetime | None = Field(None, description="Timestamp")
    local_timestamp: datetime | None = Field(
        None, alias="localTimestamp", description="Local timestamp"
    )
    service_url: str = Field(..., alias="serviceUrl", min_length=1, description="Service URL")
    channel_id: str = Field(..., alias="channelId", description="Channel ID")
    from_account: ChannelAccount = Field(..., alias="from", description="Sender account")
    conversation: ConversationAccount = Field(..., description="Conversation")
    recipient: ChannelAccount = Field(..., description="Recipient account")
    text: str | None = Field(None, description="Message text")
    text_format: str | None = Field(None, alias="textFormat", description="Text format")
    attachments: list[Attachment] = Field(default_factory=list, description="Attachments")
    entities: list[Entity] = Field(default_factory=list, description="Entities")
    channel_data: TeamsChannelData | None = Field(
        None, alias="channelData", description="Channel-specific data"
    )
    action: str | None = Field(None, description="Action name (for invoke)")
    reply_to_id: str | None = Field(None, alias="replyToId", description="Reply to activity ID")
    value: dict[str, Any] | None = Field(None, description="Value data (for invoke)")

    def is_message(self) -> bool:
        """Check if this activity is a message.

        Returns:
            True if the activity type is MESSAGE.
        """
        return self.type == ActivityType.MESSAGE

    def is_invoke(self) -> bool:
        """Check if this activity is an invoke (e.g., card action).

        Returns:
            True if the activity type is INVOKE.
        """
        return self.type == ActivityType.INVOKE

    def is_conversation_update(self) -> bool:
        """Check if this activity is a conversation update.

        Returns:
            True if the activity type is CONVERSATION_UPDATE.
        """
        return self.type == ActivityType.CONVERSATION_UPDATE

    def get_text(self) -> str:
        """Get the text content of the activity, stripping HTML tags and mentions.

        Returns:
            Cleaned text content, or empty string if no text.
        """
        if not self.text:
            return ""

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", self.text)

        # Remove @mentions
        if self.entities:
            for entity in self.entities:
                if entity.type == "mention" and entity.text:
                    text = text.replace(entity.text, "").strip()

        return text.strip()

    def get_user_id(self) -> str:
        """Get the Azure AD object ID of the user who sent the activity.

        Returns:
            Azure AD object ID, or the from account ID if not available.
        """
        return self.from_account.aad_object_id or self.from_account.id


class InvokeResponse(BaseModel):
    """Response to an invoke activity.

    Attributes:
        status: HTTP status code.
        body: Response body (typically a card or value object).
    """

    status: int = Field(..., ge=100, le=599, description="HTTP status code")
    body: dict[str, Any] | None = Field(None, description="Response body")


class MessageResponse(BaseModel):
    """Response to send back to Teams.

    Attributes:
        type: Activity type (usually 'message').
        text: Text content of the response.
        attachments: Attachments to include in the response.
        channel_data: Channel-specific data.
    """

    type: ActivityType = Field(ActivityType.MESSAGE, description="Activity type")
    text: str | None = Field(None, description="Response text")
    attachments: list[Attachment] = Field(default_factory=list, description="Attachments")
    channel_data: dict[str, Any] | None = Field(
        None, alias="channelData", description="Channel data"
    )
