"""Consistent styling for Adaptive Cards.

This module provides color schemes, container styles, and helper functions
for creating consistent adaptive cards throughout the application.

Uses AWS brand colors to match corporate identity.
"""

from typing import Final

# AWS Brand Colors
COLORS: Final[dict[str, str]] = {
    "primary": "#FF9900",  # AWS Orange
    "secondary": "#232F3E",  # AWS Dark Blue
    "tertiary": "#146EB4",  # AWS Blue
    "accent": "#00A1C9",  # AWS Light Blue
    "text_primary": "#232F3E",  # AWS Dark Blue
    "text_secondary": "#545454",  # Gray
    # Status colors
    "success": "#067F68",  # Green
    "warning": "#FF9900",  # AWS Orange
    "error": "#D13212",  # Red
    "info": "#146EB4",  # AWS Blue
    "neutral": "#545454",  # Gray
}

# Container styles mapping
CONTAINER_STYLES: Final[dict[str, str]] = {
    "success": "good",
    "warning": "warning",
    "error": "attention",
    "info": "accent",
    "neutral": "default",
    "emphasis": "emphasis",
}

# Text sizes
TEXT_SIZES: Final[dict[str, str]] = {
    "title": "ExtraLarge",
    "heading": "Large",
    "subheading": "Medium",
    "body": "Default",
    "caption": "Small",
}

# Common spacing values
SPACING: Final[dict[str, str]] = {
    "none": "None",
    "small": "Small",
    "default": "Default",
    "medium": "Medium",
    "large": "Large",
    "extra_large": "ExtraLarge",
}


def get_status_color(status: str) -> str:
    """Get adaptive card color based on status.

    Maps various status strings to adaptive card color values.
    Used for consistent coloring of instance states, health statuses, etc.

    Args:
        status: Status string (e.g., "running", "stopped", "healthy").

    Returns:
        Adaptive card color name (e.g., "Good", "Attention").

    Example:
        >>> get_status_color("running")
        'Good'
        >>> get_status_color("stopped")
        'Attention'
    """
    status_lower = status.lower()

    if status_lower in ["healthy", "running", "active", "success", "passed", "ok"]:
        return "Good"
    if status_lower in [
        "warning",
        "degraded",
        "pending",
        "stopping",
        "starting",
    ]:
        return "Warning"
    if status_lower in [
        "error",
        "failed",
        "stopped",
        "critical",
        "terminated",
        "terminating",
    ]:
        return "Attention"
    return "Default"


def get_metric_color(
    value: float,
    thresholds: dict[str, float] | None = None,
) -> str:
    """Get color based on metric value and thresholds.

    Used for coloring performance metrics like CPU, memory, disk usage.

    Args:
        value: Metric value (typically percentage).
        thresholds: Optional dict with "good", "warning", "critical" keys.
            Defaults to {"good": 60, "warning": 80, "critical": 90}.

    Returns:
        Adaptive card color name.

    Example:
        >>> get_metric_color(45.0)
        'Good'
        >>> get_metric_color(85.0)
        'Attention'
    """
    if not thresholds:
        thresholds = {"good": 60.0, "warning": 80.0, "critical": 90.0}

    if value < thresholds.get("good", 60.0):
        return "Good"
    if value < thresholds.get("warning", 80.0):
        return "Warning"
    return "Attention"


def get_platform_icon(platform: str) -> str:
    """Get platform icon emoji.

    Args:
        platform: Platform name (e.g., "Linux", "Windows").

    Returns:
        Platform icon emoji.

    Example:
        >>> get_platform_icon("Linux")
        '🐧'
        >>> get_platform_icon("Windows")
        '🪟'
    """
    platform_lower = platform.lower()

    if "linux" in platform_lower:
        return "🐧"
    if "windows" in platform_lower:
        return "🪟"
    return "💻"
