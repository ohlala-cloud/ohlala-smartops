"""Command tracking models for SSM command execution monitoring.

This module provides Pydantic models for tracking SSM command execution,
workflow coordination, and multi-instance operations.

Phase 3C: Core command tracking models for AsyncCommandTracker.
"""

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SSMCommandStatus(str, Enum):
    """SSM command execution status.

    These statuses map directly to AWS SSM command invocation states.
    """

    PENDING = "Pending"
    IN_PROGRESS = "InProgress"
    DELAYED = "Delayed"
    SUCCESS = "Success"
    DELIVERY_TIMED_OUT = "DeliveryTimedOut"
    EXECUTION_TIMED_OUT = "ExecutionTimedOut"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    UNDELIVERABLE = "Undeliverable"
    TERMINATED = "Terminated"
    CANCELLING = "Cancelling"


class CommandTrackingInfo(BaseModel):
    """Tracking information for a single SSM command.

    This model tracks the lifecycle of an SSM command from initiation
    through polling to completion.

    Attributes:
        command_id: SSM command ID from send-command.
        instance_id: Target EC2 instance ID.
        workflow_id: Optional workflow ID for multi-instance coordination.
        status: Current command status.
        document_name: SSM document being executed.
        parameters: Command parameters (sanitized for security).
        started_at: When tracking started.
        last_polled_at: Last poll timestamp.
        completed_at: When command completed (if finished).
        poll_count: Number of polling attempts.
        next_poll_delay: Next polling delay in seconds (exponential backoff).
        timeout_at: When to give up polling.
        error_message: Error details if failed.
        output_url: S3 URL for command output (if available).

    Example:
        >>> tracking = CommandTrackingInfo.create(
        ...     command_id="abc-123",
        ...     instance_id="i-1234567890abcdef0",
        ...     document_name="AWS-RunShellScript",
        ...     parameters={"commands": ["uptime"]},
        ... )
        >>> tracking.status
        <SSMCommandStatus.PENDING: 'Pending'>
    """

    command_id: str = Field(..., min_length=1, description="SSM command ID")
    instance_id: str = Field(..., pattern=r"^i-[a-f0-9]{8,17}$", description="EC2 instance ID")
    workflow_id: str | None = Field(None, description="Multi-instance workflow ID")
    status: SSMCommandStatus = Field(SSMCommandStatus.PENDING, description="Command status")
    document_name: str = Field(..., description="SSM document name")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Command parameters")

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Tracking start time"
    )
    last_polled_at: datetime | None = Field(None, description="Last poll timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")

    poll_count: int = Field(0, ge=0, description="Number of polls")
    next_poll_delay: float = Field(3.0, ge=1.0, le=10.0, description="Next poll delay (seconds)")
    timeout_at: datetime = Field(..., description="Timeout timestamp")

    error_message: str | None = Field(None, description="Error details")
    output_url: str | None = Field(None, description="S3 URL for output")

    @classmethod
    def create(
        cls,
        command_id: str,
        instance_id: str,
        document_name: str,
        parameters: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        timeout_minutes: int = 15,
    ) -> "CommandTrackingInfo":
        """Create new command tracking info.

        Args:
            command_id: SSM command ID.
            instance_id: EC2 instance ID.
            document_name: SSM document name.
            parameters: Command parameters (will be sanitized).
            workflow_id: Optional workflow ID.
            timeout_minutes: Timeout in minutes (default 15).

        Returns:
            New CommandTrackingInfo instance.

        Example:
            >>> info = CommandTrackingInfo.create(
            ...     command_id="cmd-123",
            ...     instance_id="i-abc123",
            ...     document_name="AWS-RunShellScript"
            ... )
        """
        return cls(  # type: ignore[call-arg]
            command_id=command_id,
            instance_id=instance_id,
            workflow_id=workflow_id,
            document_name=document_name,
            parameters=cls._sanitize_parameters(parameters or {}),
            timeout_at=datetime.now(UTC) + timedelta(minutes=timeout_minutes),
        )

    @staticmethod
    def _sanitize_parameters(params: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive data from parameters for storage.

        Args:
            params: Raw command parameters.

        Returns:
            Sanitized parameters with secrets redacted.
        """
        sensitive_keys = {"password", "secret", "token", "key", "credential", "apikey"}
        return {
            k: "***REDACTED***" if any(s in k.lower() for s in sensitive_keys) else v
            for k, v in params.items()
        }

    def is_terminal_state(self) -> bool:
        """Check if command is in a terminal state.

        Returns:
            True if command has finished (success or failure).
        """
        return self.status in {
            SSMCommandStatus.SUCCESS,
            SSMCommandStatus.FAILED,
            SSMCommandStatus.CANCELLED,
            SSMCommandStatus.TERMINATED,
            SSMCommandStatus.DELIVERY_TIMED_OUT,
            SSMCommandStatus.EXECUTION_TIMED_OUT,
            SSMCommandStatus.UNDELIVERABLE,
        }

    def is_timed_out(self) -> bool:
        """Check if command has timed out.

        Returns:
            True if current time has exceeded timeout_at.
        """
        return datetime.now(UTC) >= self.timeout_at

    def update_status(self, new_status: SSMCommandStatus, error_message: str | None = None) -> None:
        """Update command status and timestamps.

        Args:
            new_status: New command status.
            error_message: Optional error message if failed.
        """
        self.status = new_status
        self.last_polled_at = datetime.now(UTC)

        if self.is_terminal_state():
            self.completed_at = datetime.now(UTC)

        if error_message:
            self.error_message = error_message

    def calculate_next_poll_delay(self) -> float:
        """Calculate next polling delay with exponential backoff.

        Implements exponential backoff: 3s → 3.6s → 4.3s → 5.2s → ... (capped at 10s)

        Returns:
            Next polling delay in seconds.
        """
        self.poll_count += 1
        # Exponential backoff with 1.2x multiplier, capped at 10 seconds
        self.next_poll_delay = min(3.0 * (1.2**self.poll_count), 10.0)
        return self.next_poll_delay


class WorkflowInfo(BaseModel):
    """Multi-instance workflow coordination info.

    Tracks the progress of operations across multiple EC2 instances,
    allowing coordinated execution and result aggregation.

    Attributes:
        workflow_id: Unique workflow identifier.
        operation_type: Type of operation (e.g., "stop-instances").
        expected_count: Expected number of commands in workflow.
        completed_count: Number of completed commands.
        success_count: Number of successful commands.
        failed_count: Number of failed commands.
        command_ids: List of SSM command IDs in this workflow.
        started_at: Workflow start time.
        completed_at: Workflow completion time.

    Example:
        >>> workflow = WorkflowInfo(
        ...     workflow_id="wf-123",
        ...     operation_type="restart-services",
        ...     expected_count=5
        ... )
        >>> workflow.record_completion(success=True)
        >>> workflow.is_complete()
        False
    """

    workflow_id: str = Field(..., min_length=1, description="Workflow ID")
    operation_type: str = Field(..., description="Operation type")
    expected_count: int = Field(..., ge=1, description="Expected command count")
    completed_count: int = Field(0, ge=0, description="Completed commands")
    success_count: int = Field(0, ge=0, description="Successful commands")
    failed_count: int = Field(0, ge=0, description="Failed commands")
    command_ids: list[str] = Field(default_factory=list, description="Command IDs")

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Workflow start time"
    )
    completed_at: datetime | None = Field(None, description="Workflow completion time")

    def is_complete(self) -> bool:
        """Check if workflow is complete.

        Returns:
            True if all expected commands have completed.
        """
        return self.completed_count >= self.expected_count

    def record_completion(self, success: bool) -> None:
        """Record command completion.

        Args:
            success: Whether the command succeeded.
        """
        self.completed_count += 1
        if success:
            self.success_count += 1
        else:
            self.failed_count += 1

        if self.is_complete():
            self.completed_at = datetime.now(UTC)

    def get_success_rate(self) -> float:
        """Get workflow success rate.

        Returns:
            Success rate as percentage (0-100).
        """
        if self.completed_count == 0:
            return 0.0
        return (self.success_count / self.completed_count) * 100.0
