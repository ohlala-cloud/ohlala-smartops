"""History command - View detailed command execution history.

This command allows users to view their recent command execution history
with detailed information about command status, results, and execution times.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from ohlala_smartops.commands.base import BaseCommand

logger = logging.getLogger(__name__)


class HistoryCommand(BaseCommand):
    """Handle /history command to view command execution history.

    This command retrieves and displays the user's recent command history
    with execution details, results, and AWS Console links.

    Example:
        >>> /history          # Show last 5 commands
        >>> /history 10       # Show last 10 commands
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "history"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Show detailed command execution history"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/history [limit]"

    async def execute(self, args: list[str], context: dict[str, Any]) -> dict[str, Any]:
        """Execute the history command.

        Args:
            args: Command arguments (limit as first arg).
            context: Execution context containing state_manager and user info.

        Returns:
            Command result dictionary with message containing history.
        """
        try:
            user_id = context.get("user_id", "unknown")
            limit = self._parse_limit(args)

            # Get command history from state manager
            state_manager = context.get("state_manager")
            if not state_manager:
                return {"success": False, "error": "State manager not available"}

            recent_commands = await state_manager.get_user_command_history(user_id, limit=limit)

            if not recent_commands:
                return self._build_empty_history_response()

            message = self._build_history_message(recent_commands, limit)
            return {"success": True, "message": message}

        except Exception as e:
            logger.error(f"Error in history command: {e}")
            return {"success": False, "error": f"Failed to retrieve command history: {e!s}"}

    def _get_status_icon(self, status: str) -> str:
        """Get appropriate icon for command status.

        Args:
            status: Command status string.

        Returns:
            Emoji icon representing the status.
        """
        status_icons = {
            "pending": "⏳",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫",
        }
        return status_icons.get(status.lower(), "❓")

    def _get_elapsed_time(self, timestamp: datetime) -> str:
        """Get human-readable elapsed time.

        Args:
            timestamp: Timestamp to calculate elapsed time from.

        Returns:
            Human-readable elapsed time string.
        """
        now = datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        elapsed = now - timestamp

        if elapsed.days > 0:
            return f"{elapsed.days} day(s)"
        if elapsed.seconds > 3600:
            hours = elapsed.seconds // 3600
            return f"{hours} hour(s)"
        if elapsed.seconds > 60:
            minutes = elapsed.seconds // 60
            return f"{minutes} minute(s)"
        return f"{elapsed.seconds} second(s)"

    def _parse_limit(self, args: list[str]) -> int:
        """Parse limit from command arguments.

        Args:
            args: Command arguments.

        Returns:
            Limit value (default 5, capped at 20).
        """
        limit = 5  # default
        if len(args) > 0:
            try:
                limit = min(int(args[0]), 20)  # Cap at 20 for performance
            except ValueError:
                limit = 5
        return limit

    def _build_empty_history_response(self) -> dict[str, Any]:
        """Build response for empty history.

        Returns:
            Response dictionary for empty history.
        """
        return {
            "success": True,
            "message": (
                "📝 **No Command History Found**\n\n"
                "You haven't executed any commands yet. "
                "Try running a command like `/help` or `/list`!"
            ),
        }

    def _build_history_message(self, recent_commands: list[Any], limit: int) -> str:
        """Build the history message from command entries.

        Args:
            recent_commands: List of command history entries.
            limit: Current limit value.

        Returns:
            Formatted history message string.
        """
        message = f"## 📚 Command History (Last {len(recent_commands)} commands)\n\n"

        for i, cmd in enumerate(recent_commands, 1):
            message += self._format_command_entry(i, cmd)

        # Add helpful footer
        message += "💡 **Tips:**\n"
        message += "• Use `/status` to check currently running commands\n"
        message += "• Use `/help` to see all available commands\n"
        message += f"• Use `/history {limit+5}` to see more commands\n"

        return message

    def _format_command_entry(self, index: int, cmd: Any) -> str:
        """Format a single command history entry.

        Args:
            index: Entry index number.
            cmd: Command history entry.

        Returns:
            Formatted entry string.
        """
        status_icon = self._get_status_icon(cmd.status.value)
        elapsed_time = self._get_elapsed_time(cmd.timestamp)

        entry = f"### {index}. {status_icon} {cmd.description}\n\n"
        entry += self._format_command_details(cmd, elapsed_time)
        entry += self._format_results_summary(cmd)
        entry += self._format_console_link(cmd)
        entry += self._format_completion_time(cmd)
        entry += "\n---\n\n"

        return entry

    def _format_command_details(self, cmd: Any, elapsed_time: str) -> str:
        """Format command details section.

        Args:
            cmd: Command history entry.
            elapsed_time: Human-readable elapsed time.

        Returns:
            Formatted details string.
        """
        details = "**Command Details:**\n"
        details += f"• **Command ID**: `{cmd.command_id}`\n"
        details += f"• **Status**: {cmd.status.value.title()}\n"
        details += f"• **Executed**: {elapsed_time} ago\n"

        if cmd.user_context:
            details += f"• **User Context**: {cmd.user_context}\n"
        if cmd.approved_by:
            details += f"• **Approved by**: {cmd.approved_by}\n"
        if cmd.instance_ids:
            instances_str = ", ".join(cmd.instance_ids)
            details += f"• **Instances**: {instances_str}\n"

        return details

    def _format_results_summary(self, cmd: Any) -> str:
        """Format results summary section.

        Args:
            cmd: Command history entry.

        Returns:
            Formatted results string.
        """
        if not cmd.results:
            return ""

        success_count = sum(1 for r in cmd.results.values() if r.get("status") == "Success")
        failed_count = len(cmd.results) - success_count

        summary = "\n**Results Summary:**\n"
        summary += f"• ✅ Successful: {success_count}\n"
        if failed_count > 0:
            summary += f"• ❌ Failed: {failed_count}\n"

        # Show brief output for successful commands
        if success_count > 0:
            summary += "\n**Output Preview:**\n"
            for instance_id, result in cmd.results.items():
                if result.get("status") == "Success" and result.get("output"):
                    output = result["output"]
                    preview = output[:100] + "..." if len(output) > 100 else output
                    summary += f"• **{instance_id}**: {preview}\n"

        return summary

    def _format_console_link(self, cmd: Any) -> str:
        """Format AWS Console link if applicable.

        Args:
            cmd: Command history entry.

        Returns:
            Formatted console link or empty string.
        """
        if cmd.command_id.startswith(("cmd-", "ssm-")):
            aws_region = cmd.aws_region
            console_url = (
                f"https://{aws_region}.console.aws.amazon.com/"
                f"systems-manager/run-command/{cmd.command_id}"
            )
            return f"\n🔗 **[View in AWS Console]({console_url})**\n"
        return ""

    def _format_completion_time(self, cmd: Any) -> str:
        """Format completion time if available.

        Args:
            cmd: Command history entry.

        Returns:
            Formatted completion time or empty string.
        """
        if cmd.completion_time:
            completion_elapsed = self._get_elapsed_time(cmd.completion_time)
            return f"⏱️ **Completed**: {completion_elapsed} ago\n"
        return ""
