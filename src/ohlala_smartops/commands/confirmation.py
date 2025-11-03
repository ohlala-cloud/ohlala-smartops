"""Write operation confirmation system.

This module provides a confirmation system for write operations (start, stop,
reboot instances). It ensures users explicitly confirm potentially disruptive
actions before execution.

Phase 5B: Simplified version for basic instance operations.
Future phases may add SSM command confirmation and retry logic.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

logger: Final = logging.getLogger(__name__)


@dataclass
class PendingOperation:
    """Represents a pending write operation awaiting confirmation.

    Attributes:
        id: Unique operation ID.
        operation_type: Type of operation (e.g., "start-instances").
        resource_type: Type of resource (e.g., "EC2 Instance").
        resource_ids: List of resource IDs to operate on.
        user_id: User who requested the operation.
        user_name: Display name of requesting user.
        description: Human-readable operation description.
        expires_at: When this operation expires.
        callback: Async function to execute on confirmation.
        additional_data: Any additional context data.
    """

    id: str
    operation_type: str
    resource_type: str
    resource_ids: list[str]
    user_id: str
    user_name: str
    description: str
    expires_at: datetime
    callback: Callable[[Any], Any] | None = None
    additional_data: dict[str, Any] = field(default_factory=dict)


class ConfirmationManager:
    """Manages write operations that require user confirmation.

    This manager handles the lifecycle of write operations:
    1. Create confirmation request
    2. Generate confirmation card
    3. Wait for user confirmation
    4. Execute confirmed operation
    5. Clean up expired operations

    Example:
        >>> manager = ConfirmationManager()
        >>> await manager.start()
        >>> operation = manager.create_confirmation_request(
        ...     operation_type="start-instances",
        ...     resource_type="EC2 Instance",
        ...     resource_ids=["i-123"],
        ...     user_id="user-123",
        ...     user_name="Alice",
        ...     description="Start 1 instance",
        ...     callback=start_callback
        ... )
        >>> card = manager.create_confirmation_card(operation)
    """

    def __init__(self, confirmation_timeout_minutes: int = 15) -> None:
        """Initialize confirmation manager.

        Args:
            confirmation_timeout_minutes: How long confirmations remain valid.
        """
        self.pending_operations: dict[str, PendingOperation] = {}
        self.confirmation_timeout = timedelta(minutes=confirmation_timeout_minutes)
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background cleanup task for expired operations."""
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_operations())
        logger.info("Confirmation manager started")

    async def stop(self) -> None:
        """Stop the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
        logger.info("Confirmation manager stopped")

    def create_confirmation_request(
        self,
        operation_type: str,
        resource_type: str,
        resource_ids: list[str],
        user_id: str,
        user_name: str,
        description: str,
        callback: Callable[[Any], Any] | None = None,
        additional_data: dict[str, Any] | None = None,
    ) -> PendingOperation:
        """Create a new operation pending confirmation.

        Args:
            operation_type: Operation type (e.g., "start-instances").
            resource_type: Resource type (e.g., "EC2 Instance").
            resource_ids: List of resource IDs.
            user_id: User who requested the operation.
            user_name: Display name of requesting user.
            description: Human-readable description.
            callback: Async function to call on confirmation.
            additional_data: Optional additional context.

        Returns:
            PendingOperation object.

        Example:
            >>> operation = manager.create_confirmation_request(
            ...     operation_type="stop-instances",
            ...     resource_type="EC2 Instance",
            ...     resource_ids=["i-123", "i-456"],
            ...     user_id="user-123",
            ...     user_name="Alice",
            ...     description="Stop 2 instances",
            ...     callback=async_callback
            ... )
        """
        operation_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + self.confirmation_timeout

        operation = PendingOperation(
            id=operation_id,
            operation_type=operation_type,
            resource_type=resource_type,
            resource_ids=resource_ids,
            user_id=user_id,
            user_name=user_name,
            description=description,
            expires_at=expires_at,
            callback=callback,
            additional_data=additional_data or {},
        )

        self.pending_operations[operation_id] = operation
        logger.info(
            f"Created pending operation {operation_id}: {operation_type} "
            f"on {len(resource_ids)} {resource_type}(s)"
        )

        return operation

    def get_pending_operation(self, operation_id: str) -> PendingOperation | None:
        """Get a pending operation by ID.

        Args:
            operation_id: Unique operation ID.

        Returns:
            PendingOperation if found and not expired, None otherwise.
        """
        operation = self.pending_operations.get(operation_id)

        # Check if expired
        if operation and datetime.now(UTC) > operation.expires_at:
            del self.pending_operations[operation_id]
            logger.info(f"Operation {operation_id} has expired")
            return None

        return operation

    async def confirm_operation(self, operation_id: str, confirmed_by: str) -> dict[str, Any]:
        """Confirm and execute a pending operation.

        Args:
            operation_id: Operation ID to confirm.
            confirmed_by: User ID confirming the operation.

        Returns:
            Result dictionary with success status and operation result.

        Example:
            >>> result = await manager.confirm_operation("op-123", "user-123")
            >>> if result["success"]:
            ...     print(result["result"])
        """
        operation = self.get_pending_operation(operation_id)

        if not operation:
            return {"success": False, "error": "Operation not found or expired"}

        # Verify the user confirming is the same who initiated
        if operation.user_id != confirmed_by:
            logger.warning(
                f"User {confirmed_by} tried to confirm operation {operation_id} "
                f"initiated by {operation.user_id}"
            )
            return {
                "success": False,
                "error": "You can only confirm your own operations",
            }

        # Remove from pending
        del self.pending_operations[operation_id]

        # Execute callback if provided
        if operation.callback:
            try:
                result = await operation.callback(operation)
                logger.info(f"Operation {operation_id} confirmed and executed successfully")
                return {"success": True, "operation": operation, "result": result}
            except Exception as e:
                logger.error(
                    f"Error executing confirmed operation {operation_id}: {e}",
                    exc_info=True,
                )
                return {"success": False, "error": f"Operation failed: {e!s}"}

        return {"success": True, "operation": operation}

    def cancel_operation(self, operation_id: str, cancelled_by: str) -> bool:
        """Cancel a pending operation.

        Args:
            operation_id: Operation ID to cancel.
            cancelled_by: User ID cancelling the operation.

        Returns:
            True if cancelled successfully, False otherwise.
        """
        operation = self.get_pending_operation(operation_id)

        if not operation:
            return False

        # Verify the user cancelling is the same who initiated
        if operation.user_id != cancelled_by:
            logger.warning(
                f"User {cancelled_by} tried to cancel operation {operation_id} "
                f"initiated by {operation.user_id}"
            )
            return False

        del self.pending_operations[operation_id]
        logger.info(f"Operation {operation_id} cancelled by user")
        return True

    def get_user_pending_operations(self, user_id: str) -> list[PendingOperation]:
        """Get all pending operations for a user.

        Args:
            user_id: User ID to get operations for.

        Returns:
            List of pending operations for the user.
        """
        current_time = datetime.now(UTC)
        user_operations: list[PendingOperation] = []
        expired_ids: list[str] = []

        for op_id, operation in self.pending_operations.items():
            if current_time > operation.expires_at:
                expired_ids.append(op_id)
            elif operation.user_id == user_id:
                user_operations.append(operation)

        # Remove expired operations
        for op_id in expired_ids:
            del self.pending_operations[op_id]

        return user_operations

    async def _cleanup_expired_operations(self) -> None:
        """Periodically clean up expired operations (background task)."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                current_time = datetime.now(UTC)
                expired_operations: list[tuple[str, PendingOperation]] = []

                for op_id, operation in self.pending_operations.items():
                    if current_time > operation.expires_at:
                        expired_operations.append((op_id, operation))

                for op_id, operation in expired_operations:
                    logger.info(
                        f"Operation {op_id} expired: {operation.operation_type} "
                        f"requested by {operation.user_name}"
                    )
                    del self.pending_operations[op_id]

                if expired_operations:
                    logger.info(f"Cleaned up {len(expired_operations)} expired operations")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}", exc_info=True)

    def create_confirmation_card(self, operation: PendingOperation) -> dict[str, Any]:
        """Create an adaptive card for operation confirmation.

        Args:
            operation: Pending operation to create card for.

        Returns:
            Adaptive card dictionary.

        Example:
            >>> card = manager.create_confirmation_card(operation)
            >>> # Send card to user for confirmation
        """
        # Operation titles
        operation_titles = {
            "stop-instances": "Stop Instances",
            "start-instances": "Start Instances",
            "reboot-instances": "Reboot Instances",
        }

        title = operation_titles.get(
            operation.operation_type,
            operation.operation_type.replace("-", " ").title(),
        )

        # Determine warning level
        is_destructive = operation.operation_type in ["stop-instances"]
        is_disruptive = operation.operation_type in ["reboot-instances"]

        if is_destructive:
            warning_text = (
                "⚠️ WARNING: This action will stop your instances and may "
                "result in service interruption."
            )
        elif is_disruptive:
            warning_text = (
                "⚠️ WARNING: This action will reboot your instances causing "
                "temporary service interruption."
            )
        else:  # start-instances
            warning_text = "✅ INFO: This action will start your instances and make them available."

        # Build card body
        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"{title} - Confirmation Required",
                "weight": "Bolder",
                "size": "Large",
            },
            {
                "type": "TextBlock",
                "text": f"Operation: {operation.description}",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [
                    {
                        "title": "Operation:",
                        "value": operation.operation_type.replace("-", " ").title(),
                    },
                    {"title": "Resource Type:", "value": operation.resource_type},
                    {
                        "title": "Resource IDs:",
                        "value": ", ".join(operation.resource_ids[:3])
                        + ("..." if len(operation.resource_ids) > 3 else ""),
                    },
                    {"title": "Requested by:", "value": operation.user_name},
                    {
                        "title": "Expires in:",
                        "value": f"{int(self.confirmation_timeout.total_seconds() / 60)} minutes",
                    },
                ],
            },
            {
                "type": "TextBlock",
                "text": warning_text,
                "wrap": True,
                "color": "Warning" if (is_destructive or is_disruptive) else "Good",
            },
        ]

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


# Global instance (simplified singleton pattern)
confirmation_manager = ConfirmationManager()
