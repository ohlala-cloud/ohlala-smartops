"""AWS Systems Manager (SSM) command preprocessing utilities.

This module provides utilities for preprocessing SSM commands before execution.
It handles various input formats including JSON arrays, escaped strings, and
Python repr() formats. It also applies PowerShell syntax fixes automatically.
"""

import ast
import json
import logging
from collections.abc import Sequence
from typing import Any, Final

from ohlala_smartops.utils.powershell import validate_and_fix_powershell

logger: Final = logging.getLogger(__name__)

# Maximum line length before attempting to split commands
MAX_LINE_LENGTH: Final[int] = 500


def preprocess_ssm_commands(commands: Any, exact_passthrough: bool = False) -> list[str]:
    """Preprocess SSM commands to ensure they are in the correct format.

    This function handles various command formats that may come from AI models,
    CloudWatch logs, or other sources:
    - Lists of strings
    - JSON-encoded arrays
    - Python repr() format strings
    - Escaped/truncated JSON from logs
    - Single string commands

    The function also applies PowerShell syntax fixes automatically.

    Args:
        commands: Raw commands - could be string, list, or JSON encoded.
        exact_passthrough: DEPRECATED - always applies fixes now for natural retry flow.

    Returns:
        List of command strings ready for SSM execution.

    Example:
        >>> commands = '["ls -la"]'
        >>> result = preprocess_ssm_commands(commands)
        >>> print(result)
        ['ls -la']
    """
    if not commands:
        return []

    # Reduced verbose logging for command preprocessing
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "preprocess_ssm_commands received: %s = %s...",
            type(commands).__name__,
            repr(commands)[:200],
        )

    if exact_passthrough:
        logger.warning("exact_passthrough mode is deprecated - applying standard processing")

    # Case 1: Already a list
    if isinstance(commands, list):
        return _process_list_commands(commands)

    # Case 2: String that might be JSON
    if isinstance(commands, str):
        return _process_string_command(commands)

    # Case 3: Something else - convert to string
    logger.info("Received unexpected type %s, converting to string", type(commands))
    return _apply_powershell_fixes([str(commands)])


def _process_list_commands(commands: list[Any]) -> list[str]:
    """Process commands that are already in list format.

    Handles special cases like:
    - List with single string that looks like a Python repr() of a list
    - List with single JSON-encoded array string
    - List with mixed types

    Args:
        commands: List of command items (may be strings or other types).

    Returns:
        List of command strings.
    """
    # CRITICAL FIX: Check if it's a list with a single string that looks like
    # a Python repr() of a list
    if len(commands) == 1 and isinstance(commands[0], str):
        single_item = commands[0].strip()

        # Check for Python repr() format: ['item1', 'item2']
        if single_item.startswith("['") and "', '" in single_item:
            logger.warning("Detected Python list repr() format, attempting to parse...")
            try:
                # This is a string representation of a Python list, use ast.literal_eval
                parsed = ast.literal_eval(single_item)
                if isinstance(parsed, list):
                    logger.info("Parsed Python list repr() into %d commands", len(parsed))
                    result_commands = [str(item) for item in parsed]
                    return _apply_powershell_fixes(result_commands)
            except (ValueError, SyntaxError) as e:
                logger.warning("Failed to parse as Python list: %s", e)
                # Fall through to JSON parsing

        # Check if this single item is a JSON-encoded array
        if single_item.startswith("[") and single_item.endswith("]"):
            try:
                parsed = json.loads(single_item)
                if isinstance(parsed, list):
                    logger.info(
                        "Parsed single JSON-encoded list item into %d commands", len(parsed)
                    )
                    result_commands = [str(item) for item in parsed]
                    return _apply_powershell_fixes(result_commands)
            except json.JSONDecodeError:
                # Not valid JSON, treat as regular command
                pass

    # Process each element in the list (general case)
    result: list[str] = []
    for cmd in commands:
        if isinstance(cmd, str):
            result.append(cmd)
        else:
            # Non-string command, convert to string
            result.append(str(cmd))

    # Only log command count if debug enabled or if more than 5 commands (unusual)
    if logger.isEnabledFor(logging.DEBUG) or len(result) > 5:
        logger.info("Processed list resulted in %d command(s)", len(result))

    return _apply_powershell_fixes(result)


def _process_string_command(commands: str) -> list[str]:
    """Process commands provided as a string.

    Handles:
    - JSON arrays
    - Escaped JSON with truncation
    - Plain single commands

    Args:
        commands: String containing command(s).

    Returns:
        List of command strings.
    """
    commands = commands.strip()
    logger.info("Processing string command, first 100 chars: %s", commands[:100])

    # Check if it's a JSON array
    if commands.startswith("[") and commands.endswith("]"):
        logger.info("Input looks like JSON array, attempting to parse...")
        try:
            # Try to parse as JSON array
            parsed = json.loads(commands)
            if isinstance(parsed, list):
                # Successfully parsed - return the contents
                logger.info("Successfully parsed JSON array with %d items", len(parsed))
                result = [str(item) if not isinstance(item, str) else item for item in parsed]
                return _apply_powershell_fixes(result)
            # Parsed but not a list - shouldn't happen but handle it
            logger.warning("Parsed JSON but got %s, not a list", type(parsed))
            return _apply_powershell_fixes([str(parsed)])
        except json.JSONDecodeError as e:
            logger.warning("Direct JSON parsing failed: %s", e)
            logger.info("Trying alternative parsing strategies...")

    # Handle JSON with escaped quotes including truncated versions
    if "\\" in commands and commands.startswith('["'):
        extracted = _extract_escaped_json(commands)
        if extracted is not None:
            return extracted

    # Fallback: Last resort manual extraction for complete arrays
    if commands.startswith('["') and commands.endswith('"]'):
        logger.info("Attempting fallback manual extraction")
        inner_content = commands[2:-2]
        # Basic unescaping
        inner_content = inner_content.replace('\\\\"', '"')  # Triple escaped
        inner_content = inner_content.replace('\\"', '"')  # Double escaped
        inner_content = inner_content.replace("\\\\", "\\")  # Backslashes
        inner_content = inner_content.replace("\\n", "\n")  # Newlines
        inner_content = inner_content.replace("\\r", "\r")  # Carriage returns
        inner_content = inner_content.replace("\\t", "\t")  # Tabs
        logger.info("Fallback extraction successful: %d chars", len(inner_content))
        return _apply_powershell_fixes([inner_content])

    # Not JSON array format - return as single command
    logger.info("String is not JSON array format, wrapping as single command")
    return _apply_powershell_fixes([commands])


def _extract_escaped_json(commands: str) -> list[str] | None:
    """Extract content from escaped JSON array format.

    Handles various truncation patterns from CloudWatch logs and other sources.

    Args:
        commands: String in escaped JSON format.

    Returns:
        List of extracted commands, or None if extraction failed.
    """
    logger.info("Detected escaped JSON array format, attempting smart extraction...")

    try:
        inner_content: str | None = None

        # Handle complete JSON array: ["..."]
        if commands.endswith('"]'):
            inner_content = commands[2:-2]  # Remove [" and "]
            logger.info("Found complete JSON array")
        # Handle truncated variants
        elif len(commands) > 2:
            # Remove the opening ["
            temp_content = commands[2:]

            # Different truncation patterns from CloudWatch logs
            if temp_content.endswith('"}'):
                # Pattern: ["command content"}
                last_quote = temp_content.rfind('"')
                if last_quote > 0:
                    inner_content = temp_content[:last_quote]
                    logger.info("Found truncated JSON array ending with '\"}'")
            elif temp_content.endswith("}"):
                # Pattern: ["command content}
                inner_content = temp_content[:-1]  # Remove trailing }
                logger.info("Found truncated JSON array ending with '}'")
            elif temp_content.endswith('"]'):
                # Shouldn't happen but handle it
                inner_content = temp_content[:-2]
                logger.info("Found complete JSON array (alternate check)")
            else:
                # Just remove the opening [" and hope for the best
                inner_content = temp_content
                logger.info("Found incomplete JSON array, using available content")

        if inner_content is not None:
            # Handle different levels of escaping
            # Triple escaped quotes (rare but happens)
            if '\\\\"' in inner_content:
                inner_content = inner_content.replace('\\\\"', '"')
            # Double escaped quotes (most common from Bedrock)
            if '\\"' in inner_content:
                inner_content = inner_content.replace('\\"', '"')

            # Handle escaped special characters
            inner_content = inner_content.replace("\\n", "\n")
            inner_content = inner_content.replace("\\t", "\t")
            inner_content = inner_content.replace("\\r", "\r")
            # Handle double backslashes for Windows paths
            inner_content = inner_content.replace("\\\\", "\\")

            logger.info("Smart extraction successful, length: %d", len(inner_content))
            return _apply_powershell_fixes([inner_content])
        logger.warning("Could not extract content from JSON array format")
        return None

    except Exception as decode_err:
        logger.warning("Failed smart extraction: %s", decode_err)
        return None


def _apply_line_length_fixes(commands: Sequence[str]) -> list[str]:
    """Split commands that have very long lines that could cause SSM issues.

    Some PowerShell commands generate very long lines that can cause parsing
    errors in SSM. This function detects and splits such lines.

    Args:
        commands: Sequence of command strings.

    Returns:
        List of commands with long lines split or truncated.
    """
    fixed_commands: list[str] = []

    for cmd in commands:
        if not isinstance(cmd, str):
            fixed_commands.append(cmd)
            continue

        lines = cmd.split("\n")
        needs_fixing = any(len(line) > MAX_LINE_LENGTH for line in lines)

        if needs_fixing:
            logger.warning(
                "Command has lines longer than %d chars, attempting to fix...",
                MAX_LINE_LENGTH,
            )
            # For now, just truncate very long lines with a warning
            fixed_lines: list[str] = []
            for line in lines:
                if len(line) > MAX_LINE_LENGTH:
                    # Find a good breaking point (like after a string or semicolon)
                    if '" ' in line and line.index('" ') < MAX_LINE_LENGTH:
                        break_point = line.index('" ') + 2
                        fixed_lines.append(line[:break_point])
                        fixed_lines.append("# Line continuation: " + line[break_point:])
                    else:
                        # Just truncate with a warning
                        fixed_lines.append(line[:MAX_LINE_LENGTH] + " # WARNING: Line truncated")
                        logger.warning("Truncated line longer than %d chars", MAX_LINE_LENGTH)
                else:
                    fixed_lines.append(line)
            fixed_commands.append("\n".join(fixed_lines))
        else:
            fixed_commands.append(cmd)

    return fixed_commands


def _apply_powershell_fixes(commands: Sequence[str]) -> list[str]:
    """Apply PowerShell syntax validation and fixing to commands.

    This catches PowerShell syntax issues like double quotes at end of lines
    that are generated by Bedrock AI.

    Args:
        commands: Sequence of command strings.

    Returns:
        List of fixed command strings.
    """
    # Check if any commands look like PowerShell
    powershell_commands: list[str] = []
    other_commands: list[str] = []

    for cmd in commands:
        if isinstance(cmd, str) and _is_powershell_command(cmd):
            powershell_commands.append(cmd)
        else:
            other_commands.append(cmd)

    # If we have PowerShell commands, apply fixes
    if powershell_commands:
        logger.info("Applying PowerShell syntax fixes to %d command(s)", len(powershell_commands))
        try:
            fixed_ps_commands, issues_found = validate_and_fix_powershell(powershell_commands)

            if issues_found:
                logger.info("Fixed PowerShell syntax issues: %s", "; ".join(issues_found))

            # Combine fixed PowerShell commands with other commands
            # Maintain original order by rebuilding the list
            result: list[str] = []
            ps_index = 0
            other_index = 0

            for original_cmd in commands:
                if isinstance(original_cmd, str) and _is_powershell_command(original_cmd):
                    result.append(fixed_ps_commands[ps_index])
                    ps_index += 1
                else:
                    result.append(other_commands[other_index])
                    other_index += 1

            # Apply line length fixes to the result
            return _apply_line_length_fixes(result)
        except Exception as e:
            logger.warning("Error applying PowerShell fixes: %s, returning commands unchanged", e)
            return list(commands)
    else:
        # No PowerShell commands, but still check line lengths
        return _apply_line_length_fixes(list(commands))


def _is_powershell_command(cmd: str) -> bool:
    """Check if a command string looks like PowerShell.

    Args:
        cmd: Command string to check.

    Returns:
        True if the command appears to be PowerShell, False otherwise.
    """
    return "Write-Output" in cmd or "Get-" in cmd or "$" in cmd
