"""Reboot instances command - Reboot running EC2 instances.

This module provides the RebootInstanceCommand that reboots running EC2 instances
with user confirmation to prevent accidental service interruption.

Phase 5B: Core instance management with confirmation flow.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.commands.confirmation import confirmation_manager

logger: Final = logging.getLogger(__name__)


class RebootInstanceCommand(BaseCommand):
    """Handler for /reboot command - Reboot running EC2 instances.

    Reboots EC2 instances with user confirmation. Validates that instances
    exist and are in the running state before requesting confirmation.

    Includes warning about temporary connection interruption.

    Example:
        >>> cmd = RebootInstanceCommand()
        >>> result = await cmd.execute(["i-1234567890abcdef0"], context)
        >>> # Returns confirmation card with warning
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "reboot"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Reboot running EC2 instances"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/reboot <instance-id> [instance-id ...] - Reboot EC2 instances"

    async def execute(  # noqa: PLR0911
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute reboot instances command with confirmation.

        Args:
            args: Command arguments (instance IDs).
            context: Execution context containing:
                - user_id: User identifier
                - user_name: User display name
                - mcp_manager: MCPManager instance

        Returns:
            Command result with confirmation card.

        Example:
            >>> result = await cmd.execute(["i-123", "i-456"], context)
            >>> print(result["card"])  # Confirmation card with warning
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

            # Parse instance IDs
            instance_ids = self.parse_instance_ids(args)

            if not instance_ids:
                return {
                    "success": False,
                    "message": "❌ Please provide instance ID(s) to reboot.\n\n"
                    f"Usage: {self.usage}",
                }

            # Validate instances exist
            validation_result = await self.validate_instances_exist(instance_ids, context)

            if not validation_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {validation_result['error']}",
                }

            instances = validation_result["instances"]

            # Check if instances are in running state
            filter_result = self.filter_instances_by_state(instances, ["running"])

            if filter_result["invalid_instances"]:
                invalid_list = [
                    f"{inv['id']} ({inv['state']})" for inv in filter_result["invalid_instances"]
                ]
                # Special message for stopped instances
                stopped_ids = [
                    inv["id"]
                    for inv in filter_result["invalid_instances"]
                    if inv["state"] == "stopped"
                ]
                if stopped_ids:
                    return {
                        "success": False,
                        "message": f"❌ Cannot reboot stopped instances:\n\n"
                        f"{chr(10).join(stopped_ids)}\n\n"
                        f"Please start them first using /start.",
                    }
                return {
                    "success": False,
                    "message": f"❌ Some instances cannot be rebooted:\n\n"
                    f"{chr(10).join(invalid_list)}\n\n"
                    f"Instances must be in 'running' state to reboot.",
                }

            # Create confirmation request
            description = (
                f"Reboot {len(instance_ids)} EC2 instance(s): " f"{', '.join(instance_ids)}"
            )

            async def reboot_callback(operation: Any) -> dict[str, Any]:
                """Callback to execute instance reboot after confirmation."""
                try:
                    await self.call_mcp_tool(
                        "reboot-instances",
                        {"InstanceIds": operation.resource_ids},
                        context,
                    )

                    # Create success response card with warning
                    card = {
                        "type": "AdaptiveCard",
                        "version": "1.5",
                        "body": [
                            {
                                "type": "Container",
                                "style": "warning",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "🔄 Instances Rebooting",
                                        "size": "Large",
                                        "weight": "Bolder",
                                        "color": "Warning",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": f"Successfully initiated reboot for "
                                        f"{len(operation.resource_ids)} instance(s).",
                                        "wrap": True,
                                        "spacing": "Small",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": f"Instance IDs: "
                                        f"{', '.join(operation.resource_ids)}",
                                        "wrap": True,
                                        "spacing": "Small",
                                        "size": "Small",
                                        "isSubtle": True,
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": "⚠️ Note: Rebooting will temporarily "
                                        "disconnect all active connections. The instances "
                                        "will restart automatically.",
                                        "wrap": True,
                                        "spacing": "Small",
                                        "size": "Small",
                                        "color": "Warning",
                                    },
                                ],
                            }
                        ],
                    }

                    return {"card": card}
                except Exception as e:
                    self.logger.error(f"Error rebooting instances: {e}", exc_info=True)
                    raise Exception(f"Failed to reboot instances: {e!s}") from e

            operation = confirmation_manager.create_confirmation_request(
                operation_type="reboot-instances",
                resource_type="EC2 Instance",
                resource_ids=instance_ids,
                user_id=user_id,
                user_name=user_name,
                description=description,
                callback=reboot_callback,
            )

            # Create and return confirmation card
            confirmation_card = confirmation_manager.create_confirmation_card(operation)

            return {
                "success": True,
                "message": "Reboot instances confirmation required",
                "card": confirmation_card,
            }

        except Exception as e:
            self.logger.error(f"Error in reboot instances command: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to reboot instances: {e!s}",
                "card": self.create_error_card(
                    "Failed to Reboot Instances",
                    f"Unable to process reboot request: {e!s}",
                ),
            }
