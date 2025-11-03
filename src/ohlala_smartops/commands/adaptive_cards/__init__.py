"""Adaptive Card templates and styles for consistent UI.

This module provides reusable components for building adaptive cards
in Microsoft Teams with consistent branding and styling.
"""

from .styles import (
    COLORS,
    CONTAINER_STYLES,
    SPACING,
    TEXT_SIZES,
    get_metric_color,
    get_platform_icon,
    get_status_color,
)
from .templates import CardTemplates

__all__ = [
    "COLORS",
    "CONTAINER_STYLES",
    "SPACING",
    "TEXT_SIZES",
    "CardTemplates",
    "get_metric_color",
    "get_platform_icon",
    "get_status_color",
]
