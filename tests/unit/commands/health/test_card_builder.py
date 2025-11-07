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
