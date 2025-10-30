"""Validation utilities for AWS Systems Manager (SSM) commands.

This module provides validation functions to check SSM commands before they
are sent to AWS. It detects common issues like JSON encoding errors, invalid
formats, and PowerShell syntax problems.
"""

import logging
from collections.abc import Sequence
from typing import Final

from ohlala_smartops.constants import SSM_OUTPUT_LIMIT
from ohlala_smartops.utils.powershell import (
    detect_powershell_syntax_errors,
    validate_and_fix_powershell,
)

logger: Final = logging.getLogger(__name__)


def validate_ssm_commands(commands: Sequence[str]) -> tuple[bool, str]:  # noqa: PLR0911
    """Validate SSM commands before sending to AWS.

    Performs comprehensive validation including:
    - Empty command checks
    - Type validation (must be strings)
    - JSON encoding detection (commands should be plain strings)
    - PowerShell syntax validation
    - Length warnings (SSM has 24KB output limit)
    - Null byte and problematic character detection

    Args:
        commands: Sequence of command strings to validate.

    Returns:
        Tuple of (is_valid, error_message):
        - is_valid: True if all commands are valid, False otherwise
        - error_message: Empty string if valid, error description otherwise

    Example:
        >>> is_valid, error = validate_ssm_commands(["ls -la"])
        >>> print(is_valid)
        True
        >>> is_valid, error = validate_ssm_commands(['["command"]'])
        >>> print(error)
        'Command 0 appears to be JSON-encoded. Commands should be plain strings.'
    """
    if not commands:
        return False, "Commands list is empty"

    if not isinstance(commands, list | tuple):
        return False, f"Commands must be a list or tuple, got {type(commands)}"

    for i, cmd in enumerate(commands):
        if not isinstance(cmd, str):
            return False, f"Command {i} is not a string: {type(cmd)}"

        # Check for common JSON encoding issues
        if cmd.startswith(('["', "['")):
            logger.error("Command %d starts with JSON array syntax: %s...", i, cmd[:50])
            return (
                False,
                f"Command {i} appears to be JSON-encoded. Commands should be plain strings.",
            )

        if cmd.startswith("{") and cmd.endswith("}"):
            logger.error("Command %d appears to be JSON object: %s...", i, cmd[:50])
            return (
                False,
                f"Command {i} appears to be a JSON object. Commands should be plain strings.",
            )

        # Check for excessive escaping that would break PowerShell/Bash
        if '\\"' in cmd and cmd.count('\\"') > cmd.count('"'):
            logger.warning(
                "Command %d has escaped quotes that may cause issues: %s...", i, cmd[:50]
            )
            # This is a warning, not a failure
            # some commands legitimately need escaped quotes

        # Check for null bytes or other problematic characters
        if "\x00" in cmd:
            return False, f"Command {i} contains null bytes"

        # PowerShell syntax validation for PowerShell scripts
        if _looks_like_powershell(cmd):
            ps_issues = detect_powershell_syntax_errors(cmd)
            if ps_issues:
                error_msg = f"Command {i} has PowerShell syntax issues: {'; '.join(ps_issues)}"
                logger.error(error_msg)
                return False, error_msg

        # Warn about very long commands (SSM limit is 24KB for output)
        if len(cmd) > SSM_OUTPUT_LIMIT // 2:
            logger.warning(
                "Command %d is very long (%d chars), may hit SSM output limits",
                i,
                len(cmd),
            )

    logger.info("Validated %d command(s) successfully", len(commands))
    return True, ""


def fix_common_issues(commands: Sequence[str]) -> list[str]:
    """Attempt to fix common command issues.

    This function automatically fixes common command formatting problems:
    - JSON-wrapped commands (extracts the inner command)
    - PowerShell syntax issues (double quotes, escaping)
    - Excessive escaping

    Args:
        commands: Sequence of potentially problematic commands.

    Returns:
        List of fixed command strings.

    Example:
        >>> cmds = ['["ls -la"]']
        >>> fixed = fix_common_issues(cmds)
        >>> print(fixed[0])
        'ls -la'
    """
    fixed: list[str] = []

    for cmd in commands:
        # If command is accidentally wrapped in JSON array syntax
        if cmd.startswith('["') and cmd.endswith('"]'):
            # Extract the actual command
            inner = cmd[2:-2]
            # Unescape common sequences
            inner = inner.replace('\\"', '"')
            inner = inner.replace("\\n", "\n")
            inner = inner.replace("\\t", "\t")
            inner = inner.replace("\\\\", "\\")
            fixed.append(inner)
            logger.info("Fixed JSON-wrapped command: %s...", inner[:50])
        # Apply PowerShell syntax fixes for PowerShell commands
        elif _looks_like_powershell(cmd):
            fixed_cmds, issues = validate_and_fix_powershell([cmd])
            if issues:
                logger.info("Fixed PowerShell syntax issues: %s", "; ".join(issues))
                fixed.append(fixed_cmds[0])
            else:
                fixed.append(cmd)
        else:
            fixed.append(cmd)

    return fixed


def _looks_like_powershell(cmd: str) -> bool:
    """Detect if a command looks like PowerShell.

    Uses heuristics to determine if a command string appears to be PowerShell
    based on common cmdlets and syntax patterns.

    Args:
        cmd: Command string to check.

    Returns:
        True if the command appears to be PowerShell, False otherwise.
    """
    powershell_indicators = (
        "Write-Output",
        "Write-Host",
        "Write-Error",
        "Write-Warning",
        "Get-",
        "Set-",
        "New-",
        "Remove-",
        "$",  # PowerShell variables
        "-Property",
        "-Filter",
        "| Select",
        "| Where",
    )

    return any(indicator in cmd for indicator in powershell_indicators)
