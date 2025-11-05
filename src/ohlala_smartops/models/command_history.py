"""Command history models for tracking user command execution.

This module provides Pydantic models for tracking the history of user commands,
their execution status, results, and metadata for audit trails and history viewing.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CommandHistoryStatus(str, Enum):
    """Status of a command in history.

    These statuses track the overall lifecycle of a user command.
    """

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CommandHistoryEntry(BaseModel):
    """History entry for a user command execution.

    This model stores comprehensive information about a command execution
    for historical tracking, audit trails, and user history viewing.

    Attributes:
        command_id: Unique command identifier (SSM command ID or generated ID).
        user_id: User who executed the command.
        description: Human-readable command description.
        status: Current command status.
        timestamp: When the command was initiated.
        completion_time: When the command completed (if finished).
        user_context: Additional user context (team, conversation, etc.).
        approved_by: User ID who approved the command (if applicable).
        instance_ids: List of target instance IDs.
        results: Dictionary mapping instance IDs to execution results.
        aws_region: AWS region where command was executed.

    Example:
        >>> entry = CommandHistoryEntry.create(
        ...     command_id="cmd-123",
        ...     user_id="user@example.com",
        ...     description="Stop instances i-abc123, i-def456",
        ...     instance_ids=["i-abc123", "i-def456"],
        ... )
        >>> entry.status
        <CommandHistoryStatus.PENDING: 'pending'>
    """

    command_id: str = Field(..., min_length=1, description="Command identifier")
    user_id: str = Field(..., description="User who executed the command")
    description: str = Field(..., description="Human-readable description")
    status: CommandHistoryStatus = Field(CommandHistoryStatus.PENDING, description="Command status")

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Command initiation time"
    )
    completion_time: datetime | None = Field(None, description="Command completion time")

    user_context: str | None = Field(None, description="Additional user context")
    approved_by: str | None = Field(None, description="User who approved (if applicable)")

    instance_ids: list[str] = Field(default_factory=list, description="Target instance IDs")
    results: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Execution results by instance ID"
    )

    aws_region: str = Field("us-east-1", description="AWS region")

    @classmethod
    def create(
        cls,
        command_id: str,
        user_id: str,
        description: str,
        instance_ids: list[str] | None = None,
        user_context: str | None = None,
        aws_region: str = "us-east-1",
    ) -> "CommandHistoryEntry":
        """Create a new command history entry.

        Args:
            command_id: Unique command identifier.
            user_id: User who executed the command.
            description: Human-readable command description.
            instance_ids: Target instance IDs (if applicable).
            user_context: Additional user context.
            aws_region: AWS region.

        Returns:
            New CommandHistoryEntry instance.

        Example:
            >>> entry = CommandHistoryEntry.create(
            ...     command_id="cmd-abc123",
            ...     user_id="user@example.com",
            ...     description="Start instance i-123",
            ...     instance_ids=["i-123"],
            ... )
        """
        return cls(  # type: ignore[call-arg]
            command_id=command_id,
            user_id=user_id,
            description=description,
            instance_ids=instance_ids or [],
            user_context=user_context,
            aws_region=aws_region,
        )

    def mark_completed(self, results: dict[str, dict[str, Any]] | None = None) -> None:
        """Mark command as completed.

        Args:
            results: Execution results by instance ID.
        """
        self.status = CommandHistoryStatus.COMPLETED
        self.completion_time = datetime.now(UTC)
        if results:
            self.results = results

    def mark_failed(self, error_message: str) -> None:
        """Mark command as failed.

        Args:
            error_message: Error description.
        """
        self.status = CommandHistoryStatus.FAILED
        self.completion_time = datetime.now(UTC)
        self.results = {"error": {"message": error_message, "status": "Failed"}}

    def mark_cancelled(self) -> None:
        """Mark command as cancelled."""
        self.status = CommandHistoryStatus.CANCELLED
        self.completion_time = datetime.now(UTC)

    def set_approval(self, approved_by: str) -> None:
        """Record who approved this command.

        Args:
            approved_by: User ID who approved the command.
        """
        self.approved_by = approved_by

    def add_result(self, instance_id: str, result: dict[str, Any]) -> None:
        """Add execution result for a specific instance.

        Args:
            instance_id: Instance ID.
            result: Execution result dictionary.
        """
        self.results[instance_id] = result

    def is_completed(self) -> bool:
        """Check if command is completed (success or failure).

        Returns:
            True if command has finished execution.
        """
        return self.status in {
            CommandHistoryStatus.COMPLETED,
            CommandHistoryStatus.FAILED,
            CommandHistoryStatus.CANCELLED,
        }
