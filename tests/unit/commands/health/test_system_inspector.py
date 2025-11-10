"""Unit tests for SystemInspector."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock structlog to avoid Python 3.13 compatibility issues with zope.interface
sys.modules["structlog"] = MagicMock()

from ohlala_smartops.commands.health.system_inspector import (  # noqa: E402
    DiskInfo,
    ErrorLog,
    SystemInfo,
    SystemInspector,
)


class TestSystemInspector:
    """Test suite for SystemInspector."""

    def test_system_inspector_initialization(self) -> None:
        """Test that SystemInspector can be initialized."""
        inspector = SystemInspector(region="us-east-1")
        assert inspector.region == "us-east-1"

    def test_get_disk_usage_commands_windows(self) -> None:
        """Test getting Windows disk usage commands."""
        inspector = SystemInspector(region="us-east-1")
        commands, document_name = inspector._get_disk_usage_commands("windows")
        assert isinstance(commands, list)
        assert len(commands) > 0
        assert document_name == "AWS-RunPowerShellScript"

    def test_get_disk_usage_commands_linux(self) -> None:
        """Test getting Linux disk usage commands."""
        inspector = SystemInspector(region="us-east-1")
        commands, document_name = inspector._get_disk_usage_commands("linux")
        assert isinstance(commands, list)
        assert len(commands) > 0
        assert document_name == "AWS-RunShellScript"

    def test_get_system_info_commands_windows(self) -> None:
        """Test getting Windows system info commands."""
        inspector = SystemInspector(region="us-east-1")
        commands, document_name = inspector._get_system_info_commands("windows")
        assert isinstance(commands, list)
        assert len(commands) > 0
        assert document_name == "AWS-RunPowerShellScript"

    def test_get_system_info_commands_linux(self) -> None:
        """Test getting Linux system info commands."""
        inspector = SystemInspector(region="us-east-1")
        commands, document_name = inspector._get_system_info_commands("linux")
        assert isinstance(commands, list)
        assert len(commands) > 0
        assert document_name == "AWS-RunShellScript"

    def test_get_error_logs_commands_windows(self) -> None:
        """Test getting Windows error logs commands."""
        inspector = SystemInspector(region="us-east-1")
        commands, document_name = inspector._get_error_logs_commands("windows")
        assert isinstance(commands, list)
        assert len(commands) > 0
        assert document_name == "AWS-RunPowerShellScript"

    def test_get_error_logs_commands_linux(self) -> None:
        """Test getting Linux error logs commands."""
        inspector = SystemInspector(region="us-east-1")
        commands, document_name = inspector._get_error_logs_commands("linux")
        assert isinstance(commands, list)
        assert len(commands) > 0
        assert document_name == "AWS-RunShellScript"

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_system_info_windows_success(self, mock_ssm: MagicMock) -> None:
        """Test getting Windows system info successfully."""
        # Create a mock invocation with successful result
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = '{"OSVersion": "Windows Server 2019", "CPUCores": 4}'

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_system_info("i-1234567890abcdef0", platform="windows")

        assert isinstance(result, SystemInfo)
        assert result.OSVersion == "Windows Server 2019"
        assert result.CPUCores == 4

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_system_info_linux_success(self, mock_ssm: MagicMock) -> None:
        """Test getting Linux system info successfully."""
        # Create a mock invocation with successful result
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = '{"OSVersion": "Amazon Linux 2", "CPUCores": 2}'

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_system_info("i-1234567890abcdef0", platform="linux")

        assert isinstance(result, SystemInfo)
        assert result.OSVersion == "Amazon Linux 2"
        assert result.CPUCores == 2

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_system_info_failure(self, mock_ssm: MagicMock) -> None:
        """Test getting system info with SSM failure."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Failed"
        mock_invocation.stdout = ""

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_system_info("i-1234567890abcdef0", platform="linux")

        assert result == {}

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_disk_usage_windows(self, mock_ssm: MagicMock) -> None:
        """Test getting Windows disk usage."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = (
            '[{"Device": "C:", "Mount": "C:\\\\", "SizeGB": 100, '
            '"UsedGB": 50, "FreeGB": 50, "UsedPercent": 50}]'
        )

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_disk_usage("i-1234567890abcdef0", platform="windows")

        assert "disks" in result
        assert len(result["disks"]) == 1
        assert result["disks"][0].Device == "C:"
        assert result["disks"][0].SizeGB == 100

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_disk_usage_linux(self, mock_ssm: MagicMock) -> None:
        """Test getting Linux disk usage."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = (
            '[{"Device": "/dev/xvda1", "Mount": "/", "SizeGB": 100, '
            '"UsedGB": 30, "FreeGB": 70, "UsedPercent": 30}]'
        )

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_disk_usage("i-1234567890abcdef0", platform="linux")

        assert "disks" in result
        assert len(result["disks"]) == 1
        assert result["disks"][0].Device == "/dev/xvda1"

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_disk_usage_failure(self, mock_ssm: MagicMock) -> None:
        """Test getting disk usage with failure."""
        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(side_effect=Exception("SSM Error"))
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_disk_usage("i-1234567890abcdef0", platform="linux")

        assert result == {}

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_disk_usage_invalid_json(self, mock_ssm: MagicMock) -> None:
        """Test disk usage with invalid JSON response."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = "not valid json"

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_disk_usage("i-1234567890abcdef0", platform="linux")

        assert result == {}

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_system_info_invalid_json(self, mock_ssm: MagicMock) -> None:
        """Test system info with invalid JSON response."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = "invalid json data"

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_system_info("i-1234567890abcdef0", platform="windows")

        assert result == {}

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_recent_error_logs_windows(self, mock_ssm: MagicMock) -> None:
        """Test getting Windows error logs."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = (
            '[{"Time": "2025-11-07 10:00:00", "Source": "System", "Message": "Test error message"}]'
        )

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_recent_error_logs("i-1234567890abcdef0", platform="windows")

        assert "error_logs" in result
        assert len(result["error_logs"]) == 1
        assert result["error_logs"][0].Time == "2025-11-07 10:00:00"
        assert result["error_logs"][0].Message == "Test error message"

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_recent_error_logs_linux(self, mock_ssm: MagicMock) -> None:
        """Test getting Linux error logs."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = '[{"Time": "Nov 7 10:00:00", "Message": "Test error"}]'

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_recent_error_logs("i-1234567890abcdef0", platform="linux")

        assert "error_logs" in result
        assert len(result["error_logs"]) == 1

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_recent_error_logs_failure(self, mock_ssm: MagicMock) -> None:
        """Test error logs with SSM failure."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Failed"
        mock_invocation.stdout = ""

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_recent_error_logs("i-1234567890abcdef0", platform="linux")

        assert result == {}

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.health.system_inspector.SSMCommandManager")
    async def test_get_recent_error_logs_invalid_json(self, mock_ssm: MagicMock) -> None:
        """Test error logs with invalid JSON (should fallback to plain text)."""
        mock_invocation = MagicMock()
        mock_invocation.status = "Success"
        mock_invocation.stdout = "plain text error logs"

        mock_manager = AsyncMock()
        mock_manager.send_command = AsyncMock(return_value=MagicMock(command_id="test-cmd-id"))
        mock_manager.wait_for_completion = AsyncMock(return_value=mock_invocation)
        mock_ssm.return_value = mock_manager

        inspector = SystemInspector(ssm_manager=mock_manager, region="us-east-1")
        result = await inspector.get_recent_error_logs("i-1234567890abcdef0", platform="linux")

        assert "error_logs_text" in result
        assert result["error_logs_text"] == "plain text error logs"


class TestSystemInfo:
    """Test suite for SystemInfo Pydantic model."""

    def test_system_info_initialization(self) -> None:
        """Test that SystemInfo can be initialized with defaults."""
        info = SystemInfo()
        assert isinstance(info.OSVersion, str)
        assert isinstance(info.CPUCores, int)

    def test_system_info_with_custom_values(self) -> None:
        """Test SystemInfo with custom values."""
        info = SystemInfo(
            OSVersion="Amazon Linux 2",
            LastBoot="2025-10-01 10:00:00",
            CPUName="Intel Xeon",
            CPUCores=4,
            RunningServices=120,
            FailedServices="",
        )
        assert info.OSVersion == "Amazon Linux 2"
        assert info.CPUCores == 4
        assert info.CPUName == "Intel Xeon"

    def test_system_info_with_failed_services(self) -> None:
        """Test SystemInfo with failed services."""
        info = SystemInfo(
            OSVersion="Windows Server 2019",
            FailedServices="service1,service2",
        )
        assert info.FailedServices == "service1,service2"


class TestDiskInfo:
    """Test suite for DiskInfo Pydantic model."""

    def test_disk_info_initialization(self) -> None:
        """Test that DiskInfo can be initialized."""
        disk = DiskInfo(
            Device="/dev/sda1",
            Mount="/",
            SizeGB=100.0,
            UsedGB=30.0,
            FreeGB=70.0,
            UsedPercent=30.0,
        )
        assert disk.Device == "/dev/sda1"
        assert disk.Mount == "/"
        assert disk.SizeGB == 100.0
        assert disk.UsedGB == 30.0
        assert disk.FreeGB == 70.0
        assert disk.UsedPercent == 30.0

    def test_disk_info_windows(self) -> None:
        """Test DiskInfo with Windows disk."""
        disk = DiskInfo(
            Device="C:",
            Mount="C:\\",
            SizeGB=250.5,
            UsedGB=100.25,
            FreeGB=150.25,
            UsedPercent=40.0,
        )
        assert disk.Device == "C:"
        assert disk.Mount == "C:\\"


class TestErrorLog:
    """Test suite for ErrorLog Pydantic model."""

    def test_error_log_initialization(self) -> None:
        """Test that ErrorLog can be initialized."""
        log = ErrorLog(
            Time="2025-11-07 10:00:00",
            Message="Test error message",
        )
        assert log.Time == "2025-11-07 10:00:00"
        assert log.Message == "Test error message"
        assert log.Source is None

    def test_error_log_with_source(self) -> None:
        """Test ErrorLog with source (Windows)."""
        log = ErrorLog(
            Time="2025-11-07 10:00:00",
            Message="Test error message",
            Source="System",
        )
        assert log.Time == "2025-11-07 10:00:00"
        assert log.Message == "Test error message"
        assert log.Source == "System"
