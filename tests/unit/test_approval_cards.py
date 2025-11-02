"""Unit tests for approval card creation functions."""

import json

import pytest

from ohlala_smartops.cards import (
    create_approved_confirmation_card,
    create_batch_approval_card,
    create_batch_approval_card_sync,
    create_denied_confirmation_card,
    create_ssm_approval_card,
    create_ssm_approval_card_sync,
)
from ohlala_smartops.cards.approval_cards import (
    _is_dangerous_command,
    _is_windows_command,
    _parse_commands,
)


class TestPrivateHelpers:
    """Tests for private helper functions."""

    def test_is_windows_command_with_powershell(self) -> None:
        """Test Windows detection with PowerShell document."""
        assert _is_windows_command("AWS-RunPowerShellScript") is True

    def test_is_windows_command_with_shell(self) -> None:
        """Test Windows detection with Shell document."""
        assert _is_windows_command("AWS-RunShellScript") is False

    def test_is_windows_command_with_custom_document(self) -> None:
        """Test Windows detection with custom document name."""
        assert _is_windows_command("MyCustomPowerShellDoc") is True
        assert _is_windows_command("MyCustomShellDoc") is False

    def test_is_dangerous_command_with_rm_rf(self) -> None:
        """Test dangerous command detection with rm -rf."""
        assert _is_dangerous_command("rm -rf /") is True
        assert _is_dangerous_command("rm -rf /tmp/data") is True

    def test_is_dangerous_command_with_safe_commands(self) -> None:
        """Test dangerous command detection with safe commands."""
        assert _is_dangerous_command("Get-Process") is False
        assert _is_dangerous_command("ls -la") is False
        assert _is_dangerous_command("df -h") is False

    def test_is_dangerous_command_case_insensitive(self) -> None:
        """Test dangerous command detection is case insensitive."""
        assert _is_dangerous_command("RM -RF /") is True
        assert _is_dangerous_command("Rm -Rf /tmp") is True

    def test_parse_commands_with_string(self) -> None:
        """Test command parsing with simple string."""
        result = _parse_commands("ls -la")
        assert result == ["ls -la"]

    def test_parse_commands_with_list(self) -> None:
        """Test command parsing with list."""
        result = _parse_commands(["ps aux", "df -h"])
        assert result == ["ps aux", "df -h"]

    def test_parse_commands_with_json_string(self) -> None:
        """Test command parsing with JSON string."""
        result = _parse_commands('["Get-Process", "Get-Service"]')
        assert result == ["Get-Process", "Get-Service"]

    def test_parse_commands_with_single_item_list(self) -> None:
        """Test command parsing with single-item list."""
        result = _parse_commands(["ls -la"])
        assert result == ["ls -la"]

    def test_parse_commands_with_malformed_json(self) -> None:
        """Test command parsing with malformed JSON."""
        # Missing closing bracket
        result = _parse_commands('["ls -la"')
        assert len(result) == 1
        assert "ls -la" in result[0] or result == ["ls -la"]

    def test_parse_commands_with_wrapped_json(self) -> None:
        """Test command parsing with wrapped JSON in list."""
        result = _parse_commands(['["Get-Process"]'])
        assert result == ["Get-Process"]

    def test_parse_commands_with_empty_list(self) -> None:
        """Test command parsing with empty list."""
        result = _parse_commands([])
        assert result == []

    def test_parse_commands_with_none(self) -> None:
        """Test command parsing with None value."""
        result = _parse_commands(None)
        assert result == ["None"]


class TestSSMApprovalCard:
    """Tests for SSM approval card creation."""

    @pytest.mark.asyncio
    async def test_create_ssm_approval_card_basic(self) -> None:
        """Test basic SSM approval card creation."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0"],
            "Commands": ["Get-Process"],
            "DocumentName": "AWS-RunPowerShellScript",
        }

        card = await create_ssm_approval_card(tool_input, "cmd_123", "Show me processes", False)

        assert card["type"] == "AdaptiveCard"
        assert "body" in card
        assert len(card["body"]) > 0

        # Check for key elements
        body_text = json.dumps(card["body"])
        assert "SSM Command Approval Required" in body_text
        assert "Windows" in body_text
        assert "Get-Process" in body_text

    def test_create_ssm_approval_card_sync_with_linux(self) -> None:
        """Test SSM approval card with Linux command."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0", "i-abcdef1234567890"],
            "Commands": ["ps aux", "df -h"],
            "DocumentName": "AWS-RunShellScript",
        }

        card = create_ssm_approval_card_sync(tool_input, "cmd_456", "Check system", False)

        assert card["type"] == "AdaptiveCard"
        body_text = json.dumps(card["body"])
        assert "Linux" in body_text
        assert "ps aux" in body_text
        assert "2 instance(s)" in body_text

    def test_create_ssm_approval_card_with_dangerous_command(self) -> None:
        """Test SSM approval card with dangerous command."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0"],
            "Commands": ["rm -rf /tmp/data"],
            "DocumentName": "AWS-RunShellScript",
        }

        card = create_ssm_approval_card_sync(tool_input, "cmd_789", "Clean up", False)

        body_text = json.dumps(card["body"])
        assert "DANGEROUS COMMAND DETECTED" in body_text

    def test_create_ssm_approval_card_with_async_mode(self) -> None:
        """Test SSM approval card with async execution mode."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0"],
            "Commands": ["long-running-script.sh"],
            "DocumentName": "AWS-RunShellScript",
        }

        card = create_ssm_approval_card_sync(tool_input, "cmd_async", "Run long task", True)

        body_text = json.dumps(card["body"])
        assert "Asynchronous" in body_text

    def test_create_ssm_approval_card_with_many_instances(self) -> None:
        """Test SSM approval card with more than 5 instances."""
        tool_input = {
            "InstanceIds": [f"i-{i:017x}" for i in range(10)],
            "Commands": ["uptime"],
            "DocumentName": "AWS-RunShellScript",
        }

        card = create_ssm_approval_card_sync(tool_input, "cmd_many", "Check uptime", False)

        body_text = json.dumps(card["body"])
        assert "10 instance(s)" in body_text
        assert "and 5 more" in body_text

    def test_create_ssm_approval_card_actions(self) -> None:
        """Test SSM approval card has correct actions."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0"],
            "Commands": ["ls"],
            "DocumentName": "AWS-RunShellScript",
        }

        card = create_ssm_approval_card_sync(tool_input, "cmd_actions", "List files", False)

        # Find the ActionSet
        action_set = None
        for item in card["body"]:
            if item.get("type") == "ActionSet":
                action_set = item
                break

        assert action_set is not None
        assert len(action_set["actions"]) == 2
        assert action_set["actions"][0]["title"] == "✅ Approve"
        assert action_set["actions"][1]["title"] == "❌ Deny"


class TestBatchApprovalCard:
    """Tests for batch approval card creation."""

    @pytest.mark.asyncio
    async def test_create_batch_approval_card_basic(self) -> None:
        """Test basic batch approval card creation."""
        commands_info = [
            {"tool_input": {"InstanceIds": ["i-123"], "Commands": ["ls"]}, "tool_id": "cmd_1"},
            {"tool_input": {"InstanceIds": ["i-456"], "Commands": ["ps"]}, "tool_id": "cmd_2"},
        ]

        card = await create_batch_approval_card(commands_info, "Multiple commands")

        assert card["type"] == "AdaptiveCard"
        assert "actions" in card
        assert len(card["actions"]) == 3  # Approve All, Deny All, Review Individual

        body_text = json.dumps(card["body"])
        assert "Batch SSM Command Approval" in body_text
        assert "2 commands" in body_text

    def test_create_batch_approval_card_sync_with_mixed_platforms(self) -> None:
        """Test batch approval with mixed Windows/Linux commands."""
        commands_info = [
            {
                "tool_input": {
                    "InstanceIds": ["i-windows"],
                    "Commands": ["Get-Process"],
                    "DocumentName": "AWS-RunPowerShellScript",
                },
                "tool_id": "cmd_1",
            },
            {
                "tool_input": {
                    "InstanceIds": ["i-linux"],
                    "Commands": ["ps aux"],
                    "DocumentName": "AWS-RunShellScript",
                },
                "tool_id": "cmd_2",
            },
        ]

        card = create_batch_approval_card_sync(commands_info, "Mixed platforms")

        body_text = json.dumps(card["body"])
        assert "Windows" in body_text
        assert "Linux" in body_text

    def test_create_batch_approval_card_with_dangerous_commands(self) -> None:
        """Test batch approval with dangerous commands."""
        commands_info = [
            {
                "tool_input": {"InstanceIds": ["i-123"], "Commands": ["rm -rf /tmp"]},
                "tool_id": "cmd_1",
            },
            {"tool_input": {"InstanceIds": ["i-456"], "Commands": ["ls"]}, "tool_id": "cmd_2"},
        ]

        card = create_batch_approval_card_sync(commands_info, "Some dangerous")

        body_text = json.dumps(card["body"])
        assert "WARNING" in body_text or "dangerous" in body_text.lower()

    def test_create_batch_approval_card_tool_ids(self) -> None:
        """Test batch approval card includes all tool IDs."""
        commands_info = [
            {"tool_input": {"InstanceIds": ["i-123"], "Commands": ["ls"]}, "tool_id": "cmd_1"},
            {"tool_input": {"InstanceIds": ["i-456"], "Commands": ["ps"]}, "tool_id": "cmd_2"},
            {"tool_input": {"InstanceIds": ["i-789"], "Commands": ["df"]}, "tool_id": "cmd_3"},
        ]

        card = create_batch_approval_card_sync(commands_info, "Three commands")

        # Check that all tool_ids are in the actions
        actions_text = json.dumps(card["actions"])
        assert "cmd_1" in actions_text
        assert "cmd_2" in actions_text
        assert "cmd_3" in actions_text


class TestConfirmationCards:
    """Tests for approval/denial confirmation cards."""

    def test_create_approved_confirmation_card(self) -> None:
        """Test approved confirmation card creation."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0"],
            "Commands": ["Get-Service"],
            "DocumentName": "AWS-RunPowerShellScript",
        }

        card = create_approved_confirmation_card(tool_input, "Alice")

        assert card["type"] == "AdaptiveCard"
        body_text = json.dumps(card["body"])
        assert "Command Approved & Executed" in body_text
        assert "Alice" in body_text
        assert "Windows" in body_text
        assert "Get-Service" in body_text

    def test_create_approved_confirmation_card_with_linux(self) -> None:
        """Test approved confirmation card with Linux command."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0", "i-abcdef1234567890"],
            "Commands": ["systemctl status nginx"],
            "DocumentName": "AWS-RunShellScript",
        }

        card = create_approved_confirmation_card(tool_input, "Bob")

        body_text = json.dumps(card["body"])
        assert "Linux" in body_text
        assert "2 instance(s)" in body_text

    def test_create_denied_confirmation_card(self) -> None:
        """Test denied confirmation card creation."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0"],
            "Commands": ["rm -rf /"],
            "DocumentName": "AWS-RunShellScript",
        }

        card = create_denied_confirmation_card(tool_input, "Charlie")

        assert card["type"] == "AdaptiveCard"
        body_text = json.dumps(card["body"])
        assert "Command Denied" in body_text
        assert "Charlie" in body_text
        assert "This command was not executed" in body_text

    def test_create_denied_confirmation_card_with_windows(self) -> None:
        """Test denied confirmation card with Windows command."""
        tool_input = {
            "InstanceIds": ["i-1234567890abcdef0"],
            "Commands": ["Remove-Item -Recurse -Force C:\\Windows"],
            "DocumentName": "AWS-RunPowerShellScript",
        }

        card = create_denied_confirmation_card(tool_input, "Dave")

        body_text = json.dumps(card["body"])
        assert "Windows" in body_text
        assert "Dave" in body_text


class TestModuleExports:
    """Tests for module-level exports."""

    def test_all_functions_exported(self) -> None:
        """Test that all public functions are in __all__."""
        from ohlala_smartops.cards import __all__

        expected_exports = [
            "create_ssm_approval_card",
            "create_ssm_approval_card_sync",
            "create_batch_approval_card",
            "create_batch_approval_card_sync",
            "create_approved_confirmation_card",
            "create_denied_confirmation_card",
        ]

        for func_name in expected_exports:
            assert func_name in __all__, f"{func_name} should be exported"

    def test_functions_importable(self) -> None:
        """Test that all exported functions can be imported."""
        from ohlala_smartops.cards import (
            create_approved_confirmation_card,
            create_batch_approval_card,
            create_batch_approval_card_sync,
            create_denied_confirmation_card,
            create_ssm_approval_card,
            create_ssm_approval_card_sync,
        )

        # All functions should be callable
        assert callable(create_ssm_approval_card)
        assert callable(create_ssm_approval_card_sync)
        assert callable(create_batch_approval_card)
        assert callable(create_batch_approval_card_sync)
        assert callable(create_approved_confirmation_card)
        assert callable(create_denied_confirmation_card)
