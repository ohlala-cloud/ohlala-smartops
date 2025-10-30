"""Tests for SSM validation utilities."""

import pytest

from ohlala_smartops.utils.ssm_validation import (
    fix_common_issues,
    validate_ssm_commands,
)


class TestValidateSSMCommands:
    """Test cases for validate_ssm_commands function."""

    def test_validate_empty_list(self) -> None:
        """Test validation of empty commands list."""
        is_valid, error = validate_ssm_commands([])
        assert not is_valid
        assert error == "Commands list is empty"

    def test_validate_not_list(self) -> None:
        """Test validation when input is not a list."""
        is_valid, error = validate_ssm_commands("not a list")  # type: ignore[arg-type]
        assert not is_valid
        assert "must be a list" in error
        assert "str" in error

    def test_validate_non_string_command(self) -> None:
        """Test validation when command is not a string."""
        is_valid, error = validate_ssm_commands([123])  # type: ignore[list-item]
        assert not is_valid
        assert "not a string" in error
        assert "int" in error

    def test_validate_json_array_syntax(self) -> None:
        """Test detection of JSON array syntax in command."""
        # Double quote array
        is_valid, error = validate_ssm_commands(['["echo hello"]'])
        assert not is_valid
        assert "JSON-encoded" in error

        # Single quote array
        is_valid, error = validate_ssm_commands(["['echo hello']"])
        assert not is_valid
        assert "JSON-encoded" in error

    def test_validate_json_object_syntax(self) -> None:
        """Test detection of JSON object syntax in command."""
        is_valid, error = validate_ssm_commands(['{"key": "value"}'])
        assert not is_valid
        assert "JSON object" in error

    def test_validate_null_bytes(self) -> None:
        """Test detection of null bytes in command."""
        is_valid, error = validate_ssm_commands(["echo\x00hello"])
        assert not is_valid
        assert "null bytes" in error

    def test_validate_valid_simple_command(self) -> None:
        """Test validation of valid simple command."""
        is_valid, error = validate_ssm_commands(["echo hello"])
        assert is_valid
        assert error == ""

    def test_validate_valid_multiple_commands(self) -> None:
        """Test validation of multiple valid commands."""
        commands = ["echo hello", "ls -la", "pwd"]
        is_valid, error = validate_ssm_commands(commands)
        assert is_valid
        assert error == ""

    def test_validate_escaped_quotes_no_error(self) -> None:
        """Test that escaped quotes don't cause validation error."""
        # Even with escaped quotes, command should be valid (might trigger warning)
        commands = ['echo \\"hello\\" \\"world\\"']
        is_valid, error = validate_ssm_commands(commands)
        # Should still be valid (warning is optional)
        assert is_valid
        assert error == ""

    def test_validate_long_command_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test warning for very long commands."""
        long_command = "echo " + "x" * 10001
        is_valid, error = validate_ssm_commands([long_command])
        # Should still be valid, just a warning
        assert is_valid
        assert error == ""
        assert "very long" in caplog.text.lower()

    def test_validate_powershell_command(self) -> None:
        """Test validation of valid PowerShell command."""
        commands = ["Write-Output 'Hello World'"]
        is_valid, error = validate_ssm_commands(commands)
        assert is_valid
        assert error == ""

    def test_validate_powershell_with_syntax_error(self) -> None:
        """Test validation of PowerShell command with syntax error."""
        # This will be caught by the PowerShell validator
        commands = ['Write-Output "Hello""']
        is_valid, error = validate_ssm_commands(commands)
        assert not is_valid
        assert "PowerShell syntax issues" in error

    def test_validate_bash_command_with_dollar_sign(self) -> None:
        """Test validation of bash command with $ (shouldn't trigger PS validation)."""
        # Commands with $ but not PowerShell patterns should be validated
        # The current implementation will check for PowerShell patterns
        commands = ["echo $HOME"]
        is_valid, _error = validate_ssm_commands(commands)
        # This should pass as it's not a problematic PowerShell pattern
        assert is_valid


class TestFixCommonIssues:
    """Test cases for fix_common_issues function."""

    def test_fix_json_wrapped_command(self) -> None:
        """Test fixing of JSON-wrapped command."""
        commands = ['["echo hello"]']
        fixed = fix_common_issues(commands)
        assert fixed == ["echo hello"]

    def test_fix_json_wrapped_with_escaped_quotes(self) -> None:
        """Test fixing of JSON-wrapped command with escaped quotes."""
        commands = ['["echo \\"hello\\""]']
        fixed = fix_common_issues(commands)
        assert fixed == ['echo "hello"']

    def test_fix_json_wrapped_with_newlines(self) -> None:
        """Test fixing of JSON-wrapped command with escaped newlines."""
        commands = ['["echo hello\\necho world"]']
        fixed = fix_common_issues(commands)
        assert fixed == ["echo hello\necho world"]

    def test_fix_json_wrapped_with_tabs(self) -> None:
        """Test fixing of JSON-wrapped command with escaped tabs."""
        commands = ['["echo\\thello"]']
        fixed = fix_common_issues(commands)
        assert fixed == ["echo\thello"]

    def test_fix_json_wrapped_with_backslashes(self) -> None:
        """Test fixing of JSON-wrapped command with escaped backslashes."""
        commands = ['["echo C:\\\\Users"]']
        fixed = fix_common_issues(commands)
        assert fixed == ["echo C:\\Users"]

    def test_fix_regular_command_unchanged(self) -> None:
        """Test that regular commands are not modified."""
        commands = ["echo hello"]
        fixed = fix_common_issues(commands)
        assert fixed == commands

    def test_fix_powershell_command(self) -> None:
        """Test fixing of PowerShell command with syntax issues."""
        # Command with double quote issue
        commands = ['Write-Output "Hello""']
        fixed = fix_common_issues(commands)
        # Should be fixed by PowerShell validator
        assert fixed == ['Write-Output "Hello"']

    def test_fix_multiple_commands(self) -> None:
        """Test fixing of multiple commands."""
        commands = [
            '["echo hello"]',
            "ls -la",
            '["pwd"]',
        ]
        fixed = fix_common_issues(commands)
        assert fixed == ["echo hello", "ls -la", "pwd"]

    def test_fix_empty_list(self) -> None:
        """Test fixing of empty command list."""
        fixed = fix_common_issues([])
        assert fixed == []
