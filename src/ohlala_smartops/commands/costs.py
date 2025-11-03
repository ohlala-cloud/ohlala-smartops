"""Costs command - Display AWS cost information for EC2 instances.

This module provides the CostsCommand that shows cost data from AWS Cost Explorer
for EC2 instances, helping with cost tracking and forecasting.

Phase 5C: Monitoring & Information commands.
"""

import logging
from decimal import Decimal
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand

logger: Final = logging.getLogger(__name__)


class CostsCommand(BaseCommand):
    """Handler for /costs command - Display AWS cost information.

    Shows cost data from AWS Cost Explorer:
    - Costs for specific instance or all instances
    - Cost breakdown by day/week/month
    - Forecast for remaining period (if enabled)
    - Warning about 24-48h Cost Explorer data latency

    Supports multiple targets and periods:
    - Target: instance-id or "all" (default: all)
    - Period: today, week, month (default: month)

    Example:
        >>> cmd = CostsCommand()
        >>> result = await cmd.execute(["i-1234567890abcdef0", "week"], context)
        >>> print(result["card"])  # Cost information card
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "costs"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Display cost information for EC2 instances"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/costs [instance-id|all] [period] - Show costs (today, week, month)"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute costs command.

        Args:
            args: Command arguments (target and period optional).
            context: Execution context containing:
                - mcp_manager: MCPManager instance

        Returns:
            Command result with adaptive card showing cost data.

        Example:
            >>> result = await cmd.execute(["all", "month"], context)
            >>> if result["success"]:
            ...     print("Cost data retrieved")
        """
        try:
            # Parse arguments
            target = "all"  # Default to all instances
            period = "month"  # Default to current month

            # Check for instance ID
            instance_id = self.parse_instance_id(args)
            if instance_id:
                target = instance_id

            # Check for period
            for arg in args:
                if arg.lower() in ["today", "week", "month"]:
                    period = arg.lower()

            # If target is an instance ID, validate it exists
            instance_name = None
            if target != "all":
                validation_result = await self.validate_instances_exist([target], context)

                if not validation_result["success"]:
                    return {
                        "success": False,
                        "message": f"❌ {validation_result['error']}",
                    }

                instance = validation_result["instances"][0]
                instance_name = instance.get("Name", target)

            # Get cost data
            try:
                cost_data = await self._get_costs(target, period, context)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to retrieve cost data: {e!s}",
                    "card": self.create_error_card(
                        "Cost Data Unavailable",
                        f"Unable to retrieve cost data from AWS Cost Explorer.\n\n"
                        f"This may be because:\n"
                        f"• Cost Explorer is not enabled in your AWS account\n"
                        f"• You don't have permissions to access Cost Explorer\n"
                        f"• Cost data is not available yet (24-48h latency)\n\n"
                        f"Error: {e!s}",
                    ),
                }

            # Build costs card
            card = self._build_costs_card(target, instance_name, period, cost_data)

            return {
                "success": True,
                "message": f"Cost data for {instance_name or 'all instances'} ({period})",
                "card": card,
            }

        except Exception as e:
            self.logger.error(f"Error getting costs: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get costs: {e!s}",
                "card": self.create_error_card(
                    "Failed to Get Costs",
                    f"Unable to retrieve cost data: {e!s}",
                ),
            }

    async def _get_costs(self, target: str, period: str, context: dict[str, Any]) -> dict[str, Any]:
        """Get cost data from Cost Explorer.

        Args:
            target: Instance ID or "all".
            period: Time period ("today", "week", "month").
            context: Execution context.

        Returns:
            Dictionary with cost data.
        """
        # Build parameters for MCP tool
        params: dict[str, Any] = {"Granularity": "DAILY", "Period": period}

        if target != "all":
            # Get costs for specific instance
            params["InstanceId"] = target
            result = await self.call_mcp_tool("get-instance-costs", params, context)
        else:
            # Get costs for all instances
            params["Metrics"] = ["UnblendedCost"]
            params["Filter"] = {
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Amazon Elastic Compute Cloud - Compute"],
                }
            }
            result = await self.call_mcp_tool("get-cost-and-usage", params, context)

        costs = result.get("costs", {})
        return costs if isinstance(costs, dict) else {}

    def _build_costs_card(
        self,
        target: str,
        instance_name: str | None,
        period: str,
        cost_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Build costs visualization card.

        Args:
            target: Instance ID or "all".
            instance_name: Instance name (if target is instance ID).
            period: Time period.
            cost_data: Cost data from Cost Explorer.

        Returns:
            Adaptive card dictionary.
        """
        # Title
        if target == "all":
            title = "💰 EC2 Costs: All Instances"
            subtitle = f"Period: {period.capitalize()}"
        else:
            title = f"💰 Costs: {instance_name or target}"
            subtitle = f"Instance ID: {target} • Period: {period.capitalize()}"

        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": title,
                "size": "Large",
                "weight": "Bolder",
                "color": "Accent",
            },
            {"type": "TextBlock", "text": subtitle, "spacing": "None", "isSubtle": True},
        ]

        # Data latency warning
        card_body.append(
            {
                "type": "Container",
                "style": "warning",
                "spacing": "Medium",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "⚠️ Cost Data Latency",
                        "weight": "Bolder",
                        "size": "Small",
                    },
                    {
                        "type": "TextBlock",
                        "text": "AWS Cost Explorer data has a 24-48 hour delay. "
                        "Recent costs may not be reflected yet.",
                        "wrap": True,
                        "size": "Small",
                    },
                ],
            }
        )

        # Extract cost information
        total_cost = cost_data.get("total_cost", Decimal("0"))
        daily_costs = cost_data.get("daily_costs", [])
        forecast = cost_data.get("forecast")

        # Check if we have cost data
        if total_cost == Decimal("0") and not daily_costs:
            card_body.append(
                {
                    "type": "Container",
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "No cost data available for this period.",
                            "isSubtle": True,
                        }
                    ],
                }
            )
        else:
            # Cost summary
            card_body.append(self._build_cost_summary(total_cost, daily_costs, period))

            # Daily breakdown (if available)
            if daily_costs:
                card_body.append(self._build_daily_breakdown(daily_costs))

            # Forecast (if available)
            if forecast:
                card_body.append(self._build_forecast_section(forecast))

        # Refresh action
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
                            "action": "costs",
                            "target": target,
                            "period": period,
                        },
                    }
                ],
            }
        )

        return {"type": "AdaptiveCard", "version": "1.5", "body": card_body}

    def _build_cost_summary(
        self, total_cost: Decimal, daily_costs: list[dict[str, Any]], period: str
    ) -> dict[str, Any]:
        """Build cost summary section.

        Args:
            total_cost: Total cost for the period.
            daily_costs: List of daily cost entries.
            period: Time period.

        Returns:
            Container with cost summary.
        """
        # Calculate daily average
        num_days = len(daily_costs) if daily_costs else 1
        daily_average = total_cost / num_days if num_days > 0 else Decimal("0")

        return {
            "type": "Container",
            "spacing": "Medium",
            "style": "emphasis",
            "items": [
                {
                    "type": "ColumnSet",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": f"${total_cost:.2f}",
                                    "size": "ExtraLarge",
                                    "weight": "Bolder",
                                    "horizontalAlignment": "Center",
                                    "color": "Accent",
                                },
                                {
                                    "type": "TextBlock",
                                    "text": f"Total Cost ({period.capitalize()})",
                                    "horizontalAlignment": "Center",
                                    "spacing": "None",
                                    "isSubtle": True,
                                },
                            ],
                        },
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": f"${daily_average:.2f}",
                                    "size": "ExtraLarge",
                                    "weight": "Bolder",
                                    "horizontalAlignment": "Center",
                                },
                                {
                                    "type": "TextBlock",
                                    "text": "Daily Average",
                                    "horizontalAlignment": "Center",
                                    "spacing": "None",
                                    "isSubtle": True,
                                },
                            ],
                        },
                    ],
                }
            ],
        }

    def _build_daily_breakdown(self, daily_costs: list[dict[str, Any]]) -> dict[str, Any]:
        """Build daily cost breakdown section.

        Args:
            daily_costs: List of daily cost entries.

        Returns:
            Container with daily breakdown.
        """
        breakdown_items: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "📅 Daily Breakdown",
                "weight": "Bolder",
                "size": "Medium",
            }
        ]

        # Show last 7 days or all if less
        for daily_entry in daily_costs[-7:]:
            date = daily_entry.get("date", "Unknown")
            amount = daily_entry.get("amount", Decimal("0"))

            breakdown_items.append(
                {
                    "type": "ColumnSet",
                    "spacing": "Small",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": str(date),
                                    "size": "Small",
                                }
                            ],
                        },
                        {
                            "type": "Column",
                            "width": "auto",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": f"${float(amount):.2f}",
                                    "size": "Small",
                                    "weight": "Bolder",
                                    "horizontalAlignment": "Right",
                                }
                            ],
                        },
                    ],
                }
            )

        if len(daily_costs) > 7:
            breakdown_items.append(
                {
                    "type": "TextBlock",
                    "text": f"... and {len(daily_costs) - 7} more days",
                    "spacing": "Small",
                    "size": "Small",
                    "isSubtle": True,
                }
            )

        return {"type": "Container", "spacing": "Medium", "items": breakdown_items}

    def _build_forecast_section(self, forecast: dict[str, Any]) -> dict[str, Any]:
        """Build forecast section.

        Args:
            forecast: Forecast data.

        Returns:
            Container with forecast information.
        """
        forecast_amount = forecast.get("amount", Decimal("0"))
        forecast_period = forecast.get("period", "remaining month")

        return {
            "type": "Container",
            "spacing": "Medium",
            "style": "emphasis",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "📈 Forecast",
                    "weight": "Bolder",
                    "size": "Medium",
                },
                {
                    "type": "TextBlock",
                    "text": f"Estimated cost for {forecast_period}: ${forecast_amount:.2f}",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": "Based on historical usage patterns. Actual costs may vary.",
                    "spacing": "Small",
                    "size": "Small",
                    "isSubtle": True,
                    "wrap": True,
                },
            ],
        }
