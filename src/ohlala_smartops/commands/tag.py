"""Tag command - Add or update tags on EC2 instances.

This module provides the TagCommand that adds or updates tags on EC2 instances
with user confirmation to ensure intentional actions.

Phase 5E: Resource Tagging.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.commands.confirmation import confirmation_manager

logger: Final = logging.getLogger(__name__)


class TagCommand(BaseCommand):
    """Handler for /tag command - Add or update tags on EC2 instances.

    Adds or updates tags on EC2 instances with user confirmation. Validates
    tag keys and values according to AWS requirements.

    Tag Format Rules:
    - Tag keys: 1-128 characters
    - Tag values: 0-256 characters
    - Cannot start with "aws:"
    - Allowed characters: letters, numbers, spaces, +=._-:/@
    - Maximum 50 tags per resource

    Example:
        >>> cmd = TagCommand()
        >>> result = await cmd.execute(
        ...     ["i-1234567890abcdef0", "Environment=Production"],
        ...     context
        ... )
        >>> # Returns confirmation card
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "tag"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Add or update tags on EC2 instances"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/tag <instance-id> <key=value> [key=value...] - Add/update tags"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute tag command with confirmation.

        Args:
            args: Command arguments (instance IDs and tag key=value pairs).
            context: Execution context containing:
                - user_id: User identifier
                - user_name: User display name
                - mcp_manager: MCPManager instance

        Returns:
            Command result with confirmation card.

        Example:
            >>> result = await cmd.execute(
            ...     ["i-123", "Environment=Production", "Team=DevOps"],
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
            parse_result = self._parse_tag_args(args)

            if not parse_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {parse_result['error']}\n\n" f"Usage: {self.usage}",
                }

            instance_ids = parse_result["instance_ids"]
            tags = parse_result["tags"]

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
            tag_summary = ", ".join([f"{k}={v}" for k, v in tags.items()])
            description = (
                f"Add/update {len(tags)} tag(s) on {len(instance_ids)} instance(s): {tag_summary}"
            )

            async def tag_callback(operation: Any) -> dict[str, Any]:
                """Callback to execute tagging after confirmation."""
                try:
                    await self.call_mcp_tool(
                        "tag-resources",
                        {
                            "ResourceIds": operation.resource_ids,
                            "Tags": operation.additional_data["tags"],
                        },
                        context,
                    )

                    # Create success response card
                    success_msg = (
                        f"Successfully updated tags on "
                        f"{len(operation.resource_ids)} instance(s).\n\n"
                        f"Tags: {tag_summary}"
                    )
                    return {"card": self.create_success_card("Tags Updated", success_msg)}
                except Exception as e:
                    self.logger.error(f"Error tagging instances: {e}", exc_info=True)
                    raise Exception(f"Failed to tag instances: {e!s}") from e

            operation = confirmation_manager.create_confirmation_request(
                operation_type="tag-resources",
                resource_type="EC2 Instance",
                resource_ids=instance_ids,
                user_id=user_id,
                user_name=user_name,
                description=description,
                callback=tag_callback,
                additional_data={"tags": tags, "current_tags": current_tags},
            )

            # Create and return confirmation card
            confirmation_card = self._create_tag_confirmation_card(
                operation, instances, tags, current_tags
            )

            return {
                "success": True,
                "message": "Tag confirmation required",
                "card": confirmation_card,
            }

        except Exception as e:
            self.logger.error(f"Error in tag command: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to tag instances: {e!s}",
                "card": self.create_error_card(
                    "Failed to Tag Instances",
                    f"Unable to process tag request: {e!s}",
                ),
            }

    def _parse_tag_args(self, args: list[str]) -> dict[str, Any]:  # noqa: PLR0911, PLR0912
        """Parse instance IDs and tags from arguments.

        Args:
            args: Command arguments.

        Returns:
            Dictionary with success, instance_ids, tags, or error.
        """
        if not args:
            return {"success": False, "error": "Please provide instance ID(s) and tag(s)"}

        if len(args) < 2:
            return {"success": False, "error": "Please provide both instance ID(s) and tag(s)"}

        # Parse instance IDs
        instance_ids = self.parse_instance_ids(args)

        if not instance_ids:
            return {"success": False, "error": "No valid instance IDs found"}

        # Parse tags (key=value format)
        tags: dict[str, str] = {}
        for arg in args:
            # Skip if it's an instance ID
            if arg.startswith("i-") or "," in arg:
                continue

            # Try to parse as key=value
            if "=" in arg:
                try:
                    key, value = arg.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Validate key
                    if not key:
                        return {"success": False, "error": "Tag key cannot be empty"}

                    if len(key) > 128:
                        return {
                            "success": False,
                            "error": f"Tag key too long: {key} (max 128 characters)",
                        }

                    if key.lower().startswith("aws:"):
                        return {
                            "success": False,
                            "error": f"Tag key cannot start with 'aws:': {key}",
                        }

                    # Validate value
                    if len(value) > 256:
                        return {
                            "success": False,
                            "error": f"Tag value too long for key {key} (max 256 characters)",
                        }

                    tags[key] = value
                except ValueError:
                    continue

        if not tags:
            return {"success": False, "error": "No valid tags found (format: key=value)"}

        if len(tags) > 50:
            return {
                "success": False,
                "error": f"Too many tags ({len(tags)}). Maximum is 50 tags per resource.",
            }

        return {"success": True, "instance_ids": instance_ids, "tags": tags}

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

    def _create_tag_confirmation_card(
        self,
        operation: Any,
        instances: list[dict[str, Any]],
        new_tags: dict[str, str],
        current_tags: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        """Create confirmation card for tagging operation.

        Args:
            operation: PendingOperation object.
            instances: List of instance dictionaries.
            new_tags: New tags to add/update.
            current_tags: Current tags on instances.

        Returns:
            Adaptive card dictionary.
        """
        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "🏷️ Add/Update Tags - Confirmation Required",
                "weight": "Bolder",
                "size": "Large",
            },
            {
                "type": "TextBlock",
                "text": f"You are about to add/update tags on {len(instances)} instance(s).",
                "wrap": True,
                "spacing": "Small",
            },
        ]

        # Show new tags
        card_body.append(
            {
                "type": "Container",
                "style": "emphasis",
                "spacing": "Medium",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Tags to Add/Update:",
                        "weight": "Bolder",
                        "size": "Small",
                    },
                    {
                        "type": "FactSet",
                        "facts": [{"title": k, "value": v} for k, v in new_tags.items()],
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

        # Show current tags for first instance if available
        if current_tags and instances:
            first_instance_id = instances[0].get("InstanceId")
            if first_instance_id and isinstance(first_instance_id, str):
                first_tags = current_tags.get(first_instance_id)
            else:
                first_tags = None
            if first_tags:
                card_body.append(
                    {
                        "type": "Container",
                        "spacing": "Medium",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": (
                                    f"Current Tags on "
                                    f"{instances[0].get('Name', first_instance_id)}:"
                                ),
                                "weight": "Bolder",
                                "size": "Small",
                            },
                            {
                                "type": "FactSet",
                                "facts": [{"title": k, "value": v} for k, v in first_tags.items()],
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
                    {"title": "Operation:", "value": "Add/Update Tags"},
                    {"title": "Instances:", "value": str(len(instances))},
                    {"title": "Tags:", "value": str(len(new_tags))},
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
