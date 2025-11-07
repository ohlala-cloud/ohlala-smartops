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


class TestHealthMetrics:
    """Test suite for HealthMetrics Pydantic model."""

    def test_health_metrics_initialization(self) -> None:
        """Test that HealthMetrics can be initialized with defaults."""
        metrics = HealthMetrics()
        assert metrics.success is True
        assert isinstance(metrics.cpu_graph, dict)
        assert isinstance(metrics.network_in, dict)
        assert isinstance(metrics.network_out, dict)


class TestRealtimeMetrics:
    """Test suite for RealtimeMetrics Pydantic model."""

    def test_realtime_metrics_initialization(self) -> None:
        """Test that RealtimeMetrics can be initialized with defaults."""
        metrics = RealtimeMetrics()
        assert isinstance(metrics.cpu_percent, int | float)
        assert isinstance(metrics.memory_percent, int | float)
        assert isinstance(metrics.success, bool)
