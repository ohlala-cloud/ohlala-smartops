"""Exec command - Execute commands on EC2 instances via SSM.

This module provides the ExecCommand that executes shell/PowerShell commands
on EC2 instances via AWS Systems Manager with user confirmation.

Phase 5D: SSM Command Execution.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.commands.confirmation import confirmation_manager

logger: Final = logging.getLogger(__name__)


class ExecCommand(BaseCommand):
    """Handler for /exec command - Execute commands on EC2 instances via SSM.

    Executes shell or PowerShell commands on one or more EC2 instances using
    AWS Systems Manager. Requires user confirmation before execution.

    Features:
    - Execute on single or multiple instances
    - Automatic document selection (AWS-RunShellScript or AWS-RunPowerShellScript)
    - Command preprocessing and validation
    - Async tracking with status updates
    - Secure approval workflow

    Example:
        >>> cmd = ExecCommand()
        >>> result = await cmd.execute(
        ...     ["i-1234567890abcdef0", "systemctl status nginx"],
        ...     context
        ... )
        >>> # Returns confirmation card
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "exec"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Execute commands on EC2 instances via SSM"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/exec <instance-id> <command> - Execute command via SSM"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute command execution with confirmation.

        Args:
            args: Command arguments ([instance-ids...] + command).
            context: Execution context containing:
                - user_id: User identifier
                - user_name: User display name
                - mcp_manager: MCPManager instance

        Returns:
            Command result with confirmation card.

        Example:
            >>> result = await cmd.execute(
            ...     ["i-123", "ls -la /var/log"],
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

            # Parse instance IDs and command
            parse_result = self._parse_exec_args(args)

            if not parse_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {parse_result['error']}\n\n" f"Usage: {self.usage}",
                }

            instance_ids = parse_result["instance_ids"]
            command_text = parse_result["command"]

            # Validate instances exist
            validation_result = await self.validate_instances_exist(instance_ids, context)

            if not validation_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {validation_result['error']}",
                }

            instances = validation_result["instances"]

            # Validate instances are running (SSM requires running state)
            filter_result = self.filter_instances_by_state(instances, ["running"])

            if filter_result["invalid_instances"]:
                invalid_list = [
                    f"{inv['id']} ({inv['state']})" for inv in filter_result["invalid_instances"]
                ]
                return {
                    "success": False,
                    "message": f"❌ Some instances cannot execute commands:\n\n"
                    f"{chr(10).join(invalid_list)}\n\n"
                    f"Instances must be in 'running' state for SSM command execution.",
                }

            # Determine document name based on platform
            document_name = self._determine_document_name(instances)

            # Create confirmation request
            description = (
                f"Execute SSM command on {len(instance_ids)} instance(s): "
                f'"{command_text[:50]}{"..." if len(command_text) > 50 else ""}"'
            )

            async def exec_callback(operation: Any) -> dict[str, Any]:
                """Callback to execute SSM command after confirmation."""
                try:
                    # Call MCP send-command tool
                    result = await self.call_mcp_tool(
                        "send-command",
                        {
                            "InstanceIds": operation.resource_ids,
                            "Commands": command_text,
                            "DocumentName": operation.additional_data.get(
                                "document_name", "AWS-RunShellScript"
                            ),
                        },
                        context,
                    )

                    command_id = result.get("command_id", "Unknown")

                    # Create success response card with command ID
                    return {
                        "card": self._create_exec_initiated_card(
                            command_id, len(operation.resource_ids), command_text
                        )
                    }
                except Exception as e:
                    self.logger.error(f"Error executing SSM command: {e}", exc_info=True)
                    raise Exception(f"Failed to execute command: {e!s}") from e

            operation = confirmation_manager.create_confirmation_request(
                operation_type="exec-command",
                resource_type="EC2 Instance",
                resource_ids=instance_ids,
                user_id=user_id,
                user_name=user_name,
                description=description,
                callback=exec_callback,
                additional_data={"command": command_text, "document_name": document_name},
            )

            # Create and return confirmation card
            confirmation_card = self._create_exec_confirmation_card(
                operation, instance_ids, command_text, document_name
            )

            return {
                "success": True,
                "message": "Command execution confirmation required",
                "card": confirmation_card,
            }

        except Exception as e:
            self.logger.error(f"Error in exec command: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to execute command: {e!s}",
                "card": self.create_error_card(
                    "Failed to Execute Command",
                    f"Unable to process command execution request: {e!s}",
                ),
            }

    def _parse_exec_args(self, args: list[str]) -> dict[str, Any]:
        """Parse instance IDs and command from arguments.

        Args:
            args: Command arguments.

        Returns:
            Dictionary with success, instance_ids, command, or error.
        """
        if not args:
            return {"success": False, "error": "Please provide instance ID(s) and command"}

        if len(args) < 2:
            return {
                "success": False,
                "error": "Please provide both instance ID(s) and command to execute",
            }

        # Parse instance IDs (can be multiple)
        instance_ids = self.parse_instance_ids(args)

        if not instance_ids:
            return {"success": False, "error": "No valid instance IDs found"}

        # The rest is the command - find where command starts
        # (after last instance ID)
        command_start_idx = 0
        for i, arg in enumerate(args):
            # If this arg or any part of it looks like instance ID, it's part of IDs
            if arg.startswith("i-") or any(part.startswith("i-") for part in arg.split(",")):
                command_start_idx = i + 1
            else:
                # First non-instance-ID arg is start of command
                command_start_idx = i
                break

        if command_start_idx >= len(args):
            return {"success": False, "error": "No command provided after instance ID(s)"}

        # Join remaining args as command
        command_text = " ".join(args[command_start_idx:])

        if not command_text.strip():
            return {"success": False, "error": "Command cannot be empty"}

        return {"success": True, "instance_ids": instance_ids, "command": command_text}

    def _determine_document_name(self, instances: list[dict[str, Any]]) -> str:
        """Determine SSM document name based on instance platforms.

        Args:
            instances: List of instance dictionaries.

        Returns:
            Document name (AWS-RunShellScript or AWS-RunPowerShellScript).
        """
        # If all Windows, use PowerShell; otherwise use Shell (supports Linux/Unix)
        all_windows = all(inst.get("Platform", "Linux").lower() == "windows" for inst in instances)

        if all_windows:
            return "AWS-RunPowerShellScript"
        return "AWS-RunShellScript"

    def _create_exec_confirmation_card(
        self,
        operation: Any,
        instance_ids: list[str],
        command: str,
        document_name: str,
    ) -> dict[str, Any]:
        """Create confirmation card for SSM command execution.

        Args:
            operation: PendingOperation object.
            instance_ids: List of target instance IDs.
            command: Command to execute.
            document_name: SSM document name.

        Returns:
            Adaptive card dictionary.
        """
        # Truncate long commands for display
        display_command = command if len(command) <= 200 else f"{command[:200]}..."

        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": "⚙️ Execute SSM Command - Confirmation Required",
                "weight": "Bolder",
                "size": "Large",
            },
            {
                "type": "TextBlock",
                "text": f"You are about to execute a command on {len(instance_ids)} instance(s).",
                "wrap": True,
                "spacing": "Small",
            },
            {
                "type": "Container",
                "style": "emphasis",
                "spacing": "Medium",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "Command to Execute:",
                        "weight": "Bolder",
                        "size": "Small",
                    },
                    {
                        "type": "TextBlock",
                        "text": display_command,
                        "wrap": True,
                        "fontType": "Monospace",
                        "spacing": "Small",
                    },
                ],
            },
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": "Document:", "value": document_name},
                    {"title": "Target Instances:", "value": f"{len(instance_ids)} instance(s)"},
                    {
                        "title": "Instance IDs:",
                        "value": ", ".join(instance_ids[:3])
                        + ("..." if len(instance_ids) > 3 else ""),
                    },
                    {"title": "Requested by:", "value": operation.user_name},
                ],
            },
            {
                "type": "TextBlock",
                "text": "⚠️ WARNING: Carefully review the command before confirming. "
                "Commands will be executed with SSM permissions on the target instances.",
                "wrap": True,
                "color": "Warning",
                "spacing": "Medium",
            },
        ]

        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": card_body,
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "✅ Execute Command",
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

    def _create_exec_initiated_card(
        self, command_id: str, instance_count: int, command: str
    ) -> dict[str, Any]:
        """Create card showing command execution initiated.

        Args:
            command_id: SSM command ID.
            instance_count: Number of target instances.
            command: Command that was executed.

        Returns:
            Adaptive card dictionary.
        """
        display_command = command if len(command) <= 100 else f"{command[:100]}..."

        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "Container",
                    "style": "good",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "✅ Command Execution Initiated",
                            "size": "Large",
                            "weight": "Bolder",
                            "color": "Good",
                        },
                        {
                            "type": "TextBlock",
                            "text": f"SSM command sent to {instance_count} instance(s).",
                            "wrap": True,
                            "spacing": "Small",
                        },
                    ],
                },
                {
                    "type": "FactSet",
                    "spacing": "Medium",
                    "facts": [
                        {"title": "Command ID:", "value": command_id},
                        {"title": "Command:", "value": display_command},
                        {"title": "Status:", "value": "Pending execution"},
                    ],
                },
                {
                    "type": "TextBlock",
                    "text": "💡 Use `/commands` to view command status and output.",
                    "wrap": True,
                    "isSubtle": True,
                    "spacing": "Medium",
                    "size": "Small",
                },
            ],
        }
