"""Start instances command - Start stopped EC2 instances.

This module provides the StartInstanceCommand that starts stopped EC2 instances
with user confirmation to ensure intentional actions.

Phase 5B: Core instance management with confirmation flow.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.commands.confirmation import confirmation_manager

logger: Final = logging.getLogger(__name__)


class StartInstanceCommand(BaseCommand):
    """Handler for /start command - Start stopped EC2 instances.

    Starts EC2 instances with user confirmation. Validates that instances
    exist and are in the stopped state before requesting confirmation.

    Example:
        >>> cmd = StartInstanceCommand()
        >>> result = await cmd.execute(["i-1234567890abcdef0"], context)
        >>> # Returns confirmation card
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "start"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Start stopped EC2 instances"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/start <instance-id> [instance-id ...] - Start EC2 instances"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute start instances command with confirmation.

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

            # Parse instance IDs
            instance_ids = self.parse_instance_ids(args)

            if not instance_ids:
                return {
                    "success": False,
                    "message": "❌ Please provide instance ID(s) to start.\n\n"
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

            # Check if instances are in stopped state
            filter_result = self.filter_instances_by_state(instances, ["stopped"])

            if filter_result["invalid_instances"]:
                invalid_list = [
                    f"{inv['id']} ({inv['state']})" for inv in filter_result["invalid_instances"]
                ]
                return {
                    "success": False,
                    "message": f"❌ Some instances cannot be started:\n\n"
                    f"{chr(10).join(invalid_list)}\n\n"
                    f"Instances must be in 'stopped' state to start.",
                }

            # Create confirmation request
            description = (
                f"Start {len(instance_ids)} EC2 instance(s): " f"{', '.join(instance_ids)}"
            )

            async def start_callback(operation: Any) -> dict[str, Any]:
                """Callback to execute instance start after confirmation."""
                try:
                    await self.call_mcp_tool(
                        "start-instances",
                        {"InstanceIds": operation.resource_ids},
                        context,
                    )

                    # Create success response card
                    return {
                        "card": self.create_success_card(
                            "Instances Starting",
                            f"Successfully initiated start for "
                            f"{len(operation.resource_ids)} instance(s).\n\n"
                            f"Instance IDs: {', '.join(operation.resource_ids)}",
                        )
                    }
                except Exception as e:
                    self.logger.error(f"Error starting instances: {e}", exc_info=True)
                    raise Exception(f"Failed to start instances: {e!s}") from e

            operation = confirmation_manager.create_confirmation_request(
                operation_type="start-instances",
                resource_type="EC2 Instance",
                resource_ids=instance_ids,
                user_id=user_id,
                user_name=user_name,
                description=description,
                callback=start_callback,
            )

            # Create and return confirmation card
            confirmation_card = confirmation_manager.create_confirmation_card(operation)

            return {
                "success": True,
                "message": "Start instances confirmation required",
                "card": confirmation_card,
            }

        except Exception as e:
            self.logger.error(f"Error in start instances command: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to start instances: {e!s}",
                "card": self.create_error_card(
                    "Failed to Start Instances",
                    f"Unable to process start request: {e!s}",
                ),
            }
