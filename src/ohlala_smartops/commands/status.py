"""Status command - Check pending operations and command status.

This module provides the StatusCommand class that displays pending asynchronous
commands and recent activity.

Phase 5A: Initial implementation using AsyncCommandTracker for pending commands.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.config.settings import Settings

logger: Final = logging.getLogger(__name__)


class StatusCommand(BaseCommand):
    """Handle /status command to check pending operations.

    Displays pending asynchronous commands (like SSM Run Command) and active
    workflows. Shows command IDs, elapsed time, and progress.

    Example:
        >>> cmd = StatusCommand()
        >>> result = await cmd.execute([], context)
        >>> if result["success"]:
        ...     print(result["card"])  # Status dashboard card
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "status"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Show pending commands and recent activity"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/status"

    async def execute(
        self,
        args: list[str],  # noqa: ARG002
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the status command.

        Args:
            args: Command arguments (not used).
            context: Execution context with command_tracker (optional).

        Returns:
            Command result with status dashboard.

        Example:
            >>> result = await cmd.execute([], context)
            >>> print(result["message"])  # Status summary
        """
        try:
            # Get command tracker from context
            command_tracker = context.get("command_tracker")

            if not command_tracker:
                return {
                    "success": True,
                    "message": "✅ **No Active Commands**\n\n"
                    "Command tracking is not enabled. There are no pending operations.",
                }

            # Get active commands and workflows
            active_command_count = command_tracker.get_active_command_count()
            active_workflow_count = command_tracker.get_active_workflow_count()

            if active_command_count == 0 and active_workflow_count == 0:
                return {
                    "success": True,
                    "message": "✅ **No Active Commands**\n\n"
                    "All operations are complete. There are no pending commands.",
                }

            # Build status card
            card = await self._build_status_card(
                command_tracker, active_command_count, active_workflow_count, context
            )

            return {
                "success": True,
                "message": f"Command Status: {active_command_count} active commands, "
                f"{active_workflow_count} active workflows",
                "card": card,
            }

        except Exception as e:
            logger.error(f"Error in status command: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to retrieve status information: {e!s}",
                "message": "Error retrieving command status",
            }

    async def _build_status_card(
        self,
        command_tracker: Any,
        active_command_count: int,
        active_workflow_count: int,
        context: dict[str, Any],  # noqa: ARG002
    ) -> dict[str, Any]:
        """Build the status dashboard card.

        Args:
            command_tracker: AsyncCommandTracker instance.
            active_command_count: Number of active commands.
            active_workflow_count: Number of active workflows.
            context: Execution context.

        Returns:
            Adaptive card dictionary.
        """
        settings = Settings()
        aws_region = settings.aws_region

        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "📊 Command Status Dashboard",
                "size": "Large",
                "weight": "Bolder",
            },
            {
                "type": "FactSet",
                "facts": [
                    {"title": "Active Commands", "value": str(active_command_count)},
                    {"title": "Active Workflows", "value": str(active_workflow_count)},
                ],
                "spacing": "Medium",
            },
        ]

        # Add active commands section
        if active_command_count > 0:
            card_body.append(
                {
                    "type": "TextBlock",
                    "text": "**⏳ Active Commands:**",
                    "weight": "Bolder",
                    "spacing": "Large",
                }
            )

            # Get active commands
            for command_id, tracking_info in list(command_tracker.active_commands.items())[:5]:
                elapsed_time = self._get_elapsed_time(tracking_info.submitted_at)

                card_body.extend(
                    [
                        {
                            "type": "TextBlock",
                            "text": f"**Instance:** {tracking_info.instance_id}",
                            "spacing": "Medium",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Command ID", "value": command_id},
                                {"title": "Status", "value": tracking_info.status.value},
                                {"title": "Running for", "value": elapsed_time},
                            ],
                        },
                    ]
                )

                # Add AWS Console link
                console_url = (
                    f"https://{aws_region}.console.aws.amazon.com/systems-manager/"
                    f"run-command/{command_id}"
                )
                card_body.append(
                    {
                        "type": "TextBlock",
                        "text": f"🔗 [View in AWS Console]({console_url})",
                        "size": "Small",
                    }
                )

            if active_command_count > 5:
                card_body.append(
                    {
                        "type": "TextBlock",
                        "text": f"_...and {active_command_count - 5} more commands_",
                        "isSubtle": True,
                        "size": "Small",
                    }
                )

        # Add active workflows section
        if active_workflow_count > 0:
            card_body.append(
                {
                    "type": "TextBlock",
                    "text": "**📦 Active Workflows:**",
                    "weight": "Bolder",
                    "spacing": "Large",
                }
            )

            for workflow_id, workflow_info in list(command_tracker.active_workflows.items())[:3]:
                progress_pct = (
                    int((workflow_info.completed_count / workflow_info.expected_count) * 100)
                    if workflow_info.expected_count > 0
                    else 0
                )

                card_body.extend(
                    [
                        {
                            "type": "TextBlock",
                            "text": f"**{workflow_info.operation_type}**",
                            "spacing": "Medium",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Workflow ID", "value": workflow_id},
                                {
                                    "title": "Progress",
                                    "value": f"{workflow_info.completed_count}/"
                                    f"{workflow_info.expected_count} ({progress_pct}%)",
                                },
                                {
                                    "title": "Success Rate",
                                    "value": f"{workflow_info.success_count}/"
                                    f"{workflow_info.completed_count}",
                                },
                            ],
                        },
                    ]
                )

            if active_workflow_count > 3:
                card_body.append(
                    {
                        "type": "TextBlock",
                        "text": f"_...and {active_workflow_count - 3} more workflows_",
                        "isSubtle": True,
                        "size": "Small",
                    }
                )

        # Add tips
        card_body.extend(
            [
                {
                    "type": "TextBlock",
                    "text": "---",
                    "spacing": "Large",
                },
                {
                    "type": "TextBlock",
                    "text": "💡 **Tips:**",
                    "weight": "Bolder",
                },
                {
                    "type": "TextBlock",
                    "text": "• Commands update automatically as they complete\n"
                    "• Mention a Command ID to retrieve specific results\n"
                    "• Use /status to refresh this dashboard",
                    "wrap": True,
                    "isSubtle": True,
                    "size": "Small",
                },
            ]
        )

        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": card_body,
        }

    def _get_elapsed_time(self, timestamp: datetime) -> str:
        """Get human-readable elapsed time.

        Args:
            timestamp: Start timestamp.

        Returns:
            Elapsed time string (e.g., "5 minute(s)").

        Example:
            >>> elapsed = cmd._get_elapsed_time(datetime.now(timezone.utc))
            >>> print(elapsed)  # "0 second(s)"
        """
        now = datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        elapsed = now - timestamp

        if elapsed.days > 0:
            return f"{elapsed.days} day(s)"
        if elapsed.seconds >= 3600:
            hours = elapsed.seconds // 3600
            return f"{hours} hour(s)"
        if elapsed.seconds >= 60:
            minutes = elapsed.seconds // 60
            return f"{minutes} minute(s)"
        return f"{elapsed.seconds} second(s)"
