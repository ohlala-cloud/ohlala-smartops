"""Tests for SSM validation utilities."""

from ohlala_smartops.utils.ssm_validation import (
    fix_common_issues,
    validate_ssm_commands,
)


class TestValidateSSMCommands:
    """Tests for validate_ssm_commands function."""

    def test_validates_simple_commands(self) -> None:
        """Test validation of simple valid commands."""
        commands = ["ls -la", "pwd", "echo 'test'"]
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is True
        assert error_msg == ""

    def test_rejects_empty_command_list(self) -> None:
        """Test rejection of empty command list."""
        commands: list[str] = []
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is False
        assert "empty" in error_msg.lower()

    def test_rejects_non_list_commands(self) -> None:
        """Test rejection of non-list command input."""
        commands = "not a list"  # type: ignore[assignment]
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is False
        assert "list or tuple" in error_msg.lower()

    def test_rejects_non_string_command_items(self) -> None:
        """Test rejection of non-string items in command list."""
        commands = ["valid command", 123, "another valid command"]  # type: ignore[list-item]
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is False
        assert "not a string" in error_msg.lower()
        assert "Command 1" in error_msg

    def test_detects_json_array_syntax(self) -> None:
        """Test detection of JSON array syntax in commands."""
        commands = ['["ls -la"]']
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is False
        assert "json-encoded" in error_msg.lower()

    def test_detects_json_object_syntax(self) -> None:
        """Test detection of JSON object syntax in commands."""
        commands = ['{"command": "ls"}']
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is False
        assert "json object" in error_msg.lower()

    def test_detects_null_bytes(self) -> None:
        """Test detection of null bytes in commands."""
        commands = ["ls\x00-la"]
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is False
        assert "null bytes" in error_msg.lower()

    def test_validates_powershell_commands(self) -> None:
        """Test validation of PowerShell commands."""
        commands = ['Write-Output "Hello World"']
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is True
        assert error_msg == ""

    def test_detects_powershell_syntax_errors(self) -> None:
        """Test detection of PowerShell syntax errors."""
        commands = ['Write-Output "test"""']  # Double quotes at end
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is False
        assert "powershell syntax" in error_msg.lower()

    def test_warns_about_long_commands(self) -> None:
        """Test warning about very long commands."""
        # Create a command longer than SSM_OUTPUT_LIMIT // 2
        long_command = "echo " + "x" * 15000
        commands = [long_command]
        is_valid, _ = validate_ssm_commands(commands)

        # Should still be valid, just warned
        assert is_valid is True

    def test_handles_escaped_quotes_as_warning(self) -> None:
        """Test that escaped quotes generate warnings but don't fail."""
        commands = ['echo \\"test\\" more \\"quotes\\"']
        is_valid, _ = validate_ssm_commands(commands)

        # Should be valid, just warned
        assert is_valid is True

    def test_validates_multiple_commands(self) -> None:
        """Test validation of multiple commands."""
        commands = [
            "ls -la",
            "pwd",
            "cat /etc/hosts",
            "df -h",
        ]
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is True
        assert error_msg == ""

    def test_identifies_first_invalid_command(self) -> None:
        """Test that first invalid command is identified."""
        commands = [
            "ls -la",
            '["invalid"]',
            "pwd",
        ]
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is False
        assert "Command 1" in error_msg  # Second command (0-indexed)

    def test_accepts_tuple_commands(self) -> None:
        """Test that tuple of commands is accepted."""
        commands = ("ls -la", "pwd")
        is_valid, error_msg = validate_ssm_commands(commands)

        assert is_valid is True
        assert error_msg == ""


class TestFixCommonIssues:
    """Tests for fix_common_issues function."""

    def test_fixes_json_wrapped_commands(self) -> None:
        """Test fixing of JSON-wrapped commands."""
        commands = ['["ls -la"]']
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1
        assert fixed[0] == "ls -la"

    def test_unescapes_json_sequences(self) -> None:
        """Test unescaping of JSON escape sequences."""
        commands = ['["echo \\"test\\"\\n\\tindented"]']
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1
        assert '"test"' in fixed[0]
        assert "\n" in fixed[0]
        assert "\t" in fixed[0]

    def test_fixes_powershell_syntax(self) -> None:
        """Test fixing of PowerShell syntax issues."""
        commands = ['Write-Output "Hello World""']
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1
        assert fixed[0] == 'Write-Output "Hello World"'

    def test_preserves_valid_commands(self) -> None:
        """Test that valid commands are preserved unchanged."""
        commands = ["ls -la", "pwd", "echo 'test'"]
        fixed = fix_common_issues(commands)

        assert len(fixed) == 3
        assert fixed[0] == "ls -la"
        assert fixed[1] == "pwd"
        assert fixed[2] == "echo 'test'"

    def test_handles_multiple_issues(self) -> None:
        """Test fixing multiple commands with different issues."""
        commands = [
            '["ls -la"]',  # JSON wrapped
            'Write-Output "test""',  # PowerShell issue
            "pwd",  # Valid
        ]
        fixed = fix_common_issues(commands)

        assert len(fixed) == 3
        assert fixed[0] == "ls -la"
        assert fixed[1] == 'Write-Output "test"'
        assert fixed[2] == "pwd"

    def test_handles_empty_command_list(self) -> None:
        """Test handling of empty command list."""
        commands: list[str] = []
        fixed = fix_common_issues(commands)

        assert len(fixed) == 0

    def test_handles_complex_json_wrapping(self) -> None:
        """Test handling of complex JSON wrapping."""
        commands = ['["echo \\"Hello World\\"\\nNext line"]']
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1
        assert "Hello World" in fixed[0]
        assert "\n" in fixed[0]
        assert "Next line" in fixed[0]

    def test_preserves_get_commands(self) -> None:
        """Test that Get- PowerShell commands are identified."""
        commands = ["Get-Process | Select-Object Name"]
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1
        # Should identify as PowerShell and process it
        assert "Get-Process" in fixed[0]

    def test_preserves_set_commands(self) -> None:
        """Test that Set- PowerShell commands are identified."""
        commands = ["Set-ExecutionPolicy RemoteSigned"]
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1
        assert "Set-ExecutionPolicy" in fixed[0]

    def test_handles_variable_syntax(self) -> None:
        """Test handling of PowerShell variable syntax."""
        commands = ["$myVar = 'test'"]
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1
        assert "$myVar" in fixed[0]


class TestSSMValidationIntegration:
    """Integration tests for SSM validation."""

    def test_validate_then_fix_workflow(self) -> None:
        """Test the workflow of validating then fixing commands."""
        commands = ['["ls -la"]']

        # First validation should fail
        is_valid, error_msg = validate_ssm_commands(commands)
        assert is_valid is False

        # Fix the issues
        fixed = fix_common_issues(commands)

        # Now validation should pass
        is_valid, error_msg = validate_ssm_commands(fixed)
        assert is_valid is True
        assert error_msg == ""

    def test_powershell_validate_and_fix_workflow(self) -> None:
        """Test PowerShell command validation and fixing workflow."""
        commands = ['Write-Output "test"""']

        # Validation should fail
        is_valid, error_msg = validate_ssm_commands(commands)
        assert is_valid is False
        assert "powershell" in error_msg.lower()

        # Fix the issues
        fixed = fix_common_issues(commands)

        # Now validation should pass
        is_valid, error_msg = validate_ssm_commands(fixed)
        assert is_valid is True

    def test_mixed_commands_validation(self) -> None:
        """Test validation of mixed Linux and PowerShell commands."""
        commands = [
            "ls -la",
            'Write-Output "Windows command"',
            "pwd",
            "Get-Process",
        ]

        is_valid, error_msg = validate_ssm_commands(commands)
        assert is_valid is True
        assert error_msg == ""

    def test_edge_case_empty_string_command(self) -> None:
        """Test handling of empty string command."""
        commands = [""]
        is_valid, _ = validate_ssm_commands(commands)

        # Empty string command should be valid (will just do nothing)
        assert is_valid is True


class TestPowerShellDetection:
    """Tests for PowerShell command detection."""

    def test_detects_write_output(self) -> None:
        """Test that Write-Output is detected as PowerShell."""
        commands = ['Write-Output "test"']
        fixed = fix_common_issues(commands)

        # Should process as PowerShell
        assert len(fixed) == 1

    def test_detects_get_commands(self) -> None:
        """Test that Get- cmdlets are detected as PowerShell."""
        commands = ["Get-Process"]
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1

    def test_detects_dollar_sign_variables(self) -> None:
        """Test that $ variables are detected as PowerShell."""
        commands = ["$var = 'value'"]
        fixed = fix_common_issues(commands)

        assert len(fixed) == 1

    def test_does_not_trigger_on_bash_variables(self) -> None:
        """Test that Bash $ variables work correctly."""
        commands = ["echo $HOME"]
        fixed = fix_common_issues(commands)

        # Should still process ($ is detected, but no PowerShell-specific issues)
        assert len(fixed) == 1
        assert "$HOME" in fixed[0]
