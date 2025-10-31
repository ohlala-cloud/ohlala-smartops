"""SSM command execution utilities for running commands on EC2 instances.

This module provides high-level utilities for executing commands on EC2 instances
via AWS Systems Manager (SSM). It handles command preprocessing, execution,
status tracking, and result retrieval with automatic throttling.
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import Any, Final

from pydantic import BaseModel, Field

from ohlala_smartops.aws.client import AWSClientWrapper, create_aws_client
from ohlala_smartops.aws.exceptions import TimeoutError, ValidationError
from ohlala_smartops.utils.ssm import preprocess_ssm_commands

logger: Final = logging.getLogger(__name__)


class SSMCommandInvocation(BaseModel):
    """Model representing an SSM command invocation on a specific instance.

    Attributes:
        command_id: SSM command ID.
        instance_id: EC2 instance ID where command was executed.
        status: Command status (Pending, InProgress, Success, Failed, etc.).
        status_details: Detailed status information.
        stdout: Standard output from the command (optional).
        stderr: Standard error from the command (optional).
        response_code: Exit code from the command (optional).
    """

    command_id: str
    instance_id: str
    status: str
    status_details: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    response_code: int | None = None


class SSMCommand(BaseModel):
    """Model representing an SSM command execution request.

    Attributes:
        command_id: Unique command ID assigned by SSM.
        instance_ids: List of instance IDs where command was sent.
        document_name: SSM document name used for execution.
        parameters: Command parameters passed to the document.
        status: Overall command status.
        requested_at: ISO timestamp when command was requested.
    """

    command_id: str
    instance_ids: list[str]
    document_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: str
    requested_at: str | None = None


class SSMCommandManager:
    """Manager for executing and tracking SSM commands on EC2 instances.

    This class provides high-level methods for executing commands via AWS Systems
    Manager, tracking their status, and retrieving results. All operations use
    the AWSClientWrapper for automatic rate limiting and error handling.

    Example:
        >>> manager = SSMCommandManager(region="us-east-1")
        >>> # Execute command on instances
        >>> command = await manager.send_command(
        ...     instance_ids=["i-1234567890abcdef"],
        ...     commands=["echo 'Hello World'"],
        ... )
        >>> # Wait for completion
        >>> invocation = await manager.wait_for_completion(
        ...     command.command_id,
        ...     "i-1234567890abcdef",
        ...     timeout=300,
        ... )
        >>> print(invocation.stdout)
    """

    def __init__(self, region: str | None = None, client: AWSClientWrapper | None = None) -> None:
        """Initialize SSM command manager.

        Args:
            region: AWS region name. If None, uses default from environment/config.
                Defaults to None.
            client: Optional pre-configured AWSClientWrapper. If None, creates a new one.
                Defaults to None.

        Example:
            >>> manager = SSMCommandManager(region="us-west-2")
            >>> # Or with existing client:
            >>> client = create_aws_client("ssm", region="eu-west-1")
            >>> manager = SSMCommandManager(client=client)
        """
        self.region = region
        self.client = client or create_aws_client("ssm", region=region)
        logger.info(f"Initialized SSMCommandManager for region {region or 'default'}")

    async def send_command(
        self,
        instance_ids: Sequence[str],
        commands: str | list[str],
        document_name: str = "AWS-RunShellScript",
        timeout_seconds: int = 3600,
        comment: str | None = None,
    ) -> SSMCommand:
        """Send a command to one or more EC2 instances via SSM.

        The commands are automatically preprocessed using the existing SSM
        preprocessing utilities to fix common issues.

        Args:
            instance_ids: Sequence of EC2 instance IDs to execute command on.
            commands: Command(s) to execute. Can be a string or list of strings.
            document_name: SSM document to use. Defaults to "AWS-RunShellScript".
            timeout_seconds: Command timeout in seconds. Defaults to 3600 (1 hour).
            comment: Optional comment to attach to the command. Defaults to None.

        Returns:
            SSMCommand object with command ID and metadata.

        Raises:
            ValidationError: If instance_ids is empty or commands are invalid.
            SSMError: If AWS API call fails.

        Example:
            >>> # Single command
            >>> cmd = await manager.send_command(
            ...     instance_ids=["i-123"],
            ...     commands="ls -la /var/log",
            ... )
            >>>
            >>> # Multiple commands
            >>> cmd = await manager.send_command(
            ...     instance_ids=["i-123", "i-456"],
            ...     commands=["echo 'Starting'", "ls -la", "echo 'Done'"],
            ... )
        """
        if not instance_ids:
            raise ValidationError("instance_ids cannot be empty", service="ssm")

        # Preprocess commands using existing utilities
        processed_commands = preprocess_ssm_commands(commands)
        if not processed_commands:
            raise ValidationError("commands cannot be empty after preprocessing", service="ssm")

        logger.info(
            f"Sending command to {len(instance_ids)} instance(s): "
            f"{len(processed_commands)} command(s)"
        )

        # Build API parameters
        parameters: dict[str, Any] = {
            "InstanceIds": list(instance_ids),
            "DocumentName": document_name,
            "Parameters": {"commands": processed_commands},
            "TimeoutSeconds": timeout_seconds,
        }

        if comment:
            parameters["Comment"] = comment

        try:
            response = await self.client.call("send_command", **parameters)

            command_data = response["Command"]
            command = SSMCommand(
                command_id=command_data["CommandId"],
                instance_ids=command_data["InstanceIds"],
                document_name=command_data["DocumentName"],
                parameters=command_data.get("Parameters", {}),
                status=command_data["Status"],
                requested_at=(
                    command_data.get("RequestedDateTime", "").isoformat()
                    if command_data.get("RequestedDateTime")
                    else None
                ),
            )

            logger.info(f"Command sent successfully: {command.command_id}")
            return command

        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            raise

    async def get_command_invocation(
        self, command_id: str, instance_id: str
    ) -> SSMCommandInvocation:
        """Get the status and output of a command invocation on a specific instance.

        Args:
            command_id: SSM command ID.
            instance_id: EC2 instance ID.

        Returns:
            SSMCommandInvocation with status and output.

        Raises:
            SSMError: If command invocation not found or API call fails.

        Example:
            >>> invocation = await manager.get_command_invocation(
            ...     "cmd-123abc",
            ...     "i-1234567890abcdef",
            ... )
            >>> print(f"Status: {invocation.status}")
            >>> print(f"Output: {invocation.stdout}")
        """
        logger.debug(f"Getting invocation status: {command_id} on {instance_id}")

        try:
            response = await self.client.call(
                "get_command_invocation", CommandId=command_id, InstanceId=instance_id
            )

            invocation = SSMCommandInvocation(
                command_id=response["CommandId"],
                instance_id=response["InstanceId"],
                status=response["Status"],
                status_details=response.get("StatusDetails"),
                stdout=response.get("StandardOutputContent"),
                stderr=response.get("StandardErrorContent"),
                response_code=response.get("ResponseCode"),
            )

            logger.debug(f"Command {command_id} status: {invocation.status}")
            return invocation

        except Exception as e:
            logger.error(f"Failed to get command invocation: {e}")
            raise

    async def wait_for_completion(
        self,
        command_id: str,
        instance_id: str,
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> SSMCommandInvocation:
        """Wait for a command to complete on a specific instance.

        Polls the command status at regular intervals until it reaches a
        terminal state (Success, Failed, TimedOut, Cancelled) or the timeout expires.

        Args:
            command_id: SSM command ID.
            instance_id: EC2 instance ID.
            timeout: Maximum time to wait in seconds. Defaults to 300 (5 minutes).
            poll_interval: Time between status checks in seconds. Defaults to 5.

        Returns:
            SSMCommandInvocation with final status and output.

        Raises:
            TimeoutError: If command doesn't complete within timeout.
            SSMError: If status check fails.

        Example:
            >>> invocation = await manager.wait_for_completion(
            ...     "cmd-123abc",
            ...     "i-1234567890abcdef",
            ...     timeout=600,
            ... )
            >>> if invocation.status == "Success":
            ...     print(invocation.stdout)
        """
        logger.info(
            f"Waiting for command {command_id} to complete on {instance_id} "
            f"(timeout: {timeout}s)"
        )

        terminal_statuses = {"Success", "Failed", "TimedOut", "Cancelled"}
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(
                    f"Command {command_id} did not complete within {timeout}s",
                    service="ssm",
                    operation="wait_for_completion",
                )

            # Get current status
            invocation = await self.get_command_invocation(command_id, instance_id)

            # Check if terminal state reached
            if invocation.status in terminal_statuses:
                logger.info(f"Command {command_id} completed with status: {invocation.status}")
                return invocation

            # Wait before next poll
            logger.debug(
                f"Command {command_id} status: {invocation.status}, waiting {poll_interval}s..."
            )
            await asyncio.sleep(poll_interval)

    async def list_commands(
        self,
        instance_id: str | None = None,
        command_id: str | None = None,
        max_results: int = 50,
    ) -> list[SSMCommand]:
        """List recent SSM commands with optional filtering.

        Args:
            instance_id: Filter by instance ID. Defaults to None (no filter).
            command_id: Filter by specific command ID. Defaults to None (no filter).
            max_results: Maximum number of results to return. Defaults to 50.

        Returns:
            List of SSMCommand objects.

        Raises:
            SSMError: If API call fails.

        Example:
            >>> # List all recent commands
            >>> commands = await manager.list_commands()
            >>>
            >>> # List commands for specific instance
            >>> commands = await manager.list_commands(instance_id="i-123")
        """
        logger.debug(f"Listing commands (instance={instance_id}, max={max_results})")

        parameters: dict[str, Any] = {"MaxResults": max_results}

        if instance_id:
            parameters["InstanceId"] = instance_id
        if command_id:
            parameters["CommandId"] = command_id

        try:
            response = await self.client.call("list_commands", **parameters)

            commands: list[SSMCommand] = []
            for cmd_data in response.get("Commands", []):
                command = SSMCommand(
                    command_id=cmd_data["CommandId"],
                    instance_ids=cmd_data.get("InstanceIds", []),
                    document_name=cmd_data["DocumentName"],
                    parameters=cmd_data.get("Parameters", {}),
                    status=cmd_data["Status"],
                    requested_at=(
                        cmd_data.get("RequestedDateTime", "").isoformat()
                        if cmd_data.get("RequestedDateTime")
                        else None
                    ),
                )
                commands.append(command)

            logger.info(f"Listed {len(commands)} command(s)")
            return commands

        except Exception as e:
            logger.error(f"Failed to list commands: {e}")
            raise

    async def cancel_command(
        self, command_id: str, instance_ids: Sequence[str] | None = None
    ) -> None:
        """Cancel a running SSM command.

        Args:
            command_id: SSM command ID to cancel.
            instance_ids: Optional list of specific instances to cancel on.
                If None, cancels on all instances. Defaults to None.

        Raises:
            SSMError: If API call fails.

        Example:
            >>> # Cancel on all instances
            >>> await manager.cancel_command("cmd-123abc")
            >>>
            >>> # Cancel on specific instances
            >>> await manager.cancel_command("cmd-123abc", ["i-123", "i-456"])
        """
        logger.warning(f"Cancelling command {command_id}")

        parameters: dict[str, Any] = {"CommandId": command_id}
        if instance_ids:
            parameters["InstanceIds"] = list(instance_ids)

        try:
            await self.client.call("cancel_command", **parameters)
            logger.info(f"Command {command_id} cancelled successfully")

        except Exception as e:
            logger.error(f"Failed to cancel command: {e}")
            raise
