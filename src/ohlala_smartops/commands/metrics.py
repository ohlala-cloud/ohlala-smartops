"""Metrics command - Display CloudWatch metrics for EC2 instances.

This module provides the MetricsCommand that visualizes CloudWatch metrics
over time for specific EC2 instances, helping with performance monitoring
and troubleshooting.

Phase 5C: Monitoring & Information commands.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.adaptive_cards import CardTemplates
from ohlala_smartops.commands.base import BaseCommand

logger: Final = logging.getLogger(__name__)


class MetricsCommand(BaseCommand):
    """Handler for /metrics command - Display CloudWatch metrics.

    Shows CloudWatch metrics for an instance over a specified time period:
    - CPU Utilization
    - Network In/Out
    - Disk Read/Write Bytes
    - Statistics: Min, Max, Average

    Supports multiple duration options:
    - 1h (default): Last 1 hour
    - 6h: Last 6 hours
    - 24h: Last 24 hours
    - 7d: Last 7 days

    Example:
        >>> cmd = MetricsCommand()
        >>> result = await cmd.execute(["i-1234567890abcdef0", "6h"], context)
        >>> print(result["card"])  # Metrics visualization card
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "metrics"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Display CloudWatch metrics for an EC2 instance"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/metrics <instance-id> [duration] - Show metrics (1h, 6h, 24h, 7d)"

    # Duration mapping to seconds
    DURATION_MAP: Final[dict[str, int]] = {
        "1h": 3600,  # 1 hour
        "6h": 21600,  # 6 hours
        "24h": 86400,  # 24 hours
        "7d": 604800,  # 7 days
    }

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute metrics command.

        Args:
            args: Command arguments (instance ID required, duration optional).
            context: Execution context containing:
                - mcp_manager: MCPManager instance

        Returns:
            Command result with adaptive card showing metrics.

        Example:
            >>> result = await cmd.execute(["i-1234567890abcdef0", "6h"], context)
            >>> if result["success"]:
            ...     print("Metrics retrieved")
        """
        try:
            # Parse arguments
            instance_id = self.parse_instance_id(args)

            if not instance_id:
                return {
                    "success": False,
                    "message": "❌ Please provide an instance ID.\n\n" f"Usage: {self.usage}",
                }

            # Parse duration (default: 1h)
            duration_str = "1h"
            for arg in args:
                if arg.lower() in self.DURATION_MAP:
                    duration_str = arg.lower()
                    break

            duration_seconds = self.DURATION_MAP[duration_str]

            # Validate instance exists
            validation_result = await self.validate_instances_exist([instance_id], context)

            if not validation_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {validation_result['error']}",
                }

            instance = validation_result["instances"][0]
            instance_name = instance.get("Name", instance_id)

            # Get metrics data
            try:
                metrics_data = await self._get_metrics(instance_id, duration_seconds, context)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to retrieve metrics: {e!s}",
                    "card": self.create_error_card(
                        "Metrics Unavailable",
                        f"Unable to retrieve CloudWatch metrics for {instance_id}. "
                        "The instance may not have monitoring enabled or metrics "
                        "may not be available yet.\n\n"
                        f"Error: {e!s}",
                    ),
                }

            # Build metrics card
            card = self._build_metrics_card(instance_id, instance_name, duration_str, metrics_data)

            return {
                "success": True,
                "message": f"Metrics for {instance_name} ({duration_str})",
                "card": card,
            }

        except Exception as e:
            self.logger.error(f"Error getting metrics: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get metrics: {e!s}",
                "card": self.create_error_card(
                    "Failed to Get Metrics",
                    f"Unable to retrieve metrics: {e!s}",
                ),
            }

    async def _get_metrics(
        self, instance_id: str, period: int, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Get CloudWatch metrics for instance.

        Args:
            instance_id: EC2 instance ID.
            period: Time period in seconds.
            context: Execution context.

        Returns:
            Dictionary with metric data.
        """
        result = await self.call_mcp_tool(
            "get-instance-metrics",
            {
                "InstanceId": instance_id,
                "Period": period,
                "Statistics": ["Minimum", "Maximum", "Average"],
            },
            context,
        )

        metrics = result.get("metrics", {})
        return metrics if isinstance(metrics, dict) else {}

    def _build_metrics_card(
        self,
        instance_id: str,
        instance_name: str,
        duration: str,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """Build metrics visualization card.

        Args:
            instance_id: EC2 instance ID.
            instance_name: Instance name.
            duration: Duration string (e.g., "1h", "6h").
            metrics: Metrics data from CloudWatch.

        Returns:
            Adaptive card dictionary.
        """
        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"📊 Metrics: {instance_name}",
                "size": "Large",
                "weight": "Bolder",
                "color": "Accent",
            },
            {
                "type": "TextBlock",
                "text": f"Instance ID: {instance_id} • Duration: {duration}",
                "spacing": "None",
                "isSubtle": True,
            },
        ]

        # Check if we have any metrics
        if not metrics or all(not v for v in metrics.values()):
            card_body.append(
                {
                    "type": "Container",
                    "style": "warning",
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "⚠️ No Metrics Available",
                            "weight": "Bolder",
                        },
                        {
                            "type": "TextBlock",
                            "text": "CloudWatch metrics are not available for this instance. "
                            "This may be because:\n\n"
                            "• Detailed monitoring is not enabled\n"
                            "• The instance was recently launched\n"
                            "• Metrics have not been collected yet",
                            "wrap": True,
                        },
                    ],
                }
            )
        else:
            # CPU Utilization
            if "CPUUtilization" in metrics:
                card_body.append(
                    self._build_metric_section("CPUUtilization", "CPU Utilization", "%", metrics)
                )

            # Network In
            if "NetworkIn" in metrics:
                card_body.append(
                    self._build_metric_section(
                        "NetworkIn", "Network In", "bytes", metrics, convert_bytes=True
                    )
                )

            # Network Out
            if "NetworkOut" in metrics:
                card_body.append(
                    self._build_metric_section(
                        "NetworkOut",
                        "Network Out",
                        "bytes",
                        metrics,
                        convert_bytes=True,
                    )
                )

            # Disk Read Bytes
            if "DiskReadBytes" in metrics:
                card_body.append(
                    self._build_metric_section(
                        "DiskReadBytes",
                        "Disk Read",
                        "bytes",
                        metrics,
                        convert_bytes=True,
                    )
                )

            # Disk Write Bytes
            if "DiskWriteBytes" in metrics:
                card_body.append(
                    self._build_metric_section(
                        "DiskWriteBytes",
                        "Disk Write",
                        "bytes",
                        metrics,
                        convert_bytes=True,
                    )
                )

        # Refresh action
        card_body.append(
            {
                "type": "ActionSet",
                "separator": True,
                "spacing": "Large",
                "actions": [
                    {
                        "type": "Action.Submit",
                        "title": "🔄 Refresh",
                        "data": {
                            "action": "metrics",
                            "instanceId": instance_id,
                            "duration": duration,
                        },
                    }
                ],
            }
        )

        return {"type": "AdaptiveCard", "version": "1.5", "body": card_body}

    def _build_metric_section(
        self,
        metric_name: str,
        display_name: str,
        unit: str,
        metrics: dict[str, Any],
        convert_bytes: bool = False,
    ) -> dict[str, Any]:
        """Build a section for a specific metric.

        Args:
            metric_name: CloudWatch metric name.
            display_name: Display name for the metric.
            unit: Unit string.
            metrics: All metrics data.
            convert_bytes: Whether to convert bytes to human-readable format.

        Returns:
            Container with metric visualization.
        """
        metric_data = metrics.get(metric_name, {})
        minimum = metric_data.get("Minimum", 0.0)
        maximum = metric_data.get("Maximum", 0.0)
        average = metric_data.get("Average", 0.0)

        # Convert bytes if needed
        if convert_bytes:
            minimum_str = self._format_bytes(minimum)
            maximum_str = self._format_bytes(maximum)
            average_str = self._format_bytes(average)
        else:
            minimum_str = f"{minimum:.2f}{unit}"
            maximum_str = f"{maximum:.2f}{unit}"
            average_str = f"{average:.2f}{unit}"

        # Create gauge for average if it's a percentage
        gauge_columns: list[dict[str, Any]] = []

        if unit == "%":
            # For CPU, create visual gauge
            gauge_columns.append(
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [CardTemplates.create_metric_gauge(display_name, average)],
                }
            )
        else:
            # For other metrics, show as text
            gauge_columns.append(
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": display_name,
                            "weight": "Bolder",
                            "size": "Medium",
                        },
                        {
                            "type": "TextBlock",
                            "text": f"Average: {average_str}",
                            "spacing": "Small",
                        },
                    ],
                }
            )

        # Statistics table
        stats_facts: dict[str, str | int | float] = {
            "Minimum": minimum_str,
            "Maximum": maximum_str,
            "Average": average_str,
        }

        return {
            "type": "Container",
            "separator": True,
            "spacing": "Medium",
            "items": [
                {"type": "ColumnSet", "columns": gauge_columns},
                CardTemplates.create_fact_set(stats_facts),
            ],
        }

    def _format_bytes(self, bytes_value: float) -> str:
        """Format bytes into human-readable format.

        Args:
            bytes_value: Value in bytes.

        Returns:
            Formatted string (e.g., "1.5 MB", "234 KB").
        """
        if bytes_value < 1024:
            return f"{bytes_value:.0f} B"
        if bytes_value < 1024 * 1024:
            return f"{bytes_value / 1024:.2f} KB"
        if bytes_value < 1024 * 1024 * 1024:
            return f"{bytes_value / (1024 * 1024):.2f} MB"
        return f"{bytes_value / (1024 * 1024 * 1024):.2f} GB"
