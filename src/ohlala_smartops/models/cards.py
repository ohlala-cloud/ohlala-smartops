"""Adaptive card interaction models for Ohlala SmartOps.

This module defines Pydantic models for Teams Adaptive Card interactions,
including card actions, submissions, and responses.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CardActionType(str, Enum):
    """Types of card actions."""

    SUBMIT = "Action.Submit"
    OPEN_URL = "Action.OpenUrl"
    SHOW_CARD = "Action.ShowCard"
    TOGGLE_VISIBILITY = "Action.ToggleVisibility"


class CardElementType(str, Enum):
    """Types of card elements."""

    TEXT_BLOCK = "TextBlock"
    IMAGE = "Image"
    CONTAINER = "Container"
    COLUMN_SET = "ColumnSet"
    FACT_SET = "FactSet"
    IMAGE_SET = "ImageSet"
    ACTION_SET = "ActionSet"
    INPUT_TEXT = "Input.Text"
    INPUT_NUMBER = "Input.Number"
    INPUT_DATE = "Input.Date"
    INPUT_TIME = "Input.Time"
    INPUT_TOGGLE = "Input.Toggle"
    INPUT_CHOICE_SET = "Input.ChoiceSet"


class CardColor(str, Enum):
    """Colors for card elements."""

    DEFAULT = "default"
    DARK = "dark"
    LIGHT = "light"
    ACCENT = "accent"
    GOOD = "good"
    WARNING = "warning"
    ATTENTION = "attention"


class CardSize(str, Enum):
    """Sizes for card elements."""

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    EXTRA_LARGE = "extraLarge"


class CardAction(BaseModel):
    """Represents an action in an Adaptive Card.

    Attributes:
        type: Type of action.
        title: Title/label for the action button.
        data: Data to submit with the action.
        url: URL to open (for OpenUrl actions).
        id: Unique identifier for the action.
    """

    type: CardActionType = Field(..., description="Action type")
    title: str = Field(..., min_length=1, description="Action title")
    data: dict[str, Any] | None = Field(None, description="Action data")
    url: str | None = Field(None, description="URL to open")
    id: str | None = Field(None, description="Action ID")


class CardFact(BaseModel):
    """Represents a fact in a FactSet.

    Attributes:
        title: Title of the fact (label).
        value: Value of the fact.
    """

    title: str = Field(..., description="Fact title")
    value: str = Field(..., description="Fact value")


class CardChoice(BaseModel):
    """Represents a choice in an Input.ChoiceSet.

    Attributes:
        title: Display title for the choice.
        value: Value to submit when chosen.
    """

    title: str = Field(..., description="Choice title")
    value: str = Field(..., description="Choice value")


class CardSubmission(BaseModel):
    """Data submitted from a card action.

    Attributes:
        action_id: ID of the action that was triggered.
        data: Data submitted with the action.
        user_id: ID of the user who submitted.
        conversation_id: ID of the conversation.
        timestamp: When the submission occurred.
    """

    action_id: str = Field(..., min_length=1, description="Action ID")
    data: dict[str, Any] = Field(..., description="Submitted data")
    user_id: str = Field(..., min_length=1, description="User ID")
    conversation_id: str = Field(..., min_length=1, description="Conversation ID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Submission timestamp"
    )


class ApprovalCardData(BaseModel):
    """Data for an approval card submission.

    Attributes:
        approval_id: ID of the approval request.
        action: Action taken (approve, reject).
        reason: Reason for the decision.
    """

    approval_id: str = Field(..., min_length=1, description="Approval request ID")
    action: str = Field(..., description="Action (approve/reject)")
    reason: str | None = Field(None, description="Decision reason")


class InstanceActionCardData(BaseModel):
    """Data for an instance action card submission.

    Attributes:
        instance_ids: List of instance IDs to act on.
        action: Action to perform (start, stop, reboot, terminate).
        force: Whether to force the action.
    """

    instance_ids: list[str] = Field(..., min_length=1, description="Instance IDs")
    action: str = Field(..., description="Action to perform")
    force: bool = Field(False, description="Force the action")


class MetricsCardData(BaseModel):
    """Data for a metrics request card submission.

    Attributes:
        instance_ids: List of instance IDs.
        metrics: List of metric names to retrieve.
        time_range: Time range for metrics (e.g., '1h', '6h', '24h').
    """

    instance_ids: list[str] = Field(..., min_length=1, description="Instance IDs")
    metrics: list[str] = Field(..., min_length=1, description="Metric names")
    time_range: str = Field("1h", description="Time range")


class CommandFormData(BaseModel):
    """Generic data for a command form card submission.

    Attributes:
        command_type: Type of command.
        parameters: Command parameters from form inputs.
    """

    command_type: str = Field(..., min_length=1, description="Command type")
    parameters: dict[str, Any] = Field(..., description="Command parameters")


class CardTemplate(BaseModel):
    """Base template for building Adaptive Cards.

    Attributes:
        type: Card type (should be 'AdaptiveCard').
        version: Adaptive Card schema version.
        schema_url: URL to the Adaptive Card schema.
        body: List of card elements.
        actions: List of card actions.
    """

    type: str = Field("AdaptiveCard", description="Card type")
    version: str = Field("1.5", description="Schema version")
    schema_url: str = Field(
        "http://adaptivecards.io/schemas/adaptive-card.json",
        alias="$schema",
        description="Schema URL",
    )
    body: list[dict[str, Any]] = Field(default_factory=list, description="Card body elements")
    actions: list[dict[str, Any]] = Field(default_factory=list, description="Card actions")

    def add_text_block(
        self,
        text: str,
        weight: str = "default",
        size: str = "default",
        color: str = "default",
        wrap: bool = True,
    ) -> None:
        """Add a text block to the card.

        Args:
            text: Text content.
            weight: Text weight (default, bolder).
            size: Text size (small, medium, large, extraLarge).
            color: Text color.
            wrap: Whether to wrap text.
        """
        self.body.append(
            {
                "type": "TextBlock",
                "text": text,
                "weight": weight,
                "size": size,
                "color": color,
                "wrap": wrap,
            }
        )

    def add_fact_set(self, facts: list[tuple[str, str]]) -> None:
        """Add a fact set to the card.

        Args:
            facts: List of (title, value) tuples.
        """
        self.body.append(
            {
                "type": "FactSet",
                "facts": [{"title": title, "value": value} for title, value in facts],
            }
        )

    def add_action(
        self,
        title: str,
        action_type: str = "Action.Submit",
        data: dict[str, Any] | None = None,
        url: str | None = None,
    ) -> None:
        """Add an action to the card.

        Args:
            title: Action button title.
            action_type: Type of action.
            data: Data to submit with the action.
            url: URL to open (for OpenUrl actions).
        """
        action: dict[str, Any] = {"type": action_type, "title": title}

        if data is not None:
            action["data"] = data
        if url is not None:
            action["url"] = url

        self.actions.append(action)

    def to_attachment(self) -> dict[str, Any]:
        """Convert the card template to a Bot Framework attachment.

        Returns:
            Attachment dictionary for Bot Framework.
        """
        return {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": self.model_dump(by_alias=True, exclude_none=True),
        }
