"""Unit tests for ChartBuilder."""

import sys
from unittest.mock import MagicMock

# Mock structlog to avoid Python 3.13 compatibility issues with zope.interface
sys.modules["structlog"] = MagicMock()

from ohlala_smartops.commands.health.chart_builder import ChartBuilder  # noqa: E402


class TestChartBuilder:
    """Test suite for ChartBuilder."""

    def test_chart_builder_initialization(self) -> None:
        """Test that ChartBuilder can be initialized."""
        builder = ChartBuilder()
        assert builder is not None

    def test_create_cpu_trend_visual_with_empty_data(self) -> None:
        """Test CPU trend visual creation with empty data."""
        builder = ChartBuilder()
        cpu_graph = {"datapoints": [], "current": 0, "average": 0, "max": 0}
        result = builder.create_cpu_trend_visual(cpu_graph)
        assert isinstance(result, dict)
        assert "type" in result

    def test_create_network_visual_with_empty_data(self) -> None:
        """Test network visual creation with empty data."""
        builder = ChartBuilder()
        network_in = {"datapoints": []}
        network_out = {"datapoints": []}
        result = builder.create_network_visual(network_in, network_out)
        assert isinstance(result, dict)
        assert "type" in result
