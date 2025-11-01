"""CloudWatch custom metrics emitter for operational monitoring.

This module provides a high-level interface for emitting application metrics
to CloudWatch. It wraps the CloudWatchManager with convenient methods for
common metric patterns like command execution, security events, AI usage,
and health status.

All metrics are emitted asynchronously with automatic error handling. Failed
metric emissions are logged but do not raise exceptions to avoid disrupting
application flow.

Example:
    >>> from ohlala_smartops.aws.metrics_emitter import get_metrics_emitter
    >>> emitter = get_metrics_emitter()
    >>> await emitter.emit_command_execution(
    ...     command="start_instance",
    ...     success=True,
    ...     execution_time_ms=1234.5
    ... )
"""

import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import Final

from ohlala_smartops.aws.cloudwatch import CloudWatchManager
from ohlala_smartops.config.settings import Settings, get_settings

logger: Final = logging.getLogger(__name__)

DEFAULT_NAMESPACE: Final[str] = "OhlalaSmartOps"
"""Default CloudWatch namespace for custom metrics."""


class MetricsEmitter:
    """Emit custom CloudWatch metrics for operational monitoring.

    This class provides convenient methods for emitting application metrics
    to CloudWatch. All methods are async and handle errors gracefully by
    logging failures without disrupting application flow.

    Common dimensions (like StackName) are automatically added to all metrics
    when configured in settings.

    Attributes:
        cloudwatch: CloudWatch manager for API operations.
        namespace: CloudWatch namespace for metrics.
        common_dimensions: Dimensions added to all metrics (e.g., StackName).
        settings: Application settings.
    """

    def __init__(
        self,
        namespace: str = DEFAULT_NAMESPACE,
        cloudwatch: CloudWatchManager | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize metrics emitter.

        Args:
            namespace: CloudWatch namespace for metrics. Defaults to "OhlalaSmartOps".
            cloudwatch: Optional CloudWatch manager. If None, creates a new one.
                Defaults to None.
            settings: Application settings. If None, uses get_settings().
                Defaults to None.

        Example:
            >>> emitter = MetricsEmitter()
            >>> # Or with custom namespace:
            >>> emitter = MetricsEmitter(namespace="MyApp/Prod")
        """
        self.settings = settings or get_settings()
        self.cloudwatch = cloudwatch or CloudWatchManager(region=self.settings.aws_region)
        self.namespace = namespace
        self.common_dimensions: dict[str, str] = {}

        # Add stack name as common dimension if configured
        if self.settings.stack_name:
            self.common_dimensions["StackName"] = self.settings.stack_name

        logger.info(f"Initialized MetricsEmitter with namespace={namespace}")

    async def emit_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "Count",
        dimensions: dict[str, str] | None = None,
    ) -> None:
        """Emit a single metric to CloudWatch.

        This is the base method used by all other convenience methods.
        It adds common dimensions and handles errors gracefully.

        Args:
            metric_name: Name of the metric.
            value: Metric value.
            unit: Metric unit (Count, Seconds, Milliseconds, Bytes, Percent, etc.).
                Defaults to "Count".
            dimensions: Additional dimensions for this metric. Defaults to None.

        Example:
            >>> await emitter.emit_metric(
            ...     metric_name="CustomMetric",
            ...     value=42.0,
            ...     unit="Count",
            ...     dimensions={"Environment": "Production"}
            ... )
        """
        try:
            # Combine common dimensions with metric-specific dimensions
            all_dimensions = self.common_dimensions.copy()
            if dimensions:
                all_dimensions.update(dimensions)

            await self.cloudwatch.put_metric_data(
                namespace=self.namespace,
                metric_name=metric_name,
                value=value,
                unit=unit,
                dimensions=all_dimensions if all_dimensions else None,
                timestamp=datetime.now(UTC),
            )

        except Exception as e:
            # Log error but don't raise - metrics should not disrupt application flow
            logger.error(f"Failed to emit metric {metric_name}: {e}")

    # =========================================================================
    # Security Metrics
    # =========================================================================

    async def emit_unauthorized_access(self, source_ip: str | None = None) -> None:
        """Emit unauthorized access attempt metric.

        Args:
            source_ip: Source IP address of unauthorized access. Defaults to None.

        Example:
            >>> await emitter.emit_unauthorized_access(source_ip="192.168.1.100")
        """
        dimensions: dict[str, str] = {}
        if source_ip:
            dimensions["SourceIP"] = source_ip

        await self.emit_metric(
            metric_name="UnauthorizedAccess",
            value=1,
            dimensions=dimensions,
        )

    async def emit_auth_failure(self, auth_type: str = "MCP") -> None:
        """Emit authentication failure metric.

        Args:
            auth_type: Type of authentication that failed (MCP, Teams, AWS, etc.).
                Defaults to "MCP".

        Example:
            >>> await emitter.emit_auth_failure(auth_type="Teams")
        """
        await self.emit_metric(
            metric_name="AuthenticationFailure",
            value=1,
            dimensions={"AuthType": auth_type},
        )

    async def emit_rate_limit_exceeded(self, client_id: str | None = None) -> None:
        """Emit rate limit exceeded metric.

        Args:
            client_id: Identifier of the client that exceeded rate limit.
                Defaults to None.

        Example:
            >>> await emitter.emit_rate_limit_exceeded(client_id="user@example.com")
        """
        dimensions: dict[str, str] = {}
        if client_id:
            dimensions["ClientID"] = client_id

        await self.emit_metric(
            metric_name="RateLimitExceeded",
            value=1,
            dimensions=dimensions,
        )

    # =========================================================================
    # MCP (Model Context Protocol) Metrics
    # =========================================================================

    async def emit_mcp_call(
        self,
        tool_name: str,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Emit MCP tool call metrics.

        Emits three metrics:
        - MCPCallCount: Count of calls with success status
        - MCPCallLatency: Latency in milliseconds
        - MCPCallError: Count of errors (only if success=False)

        Args:
            tool_name: Name of the MCP tool called.
            success: Whether the tool call succeeded.
            latency_ms: Call latency in milliseconds.

        Example:
            >>> await emitter.emit_mcp_call(
            ...     tool_name="aws_ec2_describe_instances",
            ...     success=True,
            ...     latency_ms=456.2
            ... )
        """
        # Success count
        await self.emit_metric(
            metric_name="MCPCallCount",
            value=1,
            dimensions={"ToolName": tool_name, "Success": str(success)},
        )

        # Latency
        await self.emit_metric(
            metric_name="MCPCallLatency",
            value=latency_ms,
            unit="Milliseconds",
            dimensions={"ToolName": tool_name},
        )

        # Error count (only if failed)
        if not success:
            await self.emit_metric(
                metric_name="MCPCallError",
                value=1,
                dimensions={"ToolName": tool_name},
            )

    # =========================================================================
    # Command Execution Metrics
    # =========================================================================

    async def emit_command_execution(
        self,
        command: str,
        success: bool,
        execution_time_ms: float,
    ) -> None:
        """Emit command execution metrics.

        Emits three metrics:
        - CommandExecutionCount: Count of executions with success status
        - CommandExecutionTime: Execution time in milliseconds
        - CommandError: Count of errors (only if success=False)

        Args:
            command: Name of the command executed.
            success: Whether the command succeeded.
            execution_time_ms: Execution time in milliseconds.

        Example:
            >>> await emitter.emit_command_execution(
            ...     command="start_instance",
            ...     success=True,
            ...     execution_time_ms=2340.5
            ... )
        """
        # Execution count
        await self.emit_metric(
            metric_name="CommandExecutionCount",
            value=1,
            dimensions={"Command": command, "Success": str(success)},
        )

        # Execution time
        await self.emit_metric(
            metric_name="CommandExecutionTime",
            value=execution_time_ms,
            unit="Milliseconds",
            dimensions={"Command": command},
        )

        # Error count (only if failed)
        if not success:
            await self.emit_metric(
                metric_name="CommandError",
                value=1,
                dimensions={"Command": command},
            )

    # =========================================================================
    # Write Operation Metrics
    # =========================================================================

    async def emit_write_operation(
        self,
        operation_type: str,
        resource_type: str,
        confirmed: bool = False,
        timed_out: bool = False,
    ) -> None:
        """Emit write operation metric.

        Tracks destructive or state-changing operations with their status
        (confirmed, timed_out, or pending).

        Args:
            operation_type: Type of operation (start, stop, terminate, delete, etc.).
            resource_type: Type of resource affected (ec2_instance, volume, etc.).
            confirmed: Whether the operation was confirmed by user. Defaults to False.
            timed_out: Whether the operation timed out. Defaults to False.

        Example:
            >>> await emitter.emit_write_operation(
            ...     operation_type="stop",
            ...     resource_type="ec2_instance",
            ...     confirmed=True
            ... )
        """
        if confirmed:
            status = "confirmed"
        elif timed_out:
            status = "timed_out"
        else:
            status = "pending"

        await self.emit_metric(
            metric_name="WriteOperationCount",
            value=1,
            dimensions={
                "OperationType": operation_type,
                "ResourceType": resource_type,
                "Status": status,
            },
        )

    # =========================================================================
    # Bedrock (AI) Usage Metrics
    # =========================================================================

    async def emit_bedrock_usage(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> None:
        """Emit Bedrock AI usage metrics.

        Emits three metrics for cost tracking and performance monitoring:
        - BedrockInputTokens: Number of input tokens
        - BedrockOutputTokens: Number of output tokens
        - BedrockLatency: Inference latency in milliseconds

        Args:
            model_id: Bedrock model ID used.
            input_tokens: Number of input (prompt) tokens.
            output_tokens: Number of output (completion) tokens.
            latency_ms: Inference latency in milliseconds.

        Example:
            >>> await emitter.emit_bedrock_usage(
            ...     model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            ...     input_tokens=1500,
            ...     output_tokens=500,
            ...     latency_ms=3456.7
            ... )
        """
        # Input tokens
        await self.emit_metric(
            metric_name="BedrockInputTokens",
            value=float(input_tokens),
            dimensions={"ModelId": model_id},
        )

        # Output tokens
        await self.emit_metric(
            metric_name="BedrockOutputTokens",
            value=float(output_tokens),
            dimensions={"ModelId": model_id},
        )

        # Latency
        await self.emit_metric(
            metric_name="BedrockLatency",
            value=latency_ms,
            unit="Milliseconds",
            dimensions={"ModelId": model_id},
        )

    # =========================================================================
    # Health & Availability Metrics
    # =========================================================================

    async def emit_health_status(self, component: str, healthy: bool) -> None:
        """Emit component health status metric.

        Args:
            component: Component name (database, mcp, bedrock, etc.).
            healthy: Whether the component is healthy.

        Example:
            >>> await emitter.emit_health_status(component="bedrock", healthy=True)
            >>> await emitter.emit_health_status(component="database", healthy=False)
        """
        await self.emit_metric(
            metric_name="ComponentHealth",
            value=1.0 if healthy else 0.0,
            dimensions={"Component": component},
        )


@lru_cache
def get_metrics_emitter(
    namespace: str = DEFAULT_NAMESPACE,
    settings: Settings | None = None,
) -> MetricsEmitter:
    """Get cached metrics emitter instance.

    The metrics emitter is cached to reuse connections and avoid repeated
    initialization. The cache is cleared on application restart.

    Args:
        namespace: CloudWatch namespace for metrics. Defaults to "OhlalaSmartOps".
        settings: Application settings. If None, uses get_settings().
            Defaults to None.

    Returns:
        Configured MetricsEmitter instance.

    Example:
        >>> emitter = get_metrics_emitter()
        >>> await emitter.emit_command_execution(...)
        >>>
        >>> # Or with custom namespace:
        >>> prod_emitter = get_metrics_emitter(namespace="MyApp/Production")
    """
    return MetricsEmitter(namespace=namespace, settings=settings)


# ============================================================================
# Convenience Functions
# ============================================================================
#
# These module-level functions provide a simple API for common use cases
# without requiring explicit emitter instantiation.
# ============================================================================


async def emit_unauthorized_access(source_ip: str | None = None) -> None:
    """Emit unauthorized access metric.

    Convenience function using the default metrics emitter.

    Args:
        source_ip: Source IP address of unauthorized access. Defaults to None.

    Example:
        >>> await emit_unauthorized_access(source_ip="192.168.1.100")
    """
    await get_metrics_emitter().emit_unauthorized_access(source_ip)


async def emit_auth_failure(auth_type: str = "MCP") -> None:
    """Emit authentication failure metric.

    Convenience function using the default metrics emitter.

    Args:
        auth_type: Type of authentication that failed. Defaults to "MCP".

    Example:
        >>> await emit_auth_failure(auth_type="Teams")
    """
    await get_metrics_emitter().emit_auth_failure(auth_type)


async def emit_rate_limit_exceeded(client_id: str | None = None) -> None:
    """Emit rate limit exceeded metric.

    Convenience function using the default metrics emitter.

    Args:
        client_id: Identifier of the client that exceeded rate limit.
            Defaults to None.

    Example:
        >>> await emit_rate_limit_exceeded(client_id="user@example.com")
    """
    await get_metrics_emitter().emit_rate_limit_exceeded(client_id)


async def emit_mcp_call(tool_name: str, success: bool, latency_ms: float) -> None:
    """Emit MCP call metrics.

    Convenience function using the default metrics emitter.

    Args:
        tool_name: Name of the MCP tool called.
        success: Whether the tool call succeeded.
        latency_ms: Call latency in milliseconds.

    Example:
        >>> await emit_mcp_call("aws_ec2_describe_instances", True, 456.2)
    """
    await get_metrics_emitter().emit_mcp_call(tool_name, success, latency_ms)


async def emit_command_execution(
    command: str,
    success: bool,
    execution_time_ms: float,
) -> None:
    """Emit command execution metrics.

    Convenience function using the default metrics emitter.

    Args:
        command: Name of the command executed.
        success: Whether the command succeeded.
        execution_time_ms: Execution time in milliseconds.

    Example:
        >>> await emit_command_execution("start_instance", True, 2340.5)
    """
    await get_metrics_emitter().emit_command_execution(command, success, execution_time_ms)


async def emit_write_operation(
    operation_type: str,
    resource_type: str,
    confirmed: bool = False,
    timed_out: bool = False,
) -> None:
    """Emit write operation metrics.

    Convenience function using the default metrics emitter.

    Args:
        operation_type: Type of operation (start, stop, terminate, etc.).
        resource_type: Type of resource affected (ec2_instance, volume, etc.).
        confirmed: Whether the operation was confirmed by user. Defaults to False.
        timed_out: Whether the operation timed out. Defaults to False.

    Example:
        >>> await emit_write_operation("stop", "ec2_instance", confirmed=True)
    """
    await get_metrics_emitter().emit_write_operation(
        operation_type, resource_type, confirmed, timed_out
    )
