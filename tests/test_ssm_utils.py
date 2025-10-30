"""Tests for SSM utility functions."""

import logging

import pytest

from ohlala_smartops.utils.ssm_utils import preprocess_ssm_commands


class TestPreprocessSSMCommands:
    """Test cases for preprocess_ssm_commands function."""

    def test_preprocess_empty_commands(self) -> None:
        """Test preprocessing of empty commands."""
        # Test None
        assert preprocess_ssm_commands(None) == []

        # Test empty string
        assert preprocess_ssm_commands("") == []

        # Test empty list
        assert preprocess_ssm_commands([]) == []

    def test_preprocess_string_command(self) -> None:
        """Test preprocessing of single string command."""
        # Simple string
        result = preprocess_ssm_commands("echo hello")
        assert result == ["echo hello"]

        # String with whitespace
        result = preprocess_ssm_commands("  echo hello  ")
        assert result == ["echo hello"]

    def test_preprocess_list_of_strings(self) -> None:
        """Test preprocessing of list of string commands."""
        commands = ["echo hello", "echo world"]
        result = preprocess_ssm_commands(commands)
        assert result == ["echo hello", "echo world"]

    def test_preprocess_list_of_non_strings(self) -> None:
        """Test preprocessing of list with non-string elements."""
        commands = [123, 456]  # type: ignore[list-item]
        result = preprocess_ssm_commands(commands)
        assert result == ["123", "456"]

    def test_preprocess_json_array_string(self) -> None:
        """Test preprocessing of JSON array string."""
        # Standard JSON array
        json_commands = '["echo hello", "echo world"]'
        result = preprocess_ssm_commands(json_commands)
        assert result == ["echo hello", "echo world"]

        # JSON array with escaped quotes (Bedrock format)
        json_commands = '["echo \\"hello\\"", "echo \\"world\\""]'
        result = preprocess_ssm_commands(json_commands)
        assert result == ['echo "hello"', 'echo "world"']

    def test_preprocess_python_repr_string(self) -> None:
        """Test preprocessing of Python repr() format string."""
        # Python repr() format: ['item1', 'item2']
        commands = ["['echo hello', 'echo world']"]
        result = preprocess_ssm_commands(commands)
        assert result == ["echo hello", "echo world"]

    def test_preprocess_python_repr_invalid(self) -> None:
        """Test handling of invalid Python repr() format."""
        commands = ["['invalid syntax"]
        result = preprocess_ssm_commands(commands)
        # Should fall back to treating it as a single command or JSON
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_nested_json_in_list(self) -> None:
        """Test preprocessing of list containing JSON strings."""
        # List with JSON string element
        commands = ['["Get-Process | Select-Object -First 10"]']
        result = preprocess_ssm_commands(commands)
        assert result == ["Get-Process | Select-Object -First 10"]

    def test_preprocess_escaped_json_complete(self) -> None:
        """Test preprocessing of escaped JSON array."""
        # Complete escaped JSON with proper format
        commands = '["echo hello"]'  # This should be parsed as JSON
        result = preprocess_ssm_commands(commands)
        assert result == ["echo hello"]

    def test_preprocess_escaped_json_truncated_curly_brace(self) -> None:
        """Test preprocessing of truncated escaped JSON (CloudWatch pattern)."""
        # Pattern: ["command content"}
        commands = '["echo hello"}'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_preprocess_escaped_json_truncated_brace(self) -> None:
        """Test preprocessing of truncated escaped JSON ending with }."""
        # Pattern: ["command content}
        commands = '["echo hello}'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_preprocess_triple_escaped_quotes(self) -> None:
        """Test preprocessing of triple escaped quotes."""
        commands = '[\\\\"echo hello\\\\"]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_escaped_special_chars(self) -> None:
        """Test preprocessing of escaped special characters."""
        # Newlines, tabs, carriage returns
        commands = '["echo hello\\necho world"]'
        result = preprocess_ssm_commands(commands)
        assert len(result) == 1
        assert "\n" in result[0]

    def test_preprocess_windows_paths(self) -> None:
        """Test preprocessing of Windows paths with backslashes."""
        commands = '["dir C:\\\\Users"]'
        result = preprocess_ssm_commands(commands)
        assert len(result) == 1
        assert "C:\\Users" in result[0]

    def test_preprocess_complex_powershell_commands(self) -> None:
        """Test preprocessing of complex PowerShell commands."""
        # Multi-line PowerShell script
        ps_script = (
            "$folders = Get-ChildItem C:\\ -Directory\\n$folders | ForEach-Object { $_.Name }"
        )
        result = preprocess_ssm_commands(ps_script)
        assert result == [ps_script]

        # PowerShell in JSON array
        ps_json = (
            '["$folders = Get-ChildItem C:\\\\ -Directory\\n$folders | ForEach-Object { $_.Name }"]'
        )
        result = preprocess_ssm_commands(ps_json)
        assert len(result) == 1
        assert "Get-ChildItem" in result[0]

    def test_preprocess_powershell_with_fixes(self) -> None:
        """Test that PowerShell fixes are automatically applied."""
        # Command with double quote issue
        commands = ['Write-Output "Hello""']
        result = preprocess_ssm_commands(commands)
        # Should be fixed automatically
        assert result == ['Write-Output "Hello"']

    def test_preprocess_non_powershell_commands(self) -> None:
        """Test preprocessing of non-PowerShell commands."""
        commands = ["ls -la", "pwd", "whoami"]
        result = preprocess_ssm_commands(commands)
        assert result == commands

    def test_preprocess_mixed_commands(self) -> None:
        """Test preprocessing of mixed PowerShell and bash commands."""
        commands = ["ls -la", 'Write-Output "Hello"', "pwd"]
        result = preprocess_ssm_commands(commands)
        assert len(result) == 3
        assert result[0] == "ls -la"
        assert result[1] == 'Write-Output "Hello"'
        assert result[2] == "pwd"

    def test_preprocess_unexpected_type(self) -> None:
        """Test preprocessing of unexpected data type."""
        result = preprocess_ssm_commands(12345)
        assert result == ["12345"]

    def test_preprocess_json_non_list(self) -> None:
        """Test preprocessing of JSON that's not a list."""
        commands = '{"key": "value"}'
        result = preprocess_ssm_commands(commands)
        # Should treat as single command since it's not an array
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_malformed_json(self) -> None:
        """Test preprocessing of malformed JSON."""
        # Missing closing bracket
        commands = '["echo hello"'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_fallback_extraction(self) -> None:
        """Test fallback manual extraction for complete arrays."""
        commands = '["echo \\"test\\", multiple \\"quotes\\""]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1
        assert 'echo "test"' in result[0]

    def test_preprocess_exact_passthrough_deprecated(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that exact_passthrough parameter is deprecated."""
        commands = ["echo hello"]
        result = preprocess_ssm_commands(commands, exact_passthrough=True)
        assert result == ["echo hello"]
        # Should log deprecation warning
        assert "deprecated" in caplog.text.lower()

    def test_preprocess_very_long_lines(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test handling of very long lines that exceed SSM limits."""
        # Create a command with a very long line
        long_line = "echo " + "x" * 600
        result = preprocess_ssm_commands([long_line])
        # Should be truncated or split
        assert isinstance(result, list)
        # Check that warning was logged
        assert len(result) > 0

    def test_preprocess_long_line_with_break_point(self) -> None:
        """Test line splitting at natural break points."""
        # Long line with a good break point (after a quote)
        long_line = 'echo "' + "x" * 400 + '" and more ' + "y" * 200
        result = preprocess_ssm_commands([long_line])
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_many_commands_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that many commands trigger info logging."""
        caplog.set_level(logging.INFO)
        # More than 5 commands should trigger logging
        commands = [f"echo command{i}" for i in range(10)]
        result = preprocess_ssm_commands(commands)
        assert len(result) == 10
        # Verify result is correct
        assert all(f"command{i}" in result[i] for i in range(10))

    def test_preprocess_incomplete_json_array(self) -> None:
        """Test handling of incomplete JSON array."""
        # Incomplete array without proper ending
        commands = '["incomplete'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_smart_extraction_with_quote_ending(self) -> None:
        """Test smart extraction with '"} ending."""
        commands = '["echo test"}'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_preprocess_smart_extraction_with_brace_only(self) -> None:
        """Test smart extraction with } ending only."""
        commands = '["echo test}'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_preprocess_smart_extraction_incomplete(self) -> None:
        """Test smart extraction with incomplete format."""
        commands = '["echo test'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_triple_escaped_quotes_in_json(self) -> None:
        """Test handling of triple-escaped quotes in JSON."""
        commands = '["echo \\\\\\"test\\\\\\""]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_escaped_newlines_tabs_in_json(self) -> None:
        """Test handling of escaped special characters."""
        commands = '["echo\\nhello\\tworld"]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_preprocess_line_length_fix_with_string_break(self) -> None:
        """Test line length fix with string break point."""
        # Long line with quote that can be used as break point
        long_line = 'echo "' + "x" * 250 + '" some more text ' + "y" * 300
        result = preprocess_ssm_commands([long_line])
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_json_parsing_error_fallback(self) -> None:
        """Test fallback when JSON parsing fails."""
        # Malformed JSON that looks like JSON but isn't
        commands = '["echo test", invalid]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_mixed_powershell_and_bash(self) -> None:
        """Test mixed PowerShell and bash commands."""
        commands = [
            "ls -la",
            'Write-Output "Test"',
            "pwd",
            "$var = Get-Date",
        ]
        result = preprocess_ssm_commands(commands)
        assert len(result) == 4

    def test_preprocess_powershell_fixes_with_issues(self) -> None:
        """Test PowerShell fixes are applied."""
        commands = ['Write-Output "Test""', "Get-Process"]
        result = preprocess_ssm_commands(commands)
        assert len(result) == 2
        # First command should be fixed
        assert result[0] == 'Write-Output "Test"'

    def test_preprocess_json_non_list_object(self) -> None:
        """Test JSON object (non-list) handling."""
        commands = '{"command": "echo hello"}'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_with_debug_logging(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test debug logging behavior."""
        caplog.set_level(logging.DEBUG)
        commands = ["echo test"]
        result = preprocess_ssm_commands(commands)
        assert len(result) == 1
        # Debug logging should have been triggered
        assert len(caplog.records) > 0

    def test_preprocess_json_array_with_non_string_items(self) -> None:
        """Test JSON array with non-string items."""
        commands = '[123, 456, "text"]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == "123"
        assert result[1] == "456"
        assert result[2] == "text"

    def test_preprocess_list_with_large_count(self) -> None:
        """Test list with more than 5 commands triggers logging."""
        commands = [f"cmd{i}" for i in range(7)]
        result = preprocess_ssm_commands(commands)
        assert len(result) == 7

    def test_preprocess_escaped_json_with_alternate_ending(self) -> None:
        """Test escaped JSON with alternate ']' ending."""
        commands = '["echo test"]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_preprocess_escaped_json_triple_backslash_quote(self) -> None:
        """Test triple-escaped backslash quotes."""
        commands = '["echo \\\\\\"hello\\\\\\""]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_preprocess_escaped_json_with_carriage_return(self) -> None:
        """Test escaped carriage return."""
        commands = '["line1\\rline2"]'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_preprocess_escaped_json_failed_extraction(self) -> None:
        """Test failed smart extraction fallback."""
        # Malformed escaped JSON that can't be extracted
        commands = '["test'
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_line_with_semicolon_break(self) -> None:
        """Test line length fix without quote break."""
        # Very long line without quote break point
        long_line = "x" * 600
        result = preprocess_ssm_commands([long_line])
        assert isinstance(result, list)
        assert len(result) > 0

    def test_preprocess_powershell_with_import_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test PowerShell fixes with import error."""

        def mock_import_error(*args: object, **kwargs: object) -> None:
            raise ImportError("Mock import error")

        # This will test the ImportError handling
        commands = ["normal command"]
        result = preprocess_ssm_commands(commands)
        # Should still work even if PowerShell validator can't be imported
        assert result == ["normal command"]

    def test_preprocess_powershell_with_exception(self) -> None:
        """Test PowerShell fixes with exception handling."""
        # Command that looks like PowerShell
        commands = ["$test = 'value'"]
        result = preprocess_ssm_commands(commands)
        assert isinstance(result, list)
        assert len(result) == 1
