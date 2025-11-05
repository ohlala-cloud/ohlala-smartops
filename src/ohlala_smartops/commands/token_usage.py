"""Token Usage command for viewing token consumption and costs.

This command displays token usage statistics and costs for Claude API calls,
helping users monitor their AWS Bedrock consumption and manage budgets.
"""

import time
from typing import Any

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.utils.token_tracker import get_token_tracker


class TokenUsageCommand(BaseCommand):
    """Display token usage statistics and costs.

    Shows current session and daily usage with cost breakdowns.
    Provides budget monitoring and intelligent recommendations.

    Usage:
        /token-usage                Show brief usage summary
        /token-usage --detailed     Show detailed breakdown with recommendations
        /token-usage --reset-daily  Reset daily statistics (admin function)

    Example:
        >>> # Show brief summary
        >>> /token-usage
        📊 **Token Usage Summary**
        ...

        >>> # Show detailed report
        >>> /token-usage --detailed
        📊 **Detailed Token Usage Report**
        ...
    """

    @property
    def name(self) -> str:
        """Command name for registration."""
        return "token-usage"

    @property
    def description(self) -> str:
        """Brief description of the command."""
        return "Show token usage statistics and costs"

    @property
    def usage(self) -> str:
        """Usage syntax for help text."""
        return "/token-usage [--detailed] [--reset-daily]"

    @property
    def visible_to_users(self) -> bool:
        """Command is visible in help listings."""
        return True

    async def execute(self, args: list[str], context: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        """Execute the token usage command.

        Args:
            args: Command arguments:
                --detailed: Show detailed breakdown with recommendations
                --reset-daily: Reset daily statistics (requires admin)
            context: Execution context with user_id, state_manager, etc.

        Returns:
            Command result with usage report:
                - success: True if command executed successfully
                - message: Formatted usage report
                - error: Error message if failed

        Example:
            >>> result = await command.execute(["--detailed"], {"user_id": "user123"})
            >>> print(result["message"])
            📊 **Detailed Token Usage Report**
            ...
        """
        # Parse flags
        detailed = "--detailed" in args
        reset_daily = "--reset-daily" in args

        # Handle reset command (admin function)
        if reset_daily:
            return self._reset_daily_stats()

        # Get token tracker instance
        tracker = get_token_tracker()

        # Get usage statistics
        session_stats = tracker.get_session_summary()
        daily_stats = tracker.daily_stats  # Access public daily stats attribute

        # Format and return report
        if detailed:
            message = self._format_detailed_report(session_stats, daily_stats)
        else:
            message = self._format_brief_report(session_stats, daily_stats)

        return {"success": True, "message": message}

    def _reset_daily_stats(self) -> dict[str, Any]:
        """Reset daily token statistics.

        Returns:
            Success result with confirmation message.
        """
        tracker = get_token_tracker()
        tracker.daily_stats = tracker._create_daily_stats()
        tracker._save_daily_stats()
        return {
            "success": True,
            "message": "✅ **Daily Statistics Reset**\n\n"
            "Daily token statistics have been reset to zero.\n"
            "Session statistics remain unchanged.",
        }

    def _format_brief_report(
        self, session_stats: dict[str, Any], daily_stats: dict[str, Any]
    ) -> str:
        """Format brief usage summary.

        Args:
            session_stats: Current session statistics
            daily_stats: Daily statistics

        Returns:
            Formatted brief report string
        """
        # Calculate costs
        session_cost = session_stats.get("total_cost", 0.0)
        daily_cost = daily_stats.get("total_cost", 0.0)

        # Get limits
        tracker = get_token_tracker()
        daily_limit = tracker.LIMITS["max_daily_cost"]
        remaining_budget = daily_limit - daily_cost

        # Build brief summary
        daily_total_tokens = daily_stats.get("total_input_tokens", 0) + daily_stats.get(
            "total_output_tokens", 0
        )
        lines = [
            "📊 **Token Usage Summary**\n",
            "**Today's Usage:**",
            f"• Operations: {daily_stats.get('operations', 0)}",
            f"• Total Tokens: {daily_total_tokens:,}",
            f"• Cost: ${daily_cost:.4f}",
            f"• Remaining Budget: ${remaining_budget:.4f}\n",
            "**Current Session:**",
            f"• Operations: {session_stats.get('operations', 0)}",
            f"• Runtime: {self._format_runtime(session_stats.get('start_time', 0))}",
            f"• Session Cost: ${session_cost:.4f}\n",
        ]

        # Add budget warnings if needed
        if daily_cost >= daily_limit * 0.8:
            usage_pct = (daily_cost / daily_limit) * 100
            lines.append(f"⚠️ **Warning**: You have used {usage_pct:.1f}% of your daily budget!\n")

        lines.append("💡 Use `/token-usage --detailed` for more information")

        return "\n".join(lines)

    def _format_detailed_report(
        self, session_stats: dict[str, Any], daily_stats: dict[str, Any]
    ) -> str:
        """Format detailed usage report with recommendations.

        Args:
            session_stats: Current session statistics
            daily_stats: Daily statistics

        Returns:
            Formatted detailed report string
        """
        # Calculate metrics
        session_input = session_stats.get("total_input_tokens", 0)
        session_output = session_stats.get("total_output_tokens", 0)
        session_total = session_input + session_output
        session_cost = session_stats.get("total_cost", 0.0)

        daily_input = daily_stats.get("total_input_tokens", 0)
        daily_output = daily_stats.get("total_output_tokens", 0)
        daily_total = daily_input + daily_output
        daily_cost = daily_stats.get("total_cost", 0.0)

        tracker = get_token_tracker()
        daily_limit = tracker.LIMITS["max_daily_cost"]
        remaining_budget = daily_limit - daily_cost

        # Build detailed report
        lines = [
            "📊 **Detailed Token Usage Report**\n",
            "**Today's Usage:**",
            f"• Operations: {daily_stats.get('operations', 0)}",
            f"• Input Tokens: {daily_input:,}",
            f"• Output Tokens: {daily_output:,}",
            f"• Total Tokens: {daily_total:,}",
            f"• Total Cost: ${daily_cost:.4f}",
            f"• Remaining Budget: ${remaining_budget:.4f} of ${daily_limit:.2f}\n",
            "**Current Session:**",
            f"• Operations: {session_stats.get('operations', 0)}",
            f"• Runtime: {self._format_runtime(session_stats.get('start_time', 0))}",
            f"• Input Tokens: {session_input:,}",
            f"• Output Tokens: {session_output:,}",
            f"• Total Tokens: {session_total:,}",
            f"• Session Cost: ${session_cost:.4f}\n",
        ]

        # Add operations breakdown if available
        operations_by_type = daily_stats.get("operations_by_type", {})
        if operations_by_type:
            lines.append("**Operations Breakdown:**")
            for op_type, op_data in operations_by_type.items():
                count = op_data.get("count", 0)
                cost = op_data.get("cost", 0.0)
                tokens = op_data.get("tokens", 0)
                lines.append(f"• {op_type}: {count} ops, {tokens:,} tokens, ${cost:.4f}")
            lines.append("")

        # Add recommendations
        recommendations = self._generate_recommendations(daily_cost, daily_limit, daily_stats)
        if recommendations:
            lines.append("💡 **Recommendations:**")
            lines.extend(f"• {rec}" for rec in recommendations)

        return "\n".join(lines)

    def _format_runtime(self, start_time: float) -> str:
        """Format session runtime.

        Args:
            start_time: Session start time (Unix timestamp)

        Returns:
            Formatted runtime string (e.g., "5 minutes")
        """
        if start_time == 0:
            return "N/A"

        runtime_seconds = time.time() - start_time
        runtime_minutes = int(runtime_seconds / 60)

        if runtime_minutes < 1:
            return "< 1 minute"
        if runtime_minutes == 1:
            return "1 minute"
        return f"{runtime_minutes} minutes"

    def _generate_recommendations(
        self, daily_cost: float, daily_limit: float, daily_stats: dict[str, Any]
    ) -> list[str]:
        """Generate intelligent recommendations based on usage.

        Args:
            daily_cost: Current daily cost
            daily_limit: Daily cost limit
            daily_stats: Daily statistics

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Budget warnings
        usage_percent = (daily_cost / daily_limit) * 100 if daily_limit > 0 else 0

        if usage_percent >= 100:
            recommendations.append(f"⚠️ You have exceeded your daily budget of ${daily_limit:.2f}!")
        elif usage_percent >= 80:
            recommendations.append(
                f"⚠️ You have used {usage_percent:.1f}% of your daily budget. "
                "Consider reducing usage."
            )
        elif usage_percent >= 50:
            recommendations.append(
                f"You have used {usage_percent:.1f}% of your daily budget. Monitor usage carefully."
            )

        # High operation volume warning
        operations = daily_stats.get("operations", 0)
        if operations > 50:
            recommendations.append(
                f"High operation volume ({operations} operations today). "
                "Consider batching requests."
            )

        # Cost optimization tips
        daily_output = daily_stats.get("total_output_tokens", 0)
        daily_input = daily_stats.get("total_input_tokens", 0)

        if daily_output > daily_input * 2:
            recommendations.append(
                "Output tokens exceed input tokens significantly. "
                "Consider being more concise in prompts."
            )

        # General tips if no specific warnings
        if not recommendations:
            recommendations.append(
                "Usage is within normal limits. Keep monitoring your token consumption."
            )

        return recommendations
