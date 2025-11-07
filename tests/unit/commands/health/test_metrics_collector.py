"""Unit tests for MetricsCollector."""

import sys
from unittest.mock import MagicMock

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
