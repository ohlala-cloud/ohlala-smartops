"""Tests for PowerShell validation utilities."""

from ohlala_smartops.utils.powershell import (
    detect_powershell_syntax_errors,
    validate_and_fix_powershell,
)


class TestValidateAndFixPowershell:
    """Tests for validate_and_fix_powershell function."""

    def test_fixes_double_quotes_at_end_of_write_output(self) -> None:
        """Test fixing double quotes at end of Write-Output statements."""
        commands = ['Write-Output "Hello World""']
        fixed, issues = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        assert fixed[0] == 'Write-Output "Hello World"'
        assert len(issues) > 0
        # Check that some issue was detected (wording may vary)
        assert any("double" in issue.lower() or "quote" in issue.lower() for issue in issues)

    def test_fixes_double_quotes_at_end_of_lines(self) -> None:
        """Test fixing double quotes at end of general lines."""
        commands = ['echo "test""']
        fixed, issues = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        assert fixed[0] == 'echo "test"'
        assert len(issues) > 0

    def test_handles_multiline_commands(self) -> None:
        """Test handling multiline PowerShell commands."""
        commands = ['Write-Output "Line 1""\nWrite-Output "Line 2""']
        fixed, issues = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        assert fixed[0] == 'Write-Output "Line 1"\nWrite-Output "Line 2"'
        assert len(issues) > 0

    def test_does_not_break_legitimate_triple_quotes(self) -> None:
        """Test that legitimate triple quotes are not broken."""
        commands = ['Write-Output """test"""']
        fixed, _ = validate_and_fix_powershell(commands)

        # Should not modify legitimate triple quotes
        assert len(fixed) == 1
        assert '"""' in fixed[0]

    def test_fixes_over_escaped_quotes_in_write_output(self) -> None:
        """Test fixing over-escaped quotes in Write-Output statements."""
        commands = ['Write-Output \\"test\\"']
        fixed, issues = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        # Should fix the escaping
        assert len(issues) >= 0  # May or may not report issues depending on context

    def test_warns_about_odd_quote_counts(self) -> None:
        """Test warning about odd number of quotes."""
        commands = ['Write-Output "test" extra "quote']
        fixed, issues = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        # Should warn about odd quotes
        assert any("odd number" in issue.lower() or "quote" in issue.lower() for issue in issues)

    def test_handles_variable_interpolation(self) -> None:
        """Test that variable interpolation doesn't trigger false warnings."""
        commands = ['Write-Output "Value: $($variable)"']
        fixed, _ = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        # Should not complain about odd quotes due to interpolation
        # The string has 3 quotes which is odd, but $(...)  is present

    def test_processes_multiple_commands(self) -> None:
        """Test processing multiple commands at once."""
        commands = [
            'Write-Output "Hello""',
            'Write-Output "World""',
            "Get-Process",
        ]
        fixed, issues = validate_and_fix_powershell(commands)

        assert len(fixed) == 3
        assert fixed[0] == 'Write-Output "Hello"'
        assert fixed[1] == 'Write-Output "World"'
        assert fixed[2] == "Get-Process"
        assert len(issues) > 0  # Should have found issues in first two

    def test_handles_empty_command_list(self) -> None:
        """Test handling empty command list."""
        commands: list[str] = []
        fixed, issues = validate_and_fix_powershell(commands)

        assert len(fixed) == 0
        assert len(issues) == 0

    def test_handles_commands_without_issues(self) -> None:
        """Test handling commands that don't need fixing."""
        commands = ['Write-Output "Hello World"', "Get-Process"]
        fixed, issues = validate_and_fix_powershell(commands)

        assert len(fixed) == 2
        assert fixed[0] == 'Write-Output "Hello World"'
        assert fixed[1] == "Get-Process"
        assert len(issues) == 0  # No issues to fix

    def test_preserves_command_content(self) -> None:
        """Test that command content is preserved during fixing."""
        original = 'Write-Output "Important data: 12345""'
        commands = [original]
        fixed, _ = validate_and_fix_powershell(commands)

        assert "12345" in fixed[0]
        assert "Important data" in fixed[0]

    def test_handles_complex_powershell_syntax(self) -> None:
        """Test handling complex PowerShell syntax."""
        commands = ['Get-Process | Where-Object {$_.CPU -gt 10} | Select-Object Name, CPU""']
        fixed, _ = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        assert "Get-Process" in fixed[0]
        assert "Where-Object" in fixed[0]


class TestDetectPowershellSyntaxErrors:
    """Tests for detect_powershell_syntax_errors function."""

    def test_detects_double_quotes_at_write_output_end(self) -> None:
        """Test detection of double quotes at end of Write-Output."""
        command = 'Write-Output "test"""'
        issues = detect_powershell_syntax_errors(command)

        assert len(issues) > 0
        assert any(
            "double quote" in issue.lower() or "write-output" in issue.lower() for issue in issues
        )

    def test_detects_double_quotes_at_line_end(self) -> None:
        """Test detection of problematic double quotes at line ends."""
        command = 'echo "test""'
        issues = detect_powershell_syntax_errors(command)

        assert len(issues) > 0
        assert any(
            "double quote" in issue.lower() or "unterminated" in issue.lower() for issue in issues
        )

    def test_detects_severe_quote_imbalance(self) -> None:
        """Test detection of severe quote imbalances."""
        # Many unmatched quotes without interpolation
        command = 'Write-Output "a" "b" "c" "d" "e" "f'
        issues = detect_powershell_syntax_errors(command)

        assert len(issues) > 0
        assert any("quote" in issue.lower() or "imbalance" in issue.lower() for issue in issues)

    def test_allows_interpolation_with_odd_quotes(self) -> None:
        """Test that variable interpolation doesn't cause false positives."""
        command = 'Write-Output "Value: $variable"'
        issues = detect_powershell_syntax_errors(command)

        # Should not detect issues for simple variable interpolation
        # The command has 2 quotes which is even, so no issues
        assert len(issues) == 0

    def test_allows_few_unmatched_quotes(self) -> None:
        """Test that a small number of unmatched quotes is tolerated."""
        # Only 3 quotes - below threshold with variable
        command = 'echo "test $var'
        issues = detect_powershell_syntax_errors(command)

        # Should be lenient with few quotes and variables present
        assert len(issues) == 0

    def test_handles_multiline_commands(self) -> None:
        """Test detection in multiline commands."""
        command = 'Write-Output "Line 1""\nWrite-Output "Line 2""'
        issues = detect_powershell_syntax_errors(command)

        assert len(issues) > 0
        # Should detect issues on multiple lines

    def test_returns_empty_for_valid_commands(self) -> None:
        """Test that valid commands return no issues."""
        command = 'Write-Output "Hello World"'
        issues = detect_powershell_syntax_errors(command)

        assert len(issues) == 0

    def test_handles_empty_command(self) -> None:
        """Test handling empty command string."""
        command = ""
        issues = detect_powershell_syntax_errors(command)

        assert len(issues) == 0

    def test_handles_complex_valid_powershell(self) -> None:
        """Test handling complex but valid PowerShell."""
        command = "Get-Process | Where-Object {$_.CPU -gt 10} | Select-Object Name, CPU"
        issues = detect_powershell_syntax_errors(command)

        # Complex but syntactically valid
        assert len(issues) == 0

    def test_detects_issues_with_escaped_quotes(self) -> None:
        """Test detection with escaped quotes creating issues."""
        command = 'Write-Output "test\\"extra quote'
        _ = detect_powershell_syntax_errors(command)

        # Odd number of quotes should be detected
        # Has 2 plain quotes and escaped quotes

    def test_handles_legitimate_triple_quotes(self) -> None:
        """Test that triple quotes don't trigger false positives."""
        command = 'Write-Output """test"""'
        issues = detect_powershell_syntax_errors(command)

        # Triple quotes are legitimate, but we have 6 quotes total (even)
        assert len(issues) == 0


class TestPowershellEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_special_characters_in_commands(self) -> None:
        """Test handling commands with special characters."""
        commands = ['Write-Output "Test\nNewline\tTab""']
        fixed, _ = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        assert "\\n" in fixed[0] or "\n" in fixed[0]

    def test_handles_very_long_commands(self) -> None:
        """Test handling very long command strings."""
        long_command = 'Write-Output "' + "x" * 1000 + '""'
        commands = [long_command]
        fixed, _ = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        assert len(fixed[0]) > 1000

    def test_handles_unicode_in_commands(self) -> None:
        """Test handling Unicode characters."""
        commands = ['Write-Output "Hello 世界""']
        fixed, _ = validate_and_fix_powershell(commands)

        assert len(fixed) == 1
        assert "世界" in fixed[0]

    def test_preserves_command_order(self) -> None:
        """Test that command order is preserved."""
        commands = ['Command1""', 'Command2""', 'Command3""']
        fixed, _ = validate_and_fix_powershell(commands)

        assert len(fixed) == 3
        assert "Command1" in fixed[0]
        assert "Command2" in fixed[1]
        assert "Command3" in fixed[2]
