"""PowerShell syntax validation and fixing utilities.

This module provides functions to detect and fix common PowerShell syntax errors
that can occur when AI models generate PowerShell commands. It focuses on issues
like doubled quotes, unmatched quotes, and excessive escaping.
"""

import logging
import re
from typing import Final

logger: Final = logging.getLogger(__name__)


def validate_and_fix_powershell(
    commands: list[str],
) -> tuple[list[str], list[str]]:
    """Validate and fix common PowerShell syntax issues.

    This function attempts to automatically fix common PowerShell syntax errors:
    - Double quotes at end of Write-Output statements
    - General double quotes at end of lines
    - Over-escaped quotes in Write-Output contexts
    - Unmatched quote validation (warnings only)

    Args:
        commands: List of PowerShell command strings to validate and fix.

    Returns:
        Tuple of (fixed_commands, issues_found). issues_found is a list of
        strings describing what was fixed in each command.

    Examples:
        >>> validate_and_fix_powershell(['Write-Output "Hello""'])
        (['Write-Output "Hello"'], ['Command 0: Fixed double quote at end of line 1'])
    """
    fixed_commands: list[str] = []
    issues_found: list[str] = []

    for i, cmd in enumerate(commands):
        fixed_cmd = cmd
        command_issues: list[str] = []

        # Fix 1: Double quotes at end of Write-Output statements
        # Pattern: Write-Output "some text""  -> Write-Output "some text"
        double_quote_pattern = r'(Write-Output\s+"[^"]*")""'
        if re.search(double_quote_pattern, fixed_cmd):
            fixed_cmd = re.sub(double_quote_pattern, r'\1"', fixed_cmd)
            command_issues.append("Fixed double quotes at end of Write-Output statement")
            logger.info("Fixed double quotes in command %d", i)

        # Fix 2: General double quotes at end of lines
        # Pattern: "some text""  -> "some text"
        # Be careful not to break legitimate cases like nested quotes
        lines = fixed_cmd.split("\n")
        fixed_lines: list[str] = []

        for line_num, line in enumerate(lines, 1):
            # Check for lines ending with doubled quotes that look like errors
            if line.strip().endswith('""') and not line.strip().endswith('"""'):
                # Check if this looks like an unintended double quote
                # Pattern: something ends with "text"" (but not """)
                if re.search(r'[^""]""$', line.strip()):
                    # Remove only ONE trailing quote, not all of them
                    fixed_line = line[:-1] if line.endswith('""') else line
                    fixed_lines.append(fixed_line)
                    command_issues.append(f"Fixed double quote at end of line {line_num}")
                    logger.info(
                        "Fixed double quote at end of line %d: %s",
                        line_num,
                        line.strip(),
                    )
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)

        fixed_cmd = "\n".join(fixed_lines)

        # Fix 3: Unmatched quotes validation
        # Count quotes to detect potential unmatched quote issues
        double_quotes = fixed_cmd.count('"')

        # For PowerShell, double quotes should generally be even (paired)
        # BUT only flag as an error if we have a significant imbalance
        if (
            double_quotes % 2 != 0
            and double_quotes > 1
            and not ("$(" in fixed_cmd and ")" in fixed_cmd)
        ):
            command_issues.append(
                f"Warning: Odd number of double quotes ({double_quotes}) "
                "- may indicate syntax issue"
            )
            logger.warning(
                "Command %d has odd number of double quotes: %d",
                i,
                double_quotes,
            )

        # Fix 4: Common PowerShell escaping issues
        # Fix over-escaped quotes in Write-Output statements
        # Pattern: Write-Output \\"text\\"  -> Write-Output "text"
        if '\\"' in fixed_cmd:
            # Only fix escaped quotes in Write-Output contexts where they
            # shouldn't be escaped
            write_output_pattern = r'(Write-Output\s+)\\(".*?)\\"'
            if re.search(write_output_pattern, fixed_cmd):
                fixed_cmd = re.sub(write_output_pattern, r'\1\2"', fixed_cmd)
                command_issues.append("Fixed over-escaped quotes in Write-Output")
                logger.info("Fixed over-escaped quotes in command %d", i)

        fixed_commands.append(fixed_cmd)
        if command_issues:
            issues_found.extend([f"Command {i}: {issue}" for issue in command_issues])

    return fixed_commands, issues_found


def detect_powershell_syntax_errors(command: str) -> list[str]:
    """Detect common PowerShell syntax errors that would cause execution failure.

    This function performs static analysis to detect PowerShell syntax errors
    without actually executing the command. It focuses on errors that would
    definitely cause PowerShell to fail, not warnings or style issues.

    Args:
        command: PowerShell command string to analyze.

    Returns:
        List of detected issues that would actually cause PowerShell to fail.
        Empty list if no critical issues are detected.

    Examples:
        >>> detect_powershell_syntax_errors('Write-Output "Hello""')
        ['Double quotes at end of Write-Output statement']
        >>> detect_powershell_syntax_errors('Write-Output "Hello"')
        []
    """
    issues: list[str] = []

    # Check for double quotes at end of Write-Output statements (the main issue)
    if re.search(r'Write-Output\s+"[^"]*"""', command):
        issues.append("Double quotes at end of Write-Output statement")

    # Check for obvious double quote issues at end of lines
    lines = command.split("\n")
    for line_num, line in enumerate(lines, 1):
        if (
            line.strip().endswith('""')
            and not line.strip().endswith('"""')
            and re.search(r'[^""]""$', line.strip())
        ):
            # This is likely the issue causing PowerShell to fail
            issues.append(f"Line {line_num}: Double quote at end creates unterminated string")

    # Only check for severe quote imbalances that would definitely break
    # PowerShell
    double_quotes = command.count('"')
    if double_quotes % 2 != 0:
        # Be more lenient - only flag if there are many unmatched quotes
        # AND no variable interpolation
        # Variable interpolation ($(...)) and PowerShell variables ($var)
        # can cause legitimate odd quote counts
        has_interpolation = "$(" in command or bool(re.search(r"\$\w+", command))
        # Raised threshold and check for variables
        if double_quotes > 5 and not has_interpolation:
            issues.append("Severe quote imbalance detected")

    return issues
