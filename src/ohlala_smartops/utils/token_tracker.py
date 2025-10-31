"""Real-time token usage tracking and limits for AWS Bedrock operations.

This module provides token tracking, usage limits, and cost monitoring to prevent
exceeding AWS Bedrock model limits and manage costs. It maintains both session-based
and daily statistics with persistent storage.
"""

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

logger: Final = logging.getLogger(__name__)


class TokenTracker:
    """Tracks token usage, costs, and enforces limits for Bedrock operations.

    Maintains both session-based (in-memory) and daily (persistent) statistics.
    Daily statistics are stored in a JSON file and reset at midnight UTC.

    Attributes:
        PRICING: Claude Sonnet 4.0 pricing per 1K tokens.
        LIMITS: Token and cost limits with warning thresholds.
    """

    # Claude Sonnet 4.0 pricing (per 1000 tokens)
    PRICING: Final[dict[str, float]] = {
        "input_tokens_per_1k": 0.003,  # $3 per million input tokens
        "output_tokens_per_1k": 0.015,  # $15 per million output tokens
    }

    # Model limits
    LIMITS: Final[dict[str, float]] = {
        "max_input_tokens": 200000,  # Claude Sonnet 4 context window
        "max_output_tokens": 4096,  # Max response size
        "warning_threshold": 0.8,  # Warn at 80% of limit
        "max_daily_cost": 5.0,  # Daily cost limit ($5)
        "max_operation_cost": 1.0,  # Per-operation cost limit ($1)
    }

    def __init__(
        self,
        storage_path: str = "/tmp/smartops_daily_tokens.json",  # nosec B108
    ) -> None:
        """Initialize the token tracker.

        Args:
            storage_path: Path to store daily statistics.
                Defaults to /tmp/smartops_daily_tokens.json.
        """
        self.storage_path = Path(storage_path)
        self.session_stats: dict[str, Any] = {
            "operations": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost": 0.0,
            "start_time": time.time(),
        }
        self.daily_stats = self._load_daily_stats()

    def _load_daily_stats(self) -> dict[str, Any]:
        """Load daily statistics from persistent storage.

        Returns:
            Dictionary containing daily statistics, or new stats if file doesn't exist
            or is from a previous day.
        """
        try:
            with self.storage_path.open() as f:
                data: dict[str, Any] = json.load(f)
                # Check if it's a new day
                last_date = datetime.fromisoformat(data.get("date", "2000-01-01"))
                today = datetime.now(UTC).date()
                if last_date.date() != today:
                    # Reset for new day
                    return self._create_daily_stats()
                return data
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return self._create_daily_stats()

    def _create_daily_stats(self) -> dict[str, Any]:
        """Create new daily statistics.

        Returns:
            Dictionary with initialized daily statistics.
        """
        return {
            "date": datetime.now(UTC).isoformat(),
            "operations": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost": 0.0,
            "operations_by_type": {},
        }

    def _save_daily_stats(self) -> None:
        """Save daily statistics to persistent storage.

        Logs errors if saving fails but does not raise exceptions.
        """
        try:
            with self.storage_path.open("w") as f:
                json.dump(self.daily_stats, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save daily stats: {e}")

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses approximate ratio: 1 token ≈ 3.5 characters for Claude.
        This provides a conservative estimate for limit checking.

        Args:
            text: Text to estimate tokens for.

        Returns:
            Estimated token count.

        Example:
            >>> tracker = TokenTracker()
            >>> tokens = tracker.estimate_tokens("Hello, world!")
            >>> print(tokens)
            3
        """
        if not text:
            return 0

        # Rough estimation: 3.5 chars per token for Claude (conservative)
        estimated = len(str(text)) / 3.5
        return int(estimated)

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> tuple[float, float, float]:
        """Calculate costs for input, output, and total tokens.

        Args:
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Tuple of (input_cost, output_cost, total_cost) in USD.

        Example:
            >>> tracker = TokenTracker()
            >>> input_cost, output_cost, total = tracker.calculate_cost(1000, 500)
            >>> print(f"${total:.4f}")
            $0.0105
        """
        input_cost = (input_tokens / 1000) * self.PRICING["input_tokens_per_1k"]
        output_cost = (output_tokens / 1000) * self.PRICING["output_tokens_per_1k"]
        total_cost = input_cost + output_cost
        return input_cost, output_cost, total_cost

    def check_limits(
        self,
        estimated_input_tokens: int,
        operation_type: str = "bedrock_call",  # noqa: ARG002
        num_instances: int = 1,
    ) -> dict[str, Any]:
        """Check if operation would exceed limits and generate warnings.

        Args:
            estimated_input_tokens: Estimated input token count.
            operation_type: Type of operation for logging.
            num_instances: Number of instances involved in operation.

        Returns:
            Dictionary containing:
            - allowed: Whether operation is allowed
            - estimated_input_tokens: Confirmed input token estimate
            - estimated_output_tokens: Estimated output tokens
            - estimated_cost: Estimated operation cost
            - warnings: List of warning messages
            - recommendations: List of recommendations
            - limits_remaining: Remaining limits (tokens, daily cost)

        Example:
            >>> tracker = TokenTracker()
            >>> result = tracker.check_limits(10000, "health_check", 5)
            >>> if not result["allowed"]:
            ...     print("Operation blocked!")
        """
        warnings: list[str] = []
        recommendations: list[str] = []
        allowed = True

        # Check model context limit (hard limit - block if exceeded)
        if estimated_input_tokens > self.LIMITS["max_input_tokens"]:
            allowed = False
            warnings.append(
                f"❌ Input tokens ({estimated_input_tokens:,}) exceed model limit "
                f"({int(self.LIMITS['max_input_tokens']):,})"
            )
            recommendations.append(
                f"Reduce to max {self._calculate_max_instances_for_limit()} instances"
            )

        # Check warning threshold
        elif estimated_input_tokens > (
            self.LIMITS["max_input_tokens"] * self.LIMITS["warning_threshold"]
        ):
            warnings.append(
                f"⚠️ High token usage: {estimated_input_tokens:,} tokens "
                f"({estimated_input_tokens/self.LIMITS['max_input_tokens']*100:.1f}% of limit)"
            )
            recommendations.append("Consider batching or reducing output verbosity")

        # Estimate cost for this operation
        estimated_output_tokens = min(2000, 200 * num_instances)  # Conservative estimate
        _, _, estimated_cost = self.calculate_cost(estimated_input_tokens, estimated_output_tokens)

        # Check per-operation cost limit (warning only - no longer blocks)
        if estimated_cost > self.LIMITS["max_operation_cost"]:
            warnings.append(
                f"⚠️ Operation cost (${estimated_cost:.4f}) exceeds per-operation limit "
                f"(${self.LIMITS['max_operation_cost']})"
            )
            recommendations.append(
                "Consider breaking operation into smaller batches to optimize costs"
            )

        # Check daily cost limit (warning only - no longer blocks)
        projected_daily_cost = self.daily_stats["total_cost"] + estimated_cost
        if projected_daily_cost > self.LIMITS["max_daily_cost"]:
            warnings.append(
                f"⚠️ Daily cost limit will be exceeded: ${projected_daily_cost:.2f} > "
                f"${self.LIMITS['max_daily_cost']}"
            )
            recommendations.append("Monitor daily costs - consider optimizing future operations")

        # Add $5 increment warnings
        current_daily_cost = self.daily_stats["total_cost"]
        new_daily_cost = current_daily_cost + estimated_cost

        # Check if we're crossing a $5 threshold
        current_threshold = int(current_daily_cost / 5.0)
        new_threshold = int(new_daily_cost / 5.0)

        if new_threshold > current_threshold:
            next_milestone = (new_threshold + 1) * 5
            warnings.append(
                f"💰 Daily cost milestone: ${new_threshold * 5:.0f} threshold crossed "
                f"(current: ${new_daily_cost:.2f})"
            )
            recommendations.append(f"Next milestone at ${next_milestone}")

        # Warning when approaching next $5 increment (within $1)
        next_threshold_amount = (int(new_daily_cost / 5.0) + 1) * 5
        distance_to_next = next_threshold_amount - new_daily_cost
        if distance_to_next <= 1.0 and distance_to_next > 0:
            warnings.append(
                f"⚠️ Approaching ${next_threshold_amount} milestone "
                f"(${distance_to_next:.2f} remaining)"
            )
            recommendations.append("Monitor costs closely to track spending")

        return {
            "allowed": allowed,
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_cost": estimated_cost,
            "warnings": warnings,
            "recommendations": recommendations,
            "limits_remaining": {
                "tokens": int(self.LIMITS["max_input_tokens"] - estimated_input_tokens),
                "daily_cost": self.LIMITS["max_daily_cost"] - self.daily_stats["total_cost"],
            },
        }

    def _calculate_max_instances_for_limit(self) -> int:
        """Calculate maximum instances that fit within token limits.

        Returns:
            Maximum number of instances with 80% safety margin.
        """
        # Rough estimation based on typical command outputs
        base_tokens = 12000  # System prompt + tools + context
        per_instance_tokens = 1500  # Average per instance

        available_tokens = self.LIMITS["max_input_tokens"] - base_tokens
        max_instances = int(available_tokens / per_instance_tokens)

        # 80% safety margin
        return int(max_instances * 0.8)

    def track_operation(
        self,
        operation_type: str,
        input_tokens: int,
        output_tokens: int,
        num_instances: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Track a completed operation and update statistics.

        Updates both session and daily statistics, and persists daily stats to disk.

        Args:
            operation_type: Type of operation (e.g., 'health_check', 'disk_analysis').
            input_tokens: Actual input tokens consumed.
            output_tokens: Actual output tokens generated.
            num_instances: Number of instances involved. Defaults to 1.
            metadata: Additional operation metadata. Defaults to None.

        Returns:
            Operation tracking record with timestamp, tokens, costs, and metadata.

        Example:
            >>> tracker = TokenTracker()
            >>> record = tracker.track_operation("health_check", 1000, 500, 3)
            >>> print(f"Cost: ${record['costs']['total']:.4f}")
        """
        input_cost, output_cost, total_cost = self.calculate_cost(input_tokens, output_tokens)

        operation_record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": operation_type,
            "instances": num_instances,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            "costs": {
                "input": input_cost,
                "output": output_cost,
                "total": total_cost,
                "per_instance": total_cost / max(1, num_instances),
            },
            "metadata": metadata or {},
        }

        # Update session stats
        self.session_stats["operations"] += 1
        self.session_stats["total_input_tokens"] += input_tokens
        self.session_stats["total_output_tokens"] += output_tokens
        self.session_stats["total_cost"] += total_cost

        # Update daily stats
        self.daily_stats["operations"] += 1
        self.daily_stats["total_input_tokens"] += input_tokens
        self.daily_stats["total_output_tokens"] += output_tokens
        self.daily_stats["total_cost"] += total_cost

        # Track by operation type
        if operation_type not in self.daily_stats["operations_by_type"]:
            self.daily_stats["operations_by_type"][operation_type] = {
                "count": 0,
                "tokens": 0,
                "cost": 0.0,
            }

        self.daily_stats["operations_by_type"][operation_type]["count"] += 1
        self.daily_stats["operations_by_type"][operation_type]["tokens"] += (
            input_tokens + output_tokens
        )
        self.daily_stats["operations_by_type"][operation_type]["cost"] += total_cost

        # Save updated stats
        self._save_daily_stats()

        # Log the operation
        logger.info(
            f"📊 TOKEN TRACKING: {operation_type} - {input_tokens:,} in + "
            f"{output_tokens:,} out = ${total_cost:.4f}"
        )

        return operation_record

    def get_session_summary(self) -> dict[str, Any]:
        """Get current session statistics summary.

        Returns:
            Dictionary containing session, daily, and limits information.

        Example:
            >>> tracker = TokenTracker()
            >>> summary = tracker.get_session_summary()
            >>> print(f"Session cost: ${summary['session']['total_cost']:.4f}")
        """
        runtime = time.time() - self.session_stats["start_time"]
        total_tokens = (
            self.session_stats["total_input_tokens"] + self.session_stats["total_output_tokens"]
        )

        return {
            "session": {
                "runtime_minutes": runtime / 60,
                "operations": self.session_stats["operations"],
                "total_tokens": total_tokens,
                "total_cost": self.session_stats["total_cost"],
                "avg_cost_per_operation": (
                    self.session_stats["total_cost"] / max(1, self.session_stats["operations"])
                ),
            },
            "daily": {
                "operations": self.daily_stats["operations"],
                "total_tokens": (
                    self.daily_stats["total_input_tokens"] + self.daily_stats["total_output_tokens"]
                ),
                "total_cost": self.daily_stats["total_cost"],
                "cost_remaining": self.LIMITS["max_daily_cost"] - self.daily_stats["total_cost"],
                "operations_by_type": self.daily_stats["operations_by_type"],
            },
            "limits": {
                "daily_cost_limit": self.LIMITS["max_daily_cost"],
                "operation_cost_limit": self.LIMITS["max_operation_cost"],
                "token_limit": int(self.LIMITS["max_input_tokens"]),
            },
        }

    def format_usage_report(self) -> str:
        """Generate a formatted usage report.

        Returns:
            Formatted multi-line string containing usage statistics.

        Example:
            >>> tracker = TokenTracker()
            >>> print(tracker.format_usage_report())
        """
        summary = self.get_session_summary()

        report: list[str] = []
        report.append("📊 **Ohlala SmartOps Token Usage Report**")
        report.append("=" * 50)

        # Session stats
        report.append("\n**Current Session:**")
        report.append(f"• Runtime: {summary['session']['runtime_minutes']:.1f} minutes")
        report.append(f"• Operations: {summary['session']['operations']}")
        report.append(f"• Total tokens: {summary['session']['total_tokens']:,}")
        report.append(f"• Total cost: ${summary['session']['total_cost']:.4f}")
        if summary["session"]["operations"] > 0:
            report.append(
                f"• Avg cost/operation: ${summary['session']['avg_cost_per_operation']:.4f}"
            )

        # Daily stats
        report.append("\n**Today's Usage:**")
        report.append(f"• Operations: {summary['daily']['operations']}")
        report.append(f"• Total tokens: {summary['daily']['total_tokens']:,}")
        report.append(f"• Total cost: ${summary['daily']['total_cost']:.4f}")
        report.append(f"• Remaining budget: ${summary['daily']['cost_remaining']:.4f}")

        # Operations by type
        if summary["daily"]["operations_by_type"]:
            report.append("\n**Operations by Type:**")
            for op_type, stats in summary["daily"]["operations_by_type"].items():
                report.append(
                    f"• {op_type}: {stats['count']} ops, {stats['tokens']:,} tokens, "
                    f"${stats['cost']:.4f}"
                )

        # Limits
        report.append("\n**Limits:**")
        report.append(f"• Daily cost limit: ${summary['limits']['daily_cost_limit']}")
        report.append(f"• Per-operation limit: ${summary['limits']['operation_cost_limit']}")
        report.append(f"• Token limit: {summary['limits']['token_limit']:,}")

        return "\n".join(report)


# Global instance
_token_tracker: TokenTracker | None = None


def get_token_tracker() -> TokenTracker:
    """Get the global token tracker singleton instance.

    Returns:
        The global TokenTracker instance, creating it if necessary.

    Example:
        >>> tracker = get_token_tracker()
        >>> summary = tracker.get_session_summary()
    """
    global _token_tracker  # noqa: PLW0603
    if _token_tracker is None:
        _token_tracker = TokenTracker()
    return _token_tracker


def estimate_bedrock_input_tokens(
    system_prompt: str,
    user_message: str,
    tool_definitions: list[dict[str, Any]],
    conversation_context: str = "",
    tool_results: list[dict[str, Any]] | None = None,
) -> int:
    """Estimate total input tokens for a Bedrock request.

    Args:
        system_prompt: System prompt text.
        user_message: User's message.
        tool_definitions: List of tool definitions.
        conversation_context: Previous conversation context. Defaults to "".
        tool_results: Tool execution results. Defaults to None.

    Returns:
        Estimated input token count.

    Example:
        >>> tokens = estimate_bedrock_input_tokens("System", "Hello", [], "")
        >>> print(tokens)
    """
    tracker = get_token_tracker()
    total_text = ""

    # Add system prompt
    total_text += system_prompt

    # Add user message
    total_text += user_message

    # Add conversation context
    total_text += conversation_context

    # Add tool definitions (approximate)
    if tool_definitions:
        tools_text = json.dumps(tool_definitions)
        total_text += tools_text

    # Add tool results
    if tool_results:
        results_text = json.dumps(tool_results)
        total_text += results_text

    return tracker.estimate_tokens(total_text)


def check_operation_limits(
    estimated_input_tokens: int, operation_type: str, num_instances: int = 1
) -> dict[str, Any]:
    """Check if operation is within limits.

    Convenience function for the global token tracker.

    Args:
        estimated_input_tokens: Estimated input token count.
        operation_type: Type of operation.
        num_instances: Number of instances. Defaults to 1.

    Returns:
        Dictionary with limit check results.
    """
    tracker = get_token_tracker()
    return tracker.check_limits(estimated_input_tokens, operation_type, num_instances)


def track_bedrock_operation(
    operation_type: str,
    input_tokens: int,
    output_tokens: int,
    num_instances: int = 1,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Track a completed Bedrock operation.

    Convenience function for the global token tracker.

    Args:
        operation_type: Type of operation.
        input_tokens: Actual input tokens consumed.
        output_tokens: Actual output tokens generated.
        num_instances: Number of instances. Defaults to 1.
        metadata: Additional metadata. Defaults to None.

    Returns:
        Operation tracking record.
    """
    tracker = get_token_tracker()
    return tracker.track_operation(
        operation_type, input_tokens, output_tokens, num_instances, metadata
    )


def get_usage_summary() -> dict[str, Any]:
    """Get current usage summary.

    Returns:
        Dictionary containing usage statistics.
    """
    tracker = get_token_tracker()
    return tracker.get_session_summary()


def get_usage_report() -> str:
    """Get formatted usage report.

    Returns:
        Formatted multi-line usage report.
    """
    tracker = get_token_tracker()
    return tracker.format_usage_report()


def main() -> None:
    """CLI interface for token tracking."""
    parser = argparse.ArgumentParser(description="SmartOps Agent Token Tracker")
    parser.add_argument("--report", action="store_true", help="Show usage report")
    parser.add_argument("--reset-daily", action="store_true", help="Reset daily statistics")
    parser.add_argument("--estimate", type=str, help="Estimate tokens for text")

    args = parser.parse_args()

    tracker = get_token_tracker()

    if args.report:
        print(get_usage_report())
    elif args.reset_daily:
        tracker.daily_stats = tracker._create_daily_stats()
        tracker._save_daily_stats()
        print("Daily statistics reset.")
    elif args.estimate:
        tokens = tracker.estimate_tokens(args.estimate)
        print(f"Estimated tokens: {tokens:,}")
        cost = tokens / 1000 * tracker.PRICING["input_tokens_per_1k"]
        print(f"Estimated cost (as input): ${cost:.6f}")
    else:
        print("Use --help for available options")


if __name__ == "__main__":
    main()
