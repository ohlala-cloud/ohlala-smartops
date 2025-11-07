"""Chart and graph generation for health dashboards using Adaptive Cards.

This module provides functionality to create interactive visualizations for EC2 instance
health metrics using Microsoft Teams Adaptive Cards native charting capabilities.
Supports responsive design with desktop charts and mobile-friendly summaries.
"""

from datetime import datetime
from typing import Any, Final

import structlog

# Configure structured logging
logger: structlog.BoundLogger = structlog.get_logger(__name__)

# Chart color scheme constants
COLOR_USED: Final[str] = "categoricalMarigold"  # Orange tone for usage metrics
COLOR_FREE: Final[str] = "divergingYellow"  # Yellow tone for free/available resources
COLOR_PRIMARY: Final[str] = "categoricalMarigold"  # Primary metric color
COLOR_SECONDARY: Final[str] = "divergingYellow"  # Secondary metric color


class ChartBuilder:
    """Handles chart and graph generation for health visualizations.

    This class creates various types of charts using Microsoft Teams Adaptive Cards
    native charting components (Chart.Line and Chart.Pie). All charts include:
    - Desktop view with interactive charts
    - Mobile view with summary tables
    - Toggle-able raw data tables
    - Responsive layout with targetWidth

    Example:
        >>> builder = ChartBuilder()
        >>> cpu_data = {"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 45.2}]}
        >>> chart = builder.create_cpu_trend_visual(cpu_data)
    """

    def __init__(self) -> None:
        """Initialize the ChartBuilder."""
        self.logger = logger.bind(component="chart_builder")

    def create_cpu_trend_visual(self, cpu_graph: dict[str, Any]) -> dict[str, Any]:
        """Create a visual CPU trend using Chart.Line with collapsible raw data.

        Generates an interactive line chart showing CPU usage over time with:
        - Line chart for desktop (last 12 data points = 1 hour)
        - Summary facts for mobile devices
        - Toggle-able raw data table

        Args:
            cpu_graph: Dictionary containing CPU datapoints with structure:
                {
                    "datapoints": [
                        {"time": "2025-11-07T10:00:00Z", "value": 45.2},
                        ...
                    ]
                }

        Returns:
            Adaptive Card container with CPU trend visualization. Returns empty
            state message if no data available.

        Example:
            >>> cpu_data = {"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 45.2}]}
            >>> chart = builder.create_cpu_trend_visual(cpu_data)
        """
        datapoints = cpu_graph.get("datapoints", [])

        if not datapoints:
            self.logger.warning("no_cpu_data", message="No CPU data available for chart")
            return {
                "type": "TextBlock",
                "text": "No CPU data available",
                "horizontalAlignment": "Center",
                "isSubtle": True,
            }

        # Take last 12 data points for better mobile readability (1 hour of data)
        recent_points = datapoints[-12:] if len(datapoints) > 12 else datapoints

        # Format data for Chart.Line with proper time labels
        values: list[dict[str, float | str]] = []
        table_rows: list[dict[str, str]] = []  # For raw data table

        for dp in recent_points:
            y_value = dp.get("value", 0)
            # Ensure y value is a valid number
            if not isinstance(y_value, int | float) or y_value != y_value:  # Check for NaN
                y_value = 0

            # Format timestamp for x-axis
            timestamp = dp.get("time", "")
            if timestamp:
                # Extract just hour:minute from timestamp
                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    time_label = dt.strftime("%H:%M")
                except (ValueError, AttributeError) as e:
                    self.logger.warning("timestamp_parse_error", error=str(e), timestamp=timestamp)
                    time_label = str(len(values))
            else:
                time_label = str(len(values))

            values.append({"x": time_label, "y": float(round(y_value, 1))})

            # Add to table data
            table_rows.append({"Time": time_label, "CPU %": f"{round(y_value, 1)}%"})

        # Create the chart (visible on larger screens)
        chart: dict[str, Any] = {
            "type": "Chart.Line",
            "title": "CPU Usage Trend",
            "xAxisTitle": "Time",
            "yAxisTitle": "CPU %",
            "data": [{"legend": "CPU %", "values": values, "color": COLOR_PRIMARY}],
            "targetWidth": "AtLeast:Standard",  # Show chart on wider screens
            "id": "cpuChart",
        }

        # Calculate summary statistics
        avg_cpu = sum(v["y"] for v in values) / len(values) if values else 0
        max_cpu = max((v["y"] for v in values), default=0)
        latest_cpu = values[-1]["y"] if values else 0

        # Create summary for mobile (always visible)
        mobile_summary: dict[str, Any] = {
            "type": "Container",
            "targetWidth": "AtMost:Narrow",  # Show on narrow screens
            "items": [
                {
                    "type": "TextBlock",
                    "text": "CPU Usage Summary",
                    "weight": "Bolder",
                    "size": "Medium",
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Average", "value": f"{round(avg_cpu, 1)}%"},
                        {"title": "Peak", "value": f"{round(max_cpu, 1)}%"},
                        {"title": "Latest", "value": f"{latest_cpu}%"},
                    ],
                },
            ],
        }

        # Create toggle button for raw data
        toggle_button: dict[str, Any] = {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.ToggleVisibility",
                    "title": "📊 Show/Hide Raw Data",
                    "targetElements": ["cpuRawData"],
                }
            ],
        }

        # Create the raw data table (initially hidden)
        raw_data_table: dict[str, Any] = {
            "type": "Container",
            "id": "cpuRawData",
            "isVisible": False,  # Initially hidden
            "items": [
                {
                    "type": "TextBlock",
                    "text": "**CPU Usage Data**",
                    "weight": "Bolder",
                    "size": "Small",
                    "spacing": "Medium",
                },
                self.create_data_table(table_rows, ["Time", "CPU %"]),
            ],
        }

        # Combine all elements
        return {
            "type": "Container",
            "items": [
                chart,  # Chart for larger screens
                mobile_summary,  # Summary for mobile
                toggle_button,  # Toggle button
                raw_data_table,  # Hidden raw data table
            ],
        }

    def create_network_visual(
        self, network_in: dict[str, Any], network_out: dict[str, Any]
    ) -> dict[str, Any]:
        """Create network traffic visualization using Chart.Line with collapsible raw data.

        Generates a multi-series line chart showing network traffic in and out with:
        - Dual-line chart for desktop (last 12 data points = 1 hour)
        - Summary statistics for mobile devices
        - Toggle-able raw data table with combined in/out data

        Args:
            network_in: Dictionary containing network in datapoints:
                {"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 125.5}]}
            network_out: Dictionary containing network out datapoints:
                {"datapoints": [{"time": "2025-11-07T10:00:00Z", "value": 85.2}]}

        Returns:
            Adaptive Card container with network traffic visualization. Returns empty
            state message if no data available.
        """
        in_datapoints = network_in.get("datapoints", [])
        out_datapoints = network_out.get("datapoints", [])

        if not in_datapoints and not out_datapoints:
            self.logger.warning("no_network_data", message="No network data available for chart")
            return {
                "type": "TextBlock",
                "text": "No network data available",
                "horizontalAlignment": "Center",
                "isSubtle": True,
            }

        # Take last 12 data points for better mobile readability
        recent_in = in_datapoints[-12:] if len(in_datapoints) > 12 else in_datapoints
        recent_out = out_datapoints[-12:] if len(out_datapoints) > 12 else out_datapoints

        # Create data series for both in and out
        data: list[dict[str, Any]] = []
        time_data: dict[str, dict[str, str]] = {}  # To merge data by time

        in_values: list[dict[str, float | str]] = []
        if recent_in:
            for dp in recent_in:
                y_value = dp.get("value", 0)
                if not isinstance(y_value, int | float) or y_value != y_value:
                    y_value = 0

                # Format timestamp
                timestamp = dp.get("time", "")
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        time_label = dt.strftime("%H:%M")
                    except (ValueError, AttributeError) as e:
                        self.logger.warning(
                            "timestamp_parse_error", error=str(e), timestamp=timestamp
                        )
                        time_label = str(len(in_values))
                else:
                    time_label = str(len(in_values))

                in_values.append({"x": time_label, "y": float(round(y_value, 2))})

                # Add to merged table data
                if time_label not in time_data:
                    time_data[time_label] = {"Time": time_label, "In (MB)": "-", "Out (MB)": "-"}
                time_data[time_label]["In (MB)"] = f"{y_value:.2f}"

            data.append(
                {
                    "legend": "Network In (MB)",
                    "values": in_values,
                    "color": COLOR_PRIMARY,
                }
            )

        out_values: list[dict[str, float | str]] = []
        if recent_out:
            for dp in recent_out:
                y_value = dp.get("value", 0)
                if not isinstance(y_value, int | float) or y_value != y_value:
                    y_value = 0

                # Format timestamp
                timestamp = dp.get("time", "")
                if timestamp:
                    try:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        time_label = dt.strftime("%H:%M")
                    except (ValueError, AttributeError) as e:
                        self.logger.warning(
                            "timestamp_parse_error", error=str(e), timestamp=timestamp
                        )
                        time_label = str(len(out_values))
                else:
                    time_label = str(len(out_values))

                out_values.append({"x": time_label, "y": float(round(y_value, 2))})

                # Add to merged table data
                if time_label not in time_data:
                    time_data[time_label] = {"Time": time_label, "In (MB)": "-", "Out (MB)": "-"}
                time_data[time_label]["Out (MB)"] = f"{y_value:.2f}"

            data.append(
                {"legend": "Network Out (MB)", "values": out_values, "color": COLOR_SECONDARY}
            )

        table_rows = list(time_data.values())

        # Create the chart (visible on larger screens)
        chart: dict[str, Any] = {
            "type": "Chart.Line",
            "title": "Network Traffic",
            "xAxisTitle": "Time",
            "yAxisTitle": "MB",
            "data": data,
            "targetWidth": "AtLeast:Standard",  # Show chart on wider screens
            "id": "networkChart",
        }

        # Calculate summary statistics
        total_in = sum(v["y"] for v in in_values) if in_values else 0
        total_out = sum(v["y"] for v in out_values) if out_values else 0
        avg_in = total_in / len(in_values) if in_values else 0
        avg_out = total_out / len(out_values) if out_values else 0

        # Create summary for mobile (always visible)
        mobile_summary: dict[str, Any] = {
            "type": "Container",
            "targetWidth": "AtMost:Narrow",  # Show on narrow screens
            "items": [
                {
                    "type": "TextBlock",
                    "text": "Network Traffic Summary",
                    "weight": "Bolder",
                    "size": "Medium",
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Avg In", "value": f"{round(avg_in, 2)} MB"},
                        {"title": "Avg Out", "value": f"{round(avg_out, 2)} MB"},
                        {"title": "Total In", "value": f"{round(total_in, 2)} MB"},
                        {"title": "Total Out", "value": f"{round(total_out, 2)} MB"},
                    ],
                },
            ],
        }

        # Create toggle button for raw data
        toggle_button: dict[str, Any] = {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.ToggleVisibility",
                    "title": "📊 Show/Hide Raw Data",
                    "targetElements": ["networkRawData"],
                }
            ],
        }

        # Create the raw data table (initially hidden)
        raw_data_table: dict[str, Any] = {
            "type": "Container",
            "id": "networkRawData",
            "isVisible": False,  # Initially hidden
            "items": [
                {
                    "type": "TextBlock",
                    "text": "**Network Traffic Data**",
                    "weight": "Bolder",
                    "size": "Small",
                    "spacing": "Medium",
                },
                self.create_data_table(table_rows, ["Time", "In (MB)", "Out (MB)"]),
            ],
        }

        # Combine all elements
        return {
            "type": "Container",
            "items": [
                chart,  # Chart for larger screens
                mobile_summary,  # Summary for mobile
                toggle_button,  # Toggle button
                raw_data_table,  # Hidden raw data table
            ],
        }

    def create_memory_pie_chart(self, memory_data: dict[str, Any]) -> dict[str, Any]:
        """Create a pie chart for memory usage visualization.

        Generates an interactive pie chart showing memory usage with:
        - Pie chart for desktop
        - Fact set summary for mobile devices
        - Text summary below chart

        Args:
            memory_data: Dictionary containing memory information:
                {
                    "memory_used_mb": 4096.5,
                    "memory_total_mb": 16384.0,
                    "memory_percent": 25.0
                }

        Returns:
            Adaptive Card container with memory pie chart visualization. Returns
            empty state message if no data available.
        """
        # Extract memory values from SSM data
        memory_used_mb = memory_data.get("memory_used_mb", 0)
        memory_total_mb = memory_data.get("memory_total_mb", 0)
        memory_percent = memory_data.get("memory_percent", 0)

        if memory_total_mb <= 0:
            self.logger.warning("no_memory_data", message="No memory data available for chart")
            return {
                "type": "TextBlock",
                "text": "No memory data available",
                "horizontalAlignment": "Center",
                "isSubtle": True,
            }

        memory_free_mb = memory_total_mb - memory_used_mb

        # Ensure we have positive values for the pie chart
        if memory_used_mb <= 0:
            memory_used_mb = 0.1
        if memory_free_mb <= 0:
            memory_free_mb = 0.1

        # Create pie chart for memory usage
        pie_chart: dict[str, Any] = {
            "type": "Chart.Pie",
            "title": "Memory Usage",
            "data": [
                {
                    "legend": f"Used ({memory_used_mb:.1f} MB)",
                    "value": float(memory_used_mb),
                    "color": COLOR_USED,
                },
                {
                    "legend": f"Free ({memory_free_mb:.1f} MB)",
                    "value": float(memory_free_mb),
                    "color": COLOR_FREE,
                },
            ],
            "targetWidth": "AtLeast:Standard",  # Show chart on wider screens
        }

        # Create mobile fallback summary
        mobile_summary: dict[str, Any] = {
            "type": "Container",
            "targetWidth": "AtMost:Narrow",  # Show on narrow screens
            "items": [
                {"type": "TextBlock", "text": "**Memory Usage**", "weight": "Bolder"},
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Total", "value": f"{memory_total_mb:.1f} MB"},
                        {
                            "title": "Used",
                            "value": f"{memory_used_mb:.1f} MB ({memory_percent:.1f}%)",
                        },
                        {"title": "Free", "value": f"{memory_free_mb:.1f} MB"},
                    ],
                },
            ],
        }

        # Create summary text below pie chart
        summary_text: dict[str, Any] = {
            "type": "TextBlock",
            "text": f"{memory_used_mb:.1f} MB used of {memory_total_mb:.1f} MB ({memory_percent:.1f}%) • {memory_free_mb:.1f} MB available",
            "size": "Small",
            "isSubtle": True,
            "wrap": True,
            "spacing": "Small",
            "targetWidth": "AtLeast:Standard",
        }

        return {
            "type": "Container",
            "spacing": "Medium",
            "items": [
                pie_chart,  # Pie chart for desktop
                mobile_summary,  # Summary for mobile
                summary_text,  # Text summary below chart
            ],
        }

    def create_disk_pie_chart(self, disk_data: dict[str, Any]) -> dict[str, Any]:
        """Create pie charts for disk usage visualization.

        Generates pie charts for each mounted filesystem with:
        - Individual pie chart per disk/mount point
        - Mobile-friendly fact sets
        - Summary text with usage information

        Args:
            disk_data: Dictionary containing disk information:
                {
                    "disks": [
                        {
                            "Device": "/dev/sda1",
                            "Mount": "/",
                            "SizeGB": 100.0,
                            "UsedGB": 45.2,
                            "FreeGB": 54.8,
                            "UsedPercent": 45.2
                        },
                        ...
                    ]
                }

        Returns:
            Adaptive Card container with disk usage pie charts. Returns empty
            state message if no data available.
        """
        disks = disk_data.get("disks", [])

        if not disks:
            self.logger.warning("no_disk_data", message="No disk data available for chart")
            return {
                "type": "TextBlock",
                "text": "No disk data available",
                "horizontalAlignment": "Center",
                "isSubtle": True,
            }

        disk_containers: list[dict[str, Any]] = []

        for disk in disks:
            device = disk.get("Device", "Unknown")
            mount = disk.get("Mount", "/")
            size_gb = disk.get("SizeGB", 0)
            used_gb = disk.get("UsedGB", 0)
            free_gb = disk.get("FreeGB", 0)
            used_percent = disk.get("UsedPercent", 0)

            # Ensure we have positive values for the pie chart
            if used_gb <= 0:
                used_gb = 0.1
            if free_gb <= 0:
                free_gb = 0.1

            # Create pie chart for this disk
            pie_chart: dict[str, Any] = {
                "type": "Chart.Pie",
                "title": f"{device} ({mount})",
                "data": [
                    {
                        "legend": f"Used ({used_gb:.1f} GB)",
                        "value": float(used_gb),
                        "color": COLOR_USED,
                    },
                    {
                        "legend": f"Free ({free_gb:.1f} GB)",
                        "value": float(free_gb),
                        "color": COLOR_FREE,
                    },
                ],
                "targetWidth": "AtLeast:Standard",  # Show chart on wider screens
            }

            # Create mobile fallback summary
            mobile_summary: dict[str, Any] = {
                "type": "Container",
                "targetWidth": "AtMost:Narrow",  # Show on narrow screens
                "items": [
                    {"type": "TextBlock", "text": f"**{device} ({mount})**", "weight": "Bolder"},
                    {
                        "type": "FactSet",
                        "facts": [
                            {"title": "Total", "value": f"{size_gb:.1f} GB"},
                            {"title": "Used", "value": f"{used_gb:.1f} GB ({used_percent:.1f}%)"},
                            {"title": "Free", "value": f"{free_gb:.1f} GB"},
                        ],
                    },
                ],
            }

            # Create summary text below pie chart
            summary_text: dict[str, Any] = {
                "type": "TextBlock",
                "text": f"{used_gb:.1f} GB used of {size_gb:.1f} GB ({used_percent:.1f}%) • {free_gb:.1f} GB available",
                "size": "Small",
                "isSubtle": True,
                "wrap": True,
                "spacing": "Small",
                "targetWidth": "AtLeast:Standard",
            }

            # Combine chart with summary
            disk_containers.append(
                {
                    "type": "Container",
                    "spacing": "Medium",
                    "items": [
                        pie_chart,  # Pie chart for desktop
                        mobile_summary,  # Summary for mobile
                        summary_text,  # Text summary below chart
                    ],
                }
            )

        return {
            "type": "Container",
            "items": disk_containers,
            "separator": True,
            "spacing": "Large",
        }

    def create_data_table(self, rows: list[dict[str, str]], headers: list[str]) -> dict[str, Any]:
        """Create a mobile-friendly data table using Adaptive Cards ColumnSet.

        Generates a table with headers and data rows using ColumnSet components
        for proper alignment and mobile responsiveness.

        Args:
            rows: List of dictionaries where keys are column headers and values are cell data:
                [{"Time": "10:00", "CPU %": "45.2%"}, ...]
            headers: List of header names in display order:
                ["Time", "CPU %"]

        Returns:
            Adaptive Card Container with table layout using ColumnSets.

        Example:
            >>> rows = [{"Time": "10:00", "Value": "45.2"}]
            >>> headers = ["Time", "Value"]
            >>> table = builder.create_data_table(rows, headers)
        """
        # Create header row
        header_columns: list[dict[str, Any]] = []
        for header in headers:
            header_columns.append(
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"**{header}**",
                            "weight": "Bolder",
                            "horizontalAlignment": "Center",
                            "size": "Small",
                        }
                    ],
                }
            )

        table_items: list[dict[str, Any]] = [
            {"type": "ColumnSet", "columns": header_columns, "separator": True}
        ]

        # Create data rows
        for row in rows:
            row_columns: list[dict[str, Any]] = []
            for key in headers:  # Use headers to maintain column order
                value = row.get(key, "")
                row_columns.append(
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": str(value),
                                "horizontalAlignment": "Center",
                                "size": "Small",
                                "wrap": True,
                            }
                        ],
                    }
                )

            table_items.append({"type": "ColumnSet", "columns": row_columns, "spacing": "Small"})

        return {"type": "Container", "items": table_items, "spacing": "Small"}
