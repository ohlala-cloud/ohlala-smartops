"""Validation utilities for SSM commands before sending to AWS.

This module provides functions to validate and fix common issues in SSM commands
before they are sent to AWS Systems Manager. It performs checks for JSON encoding
issues, PowerShell syntax errors, and other common problems.
"""

import logging
from typing import Final

logger: Final = logging.getLogger(__name__)


def validate_ssm_commands(commands: list[str]) -> tuple[bool, str]:  # noqa: PLR0911
    """Validate SSM commands before sending to AWS.

    Performs comprehensive validation including:
    - Type checking (must be list of strings)
    - JSON encoding issue detection
    - PowerShell syntax validation
    - Special character validation
    - Size limit warnings

    Args:
        commands: List of command strings to validate.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
        If invalid, error_message describes the first issue found.

    Examples:
        >>> validate_ssm_commands(["echo hello"])
        (True, '')
        >>> validate_ssm_commands([])
        (False, 'Commands list is empty')
    """
    if not commands:
        return False, "Commands list is empty"

    if not isinstance(commands, list):
        return False, f"Commands must be a list, got {type(commands).__name__}"

    for i, cmd in enumerate(commands):
        if not isinstance(cmd, str):
            return False, f"Command {i} is not a string: {type(cmd).__name__}"

        # Check for common JSON encoding issues
        if cmd.startswith(('["', "['")):
            logger.error(
                "Command %d starts with JSON array syntax: %s...",
                i,
                cmd[:50],
            )
            return (
                False,
                f"Command {i} appears to be JSON-encoded. Commands should be plain strings.",
            )

        if cmd.startswith("{") and cmd.endswith("}"):
            logger.error(
                "Command %d appears to be JSON object: %s...",
                i,
                cmd[:50],
            )
            return (
                False,
                f"Command {i} appears to be a JSON object. Commands should be plain strings.",
            )

        # Check for excessive escaping that would break PowerShell/Bash
        if '\\"' in cmd and cmd.count('\\"') > cmd.count('"'):
            logger.warning(
                "Command %d has escaped quotes that may cause issues: %s...",
                i,
                cmd[:50],
            )
            # This is a warning, not a failure - some commands legitimately need
            # escaped quotes

        # Check for null bytes or other problematic characters
        if "\x00" in cmd:
            return False, f"Command {i} contains null bytes"

        # PowerShell syntax validation for PowerShell scripts
        if "Write-Output" in cmd or "Get-" in cmd or "$" in cmd:
            # This looks like PowerShell, validate syntax
            from ohlala_smartops.utils.powershell_validator import (
                detect_powershell_syntax_errors,
            )

            ps_issues = detect_powershell_syntax_errors(cmd)
            if ps_issues:
                error_msg = f"Command {i} has PowerShell syntax issues: {'; '.join(ps_issues)}"
                logger.error("%s", error_msg)
                return False, error_msg

        # Warn about very long commands (SSM limit is 24KB for output)
        if len(cmd) > 10000:
            logger.warning(
                "Command %d is very long (%d chars), may hit SSM limits",
                i,
                len(cmd),
            )

    logger.info("Validated %d command(s) successfully", len(commands))
    return True, ""


def fix_common_issues(commands: list[str]) -> list[str]:
    """Attempt to fix common command issues.

    This function attempts to automatically fix common issues in SSM commands:
    - JSON-wrapped commands (removes array syntax and unescapes)
    - PowerShell syntax errors (calls PowerShell validator)

    Args:
        commands: List of potentially problematic commands.

    Returns:
        List of fixed commands. If no fixes are needed, returns original commands.

    Examples:
        >>> fix_common_issues(['["echo hello"]'])
        ['echo hello']
        >>> fix_common_issues(['echo hello'])
        ['echo hello']
    """
    fixed: list[str] = []

    for cmd in commands:
        # If command is accidentally wrapped in JSON array syntax
        if cmd.startswith('["') and cmd.endswith('"]'):
            # Extract the actual command
            inner = cmd[2:-2]
            # Unescape quotes
            inner = inner.replace('\\"', '"')
            inner = inner.replace("\\n", "\n")
            inner = inner.replace("\\t", "\t")
            inner = inner.replace("\\\\", "\\")
            fixed.append(inner)
            logger.info("Fixed JSON-wrapped command: %s...", inner[:50])
        # Apply PowerShell syntax fixes if needed
        elif "Write-Output" in cmd or "Get-" in cmd or "$" in cmd:
            # This looks like PowerShell, try to fix syntax issues
            from ohlala_smartops.utils.powershell_validator import (
                validate_and_fix_powershell,
            )

            fixed_cmds, issues = validate_and_fix_powershell([cmd])
            if issues:
                logger.info(
                    "Fixed PowerShell syntax issues: %s",
                    "; ".join(issues),
                )
                fixed.append(fixed_cmds[0])
            else:
                fixed.append(cmd)
        else:
            fixed.append(cmd)

    return fixed
