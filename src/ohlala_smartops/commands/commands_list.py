"""Commands list command - List and view SSM command history.

This module provides the CommandsListCommand that displays recent SSM command
executions and their status, helping with monitoring and troubleshooting.

Phase 5D: SSM Command Execution.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand

logger: Final = logging.getLogger(__name__)


class CommandsListCommand(BaseCommand):
    """Handler for /commands command - List and view SSM command history.

    Displays recent SSM command executions with status, output, and timing
    information. Can filter by instance or show specific command details.

    Features:
    - List recent commands across all instances
    - Filter by specific instance
    - View detailed command output
    - Color-coded status badges
    - Refresh functionality

    Example:
        >>> cmd = CommandsListCommand()
        >>> result = await cmd.execute([], context)  # All recent commands
        >>> result = await cmd.execute(["i-123"], context)  # Instance-specific
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "commands"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "List and view recent SSM command history"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/commands [instance-id] - List SSM commands"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute commands list command.

        Args:
            args: Command arguments (optional instance ID or command ID filter).
            context: Execution context containing:
                - mcp_manager: MCPManager instance

        Returns:
            Command result with adaptive card showing command history.

        Example:
            >>> result = await cmd.execute([], context)  # All commands
            >>> result = await cmd.execute(["i-123"], context)  # Filtered
        """
        try:
            # Parse filter argument
            instance_id = self.parse_instance_id(args) if args else None

            # Fetch command history
            try:
                commands_data = await self._get_commands(instance_id, context)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to retrieve commands: {e!s}",
                    "card": self.create_error_card(
                        "Commands Unavailable",
                        f"Unable to retrieve SSM command history. This may be because:\n\n"
                        f"• SSM is not configured in your account\n"
                        f"• You don't have permissions to list commands\n"
                        f"• No commands have been executed yet\n\n"
                        f"Error: {e!s}",
                    ),
                }

            # Build commands list card
            card = self._build_commands_list_card(commands_data, instance_id)

            filter_msg = f" for {instance_id}" if instance_id else ""
            return {
                "success": True,
                "message": f"SSM command history{filter_msg}",
                "card": card,
            }

        except Exception as e:
            self.logger.error(f"Error listing commands: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to list commands: {e!s}",
                "card": self.create_error_card(
                    "Failed to List Commands",
                    f"Unable to retrieve command history: {e!s}",
                ),
            }

    async def _get_commands(
        self, instance_id: str | None, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get SSM command history from MCP.

        Args:
            instance_id: Optional instance ID filter.
            context: Execution context.

        Returns:
            List of command dictionaries.
        """
        params: dict[str, Any] = {"MaxResults": 25}

        if instance_id:
            params["InstanceId"] = instance_id

        result = await self.call_mcp_tool("list-commands", params, context)

        commands = result.get("commands", [])
        return commands if isinstance(commands, list) else []

    def _build_commands_list_card(
        self, commands: list[dict[str, Any]], instance_id: str | None
    ) -> dict[str, Any]:
        """Build adaptive card showing command history.

        Args:
            commands: List of command dictionaries.
            instance_id: Optional instance ID filter.

        Returns:
            Adaptive card dictionary.
        """
        filter_text = f" for {instance_id}" if instance_id else ""
        title = f"⚙️ SSM Command History{filter_text}"

        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": title,
                "size": "Large",
                "weight": "Bolder",
                "color": "Accent",
            }
        ]

        if not commands:
            card_body.append(
                {
                    "type": "Container",
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "No SSM commands found.",
                            "wrap": True,
                            "isSubtle": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": "💡 Use `/exec` to execute commands on your instances.",
                            "wrap": True,
                            "size": "Small",
                            "spacing": "Small",
                        },
                    ],
                }
            )
        else:
            # Add info text
            card_body.append(
                {
                    "type": "TextBlock",
                    "text": f"Showing {len(commands)} most recent command(s)",
                    "isSubtle": True,
                    "spacing": "Small",
                }
            )

            # Add command list (show max 10 commands)
            card_body.extend(self._create_command_entry(command) for command in commands[:10])

            if len(commands) > 10:
                card_body.append(
                    {
                        "type": "TextBlock",
                        "text": f"... and {len(commands) - 10} more command(s)",
                        "isSubtle": True,
                        "spacing": "Small",
                    }
                )

        # Add refresh action
        card_body.append(
            {
                "type": "ActionSet",
                "separator": True,
                "spacing": "Large",
                "actions": [
                    {
                        "type": "Action.Submit",
                        "title": "🔄 Refresh",
                        "data": {
                            "action": "commands",
                            "instance_id": instance_id if instance_id else "",
                        },
                    }
                ],
            }
        )

        return {"type": "AdaptiveCard", "version": "1.5", "body": card_body}

    def _create_command_entry(self, command: dict[str, Any]) -> dict[str, Any]:
        """Create a card entry for a single command.

        Args:
            command: Command dictionary from SSM.

        Returns:
            Container with command information.
        """
        command_id = command.get("CommandId", "Unknown")
        status = command.get("Status", "Unknown")
        document_name = command.get("DocumentName", "Unknown")
        instance_ids = command.get("InstanceIds", [])
        requested_at = command.get("RequestedDateTime", "Unknown")
        parameters = command.get("Parameters", {})

        # Get command text from parameters
        command_text = "Unknown"
        if isinstance(parameters, dict):
            commands_list = parameters.get("commands", [])
            if isinstance(commands_list, list) and commands_list:
                command_text = commands_list[0] if isinstance(commands_list[0], str) else "Unknown"

        # Truncate long commands
        if len(command_text) > 80:
            command_text = f"{command_text[:80]}..."

        # Determine status icon and color
        status_info = self._get_status_info(status)

        # Build command entry
        items: list[dict[str, Any]] = [
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": status_info["icon"],
                                "size": "Medium",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": document_name,
                                "weight": "Bolder",
                                "size": "Small",
                            },
                            {
                                "type": "TextBlock",
                                "text": command_text,
                                "wrap": True,
                                "fontType": "Monospace",
                                "size": "Small",
                                "spacing": "None",
                                "isSubtle": True,
                            },
                        ],
                    },
                ],
            },
            {
                "type": "FactSet",
                "spacing": "Small",
                "facts": [
                    {"title": "Status:", "value": f"{status_info['icon']} {status}"},
                    {"title": "Command ID:", "value": command_id},
                    {
                        "title": "Targets:",
                        "value": (
                            f"{len(instance_ids)} instance(s)"
                            if isinstance(instance_ids, list)
                            else "Unknown"
                        ),
                    },
                    {"title": "Requested:", "value": str(requested_at)},
                ],
            },
        ]

        # Add instance IDs if not too many
        if isinstance(instance_ids, list) and len(instance_ids) <= 3:
            items.append(
                {
                    "type": "TextBlock",
                    "text": f"Instance IDs: {', '.join(instance_ids)}",
                    "size": "Small",
                    "isSubtle": True,
                    "spacing": "Small",
                }
            )

        return {
            "type": "Container",
            "separator": True,
            "spacing": "Medium",
            "items": items,
        }

    def _get_status_info(self, status: str) -> dict[str, str]:
        """Get status icon and color for command status.

        Args:
            status: Command status string.

        Returns:
            Dictionary with icon and color keys.
        """
        status_map = {
            "Success": {"icon": "✅", "color": "Good"},
            "Failed": {"icon": "❌", "color": "Attention"},
            "Pending": {"icon": "⏳", "color": "Warning"},
            "InProgress": {"icon": "▶️", "color": "Accent"},
            "Cancelled": {"icon": "🚫", "color": "Warning"},
            "TimedOut": {"icon": "⏰", "color": "Warning"},
            "Cancelling": {"icon": "🚫", "color": "Warning"},
        }

        return status_map.get(status, {"icon": "⚪", "color": "Default"})
