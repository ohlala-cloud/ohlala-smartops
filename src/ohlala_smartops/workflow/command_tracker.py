"""Async SSM command tracking with polling and workflow coordination.

This module provides AsyncCommandTracker for monitoring SSM command execution,
handling multi-instance workflows, and coordinating command completion.

Phase 3C: Core command tracking implementation without Bot Framework dependencies.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from ohlala_smartops.mcp.manager import MCPManager
from ohlala_smartops.models.command_tracking import (
    CommandTrackingInfo,
    SSMCommandStatus,
    WorkflowInfo,
)

logger: Final = logging.getLogger(__name__)


class CommandCompletionCallback(Protocol):
    """Protocol for command completion notifications.

    This protocol decouples AsyncCommandTracker from the notification mechanism.
    Implementations handle how to notify users (Teams, CLI, etc.).
    """

    async def on_command_completed(
        self,
        tracking_info: CommandTrackingInfo,
        workflow_info: WorkflowInfo | None = None,
    ) -> None:
        """Called when a command completes.

        Args:
            tracking_info: Command tracking information.
            workflow_info: Optional workflow info if part of multi-instance operation.
        """
        ...

    async def on_workflow_completed(self, workflow_info: WorkflowInfo) -> None:
        """Called when an entire workflow completes.

        Args:
            workflow_info: Workflow information with all results.
        """
        ...


class AsyncCommandTracker:
    """Tracks SSM command execution with polling and workflow coordination.

    Phase 3C simplified implementation:
    - Polls SSM for command status using MCP Manager
    - Exponential backoff (3s → 10s)
    - Timeout handling (15 minutes default)
    - Completion callbacks for decoupled notifications
    - No direct Teams/Bedrock dependencies

    Attributes:
        mcp_manager: MCP Manager for get-command-invocation calls.
        completion_callback: Callback for completion notifications.
        active_commands: Dict of command_id -> CommandTrackingInfo.
        active_workflows: Dict of workflow_id -> WorkflowInfo.

    Example:
        >>> manager = MCPManager()
        >>> await manager.initialize()
        >>> tracker = AsyncCommandTracker(manager)
        >>> await tracker.start()
        >>> # Track a command
        >>> info = tracker.track_command(
        ...     command_id="cmd-123",
        ...     instance_id="i-abc123",
        ...     document_name="AWS-RunShellScript"
        ... )
        >>> await tracker.stop()

    Note:
        Phase 3C: Core functionality. LLM analysis and advanced features in Phase 4.
    """

    def __init__(
        self,
        mcp_manager: MCPManager,
        completion_callback: CommandCompletionCallback | None = None,
    ) -> None:
        """Initialize AsyncCommandTracker.

        Args:
            mcp_manager: MCP Manager for SSM API calls.
            completion_callback: Optional callback for notifications.
        """
        self.mcp_manager = mcp_manager
        self.completion_callback = completion_callback
        self.active_commands: dict[str, CommandTrackingInfo] = {}
        self.active_workflows: dict[str, WorkflowInfo] = {}
        self._polling_task: asyncio.Task[None] | None = None
        self._running = False
        logger.debug("AsyncCommandTracker initialized")

    async def start(self) -> None:
        """Start the background polling task.

        Example:
            >>> tracker = AsyncCommandTracker(mcp_manager)
            >>> await tracker.start()
        """
        if not self._running:
            self._running = True
            self._polling_task = asyncio.create_task(self._polling_loop())
            logger.info("AsyncCommandTracker started")

    async def stop(self) -> None:
        """Stop the background polling task.

        Example:
            >>> await tracker.stop()
        """
        self._running = False
        if self._polling_task:
            self._polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._polling_task
        logger.info("AsyncCommandTracker stopped (tracked %d commands)", len(self.active_commands))

    def track_command(
        self,
        command_id: str,
        instance_id: str,
        document_name: str,
        parameters: dict[str, Any] | None = None,
        workflow_id: str | None = None,
        timeout_minutes: int = 15,
    ) -> CommandTrackingInfo:
        """Start tracking an SSM command.

        Args:
            command_id: SSM command ID from send-command.
            instance_id: Target EC2 instance ID.
            document_name: SSM document name.
            parameters: Command parameters (will be sanitized).
            workflow_id: Optional workflow ID for coordination.
            timeout_minutes: Timeout in minutes (default 15).

        Returns:
            CommandTrackingInfo for the tracked command.

        Example:
            >>> info = tracker.track_command(
            ...     command_id="cmd-123",
            ...     instance_id="i-abc123",
            ...     document_name="AWS-RunShellScript",
            ...     workflow_id="wf-456"
            ... )
        """
        tracking_info = CommandTrackingInfo.create(
            command_id=command_id,
            instance_id=instance_id,
            document_name=document_name,
            parameters=parameters,
            workflow_id=workflow_id,
            timeout_minutes=timeout_minutes,
        )

        self.active_commands[command_id] = tracking_info

        # Add to workflow if applicable
        if workflow_id and workflow_id in self.active_workflows:
            workflow = self.active_workflows[workflow_id]
            workflow.command_ids.append(command_id)

        logger.info(
            "Tracking command %s on instance %s (workflow: %s, timeout: %dm)",
            command_id,
            instance_id,
            workflow_id or "none",
            timeout_minutes,
        )

        return tracking_info

    def create_workflow(
        self,
        workflow_id: str,
        operation_type: str,
        expected_count: int,
    ) -> WorkflowInfo:
        """Create a workflow for multi-instance operations.

        Args:
            workflow_id: Unique workflow identifier.
            operation_type: Type of operation (e.g., "restart-services").
            expected_count: Expected number of commands.

        Returns:
            WorkflowInfo for the new workflow.

        Example:
            >>> workflow = tracker.create_workflow(
            ...     workflow_id="wf-123",
            ...     operation_type="stop-instances",
            ...     expected_count=5
            ... )
        """
        workflow = WorkflowInfo(  # type: ignore[call-arg]
            workflow_id=workflow_id,
            operation_type=operation_type,
            expected_count=expected_count,
        )

        self.active_workflows[workflow_id] = workflow
        logger.info(
            "Created workflow %s for %d %s commands",
            workflow_id,
            expected_count,
            operation_type,
        )

        return workflow

    async def _polling_loop(self) -> None:
        """Main polling loop for checking command status.

        Runs continuously while _running is True, checking each command
        to see if it needs polling based on exponential backoff timing.
        """
        while self._running:
            try:
                await asyncio.sleep(1)  # Check every second

                # Poll commands that are due
                for command_id in list(self.active_commands.keys()):
                    if command_id not in self.active_commands:
                        continue  # May have been removed

                    tracking_info = self.active_commands[command_id]

                    if tracking_info.is_terminal_state():
                        continue  # Already completed

                    # Check if it's time to poll
                    if self._should_poll(tracking_info):
                        await self._poll_command(tracking_info)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in polling loop: %s", e, exc_info=True)

    def _should_poll(self, tracking_info: CommandTrackingInfo) -> bool:
        """Check if command should be polled now.

        Args:
            tracking_info: Command to check.

        Returns:
            True if command should be polled.
        """
        if tracking_info.last_polled_at is None:
            return True  # First poll

        elapsed = (datetime.now(UTC) - tracking_info.last_polled_at).total_seconds()
        return elapsed >= tracking_info.next_poll_delay

    async def _poll_command(self, tracking_info: CommandTrackingInfo) -> None:
        """Poll SSM for command status.

        Args:
            tracking_info: Command to poll.
        """
        try:
            # Check timeout first
            if tracking_info.is_timed_out():
                timeout_msg = f"Command timed out after {tracking_info.poll_count} polls"
                tracking_info.update_status(
                    SSMCommandStatus.EXECUTION_TIMED_OUT,
                    timeout_msg,
                )
                logger.warning(
                    "Command %s timed out on instance %s",
                    tracking_info.command_id,
                    tracking_info.instance_id,
                )
                await self._handle_completion(tracking_info)
                return

            # Call get-command-invocation via MCP Manager
            result = await self.mcp_manager.call_aws_api_tool(
                tool_name="get-command-invocation",
                arguments={
                    "CommandId": tracking_info.command_id,
                    "InstanceId": tracking_info.instance_id,
                },
            )

            # Parse status from result
            status_str = result.get("Status", "Pending")
            try:
                new_status = SSMCommandStatus(status_str)
            except ValueError:
                logger.warning("Unknown SSM status: %s, treating as Pending", status_str)
                new_status = SSMCommandStatus.PENDING

            # Update tracking info
            old_status = tracking_info.status
            tracking_info.update_status(new_status)
            tracking_info.calculate_next_poll_delay()

            # Log status changes
            if old_status != new_status:
                logger.info(
                    "Command %s status: %s → %s (poll #%d)",
                    tracking_info.command_id,
                    old_status.value,
                    new_status.value,
                    tracking_info.poll_count,
                )
            else:
                logger.debug(
                    "Command %s still %s (poll #%d, next in %.1fs)",
                    tracking_info.command_id,
                    new_status.value,
                    tracking_info.poll_count,
                    tracking_info.next_poll_delay,
                )

            # Handle completion
            if tracking_info.is_terminal_state():
                if new_status == SSMCommandStatus.FAILED:
                    tracking_info.error_message = result.get(
                        "StandardErrorContent", "Unknown error"
                    )

                # Store output URL if available
                if "OutputS3BucketName" in result:
                    bucket = result["OutputS3BucketName"]
                    key = result.get("OutputS3KeyPrefix", "")
                    tracking_info.output_url = f"s3://{bucket}/{key}"

                await self._handle_completion(tracking_info)

        except Exception as e:
            error_str = str(e)

            # Handle common errors gracefully
            if "InvocationDoesNotExist" in error_str:
                logger.debug(
                    "Command %s not yet available in SSM, will retry...",
                    tracking_info.command_id,
                )
            elif "circuit_breaker" in error_str.lower():
                logger.warning(
                    "Circuit breaker active for command %s, backing off...",
                    tracking_info.command_id,
                )
            else:
                logger.error(
                    "Error polling command %s: %s",
                    tracking_info.command_id,
                    e,
                    exc_info=True,
                )

            # Backoff on error
            tracking_info.calculate_next_poll_delay()

    async def _handle_completion(self, tracking_info: CommandTrackingInfo) -> None:
        """Handle command completion.

        Args:
            tracking_info: Completed command info.
        """
        command_id = tracking_info.command_id
        workflow_id = tracking_info.workflow_id

        logger.info(
            "Command %s completed: %s (instance: %s)",
            command_id,
            tracking_info.status.value,
            tracking_info.instance_id,
        )

        # Update workflow if applicable
        workflow_info: WorkflowInfo | None = None
        if workflow_id and workflow_id in self.active_workflows:
            workflow_info = self.active_workflows[workflow_id]
            success = tracking_info.status == SSMCommandStatus.SUCCESS
            workflow_info.record_completion(success)

            logger.info(
                "Workflow %s progress: %d/%d completed (%d successful, %d failed)",
                workflow_id,
                workflow_info.completed_count,
                workflow_info.expected_count,
                workflow_info.success_count,
                workflow_info.failed_count,
            )

            # Check if workflow is complete
            if workflow_info.is_complete():
                success_rate = workflow_info.get_success_rate()
                logger.info(
                    "Workflow %s completed: %.1f%% success rate (%d/%d commands)",
                    workflow_id,
                    success_rate,
                    workflow_info.success_count,
                    workflow_info.expected_count,
                )

                if self.completion_callback:
                    await self.completion_callback.on_workflow_completed(workflow_info)

                # Clean up workflow
                del self.active_workflows[workflow_id]

        # Notify completion callback
        if self.completion_callback:
            await self.completion_callback.on_command_completed(tracking_info, workflow_info)

        # Remove from active tracking
        del self.active_commands[command_id]

    def get_command_status(self, command_id: str) -> CommandTrackingInfo | None:
        """Get current status of a tracked command.

        Args:
            command_id: SSM command ID.

        Returns:
            CommandTrackingInfo if found, None otherwise.

        Example:
            >>> info = tracker.get_command_status("cmd-123")
            >>> if info:
            ...     print(info.status)
        """
        return self.active_commands.get(command_id)

    def get_workflow_status(self, workflow_id: str) -> WorkflowInfo | None:
        """Get current status of a workflow.

        Args:
            workflow_id: Workflow ID.

        Returns:
            WorkflowInfo if found, None otherwise.

        Example:
            >>> workflow = tracker.get_workflow_status("wf-123")
            >>> if workflow:
            ...     print(f"{workflow.completed_count}/{workflow.expected_count}")
        """
        return self.active_workflows.get(workflow_id)

    def get_active_command_count(self) -> int:
        """Get number of currently tracked commands.

        Returns:
            Number of active commands.
        """
        return len(self.active_commands)

    def get_active_workflow_count(self) -> int:
        """Get number of currently active workflows.

        Returns:
            Number of active workflows.
        """
        return len(self.active_workflows)
