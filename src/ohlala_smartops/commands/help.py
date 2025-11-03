"""Help command handler.

This module provides the HelpCommand class that displays available commands
and usage information to users.

Phase 5A: Simplified version without localization support.
Localization will be added in Phase 6.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand

logger: Final = logging.getLogger(__name__)


class HelpCommand(BaseCommand):
    """Handler for /help command.

    Displays available commands and usage information. Can show general help
    or detailed help for a specific command.

    Example:
        >>> cmd = HelpCommand()
        >>> result = await cmd.execute([], context)  # General help
        >>> result = await cmd.execute(["status"], context)  # Specific command help
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "help"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Show available commands and usage information"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/help [command]"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],  # noqa: ARG002
    ) -> dict[str, Any]:
        """Execute help command.

        Args:
            args: Optional command name to get specific help for.
            context: Execution context (not used for help).

        Returns:
            Command result with help information as adaptive card.

        Example:
            >>> result = await cmd.execute([], context)
            >>> print(result["success"])  # True
            >>> print("card" in result)  # True
        """
        try:
            # Extract command from args if provided
            command = args[0] if args else None

            if command:
                # Show help for specific command
                return await self._show_command_help(command)
            # Show general help
            return await self._show_general_help()

        except Exception as e:
            logger.error(f"Error showing help: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Error showing help: {e!s}",
                "message": "Failed to display help information",
            }

    async def _show_general_help(self) -> dict[str, Any]:
        """Show general help with all available commands.

        Returns:
            Command result with general help card.
        """
        card = {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "TextBlock",
                    "text": "🤖 Ohlala SmartOps Help",
                    "size": "Large",
                    "weight": "Bolder",
                },
                {
                    "type": "TextBlock",
                    "text": "I can help you manage AWS EC2 instances through natural "
                    "language or slash commands.",
                    "wrap": True,
                    "spacing": "Medium",
                },
                {
                    "type": "TextBlock",
                    "text": "📋 Available Commands",
                    "weight": "Bolder",
                    "size": "Medium",
                    "spacing": "Large",
                },
                {
                    "type": "Container",
                    "separator": True,
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "**Core Commands**",
                            "color": "Accent",
                            "weight": "Bolder",
                            "spacing": "Small",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {
                                    "title": "/help",
                                    "value": "Show this help information",
                                },
                                {
                                    "title": "/status",
                                    "value": "Show pending commands and recent activity",
                                },
                            ],
                        },
                    ],
                },
                {
                    "type": "Container",
                    "separator": True,
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "**Instance Management**",
                            "color": "Accent",
                            "weight": "Bolder",
                            "spacing": "Small",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {
                                    "title": "/list",
                                    "value": "List all EC2 instances",
                                },
                                {
                                    "title": "/start",
                                    "value": "Start stopped instances (requires confirmation)",
                                },
                                {
                                    "title": "/stop",
                                    "value": "Stop running instances (requires confirmation)",
                                },
                                {
                                    "title": "/reboot",
                                    "value": "Reboot running instances (requires confirmation)",
                                },
                            ],
                        },
                    ],
                },
                {
                    "type": "Container",
                    "separator": True,
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "**Monitoring & Information**",
                            "color": "Accent",
                            "weight": "Bolder",
                            "spacing": "Small",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {
                                    "title": "/details",
                                    "value": "Show detailed instance information",
                                },
                                {
                                    "title": "/metrics",
                                    "value": "Display CloudWatch metrics",
                                },
                                {
                                    "title": "/costs",
                                    "value": "Show cost information from Cost Explorer",
                                },
                            ],
                        },
                    ],
                },
                {
                    "type": "Container",
                    "separator": True,
                    "spacing": "Large",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "💬 Natural Language",
                            "weight": "Bolder",
                            "color": "Accent",
                        },
                        {
                            "type": "TextBlock",
                            "text": "You can use natural language for operations. "
                            "Just ask in plain English!",
                            "wrap": True,
                            "spacing": "Small",
                        },
                        {
                            "type": "TextBlock",
                            "text": '• "List my EC2 instances"\n'
                            '• "Show instance status"\n'
                            '• "Check instance health"\n'
                            '• "What instances are running?"',
                            "wrap": True,
                            "fontType": "Monospace",
                            "size": "Small",
                            "isSubtle": True,
                        },
                    ],
                },
                {
                    "type": "Container",
                    "separator": True,
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "💡 Tips",
                            "weight": "Bolder",
                        },
                        {
                            "type": "TextBlock",
                            "text": "• Type /help [command] for detailed help on a "
                            "specific command\n"
                            "• Use natural language for most operations\n"
                            "• All write operations require confirmation for safety",
                            "wrap": True,
                            "isSubtle": True,
                        },
                    ],
                },
            ],
        }

        return {
            "success": True,
            "message": "Help information",
            "card": card,
        }

    async def _show_command_help(self, command: str) -> dict[str, Any]:
        """Show help for a specific command.

        Args:
            command: Command name to show help for.

        Returns:
            Command result with specific command help.
        """
        # Command-specific help information
        command_help: dict[str, dict[str, Any]] = {
            "help": {
                "title": "Help Command",
                "description": "Display available commands and usage information",
                "usage": [
                    "/help - Show all available commands",
                    "/help [command] - Show detailed help for a specific command",
                ],
                "details": "The help command provides information about all available "
                "commands and how to use them. You can get general help or "
                "detailed help for any specific command.",
                "examples": ["/help", "/help status"],
            },
            "status": {
                "title": "Status Command",
                "description": "Check pending commands and recent activity",
                "usage": ["/status - Show command status dashboard"],
                "details": "Displays pending asynchronous commands and recent command "
                "history. Useful for checking the status of long-running "
                "operations like SSM commands.",
                "examples": ["/status"],
            },
            "list": {
                "title": "List Instances Command",
                "description": "List all EC2 instances with status and details",
                "usage": ["/list - Show all EC2 instances"],
                "details": "Displays a comprehensive list of all EC2 instances in your account, "
                "including instance ID, name, type, state, and IP addresses. Instances are "
                "sorted by state (running first) and then by name.",
                "examples": ["/list"],
            },
            "start": {
                "title": "Start Instances Command",
                "description": "Start stopped EC2 instances",
                "usage": ["/start <instance-id> [instance-id ...] - Start EC2 instances"],
                "details": "Starts one or more stopped EC2 instances. Requires user confirmation "
                "before execution. Only works on instances in 'stopped' state. Supports "
                "multiple instance IDs (space or comma-separated).",
                "examples": ["/start i-1234567890abcdef0", "/start i-abc123 i-def456"],
            },
            "stop": {
                "title": "Stop Instances Command",
                "description": "Stop running EC2 instances",
                "usage": ["/stop <instance-id> [instance-id ...] - Stop EC2 instances"],
                "details": "Stops one or more running EC2 instances. Requires user confirmation "
                "with warning about service interruption. Only works on instances in 'running' "
                "state. Supports multiple instance IDs (space or comma-separated).",
                "examples": ["/stop i-1234567890abcdef0", "/stop i-abc123 i-def456"],
            },
            "reboot": {
                "title": "Reboot Instances Command",
                "description": "Reboot running EC2 instances",
                "usage": ["/reboot <instance-id> [instance-id ...] - Reboot EC2 instances"],
                "details": "Reboots one or more running EC2 instances. Requires user confirmation "
                "with warning about temporary connection interruption. Only works on instances in "
                "'running' state. Supports multiple instance IDs (space or comma-separated).",
                "examples": ["/reboot i-1234567890abcdef0", "/reboot i-abc123 i-def456"],
            },
            "details": {
                "title": "Instance Details Command",
                "description": "Show detailed information about a specific EC2 instance",
                "usage": ["/details <instance-id> - Show detailed instance information"],
                "details": "Displays comprehensive information about a specific EC2 instance, "
                "including instance details, recent CloudWatch metrics (last hour), active SSM "
                "sessions, and recent SSM commands. Provides quick action buttons based on "
                "current instance state.",
                "examples": ["/details i-1234567890abcdef0"],
            },
            "metrics": {
                "title": "Metrics Command",
                "description": "Display CloudWatch metrics for an EC2 instance",
                "usage": [
                    "/metrics <instance-id> [duration] - Show metrics",
                    "Duration options: 1h (default), 6h, 24h, 7d",
                ],
                "details": "Shows CloudWatch metrics for an instance over a specified time period. "
                "Displays CPU utilization, network in/out, and disk read/write metrics with "
                "min/max/average statistics. Metrics are shown for the last hour by default.",
                "examples": [
                    "/metrics i-1234567890abcdef0",
                    "/metrics i-1234567890abcdef0 6h",
                    "/metrics i-1234567890abcdef0 24h",
                ],
            },
            "costs": {
                "title": "Costs Command",
                "description": "Display cost information from AWS Cost Explorer",
                "usage": [
                    "/costs [instance-id|all] [period] - Show costs",
                    "Periods: today, week, month (default: month)",
                ],
                "details": "Shows cost data from AWS Cost Explorer for EC2 instances. Can show "
                "costs for a specific instance or all instances. Includes cost breakdown by day "
                "and forecast (if enabled). Note: Cost Explorer data has a 24-48 hour delay.",
                "examples": [
                    "/costs",
                    "/costs all month",
                    "/costs i-1234567890abcdef0 week",
                    "/costs all today",
                ],
            },
        }

        help_info = command_help.get(command.lower())
        if not help_info:
            return {
                "success": False,
                "message": f"No help available for command: {command}",
                "error": f"Command '{command}' not found. Use /help to see all commands.",
            }

        # Build help card for specific command
        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"📖 {help_info['title']}",
                "size": "Large",
                "weight": "Bolder",
            },
            {
                "type": "TextBlock",
                "text": help_info["description"],
                "wrap": True,
                "spacing": "Small",
            },
            {
                "type": "TextBlock",
                "text": "**Usage:**",
                "weight": "Bolder",
                "spacing": "Medium",
            },
        ]

        # Add usage examples
        card_body.extend(
            [
                {
                    "type": "TextBlock",
                    "text": f"• {usage}",
                    "fontType": "Monospace",
                    "wrap": True,
                    "isSubtle": True,
                }
                for usage in help_info["usage"]
            ]
        )

        if help_info.get("details"):
            card_body.extend(
                [
                    {
                        "type": "TextBlock",
                        "text": "**Details:**",
                        "weight": "Bolder",
                        "spacing": "Medium",
                    },
                    {
                        "type": "TextBlock",
                        "text": help_info["details"],
                        "wrap": True,
                        "isSubtle": True,
                    },
                ]
            )

        if help_info.get("examples"):
            card_body.extend(
                [
                    {
                        "type": "TextBlock",
                        "text": "**Examples:**",
                        "weight": "Bolder",
                        "spacing": "Medium",
                    },
                ]
            )
            card_body.extend(
                [
                    {
                        "type": "TextBlock",
                        "text": f"• {example}",
                        "fontType": "Monospace",
                        "wrap": True,
                        "isSubtle": True,
                        "color": "Accent",
                    }
                    for example in help_info["examples"]
                ]
            )

        card = {"type": "AdaptiveCard", "version": "1.5", "body": card_body}

        return {
            "success": True,
            "message": f"Help for /{command}",
            "card": card,
        }
