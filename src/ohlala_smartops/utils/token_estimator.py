"""Token consumption estimation for multi-instance AWS Bedrock operations.

This module provides utilities for estimating AWS Bedrock token consumption and costs
when managing multiple EC2 instances with the SmartOps bot. It helps users understand
the token and cost implications of various operations at scale.
"""

import json
import math
from typing import Any, Final


class TokenEstimator:
    """Estimates token consumption and costs for bot operations.

    This class provides static methods to estimate token usage for various
    operations when managing multiple EC2 instances. It includes cost calculations,
    limit checking, and throttling risk assessments.

    Attributes:
        PRICING: Claude Sonnet 4.0 pricing per 1K tokens.
        MODEL_LIMITS: Maximum token limits for the model.
        OPERATION_TOKENS: Typical token counts for different operations.
    """

    # Claude Sonnet 4.0 pricing (as of 2024)
    PRICING: Final[dict[str, float]] = {
        "input_tokens_per_1k": 0.003,  # $3 per million input tokens
        "output_tokens_per_1k": 0.015,  # $15 per million output tokens
    }

    # Model limits
    MODEL_LIMITS: Final[dict[str, int]] = {
        "max_input_tokens": 200000,  # Claude Sonnet 4 context window
        "max_output_tokens": 4096,  # Max response size
        "bedrock_max_tokens": 4096,  # BEDROCK_MAX_TOKENS from constants.py
    }

    # Typical token counts for different operations (based on observation)
    OPERATION_TOKENS: Final[dict[str, int]] = {
        # Base conversation overhead
        "system_prompt": 2500,  # System prompt with available tools
        "tool_definitions": 8000,  # ~80 MCP tools at ~100 tokens each
        "conversation_context": 1500,  # Last 5 messages of context
        # Per-instance data
        "instance_metadata": 150,  # Basic instance info (ID, name, type, etc.)
        "ssm_command_request": 200,  # Send-command tool call
        "ssm_command_response": 500,  # Command execution result metadata
        # Command output (varies by command type)
        "disk_check_output": 800,  # Disk usage check per instance
        "process_list_output": 2000,  # Process listing per instance
        "health_check_output": 1200,  # Comprehensive health check
        "software_inventory_output": 3000,  # Detailed software inventory
        "log_analysis_output": 2500,  # Log file analysis
        # LLM analysis
        "per_instance_analysis": 300,  # LLM's analysis text per instance
        "summary_overhead": 500,  # Final summary overhead
    }

    @classmethod
    def estimate_tokens(
        cls,
        num_instances: int,
        command_type: str = "health_check",
        include_analysis: bool = True,
    ) -> dict[str, Any]:
        """Estimate token consumption for a multi-instance operation.

        Args:
            num_instances: Number of EC2 instances to process.
            command_type: Type of command (disk_check, process_list, health_check, etc.).
            include_analysis: Whether to include LLM analysis in the response. Defaults to True.

        Returns:
            Dictionary containing token estimates, costs, limits, and recommendations:
            - instances: Number of instances
            - command_type: Type of command
            - tokens: Input, output, and total token counts with percentage of limit
            - costs: Input, output, total, and per-instance costs
            - limits: Whether within limits and tokens remaining
            - throttling_risk: Risk assessment with level, score, and mitigation
            - warnings: List of warning messages
            - recommendations: List of optimization recommendations

        Example:
            >>> estimate = TokenEstimator.estimate_tokens(10, "health_check")
            >>> print(f"Total cost: {estimate['costs']['total_cost']}")
            Total cost: $0.0450
        """
        # Calculate input tokens (request to Bedrock)
        input_tokens = (
            cls.OPERATION_TOKENS["system_prompt"]
            + cls.OPERATION_TOKENS["tool_definitions"]
            + cls.OPERATION_TOKENS["conversation_context"]
            + (cls.OPERATION_TOKENS["instance_metadata"] * num_instances)
            + (
                cls.OPERATION_TOKENS["ssm_command_request"] * math.ceil(num_instances / 5)
            )  # Commands batched by 5
        )

        # Calculate tokens for command outputs
        output_key = f"{command_type}_output"
        command_output_tokens = (
            cls.OPERATION_TOKENS.get(output_key, cls.OPERATION_TOKENS["health_check_output"])
            * num_instances
        )

        # Add tool response tokens (command results fed back to LLM)
        input_tokens += command_output_tokens

        # Calculate output tokens (LLM's response)
        output_tokens = cls.OPERATION_TOKENS["summary_overhead"]
        if include_analysis:
            output_tokens += cls.OPERATION_TOKENS["per_instance_analysis"] * num_instances

        # Total tokens for the complete interaction
        total_tokens = input_tokens + output_tokens

        # Calculate costs
        input_cost = (input_tokens / 1000) * cls.PRICING["input_tokens_per_1k"]
        output_cost = (output_tokens / 1000) * cls.PRICING["output_tokens_per_1k"]
        total_cost = input_cost + output_cost

        # Check limits and provide recommendations
        warnings: list[str] = []
        recommendations: list[str] = []

        if input_tokens > cls.MODEL_LIMITS["max_input_tokens"]:
            warnings.append(
                f"⚠️ Input tokens ({input_tokens:,}) exceed model limit "
                f"({cls.MODEL_LIMITS['max_input_tokens']:,})"
            )
            max_instances = cls._calculate_max_instances(command_type)
            recommendations.append(f"Maximum instances for {command_type}: {max_instances}")

        if input_tokens > cls.MODEL_LIMITS["max_input_tokens"] * 0.8:
            warnings.append("⚡ High token usage - approaching model limits")
            recommendations.append(
                "Consider batching operations or reducing command output verbosity"
            )

        # Throttling risk assessment
        throttling_risk = cls._assess_throttling_risk(num_instances, command_type)

        return {
            "instances": num_instances,
            "command_type": command_type,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
                "percentage_of_limit": (input_tokens / cls.MODEL_LIMITS["max_input_tokens"]) * 100,
            },
            "costs": {
                "input_cost": f"${input_cost:.4f}",
                "output_cost": f"${output_cost:.4f}",
                "total_cost": f"${total_cost:.4f}",
                "cost_per_instance": f"${total_cost/num_instances:.4f}",
            },
            "limits": {
                "within_limits": input_tokens <= cls.MODEL_LIMITS["max_input_tokens"],
                "tokens_remaining": max(0, cls.MODEL_LIMITS["max_input_tokens"] - input_tokens),
            },
            "throttling_risk": throttling_risk,
            "warnings": warnings,
            "recommendations": recommendations,
        }

    @classmethod
    def _calculate_max_instances(cls, command_type: str) -> int:
        """Calculate maximum instances that can be processed without exceeding token limits.

        Args:
            command_type: Type of command being executed.

        Returns:
            Maximum number of instances that can be safely processed (with 80% safety margin).
        """
        # Fixed overhead
        base_tokens = (
            cls.OPERATION_TOKENS["system_prompt"]
            + cls.OPERATION_TOKENS["tool_definitions"]
            + cls.OPERATION_TOKENS["conversation_context"]
            + cls.OPERATION_TOKENS["summary_overhead"]
        )

        # Per-instance tokens
        output_key = f"{command_type}_output"
        per_instance_tokens = (
            cls.OPERATION_TOKENS["instance_metadata"]
            + cls.OPERATION_TOKENS.get(output_key, cls.OPERATION_TOKENS["health_check_output"])
            + cls.OPERATION_TOKENS["per_instance_analysis"]
            + 40  # Amortized SSM command request tokens
        )

        # Calculate maximum instances
        available_tokens = cls.MODEL_LIMITS["max_input_tokens"] - base_tokens
        max_instances = int(available_tokens / per_instance_tokens)

        # Apply safety margin (80% of theoretical max)
        return int(max_instances * 0.8)

    @classmethod
    def _assess_throttling_risk(cls, num_instances: int, command_type: str) -> dict[str, Any]:
        """Assess risk of hitting AWS Bedrock throttling limits.

        Args:
            num_instances: Number of instances being processed.
            command_type: Type of command being executed.

        Returns:
            Dictionary with risk level, score, API call count, and mitigation strategies.
        """
        # Estimate API calls needed
        num_commands = math.ceil(num_instances / 5)  # Commands batched by 5
        bedrock_calls = 1 + num_commands  # Initial call + follow-up for results

        # Risk levels based on number of instances and operation complexity
        if num_instances <= 10:
            risk_level = "Low"
            risk_score = 0.2
        elif num_instances <= 25:
            risk_level = "Medium"
            risk_score = 0.5
        elif num_instances <= 50:
            risk_level = "High"
            risk_score = 0.8
        else:
            risk_level = "Very High"
            risk_score = 0.95

        # Adjust based on command complexity
        if command_type in ["software_inventory_output", "log_analysis_output"]:
            risk_score = min(1.0, risk_score * 1.3)

        return {
            "level": risk_level,
            "score": risk_score,
            "bedrock_api_calls": bedrock_calls,
            "mitigation": cls._get_throttling_mitigation(risk_level),
        }

    @classmethod
    def _get_throttling_mitigation(cls, risk_level: str) -> list[str]:
        """Get throttling mitigation strategies based on risk level.

        Args:
            risk_level: Risk level (Low, Medium, High, Very High).

        Returns:
            List of mitigation strategy recommendations.
        """
        mitigations: dict[str, list[str]] = {
            "Low": ["Current configuration should work without issues"],
            "Medium": [
                "Consider adding 1-2 second delays between operations",
                "Monitor for throttling errors in logs",
            ],
            "High": [
                "Implement progressive batching (5-10 instances at a time)",
                "Add 2-3 second delays between batches",
                "Consider using async processing for better throughput",
            ],
            "Very High": [
                "Break operations into smaller batches (max 10 instances)",
                "Implement exponential backoff between batches",
                "Consider scheduling operations during off-peak hours",
                "Request AWS Bedrock quota increase if needed regularly",
            ],
        }

        return mitigations.get(risk_level, ["Unknown risk level"])

    @classmethod
    def generate_scaling_report(cls) -> str:
        """Generate a comprehensive scaling report for different scenarios.

        Returns:
            Formatted multi-line string containing token consumption analysis
            for various deployment scenarios with recommendations.

        Example:
            >>> report = TokenEstimator.generate_scaling_report()
            >>> print(report)
        """
        report: list[str] = []
        report.append("=" * 80)
        report.append("SMARTOPS AGENT TOKEN CONSUMPTION AND SCALING GUIDE")
        report.append("=" * 80)
        report.append("")

        # Test different scenarios
        scenarios: list[tuple[int, str, str]] = [
            (10, "disk_check", "Small deployment - Disk monitoring"),
            (25, "health_check", "Medium deployment - Health checks"),
            (50, "process_list", "Large deployment - Process monitoring"),
            (100, "software_inventory", "Extra large - Software inventory"),
            (200, "health_check", "Enterprise - Comprehensive monitoring"),
        ]

        for num_instances, command_type, description in scenarios:
            report.append(f"\n📊 SCENARIO: {description}")
            report.append(f"   Instances: {num_instances}")
            report.append(f"   Command: {command_type}")
            report.append("-" * 60)

            estimate = cls.estimate_tokens(num_instances, command_type)

            report.append("   Token Usage:")
            report.append(f"   • Input tokens: {estimate['tokens']['input']:,}")
            report.append(f"   • Output tokens: {estimate['tokens']['output']:,}")
            report.append(f"   • Total tokens: {estimate['tokens']['total']:,}")
            report.append(f"   • % of limit: {estimate['tokens']['percentage_of_limit']:.1f}%")

            report.append("\n   Estimated Costs:")
            report.append(f"   • Total: {estimate['costs']['total_cost']}")
            report.append(f"   • Per instance: {estimate['costs']['cost_per_instance']}")

            report.append(f"\n   Throttling Risk: {estimate['throttling_risk']['level']}")

            if estimate["warnings"]:
                report.append("\n   ⚠️ Warnings:")
                for warning in estimate["warnings"]:
                    report.append(f"   {warning}")  # noqa: PERF401

            if estimate["recommendations"]:
                report.append("\n   💡 Recommendations:")
                for rec in estimate["recommendations"]:
                    report.append(f"   • {rec}")  # noqa: PERF401

        # Add general recommendations
        report.append("\n" + "=" * 80)
        report.append("GENERAL RECOMMENDATIONS")
        report.append("=" * 80)

        report.append("\n✅ OPTIMAL OPERATING RANGES:")
        report.append("• 1-10 instances: Ideal for real-time operations")
        report.append("• 11-25 instances: Good performance with occasional delays")
        report.append("• 26-50 instances: Consider batching and async processing")
        report.append("• 50+ instances: Implement progressive batching and monitoring")

        report.append("\n🎯 TOKEN OPTIMIZATION STRATEGIES:")
        report.append("• Use targeted SSM commands (avoid verbose outputs)")
        report.append("• Filter command outputs at source (grep, select-object)")
        report.append("• Implement command result caching for repeated checks")
        report.append("• Use CloudWatch metrics for historical data instead of live queries")

        report.append("\n⚡ HANDLING SCALE:")
        report.append("• For 100+ instances: Consider CloudWatch + EventBridge for monitoring")
        report.append("• For regular large-scale operations: Request Bedrock quota increases")
        report.append("• Implement circuit breakers to prevent cascade failures")
        report.append("• Use AWS Systems Manager Fleet Manager for massive deployments")

        return "\n".join(report)


def main() -> None:
    """CLI interface for token estimation.

    Provides command-line interface for estimating token consumption
    for various instance counts and command types.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Estimate token consumption for Ohlala SmartOps")
    parser.add_argument("--instances", type=int, default=10, help="Number of EC2 instances")
    parser.add_argument(
        "--command",
        default="health_check",
        choices=[
            "disk_check",
            "process_list",
            "health_check",
            "software_inventory",
            "log_analysis",
        ],
        help="Type of command to run",
    )
    parser.add_argument("--report", action="store_true", help="Generate full scaling report")

    args = parser.parse_args()

    if args.report:
        print(TokenEstimator.generate_scaling_report())
    else:
        estimate = TokenEstimator.estimate_tokens(args.instances, args.command)
        print(json.dumps(estimate, indent=2))


if __name__ == "__main__":
    main()
