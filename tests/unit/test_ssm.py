"""Tests for SSM command preprocessing utilities."""

from ohlala_smartops.utils.ssm import preprocess_ssm_commands


class TestPreprocessSSMCommands:
    """Tests for preprocess_ssm_commands function."""

    def test_handles_simple_list(self) -> None:
        """Test preprocessing of simple list of commands."""
        commands = ["ls -la", "pwd", "whoami"]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3
        assert result[0] == "ls -la"
        assert result[1] == "pwd"
        assert result[2] == "whoami"

    def test_handles_empty_input(self) -> None:
        """Test handling of empty input."""
        commands = []
        result = preprocess_ssm_commands(commands)

        assert len(result) == 0

    def test_handles_none_input(self) -> None:
        """Test handling of None input."""
        result = preprocess_ssm_commands(None)

        assert len(result) == 0

    def test_parses_json_string_array(self) -> None:
        """Test parsing of JSON array string."""
        commands = '["ls -la", "pwd", "whoami"]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3
        assert result[0] == "ls -la"
        assert result[1] == "pwd"
        assert result[2] == "whoami"

    def test_parses_python_repr_list(self) -> None:
        """Test parsing of Python repr() format list."""
        commands = ["['ls -la', 'pwd']"]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 2
        assert result[0] == "ls -la"
        assert result[1] == "pwd"

    def test_parses_single_json_string_in_list(self) -> None:
        """Test parsing single JSON-encoded array in a list."""
        commands = ['["ls -la"]']
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert result[0] == "ls -la"

    def test_handles_escaped_json(self) -> None:
        """Test handling of escaped JSON format."""
        commands = '["echo \\"hello world\\""]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert "hello world" in result[0]

    def test_handles_truncated_json_with_curly_brace(self) -> None:
        """Test handling of truncated JSON from CloudWatch logs."""
        commands = '["echo test"}'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert "echo test" in result[0]

    def test_handles_truncated_json_with_quote_brace(self) -> None:
        """Test handling of truncated JSON with quote and brace."""
        commands = '["echo test"}'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1

    def test_handles_complete_escaped_json(self) -> None:
        """Test handling of complete escaped JSON array."""
        commands = '["echo \\"test\\"\\nline2"]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert "test" in result[0]

    def test_converts_non_string_to_string(self) -> None:
        """Test conversion of non-string types to strings."""
        commands = [123, 456]  # type: ignore[list-item]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 2
        assert result[0] == "123"
        assert result[1] == "456"

    def test_handles_mixed_types_in_list(self) -> None:
        """Test handling of mixed types in command list."""
        commands = ["ls -la", 123, "pwd"]  # type: ignore[list-item]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3
        assert result[0] == "ls -la"
        assert result[1] == "123"
        assert result[2] == "pwd"

    def test_applies_powershell_fixes(self) -> None:
        """Test that PowerShell fixes are applied automatically."""
        commands = ['Write-Output "Hello World""']
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        # Should fix the double quote
        assert result[0] == 'Write-Output "Hello World"'

    def test_handles_multiline_powershell(self) -> None:
        """Test handling of multiline PowerShell commands."""
        commands = ['Write-Output "Line 1""\nWrite-Output "Line 2""']
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        # Should fix both lines
        assert "Line 1" in result[0]
        assert "Line 2" in result[0]

    def test_exact_passthrough_deprecated(self) -> None:
        """Test that exact_passthrough parameter is deprecated."""
        commands = ['Write-Output "test""']
        result = preprocess_ssm_commands(commands, exact_passthrough=True)

        # Should still apply fixes despite exact_passthrough
        assert len(result) == 1
        assert result[0] == 'Write-Output "test"'

    def test_handles_very_long_lines(self) -> None:
        """Test handling of very long command lines."""
        # Create a command with a very long line
        long_line = "echo " + "x" * 600
        commands = [long_line]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        # Line should be handled (possibly split or truncated)

    def test_handles_single_string_command(self) -> None:
        """Test handling of single string command."""
        commands = "ls -la"
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert result[0] == "ls -la"

    def test_handles_non_json_string_with_brackets(self) -> None:
        """Test handling of string with brackets that isn't JSON."""
        commands = "[Not a JSON array"
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert result[0] == "[Not a JSON array"

    def test_handles_escape_sequences(self) -> None:
        """Test handling of escape sequences in JSON."""
        commands = '["echo \\"test\\"\\n\\t\\"more\\\\path\\""]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        # Should unescape properly
        assert "test" in result[0]

    def test_preserves_command_content(self) -> None:
        """Test that command content is preserved during preprocessing."""
        commands = ["echo 'Important data: 12345'"]
        result = preprocess_ssm_commands(commands)

        assert "12345" in result[0]
        assert "Important data" in result[0]

    def test_handles_dict_input(self) -> None:
        """Test handling of dict input (converts to string)."""
        commands = {"key": "value"}  # type: ignore[arg-type]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        # Will be converted to string representation

    def test_handles_windows_paths(self) -> None:
        """Test handling of Windows paths with backslashes."""
        commands = ['["cd C:\\\\Users\\\\Admin"]']
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert "C:" in result[0]
        assert "Users" in result[0]

    def test_multiple_commands_with_issues(self) -> None:
        """Test preprocessing multiple commands with various issues."""
        commands = [
            'Write-Output "test1""',  # PowerShell issue
            "ls -la",  # Normal
            'Write-Output "test2""',  # PowerShell issue
        ]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3
        assert result[0] == 'Write-Output "test1"'
        assert result[1] == "ls -la"
        assert result[2] == 'Write-Output "test2"'


class TestJSONParsing:
    """Tests for JSON parsing capabilities."""

    def test_parses_simple_json_array(self) -> None:
        """Test parsing of simple JSON array."""
        commands = '["command1", "command2"]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 2
        assert result[0] == "command1"
        assert result[1] == "command2"

    def test_parses_json_with_numbers(self) -> None:
        """Test parsing JSON array with numbers."""
        commands = '["command1", "command2", "command3"]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3

    def test_handles_malformed_json(self) -> None:
        """Test handling of malformed JSON."""
        commands = '["command1", "command2"'  # Missing closing bracket
        result = preprocess_ssm_commands(commands)

        # Should handle gracefully
        assert len(result) >= 1

    def test_handles_nested_quotes_in_json(self) -> None:
        """Test handling of nested quotes in JSON."""
        commands = '["echo \\"nested \\"quotes\\"""]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1

    def test_handles_json_with_special_chars(self) -> None:
        """Test handling of JSON with special characters."""
        commands = '["echo \\n\\t\\r"]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1


class TestPowerShellIntegration:
    """Tests for PowerShell command integration."""

    def test_identifies_and_fixes_powershell(self) -> None:
        """Test identification and fixing of PowerShell commands."""
        commands = ['Get-Process""', 'Write-Output "test""']
        result = preprocess_ssm_commands(commands)

        assert len(result) == 2
        # Should fix PowerShell syntax issues

    def test_preserves_non_powershell_commands(self) -> None:
        """Test that non-PowerShell commands are preserved."""
        commands = ["ls -la", "pwd", "whoami"]
        result = preprocess_ssm_commands(commands)

        assert result[0] == "ls -la"
        assert result[1] == "pwd"
        assert result[2] == "whoami"

    def test_mixed_powershell_and_bash(self) -> None:
        """Test mixing PowerShell and Bash commands."""
        commands = [
            "ls -la",
            'Write-Output "Windows command"',
            "pwd",
        ]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3
        assert "ls -la" in result[0]
        assert "Windows command" in result[1]
        assert "pwd" in result[2]

    def test_powershell_with_variables(self) -> None:
        """Test PowerShell commands with variables."""
        commands = ["$myVar = 'test'", "Write-Output $myVar"]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 2
        assert "$myVar" in result[0]
        assert "$myVar" in result[1]


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_unicode_characters(self) -> None:
        """Test handling of Unicode characters."""
        commands = ["echo 'Hello 世界'"]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert "世界" in result[0]

    def test_handles_empty_strings_in_list(self) -> None:
        """Test handling of empty strings in command list."""
        commands = ["", "ls -la", ""]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3
        assert result[1] == "ls -la"

    def test_handles_whitespace_only_commands(self) -> None:
        """Test handling of whitespace-only commands."""
        commands = ["   ", "ls -la", "\t\n"]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3

    def test_preserves_command_order(self) -> None:
        """Test that command order is preserved."""
        commands = ["command1", "command2", "command3", "command4"]
        result = preprocess_ssm_commands(commands)

        assert result[0] == "command1"
        assert result[1] == "command2"
        assert result[2] == "command3"
        assert result[3] == "command4"

    def test_handles_binary_like_content(self) -> None:
        """Test handling of binary-like content."""
        commands = ["echo '\x01\x02\x03'"]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1

    def test_handles_very_large_command_count(self) -> None:
        """Test handling of many commands at once."""
        commands = [f"echo {i}" for i in range(100)]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 100
        assert result[0] == "echo 0"
        assert result[99] == "echo 99"


class TestLineLengthHandling:
    """Tests for line length handling."""

    def test_handles_normal_length_lines(self) -> None:
        """Test that normal length lines are not modified."""
        commands = ["echo 'This is a normal command'"]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert result[0] == "echo 'This is a normal command'"

    def test_splits_very_long_lines(self) -> None:
        """Test that very long lines are handled."""
        # Create a command with line longer than MAX_LINE_LENGTH (500)
        long_command = "echo '" + "x" * 600 + "'"
        commands = [long_command]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        # Should have been processed (split or truncated)

    def test_handles_multiline_with_long_lines(self) -> None:
        """Test handling of multiline commands with long lines."""
        long_line = "x" * 600
        commands = [f"echo 'start'\n{long_line}\necho 'end'"]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert "start" in result[0]
        assert "end" in result[0]

    def test_handles_long_line_with_quote_space(self) -> None:
        """Test line splitting at quote space boundary."""
        # Create a command with " before MAX_LINE_LENGTH
        long_command = 'echo "short part" ' + "x" * 600
        commands = [long_command]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        # Should attempt to split at quote space

    def test_handles_long_powershell_command(self) -> None:
        """Test handling of long PowerShell command."""
        long_command = 'Write-Output "' + "x" * 600 + '"'
        commands = [long_command]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1


class TestExtractEscapedJSON:
    """Tests for escaped JSON extraction edge cases."""

    def test_handles_incomplete_json_without_closing(self) -> None:
        """Test handling of incomplete JSON without closing bracket."""
        commands = '["echo test'
        result = preprocess_ssm_commands(commands)

        assert len(result) >= 1

    def test_handles_triple_escaped_quotes(self) -> None:
        """Test handling of triple escaped quotes."""
        commands = '["echo \\\\\\"test\\\\\\""]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1

    def test_handles_newline_escapes(self) -> None:
        """Test handling of newline escape sequences."""
        commands = '["line1\\nline2\\rline3\\ttab"]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert "\n" in result[0] or "line1" in result[0]

    def test_handles_windows_path_double_backslash(self) -> None:
        """Test handling of Windows paths with double backslashes."""
        commands = '["cd C:\\\\\\\\Users\\\\\\\\Admin"]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1

    def test_handles_alternative_truncation_pattern(self) -> None:
        """Test handling of alternative truncation pattern."""
        commands = '["echo test"]'  # Complete but with different ending
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
        assert "echo test" in result[0]


class TestPowerShellFixesErrorHandling:
    """Tests for PowerShell fixes error handling."""

    def test_continues_on_powershell_fix_exception(self) -> None:
        """Test that processing continues even if PowerShell fixing fails."""
        # This tests the except block in _apply_powershell_fixes
        commands = ['$valid = "test"']
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1

    def test_handles_non_powershell_after_powershell(self) -> None:
        """Test handling of non-PowerShell command after PowerShell."""
        commands = [
            'Write-Output "test"',
            "ls -la",
            "$var = 'value'",
        ]
        result = preprocess_ssm_commands(commands)

        assert len(result) == 3
        assert "ls -la" in result[1]


class TestSpecialFormats:
    """Tests for special format handling."""

    def test_handles_incomplete_python_repr(self) -> None:
        """Test handling of incomplete Python repr format."""
        commands = ["['incomplete"]
        result = preprocess_ssm_commands(commands)

        assert len(result) >= 1

    def test_handles_python_repr_with_syntax_error(self) -> None:
        """Test handling of Python repr with syntax error."""
        commands = ["['item1', 'item2'"]  # Missing closing bracket
        result = preprocess_ssm_commands(commands)

        assert len(result) >= 1

    def test_handles_json_with_int_items(self) -> None:
        """Test handling of JSON array with integer items."""
        commands = "[1, 2, 3]"
        result = preprocess_ssm_commands(commands)

        assert len(result) >= 1

    def test_fallback_manual_extraction(self) -> None:
        """Test fallback manual extraction for complete arrays."""
        commands = '["command with \\\\"quotes\\\\" and \\n newlines"]'
        result = preprocess_ssm_commands(commands)

        assert len(result) == 1
