"""Tests for PowerShell validation utilities."""

from ohlala_smartops.utils.powershell_validator import (
    detect_powershell_syntax_errors,
    validate_and_fix_powershell,
)


class TestValidateAndFixPowershell:
    """Test cases for validate_and_fix_powershell function."""

    def test_fix_double_quotes_write_output(self) -> None:
        """Test fixing double quotes at end of Write-Output statement."""
        commands = ['Write-Output "Hello""']
        fixed, issues = validate_and_fix_powershell(commands)
        assert fixed == ['Write-Output "Hello"']
        assert len(issues) > 0
        assert "double quote" in issues[0].lower()  # Changed from "double quotes"

    def test_fix_double_quotes_at_end_of_line(self) -> None:
        """Test fixing double quotes at end of line."""
        commands = ['echo "Hello""']
        fixed, issues = validate_and_fix_powershell(commands)
        assert fixed == ['echo "Hello"']
        assert len(issues) > 0

    def test_fix_multiline_double_quotes(self) -> None:
        """Test fixing double quotes in multiline commands."""
        commands = ['Write-Output "Line1""\nWrite-Output "Line2""']
        fixed, issues = validate_and_fix_powershell(commands)
        assert fixed == ['Write-Output "Line1"\nWrite-Output "Line2"']
        assert len(issues) >= 2  # Should fix both lines

    def test_fix_over_escaped_quotes(self) -> None:
        """Test fixing over-escaped quotes in Write-Output."""
        commands = ['Write-Output \\"Hello\\"']
        fixed, issues = validate_and_fix_powershell(commands)
        assert fixed == ['Write-Output "Hello"']
        assert any("over-escaped" in issue.lower() for issue in issues)

    def test_no_fix_needed(self) -> None:
        """Test that valid commands are not modified."""
        commands = ['Write-Output "Hello"', "Get-Process"]
        fixed, issues = validate_and_fix_powershell(commands)
        assert fixed == commands
        assert len(issues) == 0

    def test_no_fix_triple_quotes(self) -> None:
        """Test that triple quotes are not incorrectly modified."""
        commands = ['echo """']
        fixed, _issues = validate_and_fix_powershell(commands)
        # Should not be modified as """ is a different pattern
        assert fixed == commands

    def test_odd_quotes_warning(self) -> None:
        """Test warning for odd number of quotes."""
        commands = ['echo "Hello" "World" "']
        _fixed, issues = validate_and_fix_powershell(commands)
        assert any("odd number" in issue.lower() for issue in issues)

    def test_odd_quotes_with_interpolation_no_warning(self) -> None:
        """Test that interpolation doesn't trigger false warnings."""
        # Variable interpolation can have odd quotes legitimately
        commands = ['echo "Value: $(Get-Date)"']
        _fixed, issues = validate_and_fix_powershell(commands)
        # Should not flag this as an error due to interpolation
        assert not any("odd number" in issue.lower() for issue in issues)

    def test_empty_commands(self) -> None:
        """Test handling of empty command list."""
        fixed, issues = validate_and_fix_powershell([])
        assert fixed == []
        assert issues == []

    def test_multiple_commands_with_mixed_issues(self) -> None:
        """Test fixing multiple commands with different issues."""
        commands = [
            'Write-Output "Good"',  # No issue
            'Write-Output "Bad""',  # Double quote issue
            'echo "Test"',  # No issue
        ]
        fixed, issues = validate_and_fix_powershell(commands)
        assert fixed[0] == 'Write-Output "Good"'
        assert fixed[1] == 'Write-Output "Bad"'
        assert fixed[2] == 'echo "Test"'
        # Only one command should have issues
        assert len([i for i in issues if "Command 1" in i]) > 0


class TestDetectPowershellSyntaxErrors:
    """Test cases for detect_powershell_syntax_errors function."""

    def test_detect_double_quotes_write_output(self) -> None:
        """Test detection of double quotes at end of Write-Output."""
        issues = detect_powershell_syntax_errors('Write-Output "Hello""')
        assert len(issues) > 0
        assert any("double quote" in issue.lower() for issue in issues)

    def test_detect_double_quotes_at_line_end(self) -> None:
        """Test detection of double quotes at end of line."""
        issues = detect_powershell_syntax_errors('echo "Hello""')
        assert len(issues) > 0
        assert any("double quote" in issue.lower() for issue in issues)

    def test_detect_multiline_issues(self) -> None:
        """Test detection of issues in multiline commands."""
        command = 'Write-Output "Line1""\nWrite-Output "Line2""'
        issues = detect_powershell_syntax_errors(command)
        assert len(issues) >= 2
        assert any("Line 1" in issue for issue in issues)
        assert any("Line 2" in issue for issue in issues)

    def test_detect_severe_quote_imbalance(self) -> None:
        """Test detection of severe quote imbalance."""
        # Many unmatched quotes without interpolation
        command = 'echo "a" "b" "c" "d" "e" "f"'  # 12 quotes = even, should pass
        issues = detect_powershell_syntax_errors(command)
        assert len(issues) == 0

        # Odd number with many quotes
        command = 'echo "a" "b" "c" "d" "e" "f" "'  # 13 quotes = odd
        issues = detect_powershell_syntax_errors(command)
        assert len(issues) > 0
        assert any("imbalance" in issue.lower() for issue in issues)

    def test_no_error_for_valid_command(self) -> None:
        """Test that valid commands have no detected errors."""
        issues = detect_powershell_syntax_errors('Write-Output "Hello World"')
        assert len(issues) == 0

    def test_no_error_for_interpolation(self) -> None:
        """Test that interpolation doesn't trigger false errors."""
        issues = detect_powershell_syntax_errors('Write-Output "Date: $(Get-Date)"')
        assert len(issues) == 0

    def test_no_error_for_variables(self) -> None:
        """Test that PowerShell variables don't trigger false errors."""
        issues = detect_powershell_syntax_errors("echo $HOME")
        assert len(issues) == 0

    def test_no_error_for_triple_quotes(self) -> None:
        """Test that triple quotes are not flagged as errors."""
        issues = detect_powershell_syntax_errors('echo """')
        assert len(issues) == 0

    def test_empty_command(self) -> None:
        """Test handling of empty command."""
        issues = detect_powershell_syntax_errors("")
        assert issues == []

    def test_complex_valid_powershell(self) -> None:
        """Test complex but valid PowerShell command."""
        command = """
        $folders = Get-ChildItem C:\\ -Directory
        $folders | ForEach-Object {
            Write-Output "Folder: $($_.Name)"
        }
        """
        issues = detect_powershell_syntax_errors(command)
        # Should not flag this as having errors
        assert len(issues) == 0
