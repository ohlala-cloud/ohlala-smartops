"""Reusable Adaptive Card templates and components.

This module provides reusable components for building consistent adaptive cards
throughout the application. Templates include instance cards, metric gauges,
action buttons, and more.
"""

from typing import Any, Final

from .styles import get_platform_icon, get_status_color

logger: Final = __import__("logging").getLogger(__name__)


class CardTemplates:
    """Collection of reusable Adaptive Card templates and components."""

    @staticmethod
    def create_instance_card(
        instance_id: str,
        name: str,
        instance_type: str,
        state: str,
        platform: str,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        """Create an instance summary card.

        Args:
            instance_id: EC2 instance ID.
            name: Instance name (from Name tag).
            instance_type: EC2 instance type (e.g., "t3.micro").
            state: Instance state (e.g., "running", "stopped").
            platform: Platform (e.g., "Linux", "Windows").
            ip_address: Optional IP address (private or public).

        Returns:
            Adaptive card container dictionary.

        Example:
            >>> card = CardTemplates.create_instance_card(
            ...     "i-1234567890abcdef0",
            ...     "web-server-01",
            ...     "t3.micro",
            ...     "running",
            ...     "Linux",
            ...     "10.0.1.50"
            ... )
        """
        # Determine state color
        state_color = get_status_color(state)

        # Platform icon
        platform_icon = get_platform_icon(platform)

        card_body: list[dict[str, Any]] = [
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": platform_icon,
                                "size": "ExtraLarge",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": name or instance_id,
                                "weight": "Bolder",
                                "size": "Large",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"{instance_type} • {instance_id}",
                                "spacing": "None",
                                "isSubtle": True,
                            },
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": state.upper(),
                                "weight": "Bolder",
                                "color": state_color,
                            }
                        ],
                    },
                ],
            }
        ]

        # Add IP address if available
        if ip_address:
            card_body.append(
                {
                    "type": "TextBlock",
                    "text": f"IP: {ip_address}",
                    "spacing": "Small",
                    "isSubtle": True,
                }
            )

        return {
            "type": "Container",
            "style": "emphasis" if state.lower() == "running" else "default",
            "items": card_body,
        }

    @staticmethod
    def create_action_button(
        title: str,
        action: str,
        instance_id: str,
        style: str = "default",
        icon: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create an action button for adaptive cards.

        Args:
            title: Button text.
            action: Action identifier (e.g., "start_instance").
            instance_id: EC2 instance ID.
            style: Button style ("default", "positive", "destructive").
            icon: Optional emoji icon.
            **kwargs: Additional data to include in button payload.

        Returns:
            Adaptive card action button dictionary.

        Example:
            >>> button = CardTemplates.create_action_button(
            ...     "Start",
            ...     "start_instance",
            ...     "i-1234567890abcdef0",
            ...     style="positive",
            ...     icon="▶️"
            ... )
        """
        button_title = f"{icon} {title}" if icon else title

        data: dict[str, Any] = {"action": action, "instanceId": instance_id}
        data.update(kwargs)

        button: dict[str, Any] = {
            "type": "Action.Submit",
            "title": button_title,
            "data": data,
        }

        if style == "positive":
            button["style"] = "positive"
        elif style == "destructive":
            button["style"] = "destructive"

        return button

    @staticmethod
    def create_fact_set(facts: dict[str, str | int | float]) -> dict[str, Any]:
        """Create a fact set from a dictionary.

        Args:
            facts: Dictionary of facts (key-value pairs).

        Returns:
            Adaptive card FactSet dictionary.

        Example:
            >>> fact_set = CardTemplates.create_fact_set({
            ...     "Instance ID": "i-1234567890abcdef0",
            ...     "Instance Type": "t3.micro",
            ...     "State": "running"
            ... })
        """
        return {
            "type": "FactSet",
            "facts": [{"title": key, "value": str(value)} for key, value in facts.items()],
        }

    @staticmethod
    def create_metric_gauge(
        title: str,
        value: float,
        unit: str = "%",
        max_value: float = 100,
    ) -> dict[str, Any]:
        """Create a metric gauge component using text-based visualization.

        Args:
            title: Metric name (e.g., "CPU", "Memory").
            value: Current value.
            unit: Unit string (default "%").
            max_value: Maximum value for percentage calculation (default 100).

        Returns:
            Adaptive card column with metric gauge.

        Example:
            >>> gauge = CardTemplates.create_metric_gauge("CPU", 45.5)
        """
        # Create a text-based progress bar
        bar_length = 10
        filled_length = int((value / max_value) * bar_length)
        empty_length = bar_length - filled_length

        # Create the progress bar
        progress_bar = "█" * filled_length + "░" * empty_length

        # Determine colors
        if value < 60:
            status_color = "Good"
        elif value < 80:
            status_color = "Warning"
        else:
            status_color = "Attention"

        return {
            "type": "Column",
            "width": "stretch",
            "items": [
                {
                    "type": "TextBlock",
                    "text": title,
                    "weight": "Bolder",
                    "horizontalAlignment": "Center",
                    "size": "Small",
                },
                {
                    "type": "TextBlock",
                    "text": progress_bar,
                    "horizontalAlignment": "Center",
                    "color": status_color,
                    "fontType": "Monospace",
                    "size": "Medium",
                },
                {
                    "type": "TextBlock",
                    "text": f"{value:.1f}{unit}",
                    "horizontalAlignment": "Center",
                    "color": status_color,
                    "size": "Small",
                    "weight": "Bolder",
                },
            ],
        }

    @staticmethod
    def create_state_summary(
        state_counts: dict[str, int],
    ) -> dict[str, Any]:
        """Create a state summary visualization.

        Args:
            state_counts: Dictionary mapping states to counts.

        Returns:
            Adaptive card container with state summary.

        Example:
            >>> summary = CardTemplates.create_state_summary({
            ...     "running": 5,
            ...     "stopped": 2,
            ...     "pending": 1
            ... })
        """
        state_columns: list[dict[str, Any]] = []

        # State icons
        state_icons = {
            "running": "🟢",
            "stopped": "🔴",
            "pending": "🟡",
            "stopping": "🟡",
            "terminated": "⚫",
        }

        for state, count in sorted(state_counts.items()):
            color = get_status_color(state)
            icon = state_icons.get(state, "⚪")

            state_columns.append(
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"{icon} {count}",
                            "size": "Large",
                            "weight": "Bolder",
                            "horizontalAlignment": "Center",
                            "color": color,
                        },
                        {
                            "type": "TextBlock",
                            "text": state.capitalize(),
                            "horizontalAlignment": "Center",
                            "spacing": "None",
                            "size": "Small",
                        },
                    ],
                }
            )

        return {
            "type": "Container",
            "spacing": "Medium",
            "items": [{"type": "ColumnSet", "columns": state_columns}],
        }
