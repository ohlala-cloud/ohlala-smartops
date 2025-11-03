"""Tests for Phase 5C monitoring and information commands.

This test suite covers the three monitoring commands:
- InstanceDetailsCommand (/details)
- MetricsCommand (/metrics)
- CostsCommand (/costs)

Tests include success cases, error handling, edge cases, and data formatting.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ohlala_smartops.commands import CostsCommand, InstanceDetailsCommand, MetricsCommand


class TestInstanceDetailsCommand:
    """Test suite for InstanceDetailsCommand."""

    @pytest.fixture
    def command(self) -> InstanceDetailsCommand:
        """Create command instance."""
        return InstanceDetailsCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        return {"mcp_manager": AsyncMock()}

    def test_name_property(self, command: InstanceDetailsCommand) -> None:
        """Test command name."""
        assert command.name == "details"

    def test_description_property(self, command: InstanceDetailsCommand) -> None:
        """Test command description."""
        assert "detailed information" in command.description.lower()

    def test_usage_property(self, command: InstanceDetailsCommand) -> None:
        """Test command usage."""
        assert command.usage.startswith("/details")

    @pytest.mark.asyncio
    async def test_execute_no_instance_id(
        self, command: InstanceDetailsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute without instance ID."""
        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "provide an instance id" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_instance(
        self, command: InstanceDetailsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with invalid instance ID."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("Instance not found")

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_success_with_all_data(
        self, command: InstanceDetailsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test successful execution with all data available."""
        mock_mcp = mock_context["mcp_manager"]

        # Mock responses for different API calls
        def mock_call_side_effect(tool_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if tool_name == "describe-instances":
                return {
                    "instances": [
                        {
                            "InstanceId": "i-1234567890abcdef0",
                            "Name": "test-instance",
                            "InstanceType": "t3.micro",
                            "State": "running",
                            "Platform": "Linux",
                            "PrivateIpAddress": "10.0.1.50",
                            "PublicIpAddress": "54.123.45.67",
                            "AvailabilityZone": "us-east-1a",
                            "LaunchTime": "2024-01-01T00:00:00Z",
                            "Tags": {"Environment": "Production", "Team": "DevOps"},
                        }
                    ]
                }
            if tool_name == "get-instance-metrics":
                return {
                    "metrics": {
                        "CPUUtilization": {"Average": 45.5, "Maximum": 75.0, "Minimum": 20.0},
                        "NetworkIn": {"Average": 1024000, "Maximum": 2048000, "Minimum": 512000},
                        "NetworkOut": {
                            "Average": 512000,
                            "Maximum": 1024000,
                            "Minimum": 256000,
                        },
                    }
                }
            if tool_name == "list-commands":
                return {
                    "commands": [
                        {
                            "CommandId": "cmd-123",
                            "Status": "Success",
                            "DocumentName": "AWS-RunShellScript",
                        }
                    ]
                }
            if tool_name == "list-sessions":
                return {
                    "sessions": [
                        {
                            "SessionId": "session-123",
                            "Status": "Connected",
                            "StartDate": "2024-01-01T12:00:00Z",
                        }
                    ]
                }
            return {}

        mock_mcp.call_aws_api_tool.side_effect = mock_call_side_effect

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is True
        assert "card" in result
        assert result["card"]["type"] == "AdaptiveCard"

    @pytest.mark.asyncio
    async def test_execute_success_without_optional_data(
        self, command: InstanceDetailsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test successful execution when metrics/commands/sessions unavailable."""
        mock_mcp = mock_context["mcp_manager"]

        def mock_call_side_effect(tool_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if tool_name == "describe-instances":
                return {
                    "instances": [
                        {
                            "InstanceId": "i-1234567890abcdef0",
                            "Name": "test-instance",
                            "InstanceType": "t3.micro",
                            "State": "stopped",
                            "Platform": "Linux",
                            "AvailabilityZone": "us-east-1a",
                            "LaunchTime": "2024-01-01T00:00:00Z",
                        }
                    ]
                }
            # Metrics, commands, and sessions raise exceptions
            raise Exception("Not available")

        mock_mcp.call_aws_api_tool.side_effect = mock_call_side_effect

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is True
        assert "card" in result


class TestMetricsCommand:
    """Test suite for MetricsCommand."""

    @pytest.fixture
    def command(self) -> MetricsCommand:
        """Create command instance."""
        return MetricsCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        return {"mcp_manager": AsyncMock()}

    def test_name_property(self, command: MetricsCommand) -> None:
        """Test command name."""
        assert command.name == "metrics"

    def test_description_property(self, command: MetricsCommand) -> None:
        """Test command description."""
        assert "cloudwatch" in command.description.lower()

    def test_usage_property(self, command: MetricsCommand) -> None:
        """Test command usage."""
        assert command.usage.startswith("/metrics")

    @pytest.mark.asyncio
    async def test_execute_no_instance_id(
        self, command: MetricsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute without instance ID."""
        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "provide an instance id" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_default_duration(
        self, command: MetricsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with default duration (1h)."""
        mock_mcp = mock_context["mcp_manager"]

        # Mock instance validation
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "Name": "test-instance",
                    "State": "running",
                }
            ],
            "metrics": {"CPUUtilization": {"Average": 45.5, "Maximum": 75.0, "Minimum": 20.0}},
        }

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is True
        assert "card" in result

    @pytest.mark.asyncio
    async def test_execute_custom_duration(
        self, command: MetricsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with custom duration."""
        mock_mcp = mock_context["mcp_manager"]

        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {"InstanceId": "i-1234567890abcdef0", "Name": "test", "State": "running"}
            ],
            "metrics": {},
        }

        result = await command.execute(["i-1234567890abcdef0", "6h"], mock_context)

        assert result["success"] is True
        assert "6h" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_metrics_unavailable(
        self, command: MetricsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute when metrics are unavailable."""
        mock_mcp = mock_context["mcp_manager"]

        def mock_call_side_effect(tool_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if tool_name == "describe-instances":
                return {
                    "instances": [
                        {"InstanceId": "i-1234567890abcdef0", "Name": "test", "State": "running"}
                    ]
                }
            # get-instance-metrics raises exception
            raise Exception("Metrics not available")

        mock_mcp.call_aws_api_tool.side_effect = mock_call_side_effect

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False
        assert "metrics unavailable" in result["card"]["body"][0]["items"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_execute_all_durations(
        self, command: MetricsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test all supported duration options."""
        mock_mcp = mock_context["mcp_manager"]

        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {"InstanceId": "i-1234567890abcdef0", "Name": "test", "State": "running"}
            ],
            "metrics": {},
        }

        for duration in ["1h", "6h", "24h", "7d"]:
            result = await command.execute(["i-1234567890abcdef0", duration], mock_context)
            assert result["success"] is True

    def test_format_bytes(self, command: MetricsCommand) -> None:
        """Test byte formatting helper."""
        assert command._format_bytes(500) == "500 B"
        assert command._format_bytes(1536) == "1.50 KB"
        assert command._format_bytes(1048576) == "1.00 MB"
        assert command._format_bytes(1073741824) == "1.00 GB"


class TestCostsCommand:
    """Test suite for CostsCommand."""

    @pytest.fixture
    def command(self) -> CostsCommand:
        """Create command instance."""
        return CostsCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        return {"mcp_manager": AsyncMock()}

    def test_name_property(self, command: CostsCommand) -> None:
        """Test command name."""
        assert command.name == "costs"

    def test_description_property(self, command: CostsCommand) -> None:
        """Test command description."""
        assert "cost" in command.description.lower()

    def test_usage_property(self, command: CostsCommand) -> None:
        """Test command usage."""
        assert command.usage.startswith("/costs")

    @pytest.mark.asyncio
    async def test_execute_default_all_month(
        self, command: CostsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with defaults (all instances, month)."""
        mock_mcp = mock_context["mcp_manager"]

        mock_mcp.call_aws_api_tool.return_value = {
            "costs": {
                "total_cost": Decimal("123.45"),
                "daily_costs": [
                    {"date": "2024-01-01", "amount": Decimal("4.50")},
                    {"date": "2024-01-02", "amount": Decimal("4.75")},
                ],
            }
        }

        result = await command.execute([], mock_context)

        assert result["success"] is True
        assert "card" in result

    @pytest.mark.asyncio
    async def test_execute_specific_instance(
        self, command: CostsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute for specific instance."""
        mock_mcp = mock_context["mcp_manager"]

        def mock_call_side_effect(tool_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if tool_name == "describe-instances":
                return {
                    "instances": [
                        {"InstanceId": "i-1234567890abcdef0", "Name": "test", "State": "running"}
                    ]
                }
            if tool_name == "get-instance-costs":
                return {
                    "costs": {
                        "total_cost": Decimal("45.67"),
                        "daily_costs": [{"date": "2024-01-01", "amount": Decimal("1.50")}],
                    }
                }
            return {}

        mock_mcp.call_aws_api_tool.side_effect = mock_call_side_effect

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is True
        assert "test" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_with_forecast(
        self, command: CostsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with forecast data."""
        mock_mcp = mock_context["mcp_manager"]

        mock_mcp.call_aws_api_tool.return_value = {
            "costs": {
                "total_cost": Decimal("100.00"),
                "daily_costs": [],
                "forecast": {"amount": Decimal("150.00"), "period": "remaining month"},
            }
        }

        result = await command.execute(["all", "month"], mock_context)

        assert result["success"] is True
        assert "card" in result

    @pytest.mark.asyncio
    async def test_execute_cost_explorer_unavailable(
        self, command: CostsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute when Cost Explorer is unavailable."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("Cost Explorer not enabled")

        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "cost data unavailable" in result["card"]["body"][0]["items"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_execute_no_cost_data(
        self, command: CostsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute when no cost data available."""
        mock_mcp = mock_context["mcp_manager"]

        mock_mcp.call_aws_api_tool.return_value = {
            "costs": {"total_cost": Decimal("0"), "daily_costs": []}
        }

        result = await command.execute([], mock_context)

        assert result["success"] is True
        # Card should indicate no data available

    @pytest.mark.asyncio
    async def test_execute_all_periods(
        self, command: CostsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test all supported period options."""
        mock_mcp = mock_context["mcp_manager"]

        mock_mcp.call_aws_api_tool.return_value = {
            "costs": {"total_cost": Decimal("10.00"), "daily_costs": []}
        }

        for period in ["today", "week", "month"]:
            result = await command.execute(["all", period], mock_context)
            assert result["success"] is True
            assert period in result["message"]
