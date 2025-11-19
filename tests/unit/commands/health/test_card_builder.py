"""Unit tests for CardBuilder."""

import sys
from unittest.mock import MagicMock

# Mock structlog to avoid Python 3.13 compatibility issues with zope.interface
sys.modules["structlog"] = MagicMock()

from ohlala_smartops.commands.health.card_builder import CardBuilder  # noqa: E402
from ohlala_smartops.commands.health.chart_builder import ChartBuilder  # noqa: E402


class TestCardBuilder:
    """Test suite for CardBuilder."""

    def test_card_builder_initialization(self) -> None:
        """Test that CardBuilder can be initialized."""
        builder = CardBuilder()
        assert builder is not None
        assert isinstance(builder.chart_builder, ChartBuilder)

    def test_card_builder_with_custom_chart_builder(self) -> None:
        """Test CardBuilder with custom ChartBuilder."""
        chart_builder = ChartBuilder()
        builder = CardBuilder(chart_builder=chart_builder)
        assert builder.chart_builder is chart_builder

    def test_build_health_dashboard_card_with_full_metrics(self) -> None:
        """Test building health dashboard card with complete metrics."""
        builder = CardBuilder()
        instance = {
            "name": "web-server-1",
            "instance_id": "i-1234567890abcdef0",
            "type": "t3.micro",
            "state": "running",
        }
        metrics = {
            "cloudwatch_metrics": {
                "cpu_graph": {
                    "datapoints": [
                        {"time": "2025-11-07T10:00:00Z", "value": 45.2},
                        {"time": "2025-11-07T10:05:00Z", "value": 50.0},
                    ],
                    "current": 50.0,
                    "average": 47.6,
                    "max": 50.0,
                },
                "network_in": {"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 1024}]},
                "network_out": {"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 512}]},
                "ebs_read": {"datapoints": [], "average": 0},
                "ebs_write": {"datapoints": [], "average": 0},
            },
            "system_metrics": {
                "cpu_percent": 45.5,
                "memory_used_mb": 1024,
                "memory_total_mb": 4096,
                "memory_percent": 25.0,
                "process_count": 120,
            },
            "disk_usage": {
                "disks": [
                    {
                        "Device": "/dev/sda1",
                        "Mount": "/",
                        "SizeGB": 100,
                        "UsedGB": 30,
                        "FreeGB": 70,
                        "UsedPercent": 30.0,
                    }
                ]
            },
            "system_logs": {
                "logs": [{"timestamp": "2025-11-07 10:00:00", "message": "Error occurred"}]
            },
            "system_info": {"os": "Ubuntu 22.04", "kernel": "5.15.0", "uptime": "5 days"},
        }
        context = {"region": "us-east-1"}

        card = builder.build_health_dashboard_card(instance, metrics, context)

        assert card is not None
        assert card["type"] == "AdaptiveCard"
        assert "body" in card
        assert len(card["body"]) > 0

    def test_build_health_dashboard_card_with_minimal_metrics(self) -> None:
        """Test building health dashboard card with minimal metrics."""
        builder = CardBuilder()
        instance = {"name": "test-instance", "instance_id": "i-test123", "type": "t3.nano"}
        metrics = {}  # Empty metrics

        card = builder.build_health_dashboard_card(instance, metrics)

        assert card is not None
        assert card["type"] == "AdaptiveCard"
        assert "body" in card

    def test_build_health_dashboard_card_with_high_cpu(self) -> None:
        """Test building dashboard card with high CPU usage (critical threshold)."""
        builder = CardBuilder()
        instance = {"name": "cpu-intensive", "instance_id": "i-high", "type": "c5.large"}
        metrics = {
            "system_metrics": {
                "cpu_percent": 95.0,  # Above critical threshold
                "memory_percent": 50.0,
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)

        assert card is not None
        assert "body" in card

    def test_build_health_dashboard_card_with_high_memory(self) -> None:
        """Test building dashboard card with high memory usage."""
        builder = CardBuilder()
        instance = {"name": "memory-intensive", "instance_id": "i-mem", "type": "r5.large"}
        metrics = {
            "system_metrics": {
                "cpu_percent": 30.0,
                "memory_percent": 85.0,  # Above warning threshold
                "memory_used_mb": 13568,
                "memory_total_mb": 16384,
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)

        assert card is not None
        assert "body" in card

    def test_build_overview_card_with_multiple_instances(self) -> None:
        """Test building overview card with multiple instances."""
        builder = CardBuilder()
        instances = [
            {"instance_id": "i-running1", "name": "web-1", "type": "t3.micro", "state": "running"},
            {"instance_id": "i-running2", "name": "web-2", "type": "t3.micro", "state": "running"},
        ]
        summaries = [
            {
                "instance_id": "i-running1",
                "cpu_avg": 45.5,
                "memory_percent": 60.0,
                "status": "healthy",
            },
            {
                "instance_id": "i-running2",
                "cpu_avg": 85.5,  # High CPU
                "memory_percent": 70.0,
                "status": "warning",
            },
        ]
        context = {"region": "us-east-1"}

        card = builder.build_overview_card(instances, summaries, context)

        assert card is not None
        assert card["type"] == "AdaptiveCard"
        assert "body" in card

    def test_build_overview_card_with_empty_summaries(self) -> None:
        """Test building overview card with no instances."""
        builder = CardBuilder()
        instances = []
        summaries = []
        context = {"region": "us-east-1"}

        card = builder.build_overview_card(instances, summaries, context)

        assert card is not None
        assert card["type"] == "AdaptiveCard"

    def test_build_overview_card_with_single_instance(self) -> None:
        """Test building overview card with a single instance."""
        builder = CardBuilder()
        instances = [
            {
                "instance_id": "i-single",
                "name": "single-instance",
                "type": "t3.small",
                "state": "running",
            }
        ]
        summaries = [
            {
                "instance_id": "i-single",
                "cpu_avg": 30.0,
                "memory_percent": 40.0,
                "status": "healthy",
            }
        ]

        card = builder.build_overview_card(instances, summaries, {})

        assert card is not None
        assert "body" in card

    def test_get_metric_color_healthy(self) -> None:
        """Test _get_metric_color returns green for healthy values."""
        builder = CardBuilder()
        color = builder._get_metric_color(50.0)
        assert color == "Good"

    def test_get_metric_color_warning(self) -> None:
        """Test _get_metric_color returns yellow for warning values."""
        builder = CardBuilder()
        color = builder._get_metric_color(85.0)
        assert color == "Warning"

    def test_get_metric_color_critical(self) -> None:
        """Test _get_metric_color returns red for critical values."""
        builder = CardBuilder()
        color = builder._get_metric_color(95.0)
        assert color == "Attention"

    def test_normalize_metrics_keys(self) -> None:
        """Test _normalize_metrics_keys normalizes metric key names."""
        builder = CardBuilder()
        sys_metrics = {
            "cpu_percent": 45.5,
            "memory_used_mb": 1024,
            "memory_total_mb": 4096,
            "process_count": 120,
        }

        normalized = builder._normalize_metrics_keys(sys_metrics)

        assert "CPU" in normalized
        assert "MemoryUsedMB" in normalized or "MemoryPercent" in normalized
        assert "ProcessCount" in normalized
        assert normalized["CPU"] == 45.5

    def test_build_health_dashboard_card_with_error_logs(self) -> None:
        """Test dashboard card with error logs section."""
        builder = CardBuilder()
        instance = {"name": "server", "instance_id": "i-logs", "type": "t3.micro"}
        metrics = {
            "system_logs": {
                "logs": [
                    {"timestamp": "2025-11-07 10:00:00", "message": "Error 1"},
                    {"timestamp": "2025-11-07 10:05:00", "message": "Error 2"},
                ]
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)

        assert card is not None
        assert "body" in card

    def test_build_health_dashboard_card_with_ebs_metrics(self) -> None:
        """Test dashboard card with EBS metrics."""
        builder = CardBuilder()
        instance = {"name": "storage-server", "instance_id": "i-ebs", "type": "i3.large"}
        metrics = {
            "cloudwatch_metrics": {
                "ebs_read": {
                    "datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 1024}],
                    "average": 1024,
                },
                "ebs_write": {
                    "datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 512}],
                    "average": 512,
                },
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)

        assert card is not None
        assert "body" in card

    def test_build_health_dashboard_card_with_network_metrics(self) -> None:
        """Test dashboard card with network metrics."""
        builder = CardBuilder()
        instance = {"name": "net-server", "instance_id": "i-net", "type": "t3.large"}
        metrics = {
            "cloudwatch_metrics": {
                "cpu_graph": {"datapoints": [], "current": 0, "average": 0, "max": 0},
                "network_in": {
                    "datapoints": [
                        {"time": "2025-11-07T10:00:00Z", "value": 2048},
                        {"time": "2025-11-07T10:05:00Z", "value": 3072},
                    ]
                },
                "network_out": {
                    "datapoints": [
                        {"time": "2025-11-07T10:00:00Z", "value": 1024},
                        {"time": "2025-11-07T10:05:00Z", "value": 1536},
                    ]
                },
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None
        assert "body" in card

    def test_build_health_dashboard_card_with_multiple_disks(self) -> None:
        """Test dashboard card with multiple disk volumes."""
        builder = CardBuilder()
        instance = {"name": "storage", "instance_id": "i-storage", "type": "m5.large"}
        metrics = {
            "disk_usage": {
                "disks": [
                    {
                        "Device": "/dev/sda1",
                        "Mount": "/",
                        "SizeGB": 100,
                        "UsedGB": 30,
                        "FreeGB": 70,
                        "UsedPercent": 30.0,
                    },
                    {
                        "Device": "/dev/sdb1",
                        "Mount": "/data",
                        "SizeGB": 500,
                        "UsedGB": 200,
                        "FreeGB": 300,
                        "UsedPercent": 40.0,
                    },
                    {
                        "Device": "/dev/sdc1",
                        "Mount": "/backup",
                        "SizeGB": 1000,
                        "UsedGB": 850,
                        "FreeGB": 150,
                        "UsedPercent": 85.0,
                    },
                ]
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None

    def test_build_health_dashboard_card_with_detailed_system_info(self) -> None:
        """Test dashboard card with detailed system information."""
        builder = CardBuilder()
        instance = {"name": "app-server", "instance_id": "i-app", "type": "c5.xlarge"}
        metrics = {"system_info": {"os": "Ubuntu 22.04", "kernel": "5.15", "uptime": "15 days"}}

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None

    def test_build_health_dashboard_card_with_many_error_logs(self) -> None:
        """Test dashboard card with many error log entries."""
        builder = CardBuilder()
        instance = {"name": "error-prone", "instance_id": "i-errors", "type": "t3.micro"}
        logs = [
            {"timestamp": f"2025-11-07 10:{i:02d}:00", "message": f"Error {i}"} for i in range(15)
        ]
        metrics = {"system_logs": {"logs": logs}}

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None

    def test_build_overview_card_with_varied_statuses(self) -> None:
        """Test overview card with instances having different health statuses."""
        builder = CardBuilder()
        instances = [
            {
                "instance_id": "i-healthy",
                "name": "healthy-1",
                "type": "t3.micro",
                "state": "running",
            },
            {
                "instance_id": "i-warning",
                "name": "warning-1",
                "type": "t3.small",
                "state": "running",
            },
            {
                "instance_id": "i-critical",
                "name": "critical-1",
                "type": "t3.medium",
                "state": "running",
            },
        ]
        summaries = [
            {
                "instance_id": "i-healthy",
                "cpu_avg": 30.0,
                "memory_percent": 40.0,
                "status": "healthy",
            },
            {
                "instance_id": "i-warning",
                "cpu_avg": 82.0,
                "memory_percent": 75.0,
                "status": "warning",
            },
            {
                "instance_id": "i-critical",
                "cpu_avg": 95.0,
                "memory_percent": 92.0,
                "status": "critical",
            },
        ]

        card = builder.build_overview_card(instances, summaries, {})
        assert card is not None

    def test_build_health_dashboard_card_with_all_sections(self) -> None:
        """Test dashboard card with all possible sections populated."""
        builder = CardBuilder()
        instance = {"name": "complete-server", "instance_id": "i-complete", "type": "m5.2xlarge"}
        metrics = {
            "cloudwatch_metrics": {
                "cpu_graph": {
                    "datapoints": [
                        {"time": f"2025-11-07T10:{i:02d}:00Z", "value": 40 + i * 2}
                        for i in range(10)
                    ],
                    "current": 58.0,
                    "average": 49.0,
                    "max": 58.0,
                },
                "network_in": {"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 5120}]},
                "network_out": {"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 2560}]},
                "ebs_read": {
                    "datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 2048}],
                    "average": 2048,
                },
                "ebs_write": {
                    "datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 1024}],
                    "average": 1024,
                },
            },
            "system_metrics": {
                "cpu_percent": 58.0,
                "memory_used_mb": 24576,
                "memory_total_mb": 32768,
                "memory_percent": 75.0,
                "process_count": 250,
            },
            "disk_usage": {
                "disks": [
                    {
                        "Device": "/dev/nvme0n1p1",
                        "Mount": "/",
                        "SizeGB": 200,
                        "UsedGB": 80,
                        "FreeGB": 120,
                        "UsedPercent": 40.0,
                    }
                ]
            },
            "system_logs": {
                "logs": [{"timestamp": "2025-11-07 10:00:00", "message": "Connection timeout"}]
            },
            "system_info": {"os": "Amazon Linux 2023", "kernel": "6.1.0", "uptime": "30 days"},
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None
        assert len(card["body"]) > 5

    def test_build_health_dashboard_card_with_error_logs_key(self) -> None:
        """Test dashboard card with error_logs key (not logs)."""
        builder = CardBuilder()
        instance = {"name": "server", "instance_id": "i-logs2", "type": "t3.micro"}
        metrics = {
            "system_logs": {
                "error_logs": [
                    {"Time": "2025-11-07 10:00:00", "Source": "kernel", "Message": "Error 1"},
                    {"Time": "2025-11-07 10:05:00", "Source": "systemd", "Message": "Error 2"},
                    {"Time": "2025-11-07 10:10:00", "Source": "app", "Message": "Error 3"},
                ]
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None
        assert "body" in card

    def test_build_health_dashboard_card_with_long_error_messages(self) -> None:
        """Test dashboard card with very long error messages (truncation)."""
        builder = CardBuilder()
        instance = {"name": "server", "instance_id": "i-long-err", "type": "t3.micro"}
        long_message = "Error: " + "x" * 300  # 306 chars, should be truncated to 200
        metrics = {
            "system_logs": {
                "error_logs": [{"Time": "2025-11-07 10:00:00", "Message": long_message}]
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None

    def test_build_health_dashboard_card_with_six_error_logs(self) -> None:
        """Test dashboard card with 6 error logs (only 5 should be shown)."""
        builder = CardBuilder()
        instance = {"name": "server", "instance_id": "i-six-errors", "type": "t3.micro"}
        metrics = {
            "system_logs": {
                "error_logs": [{"Time": f"10:{i:02d}", "Message": f"Error {i}"} for i in range(6)]
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None

    def test_build_health_dashboard_card_with_empty_error_message(self) -> None:
        """Test dashboard card with empty error message."""
        builder = CardBuilder()
        instance = {"name": "server", "instance_id": "i-empty", "type": "t3.micro"}
        metrics = {
            "system_logs": {
                "error_logs": [
                    {"Time": "2025-11-07 10:00:00", "Message": ""},  # Empty message
                    {"Time": "2025-11-07 10:05:00", "Message": "Real error"},
                ]
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None

    def test_build_health_dashboard_card_with_zero_memory_total(self) -> None:
        """Test dashboard card with zero total memory."""
        builder = CardBuilder()
        instance = {"name": "server", "instance_id": "i-zero-mem", "type": "t3.micro"}
        metrics = {
            "system_metrics": {
                "memory_used_mb": 100,
                "memory_total_mb": 0,  # Zero total
                "memory_percent": 0,
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None

    def test_build_overview_card_with_missing_instance_data(self) -> None:
        """Test overview card when summary has no matching instance."""
        builder = CardBuilder()
        instances = [
            {"instance_id": "i-exists", "name": "exists", "type": "t3.micro", "state": "running"}
        ]
        summaries = [
            {
                "instance_id": "i-missing",
                "cpu_avg": 50.0,
                "status": "healthy",
            }  # No matching instance
        ]

        card = builder.build_overview_card(instances, summaries, {})
        assert card is not None

    def test_build_health_dashboard_card_with_empty_disk_list(self) -> None:
        """Test dashboard card with explicitly empty disk list."""
        builder = CardBuilder()
        instance = {"name": "server", "instance_id": "i-no-disks", "type": "t3.micro"}
        metrics = {"disk_usage": {"disks": []}}  # Explicitly empty

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None

    def test_build_health_dashboard_card_with_high_disk_usage(self) -> None:
        """Test dashboard card with very high disk usage (>90%)."""
        builder = CardBuilder()
        instance = {"name": "server", "instance_id": "i-full-disk", "type": "t3.micro"}
        metrics = {
            "disk_usage": {
                "disks": [
                    {
                        "Device": "/dev/sda1",
                        "Mount": "/",
                        "SizeGB": 100,
                        "UsedGB": 95,
                        "FreeGB": 5,
                        "UsedPercent": 95.0,  # Very high
                    }
                ]
            }
        }

        card = builder.build_health_dashboard_card(instance, metrics)
        assert card is not None
