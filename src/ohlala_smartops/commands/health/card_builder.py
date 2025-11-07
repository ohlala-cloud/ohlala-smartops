"""Adaptive card generation for EC2 instance health dashboards.

This module provides comprehensive adaptive card generation for displaying EC2 instance
health metrics in Microsoft Teams. Supports both single-instance detailed dashboards
and multi-instance overview cards with responsive design for desktop and mobile.
"""

from datetime import UTC, datetime
from typing import Any, Final

import structlog

from ohlala_smartops.commands.health.chart_builder import ChartBuilder

# Configure structured logging
logger: structlog.BoundLogger = structlog.get_logger(__name__)

# Health status thresholds
CPU_WARNING_THRESHOLD: Final[float] = 80.0
CPU_CRITICAL_THRESHOLD: Final[float] = 90.0
MEMORY_WARNING_THRESHOLD: Final[float] = 80.0
MEMORY_CRITICAL_THRESHOLD: Final[float] = 90.0


class CardBuilder:
    """Handles adaptive card generation for health dashboards.

    This class builds comprehensive Microsoft Teams Adaptive Cards for displaying
    EC2 instance health metrics. Supports both detailed single-instance dashboards
    and multi-instance overview cards with drill-down capabilities.

    Example:
        >>> builder = CardBuilder()
        >>> instance_info = {"name": "web-server-1", "instance_id": "i-123", "type": "t3.micro"}
        >>> metrics = {
        ...     "cloudwatch_metrics": {...},
        ...     "system_metrics": {...},
        ...     "disk_usage": {...}
        ... }
        >>> card = builder.build_health_dashboard_card(instance_info, metrics)
    """

    def __init__(self, chart_builder: ChartBuilder | None = None) -> None:
        """Initialize the card builder.

        Args:
            chart_builder: ChartBuilder instance for creating visualizations.
                Creates new instance if None.
        """
        self.chart_builder = chart_builder or ChartBuilder()
        self.logger = logger.bind(component="card_builder")

    def build_health_dashboard_card(
        self,
        instance: dict[str, Any],
        metrics: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build comprehensive health dashboard card for a single instance.

        Creates a detailed adaptive card showing real-time metrics, performance trends,
        disk usage, system information, and recent errors for an EC2 instance.

        Args:
            instance: Instance information with keys:
                - name: Instance name
                - instance_id: EC2 instance ID
                - type: Instance type (e.g., "t3.micro")
            metrics: Dictionary containing:
                - cloudwatch_metrics: CloudWatch metrics data
                - system_metrics: Real-time SSM metrics
                - disk_usage: Disk usage information
                - system_logs: Recent error logs
                - system_info: System details
            context: Optional context dictionary (unused, kept for compatibility).

        Returns:
            Adaptive Card JSON dictionary ready for Teams.

        Example:
            >>> instance = {"name": "web-1", "instance_id": "i-123", "type": "t3.micro"}
            >>> metrics = {"cloudwatch_metrics": {...}, "system_metrics": {...}}
            >>> card = builder.build_health_dashboard_card(instance, metrics)
        """
        self.logger.info("building_health_dashboard", instance_id=instance.get("instance_id"))

        cw_metrics = metrics.get("cloudwatch_metrics", {})
        sys_metrics = metrics.get("system_metrics", {})
        disk_usage = metrics.get("disk_usage", {})
        logs = metrics.get("system_logs", {})
        sys_info = metrics.get("system_info", {})

        # Build card sections
        card_body: list[dict[str, Any]] = [
            # Header
            {
                "type": "TextBlock",
                "text": f"🏥 Health Dashboard: {instance['name']}",
                "size": "Large",
                "weight": "Bolder",
            },
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"**Instance:** {instance['instance_id']}",
                                "wrap": True,
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": f"**Type:** {instance['type']}",
                                "horizontalAlignment": "Right",
                            }
                        ],
                    },
                ],
                "spacing": "Small",
            },
        ]

        # System Metrics Overview
        if sys_metrics or cw_metrics:
            card_body.extend(self._build_system_metrics_section(sys_metrics))

        # Memory Usage Pie Chart
        if sys_metrics and not sys_metrics.get("ssm_unavailable"):
            card_body.extend(self._build_memory_usage_section(sys_metrics))

        # CloudWatch Performance Trends
        if cw_metrics.get("success") and (
            cw_metrics.get("cpu_graph", {}).get("datapoints")
            or cw_metrics.get("network_in", {}).get("datapoints")
            or cw_metrics.get("network_out", {}).get("datapoints")
        ):
            card_body.extend(self._build_performance_trends_section(cw_metrics))

        # Disk Usage
        if disk_usage.get("disks"):
            card_body.extend(self._build_disk_usage_section(disk_usage))

        # EBS Metrics
        if cw_metrics.get("ebs_metrics"):
            card_body.extend(self._build_ebs_metrics_section(cw_metrics))

        # System Information
        if sys_info:
            self.logger.info("building_system_info_section")
            card_body.extend(self._build_system_info_section(sys_info))

        # Recent Errors
        if logs.get("error_logs"):
            card_body.extend(self._build_error_logs_section(logs))
        elif logs.get("error_logs_text"):
            card_body.extend(self._build_error_logs_text_section(logs))

        # Timestamp
        card_body.append(
            {
                "type": "TextBlock",
                "text": f"Last updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "size": "Small",
                "isSubtle": True,
                "horizontalAlignment": "Right",
                "spacing": "Large",
            }
        )

        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": card_body,
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "🔄 Refresh",
                    "data": {"action": "health_check", "instanceId": instance["instance_id"]},
                }
            ],
            "msteams": {"width": "Full"},
        }

    def build_overview_card(
        self,
        instances: list[dict[str, Any]],
        summaries: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build health overview card for all instances.

        Creates a summary card showing health status for all EC2 instances with
        drill-down capability to individual instance dashboards.

        Args:
            instances: List of instance dictionaries with instance details.
            summaries: List of health summary dictionaries for each instance.
            context: Optional context dictionary (unused, kept for compatibility).

        Returns:
            Adaptive Card JSON dictionary ready for Teams.

        Example:
            >>> instances = [{"instance_id": "i-123", "name": "web-1", "state": "running"}]
            >>> summaries = [{"instance_id": "i-123", "cpu_percent": 45, "status": "healthy"}]
            >>> card = builder.build_overview_card(instances, summaries)
        """
        self.logger.info("building_overview_card", instance_count=len(instances))

        # Create lookup for summaries
        summary_lookup = {s["instance_id"]: s for s in summaries if s}

        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "🏥 EC2 Health Overview",
                "size": "Large",
                "weight": "Bolder",
            },
            {
                "type": "TextBlock",
                "text": f"Monitoring {len(instances)} instances | Last updated: {datetime.now(UTC).strftime('%H:%M:%S UTC')}",
                "isSubtle": True,
                "spacing": "Small",
            },
        ]

        # Group instances by status
        healthy: list[tuple[str, str, float, float, str]] = []
        warning: list[tuple[str, str, float, float, str]] = []
        critical: list[tuple[str, str, float, float, str]] = []
        stopped: list[tuple[str, str, str]] = []

        for instance in instances:
            # Handle both lowercase and uppercase keys
            inst_id = instance.get("instance_id") or instance.get("InstanceId")
            name = instance.get("name") or instance.get("Name", inst_id)
            state = instance.get("state") or instance.get("State", "unknown")

            if state != "running":
                stopped.append((name, inst_id, state))
            else:
                summary = summary_lookup.get(inst_id, {})
                status = summary.get("status", "unknown")
                cpu = summary.get("cpu_percent", summary.get("cpu", 0))
                memory = summary.get("memory_percent", 0)
                data_source = summary.get("data_source", "ssm")

                instance_info = (name, inst_id, cpu, memory, data_source)

                if status == "critical" or cpu >= CPU_CRITICAL_THRESHOLD:
                    critical.append(instance_info)
                elif status == "warning" or cpu >= CPU_WARNING_THRESHOLD:
                    warning.append(instance_info)
                else:
                    healthy.append(instance_info)

        # Show summary counts
        card_body.extend(self._build_status_summary_section(healthy, warning, critical, stopped))

        # Show all instances with drill-down buttons
        card_body.extend(self._build_instances_list_section(critical, warning, healthy, stopped))

        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": card_body,
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "🔄 Refresh Overview",
                    "data": {"action": "health_dashboard"},
                }
            ],
            "msteams": {"width": "Full"},
        }

    def _build_system_metrics_section(self, sys_metrics: dict[str, Any]) -> list[dict[str, Any]]:
        """Build system metrics section with real-time OS metrics.

        Args:
            sys_metrics: System metrics dictionary from SSM.

        Returns:
            List of adaptive card elements for system metrics section.
        """
        # Check if SSM is unavailable
        if sys_metrics.get("ssm_unavailable"):
            return [
                {
                    "type": "Container",
                    "separator": True,
                    "spacing": "Large",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "⚠️ **System Metrics (Limited)**",
                            "size": "Medium",
                            "weight": "Bolder",
                            "color": "Warning",
                        },
                        {
                            "type": "Container",
                            "style": "warning",
                            "bleed": True,
                            "spacing": "Small",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": sys_metrics.get(
                                        "error", "SSM not available for real-time OS metrics"
                                    ),
                                    "wrap": True,
                                    "size": "Small",
                                    "spacing": "Small",
                                },
                                {
                                    "type": "TextBlock",
                                    "text": "ℹ️ **Note:** Showing CloudWatch metrics instead. These may have a 5-minute delay.",
                                    "wrap": True,
                                    "size": "Small",
                                    "weight": "Bolder",
                                    "spacing": "Small",
                                },
                            ],
                        },
                    ],
                }
            ]

        # Normalize metrics keys
        normalized = self._normalize_metrics_keys(sys_metrics)

        return [
            {
                "type": "Container",
                "separator": True,
                "spacing": "Large",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "📊 **Real-time System Metrics**",
                        "size": "Medium",
                        "weight": "Bolder",
                    },
                    {
                        "type": "TextBlock",
                        "text": "_(OS) = Direct from Operating System • (CW) = CloudWatch Metrics_",
                        "size": "Small",
                        "isSubtle": True,
                        "wrap": True,
                    },
                    {
                        "type": "ColumnSet",
                        "spacing": "Medium",
                        "columns": [
                            # CPU Column
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "**CPU Usage** (OS)",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": f"{normalized.get('CPU', 0):.1f}%",
                                        "size": "ExtraLarge",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                        "color": self._get_metric_color(normalized.get("CPU", 0)),
                                    },
                                ],
                            },
                            # Memory Column
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "**Memory Usage** (OS)",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": f"{normalized.get('MemoryPercent', 0):.1f}%",
                                        "size": "ExtraLarge",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                        "color": self._get_metric_color(
                                            normalized.get("MemoryPercent", 0)
                                        ),
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": f"{normalized.get('MemoryUsedMB', 0):.0f} / {normalized.get('MemoryTotalMB', 0):.0f} MB",
                                        "size": "Small",
                                        "horizontalAlignment": "Center",
                                        "isSubtle": True,
                                    },
                                ],
                            },
                            # Processes Column
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "**Processes** (OS)",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": (
                                            str(normalized.get("ProcessCount", "N/A"))
                                            if normalized.get("ProcessCount") is not None
                                            else "N/A"
                                        ),
                                        "size": "ExtraLarge",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                ],
                            },
                            # Uptime Column
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "**Uptime** (OS)",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": str(normalized.get("UptimeDays", "N/A")),
                                        "size": "Large",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                ],
                            },
                        ],
                    },
                ],
            }
        ]

    def _build_memory_usage_section(self, sys_metrics: dict[str, Any]) -> list[dict[str, Any]]:
        """Build memory usage section with pie chart.

        Args:
            sys_metrics: System metrics dictionary.

        Returns:
            List of adaptive card elements for memory section.
        """
        memory_used_mb = sys_metrics.get("memory_used_mb", 0)
        memory_total_mb = sys_metrics.get("memory_total_mb", 0)
        memory_percent = sys_metrics.get("memory_percent", 0)

        # Skip if no valid memory data
        if not memory_total_mb or memory_total_mb <= 0:
            return []

        return [
            {
                "type": "Container",
                "separator": True,
                "spacing": "Large",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "🧠 **Memory Usage** (OS)",
                        "size": "Medium",
                        "weight": "Bolder",
                    },
                    {
                        "type": "TextBlock",
                        "text": "Real-time memory utilization from Systems Manager",
                        "size": "Small",
                        "isSubtle": True,
                        "wrap": True,
                    },
                    self.chart_builder.create_memory_pie_chart(
                        {
                            "memory_used_mb": memory_used_mb,
                            "memory_total_mb": memory_total_mb,
                            "memory_percent": memory_percent,
                        }
                    ),
                ],
            }
        ]

    def _build_performance_trends_section(self, cw_metrics: dict[str, Any]) -> list[dict[str, Any]]:
        """Build performance trends section with CloudWatch charts.

        Args:
            cw_metrics: CloudWatch metrics dictionary.

        Returns:
            List of adaptive card elements for performance trends.
        """
        cpu_graph = cw_metrics["cpu_graph"]
        network_in = cw_metrics.get("network_in", {})
        network_out = cw_metrics.get("network_out", {})

        return [
            {
                "type": "Container",
                "separator": True,
                "spacing": "Large",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "📈 **Performance Trends (6 Hours)** (CW)",
                        "size": "Medium",
                        "weight": "Bolder",
                    },
                    # CPU Chart
                    {
                        "type": "Container",
                        "spacing": "Medium",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "**CPU Usage**",
                                "horizontalAlignment": "Center",
                                "weight": "Bolder",
                            },
                            self.chart_builder.create_cpu_trend_visual(cpu_graph),
                            {
                                "type": "ColumnSet",
                                "spacing": "Small",
                                "columns": [
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": f"Current: {cpu_graph.get('current', 0):.1f}%",
                                                "horizontalAlignment": "Center",
                                                "size": "Small",
                                            }
                                        ],
                                    },
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": f"Avg: {cpu_graph.get('avg', 0):.1f}%",
                                                "horizontalAlignment": "Center",
                                                "size": "Small",
                                            }
                                        ],
                                    },
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": f"Max: {cpu_graph.get('max', 0):.1f}%",
                                                "horizontalAlignment": "Center",
                                                "size": "Small",
                                            }
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    # Network Chart
                    {
                        "type": "Container",
                        "separator": True,
                        "spacing": "Medium",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "**Network Traffic**",
                                "horizontalAlignment": "Center",
                                "weight": "Bolder",
                            },
                            self.chart_builder.create_network_visual(network_in, network_out),
                            {
                                "type": "ColumnSet",
                                "spacing": "Small",
                                "columns": [
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": f"In: {network_in.get('total_mb', 0):.1f} MB",
                                                "horizontalAlignment": "Center",
                                                "size": "Small",
                                            }
                                        ],
                                    },
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": f"Out: {network_out.get('total_mb', 0):.1f} MB",
                                                "horizontalAlignment": "Center",
                                                "size": "Small",
                                            }
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            }
        ]

    def _build_disk_usage_section(self, disk_usage: dict[str, Any]) -> list[dict[str, Any]]:
        """Build disk usage section with pie charts.

        Args:
            disk_usage: Disk usage dictionary.

        Returns:
            List of adaptive card elements for disk usage.
        """
        if not disk_usage.get("disks") or disk_usage.get("ssm_unavailable"):
            return []

        header = {
            "type": "Container",
            "separator": True,
            "spacing": "Large",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "💾 **Storage Usage** (OS)",
                    "size": "Medium",
                    "weight": "Bolder",
                },
                {
                    "type": "TextBlock",
                    "text": "Visual breakdown of disk usage across mounted filesystems",
                    "size": "Small",
                    "isSubtle": True,
                    "wrap": True,
                },
            ],
        }

        disk_charts = self.chart_builder.create_disk_pie_chart(disk_usage)

        return [header, disk_charts]

    def _build_ebs_metrics_section(self, cw_metrics: dict[str, Any]) -> list[dict[str, Any]]:
        """Build EBS metrics section with I/O statistics.

        Args:
            cw_metrics: CloudWatch metrics containing EBS data.

        Returns:
            List of adaptive card elements for EBS metrics.
        """
        ebs_data = cw_metrics.get("ebs_metrics", {})
        ebs_aggregated = ebs_data.get("aggregated", {}) if ebs_data else {}

        read_iops = ebs_aggregated.get("avg_read_iops", 0)
        write_iops = ebs_aggregated.get("avg_write_iops", 0)
        # Note: read_mbps and write_mbps available in aggregated if needed in future

        return [
            {
                "type": "Container",
                "separator": True,
                "spacing": "Large",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "💾 **Disk I/O Statistics (6 Hours)** (EBS)",
                        "size": "Medium",
                        "weight": "Bolder",
                    },
                    {
                        "type": "ColumnSet",
                        "spacing": "Medium",
                        "columns": [
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "📖 **Read IOPS**",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": f"{read_iops:.1f}",
                                        "size": "Large",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": "ops/sec",
                                        "size": "Small",
                                        "horizontalAlignment": "Center",
                                        "isSubtle": True,
                                    },
                                ],
                            },
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "✍️ **Write IOPS**",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": f"{write_iops:.1f}",
                                        "size": "Large",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": "ops/sec",
                                        "size": "Small",
                                        "horizontalAlignment": "Center",
                                        "isSubtle": True,
                                    },
                                ],
                            },
                        ],
                    },
                ],
            }
        ]

    def _build_system_info_section(self, sys_info: dict[str, Any]) -> list[dict[str, Any]]:
        """Build system information section.

        Args:
            sys_info: System information dictionary.

        Returns:
            List of adaptive card elements for system info.
        """
        if sys_info.get("ssm_unavailable") and not sys_info.get("success"):
            return []

        # Handle both dict and Pydantic model
        os_version = (
            sys_info.get("OSVersion", "Unknown")
            if isinstance(sys_info, dict)
            else getattr(sys_info, "OSVersion", "Unknown")
        )
        last_boot = (
            sys_info.get("LastBoot", "Unknown")
            if isinstance(sys_info, dict)
            else getattr(sys_info, "LastBoot", "Unknown")
        )
        cpu_name = (
            sys_info.get("CPUName", "Unknown")
            if isinstance(sys_info, dict)
            else getattr(sys_info, "CPUName", "Unknown")
        )
        cpu_cores = (
            sys_info.get("CPUCores", 0)
            if isinstance(sys_info, dict)
            else getattr(sys_info, "CPUCores", 0)
        )
        running_services = (
            sys_info.get("RunningServices", 0)
            if isinstance(sys_info, dict)
            else getattr(sys_info, "RunningServices", 0)
        )

        return [
            {
                "type": "Container",
                "separator": True,
                "spacing": "Large",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "ℹ️ **System Information** (OS)",
                        "size": "Medium",
                        "weight": "Bolder",
                    },
                    {
                        "type": "Container",
                        "style": "emphasis",
                        "bleed": True,
                        "spacing": "Medium",
                        "items": [
                            {
                                "type": "ColumnSet",
                                "columns": [
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": "**Operating System**",
                                                "size": "Small",
                                                "isSubtle": True,
                                            },
                                            {
                                                "type": "TextBlock",
                                                "text": os_version[:50],
                                                "wrap": True,
                                                "spacing": "None",
                                            },
                                        ],
                                    },
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": "**Last Boot**",
                                                "size": "Small",
                                                "isSubtle": True,
                                            },
                                            {
                                                "type": "TextBlock",
                                                "text": last_boot,
                                                "spacing": "None",
                                            },
                                        ],
                                    },
                                ],
                            },
                            {
                                "type": "ColumnSet",
                                "spacing": "Medium",
                                "columns": [
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": "**CPU Information**",
                                                "size": "Small",
                                                "isSubtle": True,
                                            },
                                            {
                                                "type": "TextBlock",
                                                "text": f"{cpu_name[:30]}",
                                                "wrap": True,
                                                "spacing": "None",
                                            },
                                            {
                                                "type": "TextBlock",
                                                "text": f"{cpu_cores} cores",
                                                "size": "Small",
                                                "spacing": "None",
                                                "isSubtle": True,
                                            },
                                        ],
                                    },
                                    {
                                        "type": "Column",
                                        "width": "stretch",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": "**Services Status**",
                                                "size": "Small",
                                                "isSubtle": True,
                                            },
                                            {
                                                "type": "TextBlock",
                                                "text": f"{running_services} running",
                                                "spacing": "None",
                                                "color": "Good",
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            }
        ]

    def _build_error_logs_section(self, logs: dict[str, Any]) -> list[dict[str, Any]]:
        """Build error logs section.

        Args:
            logs: Logs dictionary with error_logs list.

        Returns:
            List of adaptive card elements for error logs.
        """
        error_logs = logs.get("error_logs", [])
        sections: list[dict[str, Any]] = [
            {
                "type": "Container",
                "separator": True,
                "spacing": "Large",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "🚨 **Recent System Errors** (OS)",
                        "size": "Medium",
                        "weight": "Bolder",
                        "color": "Attention",
                    }
                ],
            }
        ]

        error_container: dict[str, Any] = {
            "type": "Container",
            "style": "attention",
            "bleed": True,
            "spacing": "Medium",
            "items": [],
        }

        # Show up to 5 recent errors
        for i, log in enumerate(error_logs[:5]):
            # Handle both dict and Pydantic model
            time_str = log.get("Time", "") if isinstance(log, dict) else getattr(log, "Time", "")
            source = log.get("Source", "") if isinstance(log, dict) else getattr(log, "Source", "")
            message = (
                log.get("Message", "") if isinstance(log, dict) else getattr(log, "Message", "")
            )
            message = message[:200]

            if message:
                error_item = {
                    "type": "Container",
                    "separator": i > 0,
                    "spacing": "Small",
                    "items": [
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "⚠️",
                                            "size": "Medium",
                                            "color": "Attention",
                                        }
                                    ],
                                },
                                {
                                    "type": "Column",
                                    "width": "stretch",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": f"{time_str} {source}".strip(),
                                            "weight": "Bolder",
                                            "size": "Small",
                                            "wrap": True,
                                        },
                                        {
                                            "type": "TextBlock",
                                            "text": message,
                                            "wrap": True,
                                            "size": "Small",
                                            "spacing": "None",
                                            "isSubtle": True,
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
                error_container["items"].append(error_item)

        if error_container["items"]:
            sections.append(error_container)

        return sections

    def _build_error_logs_text_section(self, logs: dict[str, Any]) -> list[dict[str, Any]]:
        """Build error logs text fallback section.

        Args:
            logs: Logs dictionary with error_logs_text.

        Returns:
            List of adaptive card elements for error logs text.
        """
        return [
            {
                "type": "Container",
                "separator": True,
                "spacing": "Large",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "🚨 **Recent System Activity**",
                        "size": "Medium",
                        "weight": "Bolder",
                    },
                    {
                        "type": "TextBlock",
                        "text": logs["error_logs_text"][:500],
                        "wrap": True,
                        "fontType": "Monospace",
                        "size": "Small",
                        "spacing": "Small",
                    },
                ],
            }
        ]

    def _build_status_summary_section(
        self,
        healthy: list[tuple],
        warning: list[tuple],
        critical: list[tuple],
        stopped: list[tuple],
    ) -> list[dict[str, Any]]:
        """Build status summary section for overview card.

        Args:
            healthy: List of healthy instance tuples.
            warning: List of warning instance tuples.
            critical: List of critical instance tuples.
            stopped: List of stopped instance tuples.

        Returns:
            List of adaptive card elements for status summary.
        """
        return [
            {
                "type": "Container",
                "separator": True,
                "spacing": "Medium",
                "items": [
                    {
                        "type": "ColumnSet",
                        "columns": [
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "🟢 Healthy",
                                        "horizontalAlignment": "Center",
                                        "color": "Good",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": str(len(healthy)),
                                        "size": "ExtraLarge",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                ],
                            },
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "🟡 Warning",
                                        "horizontalAlignment": "Center",
                                        "color": "Warning",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": str(len(warning)),
                                        "size": "ExtraLarge",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                ],
                            },
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "🔴 Critical",
                                        "horizontalAlignment": "Center",
                                        "color": "Attention",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": str(len(critical)),
                                        "size": "ExtraLarge",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                ],
                            },
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "⚫ Stopped",
                                        "horizontalAlignment": "Center",
                                        "color": "Dark",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": str(len(stopped)),
                                        "size": "ExtraLarge",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                ],
                            },
                        ],
                    }
                ],
            }
        ]

    def _build_instances_list_section(
        self,
        critical: list[tuple],
        warning: list[tuple],
        healthy: list[tuple],
        stopped: list[tuple],
    ) -> list[dict[str, Any]]:
        """Build instances list section for overview card.

        Args:
            critical: List of critical instance tuples.
            warning: List of warning instance tuples.
            healthy: List of healthy instance tuples.
            stopped: List of stopped instance tuples.

        Returns:
            List of adaptive card elements for instances list.
        """
        sections: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "📋 **All Instances**",
                "weight": "Bolder",
                "spacing": "Large",
            },
            {
                "type": "TextBlock",
                "text": "💡 Click 'View Details' to see comprehensive health dashboard with CPU graphs, memory, disk usage, logs, and more.",
                "size": "Small",
                "isSubtle": True,
                "wrap": True,
                "spacing": "Small",
            },
        ]

        # Show critical instances first
        for instance_info in critical:
            name, inst_id, cpu, memory, data_source = instance_info
            metrics_text = f"CPU: {cpu:.1f}%"
            if memory > 0:
                metrics_text += f" | Memory: {memory:.1f}%"
            metrics_text += f" | Status: Critical ({data_source.upper()})"
            sections.append(
                self._create_instance_row("🔴", name, metrics_text, "Attention", inst_id)
            )

        # Show warning instances
        for instance_info in warning:
            name, inst_id, cpu, memory, data_source = instance_info
            metrics_text = f"CPU: {cpu:.1f}%"
            if memory > 0:
                metrics_text += f" | Memory: {memory:.1f}%"
            metrics_text += f" | Status: Warning ({data_source.upper()})"
            sections.append(self._create_instance_row("🟡", name, metrics_text, "Warning", inst_id))

        # Show healthy instances
        for instance_info in healthy:
            name, inst_id, cpu, memory, data_source = instance_info
            metrics_text = f"CPU: {cpu:.1f}%"
            if memory > 0:
                metrics_text += f" | Memory: {memory:.1f}%"
            metrics_text += f" | Status: Healthy ({data_source.upper()})"
            sections.append(self._create_instance_row("🟢", name, metrics_text, "Good", inst_id))

        # Show stopped instances
        for name, _inst_id, state in stopped:
            sections.append(
                self._create_instance_row("⚫", name, f"State: {state}", "Dark", None, False)
            )

        return sections

    def _create_instance_row(
        self,
        emoji: str,
        name: str,
        status_text: str,
        color: str,
        inst_id: str | None = None,
        show_button: bool = True,
    ) -> dict[str, Any]:
        """Create an instance row with status container.

        Args:
            emoji: Status emoji.
            name: Instance name.
            status_text: Status description text.
            color: Adaptive card color (Good, Warning, Attention, Dark).
            inst_id: Instance ID for drill-down (optional).
            show_button: Whether to show View Details button.

        Returns:
            Adaptive card container for instance row.
        """
        container_style = "default"
        if color == "Attention":
            container_style = "attention"
        elif color == "Warning":
            container_style = "warning"
        elif color == "Good":
            container_style = "good"

        columns: list[dict[str, Any]] = [
            {
                "type": "Column",
                "width": "auto",
                "items": [{"type": "TextBlock", "text": emoji, "size": "Medium"}],
            },
            {
                "type": "Column",
                "width": "stretch",
                "items": [
                    {"type": "TextBlock", "text": name, "weight": "Bolder"},
                    {
                        "type": "TextBlock",
                        "text": status_text,
                        "size": "Small",
                        "isSubtle": True,
                    },
                ],
            },
        ]

        if show_button and inst_id:
            columns.append(
                {
                    "type": "Column",
                    "width": "auto",
                    "items": [
                        {
                            "type": "ActionSet",
                            "actions": [
                                {
                                    "type": "Action.Submit",
                                    "title": "View Details",
                                    "data": {"action": "health_check", "instanceId": inst_id},
                                }
                            ],
                        }
                    ],
                }
            )

        return {
            "type": "Container",
            "style": container_style,
            "bleed": True,
            "spacing": "Small",
            "items": [{"type": "ColumnSet", "columns": columns}],
        }

    def _get_metric_color(self, value: float) -> str:
        """Get color based on metric value.

        Args:
            value: Metric value (percentage).

        Returns:
            Adaptive card color string.
        """
        if value >= CPU_CRITICAL_THRESHOLD:
            return "Attention"
        if value >= CPU_WARNING_THRESHOLD:
            return "Warning"
        return "Good"

    def _normalize_metrics_keys(self, sys_metrics: dict[str, Any]) -> dict[str, Any]:
        """Normalize metrics keys to expected format.

        Handles various key formats from different metric sources.

        Args:
            sys_metrics: Raw system metrics dictionary.

        Returns:
            Normalized metrics dictionary with consistent keys.
        """
        if not sys_metrics:
            return {}

        normalized: dict[str, Any] = {}

        # CPU
        cpu_val = sys_metrics.get("cpu_percent", sys_metrics.get("CPU", 0))
        normalized["CPU"] = cpu_val if isinstance(cpu_val, int | float) else 0

        # Memory
        mem_val = sys_metrics.get("memory_percent", sys_metrics.get("MemoryPercent", 0))
        normalized["MemoryPercent"] = mem_val if isinstance(mem_val, int | float) else 0

        # Process count
        proc_val = sys_metrics.get("processes", sys_metrics.get("ProcessCount"))
        normalized["ProcessCount"] = proc_val if proc_val is not None else None

        # Memory totals
        normalized["MemoryUsedMB"] = sys_metrics.get("memory_used_mb", 0)
        normalized["MemoryTotalMB"] = sys_metrics.get("memory_total_mb", 0)

        # Uptime
        normalized["UptimeDays"] = sys_metrics.get(
            "uptime_text", sys_metrics.get("UptimeDays", "N/A")
        )

        # Load average
        normalized["LoadAverage"] = sys_metrics.get(
            "load_average", sys_metrics.get("LoadAverage", "N/A")
        )

        return normalized
