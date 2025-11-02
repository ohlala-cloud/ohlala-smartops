"""Adaptive card creation for SSM command approval workflows.

This module provides functions to create Microsoft Teams Adaptive Cards for
SSM (AWS Systems Manager) command approval workflows. It supports both
single and batch command approvals with visual indicators for platform type,
command safety, and execution mode.

Example:
    Create a single command approval card:

    ```python
    from ohlala_smartops.cards import create_ssm_approval_card

    tool_input = {
        "InstanceIds": ["i-1234567890abcdef0"],
        "Commands": ["Get-Process | Select-Object -First 10"],
        "DocumentName": "AWS-RunPowerShellScript"
    }

    card = await create_ssm_approval_card(
        tool_input=tool_input,
        tool_id="cmd_123",
        original_prompt="Show me the top processes",
        is_async=False
    )
    ```
"""

import json
import logging
from typing import Any, Final

from ohlala_smartops.constants import (
    ACTION_BATCH_SSM_APPROVE,
    ACTION_BATCH_SSM_DENY,
    ACTION_SSM_APPROVE,
    ACTION_SSM_DENY,
    CARD_COLOR_ACCENT,
    CARD_COLOR_ATTENTION,
    CARD_COLOR_WARNING,
    CARD_SIZE_LARGE,
    CARD_SIZE_SMALL,
    CARD_VERSION,
    CARD_WEIGHT_BOLDER,
    DANGEROUS_COMMAND_PATTERNS,
)

logger: Final = logging.getLogger(__name__)


def _is_windows_command(document_name: str) -> bool:
    """Check if command is for Windows based on document name.

    Args:
        document_name: AWS SSM document name (e.g., "AWS-RunPowerShellScript").

    Returns:
        True if the document is for Windows, False otherwise.

    Example:
        >>> _is_windows_command("AWS-RunPowerShellScript")
        True
        >>> _is_windows_command("AWS-RunShellScript")
        False
    """
    return "PowerShell" in document_name


def _is_dangerous_command(command_text: str) -> bool:
    """Check if command contains dangerous patterns.

    Args:
        command_text: Command text to check for dangerous patterns.

    Returns:
        True if dangerous patterns are detected, False otherwise.

    Example:
        >>> _is_dangerous_command("rm -rf /")
        True
        >>> _is_dangerous_command("Get-Process")
        False
    """
    command_lower = command_text.lower()
    return any(pattern in command_lower for pattern in DANGEROUS_COMMAND_PATTERNS)


def _parse_commands(commands: Any) -> list[str]:  # noqa: PLR0912
    """Parse commands from various formats.

    This function handles multiple input formats including JSON strings,
    arrays, and malformed inputs, normalizing them to a list of commands.

    Args:
        commands: Commands in various formats (string, list, JSON string).

    Returns:
        List of command strings.

    Example:
        >>> _parse_commands('["ls -la"]')
        ['ls -la']
        >>> _parse_commands(["ps aux"])
        ['ps aux']
        >>> _parse_commands("df -h")
        ['df -h']
    """
    if isinstance(commands, str):
        # Check if it's a JSON-encoded array string
        if commands.strip().startswith("[") and commands.strip().endswith("]"):
            try:
                commands = json.loads(commands)
            except Exception as e:
                logger.warning(f"Failed to parse JSON commands: {e}")
                # Check if it's missing the closing bracket
                if commands.startswith('["') and not commands.endswith('"]'):
                    try:
                        # Add the missing closing bracket
                        fixed_commands = commands + "]"
                        commands = json.loads(fixed_commands)
                    except:  # noqa: E722
                        # Last resort - strip the JSON wrapper manually
                        if commands.startswith('["'):
                            cleaned = commands[2:]
                            if cleaned.endswith('"'):
                                cleaned = cleaned[:-1]
                            commands = [cleaned]
                        else:
                            commands = [commands]
                else:
                    commands = [commands]
        else:
            commands = [commands]
    elif isinstance(commands, list) and len(commands) == 1:
        # Check if the single command is wrapped in JSON array syntax
        first_cmd = str(commands[0])
        if (
            (first_cmd.startswith('["') and first_cmd.endswith('"]'))
            or (first_cmd.startswith('["') and first_cmd.endswith('"'))
            or (first_cmd.startswith('["#') and '"' in first_cmd)
            or (first_cmd.startswith('["'))
        ):
            # This is a malformed command wrapped in JSON array syntax
            try:
                # Try to parse the whole thing as JSON
                if not first_cmd.endswith('"]'):
                    first_cmd = first_cmd + "]"
                fixed_cmd = json.loads(first_cmd)
                if isinstance(fixed_cmd, list) and fixed_cmd:
                    commands = fixed_cmd
            except:  # noqa: E722
                # Try a more aggressive fix - just strip the [" and "]
                if first_cmd.startswith('["'):
                    cleaned = first_cmd[2:]
                    if cleaned.endswith('"]'):
                        cleaned = cleaned[:-2]
                    elif cleaned.endswith('"'):
                        cleaned = cleaned[:-1]
                    commands = [cleaned]

    return commands if isinstance(commands, list) else [str(commands)]


async def create_ssm_approval_card(
    tool_input: dict[str, Any], tool_id: str, original_prompt: str = "", is_async: bool = False
) -> dict[str, Any]:
    """Create an approval card for SSM commands (async version for compatibility).

    Args:
        tool_input: Tool input containing InstanceIds, Commands, and DocumentName.
        tool_id: Unique identifier for this tool call.
        original_prompt: Original user prompt that triggered this command.
        is_async: Whether this is an async long-running command.

    Returns:
        Adaptive Card JSON structure.

    Example:
        >>> tool_input = {
        ...     "InstanceIds": ["i-1234567890abcdef0"],
        ...     "Commands": ["Get-Service"],
        ...     "DocumentName": "AWS-RunPowerShellScript"
        ... }
        >>> card = await create_ssm_approval_card(
        ...     tool_input, "cmd_123", "Show me services", False
        ... )
        >>> card["type"]
        'AdaptiveCard'
    """
    return create_ssm_approval_card_sync(tool_input, tool_id, original_prompt, is_async)


def create_ssm_approval_card_sync(
    tool_input: dict[str, Any], tool_id: str, original_prompt: str = "", is_async: bool = False
) -> dict[str, Any]:
    """Create an approval card for SSM commands (sync version).

    Args:
        tool_input: Tool input containing InstanceIds, Commands, and DocumentName.
        tool_id: Unique identifier for this tool call.
        original_prompt: Original user prompt that triggered this command.
        is_async: Whether this is an async long-running command.

    Returns:
        Adaptive Card JSON structure.
    """
    instance_ids = tool_input.get("InstanceIds", [])
    commands = _parse_commands(tool_input.get("Commands", []))
    document_name = tool_input.get("DocumentName", "AWS-RunShellScript")

    # Detect platform
    is_windows = _is_windows_command(document_name)
    platform_icon = "🪟" if is_windows else "🐧"
    platform_name = "Windows" if is_windows else "Linux"

    # Check for dangerous commands
    command_text = "\n".join(commands)  # Use line breaks for better formatting
    is_dangerous = _is_dangerous_command(command_text)

    card_body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": "🔐 SSM Command Approval Required",
            "size": CARD_SIZE_LARGE,
            "weight": CARD_WEIGHT_BOLDER,
            "color": CARD_COLOR_ACCENT,
        },
        {
            "type": "TextBlock",
            "text": "Ohlala SmartOps is requesting to execute a command on your EC2 instances:",
            "wrap": True,
            "spacing": "Small",
        },
    ]

    # Command details
    command_details_items: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"{platform_icon} Command Details",
            "weight": CARD_WEIGHT_BOLDER,
        },
        {"type": "TextBlock", "text": f"**Platform:** {platform_name}", "spacing": "Small"},
        {
            "type": "TextBlock",
            "text": f"**Target Instances:** {len(instance_ids)} instance(s)",
            "spacing": "Small",
        },
    ]

    # Add execution mode indicator
    if is_async:
        command_details_items.append(
            {
                "type": "TextBlock",
                "text": "**Execution Mode:** ⏳ Asynchronous (Long-running command)",
                "spacing": "Small",
                "color": CARD_COLOR_ACCENT,
            }
        )
    else:
        command_details_items.append(
            {
                "type": "TextBlock",
                "text": "**Execution Mode:** ⚡ Synchronous (Quick command)",
                "spacing": "Small",
                "color": "Good",
            }
        )

    command_details_items.extend(
        [
            {"type": "TextBlock", "text": "**Command:**", "spacing": "Small"},
            {
                "type": "TextBlock",
                "text": command_text,
                "fontType": "Monospace",
                "wrap": True,
                "spacing": "Small",
                "size": CARD_SIZE_SMALL,
            },
        ]
    )

    card_body.append(
        {
            "type": "Container",
            "separator": True,
            "spacing": "Medium",
            "style": "emphasis",
            "items": command_details_items,
        }
    )

    # Target instances
    instance_items: list[dict[str, Any]] = [
        {"type": "TextBlock", "text": "📋 Target Instances:", "weight": CARD_WEIGHT_BOLDER}
    ]

    # Show first 5 instances
    instance_items.extend(
        [
            {
                "type": "TextBlock",
                "text": f"• {instance_id}",
                "spacing": "Small",
                "size": CARD_SIZE_SMALL,
            }
            for instance_id in instance_ids[:5]
        ]
    )

    # Add "and X more" if needed
    if len(instance_ids) > 5:
        instance_items.append(
            {
                "type": "TextBlock",
                "text": f"... and {len(instance_ids) - 5} more",
                "spacing": "Small",
                "size": CARD_SIZE_SMALL,
                "isSubtle": True,
            }
        )

    card_body.append(
        {"type": "Container", "separator": True, "spacing": "Medium", "items": instance_items}
    )

    # Warnings
    if is_dangerous:
        card_body.append(
            {
                "type": "Container",
                "separator": True,
                "spacing": "Medium",
                "style": "warning",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "⚠️ DANGEROUS COMMAND DETECTED",
                        "weight": CARD_WEIGHT_BOLDER,
                        "color": CARD_COLOR_ATTENTION,
                    },
                    {
                        "type": "TextBlock",
                        "text": (
                            "This command contains potentially destructive operations. "
                            "Please review carefully before approving."
                        ),
                        "wrap": True,
                        "spacing": "Small",
                        "color": CARD_COLOR_WARNING,
                    },
                ],
            }
        )

    # Actions
    card_body.append(
        {
            "type": "ActionSet",
            "spacing": "Large",
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "✅ Approve",
                    "style": "positive",
                    "data": {
                        "action": ACTION_SSM_APPROVE,
                        "tool_id": tool_id,
                        "original_prompt": original_prompt,
                        "is_async": is_async,
                    },
                },
                {
                    "type": "Action.Submit",
                    "title": "❌ Deny",
                    "style": "destructive",
                    "data": {"action": ACTION_SSM_DENY, "tool_id": tool_id},
                },
            ],
        }
    )

    return {"type": "AdaptiveCard", "version": CARD_VERSION, "body": card_body}


async def create_batch_approval_card(
    commands_info: list[dict[str, Any]], original_prompt: str = ""
) -> dict[str, Any]:
    """Create a batch approval card for multiple SSM commands (async version).

    Args:
        commands_info: List of command info dicts with tool_input and tool_id.
        original_prompt: Original user prompt that triggered these commands.

    Returns:
        Adaptive Card JSON structure for batch approval.

    Example:
        >>> commands_info = [
        ...     {"tool_input": {"InstanceIds": ["i-123"], "Commands": ["ls"]}, "tool_id": "cmd_1"},
        ...     {"tool_input": {"InstanceIds": ["i-456"], "Commands": ["ps"]}, "tool_id": "cmd_2"}
        ... ]
        >>> card = await create_batch_approval_card(commands_info, "Show system info")
        >>> len(card["body"])
        >= 3
    """
    return create_batch_approval_card_sync(commands_info, original_prompt)


def create_batch_approval_card_sync(
    commands_info: list[dict[str, Any]], original_prompt: str = ""
) -> dict[str, Any]:
    """Create a batch approval card for multiple SSM commands (sync version).

    Args:
        commands_info: List of command info dicts with tool_input and tool_id.
        original_prompt: Original user prompt that triggered these commands.

    Returns:
        Adaptive Card JSON structure for batch approval.
    """
    total_instances = sum(len(cmd["tool_input"].get("InstanceIds", [])) for cmd in commands_info)

    card_body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": "🔐 Batch SSM Command Approval",
            "size": CARD_SIZE_LARGE,
            "weight": CARD_WEIGHT_BOLDER,
            "color": CARD_COLOR_ACCENT,
        },
        {
            "type": "TextBlock",
            "text": (
                f"Ohlala SmartOps is requesting to execute {len(commands_info)} commands "
                f"on {total_instances} EC2 instances:"
            ),
            "wrap": True,
            "spacing": "Small",
        },
    ]

    # Add each command
    for i, cmd_info in enumerate(commands_info):
        tool_input = cmd_info["tool_input"]
        instance_ids = tool_input.get("InstanceIds", [])
        commands = _parse_commands(tool_input.get("Commands", []))
        document_name = tool_input.get("DocumentName", "AWS-RunShellScript")

        # Detect platform
        is_windows = _is_windows_command(document_name)
        platform_icon = "🪟" if is_windows else "🐧"
        platform_name = "Windows" if is_windows else "Linux"

        command_text = "\n".join(commands)

        card_body.append(
            {
                "type": "Container",
                "separator": True,
                "spacing": "Medium",
                "style": "emphasis",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"{platform_icon} Command {i+1} - {platform_name}",
                        "weight": CARD_WEIGHT_BOLDER,
                    },
                    {
                        "type": "TextBlock",
                        "text": (
                            f"**Target:** {len(instance_ids)} instance(s) "
                            f"({', '.join(instance_ids[:2])}"
                            f"{', ...' if len(instance_ids) > 2 else ''})"
                        ),
                        "spacing": "Small",
                        "size": CARD_SIZE_SMALL,
                    },
                    {
                        "type": "TextBlock",
                        "text": f"**Command:** {command_text}",
                        "fontType": "Monospace",
                        "spacing": "Small",
                        "size": CARD_SIZE_SMALL,
                        "wrap": True,
                    },
                ],
            }
        )

    # Warning if dangerous
    all_commands_text = "\n".join(
        "\n".join(cmd["tool_input"].get("Commands", [])) for cmd in commands_info
    )
    is_dangerous = _is_dangerous_command(all_commands_text)

    if is_dangerous:
        card_body.append(
            {
                "type": "Container",
                "style": "attention",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": (
                            "⚠️ **WARNING:** These commands may be potentially dangerous. "
                            "Please review carefully."
                        ),
                        "wrap": True,
                        "color": CARD_COLOR_WARNING,
                        "weight": CARD_WEIGHT_BOLDER,
                    }
                ],
            }
        )

    # Collect all tool IDs
    all_tool_ids = [cmd["tool_id"] for cmd in commands_info]

    # Action buttons
    actions: list[dict[str, Any]] = [
        {
            "type": "Action.Submit",
            "title": "✅ Approve All",
            "style": "positive",
            "data": {
                "action": ACTION_BATCH_SSM_APPROVE,
                "tool_ids": all_tool_ids,
                "original_prompt": original_prompt,
            },
        },
        {
            "type": "Action.Submit",
            "title": "❌ Deny All",
            "style": "destructive",
            "data": {
                "action": ACTION_BATCH_SSM_DENY,
                "tool_ids": all_tool_ids,
                "original_prompt": original_prompt,
            },
        },
        {
            "type": "Action.Submit",
            "title": "🔍 Review Individual",
            "data": {
                "action": "review_individual",
                "tool_ids": all_tool_ids,
                "original_prompt": original_prompt,
            },
        },
    ]

    return {"type": "AdaptiveCard", "version": CARD_VERSION, "body": card_body, "actions": actions}


def create_approved_confirmation_card(
    original_tool_input: dict[str, Any], user_name: str = "User"
) -> dict[str, Any]:
    """Create a confirmation card showing the approval was processed.

    Args:
        original_tool_input: Original tool input from the approval request.
        user_name: Name of the user who approved the command.

    Returns:
        Adaptive Card JSON structure for approval confirmation.

    Example:
        >>> tool_input = {
        ...     "InstanceIds": ["i-123"],
        ...     "Commands": ["ls -la"],
        ...     "DocumentName": "AWS-RunShellScript"
        ... }
        >>> card = create_approved_confirmation_card(tool_input, "Alice")
        >>> card["body"][0]["text"]
        '✅ Command Approved & Executed'
    """
    instance_ids = original_tool_input.get("InstanceIds", [])
    commands = _parse_commands(original_tool_input.get("Commands", []))
    document_name = original_tool_input.get("DocumentName", "AWS-RunShellScript")

    # Detect platform
    is_windows = _is_windows_command(document_name)
    platform_icon = "🪟" if is_windows else "🐧"
    platform_name = "Windows" if is_windows else "Linux"
    command_text = "\n".join(commands)

    card_body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": "✅ Command Approved & Executed",
            "size": CARD_SIZE_LARGE,
            "weight": CARD_WEIGHT_BOLDER,
            "color": "Good",
        },
        {
            "type": "TextBlock",
            "text": f"Approved by: **{user_name}**",
            "wrap": True,
            "spacing": "Small",
            "isSubtle": True,
        },
        {
            "type": "Container",
            "separator": True,
            "spacing": "Medium",
            "style": "emphasis",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"{platform_icon} Executed Command",
                    "weight": CARD_WEIGHT_BOLDER,
                },
                {"type": "TextBlock", "text": f"**Platform:** {platform_name}", "spacing": "Small"},
                {
                    "type": "TextBlock",
                    "text": f"**Target Instances:** {len(instance_ids)} instance(s)",
                    "spacing": "Small",
                },
                {"type": "TextBlock", "text": "**Command:**", "spacing": "Small"},
                {
                    "type": "TextBlock",
                    "text": command_text,
                    "fontType": "Monospace",
                    "wrap": True,
                    "spacing": "Small",
                    "size": CARD_SIZE_SMALL,
                },
            ],
        },
    ]

    return {"type": "AdaptiveCard", "version": CARD_VERSION, "body": card_body}


def create_denied_confirmation_card(
    original_tool_input: dict[str, Any], user_name: str = "User"
) -> dict[str, Any]:
    """Create a confirmation card showing the denial was processed.

    Args:
        original_tool_input: Original tool input from the approval request.
        user_name: Name of the user who denied the command.

    Returns:
        Adaptive Card JSON structure for denial confirmation.

    Example:
        >>> tool_input = {
        ...     "InstanceIds": ["i-123"],
        ...     "Commands": ["rm -rf /"],
        ...     "DocumentName": "AWS-RunShellScript"
        ... }
        >>> card = create_denied_confirmation_card(tool_input, "Bob")
        >>> card["body"][0]["text"]
        '❌ Command Denied'
    """
    instance_ids = original_tool_input.get("InstanceIds", [])
    commands = _parse_commands(original_tool_input.get("Commands", []))
    document_name = original_tool_input.get("DocumentName", "AWS-RunShellScript")

    # Detect platform
    is_windows = _is_windows_command(document_name)
    platform_icon = "🪟" if is_windows else "🐧"
    platform_name = "Windows" if is_windows else "Linux"
    command_text = "\n".join(commands)

    card_body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": "❌ Command Denied",
            "size": CARD_SIZE_LARGE,
            "weight": CARD_WEIGHT_BOLDER,
            "color": CARD_COLOR_ATTENTION,
        },
        {
            "type": "TextBlock",
            "text": f"Denied by: **{user_name}**",
            "wrap": True,
            "spacing": "Small",
            "isSubtle": True,
        },
        {
            "type": "Container",
            "separator": True,
            "spacing": "Medium",
            "style": "attention",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"{platform_icon} Denied Command",
                    "weight": CARD_WEIGHT_BOLDER,
                },
                {"type": "TextBlock", "text": f"**Platform:** {platform_name}", "spacing": "Small"},
                {
                    "type": "TextBlock",
                    "text": f"**Target Instances:** {len(instance_ids)} instance(s)",
                    "spacing": "Small",
                },
                {"type": "TextBlock", "text": "**Command:**", "spacing": "Small"},
                {
                    "type": "TextBlock",
                    "text": command_text,
                    "fontType": "Monospace",
                    "wrap": True,
                    "spacing": "Small",
                    "size": CARD_SIZE_SMALL,
                },
                {
                    "type": "TextBlock",
                    "text": "This command was not executed.",
                    "spacing": "Medium",
                    "color": CARD_COLOR_ATTENTION,
                    "weight": CARD_WEIGHT_BOLDER,
                },
            ],
        },
    ]

    return {"type": "AdaptiveCard", "version": CARD_VERSION, "body": card_body}
