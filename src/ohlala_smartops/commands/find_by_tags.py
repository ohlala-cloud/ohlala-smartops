"""Find by tags command - Search for instances by tag criteria.

This module provides the FindByTagsCommand that searches for EC2 instances
matching specified tag filters.

Phase 5E: Resource Tagging.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand

logger: Final = logging.getLogger(__name__)


class FindByTagsCommand(BaseCommand):
    """Handler for /find-tags command - Find instances by tag criteria.

    Searches for EC2 instances that match specified tag filters. Supports
    searching by tag key only or by key=value pairs. All specified tags
    must match (AND logic).

    Example:
        >>> cmd = FindByTagsCommand()
        >>> result = await cmd.execute(["Environment=Production"], context)
        >>> print(result["card"])  # List of matching instances
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "find-tags"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Find EC2 instances by tag criteria"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/find-tags <key=value> [key=value...] - Find instances by tags"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute find-tags command.

        Args:
            args: Command arguments (tag filters).
            context: Execution context containing:
                - mcp_manager: MCPManager instance

        Returns:
            Command result with card showing matching instances.

        Example:
            >>> result = await cmd.execute(["Environment=Production"], context)
            >>> if result["success"]:
            ...     print("Found matching instances")
        """
        try:
            # Parse tag filters
            parse_result = self._parse_tag_filters(args)

            if not parse_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {parse_result['error']}\n\n" f"Usage: {self.usage}",
                }

            tag_filters = parse_result["tag_filters"]

            # Search for instances by tags
            try:
                matching_instances = await self._find_instances_by_tags(tag_filters, context)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to search instances: {e!s}",
                    "card": self.create_error_card(
                        "Search Failed",
                        f"Unable to search for instances by tags. This may be because:\n\n"
                        f"• Tag search service is not available\n"
                        f"• You don't have permissions to search tags\n\n"
                        f"Error: {e!s}",
                    ),
                }

            # Build results card
            card = self._build_results_card(tag_filters, matching_instances)

            filter_summary = ", ".join([f"{k}={v}" if v else k for k, v in tag_filters.items()])
            count_msg = f"Found {len(matching_instances)} instance(s) matching"
            return {
                "success": True,
                "message": f"{count_msg}: {filter_summary}",
                "card": card,
            }

        except Exception as e:
            self.logger.error(f"Error finding instances by tags: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to find instances: {e!s}",
                "card": self.create_error_card(
                    "Failed to Find Instances",
                    f"Unable to search by tags: {e!s}",
                ),
            }

    def _parse_tag_filters(self, args: list[str]) -> dict[str, Any]:
        """Parse tag filters from arguments.

        Args:
            args: Command arguments.

        Returns:
            Dictionary with success, tag_filters (dict), or error.
        """
        if not args:
            return {"success": False, "error": "Please provide tag filter(s)"}

        tag_filters: dict[str, str | None] = {}

        for arg in args:
            # Parse as key=value or just key
            if "=" in arg:
                try:
                    key, value = arg.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    if not key:
                        return {"success": False, "error": "Tag key cannot be empty"}

                    tag_filters[key] = value
                except ValueError:
                    return {"success": False, "error": f"Invalid tag filter format: {arg}"}
            else:
                # Just a key (search for any instance with this tag)
                key = arg.strip()
                if not key:
                    continue
                tag_filters[key] = None  # None means any value

        if not tag_filters:
            return {"success": False, "error": "No valid tag filters found"}

        return {"success": True, "tag_filters": tag_filters}

    async def _find_instances_by_tags(
        self, tag_filters: dict[str, str | None], context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Find instances matching tag filters.

        Args:
            tag_filters: Dictionary of tag key to value (None means any value).
            context: Execution context.

        Returns:
            List of matching instance dictionaries.
        """
        # First get all instances
        result = await self.call_mcp_tool("list-instances", {}, context)
        all_instances = result.get("instances", [])

        if not all_instances:
            return []

        # Filter instances by tags
        matching_instances: list[dict[str, Any]] = []

        for instance in all_instances:
            instance_tags = instance.get("Tags", {})

            if not isinstance(instance_tags, dict):
                continue

            # Check if all filters match (AND logic)
            matches = True
            for filter_key, filter_value in tag_filters.items():
                if filter_key not in instance_tags:
                    matches = False
                    break

                # If filter_value is None, just check key exists
                # Check exact value match if filter_value is provided
                if filter_value is not None and instance_tags[filter_key] != filter_value:
                    matches = False
                    break

            if matches:
                matching_instances.append(instance)

        return matching_instances

    def _build_results_card(
        self, tag_filters: dict[str, str | None], instances: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Build results card showing matching instances.

        Args:
            tag_filters: Tag filters used for search.
            instances: Matching instances.

        Returns:
            Adaptive card dictionary.
        """
        # Build filter description
        filter_items = []
        for k, v in tag_filters.items():
            if v is None:
                filter_items.append(f"{k}=*")
            else:
                filter_items.append(f"{k}={v}")

        filter_text = ", ".join(filter_items)

        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "🔍 Find Instances by Tags",
                "size": "Large",
                "weight": "Bolder",
                "color": "Accent",
            },
            {
                "type": "TextBlock",
                "text": f"Search Criteria: {filter_text}",
                "isSubtle": True,
                "spacing": "Small",
            },
        ]

        if not instances:
            card_body.append(
                {
                    "type": "Container",
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "No instances found matching the criteria.",
                            "wrap": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": "💡 Try different tag filters or check your tag spelling.",
                            "wrap": True,
                            "size": "Small",
                            "spacing": "Small",
                        },
                    ],
                }
            )
        else:
            card_body.append(
                {
                    "type": "TextBlock",
                    "text": f"Found {len(instances)} matching instance(s)",
                    "weight": "Bolder",
                    "spacing": "Medium",
                }
            )

            # Show instances (similar to /list command)
            for instance in instances[:10]:  # Limit to 10
                instance_id = instance.get("InstanceId", "Unknown")
                name = instance.get("Name", instance_id)
                state = instance.get("State", "unknown")
                instance_type = instance.get("InstanceType", "Unknown")
                private_ip = instance.get("PrivateIpAddress", "N/A")

                # Determine state color
                state_color = "Good" if state == "running" else "Attention"

                card_body.append(
                    {
                        "type": "Container",
                        "separator": True,
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
                                                "text": name,
                                                "weight": "Bolder",
                                            },
                                            {
                                                "type": "TextBlock",
                                                "text": f"{instance_type} • {private_ip}",
                                                "isSubtle": True,
                                                "spacing": "None",
                                                "size": "Small",
                                            },
                                        ],
                                    },
                                    {
                                        "type": "Column",
                                        "width": "auto",
                                        "items": [
                                            {
                                                "type": "TextBlock",
                                                "text": state.upper(),
                                                "color": state_color,
                                                "weight": "Bolder",
                                                "horizontalAlignment": "Right",
                                            },
                                        ],
                                    },
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": f"ID: {instance_id}",
                                "size": "Small",
                                "isSubtle": True,
                                "spacing": "Small",
                            },
                        ],
                    }
                )

            if len(instances) > 10:
                card_body.append(
                    {
                        "type": "TextBlock",
                        "text": f"... and {len(instances) - 10} more instance(s)",
                        "isSubtle": True,
                        "spacing": "Small",
                    }
                )

        return {"type": "AdaptiveCard", "version": "1.5", "body": card_body}
