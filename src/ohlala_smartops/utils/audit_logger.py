"""Audit logging for security and compliance tracking.

This module provides centralized audit logging for all bot operations,
including command execution, MCP calls, Bedrock inference, security events,
and write operations. Audit logs are structured JSON entries that can be
ingested by log aggregation systems for compliance and security monitoring.

Example:
    >>> from ohlala_smartops.utils.audit_logger import get_audit_logger
    >>> audit_logger = get_audit_logger()
    >>> audit_logger.log_command_execution(
    ...     user_id="user@example.com",
    ...     user_name="John Doe",
    ...     team_id="team-123",
    ...     command="start_instance",
    ...     arguments={"instance_id": "i-1234567890abcdef0"},
    ...     result="success",
    ...     success=True,
    ...     execution_time_ms=1234.5,
    ... )
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Final

from ohlala_smartops.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# Sensitive keywords that should be redacted in audit logs
SENSITIVE_KEYS: Final[tuple[str, ...]] = (
    "password",
    "token",
    "secret",
    "key",
    "credential",
    "auth",
    "api_key",
    "access_token",
)


class AuditLogger:
    """Centralized audit logging for all bot operations.

    This class provides structured audit logging with automatic PII
    redaction and configurable sensitivity levels. All audit entries
    are logged as JSON structures for easy parsing and analysis.

    Attributes:
        enabled: Whether audit logging is enabled.
        include_pii: Whether to include PII in audit logs.
        settings: Application settings instance.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the audit logger.

        Args:
            settings: Application settings. If None, uses get_settings().
        """
        self.settings = settings or get_settings()
        self.enabled = self.settings.enable_audit_logging
        self.include_pii = self.settings.audit_log_include_pii

    def log_command_execution(
        self,
        user_id: str,
        user_name: str,
        team_id: str,
        command: str,
        arguments: dict[str, Any],
        result: str,
        success: bool,
        execution_time_ms: float,
        error: str | None = None,
    ) -> None:
        """Log command execution for audit trail.

        Records user commands with execution results, timing, and errors.
        User names are redacted unless include_pii is enabled.

        Args:
            user_id: Unique identifier for the user.
            user_name: Display name of the user (may be redacted).
            team_id: Team or tenant identifier.
            command: Name of the command executed.
            arguments: Command arguments (sensitive data will be sanitized).
            result: Brief description of the result.
            success: Whether the command succeeded.
            execution_time_ms: Execution time in milliseconds.
            error: Error message if the command failed. Defaults to None.

        Example:
            >>> audit_logger.log_command_execution(
            ...     user_id="user@example.com",
            ...     user_name="John Doe",
            ...     team_id="team-123",
            ...     command="stop_instance",
            ...     arguments={"instance_id": "i-1234567890abcdef0"},
            ...     result="instance stopped",
            ...     success=True,
            ...     execution_time_ms=2340.5,
            ... )
        """
        if not self.enabled:
            return

        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": "command_execution",
            "user": {
                "id": user_id,
                "name": user_name if self.include_pii else "[REDACTED]",
                "team_id": team_id,
            },
            "command": {
                "name": command,
                "arguments": self._sanitize_arguments(arguments),
            },
            "result": {
                "success": success,
                "message": result,
                "execution_time_ms": execution_time_ms,
                "error": error,
            },
        }

        self._emit_audit_log("AUDIT_COMMAND", audit_entry, success)

    def log_mcp_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
        execution_time_ms: float,
        error: str | None = None,
    ) -> None:
        """Log MCP (Model Context Protocol) tool calls.

        Records calls to MCP tools with arguments and timing
        for operational visibility and debugging.

        Args:
            tool_name: Name of the MCP tool called.
            arguments: Tool arguments (sensitive data will be sanitized).
            success: Whether the tool call succeeded.
            execution_time_ms: Execution time in milliseconds.
            error: Error message if the call failed. Defaults to None.

        Example:
            >>> audit_logger.log_mcp_call(
            ...     tool_name="aws_ec2_describe_instances",
            ...     arguments={"instance_ids": ["i-1234567890abcdef0"]},
            ...     success=True,
            ...     execution_time_ms=456.2,
            ... )
        """
        if not self.enabled:
            return

        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": "mcp_tool_call",
            "tool": tool_name,
            "arguments": self._sanitize_arguments(arguments),
            "success": success,
            "execution_time_ms": execution_time_ms,
        }

        if error:
            audit_entry["error"] = error

        self._emit_audit_log("AUDIT_MCP", audit_entry, success)

    def log_bedrock_call(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model_id: str,
        guardrail_applied: bool,
        execution_time_ms: float,
    ) -> None:
        """Log Bedrock AI calls for cost tracking and usage monitoring.

        Records Bedrock inference calls with token usage for cost tracking,
        compliance, and usage analytics.

        Args:
            prompt_tokens: Number of tokens in the prompt.
            completion_tokens: Number of tokens in the completion.
            model_id: Bedrock model ID used.
            guardrail_applied: Whether Bedrock Guardrails were applied.
            execution_time_ms: Execution time in milliseconds.

        Example:
            >>> audit_logger.log_bedrock_call(
            ...     prompt_tokens=1500,
            ...     completion_tokens=500,
            ...     model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            ...     guardrail_applied=True,
            ...     execution_time_ms=3456.7,
            ... )
        """
        if not self.enabled:
            return

        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": "bedrock_inference",
            "model_id": model_id,
            "tokens": {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            },
            "guardrail_applied": guardrail_applied,
            "execution_time_ms": execution_time_ms,
        }

        logger.info(f"AUDIT_BEDROCK: {json.dumps(audit_entry)}")

    def log_security_event(
        self,
        event_name: str,
        details: dict[str, Any],
        severity: str = "info",
    ) -> None:
        """Log security-related events.

        Records security events such as authentication failures, permission
        denials, suspicious activity, or policy violations.

        Args:
            event_name: Name of the security event.
            details: Event details (sensitive data will be sanitized).
            severity: Event severity level (info, warning, critical).
                Defaults to "info".

        Example:
            >>> audit_logger.log_security_event(
            ...     event_name="dangerous_command_blocked",
            ...     details={
            ...         "command": "rm -rf /",
            ...         "user_id": "user@example.com",
            ...         "reason": "destructive command pattern detected",
            ...     },
            ...     severity="warning",
            ... )
        """
        if not self.enabled:
            return

        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": "security_event",
            "event_name": event_name,
            "severity": severity,
            "details": self._sanitize_arguments(details),
        }

        # Map severity to appropriate log level
        log_func: Callable[[str], None]
        if severity == "critical":
            log_func = logger.critical
        elif severity == "warning":
            log_func = logger.warning
        else:
            log_func = logger.info

        log_func(f"AUDIT_SECURITY: {json.dumps(audit_entry)}")

    def log_write_operation(
        self,
        operation: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        changes: dict[str, Any],
        confirmed: bool = True,
    ) -> None:
        """Log write operations for change tracking.

        Records destructive or state-changing operations for audit trails
        and change management tracking.

        Args:
            operation: Type of operation (create, update, delete, start, stop).
            resource_type: Type of resource affected (instance, volume, etc.).
            resource_id: Unique identifier for the resource.
            user_id: User who performed the operation.
            changes: Changes made (sensitive data will be sanitized).
            confirmed: Whether the operation was confirmed by user.
                Defaults to True.

        Example:
            >>> audit_logger.log_write_operation(
            ...     operation="stop",
            ...     resource_type="ec2_instance",
            ...     resource_id="i-1234567890abcdef0",
            ...     user_id="user@example.com",
            ...     changes={"state": "running -> stopping"},
            ...     confirmed=True,
            ... )
        """
        if not self.enabled:
            return

        audit_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": "write_operation",
            "operation": operation,
            "resource": {
                "type": resource_type,
                "id": resource_id,
            },
            "user_id": user_id,
            "changes": self._sanitize_arguments(changes),
            "confirmed": confirmed,
        }

        logger.info(f"AUDIT_WRITE: {json.dumps(audit_entry)}")

    def _sanitize_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Remove or redact sensitive information from arguments.

        Recursively processes dictionaries to redact sensitive keys such
        as passwords, tokens, secrets, and credentials.

        Args:
            arguments: Dictionary potentially containing sensitive data.

        Returns:
            Sanitized dictionary with sensitive values redacted.
        """
        if self.include_pii:
            return arguments

        sanitized: dict[str, Any] = {}

        for key, value in arguments.items():
            # Check if key contains sensitive keywords
            if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = self._sanitize_arguments(value)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # Sanitize list of dictionaries
                sanitized[key] = [
                    self._sanitize_arguments(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                # Keep other values as-is (primitives, lists of IDs, etc.)
                sanitized[key] = value

        return sanitized

    def _emit_audit_log(
        self,
        log_prefix: str,
        audit_entry: dict[str, Any],
        success: bool = True,
    ) -> None:
        """Emit an audit log entry at the appropriate level.

        Args:
            log_prefix: Prefix for the log message.
            audit_entry: Structured audit entry to log.
            success: Whether the operation was successful.
        """
        log_message = f"{log_prefix}: {json.dumps(audit_entry)}"

        if success:
            logger.info(log_message)
        else:
            logger.warning(f"{log_prefix}_FAILED: {json.dumps(audit_entry)}")


@lru_cache
def get_audit_logger(settings: Settings | None = None) -> AuditLogger:
    """Get cached audit logger instance.

    The audit logger is cached to avoid repeated initialization. The cache
    is cleared on application restart.

    Args:
        settings: Application settings. If None, uses get_settings().

    Returns:
        Configured AuditLogger instance.

    Example:
        >>> audit_logger = get_audit_logger()
        >>> audit_logger.log_security_event(...)
    """
    return AuditLogger(settings=settings)
