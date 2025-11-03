"""Tests for Phase 5D SSM command execution commands.

This test suite covers the two SSM execution commands:
- ExecCommand (/exec)
- CommandsListCommand (/commands)

Tests include success cases, error handling, edge cases, and confirmation workflow.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ohlala_smartops.commands.commands_list import CommandsListCommand
from ohlala_smartops.commands.exec import ExecCommand


class TestExecCommand:
    """Test suite for ExecCommand."""

    @pytest.fixture
    def command(self) -> ExecCommand:
        """Create command instance."""
        return ExecCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context with user info."""
        return {
            "mcp_manager": AsyncMock(),
            "user_id": "user-123",
            "user_name": "Test User",
        }

    def test_name_property(self, command: ExecCommand) -> None:
        """Test command name."""
        assert command.name == "exec"

    def test_description_property(self, command: ExecCommand) -> None:
        """Test command description."""
        assert "execute" in command.description.lower()
        assert "ssm" in command.description.lower()

    def test_usage_property(self, command: ExecCommand) -> None:
        """Test command usage."""
        assert command.usage.startswith("/exec")

    @pytest.mark.asyncio
    async def test_execute_no_args(
        self, command: ExecCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute without arguments."""
        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "provide instance id" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_no_command(
        self, command: ExecCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with instance ID but no command."""
        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False
        assert "command" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_no_user_id(self, command: ExecCommand) -> None:
        """Test execute without user ID in context."""
        context = {"mcp_manager": AsyncMock()}
        result = await command.execute(["i-1234567890abcdef0", "ls"], context)

        assert result["success"] is False
        assert "unable to identify user" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_instance(
        self, command: ExecCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with invalid instance ID."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("Instance not found")

        result = await command.execute(["i-1234567890abcdef0", "ls", "-la"], mock_context)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_instance_not_running(
        self, command: ExecCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with non-running instance."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "Name": "test-instance",
                    "State": "stopped",
                }
            ]
        }

        result = await command.execute(
            ["i-1234567890abcdef0", "systemctl", "status", "nginx"], mock_context
        )

        assert result["success"] is False
        assert "running" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.exec.confirmation_manager")
    async def test_execute_success_creates_confirmation(
        self, mock_conf_mgr: MagicMock, command: ExecCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test successful execution creates confirmation request."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "Name": "test-instance",
                    "State": "running",
                    "Platform": "Linux",
                }
            ]
        }

        # Mock confirmation manager
        mock_operation = MagicMock()
        mock_operation.id = "op-123"
        mock_operation.user_name = "Test User"
        mock_conf_mgr.create_confirmation_request.return_value = mock_operation
        mock_conf_mgr.create_confirmation_card.return_value = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [],
        }

        result = await command.execute(["i-1234567890abcdef0", "ls", "-la"], mock_context)

        assert result["success"] is True
        assert "card" in result
        mock_conf_mgr.create_confirmation_request.assert_called_once()

        # Verify confirmation request parameters
        call_args = mock_conf_mgr.create_confirmation_request.call_args
        assert call_args.kwargs["operation_type"] == "exec-command"
        assert call_args.kwargs["resource_type"] == "EC2 Instance"
        assert call_args.kwargs["resource_ids"] == ["i-1234567890abcdef0"]
        assert call_args.kwargs["user_id"] == "user-123"
        assert "ls -la" in call_args.kwargs["additional_data"]["command"]

    @pytest.mark.asyncio
    async def test_execute_multiple_instances(
        self, command: ExecCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with multiple instances."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-1234567890abcdef0",
                    "Name": "instance-1",
                    "State": "running",
                    "Platform": "Linux",
                },
                {
                    "InstanceId": "i-1234567890abcdef1",
                    "Name": "instance-2",
                    "State": "running",
                    "Platform": "Linux",
                },
            ]
        }

        with patch("ohlala_smartops.commands.exec.confirmation_manager") as mock_conf_mgr:
            mock_operation = MagicMock()
            mock_operation.id = "op-123"
            mock_operation.user_name = "Test User"
            mock_conf_mgr.create_confirmation_request.return_value = mock_operation
            mock_conf_mgr.create_confirmation_card.return_value = {
                "type": "AdaptiveCard",
                "body": [],
            }

            result = await command.execute(
                ["i-1234567890abcdef0,i-1234567890abcdef1", "df", "-h"], mock_context
            )

            assert result["success"] is True
            call_args = mock_conf_mgr.create_confirmation_request.call_args
            assert len(call_args.kwargs["resource_ids"]) == 2

    def test_parse_exec_args_no_args(self, command: ExecCommand) -> None:
        """Test parsing with no arguments."""
        result = command._parse_exec_args([])
        assert result["success"] is False
        assert "provide instance id" in result["error"].lower()

    def test_parse_exec_args_only_instance(self, command: ExecCommand) -> None:
        """Test parsing with only instance ID."""
        result = command._parse_exec_args(["i-1234567890abcdef0"])
        assert result["success"] is False
        assert "command" in result["error"].lower()

    def test_parse_exec_args_success(self, command: ExecCommand) -> None:
        """Test successful argument parsing."""
        result = command._parse_exec_args(["i-1234567890abcdef0", "ls", "-la", "/var/log"])
        assert result["success"] is True
        assert result["instance_ids"] == ["i-1234567890abcdef0"]
        assert result["command"] == "ls -la /var/log"

    def test_parse_exec_args_multiple_instances(self, command: ExecCommand) -> None:
        """Test parsing with multiple instance IDs."""
        result = command._parse_exec_args(
            ["i-1234567890abcdef0", "i-1234567890abcdef1", "echo", "hello"]
        )
        assert result["success"] is True
        assert len(result["instance_ids"]) == 2
        assert result["command"] == "echo hello"

    def test_parse_exec_args_comma_separated_instances(self, command: ExecCommand) -> None:
        """Test parsing with comma-separated instance IDs."""
        result = command._parse_exec_args(
            ["i-1234567890abcdef0,i-1234567890abcdef1", "systemctl", "status", "nginx"]
        )
        assert result["success"] is True
        assert len(result["instance_ids"]) == 2
        assert result["command"] == "systemctl status nginx"

    def test_determine_document_name_linux(self, command: ExecCommand) -> None:
        """Test document name determination for Linux instances."""
        instances = [{"InstanceId": "i-123", "Platform": "Linux"}]
        doc = command._determine_document_name(instances)
        assert doc == "AWS-RunShellScript"

    def test_determine_document_name_windows(self, command: ExecCommand) -> None:
        """Test document name determination for Windows instances."""
        instances = [{"InstanceId": "i-123", "Platform": "Windows"}]
        doc = command._determine_document_name(instances)
        assert doc == "AWS-RunPowerShellScript"

    def test_determine_document_name_mixed(self, command: ExecCommand) -> None:
        """Test document name determination for mixed platforms."""
        instances = [
            {"InstanceId": "i-123", "Platform": "Linux"},
            {"InstanceId": "i-456", "Platform": "Windows"},
        ]
        doc = command._determine_document_name(instances)
        # Should default to Shell for mixed environments
        assert doc == "AWS-RunShellScript"

    def test_create_exec_confirmation_card(self, command: ExecCommand) -> None:
        """Test confirmation card creation."""
        mock_operation = MagicMock()
        mock_operation.id = "op-123"
        mock_operation.user_name = "Test User"

        card = command._create_exec_confirmation_card(
            mock_operation, ["i-123"], "ls -la", "AWS-RunShellScript"
        )

        assert card["type"] == "AdaptiveCard"
        assert len(card["actions"]) == 2  # Confirm and Cancel
        assert card["actions"][0]["title"] == "✅ Execute Command"
        assert card["actions"][1]["title"] == "❌ Cancel"

    def test_create_exec_initiated_card(self, command: ExecCommand) -> None:
        """Test execution initiated card creation."""
        card = command._create_exec_initiated_card("cmd-123", 2, "df -h")

        assert card["type"] == "AdaptiveCard"
        body_text = str(card["body"])
        assert "cmd-123" in body_text
        assert "Command Execution Initiated" in body_text


class TestCommandsListCommand:
    """Test suite for CommandsListCommand."""

    @pytest.fixture
    def command(self) -> CommandsListCommand:
        """Create command instance."""
        return CommandsListCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        return {"mcp_manager": AsyncMock()}

    def test_name_property(self, command: CommandsListCommand) -> None:
        """Test command name."""
        assert command.name == "commands"

    def test_description_property(self, command: CommandsListCommand) -> None:
        """Test command description."""
        assert "list" in command.description.lower() or "view" in command.description.lower()
        assert "ssm" in command.description.lower()

    def test_usage_property(self, command: CommandsListCommand) -> None:
        """Test command usage."""
        assert command.usage.startswith("/commands")

    @pytest.mark.asyncio
    async def test_execute_no_commands(
        self, command: CommandsListCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute when no commands exist."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {"commands": []}

        result = await command.execute([], mock_context)

        assert result["success"] is True
        assert "card" in result
        body_text = str(result["card"]["body"])
        assert "no ssm commands" in body_text.lower()

    @pytest.mark.asyncio
    async def test_execute_with_commands(
        self, command: CommandsListCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with command history."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "commands": [
                {
                    "CommandId": "cmd-123",
                    "Status": "Success",
                    "DocumentName": "AWS-RunShellScript",
                    "InstanceIds": ["i-123"],
                    "RequestedDateTime": "2024-01-01T12:00:00Z",
                    "Parameters": {"commands": ["ls -la"]},
                },
                {
                    "CommandId": "cmd-456",
                    "Status": "InProgress",
                    "DocumentName": "AWS-RunShellScript",
                    "InstanceIds": ["i-456"],
                    "RequestedDateTime": "2024-01-01T12:05:00Z",
                    "Parameters": {"commands": ["df -h"]},
                },
            ]
        }

        result = await command.execute([], mock_context)

        assert result["success"] is True
        assert "card" in result
        assert result["card"]["type"] == "AdaptiveCard"

    @pytest.mark.asyncio
    async def test_execute_with_instance_filter(
        self, command: CommandsListCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with instance ID filter."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "commands": [
                {
                    "CommandId": "cmd-123",
                    "Status": "Success",
                    "DocumentName": "AWS-RunShellScript",
                    "InstanceIds": ["i-1234567890abcdef0"],
                    "RequestedDateTime": "2024-01-01T12:00:00Z",
                    "Parameters": {"commands": ["ls"]},
                }
            ]
        }

        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is True
        assert "i-1234567890abcdef0" in result["message"]

        # Verify MCP tool was called with instance filter
        mock_mcp.call_aws_api_tool.assert_called_once()
        call_args = mock_mcp.call_aws_api_tool.call_args
        assert call_args[0][0] == "list-commands"
        assert call_args[0][1]["InstanceId"] == "i-1234567890abcdef0"

    @pytest.mark.asyncio
    async def test_execute_api_error(
        self, command: CommandsListCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute when API call fails."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("SSM not available")

        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "unavailable" in result["card"]["body"][0]["items"][0]["text"].lower()

    def test_get_status_info_success(self, command: CommandsListCommand) -> None:
        """Test status info for success status."""
        info = command._get_status_info("Success")
        assert info["icon"] == "✅"
        assert info["color"] == "Good"

    def test_get_status_info_failed(self, command: CommandsListCommand) -> None:
        """Test status info for failed status."""
        info = command._get_status_info("Failed")
        assert info["icon"] == "❌"
        assert info["color"] == "Attention"

    def test_get_status_info_pending(self, command: CommandsListCommand) -> None:
        """Test status info for pending status."""
        info = command._get_status_info("Pending")
        assert info["icon"] == "⏳"
        assert info["color"] == "Warning"

    def test_get_status_info_in_progress(self, command: CommandsListCommand) -> None:
        """Test status info for in progress status."""
        info = command._get_status_info("InProgress")
        assert info["icon"] == "▶️"
        assert info["color"] == "Accent"

    def test_get_status_info_unknown(self, command: CommandsListCommand) -> None:
        """Test status info for unknown status."""
        info = command._get_status_info("UnknownStatus")
        assert info["icon"] == "⚪"
        assert info["color"] == "Default"

    def test_create_command_entry(self, command: CommandsListCommand) -> None:
        """Test command entry creation."""
        command_data = {
            "CommandId": "cmd-123",
            "Status": "Success",
            "DocumentName": "AWS-RunShellScript",
            "InstanceIds": ["i-123"],
            "RequestedDateTime": "2024-01-01T12:00:00Z",
            "Parameters": {"commands": ["ls -la /var/log"]},
        }

        entry = command._create_command_entry(command_data)

        assert entry["type"] == "Container"
        assert entry["separator"] is True

    @pytest.mark.asyncio
    async def test_execute_many_commands_truncated(
        self, command: CommandsListCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test that command list is truncated when too many commands."""
        # Create 15 mock commands
        commands = [
            {
                "CommandId": f"cmd-{i}",
                "Status": "Success",
                "DocumentName": "AWS-RunShellScript",
                "InstanceIds": ["i-123"],
                "RequestedDateTime": "2024-01-01T12:00:00Z",
                "Parameters": {"commands": ["echo test"]},
            }
            for i in range(15)
        ]

        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {"commands": commands}

        result = await command.execute([], mock_context)

        assert result["success"] is True
        # Check that truncation message appears
        body_text = str(result["card"]["body"])
        assert "more command" in body_text.lower()

    def test_build_commands_list_card_structure(self, command: CommandsListCommand) -> None:
        """Test card structure with commands."""
        commands_data = [
            {
                "CommandId": "cmd-123",
                "Status": "Success",
                "DocumentName": "AWS-RunShellScript",
                "InstanceIds": ["i-123"],
                "RequestedDateTime": "2024-01-01T12:00:00Z",
                "Parameters": {"commands": ["ls"]},
            }
        ]

        card = command._build_commands_list_card(commands_data, None)

        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.5"
        assert len(card["body"]) > 0
        # Should have title, commands, and refresh action
        assert any("Command History" in str(item) for item in card["body"])
