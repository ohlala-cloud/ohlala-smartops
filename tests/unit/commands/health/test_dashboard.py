"""Unit tests for HealthDashboardCommand."""

import sys
from unittest.mock import MagicMock

# Mock structlog to avoid Python 3.13 compatibility issues with zope.interface
sys.modules["structlog"] = MagicMock()

from ohlala_smartops.commands.health.dashboard import HealthDashboardCommand  # noqa: E402


class TestHealthDashboardCommand:
    """Test suite for HealthDashboardCommand."""

    def test_command_initialization(self) -> None:
        """Test that command can be initialized."""
        command = HealthDashboardCommand()
        assert command.name == "health"
        assert command.description
        assert command.usage

    def test_parse_instance_id_with_valid_id(self) -> None:
        """Test parsing valid instance ID from arguments."""
        command = HealthDashboardCommand()
        instance_id = command.parse_instance_id(["i-1234567890abcdef0"])
        assert instance_id == "i-1234567890abcdef0"

    def test_parse_instance_id_with_no_args(self) -> None:
        """Test parsing when no arguments provided."""
        command = HealthDashboardCommand()
        instance_id = command.parse_instance_id([])
        assert instance_id is None

    def test_parse_instance_id_with_empty_string(self) -> None:
        """Test parsing with empty string argument."""
        command = HealthDashboardCommand()
        instance_id = command.parse_instance_id([""])
        assert instance_id in [None, ""]  # Either is acceptable
