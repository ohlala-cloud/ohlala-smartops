"""Unit tests for MetricsCollector."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock structlog to avoid Python 3.13 compatibility issues with zope.interface
sys.modules["structlog"] = MagicMock()

from ohlala_smartops.commands.health.metrics_collector import (  # noqa: E402
    HealthMetrics,
    MetricsCollector,
    RealtimeMetrics,
)


class TestMetricsCollector:
    """Test suite for MetricsCollector."""

    def test_metrics_collector_initialization(self) -> None:
        """Test that MetricsCollector can be initialized."""
        collector = MetricsCollector(region="us-east-1")
        assert collector.region == "us-east-1"

    def test_get_platform_commands_windows(self) -> None:
        """Test getting Windows platform commands."""
        collector = MetricsCollector(region="us-east-1")
        commands = collector._get_platform_commands("windows")
        assert isinstance(commands, list)
        assert len(commands) > 0

    def test_get_platform_commands_linux(self) -> None:
        """Test getting Linux platform commands."""
        collector = MetricsCollector(region="us-east-1")
        commands = collector._get_platform_commands("linux")
        assert isinstance(commands, list)
        assert len(commands) > 0

    def test_get_windows_metrics_command(self) -> None:
        """Test getting Windows metrics command."""
        collector = MetricsCollector(region="us-east-1")
        command = collector._get_windows_metrics_command()
        assert isinstance(command, str)
        assert len(command) > 0

    def test_get_linux_metrics_command(self) -> None:
        """Test getting Linux metrics command."""
        collector = MetricsCollector(region="us-east-1")
        command = collector._get_linux_metrics_command()
        assert isinstance(command, str)
        assert len(command) > 0

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.CloudWatchManager")
    async def test_get_cloudwatch_metrics_success(self, mock_cw: MagicMock) -> None:
        """Test getting CloudWatch metrics successfully."""
        # Create mock datapoints
        mock_datapoint = MagicMock()
        mock_datapoint.value = 45.5
        mock_datapoint.timestamp = MagicMock()
        mock_datapoint.timestamp.isoformat.return_value = "2025-11-07T10:00:00Z"

        mock_manager = AsyncMock()
        mock_manager.get_metric_statistics = AsyncMock(return_value=[mock_datapoint])
        mock_cw.return_value = mock_manager

        collector = MetricsCollector(cloudwatch_manager=mock_manager, region="us-east-1")
        result = await collector.get_cloudwatch_metrics("i-1234567890abcdef0", hours=6)

        assert isinstance(result, HealthMetrics)
        assert result.success is True
        assert "datapoints" in result.cpu_graph
        assert len(result.cpu_graph["datapoints"]) > 0

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.CloudWatchManager")
    async def test_get_cloudwatch_metrics_failure(self, mock_cw: MagicMock) -> None:
        """Test CloudWatch metrics with API failure."""
        mock_manager = AsyncMock()
        mock_manager.get_metric_statistics = AsyncMock(side_effect=Exception("API Error"))
        mock_cw.return_value = mock_manager

        collector = MetricsCollector(cloudwatch_manager=mock_manager, region="us-east-1")
        result = await collector.get_cloudwatch_metrics("i-1234567890abcdef0", hours=6)

        assert isinstance(result, HealthMetrics)
        # Even with errors, partial data may be available
        assert "datapoints" in result.cpu_graph

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.SSMCommandManager")
    async def test_get_realtime_system_metrics_linux_success(self, mock_ssm: MagicMock) -> None:
        """Test getting real-time metrics for Linux."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = (
            '{"cpu_percent": 45.2, "memory_percent": 60.5, "memory_used_mb": 12800, '
            '"memory_total_mb": 16384, "processes": 120, "uptime_text": "5 days"}'
        )

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        # Mock SSM availability check
        with patch.object(MetricsCollector, "_check_ssm_availability", return_value=True):
            collector = MetricsCollector(ssm_manager=mock_manager, region="us-east-1")
            result = await collector.get_realtime_system_metrics(
                "i-1234567890abcdef0", platform="linux"
            )

            assert isinstance(result, RealtimeMetrics)
            assert result.success is True
            assert result.cpu_percent == 45.2
            assert result.memory_percent == 60.5

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.SSMCommandManager")
    async def test_get_realtime_system_metrics_windows_success(self, mock_ssm: MagicMock) -> None:
        """Test getting real-time metrics for Windows."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = (
            '{"cpu_percent": 35.0, "memory_percent": 55.0, "memory_used_mb": 8000, '
            '"memory_total_mb": 16384, "processes": 80, "uptime_text": "3 days"}'
        )

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        with patch.object(MetricsCollector, "_check_ssm_availability", return_value=True):
            collector = MetricsCollector(ssm_manager=mock_manager, region="us-east-1")
            result = await collector.get_realtime_system_metrics(
                "i-1234567890abcdef0", platform="windows"
            )

            assert isinstance(result, RealtimeMetrics)
            assert result.success is True
            assert result.cpu_percent == 35.0

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.SSMCommandManager")
    async def test_get_realtime_system_metrics_ssm_unavailable(self, mock_ssm: MagicMock) -> None:
        """Test real-time metrics when SSM is unavailable."""
        mock_manager = AsyncMock()
        mock_ssm.return_value = mock_manager

        with (
            patch.object(MetricsCollector, "_check_ssm_availability", return_value=False),
            patch.object(
                MetricsCollector,
                "_generate_ssm_unavailable_message",
                return_value="SSM not available",
            ),
        ):
            collector = MetricsCollector(ssm_manager=mock_manager, region="us-east-1")
            result = await collector.get_realtime_system_metrics(
                "i-1234567890abcdef0", platform="linux"
            )

            assert isinstance(result, RealtimeMetrics)
            assert result.success is False
            assert result.ssm_unavailable is True

    @pytest.mark.asyncio
    async def test_get_realtime_system_metrics_invalid_platform(self) -> None:
        """Test real-time metrics with invalid platform."""
        collector = MetricsCollector(region="us-east-1")
        with pytest.raises(ValueError, match="Invalid platform"):
            await collector.get_realtime_system_metrics("i-1234567890abcdef0", platform="invalid")

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.SSMCommandManager")
    async def test_get_realtime_system_metrics_invalid_json(self, mock_ssm: MagicMock) -> None:
        """Test real-time metrics with invalid JSON response."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = "not valid json"

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        with patch.object(MetricsCollector, "_check_ssm_availability", return_value=True):
            collector = MetricsCollector(ssm_manager=mock_manager, region="us-east-1")
            result = await collector.get_realtime_system_metrics(
                "i-1234567890abcdef0", platform="linux"
            )

            assert isinstance(result, RealtimeMetrics)
            assert result.success is False

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.SSMCommandManager")
    async def test_get_realtime_system_metrics_command_failure(self, mock_ssm: MagicMock) -> None:
        """Test real-time metrics when SSM command fails."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Failed"
        mock_invocation.stdout = ""
        mock_invocation.stderr = "Command execution failed"

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        with patch.object(MetricsCollector, "_check_ssm_availability", return_value=True):
            collector = MetricsCollector(ssm_manager=mock_manager, region="us-east-1")
            result = await collector.get_realtime_system_metrics(
                "i-1234567890abcdef0", platform="linux"
            )

            assert isinstance(result, RealtimeMetrics)
            assert result.success is False

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.CloudWatchManager")
    async def test_get_cloudwatch_metrics_with_ebs(self, mock_cw: MagicMock) -> None:
        """Test CloudWatch metrics including EBS metrics."""
        # Create mock datapoints for all metrics
        mock_cpu_dp = MagicMock()
        mock_cpu_dp.value = 45.5
        mock_cpu_dp.timestamp = MagicMock()
        mock_cpu_dp.timestamp.isoformat.return_value = "2025-11-07T10:00:00Z"

        mock_ebs_dp = MagicMock()
        mock_ebs_dp.value = 1000.0
        mock_ebs_dp.timestamp = MagicMock()
        mock_ebs_dp.timestamp.isoformat.return_value = "2025-11-07T10:00:00Z"

        async def mock_get_metric_stats(namespace, metric_name, **kwargs):
            if namespace == "AWS/EC2":
                return [mock_cpu_dp]
            if namespace == "AWS/EBS":
                return [mock_ebs_dp]
            return []

        mock_manager = AsyncMock()
        mock_manager.get_metric_statistics = AsyncMock(side_effect=mock_get_metric_stats)
        mock_cw.return_value = mock_manager

        collector = MetricsCollector(cloudwatch_manager=mock_manager, region="us-east-1")
        result = await collector.get_cloudwatch_metrics("i-1234567890abcdef0", hours=6)

        assert isinstance(result, HealthMetrics)
        assert result.success is True
        assert "ebs_metrics" in result.model_dump() or result.ebs_metrics

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.metrics_collector.CloudWatchManager")
    async def test_get_cloudwatch_metrics_no_datapoints(self, mock_cw: MagicMock) -> None:
        """Test CloudWatch metrics with no datapoints returned."""
        mock_manager = AsyncMock()
        mock_manager.get_metric_statistics = AsyncMock(return_value=[])
        mock_cw.return_value = mock_manager

        collector = MetricsCollector(cloudwatch_manager=mock_manager, region="us-east-1")
        result = await collector.get_cloudwatch_metrics("i-1234567890abcdef0", hours=6)

        assert isinstance(result, HealthMetrics)
        # Should still succeed but with empty datapoints
        assert "datapoints" in result.cpu_graph

    @pytest.mark.asyncio
    @patch("ohlala_smartops.aws.client.create_aws_client")
    async def test_check_ssm_availability_available(self, mock_create_client: MagicMock) -> None:
        """Test SSM availability check when instance is available."""
        mock_ssm_client = AsyncMock()
        mock_ssm_client.call_api = AsyncMock(
            return_value={"InstanceInformationList": [{"InstanceId": "i-1234567890abcdef0"}]}
        )
        mock_create_client.return_value = mock_ssm_client

        collector = MetricsCollector(region="us-east-1")
        result = await collector._check_ssm_availability("i-1234567890abcdef0")

        assert result is True

    @pytest.mark.asyncio
    @patch("ohlala_smartops.aws.client.create_aws_client")
    async def test_check_ssm_availability_not_available(
        self, mock_create_client: MagicMock
    ) -> None:
        """Test SSM availability check when instance is not available."""
        mock_ssm_client = AsyncMock()
        mock_ssm_client.call_api = AsyncMock(return_value={"InstanceInformationList": []})
        mock_create_client.return_value = mock_ssm_client

        collector = MetricsCollector(region="us-east-1")
        result = await collector._check_ssm_availability("i-1234567890abcdef0")

        assert result is False

    @pytest.mark.asyncio
    @patch("ohlala_smartops.aws.client.create_aws_client")
    async def test_check_ssm_availability_error(self, mock_create_client: MagicMock) -> None:
        """Test SSM availability check with API error."""
        mock_ssm_client = AsyncMock()
        mock_ssm_client.call_api = AsyncMock(side_effect=Exception("API Error"))
        mock_create_client.return_value = mock_ssm_client

        collector = MetricsCollector(region="us-east-1")
        result = await collector._check_ssm_availability("i-1234567890abcdef0")

        assert result is False

    @pytest.mark.asyncio
    @patch("ohlala_smartops.aws.client.create_aws_client")
    async def test_generate_ssm_unavailable_message_stopped(
        self, mock_create_client: MagicMock
    ) -> None:
        """Test SSM unavailable message for stopped instance."""
        mock_ec2_client = AsyncMock()
        mock_ec2_client.call_api = AsyncMock(
            return_value={
                "Reservations": [
                    {"Instances": [{"State": {"Name": "stopped"}, "PlatformDetails": "Linux/UNIX"}]}
                ]
            }
        )
        mock_create_client.return_value = mock_ec2_client

        collector = MetricsCollector(region="us-east-1")
        result = await collector._generate_ssm_unavailable_message("i-1234567890abcdef0")

        assert "stopped" in result.lower()

    @pytest.mark.asyncio
    @patch("ohlala_smartops.aws.client.create_aws_client")
    async def test_generate_ssm_unavailable_message_old_platform(
        self, mock_create_client: MagicMock
    ) -> None:
        """Test SSM unavailable message for old platform."""
        mock_ec2_client = AsyncMock()
        mock_ec2_client.call_api = AsyncMock(
            return_value={
                "Reservations": [
                    {
                        "Instances": [
                            {"State": {"Name": "running"}, "PlatformDetails": "Amazon Linux AMI"}
                        ]
                    }
                ]
            }
        )
        mock_create_client.return_value = mock_ec2_client

        collector = MetricsCollector(region="us-east-1")
        result = await collector._generate_ssm_unavailable_message("i-1234567890abcdef0")

        assert "Amazon Linux AMI" in result

    @pytest.mark.asyncio
    @patch("ohlala_smartops.aws.client.create_aws_client")
    async def test_generate_ssm_unavailable_message_generic(
        self, mock_create_client: MagicMock
    ) -> None:
        """Test SSM unavailable message generic case."""
        mock_ec2_client = AsyncMock()
        mock_ec2_client.call_api = AsyncMock(
            return_value={
                "Reservations": [
                    {"Instances": [{"State": {"Name": "running"}, "PlatformDetails": "Linux/UNIX"}]}
                ]
            }
        )
        mock_create_client.return_value = mock_ec2_client

        collector = MetricsCollector(region="us-east-1")
        result = await collector._generate_ssm_unavailable_message("i-1234567890abcdef0")

        assert "SSM" in result or "agent" in result.lower()

    @pytest.mark.asyncio
    async def test_get_instance_health_summary_with_ssm_success(self) -> None:
        """Test health summary using SSM metrics."""
        mock_ssm_manager = AsyncMock()
        collector = MetricsCollector(ssm_manager=mock_ssm_manager, region="us-east-1")

        # Mock successful SSM metrics
        mock_metrics = RealtimeMetrics(
            cpu_percent=45.0, memory_percent=60.0, success=True, ssm_unavailable=False
        )
        with patch.object(collector, "get_realtime_system_metrics", return_value=mock_metrics):
            result = await collector.get_instance_health_summary("i-1234567890abcdef0")

            assert result["instance_id"] == "i-1234567890abcdef0"
            assert result["cpu_percent"] == 45.0
            assert result["memory_percent"] == 60.0
            assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_instance_health_summary_fallback_to_cloudwatch(self) -> None:
        """Test health summary falling back to CloudWatch."""
        mock_ssm_manager = AsyncMock()
        mock_cw_manager = AsyncMock()
        collector = MetricsCollector(
            ssm_manager=mock_ssm_manager,
            cloudwatch_manager=mock_cw_manager,
            region="us-east-1",
        )

        # Mock failed SSM metrics
        mock_ssm_metrics = RealtimeMetrics(success=False, ssm_unavailable=True)
        mock_cw_metrics = HealthMetrics(
            cpu_graph={"datapoints": [{"value": 85.0}], "current": 85.0}, success=True
        )

        with (
            patch.object(collector, "get_realtime_system_metrics", return_value=mock_ssm_metrics),
            patch.object(collector, "get_cloudwatch_metrics", return_value=mock_cw_metrics),
        ):
            result = await collector.get_instance_health_summary("i-1234567890abcdef0")

            assert result["instance_id"] == "i-1234567890abcdef0"
            assert result["cpu_percent"] == 85.0
            assert result["status"] == "warning"
            assert result["data_source"] == "cloudwatch"

    @pytest.mark.asyncio
    async def test_get_instance_health_summary_critical_status(self) -> None:
        """Test health summary with critical CPU status."""
        mock_ssm_manager = AsyncMock()
        collector = MetricsCollector(ssm_manager=mock_ssm_manager, region="us-east-1")

        mock_metrics = RealtimeMetrics(
            cpu_percent=95.0, memory_percent=80.0, success=True, ssm_unavailable=False
        )
        with patch.object(collector, "get_realtime_system_metrics", return_value=mock_metrics):
            result = await collector.get_instance_health_summary("i-1234567890abcdef0")

            assert result["status"] == "critical"

    @pytest.mark.asyncio
    async def test_get_instance_health_summary_error(self) -> None:
        """Test health summary with error."""
        collector = MetricsCollector(region="us-east-1")

        with patch.object(
            collector,
            "get_realtime_system_metrics",
            side_effect=Exception("Test error"),
        ):
            result = await collector.get_instance_health_summary("i-1234567890abcdef0")

            assert result["status"] == "error"
            assert "error" in result


class TestHealthMetrics:
    """Test suite for HealthMetrics Pydantic model."""

    def test_health_metrics_initialization(self) -> None:
        """Test that HealthMetrics can be initialized with defaults."""
        metrics = HealthMetrics()
        assert metrics.success is True
        assert isinstance(metrics.cpu_graph, dict)
        assert isinstance(metrics.network_in, dict)
        assert isinstance(metrics.network_out, dict)

    def test_health_metrics_with_custom_values(self) -> None:
        """Test HealthMetrics with custom values."""
        metrics = HealthMetrics(
            success=True,
            cpu_graph={"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 45.2}]},
            network_in={"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 1024}]},
            network_out={"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 512}]},
        )
        assert metrics.success is True
        assert len(metrics.cpu_graph["datapoints"]) == 1

    def test_health_metrics_failure_state(self) -> None:
        """Test HealthMetrics in failure state."""
        metrics = HealthMetrics(success=False, error="Test error")
        assert metrics.success is False
        assert metrics.error == "Test error"


class TestRealtimeMetrics:
    """Test suite for RealtimeMetrics Pydantic model."""

    def test_realtime_metrics_initialization(self) -> None:
        """Test that RealtimeMetrics can be initialized with defaults."""
        metrics = RealtimeMetrics()
        assert isinstance(metrics.cpu_percent, int | float)
        assert isinstance(metrics.memory_percent, int | float)
        assert isinstance(metrics.success, bool)

    def test_realtime_metrics_with_custom_values(self) -> None:
        """Test RealtimeMetrics with custom values."""
        metrics = RealtimeMetrics(
            success=True,
            cpu_percent=45.2,
            memory_percent=60.5,
            memory_used_mb=12800.0,
            memory_total_mb=16384.0,
        )
        assert metrics.cpu_percent == 45.2
        assert metrics.memory_percent == 60.5
        assert metrics.memory_used_mb == 12800.0

    def test_realtime_metrics_failure_state(self) -> None:
        """Test RealtimeMetrics in failure state."""
        metrics = RealtimeMetrics(success=False)
        assert metrics.success is False
