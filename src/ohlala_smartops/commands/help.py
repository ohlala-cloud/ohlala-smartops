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
