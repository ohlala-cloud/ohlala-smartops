"""Write operation confirmation and control manager.

This module provides the WriteOperationManager class for managing write operations
that require user confirmation before execution.

Phase 3B focuses on core operation management. Card creation logic is handled
by the approval_cards module.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from ohlala_smartops.models.approvals import ApprovalLevel, ApprovalRequest, ApprovalStatus

logger: Final = logging.getLogger(__name__)


class WriteOperationManager:
    """Manages write operations that require user confirmation.

    This manager handles the lifecycle of operations requiring approval:
    - Creating approval requests
    - Tracking pending operations
    - Confirming or cancelling operations
    - Cleaning up expired operations

    Attributes:
        confirmation_timeout: Time until pending operations expire.
        pending_operations: Dict mapping operation IDs to ApprovalRequests.
        operation_callbacks: Dict mapping operation IDs to callback functions.

    Example:
        >>> manager = WriteOperationManager(confirmation_timeout_minutes=15)
        >>> await manager.start()
        >>> # Create approval request
        >>> operation = manager.create_approval_request(
        ...     operation_type="stop-instances",
        ...     resource_ids=["i-1234567890abcdef0"],
        ...     user_id="user-123",
        ...     user_name="John Doe",
        ...     team_id="team-456",
        ...     description="Stop 1 instance",
        ...     callback=stop_instances_callback,
        ... )
        >>> # Later, confirm the operation
        >>> result = await manager.confirm_operation(operation.id, "user-123")
        >>> await manager.stop()

    Note:
        Phase 3B: Core operation management. Card creation in approval_cards module.
    """

    def __init__(self, confirmation_timeout_minutes: int = 15) -> None:
        """Initialize Write Operation Manager.

        Args:
            confirmation_timeout_minutes: Minutes until operations expire. Defaults to 15.
        """
        self.confirmation_timeout = timedelta(minutes=confirmation_timeout_minutes)
        self.pending_operations: dict[str, ApprovalRequest] = {}
        self.operation_callbacks: dict[
            str, Callable[[ApprovalRequest], Coroutine[Any, Any, dict[str, Any]]]
        ] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background cleanup task for expired operations.

        Example:
            >>> manager = WriteOperationManager()
            >>> await manager.start()
        """
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_operations())
            logger.info(
                "Write operation manager started with %d minute timeout",
                self.confirmation_timeout.seconds // 60,
            )

    async def stop(self) -> None:
        """Stop the background cleanup task.

        Example:
            >>> await manager.stop()
        """
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
            logger.info("Write operation manager stopped")

    def create_approval_request(
        self,
        operation_type: str,
        resource_ids: list[str],
        user_id: str,
        user_name: str,
        team_id: str,
        description: str,
        callback: Callable[[ApprovalRequest], Coroutine[Any, Any, dict[str, Any]]] | None = None,
        additional_data: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        """Create a new operation pending user confirmation.

        Args:
            operation_type: Type of operation (e.g., "stop-instances", "send-command").
            resource_ids: List of AWS resource IDs affected.
            user_id: ID of the user requesting the operation.
            user_name: Name of the user requesting the operation.
            team_id: ID of the team/conversation.
            description: Human-readable description of the operation.
            callback: Optional async callback function to execute upon confirmation.
            additional_data: Optional additional metadata.

        Returns:
            ApprovalRequest object for the pending operation.

        Example:
            >>> operation = manager.create_approval_request(
            ...     operation_type="stop-instances",
            ...     resource_ids=["i-1234"],
            ...     user_id="user-123",
            ...     user_name="John Doe",
            ...     team_id="team-456",
            ...     description="Stop 1 instance",
            ...     callback=my_callback,
            ... )
        """
        operation_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + self.confirmation_timeout

        # Build metadata with resource information
        metadata = {
            "resource_ids": resource_ids,
            "resource_count": len(resource_ids),
            "team_id": team_id,
            "description": description,
        }
        if additional_data:
            metadata.update(additional_data)

        # Create approval request
        approval_request = ApprovalRequest(
            id=operation_id,
            command_type=operation_type,
            command_parameters={},  # Stored in metadata instead
            requester_id=user_id,
            requester_name=user_name,
            conversation_id=team_id,
            approval_level=ApprovalLevel.SINGLE,  # Always single approval for now
            approvers_required=1,
            status=ApprovalStatus.PENDING,
            reason=description,  # Use description as reason
            rejection_reason=None,
            approved_at=None,
            rejected_at=None,
            expires_at=expires_at,
            metadata=metadata,
        )

        self.pending_operations[operation_id] = approval_request

        # Store callback separately (not serializable in the model)
        if callback:
            self.operation_callbacks[operation_id] = callback

        logger.info(
            "Created pending operation %s: %s on %d resource(s)",
            operation_id,
            operation_type,
            len(resource_ids),
        )

        return approval_request

    def get_pending_operation(self, operation_id: str) -> ApprovalRequest | None:
        """Get a pending operation by ID.

        Automatically removes expired operations.

        Args:
            operation_id: ID of the operation to retrieve.

        Returns:
            ApprovalRequest if found and not expired, None otherwise.

        Example:
            >>> operation = manager.get_pending_operation("op-123")
            >>> if operation:
            ...     print(f"Operation status: {operation.status}")
        """
        operation = self.pending_operations.get(operation_id)

        if operation is None:
            return None

        # Check if expired
        if datetime.now(UTC) > operation.expires_at:
            self._remove_operation(operation_id)
            logger.info("Operation %s has expired", operation_id)
            return None

        return operation

    async def confirm_operation(self, operation_id: str, confirmed_by: str) -> dict[str, Any]:
        """Confirm a pending operation and execute its callback.

        Args:
            operation_id: ID of the operation to confirm.
            confirmed_by: User ID of the person confirming.

        Returns:
            Dict with success status and optionally the execution result.

        Example:
            >>> result = await manager.confirm_operation("op-123", "user-123")
            >>> if result["success"]:
            ...     print("Operation confirmed and executed")

        Note:
            Only the user who created the operation can confirm it.
        """
        operation = self.get_pending_operation(operation_id)

        if operation is None:
            return {"success": False, "error": "Operation not found or expired"}

        # Verify the user confirming is the same who initiated
        if operation.requester_id != confirmed_by:
            logger.warning(
                "User %s tried to confirm operation %s initiated by %s",
                confirmed_by,
                operation_id,
                operation.requester_id,
            )
            return {"success": False, "error": "You can only confirm your own operations"}

        # Update status
        operation.status = ApprovalStatus.APPROVED
        operation.approved_at = datetime.now(UTC)
        operation.approvers = [confirmed_by]

        # Execute callback if provided
        callback = self.operation_callbacks.get(operation_id)
        if callback:
            try:
                result = await callback(operation)
                logger.info("Operation %s confirmed and executed successfully", operation_id)
                self._remove_operation(operation_id)
                return {"success": True, "operation": operation, "result": result}
            except Exception as e:
                logger.error(
                    "Error executing confirmed operation %s: %s", operation_id, e, exc_info=True
                )
                self._remove_operation(operation_id)
                return {"success": False, "error": f"Operation failed: {e!s}"}

        # No callback - just mark as confirmed
        self._remove_operation(operation_id)
        return {"success": True, "operation": operation}

    def cancel_operation(self, operation_id: str, cancelled_by: str) -> bool:
        """Cancel a pending operation.

        Args:
            operation_id: ID of the operation to cancel.
            cancelled_by: User ID of the person cancelling.

        Returns:
            True if cancelled successfully, False otherwise.

        Example:
            >>> success = manager.cancel_operation("op-123", "user-123")
            >>> if success:
            ...     print("Operation cancelled")

        Note:
            Only the user who created the operation can cancel it.
        """
        operation = self.get_pending_operation(operation_id)

        if operation is None:
            return False

        # Verify the user cancelling is the same who initiated
        if operation.requester_id != cancelled_by:
            logger.warning(
                "User %s tried to cancel operation %s initiated by %s",
                cancelled_by,
                operation_id,
                operation.requester_id,
            )
            return False

        # Update status and remove
        operation.status = ApprovalStatus.CANCELLED
        self._remove_operation(operation_id)
        logger.info("Operation %s cancelled by user", operation_id)
        return True

    def get_user_pending_operations(self, user_id: str) -> list[ApprovalRequest]:
        """Get all pending operations for a specific user.

        Args:
            user_id: ID of the user.

        Returns:
            List of ApprovalRequest objects for the user.

        Example:
            >>> operations = manager.get_user_pending_operations("user-123")
            >>> print(f"User has {len(operations)} pending operations")
        """
        current_time = datetime.now(UTC)
        user_operations: list[ApprovalRequest] = []
        expired_ids: list[str] = []

        for op_id, operation in self.pending_operations.items():
            if current_time > operation.expires_at:
                expired_ids.append(op_id)
            elif operation.requester_id == user_id:
                user_operations.append(operation)

        # Clean up expired operations
        for op_id in expired_ids:
            self._remove_operation(op_id)

        return user_operations

    def _remove_operation(self, operation_id: str) -> None:
        """Remove an operation from pending state.

        Args:
            operation_id: ID of the operation to remove.
        """
        self.pending_operations.pop(operation_id, None)
        self.operation_callbacks.pop(operation_id, None)

    async def _cleanup_expired_operations(self) -> None:
        """Periodically clean up expired operations.

        This background task runs every minute to remove expired operations.
        """
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                current_time = datetime.now(UTC)
                expired_operations: list[tuple[str, ApprovalRequest]] = []

                for op_id, operation in self.pending_operations.items():
                    if current_time > operation.expires_at:
                        expired_operations.append((op_id, operation))

                for op_id, operation in expired_operations:
                    # Log the expiration with details
                    resource_count = operation.metadata.get("resource_count", 0)
                    logger.info(
                        "Operation %s expired: %s on %d resource(s) requested by %s",
                        op_id,
                        operation.command_type,
                        resource_count,
                        operation.requester_name,
                    )
                    self._remove_operation(op_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in cleanup task: %s", e, exc_info=True)
