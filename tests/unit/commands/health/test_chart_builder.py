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
        assert result["type"] == "TextBlock"
        assert "No CPU data available" in result["text"]

    def test_create_cpu_trend_visual_with_valid_data(self) -> None:
        """Test CPU trend visual creation with valid data."""
        builder = ChartBuilder()
        cpu_graph = {
            "datapoints": [
                {"time": "2025-11-07T10:00:00Z", "value": 45.2},
                {"time": "2025-11-07T10:05:00Z", "value": 50.0},
                {"time": "2025-11-07T10:10:00Z", "value": 55.5},
            ],
            "current": 55.5,
            "average": 50.2,
            "max": 55.5,
        }
        result = builder.create_cpu_trend_visual(cpu_graph)
        assert isinstance(result, dict)
        assert "type" in result
        assert result["type"] == "Container"
        assert "items" in result

    def test_create_cpu_trend_visual_with_nan_values(self) -> None:
        """Test CPU trend visual handles NaN values."""
        builder = ChartBuilder()
        cpu_graph = {
            "datapoints": [
                {"time": "2025-11-07T10:00:00Z", "value": float("nan")},
                {"time": "2025-11-07T10:05:00Z", "value": 50.0},
            ],
            "current": 50.0,
            "average": 50.0,
            "max": 50.0,
        }
        result = builder.create_cpu_trend_visual(cpu_graph)
        assert isinstance(result, dict)
        assert result["type"] == "Container"

    def test_create_cpu_trend_visual_with_many_datapoints(self) -> None:
        """Test CPU trend visual with more than 12 datapoints."""
        builder = ChartBuilder()
        datapoints = [
            {"time": f"2025-11-07T{10 + i // 12:02d}:{(i % 12) * 5:02d}:00Z", "value": 40 + i}
            for i in range(20)
        ]
        cpu_graph = {"datapoints": datapoints, "current": 59, "average": 50, "max": 59}
        result = builder.create_cpu_trend_visual(cpu_graph)
        assert isinstance(result, dict)
        assert result["type"] == "Container"

    def test_create_cpu_trend_visual_with_invalid_timestamps(self) -> None:
        """Test CPU trend visual handles invalid timestamps."""
        builder = ChartBuilder()
        cpu_graph = {
            "datapoints": [
                {"time": "invalid-timestamp", "value": 45.2},
                {"time": "", "value": 50.0},
            ],
            "current": 50.0,
            "average": 47.6,
            "max": 50.0,
        }
        result = builder.create_cpu_trend_visual(cpu_graph)
        assert isinstance(result, dict)
        assert result["type"] == "Container"

    def test_create_network_visual_with_empty_data(self) -> None:
        """Test network visual creation with empty data."""
        builder = ChartBuilder()
        network_in = {"datapoints": []}
        network_out = {"datapoints": []}
        result = builder.create_network_visual(network_in, network_out)
        assert isinstance(result, dict)
        assert "type" in result
        assert result["type"] == "TextBlock"

    def test_create_network_visual_with_valid_data(self) -> None:
        """Test network visual creation with valid data."""
        builder = ChartBuilder()
        network_in = {
            "datapoints": [
                {"time": "2025-11-07T10:00:00Z", "value": 1024},
                {"time": "2025-11-07T10:05:00Z", "value": 2048},
            ]
        }
        network_out = {
            "datapoints": [
                {"time": "2025-11-07T10:00:00Z", "value": 512},
                {"time": "2025-11-07T10:05:00Z", "value": 768},
            ]
        }
        result = builder.create_network_visual(network_in, network_out)
        assert isinstance(result, dict)
        assert result["type"] == "Container"

    def test_create_network_visual_with_nan_values(self) -> None:
        """Test network visual handles NaN values."""
        builder = ChartBuilder()
        network_in = {
            "datapoints": [
                {"time": "2025-11-07T10:00:00Z", "value": float("nan")},
                {"time": "2025-11-07T10:05:00Z", "value": 2048},
            ]
        }
        network_out = {
            "datapoints": [
                {"time": "2025-11-07T10:00:00Z", "value": 512},
                {"time": "2025-11-07T10:05:00Z", "value": float("nan")},
            ]
        }
        result = builder.create_network_visual(network_in, network_out)
        assert isinstance(result, dict)
        assert result["type"] == "Container"

    def test_create_memory_pie_chart_with_valid_data(self) -> None:
        """Test memory pie chart creation with valid data."""
        builder = ChartBuilder()
        memory_data = {
            "memory_used_mb": 12800,
            "memory_total_mb": 16384,
            "memory_percent": 78.1,
        }
        result = builder.create_memory_pie_chart(memory_data)
        assert isinstance(result, dict)
        assert result["type"] == "Container"
        assert "items" in result
        assert len(result["items"]) == 3  # pie chart, mobile summary, summary text

    def test_create_memory_pie_chart_with_no_data(self) -> None:
        """Test memory pie chart with no data."""
        builder = ChartBuilder()
        memory_data = {}
        result = builder.create_memory_pie_chart(memory_data)
        assert isinstance(result, dict)
        assert result["type"] == "TextBlock"
        assert "No memory data available" in result["text"]

    def test_create_memory_pie_chart_with_zero_total(self) -> None:
        """Test memory pie chart with zero total memory."""
        builder = ChartBuilder()
        memory_data = {"memory_used_mb": 0, "memory_total_mb": 0, "memory_percent": 0}
        result = builder.create_memory_pie_chart(memory_data)
        assert isinstance(result, dict)
        assert result["type"] == "TextBlock"

    def test_create_disk_pie_chart_with_valid_data(self) -> None:
        """Test disk pie chart creation with valid data."""
        builder = ChartBuilder()
        disk_data = {
            "disks": [
                {
                    "Device": "/dev/sda1",
                    "Mount": "/",
                    "SizeGB": 500,
                    "UsedGB": 150,
                    "FreeGB": 350,
                    "UsedPercent": 30.0,
                }
            ]
        }
        result = builder.create_disk_pie_chart(disk_data)
        assert isinstance(result, dict)
        assert result["type"] == "Container"
        assert "items" in result
        assert len(result["items"]) == 1  # One disk

    def test_create_disk_pie_chart_with_multiple_disks(self) -> None:
        """Test disk pie chart with multiple disks."""
        builder = ChartBuilder()
        disk_data = {
            "disks": [
                {
                    "Device": "/dev/sda1",
                    "Mount": "/",
                    "SizeGB": 500,
                    "UsedGB": 150,
                    "FreeGB": 350,
                    "UsedPercent": 30.0,
                },
                {
                    "Device": "/dev/sdb1",
                    "Mount": "/data",
                    "SizeGB": 1000,
                    "UsedGB": 400,
                    "FreeGB": 600,
                    "UsedPercent": 40.0,
                },
            ]
        }
        result = builder.create_disk_pie_chart(disk_data)
        assert isinstance(result, dict)
        assert result["type"] == "Container"
        assert len(result["items"]) == 2  # Two disks

    def test_create_disk_pie_chart_with_no_disks(self) -> None:
        """Test disk pie chart with no disks."""
        builder = ChartBuilder()
        disk_data = {"disks": []}
        result = builder.create_disk_pie_chart(disk_data)
        assert isinstance(result, dict)
        assert result["type"] == "TextBlock"
        assert "No disk data available" in result["text"]

    def test_create_data_table_with_valid_data(self) -> None:
        """Test data table creation with valid data."""
        builder = ChartBuilder()
        rows = [{"Time": "10:00", "CPU %": "45.2"}, {"Time": "10:05", "CPU %": "50.0"}]
        headers = ["Time", "CPU %"]
        result = builder.create_data_table(rows, headers)
        assert isinstance(result, dict)
        assert result["type"] == "Container"
        assert "items" in result
        assert len(result["items"]) == 3  # header + 2 rows

    def test_create_data_table_with_empty_rows(self) -> None:
        """Test data table with empty rows."""
        builder = ChartBuilder()
        rows: list[dict[str, str]] = []
        headers = ["Time", "CPU %"]
        result = builder.create_data_table(rows, headers)
        assert isinstance(result, dict)
        assert result["type"] == "Container"
        assert len(result["items"]) == 1  # header only
