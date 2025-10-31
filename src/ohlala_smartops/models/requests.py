"""Command request and response models for Ohlala SmartOps.

This module defines Pydantic models for command requests and responses,
including command parameters, execution results, and error handling.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CommandType(str, Enum):
    """Types of commands supported by the bot."""

    # EC2 commands
    EC2_LIST = "ec2_list"
    EC2_SHOW = "ec2_show"
    EC2_START = "ec2_start"
    EC2_STOP = "ec2_stop"
    EC2_REBOOT = "ec2_reboot"
    EC2_TERMINATE = "ec2_terminate"

    # SSM commands
    SSM_SESSION_START = "ssm_session_start"
    SSM_SESSION_LIST = "ssm_session_list"
    SSM_SESSION_TERMINATE = "ssm_session_terminate"
    SSM_COMMAND_EXECUTE = "ssm_command_execute"

    # CloudWatch commands
    CLOUDWATCH_METRICS = "cloudwatch_metrics"
    CLOUDWATCH_HEALTH = "cloudwatch_health"
    CLOUDWATCH_ALARMS = "cloudwatch_alarms"

    # Cost commands
    COST_CURRENT = "cost_current"
    COST_FORECAST = "cost_forecast"
    COST_BREAKDOWN = "cost_breakdown"

    # Utility commands
    HELP = "help"
    HEALTH = "health"


class CommandPriority(str, Enum):
    """Priority levels for command execution."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class CommandStatus(str, Enum):
    """Status of command execution."""

    PENDING = "pending"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REQUIRES_APPROVAL = "requires_approval"


class CommandRequest(BaseModel):
    """Request to execute a command.

    Attributes:
        command_type: Type of command to execute.
        parameters: Command-specific parameters.
        user_id: ID of the user who requested the command.
        conversation_id: ID of the conversation where the command was requested.
        priority: Priority level for execution.
        requires_approval: Whether the command requires approval before execution.
        timeout_seconds: Maximum time allowed for command execution.
        metadata: Additional metadata for the command.
    """

    command_type: CommandType = Field(..., description="Command type")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    user_id: str = Field(..., min_length=1, description="User ID")
    conversation_id: str = Field(..., min_length=1, description="Conversation ID")
    priority: CommandPriority = Field(CommandPriority.NORMAL, description="Execution priority")
    requires_approval: bool = Field(False, description="Requires approval before execution")
    timeout_seconds: int = Field(300, ge=1, le=3600, description="Execution timeout in seconds")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class CommandResponse(BaseModel):
    """Response from command execution.

    Attributes:
        command_type: Type of command that was executed.
        status: Execution status.
        result: Command execution result (success data).
        error: Error information (if status is FAILED).
        execution_time_ms: Time taken to execute the command in milliseconds.
        timestamp: When the response was generated.
        metadata: Additional metadata.
    """

    command_type: CommandType = Field(..., description="Command type")
    status: CommandStatus = Field(..., description="Execution status")
    result: dict[str, Any] | None = Field(None, description="Execution result")
    error: str | None = Field(None, description="Error message")
    execution_time_ms: int = Field(..., ge=0, description="Execution time in milliseconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class EC2InstanceFilter(BaseModel):
    """Filters for EC2 instance queries.

    Attributes:
        instance_ids: Specific instance IDs to filter by.
        tags: Tag filters (key-value pairs).
        states: Instance states to filter by.
        names: Instance names to filter by (Name tag).
    """

    instance_ids: list[str] | None = Field(None, description="Instance IDs")
    tags: dict[str, str] = Field(default_factory=dict, description="Tag filters")
    states: list[str] | None = Field(None, description="Instance states")
    names: list[str] | None = Field(None, description="Instance names (Name tag)")


class EC2InstanceAction(BaseModel):
    """Request to perform an action on EC2 instances.

    Attributes:
        instance_ids: List of instance IDs to act on.
        action: Action to perform (start, stop, reboot, terminate).
        dry_run: Whether to perform a dry run (validation only).
        force: Force the action (for terminate).
    """

    instance_ids: list[str] = Field(..., min_length=1, description="Instance IDs to act on")
    action: str = Field(..., description="Action to perform")
    dry_run: bool = Field(False, description="Perform dry run only")
    force: bool = Field(False, description="Force the action")


class SSMSessionRequest(BaseModel):
    """Request to start an SSM session.

    Attributes:
        instance_id: Instance ID to connect to.
        session_type: Type of session (interactive, port_forwarding).
        local_port: Local port for port forwarding.
        remote_port: Remote port for port forwarding.
        document_name: SSM document to use.
    """

    instance_id: str = Field(..., min_length=1, description="Instance ID")
    session_type: str = Field("interactive", description="Session type")
    local_port: int | None = Field(None, ge=1, le=65535, description="Local port")
    remote_port: int | None = Field(None, ge=1, le=65535, description="Remote port")
    document_name: str | None = Field(None, description="SSM document name")


class SSMCommandRequest(BaseModel):
    """Request to execute an SSM command.

    Attributes:
        instance_ids: List of instance IDs to execute command on.
        commands: List of commands to execute.
        working_directory: Working directory for command execution.
        timeout_seconds: Command execution timeout.
        execution_timeout: SSM execution timeout.
        comment: Comment for the command execution.
    """

    instance_ids: list[str] = Field(..., min_length=1, description="Instance IDs")
    commands: list[str] = Field(..., min_length=1, description="Commands to execute")
    working_directory: str | None = Field(None, description="Working directory")
    timeout_seconds: int = Field(3600, ge=1, description="Command timeout")
    execution_timeout: int = Field(3600, ge=1, description="Execution timeout")
    comment: str | None = Field(None, description="Execution comment")


class CloudWatchMetricsRequest(BaseModel):
    """Request to retrieve CloudWatch metrics.

    Attributes:
        instance_ids: List of instance IDs to get metrics for.
        metric_names: List of metric names to retrieve.
        start_time: Start time for metrics query.
        end_time: End time for metrics query.
        period_seconds: Period for metric aggregation in seconds.
        statistic: Statistic to calculate (Average, Sum, Maximum, Minimum).
    """

    instance_ids: list[str] = Field(..., min_length=1, description="Instance IDs")
    metric_names: list[str] = Field(..., min_length=1, description="Metric names")
    start_time: datetime = Field(..., description="Start time")
    end_time: datetime = Field(..., description="End time")
    period_seconds: int = Field(300, ge=60, description="Aggregation period")
    statistic: str = Field("Average", description="Statistic to calculate")


class CostRequest(BaseModel):
    """Request for cost information.

    Attributes:
        start_date: Start date for cost query.
        end_date: End date for cost query.
        granularity: Granularity of cost data (DAILY, MONTHLY).
        group_by: Dimension to group costs by (SERVICE, TAG, INSTANCE_TYPE, etc.).
        filter_tags: Tags to filter costs by.
    """

    start_date: datetime = Field(..., description="Start date")
    end_date: datetime = Field(..., description="End date")
    granularity: str = Field("DAILY", description="Cost granularity")
    group_by: list[str] | None = Field(None, description="Dimensions to group by")
    filter_tags: dict[str, str] = Field(default_factory=dict, description="Tag filters")


class NaturalLanguageRequest(BaseModel):
    """Request containing natural language input for AI processing.

    Attributes:
        text: Natural language text from the user.
        conversation_id: ID of the conversation.
        user_id: ID of the user.
        context: Additional context for the AI (conversation history, etc.).
    """

    text: str = Field(..., min_length=1, description="Natural language text")
    conversation_id: str = Field(..., min_length=1, description="Conversation ID")
    user_id: str = Field(..., min_length=1, description="User ID")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")


class AIInterpretation(BaseModel):
    """AI interpretation of natural language input.

    Attributes:
        command_type: Interpreted command type.
        parameters: Extracted command parameters.
        confidence: Confidence score (0.0 to 1.0).
        explanation: Explanation of the interpretation.
        requires_clarification: Whether the AI needs more information.
        clarification_questions: Questions to ask the user for clarification.
    """

    command_type: CommandType | None = Field(None, description="Interpreted command type")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Extracted parameters")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    explanation: str = Field(..., description="Interpretation explanation")
    requires_clarification: bool = Field(False, description="Needs clarification")
    clarification_questions: list[str] = Field(
        default_factory=list, description="Clarification questions"
    )
