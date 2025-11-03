"""List instances command - Display all EC2 instances.

This module provides the ListInstancesCommand that lists all EC2 instances
in the account with their status, instance type, and quick action buttons.

Phase 5B: Core instance management command.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.adaptive_cards import CardTemplates
from ohlala_smartops.commands.base import BaseCommand

logger: Final = logging.getLogger(__name__)


class ListInstancesCommand(BaseCommand):
    """Handler for /list command - List all EC2 instances.

    Displays comprehensive list of instances with:
    - Instance overview (total count, state summary)
    - Individual instance cards with key details
    - Quick action buttons for running instances
    - Sortedby state (running first) and name

    Example:
        >>> cmd = ListInstancesCommand()
        >>> result = await cmd.execute([], context)
        >>> print(result["card"])  # Adaptive card with instance list
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "list"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "List all EC2 instances with status and details"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/list - Show all EC2 instances"

    async def execute(
        self,
        args: list[str],  # noqa: ARG002
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute list instances command.

        Args:
            args: Command arguments (not used for list).
            context: Execution context containing:
                - turn_context: Bot Framework TurnContext (optional)
                - mcp_manager: MCPManager instance

        Returns:
            Command result with adaptive card showing all instances.

        Example:
            >>> result = await cmd.execute([], context)
            >>> if result["success"]:
            ...     print(f"Found {len(instances)} instances")
        """
        try:
            # Send progress message if possible
            turn_context = context.get("turn_context")
            if turn_context:
                try:
                    # Note: Message updates don't work reliably in Teams
                    # This is a best-effort progress indication
                    pass
                except Exception as progress_error:
                    self.logger.warning(f"Failed to send progress message: {progress_error}")

            # Get all instances via MCP
            instances_result = await self.call_mcp_tool("list-instances", {}, context)
            instances = instances_result.get("instances", [])

            if not instances:
                return {
                    "success": True,
                    "message": "No EC2 instances found in this AWS account.",
                }

            # Build the instances card
            card = self._build_instances_card(instances)

            return {
                "success": True,
                "message": f"Found {len(instances)} EC2 instances",
                "card": card,
            }

        except Exception as e:
            self.logger.error(f"Error listing instances: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to list instances: {e!s}",
                "card": self.create_error_card(
                    "Failed to List Instances",
                    f"Unable to retrieve EC2 instances: {e!s}",
                ),
            }

    def _build_instances_card(self, instances: list[dict[str, Any]]) -> dict[str, Any]:
        """Build adaptive card for instances list.

        Args:
            instances: List of instance dictionaries from MCP.

        Returns:
            Adaptive card dictionary.
        """
        # Count instances by state
        state_counts: dict[str, int] = {}
        for instance in instances:
            state = instance.get("State", "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1

        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "📊 EC2 Instances Overview",
                "size": "Large",
                "weight": "Bolder",
                "color": "Accent",
            },
            {
                "type": "Container",
                "style": "emphasis",
                "spacing": "Medium",
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
                                        "text": str(len(instances)),
                                        "size": "ExtraLarge",
                                        "weight": "Bolder",
                                        "horizontalAlignment": "Center",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": "Total Instances",
                                        "horizontalAlignment": "Center",
                                        "spacing": "None",
                                        "isSubtle": True,
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
        ]

        # Add state summary if multiple states or not all running
        if len(state_counts) > 1 or "running" not in state_counts:
            state_summary = CardTemplates.create_state_summary(state_counts)
            card_body.append(state_summary)

        # Instance list header
        card_body.append(
            {
                "type": "TextBlock",
                "text": "Instance Details",
                "weight": "Bolder",
                "size": "Medium",
                "spacing": "Large",
            }
        )

        # Sort instances by state (running first) and then by name
        sorted_instances = sorted(
            instances,
            key=lambda x: (
                0 if x.get("State") == "running" else 1,
                x.get("Name", x.get("InstanceId", "")),
            ),
        )

        # Add each instance
        for instance in sorted_instances:
            instance_id = instance.get("InstanceId", "Unknown")
            name = instance.get("Name", instance_id)
            state = instance.get("State", "unknown")
            instance_type = instance.get("InstanceType", "Unknown")
            platform = instance.get("Platform", "Linux")
            ip_address = instance.get("PrivateIpAddress") or instance.get("PublicIpAddress")

            # Create instance container
            instance_container: dict[str, Any] = {
                "type": "Container",
                "separator": True,
                "spacing": "Medium",
                "items": [
                    CardTemplates.create_instance_card(
                        instance_id, name, instance_type, state, platform, ip_address
                    )
                ],
            }

            # Add actions based on state
            actions: list[dict[str, Any]] = []

            if state == "running":
                # For running instances, could add health check button
                # (will be added in Phase 5C)
                pass
            elif state == "stopped":
                # Could add start button
                # (will be added with action handling)
                pass

            if actions:
                instance_container["items"].append(
                    {"type": "ActionSet", "spacing": "Small", "actions": actions}
                )

            card_body.append(instance_container)

        # Global actions
        card_body.append(
            {
                "type": "ActionSet",
                "separator": True,
                "spacing": "Large",
                "actions": [
                    {
                        "type": "Action.Submit",
                        "title": "🔄 Refresh List",
                        "data": {"action": "list_instances"},
                    },
                ],
            }
        )

        return {"type": "AdaptiveCard", "version": "1.5", "body": card_body}
