"""Unit tests for CloudWatch metrics emitter."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ohlala_smartops.aws.cloudwatch import CloudWatchManager
from ohlala_smartops.aws.metrics_emitter import (
    DEFAULT_NAMESPACE,
    MetricsEmitter,
    emit_command_execution,
    emit_unauthorized_access,
    get_metrics_emitter,
)
from ohlala_smartops.config.settings import Settings


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        aws_region="us-east-1",
        stack_name="test-stack",
        microsoft_app_id="test-app-id",
        microsoft_app_password="test-password",
        microsoft_app_tenant_id="test-tenant-id",
    )


@pytest.fixture
def settings_no_stack() -> Settings:
    """Create test settings without stack name."""
    return Settings(
        aws_region="us-east-1",
        stack_name="",
        microsoft_app_id="test-app-id",
        microsoft_app_password="test-password",
        microsoft_app_tenant_id="test-tenant-id",
    )


@pytest.fixture
def mock_cloudwatch() -> MagicMock:
    """Create mock CloudWatch manager."""
    mock = MagicMock(spec=CloudWatchManager)
    mock.put_metric_data = AsyncMock()
    return mock


@pytest.fixture
def metrics_emitter(settings: Settings, mock_cloudwatch: MagicMock) -> MetricsEmitter:
    """Create metrics emitter for testing."""
    return MetricsEmitter(
        namespace="TestNamespace",
        cloudwatch=mock_cloudwatch,
        settings=settings,
    )


class TestMetricsEmitterInitialization:
    """Test metrics emitter initialization."""

    def test_init_with_defaults(self, mock_cloudwatch: MagicMock) -> None:
        """Test initialization with default values."""
        emitter = MetricsEmitter(cloudwatch=mock_cloudwatch)

        assert emitter.namespace == DEFAULT_NAMESPACE
        assert emitter.cloudwatch == mock_cloudwatch
        assert isinstance(emitter.settings, Settings)
        assert isinstance(emitter.common_dimensions, dict)

    def test_init_with_stack_name(self, settings: Settings, mock_cloudwatch: MagicMock) -> None:
        """Test initialization with stack name in settings."""
        emitter = MetricsEmitter(
            cloudwatch=mock_cloudwatch,
            settings=settings,
        )

        assert emitter.common_dimensions == {"StackName": "test-stack"}

    def test_init_without_stack_name(
        self, settings_no_stack: Settings, mock_cloudwatch: MagicMock
    ) -> None:
        """Test initialization without stack name."""
        emitter = MetricsEmitter(
            cloudwatch=mock_cloudwatch,
            settings=settings_no_stack,
        )

        assert emitter.common_dimensions == {}

    def test_init_with_custom_namespace(self, mock_cloudwatch: MagicMock) -> None:
        """Test initialization with custom namespace."""
        emitter = MetricsEmitter(
            namespace="CustomApp/Prod",
            cloudwatch=mock_cloudwatch,
        )

        assert emitter.namespace == "CustomApp/Prod"


class TestEmitMetric:
    """Test base emit_metric method."""

    @pytest.mark.asyncio
    async def test_emit_metric_basic(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting a basic metric."""
        await metrics_emitter.emit_metric(
            metric_name="TestMetric",
            value=42.0,
            unit="Count",
        )

        mock_cloudwatch.put_metric_data.assert_called_once()
        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]

        assert call_kwargs["namespace"] == "TestNamespace"
        assert call_kwargs["metric_name"] == "TestMetric"
        assert call_kwargs["value"] == 42.0
        assert call_kwargs["unit"] == "Count"
        assert isinstance(call_kwargs["timestamp"], datetime)
        assert call_kwargs["timestamp"].tzinfo == UTC

    @pytest.mark.asyncio
    async def test_emit_metric_with_dimensions(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting metric with custom dimensions."""
        await metrics_emitter.emit_metric(
            metric_name="CustomMetric",
            value=100.0,
            unit="Milliseconds",
            dimensions={"Environment": "Production", "Service": "API"},
        )

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]

        # Should include both common dimensions and custom dimensions
        expected_dimensions = {
            "StackName": "test-stack",
            "Environment": "Production",
            "Service": "API",
        }
        assert call_kwargs["dimensions"] == expected_dimensions

    @pytest.mark.asyncio
    async def test_emit_metric_error_handling(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test that errors are logged but not raised."""
        mock_cloudwatch.put_metric_data.side_effect = Exception("CloudWatch error")

        # Should not raise exception
        with patch("ohlala_smartops.aws.metrics_emitter.logger") as mock_logger:
            await metrics_emitter.emit_metric(
                metric_name="FailingMetric",
                value=1.0,
            )

            # Error should be logged
            mock_logger.error.assert_called_once()
            error_message = mock_logger.error.call_args[0][0]
            assert "Failed to emit metric FailingMetric" in error_message


class TestSecurityMetrics:
    """Test security-related metrics."""

    @pytest.mark.asyncio
    async def test_emit_unauthorized_access_without_ip(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting unauthorized access without source IP."""
        await metrics_emitter.emit_unauthorized_access()

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]

        assert call_kwargs["metric_name"] == "UnauthorizedAccess"
        assert call_kwargs["value"] == 1
        # Should only have common dimensions
        assert call_kwargs["dimensions"] == {"StackName": "test-stack"}

    @pytest.mark.asyncio
    async def test_emit_unauthorized_access_with_ip(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting unauthorized access with source IP."""
        await metrics_emitter.emit_unauthorized_access(source_ip="192.168.1.100")

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]

        expected_dimensions = {
            "StackName": "test-stack",
            "SourceIP": "192.168.1.100",
        }
        assert call_kwargs["dimensions"] == expected_dimensions

    @pytest.mark.asyncio
    async def test_emit_auth_failure(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting authentication failure."""
        await metrics_emitter.emit_auth_failure(auth_type="Teams")

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]

        assert call_kwargs["metric_name"] == "AuthenticationFailure"
        assert call_kwargs["value"] == 1
        expected_dimensions = {"StackName": "test-stack", "AuthType": "Teams"}
        assert call_kwargs["dimensions"] == expected_dimensions

    @pytest.mark.asyncio
    async def test_emit_rate_limit_exceeded(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting rate limit exceeded."""
        await metrics_emitter.emit_rate_limit_exceeded(client_id="user@example.com")

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]

        assert call_kwargs["metric_name"] == "RateLimitExceeded"
        expected_dimensions = {
            "StackName": "test-stack",
            "ClientID": "user@example.com",
        }
        assert call_kwargs["dimensions"] == expected_dimensions


class TestMCPMetrics:
    """Test MCP-related metrics."""

    @pytest.mark.asyncio
    async def test_emit_mcp_call_success(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting successful MCP call metrics."""
        await metrics_emitter.emit_mcp_call(
            tool_name="aws_ec2_describe_instances",
            success=True,
            latency_ms=456.2,
        )

        # Should emit 2 metrics: count and latency (not error for success)
        assert mock_cloudwatch.put_metric_data.call_count == 2

        # Check first call (count)
        first_call = mock_cloudwatch.put_metric_data.call_args_list[0][1]
        assert first_call["metric_name"] == "MCPCallCount"
        assert first_call["value"] == 1
        assert first_call["dimensions"]["ToolName"] == "aws_ec2_describe_instances"
        assert first_call["dimensions"]["Success"] == "True"

        # Check second call (latency)
        second_call = mock_cloudwatch.put_metric_data.call_args_list[1][1]
        assert second_call["metric_name"] == "MCPCallLatency"
        assert second_call["value"] == 456.2
        assert second_call["unit"] == "Milliseconds"

    @pytest.mark.asyncio
    async def test_emit_mcp_call_failure(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting failed MCP call metrics."""
        await metrics_emitter.emit_mcp_call(
            tool_name="aws_ec2_start_instances",
            success=False,
            latency_ms=123.4,
        )

        # Should emit 3 metrics: count, latency, and error
        assert mock_cloudwatch.put_metric_data.call_count == 3

        # Check error metric
        error_call = mock_cloudwatch.put_metric_data.call_args_list[2][1]
        assert error_call["metric_name"] == "MCPCallError"
        assert error_call["value"] == 1


class TestCommandMetrics:
    """Test command execution metrics."""

    @pytest.mark.asyncio
    async def test_emit_command_execution_success(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting successful command execution."""
        await metrics_emitter.emit_command_execution(
            command="start_instance",
            success=True,
            execution_time_ms=2340.5,
        )

        # Should emit 2 metrics: count and time (not error)
        assert mock_cloudwatch.put_metric_data.call_count == 2

        # Check count metric
        count_call = mock_cloudwatch.put_metric_data.call_args_list[0][1]
        assert count_call["metric_name"] == "CommandExecutionCount"
        assert count_call["dimensions"]["Command"] == "start_instance"
        assert count_call["dimensions"]["Success"] == "True"

        # Check time metric
        time_call = mock_cloudwatch.put_metric_data.call_args_list[1][1]
        assert time_call["metric_name"] == "CommandExecutionTime"
        assert time_call["value"] == 2340.5
        assert time_call["unit"] == "Milliseconds"

    @pytest.mark.asyncio
    async def test_emit_command_execution_failure(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting failed command execution."""
        await metrics_emitter.emit_command_execution(
            command="stop_instance",
            success=False,
            execution_time_ms=500.0,
        )

        # Should emit 3 metrics including error
        assert mock_cloudwatch.put_metric_data.call_count == 3

        error_call = mock_cloudwatch.put_metric_data.call_args_list[2][1]
        assert error_call["metric_name"] == "CommandError"


class TestWriteOperationMetrics:
    """Test write operation metrics."""

    @pytest.mark.asyncio
    async def test_emit_write_operation_confirmed(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting confirmed write operation."""
        await metrics_emitter.emit_write_operation(
            operation_type="stop",
            resource_type="ec2_instance",
            confirmed=True,
        )

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]

        assert call_kwargs["metric_name"] == "WriteOperationCount"
        assert call_kwargs["value"] == 1
        assert call_kwargs["dimensions"]["OperationType"] == "stop"
        assert call_kwargs["dimensions"]["ResourceType"] == "ec2_instance"
        assert call_kwargs["dimensions"]["Status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_emit_write_operation_timed_out(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting timed out write operation."""
        await metrics_emitter.emit_write_operation(
            operation_type="terminate",
            resource_type="ec2_instance",
            confirmed=False,
            timed_out=True,
        )

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]
        assert call_kwargs["dimensions"]["Status"] == "timed_out"

    @pytest.mark.asyncio
    async def test_emit_write_operation_pending(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting pending write operation."""
        await metrics_emitter.emit_write_operation(
            operation_type="start",
            resource_type="ec2_instance",
            confirmed=False,
            timed_out=False,
        )

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]
        assert call_kwargs["dimensions"]["Status"] == "pending"


class TestBedrockMetrics:
    """Test Bedrock usage metrics."""

    @pytest.mark.asyncio
    async def test_emit_bedrock_usage(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting Bedrock usage metrics."""
        await metrics_emitter.emit_bedrock_usage(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            input_tokens=1500,
            output_tokens=500,
            latency_ms=3456.7,
        )

        # Should emit 3 metrics: input tokens, output tokens, latency
        assert mock_cloudwatch.put_metric_data.call_count == 3

        # Check input tokens
        input_call = mock_cloudwatch.put_metric_data.call_args_list[0][1]
        assert input_call["metric_name"] == "BedrockInputTokens"
        assert input_call["value"] == 1500.0
        assert input_call["dimensions"]["ModelId"] == "anthropic.claude-3-sonnet-20240229-v1:0"

        # Check output tokens
        output_call = mock_cloudwatch.put_metric_data.call_args_list[1][1]
        assert output_call["metric_name"] == "BedrockOutputTokens"
        assert output_call["value"] == 500.0

        # Check latency
        latency_call = mock_cloudwatch.put_metric_data.call_args_list[2][1]
        assert latency_call["metric_name"] == "BedrockLatency"
        assert latency_call["value"] == 3456.7
        assert latency_call["unit"] == "Milliseconds"


class TestHealthMetrics:
    """Test health status metrics."""

    @pytest.mark.asyncio
    async def test_emit_health_status_healthy(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting healthy component status."""
        await metrics_emitter.emit_health_status(
            component="bedrock",
            healthy=True,
        )

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]

        assert call_kwargs["metric_name"] == "ComponentHealth"
        assert call_kwargs["value"] == 1.0
        assert call_kwargs["dimensions"]["Component"] == "bedrock"

    @pytest.mark.asyncio
    async def test_emit_health_status_unhealthy(
        self, metrics_emitter: MetricsEmitter, mock_cloudwatch: MagicMock
    ) -> None:
        """Test emitting unhealthy component status."""
        await metrics_emitter.emit_health_status(
            component="database",
            healthy=False,
        )

        call_kwargs = mock_cloudwatch.put_metric_data.call_args[1]
        assert call_kwargs["value"] == 0.0


class TestGetMetricsEmitter:
    """Test get_metrics_emitter factory function."""

    def test_get_metrics_emitter_singleton(self) -> None:
        """Test that get_metrics_emitter returns cached instance."""
        emitter1 = get_metrics_emitter()
        emitter2 = get_metrics_emitter()

        # Should return same instance for same namespace
        assert emitter1 is emitter2

    def test_get_metrics_emitter_with_custom_namespace(self) -> None:
        """Test get_metrics_emitter with custom namespace."""
        emitter = get_metrics_emitter(namespace="CustomApp")

        assert emitter.namespace == "CustomApp"
        assert isinstance(emitter, MetricsEmitter)

    def test_get_metrics_emitter_returns_instance(self) -> None:
        """Test get_metrics_emitter returns MetricsEmitter instance."""
        emitter = get_metrics_emitter()

        assert isinstance(emitter, MetricsEmitter)
        assert isinstance(emitter.settings, Settings)


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_convenience_emit_unauthorized_access(self) -> None:
        """Test convenience function for unauthorized access."""
        with patch("ohlala_smartops.aws.metrics_emitter.get_metrics_emitter") as mock_get:
            mock_emitter = MagicMock()
            mock_emitter.emit_unauthorized_access = AsyncMock()
            mock_get.return_value = mock_emitter

            await emit_unauthorized_access(source_ip="192.168.1.1")

            mock_emitter.emit_unauthorized_access.assert_called_once_with("192.168.1.1")

    @pytest.mark.asyncio
    async def test_convenience_emit_command_execution(self) -> None:
        """Test convenience function for command execution."""
        with patch("ohlala_smartops.aws.metrics_emitter.get_metrics_emitter") as mock_get:
            mock_emitter = MagicMock()
            mock_emitter.emit_command_execution = AsyncMock()
            mock_get.return_value = mock_emitter

            await emit_command_execution("start_instance", True, 1234.5)

            mock_emitter.emit_command_execution.assert_called_once_with(
                "start_instance", True, 1234.5
            )
