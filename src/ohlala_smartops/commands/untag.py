"""Untag command - Remove tags from EC2 instances.

This module provides the UntagCommand that removes tags from EC2 instances
with user confirmation to ensure intentional actions.

Phase 5E: Resource Tagging.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.commands.confirmation import confirmation_manager

logger: Final = logging.getLogger(__name__)


class UntagCommand(BaseCommand):
    """Handler for /untag command - Remove tags from EC2 instances.

    Removes tags from EC2 instances with user confirmation. Tags are removed
    by key - the values are not required.

    Example:
        >>> cmd = UntagCommand()
        >>> result = await cmd.execute(
        ...     ["i-1234567890abcdef0", "Environment", "TempTag"],
        ...     context
        ... )
        >>> # Returns confirmation card
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "untag"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Remove tags from EC2 instances"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/untag <instance-id> <tag-key> [tag-key...] - Remove tags"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute untag command with confirmation.

        Args:
            args: Command arguments (instance IDs and tag keys).
            context: Execution context containing:
                - user_id: User identifier
                - user_name: User display name
                - mcp_manager: MCPManager instance

        Returns:
            Command result with confirmation card.

        Example:
            >>> result = await cmd.execute(
            ...     ["i-123", "Environment", "TempTag"],
            ...     context
            ... )
            >>> print(result["card"])  # Confirmation card
        """
        try:
            # Get user info
            user_id = context.get("user_id")
            user_name = context.get("user_name", "Unknown User")

            if not user_id:
                return {
                    "success": False,
                    "message": "❌ Unable to identify user for confirmation",
                }

            # Parse arguments
            parse_result = self._parse_untag_args(args)

            if not parse_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {parse_result['error']}\n\n" f"Usage: {self.usage}",
                }

            instance_ids = parse_result["instance_ids"]
            tag_keys = parse_result["tag_keys"]

            # Validate instances exist
            validation_result = await self.validate_instances_exist(instance_ids, context)

            if not validation_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {validation_result['error']}",
                }

            instances = validation_result["instances"]

            # Get current tags for display
            current_tags = await self._get_current_tags(instance_ids, context)

            # Create confirmation request
            keys_summary = ", ".join(tag_keys)
            description = (
                f"Remove {len(tag_keys)} tag(s) from "
                f"{len(instance_ids)} instance(s): {keys_summary}"
            )

            async def untag_callback(operation: Any) -> dict[str, Any]:
                """Callback to execute untagging after confirmation."""
                try:
                    await self.call_mcp_tool(
                        "remove-tags",
                        {
                            "ResourceIds": operation.resource_ids,
                            "TagKeys": operation.additional_data["tag_keys"],
                        },
                        context,
                    )

                    # Create success response card
                    return {
                        "card": self.create_success_card(
                            "Tags Removed",
                            f"Successfully removed {len(tag_keys)} tag(s) from "
                            f"{len(operation.resource_ids)} instance(s).\n\n"
                            f"Removed: {keys_summary}",
                        )
                    }
                except Exception as e:
                    self.logger.error(f"Error removing tags: {e}", exc_info=True)
                    raise Exception(f"Failed to remove tags: {e!s}") from e

            operation = confirmation_manager.create_confirmation_request(
                operation_type="remove-tags",
                resource_type="EC2 Instance",
                resource_ids=instance_ids,
                user_id=user_id,
                user_name=user_name,
                description=description,
                callback=untag_callback,
                additional_data={"tag_keys": tag_keys, "current_tags": current_tags},
            )

            # Create and return confirmation card
            confirmation_card = self._create_untag_confirmation_card(
                operation, instances, tag_keys, current_tags
            )

            return {
                "success": True,
                "message": "Untag confirmation required",
                "card": confirmation_card,
            }

        except Exception as e:
            self.logger.error(f"Error in untag command: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to remove tags: {e!s}",
                "card": self.create_error_card(
                    "Failed to Remove Tags",
                    f"Unable to process untag request: {e!s}",
                ),
            }

    def _parse_untag_args(self, args: list[str]) -> dict[str, Any]:
        """Parse instance IDs and tag keys from arguments.

        Args:
            args: Command arguments.

        Returns:
            Dictionary with success, instance_ids, tag_keys, or error.
        """
        if not args:
            return {"success": False, "error": "Please provide instance ID(s) and tag key(s)"}

        if len(args) < 2:
            return {
                "success": False,
                "error": "Please provide both instance ID(s) and tag key(s)",
            }

        # Parse instance IDs
        instance_ids = self.parse_instance_ids(args)

        if not instance_ids:
            return {"success": False, "error": "No valid instance IDs found"}

        # Parse tag keys (any arg that's not an instance ID)
        tag_keys: list[str] = []
        for arg in args:
            # Skip if it's an instance ID or part of instance ID list
            if arg.startswith("i-") or "," in arg:
                continue

            # Treat as tag key
            tag_key = arg.strip()
            if tag_key:
                # Check for aws: prefix
                if tag_key.lower().startswith("aws:"):
                    return {
                        "success": False,
                        "error": f"Cannot remove AWS system tag: {tag_key}",
                    }
                tag_keys.append(tag_key)

        if not tag_keys:
            return {"success": False, "error": "No valid tag keys found"}

        return {"success": True, "instance_ids": instance_ids, "tag_keys": tag_keys}

    async def _get_current_tags(
        self, instance_ids: list[str], context: dict[str, Any]
    ) -> dict[str, dict[str, str]]:
        """Get current tags for instances.

        Args:
            instance_ids: List of instance IDs.
            context: Execution context.

        Returns:
            Dictionary mapping instance IDs to their current tags.
        """
        try:
            result = await self.call_mcp_tool(
                "get-resource-tags",
                {"ResourceIds": instance_ids},
                context,
            )
            tags = result.get("tags", {})
            return tags if isinstance(tags, dict) else {}
        except Exception as e:
            self.logger.warning(f"Could not retrieve current tags: {e}")
            return {}

    def _create_untag_confirmation_card(
        self,
        operation: Any,
        instances: list[dict[str, Any]],
        tag_keys: list[str],
        current_tags: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        """Create confirmation card for untagging operation.

        Args:
            operation: PendingOperation object.
            instances: List of instance dictionaries.
            tag_keys: Tag keys to remove.
            current_tags: Current tags on instances.

        Returns:
            Adaptive card dictionary.
        """
        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "🏷️ Remove Tags - Confirmation Required",
                "weight": "Bolder",
                "size": "Large",
            },
            {
                "type": "TextBlock",
                "text": f"You are about to remove {len(tag_keys)} tag(s) from "
                f"{len(instances)} instance(s).",
                "wrap": True,
                "spacing": "Small",
            },
        ]

        # Show tags to remove
        card_body.append(
            {
                "type": "Container",
                "style": "warning",
                "spacing": "Medium",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Tags to Remove:",
                        "weight": "Bolder",
                        "size": "Small",
                    },
                    {
                        "type": "TextBlock",
                        "text": ", ".join(tag_keys),
                        "wrap": True,
                        "spacing": "Small",
                    },
                ],
            }
        )

        # Show target instances
        instance_list = []
        for inst in instances[:5]:  # Show first 5
            inst_id = inst.get("InstanceId", "Unknown")
            inst_name = inst.get("Name", inst_id)
            instance_list.append(f"• {inst_name} ({inst_id})")

        if len(instances) > 5:
            instance_list.append(f"... and {len(instances) - 5} more")

        card_body.append(
            {
                "type": "Container",
                "spacing": "Medium",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Target Instances:",
                        "weight": "Bolder",
                        "size": "Small",
                    },
                    {
                        "type": "TextBlock",
                        "text": "\n".join(instance_list),
                        "wrap": True,
                        "spacing": "Small",
                    },
                ],
            }
        )

        # Show which tags will be removed from first instance if available
        if current_tags and instances:
            first_instance_id = instances[0].get("InstanceId")
            if first_instance_id in current_tags:
                inst_tags = current_tags[first_instance_id]
                # Find which requested keys exist on this instance
                existing_keys = [k for k in tag_keys if k in inst_tags]
                if existing_keys:
                    card_body.append(
                        {
                            "type": "Container",
                            "spacing": "Medium",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": (
                                        f"Tags on {instances[0].get('Name', first_instance_id)} "
                                        "that will be removed:"
                                    ),
                                    "weight": "Bolder",
                                    "size": "Small",
                                },
                                {
                                    "type": "FactSet",
                                    "facts": [
                                        {"title": k, "value": inst_tags[k]} for k in existing_keys
                                    ],
                                    "spacing": "Small",
                                },
                            ],
                        }
                    )

        # Operation info
        card_body.append(
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": "Operation:", "value": "Remove Tags"},
                    {"title": "Instances:", "value": str(len(instances))},
                    {"title": "Tag Keys:", "value": str(len(tag_keys))},
                    {"title": "Requested by:", "value": operation.user_name},
                ],
            }
        )

        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": card_body,
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "✅ Confirm",
                    "style": "positive",
                    "data": {
                        "action": "confirm_operation",
                        "operation_id": operation.id,
                    },
                },
                {
                    "type": "Action.Submit",
                    "title": "❌ Cancel",
                    "style": "destructive",
                    "data": {"action": "cancel_operation", "operation_id": operation.id},
                },
            ],
            "msteams": {"width": "Full"},
        }
