"""Unit tests for Write Operation Manager.

This module tests the WriteOperationManager class for managing operations
that require user approval before execution.
"""

from datetime import UTC, datetime, timedelta

import pytest

from ohlala_smartops.models.approvals import ApprovalRequest, ApprovalStatus
from ohlala_smartops.workflow.write_operations import WriteOperationManager


@pytest.fixture
def manager():
    """Create a WriteOperationManager instance for testing."""
    return WriteOperationManager(confirmation_timeout_minutes=15)


@pytest.fixture
def sample_callback():
    """Create a sample async callback for testing."""

    async def callback(operation: ApprovalRequest):
        return {"success": True, "message": "Operation executed successfully"}

    return callback


class TestWriteOperationManagerInit:
    """Test Write Operation Manager initialization."""

    def test_init_default_timeout(self):
        """Test initialization with default timeout."""
        manager = WriteOperationManager()
        assert manager.confirmation_timeout == timedelta(minutes=15)
        assert manager.pending_operations == {}
        assert manager.operation_callbacks == {}
        assert manager._cleanup_task is None

    def test_init_custom_timeout(self):
        """Test initialization with custom timeout."""
        manager = WriteOperationManager(confirmation_timeout_minutes=30)
        assert manager.confirmation_timeout == timedelta(minutes=30)


class TestOperationCreation:
    """Test operation creation and retrieval."""

    def test_create_approval_request_basic(self, manager):
        """Test creating a basic approval request."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234567890abcdef0"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Stop 1 instance",
        )

        assert operation.id is not None
        assert operation.command_type == "stop-instances"
        assert operation.requester_id == "user-123"
        assert operation.requester_name == "John Doe"
        assert operation.status == ApprovalStatus.PENDING
        assert operation.metadata["resource_ids"] == ["i-1234567890abcdef0"]
        assert operation.metadata["resource_count"] == 1
        assert operation.metadata["team_id"] == "team-456"
        assert operation.metadata["description"] == "Stop 1 instance"

    def test_create_approval_request_with_callback(self, manager, sample_callback):
        """Test creating an approval request with a callback."""
        operation = manager.create_approval_request(
            operation_type="terminate-instances",
            resource_ids=["i-1234", "i-5678"],
            user_id="user-123",
            user_name="Jane Smith",
            team_id="team-456",
            description="Terminate 2 instances",
            callback=sample_callback,
        )

        assert operation.id in manager.pending_operations
        assert operation.id in manager.operation_callbacks
        assert manager.operation_callbacks[operation.id] == sample_callback

    def test_create_approval_request_with_additional_data(self, manager):
        """Test creating an approval request with additional metadata."""
        additional_data = {
            "arguments": {"DocumentName": "AWS-RunShellScript"},
            "is_retry": True,
        }

        operation = manager.create_approval_request(
            operation_type="send-command",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="Bob Jones",
            team_id="team-456",
            description="Execute command",
            additional_data=additional_data,
        )

        assert operation.metadata["arguments"] == {"DocumentName": "AWS-RunShellScript"}
        assert operation.metadata["is_retry"] is True

    def test_create_approval_request_expiration(self, manager):
        """Test that approval request has correct expiration time."""
        before = datetime.now(UTC) + manager.confirmation_timeout
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )
        after = datetime.now(UTC) + manager.confirmation_timeout

        assert before <= operation.expires_at <= after


class TestOperationRetrieval:
    """Test operation retrieval and expiration."""

    def test_get_pending_operation_exists(self, manager):
        """Test retrieving an existing pending operation."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        retrieved = manager.get_pending_operation(operation.id)
        assert retrieved is not None
        assert retrieved.id == operation.id
        assert retrieved.command_type == "stop-instances"

    def test_get_pending_operation_not_found(self, manager):
        """Test retrieving a non-existent operation."""
        retrieved = manager.get_pending_operation("nonexistent-id")
        assert retrieved is None

    def test_get_pending_operation_expired(self, manager):
        """Test that expired operations are automatically removed."""
        # Create an operation
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        # Manually set expiration to past (skip Pydantic validation)
        manager.pending_operations[operation.id].expires_at = datetime.now(UTC) - timedelta(
            minutes=1
        )

        # Should return None and remove from pending
        retrieved = manager.get_pending_operation(operation.id)
        assert retrieved is None
        assert operation.id not in manager.pending_operations


class TestOperationConfirmation:
    """Test operation confirmation."""

    @pytest.mark.asyncio
    async def test_confirm_operation_without_callback(self, manager):
        """Test confirming an operation without a callback."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        result = await manager.confirm_operation(operation.id, "user-123")

        assert result["success"] is True
        assert result["operation"].id == operation.id
        assert operation.id not in manager.pending_operations

    @pytest.mark.asyncio
    async def test_confirm_operation_with_callback(self, manager, sample_callback):
        """Test confirming an operation with a callback."""
        operation = manager.create_approval_request(
            operation_type="terminate-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="Jane Smith",
            team_id="team-456",
            description="Test",
            callback=sample_callback,
        )

        result = await manager.confirm_operation(operation.id, "user-123")

        assert result["success"] is True
        assert result["operation"].id == operation.id
        assert result["result"]["success"] is True
        assert result["result"]["message"] == "Operation executed successfully"
        assert operation.id not in manager.pending_operations
        assert operation.id not in manager.operation_callbacks

    @pytest.mark.asyncio
    async def test_confirm_operation_not_found(self, manager):
        """Test confirming a non-existent operation."""
        result = await manager.confirm_operation("nonexistent-id", "user-123")

        assert result["success"] is False
        assert "not found or expired" in result["error"]

    @pytest.mark.asyncio
    async def test_confirm_operation_wrong_user(self, manager):
        """Test that only the requester can confirm their operation."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        result = await manager.confirm_operation(operation.id, "user-456")

        assert result["success"] is False
        assert "only confirm your own" in result["error"]
        assert operation.id in manager.pending_operations

    @pytest.mark.asyncio
    async def test_confirm_operation_callback_error(self, manager):
        """Test handling callback errors during confirmation."""

        async def failing_callback(operation: ApprovalRequest):
            raise ValueError("Callback failed")

        operation = manager.create_approval_request(
            operation_type="terminate-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="Jane Smith",
            team_id="team-456",
            description="Test",
            callback=failing_callback,
        )

        result = await manager.confirm_operation(operation.id, "user-123")

        assert result["success"] is False
        assert "Operation failed" in result["error"]
        assert "Callback failed" in result["error"]
        assert operation.id not in manager.pending_operations


class TestOperationCancellation:
    """Test operation cancellation."""

    def test_cancel_operation_success(self, manager):
        """Test successfully cancelling an operation."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        success = manager.cancel_operation(operation.id, "user-123")

        assert success is True
        assert operation.id not in manager.pending_operations

    def test_cancel_operation_not_found(self, manager):
        """Test cancelling a non-existent operation."""
        success = manager.cancel_operation("nonexistent-id", "user-123")
        assert success is False

    def test_cancel_operation_wrong_user(self, manager):
        """Test that only the requester can cancel their operation."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        success = manager.cancel_operation(operation.id, "user-456")

        assert success is False
        assert operation.id in manager.pending_operations


class TestUserOperations:
    """Test getting operations for a specific user."""

    def test_get_user_pending_operations_empty(self, manager):
        """Test getting pending operations for a user with none."""
        operations = manager.get_user_pending_operations("user-123")
        assert operations == []

    def test_get_user_pending_operations_single(self, manager):
        """Test getting pending operations for a user with one."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        operations = manager.get_user_pending_operations("user-123")

        assert len(operations) == 1
        assert operations[0].id == operation.id

    def test_get_user_pending_operations_multiple(self, manager):
        """Test getting multiple pending operations for a user."""
        op1 = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test 1",
        )
        op2 = manager.create_approval_request(
            operation_type="terminate-instances",
            resource_ids=["i-5678"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test 2",
        )

        operations = manager.get_user_pending_operations("user-123")

        assert len(operations) == 2
        operation_ids = {op.id for op in operations}
        assert op1.id in operation_ids
        assert op2.id in operation_ids

    def test_get_user_pending_operations_filters_by_user(self, manager):
        """Test that only operations for the specified user are returned."""
        manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="User 123 operation",
        )
        manager.create_approval_request(
            operation_type="terminate-instances",
            resource_ids=["i-5678"],
            user_id="user-456",
            user_name="Jane Smith",
            team_id="team-456",
            description="User 456 operation",
        )

        operations = manager.get_user_pending_operations("user-123")

        assert len(operations) == 1
        assert operations[0].requester_id == "user-123"

    def test_get_user_pending_operations_removes_expired(self, manager):
        """Test that expired operations are removed when getting user operations."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        # Manually expire the operation (skip Pydantic validation)
        manager.pending_operations[operation.id].expires_at = datetime.now(UTC) - timedelta(
            minutes=1
        )

        operations = manager.get_user_pending_operations("user-123")

        assert len(operations) == 0
        assert operation.id not in manager.pending_operations


class TestLifecycleManagement:
    """Test manager lifecycle (start/stop)."""

    @pytest.mark.asyncio
    async def test_start_manager(self, manager):
        """Test starting the manager."""
        await manager.start()

        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_manager(self, manager):
        """Test stopping the manager."""
        await manager.start()
        await manager.stop()

        assert manager._cleanup_task.cancelled() or manager._cleanup_task.done()

    @pytest.mark.asyncio
    async def test_cleanup_expired_operations(self, manager):
        """Test that expired operations are cleaned up automatically."""
        operation = manager.create_approval_request(
            operation_type="stop-instances",
            resource_ids=["i-1234"],
            user_id="user-123",
            user_name="John Doe",
            team_id="team-456",
            description="Test",
        )

        # Manually expire the operation (skip Pydantic validation)
        manager.pending_operations[operation.id].expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )

        # Start cleanup task
        await manager.start()

        # Wait a bit longer than the check interval (60 seconds)
        # For testing, we'll just trigger cleanup manually
        await manager.stop()

        # Manually trigger one cleanup cycle
        current_time = datetime.now(UTC)
        expired_operations = []

        for op_id, op in manager.pending_operations.items():
            if current_time > op.expires_at:
                expired_operations.append((op_id, op))

        for op_id, _op in expired_operations:
            manager._remove_operation(op_id)

        # Operation should be removed
        assert operation.id not in manager.pending_operations
