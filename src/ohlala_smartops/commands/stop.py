"""Stop instances command - Stop running EC2 instances.

This module provides the StopInstanceCommand that stops running EC2 instances
with user confirmation to prevent accidental service interruption.

Phase 5B: Core instance management with confirmation flow.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.commands.confirmation import confirmation_manager

logger: Final = logging.getLogger(__name__)


class StopInstanceCommand(BaseCommand):
    """Handler for /stop command - Stop running EC2 instances.

    Stops EC2 instances with user confirmation. Validates that instances
    exist and are in the running state before requesting confirmation.

    Includes warning about potential service interruption and data loss.

    Example:
        >>> cmd = StopInstanceCommand()
        >>> result = await cmd.execute(["i-1234567890abcdef0"], context)
        >>> # Returns confirmation card with warning
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "stop"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Stop running EC2 instances"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/stop <instance-id> [instance-id ...] - Stop EC2 instances"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute stop instances command with confirmation.

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
                    "message": "❌ Please provide instance ID(s) to stop.\n\n"
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
                return {
                    "success": False,
                    "message": f"❌ Some instances cannot be stopped:\n\n"
                    f"{chr(10).join(invalid_list)}\n\n"
                    f"Instances must be in 'running' state to stop.",
                }

            # Create confirmation request
            description = f"Stop {len(instance_ids)} EC2 instance(s): " f"{', '.join(instance_ids)}"

            async def stop_callback(operation: Any) -> dict[str, Any]:
                """Callback to execute instance stop after confirmation."""
                try:
                    await self.call_mcp_tool(
                        "stop-instances",
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
                                        "text": "⏹️ Instances Stopping",
                                        "size": "Large",
                                        "weight": "Bolder",
                                        "color": "Warning",
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": f"Successfully initiated stop for "
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
                                        "text": "⚠️ Note: Stopping instances will "
                                        "terminate active connections and may result in "
                                        "data loss if applications are not properly shut down.",
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
                    self.logger.error(f"Error stopping instances: {e}", exc_info=True)
                    raise Exception(f"Failed to stop instances: {e!s}") from e

            operation = confirmation_manager.create_confirmation_request(
                operation_type="stop-instances",
                resource_type="EC2 Instance",
                resource_ids=instance_ids,
                user_id=user_id,
                user_name=user_name,
                description=description,
                callback=stop_callback,
            )

            # Create and return confirmation card
            confirmation_card = confirmation_manager.create_confirmation_card(operation)

            return {
                "success": True,
                "message": "Stop instances confirmation required",
                "card": confirmation_card,
            }

        except Exception as e:
            self.logger.error(f"Error in stop instances command: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to stop instances: {e!s}",
                "card": self.create_error_card(
                    "Failed to Stop Instances",
                    f"Unable to process stop request: {e!s}",
                ),
            }
