"""Utilities for SSM command preprocessing and formatting.

This module provides comprehensive preprocessing for SSM commands, handling various
input formats including strings, lists, JSON arrays, and escaped formats. It also
applies PowerShell syntax fixes and line length validation.
"""

import ast
import json
import logging
from typing import Any, Final

logger: Final = logging.getLogger(__name__)

# SSM and PowerShell have various limits
MAX_LINE_LENGTH: Final = 500  # Conservative limit to prevent parsing errors


def preprocess_ssm_commands(
    commands: Any,
    exact_passthrough: bool = False,
) -> list[str]:
    """Preprocess SSM commands to ensure they are in the correct format.

    This function handles multiple input formats and normalizes them to a list
    of command strings. It also applies PowerShell syntax fixes automatically.

    Common formats handled:
    - List of strings: ['cmd1', 'cmd2']
    - JSON string: '["cmd1", "cmd2"]'
    - Python repr string: "['cmd1', 'cmd2']"
    - Escaped JSON: '[\\"cmd1\\", \\"cmd2\\"]'
    - Truncated JSON from CloudWatch logs

    Args:
        commands: Raw commands from AI model - could be string, list, or JSON.
        exact_passthrough: DEPRECATED - always applies fixes now for reliability.

    Returns:
        List of command strings, with PowerShell syntax fixes applied.

    Examples:
        >>> preprocess_ssm_commands(['echo hello'])
        ['echo hello']
        >>> preprocess_ssm_commands('["echo hello"]')
        ['echo hello']
        >>> preprocess_ssm_commands('[\\"echo hello\\"]')
        ['echo hello']
    """
    if not commands:
        return []

    # Log deprecation warning for exact_passthrough
    if exact_passthrough:
        logger.warning("exact_passthrough mode is deprecated - applying standard processing")

    # Reduced verbose logging for command preprocessing
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "preprocess_ssm_commands received: %s = %s...",
            type(commands).__name__,
            repr(commands)[:200],
        )

    # Case 1: Already a list
    if isinstance(commands, list):
        return _handle_list_input(commands)

    # Case 2: String that might be JSON or Python repr
    if isinstance(commands, str):
        return _handle_string_input(commands)

    # Case 3: Something else - convert to string
    logger.info(
        "Received unexpected type %s, converting to string",
        type(commands).__name__,
    )
    return _apply_powershell_fixes([str(commands)])


def _handle_list_input(commands: list[Any]) -> list[str]:
    """Handle list input, detecting nested JSON or Python repr formats.

    Args:
        commands: List of command items.

    Returns:
        Normalized list of command strings.
    """
    # Check if it's a list with a single string that looks like a Python repr()
    # of a list
    if len(commands) == 1 and isinstance(commands[0], str):
        single_item = commands[0].strip()

        # Check for Python repr() format: ['item1', 'item2']
        if single_item.startswith("['") and "', '" in single_item:
            logger.warning("Detected Python list repr() format, attempting to parse")
            try:
                parsed = ast.literal_eval(single_item)
                if isinstance(parsed, list):
                    logger.info(
                        "Parsed Python list repr() into %d commands",
                        len(parsed),
                    )
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
                        "Parsed single JSON-encoded list item into %d commands",
                        len(parsed),
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

    # Only log command count if debug enabled or if more than 5 commands
    if logger.isEnabledFor(logging.DEBUG) or len(result) > 5:
        logger.info("Processed list resulted in %d command(s)", len(result))

    return _apply_powershell_fixes(result)


def _handle_string_input(commands: str) -> list[str]:
    """Handle string input, detecting JSON arrays and escaped formats.

    Args:
        commands: String that might contain JSON or escaped content.

    Returns:
        List of command strings.
    """
    commands = commands.strip()
    logger.info("Processing string command, first 100 chars: %s", commands[:100])

    # Check if it's a JSON array
    if commands.startswith("[") and commands.endswith("]"):
        logger.info("Input looks like JSON array, attempting to parse")
        try:
            parsed = json.loads(commands)
            if isinstance(parsed, list):
                logger.info(
                    "Successfully parsed JSON array with %d items",
                    len(parsed),
                )
                result = [str(item) if not isinstance(item, str) else item for item in parsed]
                return _apply_powershell_fixes(result)
            # Parsed but not a list - shouldn't happen but handle it
            logger.warning(
                "Parsed JSON but got %s, not a list",
                type(parsed).__name__,
            )
            return _apply_powershell_fixes([str(parsed)])
        except json.JSONDecodeError as e:
            logger.warning("Direct JSON parsing failed: %s", e)
            logger.info("Trying alternative parsing strategies")

    # Handle JSON with escaped quotes including truncated versions
    if "\\" in commands and commands.startswith('["'):
        return _handle_escaped_json(commands)

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
        logger.info(
            "Fallback extraction successful: %d chars",
            len(inner_content),
        )
        return _apply_powershell_fixes([inner_content])

    # Not JSON array format - return as single command
    logger.info("String is not JSON array format, wrapping as single command")
    return _apply_powershell_fixes([commands])


def _handle_escaped_json(commands: str) -> list[str]:
    """Handle escaped JSON array format with smart extraction.

    This handles various truncation patterns from CloudWatch logs and
    different levels of escaping from Bedrock AI responses.

    Args:
        commands: String starting with '["' and containing escaped content.

    Returns:
        List with extracted and unescaped command.
    """
    logger.info("Detected escaped JSON array format, attempting smart extraction")
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

            logger.info(
                "Smart extraction successful, length: %d",
                len(inner_content),
            )
            return _apply_powershell_fixes([inner_content])
        logger.warning("Could not extract content from JSON array format")

    except Exception as decode_err:
        logger.warning("Failed smart extraction: %s", decode_err)

    # If smart extraction failed, return as-is
    return _apply_powershell_fixes([commands])


def _apply_line_length_fixes(commands: list[str]) -> list[str]:
    """Split commands that have very long lines that could cause SSM issues.

    Some PowerShell commands generate very long lines that can cause parsing
    errors in SSM. This function detects and splits such lines.

    Args:
        commands: List of command strings.

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
                "Command has lines longer than %d chars, attempting to fix",
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
                        logger.warning(
                            "Truncated line longer than %d chars",
                            MAX_LINE_LENGTH,
                        )
                else:
                    fixed_lines.append(line)
            fixed_commands.append("\n".join(fixed_lines))
        else:
            fixed_commands.append(cmd)

    return fixed_commands


def _apply_powershell_fixes(commands: list[str]) -> list[str]:
    """Apply PowerShell syntax validation and fixing to commands.

    This catches PowerShell syntax issues like double quotes at end of lines
    that are generated by Bedrock AI.

    Args:
        commands: List of command strings.

    Returns:
        List of fixed command strings.
    """
    try:
        # Import PowerShell validation functions
        from ohlala_smartops.utils.powershell_validator import (
            validate_and_fix_powershell,
        )

        # Check if any commands look like PowerShell
        powershell_commands: list[str] = []
        other_commands: list[str] = []

        for cmd in commands:
            if isinstance(cmd, str) and ("Write-Output" in cmd or "Get-" in cmd or "$" in cmd):
                powershell_commands.append(cmd)
            else:
                other_commands.append(cmd)

        # If we have PowerShell commands, apply fixes
        if powershell_commands:
            logger.info(
                "Applying PowerShell syntax fixes to %d command(s)",
                len(powershell_commands),
            )
            fixed_ps_commands, issues_found = validate_and_fix_powershell(powershell_commands)

            if issues_found:
                logger.info(
                    "Fixed PowerShell syntax issues: %s",
                    "; ".join(issues_found),
                )

            # Combine fixed PowerShell commands with other commands
            # Maintain original order by rebuilding the list
            result: list[str] = []
            ps_index = 0
            other_index = 0

            for original_cmd in commands:
                if isinstance(original_cmd, str) and (
                    "Write-Output" in original_cmd or "Get-" in original_cmd or "$" in original_cmd
                ):
                    result.append(fixed_ps_commands[ps_index])
                    ps_index += 1
                else:
                    result.append(other_commands[other_index])
                    other_index += 1

            # Apply line length fixes to the result
            return _apply_line_length_fixes(result)
        # No PowerShell commands, but still check line lengths
        return _apply_line_length_fixes(commands)

    except ImportError:
        logger.warning("PowerShell validator not available, returning commands unchanged")
        return commands
    except Exception as e:
        logger.warning(
            "Error applying PowerShell fixes: %s, returning commands unchanged",
            e,
        )
        return commands
