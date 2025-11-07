"""Unit tests for HealthDashboardCommand."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    @pytest.mark.asyncio
    async def test_detect_platform_windows(self) -> None:
        """Test platform detection for Windows instance."""
        command = HealthDashboardCommand()
        instance_data = {
            "instance_id": "i-1234567890abcdef0",
            "platform_details": "Windows Server 2019",
        }

        # Mock SSM response for Windows
        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(
            return_value={
                "InstanceInformationList": [
                    {
                        "InstanceId": "i-1234567890abcdef0",
                        "PlatformType": "Windows",
                        "PlatformName": "Windows Server 2019",
                    }
                ]
            }
        )
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        platform = await command._detect_platform("i-1234567890abcdef0", instance_data, context)
        assert platform == "windows"

    @pytest.mark.asyncio
    async def test_detect_platform_linux(self) -> None:
        """Test platform detection for Linux instance."""
        command = HealthDashboardCommand()
        instance_data = {"instance_id": "i-1234567890abcdef0", "platform_details": "Linux/UNIX"}

        # Mock SSM response for Linux
        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(
            return_value={
                "InstanceInformationList": [
                    {
                        "InstanceId": "i-1234567890abcdef0",
                        "PlatformType": "Linux",
                        "PlatformName": "Ubuntu",
                    }
                ]
            }
        )
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        platform = await command._detect_platform("i-1234567890abcdef0", instance_data, context)
        assert platform == "linux"

    @pytest.mark.asyncio
    async def test_detect_platform_default(self) -> None:
        """Test platform detection returns Linux as default."""
        command = HealthDashboardCommand()
        instance_data = {"instance_id": "i-1234567890abcdef0", "platform_details": "Other"}

        # Mock SSM response with empty InstanceInformationList (defaults to Linux)
        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(return_value={"InstanceInformationList": []})
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        platform = await command._detect_platform("i-1234567890abcdef0", instance_data, context)
        assert platform == "linux"

    @pytest.mark.asyncio
    async def test_detect_platform_error(self) -> None:
        """Test platform detection with error defaults to Linux."""
        command = HealthDashboardCommand()
        instance_data = {
            "instance_id": "i-1234567890abcdef0",
            "platform_details": None,  # Missing or invalid platform details
        }

        # Mock SSM call to raise an exception
        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(side_effect=Exception("SSM API Error"))
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        platform = await command._detect_platform("i-1234567890abcdef0", instance_data, context)
        assert platform == "linux"

    @pytest.mark.asyncio
    async def test_send_progress_message(self) -> None:
        """Test sending progress message."""
        command = HealthDashboardCommand()
        context = {"conversation_id": "test-123", "activity_id": "activity-456"}

        # Just verify it doesn't raise an exception
        await command._send_progress_message(context, "Processing...")

    @pytest.mark.asyncio
    async def test_execute_with_instance_id(self) -> None:
        """Test execute with specific instance ID."""
        command = HealthDashboardCommand()
        args = ["i-1234567890abcdef0"]
        context = {"region": "us-east-1"}

        mock_result = {"success": True, "card": {}}
        with patch.object(
            command, "_single_instance_health_dashboard", return_value=mock_result
        ) as mock_method:
            result = await command.execute(args, context)

            assert result == mock_result
            mock_method.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_without_instance_id(self) -> None:
        """Test execute without instance ID (overview mode)."""
        command = HealthDashboardCommand()
        args = []
        context = {"region": "us-east-1"}

        mock_result = {"success": True, "card": {}}
        with patch.object(
            command, "_all_instances_health_overview", return_value=mock_result
        ) as mock_method:
            result = await command.execute(args, context)

            assert result == mock_result
            mock_method.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_instance_health_dashboard_no_mcp_manager(self) -> None:
        """Test single instance dashboard with no MCP manager."""
        command = HealthDashboardCommand()
        instance_id = "i-1234567890abcdef0"
        context = {}  # No mcp_manager

        result = await command._single_instance_health_dashboard(instance_id, context)

        assert result["success"] is False
        assert "MCP manager not available" in result["error"]

    @pytest.mark.asyncio
    async def test_all_instances_health_overview_no_mcp_manager(self) -> None:
        """Test all instances overview with no MCP manager."""
        command = HealthDashboardCommand()
        context = {}  # No mcp_manager

        result = await command._all_instances_health_overview(context)

        assert result["success"] is False
        assert "MCP manager not available" in result["error"]

    @pytest.mark.asyncio
    async def test_single_instance_health_dashboard_instance_not_found(self) -> None:
        """Test single instance dashboard when instance not found."""
        command = HealthDashboardCommand()
        instance_id = "i-nonexistent"

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(
            return_value={
                "instances": [{"instance_id": "i-different", "state": {"name": "running"}}]
            }
        )
        context = {"mcp_manager": mock_mcp}

        result = await command._single_instance_health_dashboard(instance_id, context)

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_all_instances_health_overview_no_running_instances(self) -> None:
        """Test all instances overview with no running instances."""
        command = HealthDashboardCommand()

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(
            return_value={"instances": [{"instance_id": "i-stopped", "state": "stopped"}]}
        )
        context = {"mcp_manager": mock_mcp}

        result = await command._all_instances_health_overview(context)

        # Should still succeed with message about no running instances
        assert result["success"] is True
        assert "message" in result or "card" in result

    @pytest.mark.asyncio
    async def test_all_instances_health_overview_no_instances(self) -> None:
        """Test all instances overview when no instances exist."""
        command = HealthDashboardCommand()

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(return_value={"instances": []})
        context = {"mcp_manager": mock_mcp}

        result = await command._all_instances_health_overview(context)

        # Should succeed with message about no instances
        assert result["success"] is True
        assert result["message"] == "No EC2 instances found."

    @pytest.mark.asyncio
    async def test_all_instances_health_overview_with_running_instances(self) -> None:
        """Test all instances overview with running instances."""
        command = HealthDashboardCommand()
        command.metrics_collector = AsyncMock()
        command.metrics_collector.get_instance_health_summary = AsyncMock(
            return_value={"instance_id": "i-running1", "cpu_avg": 45.5, "status": "healthy"}
        )
        command.card_builder = MagicMock()
        command.card_builder.build_health_overview_card = MagicMock(
            return_value={"type": "AdaptiveCard"}
        )

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(
            return_value={
                "instances": [
                    {"instance_id": "i-running1", "state": "running"},
                    {"instance_id": "i-running2", "state": "running"},
                ]
            }
        )
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        result = await command._all_instances_health_overview(context)

        # Should succeed with card
        assert result["success"] is True
        assert "card" in result

    @pytest.mark.asyncio
    async def test_execute_exception_handling(self) -> None:
        """Test execute method exception handling."""
        command = HealthDashboardCommand()
        args = ["i-test"]
        context = {"region": "us-east-1"}

        # Mock _single_instance_health_dashboard to raise an exception
        with patch.object(
            command, "_single_instance_health_dashboard", side_effect=Exception("Test error")
        ):
            result = await command.execute(args, context)

            assert result["success"] is False
            assert "card" in result  # Error card

    @pytest.mark.asyncio
    async def test_single_instance_health_dashboard_with_metrics(self) -> None:
        """Test single instance dashboard with successful metric collection."""
        command = HealthDashboardCommand()
        command.metrics_collector = AsyncMock()
        command.system_inspector = AsyncMock()
        command.card_builder = MagicMock()

        # Mock metric collection
        command.metrics_collector.get_cloudwatch_metrics = AsyncMock(
            return_value={"cpu_graph": {"datapoints": []}}
        )
        command.metrics_collector.get_realtime_system_metrics = AsyncMock(
            return_value={"cpu_percent": 45.5}
        )
        command.system_inspector.get_disk_usage = AsyncMock(return_value={"disks": []})
        command.system_inspector.get_recent_error_logs = AsyncMock(return_value={"logs": []})
        command.system_inspector.get_system_info = AsyncMock(return_value={"os": "Linux"})
        command.card_builder.build_health_dashboard_card = MagicMock(
            return_value={"type": "AdaptiveCard"}
        )

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(
            return_value={
                "instances": [
                    {
                        "instance_id": "i-test123",
                        "name": "Test Instance",
                        "instance_type": "t3.micro",
                        "state": "running",
                        "platform_details": "Linux/UNIX",
                    }
                ],
                "InstanceInformationList": [
                    {"InstanceId": "i-test123", "PlatformType": "Linux", "PlatformName": "Ubuntu"}
                ],
            }
        )
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        result = await command._single_instance_health_dashboard("i-test123", context)

        # Should succeed with card
        assert result["success"] is True
        assert "card" in result

    @pytest.mark.asyncio
    async def test_execute_initializes_components(self) -> None:
        """Test that execute initializes metrics_collector and system_inspector."""
        command = HealthDashboardCommand()
        args = []

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(return_value={"instances": []})
        context = {"mcp_manager": mock_mcp, "region": "us-west-2"}

        # Verify components are None initially
        assert command.metrics_collector is None
        assert command.system_inspector is None

        await command.execute(args, context)

        # Verify components are initialized after execute
        assert command.metrics_collector is not None
        assert command.system_inspector is not None

    @pytest.mark.asyncio
    async def test_all_instances_health_overview_with_many_instances(self) -> None:
        """Test all instances overview with more than 10 instances (progress message)."""
        command = HealthDashboardCommand()
        command.metrics_collector = AsyncMock()
        command.metrics_collector.get_instance_health_summary = AsyncMock(
            return_value={"instance_id": "i-test", "status": "healthy"}
        )
        command.card_builder = MagicMock()
        command.card_builder.build_health_overview_card = MagicMock(
            return_value={"type": "AdaptiveCard"}
        )

        # Create 12 running instances
        instances = [{"instance_id": f"i-test{i}", "state": "running"} for i in range(12)]

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(return_value={"instances": instances})
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        result = await command._all_instances_health_overview(context)

        # Should succeed with card
        assert result["success"] is True
        assert "card" in result

    @pytest.mark.asyncio
    async def test_single_instance_health_dashboard_with_metric_error(self) -> None:
        """Test single instance dashboard when metric collection fails."""
        command = HealthDashboardCommand()
        command.metrics_collector = AsyncMock()
        command.system_inspector = AsyncMock()
        command.card_builder = MagicMock()

        # Mock one metric to raise an exception
        command.metrics_collector.get_cloudwatch_metrics = AsyncMock(
            side_effect=Exception("CloudWatch error")
        )
        command.metrics_collector.get_realtime_system_metrics = AsyncMock(
            return_value={"cpu_percent": 45.5}
        )
        command.system_inspector.get_disk_usage = AsyncMock(return_value={"disks": []})
        command.system_inspector.get_recent_error_logs = AsyncMock(return_value={"logs": []})
        command.system_inspector.get_system_info = AsyncMock(return_value={"os": "Linux"})
        command.card_builder.build_health_dashboard_card = MagicMock(
            return_value={"type": "AdaptiveCard"}
        )

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(
            return_value={
                "instances": [
                    {
                        "instance_id": "i-test456",
                        "name": "Test",
                        "instance_type": "t3.micro",
                        "state": "running",
                        "platform_details": "Linux/UNIX",
                    }
                ],
                "InstanceInformationList": [
                    {"InstanceId": "i-test456", "PlatformType": "Linux", "PlatformName": "Ubuntu"}
                ],
            }
        )
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        result = await command._single_instance_health_dashboard("i-test456", context)

        # Should still succeed even with one metric failing
        assert result["success"] is True
        assert "card" in result

    @pytest.mark.asyncio
    async def test_all_instances_health_overview_with_batch_errors(self) -> None:
        """Test all instances overview when some batch items fail."""
        command = HealthDashboardCommand()
        command.metrics_collector = AsyncMock()

        # Mock to alternate between success and exception
        async def mock_health_summary(instance_id: str):
            if instance_id == "i-good":
                return {"instance_id": instance_id, "status": "healthy"}
            raise Exception("Metrics unavailable")

        command.metrics_collector.get_instance_health_summary = mock_health_summary
        command.card_builder = MagicMock()
        command.card_builder.build_health_overview_card = MagicMock(
            return_value={"type": "AdaptiveCard"}
        )

        mock_mcp = AsyncMock()
        mock_mcp.call_tool = AsyncMock(
            return_value={
                "instances": [
                    {"instance_id": "i-good", "state": "running"},
                    {"instance_id": "i-bad", "state": "running"},
                ]
            }
        )
        context = {"mcp_manager": mock_mcp, "region": "us-east-1"}

        result = await command._all_instances_health_overview(context)

        # Should still succeed even with some failures
        assert result["success"] is True
        assert "card" in result
