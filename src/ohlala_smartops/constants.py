"""Constants used throughout Ohlala SmartOps.

This module contains application constants that do not depend on runtime
configuration or environment variables. For environment-based configuration,
see the config module.
"""

from typing import Final

# =============================================================================
# SSM (AWS Systems Manager) Configuration
# =============================================================================

SSM_DOCUMENT_LINUX: Final[str] = "AWS-RunShellScript"
"""SSM document name for executing shell scripts on Linux instances."""

SSM_DOCUMENT_WINDOWS: Final[str] = "AWS-RunPowerShellScript"
"""SSM document name for executing PowerShell scripts on Windows instances."""

SSM_OUTPUT_LIMIT: Final[int] = 24000
"""Maximum character limit for SSM command output.

SSM Run Command has a 24,000 character limit for command output.
Commands producing more output will be truncated.
"""

SSM_SYNC_TIMEOUT: Final[int] = 60
"""Timeout in seconds for synchronous SSM command execution."""

SSM_ASYNC_TIMEOUT: Final[int] = 300
"""Timeout in seconds for asynchronous SSM commands awaiting approval."""

SSM_POLL_INTERVAL: Final[int] = 2
"""Interval in seconds between status polls for SSM command execution."""

# =============================================================================
# Security - Dangerous Command Patterns
# =============================================================================

DANGEROUS_COMMAND_PATTERNS: Final[tuple[str, ...]] = (
    "rm -rf /",
    "del /f /s /q C:\\",
    "format c:",
    "format.com",
    "mkfs",
    "dd if=/dev/zero",
    "shutdown",
    "init 0",
    "poweroff",
    "diskpart",
)
"""Command patterns that are considered dangerous and require special approval.

These commands can cause data loss, system shutdown, or other destructive
actions. They should trigger additional confirmation workflows.
"""

# =============================================================================
# Platform Detection
# =============================================================================

WINDOWS_PLATFORM_INDICATORS: Final[tuple[str, ...]] = ("PowerShell", "Windows")
"""Strings that indicate a Windows platform in SSM output or platform info."""

PLACEHOLDER_INSTANCE_PATTERNS: Final[tuple[str, ...]] = (
    "i-0123456789abcdef0",
    "i-xxxxxxxxxxxxxxxxx",
    "i-example",
    "i-xxxxx",
)
"""Instance ID patterns that should be recognized as placeholders/examples.

These are commonly used in documentation and should not be treated as
valid instance IDs in validation logic.
"""

# =============================================================================
# Microsoft Teams Adaptive Cards
# =============================================================================

CARD_VERSION: Final[str] = "1.5"
"""Adaptive Card schema version."""

TEAMS_ADAPTIVE_CARD_VERSION: Final[str] = "1.5"
"""Microsoft Teams Adaptive Card version."""

# Card color themes
CARD_COLOR_ACCENT: Final[str] = "Accent"
"""Accent color for cards (neutral, informational)."""

CARD_COLOR_WARNING: Final[str] = "Warning"
"""Warning color for cards (caution, needs attention)."""

CARD_COLOR_GOOD: Final[str] = "Good"
"""Good/success color for cards (positive outcomes)."""

CARD_COLOR_ATTENTION: Final[str] = "Attention"
"""Attention color for cards (errors, critical issues)."""

# Card element sizes
CARD_SIZE_LARGE: Final[str] = "Large"
"""Large size for card elements (headings, important text)."""

CARD_SIZE_SMALL: Final[str] = "Small"
"""Small size for card elements (supporting text, metadata)."""

CARD_WEIGHT_BOLDER: Final[str] = "Bolder"
"""Bold weight for card text elements."""

# =============================================================================
# Microsoft Teams Activity Types
# =============================================================================

TEAMS_INVOKE_ACTIVITY: Final[str] = "invoke"
"""Teams activity type for invoke actions (button clicks, etc.)."""

TEAMS_MESSAGE_ACTIVITY: Final[str] = "message"
"""Teams activity type for messages (user sends a message)."""

TEAMS_MESSAGE_UPDATE_UNRELIABLE: Final[bool] = True
"""Flag indicating that Teams message updates can be unreliable.

Microsoft Teams Bot Framework has known issues with message updates
returning ServiceError. This flag reminds developers to handle failures
gracefully when attempting to update existing messages.
"""

# =============================================================================
# Card Action Types
# =============================================================================

ACTION_SSM_APPROVE: Final[str] = "ssm_command_approve"
"""Action ID for approving an SSM command execution."""

ACTION_SSM_DENY: Final[str] = "ssm_command_deny"
"""Action ID for denying an SSM command execution."""

ACTION_BATCH_SSM_APPROVE: Final[str] = "batch_ssm_approve"
"""Action ID for approving multiple SSM commands in batch."""

ACTION_BATCH_SSM_DENY: Final[str] = "batch_ssm_deny"
"""Action ID for denying multiple SSM commands in batch."""

ACTION_SHOW_HEALTH: Final[str] = "show_health"
"""Action ID for displaying instance health information."""

# =============================================================================
# Chart and Visualization Types
# =============================================================================

CHART_GAUGE: Final[str] = "Chart.Gauge"
"""Gauge chart type for displaying single metric values."""

CHART_DONUT: Final[str] = "Chart.Donut"
"""Donut chart type for displaying proportional data."""

CHART_LINE: Final[str] = "Chart.Line"
"""Line chart type for displaying time-series data."""

# =============================================================================
# SSM Command Status Values
# =============================================================================

STATUS_SUCCESS: Final[str] = "Success"
"""SSM command completed successfully."""

STATUS_FAILED: Final[str] = "Failed"
"""SSM command failed during execution."""

STATUS_CANCELLED: Final[str] = "Cancelled"
"""SSM command was cancelled before completion."""

STATUS_TERMINATED: Final[str] = "Terminated"
"""SSM command was terminated (timeout or forced stop)."""

STATUS_IN_PROGRESS: Final[str] = "InProgress"
"""SSM command is currently executing."""

STATUS_PENDING: Final[str] = "Pending"
"""SSM command is pending execution (queued or awaiting approval)."""

COMPLETION_STATUSES: Final[tuple[str, ...]] = (
    STATUS_SUCCESS,
    STATUS_FAILED,
    STATUS_CANCELLED,
    STATUS_TERMINATED,
)
"""SSM command statuses that indicate completion (no further state changes)."""

# =============================================================================
# CloudWatch Metrics Defaults
# =============================================================================

DEFAULT_METRIC_HOURS: Final[int] = 1
"""Default number of hours of metric data to retrieve."""

DEFAULT_METRIC_PERIOD: Final[int] = 300
"""Default metric period in seconds (5 minutes)."""

DEFAULT_MAX_TOOLS_DISPLAY: Final[int] = 10
"""Maximum number of tools/resources to display in responses."""

# =============================================================================
# Bedrock Model Configuration
# =============================================================================

BEDROCK_PRIMARY_MODEL_BY_REGION: Final[dict[str, str]] = {
    # EU regions - use EU inference profile
    "eu-west-1": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "eu-west-2": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "eu-west-3": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "eu-central-1": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "eu-north-1": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    # US regions - use US inference profile
    "us-east-1": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us-east-2": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us-west-1": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us-west-2": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    # APAC regions - use APAC inference profile
    "ap-northeast-1": "apac.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "ap-northeast-2": "apac.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "ap-southeast-1": "apac.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "ap-southeast-2": "apac.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "ap-south-1": "apac.anthropic.claude-sonnet-4-5-20250929-v1:0",
    # Other regions - use global inference profile
    "ca-central-1": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "sa-east-1": "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
}
"""Mapping of AWS regions to optimal Claude Sonnet 4.5 model IDs.

Each region is mapped to its nearest inference profile for optimal
latency and reliability. The region-specific profiles (eu., us., apac.)
provide better performance than the global profile when available.
"""

BEDROCK_FALLBACK_MODEL: Final[str] = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
"""Fallback Claude Sonnet 4.5 model ID that works from any AWS region.

Used when the primary region-optimized model is unavailable or when
the deployment region is not in BEDROCK_PRIMARY_MODEL_BY_REGION.
"""

BEDROCK_MAX_TOKENS: Final[int] = 4000
"""Maximum number of tokens for Bedrock model responses."""

BEDROCK_TEMPERATURE: Final[float] = 0.3
"""Temperature parameter for Bedrock model (0.0-1.0).

Lower values (0.0-0.4) produce more focused and deterministic responses,
suitable for operational tasks. Higher values (0.7-1.0) produce more
creative and varied responses.
"""

BEDROCK_ANTHROPIC_VERSION: Final[str] = "bedrock-2023-05-31"
"""Anthropic API version for Bedrock integration."""


def get_bedrock_model_for_region(aws_region: str) -> str:
    """Get the optimal Claude Sonnet 4.5 model ID for an AWS region.

    Returns the region-optimized model if available, otherwise falls back
    to the global model that works from any region.

    Args:
        aws_region: AWS region code (e.g., 'us-east-1', 'eu-west-1').

    Returns:
        Bedrock model ID string optimized for the specified region.

    Example:
        >>> get_bedrock_model_for_region('us-east-1')
        'us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        >>> get_bedrock_model_for_region('unknown-region')
        'global.anthropic.claude-sonnet-4-5-20250929-v1:0'
    """
    return BEDROCK_PRIMARY_MODEL_BY_REGION.get(aws_region, BEDROCK_FALLBACK_MODEL)
