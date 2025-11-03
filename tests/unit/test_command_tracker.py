"""Unit tests for Async Command Tracker.

This module tests the AsyncCommandTracker class for tracking SSM command execution
with polling, workflow coordination, and completion callbacks.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from ohlala_smartops.models.command_tracking import (
    CommandTrackingInfo,
    SSMCommandStatus,
    WorkflowInfo,
)
from ohlala_smartops.workflow.command_tracker import AsyncCommandTracker


class MockCompletionCallback:
    """Mock implementation of CommandCompletionCallback for testing."""

    def __init__(self) -> None:
        """Initialize mock callback with tracking."""
        self.command_completions: list[tuple[CommandTrackingInfo, WorkflowInfo | None]] = []
        self.workflow_completions: list[WorkflowInfo] = []

    async def on_command_completed(
        self,
        tracking_info: CommandTrackingInfo,
        workflow_info: WorkflowInfo | None = None,
    ) -> None:
        """Record command completion."""
        self.command_completions.append((tracking_info, workflow_info))

    async def on_workflow_completed(self, workflow_info: WorkflowInfo) -> None:
        """Record workflow completion."""
        self.workflow_completions.append(workflow_info)


@pytest.fixture
def mock_mcp_manager():
    """Create a mock MCP Manager."""
    manager = Mock()
    manager.call_aws_api_tool = AsyncMock()
    return manager


@pytest.fixture
def mock_callback():
    """Create a mock completion callback."""
    return MockCompletionCallback()


@pytest.fixture
def tracker(mock_mcp_manager):
    """Create an AsyncCommandTracker instance for testing."""
    return AsyncCommandTracker(mock_mcp_manager)


@pytest.fixture
def tracker_with_callback(mock_mcp_manager, mock_callback):
    """Create an AsyncCommandTracker with completion callback."""
    return AsyncCommandTracker(mock_mcp_manager, mock_callback)


class TestAsyncCommandTrackerInit:
    """Test Async Command Tracker initialization."""

    def test_init_without_callback(self, mock_mcp_manager):
        """Test initialization without completion callback."""
        tracker = AsyncCommandTracker(mock_mcp_manager)
        assert tracker.mcp_manager is mock_mcp_manager
        assert tracker.completion_callback is None
        assert tracker.active_commands == {}
        assert tracker.active_workflows == {}
        assert tracker._polling_task is None
        assert tracker._running is False

    def test_init_with_callback(self, mock_mcp_manager, mock_callback):
        """Test initialization with completion callback."""
        tracker = AsyncCommandTracker(mock_mcp_manager, mock_callback)
        assert tracker.completion_callback is mock_callback


class TestCommandTracking:
    """Test command tracking functionality."""

    def test_track_command_basic(self, tracker):
        """Test tracking a basic command."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        assert tracking_info.command_id == "cmd-123"
        assert tracking_info.instance_id == "i-1234567890abcdef0"
        assert tracking_info.document_name == "AWS-RunShellScript"
        assert tracking_info.status == SSMCommandStatus.PENDING
        assert tracking_info.workflow_id is None
        assert "cmd-123" in tracker.active_commands

    def test_track_command_with_parameters(self, tracker):
        """Test tracking a command with parameters."""
        parameters = {"commands": ["uptime"]}
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            parameters=parameters,
        )

        assert tracking_info.parameters == parameters

    def test_track_command_with_workflow(self, tracker):
        """Test tracking a command as part of a workflow."""
        # Create workflow first
        workflow = tracker.create_workflow(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=2,
        )

        # Track command with workflow ID
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            workflow_id="wf-123",
        )

        assert tracking_info.workflow_id == "wf-123"
        assert "cmd-123" in workflow.command_ids

    def test_track_command_custom_timeout(self, tracker):
        """Test tracking a command with custom timeout."""
        before = datetime.now(UTC) + timedelta(minutes=30)
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            timeout_minutes=30,
        )
        after = datetime.now(UTC) + timedelta(minutes=30)

        assert before <= tracking_info.timeout_at <= after

    def test_get_command_status_exists(self, tracker):
        """Test retrieving status for an existing command."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        retrieved = tracker.get_command_status("cmd-123")
        assert retrieved is not None
        assert retrieved.command_id == "cmd-123"
        assert retrieved is tracking_info

    def test_get_command_status_not_found(self, tracker):
        """Test retrieving status for non-existent command."""
        retrieved = tracker.get_command_status("nonexistent")
        assert retrieved is None

    def test_get_active_command_count(self, tracker):
        """Test getting count of active commands."""
        assert tracker.get_active_command_count() == 0

        tracker.track_command(
            command_id="cmd-1",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )
        assert tracker.get_active_command_count() == 1

        tracker.track_command(
            command_id="cmd-2",
            instance_id="i-1234567890abcdef1",
            document_name="AWS-RunShellScript",
        )
        assert tracker.get_active_command_count() == 2


class TestWorkflowCreation:
    """Test workflow creation and management."""

    def test_create_workflow(self, tracker):
        """Test creating a workflow."""
        workflow = tracker.create_workflow(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=5,
        )

        assert workflow.workflow_id == "wf-123"
        assert workflow.operation_type == "stop-instances"
        assert workflow.expected_count == 5
        assert workflow.completed_count == 0
        assert workflow.success_count == 0
        assert workflow.failed_count == 0
        assert workflow.command_ids == []
        assert "wf-123" in tracker.active_workflows

    def test_get_workflow_status_exists(self, tracker):
        """Test retrieving status for an existing workflow."""
        workflow = tracker.create_workflow(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=5,
        )

        retrieved = tracker.get_workflow_status("wf-123")
        assert retrieved is not None
        assert retrieved.workflow_id == "wf-123"
        assert retrieved is workflow

    def test_get_workflow_status_not_found(self, tracker):
        """Test retrieving status for non-existent workflow."""
        retrieved = tracker.get_workflow_status("nonexistent")
        assert retrieved is None

    def test_get_active_workflow_count(self, tracker):
        """Test getting count of active workflows."""
        assert tracker.get_active_workflow_count() == 0

        tracker.create_workflow(
            workflow_id="wf-1",
            operation_type="stop-instances",
            expected_count=2,
        )
        assert tracker.get_active_workflow_count() == 1

        tracker.create_workflow(
            workflow_id="wf-2",
            operation_type="restart-services",
            expected_count=3,
        )
        assert tracker.get_active_workflow_count() == 2


class TestPollingLogic:
    """Test command polling logic."""

    def test_should_poll_first_time(self, tracker):
        """Test that command should be polled on first check."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        assert tracker._should_poll(tracking_info) is True

    def test_should_poll_after_delay(self, tracker):
        """Test polling after sufficient delay."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Simulate first poll
        tracking_info.last_polled_at = datetime.now(UTC) - timedelta(seconds=5)
        tracking_info.next_poll_delay = 3.0

        assert tracker._should_poll(tracking_info) is True

    def test_should_not_poll_too_soon(self, tracker):
        """Test that polling is delayed when too soon."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Simulate recent poll
        tracking_info.last_polled_at = datetime.now(UTC)
        tracking_info.next_poll_delay = 3.0

        assert tracker._should_poll(tracking_info) is False

    @pytest.mark.asyncio
    async def test_poll_command_success(self, tracker, mock_mcp_manager):
        """Test successful command polling."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Mock successful response
        mock_mcp_manager.call_aws_api_tool.return_value = {
            "Status": "Success",
            "StandardOutputContent": "Command completed",
        }

        await tracker._poll_command(tracking_info)

        assert tracking_info.status == SSMCommandStatus.SUCCESS
        assert tracking_info.last_polled_at is not None
        assert tracking_info.poll_count == 1
        assert "cmd-123" not in tracker.active_commands  # Removed after completion

    @pytest.mark.asyncio
    async def test_poll_command_in_progress(self, tracker, mock_mcp_manager):
        """Test polling command still in progress."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Mock in-progress response
        mock_mcp_manager.call_aws_api_tool.return_value = {
            "Status": "InProgress",
        }

        await tracker._poll_command(tracking_info)

        assert tracking_info.status == SSMCommandStatus.IN_PROGRESS
        assert tracking_info.poll_count == 1
        assert "cmd-123" in tracker.active_commands  # Still tracking

    @pytest.mark.asyncio
    async def test_poll_command_failed(self, tracker, mock_mcp_manager):
        """Test polling failed command."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Mock failed response
        mock_mcp_manager.call_aws_api_tool.return_value = {
            "Status": "Failed",
            "StandardErrorContent": "Command execution failed",
        }

        await tracker._poll_command(tracking_info)

        assert tracking_info.status == SSMCommandStatus.FAILED
        assert tracking_info.error_message == "Command execution failed"
        assert "cmd-123" not in tracker.active_commands  # Removed after completion

    @pytest.mark.asyncio
    async def test_poll_command_timeout(self, tracker, mock_mcp_manager):
        """Test command timeout handling."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            timeout_minutes=1,
        )

        # Manually set timeout to past
        tracking_info.timeout_at = datetime.now(UTC) - timedelta(minutes=1)

        await tracker._poll_command(tracking_info)

        assert tracking_info.status == SSMCommandStatus.EXECUTION_TIMED_OUT
        assert tracking_info.error_message is not None
        assert "timed out" in tracking_info.error_message
        assert "cmd-123" not in tracker.active_commands

    @pytest.mark.asyncio
    async def test_poll_command_invocation_not_exist(self, tracker, mock_mcp_manager):
        """Test handling when command invocation doesn't exist yet."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Mock InvocationDoesNotExist error
        mock_mcp_manager.call_aws_api_tool.side_effect = Exception("InvocationDoesNotExist")

        # Should not raise, just backoff
        await tracker._poll_command(tracking_info)

        assert tracking_info.poll_count == 1
        assert "cmd-123" in tracker.active_commands  # Still tracking


class TestCompletionHandling:
    """Test command and workflow completion handling."""

    @pytest.mark.asyncio
    async def test_handle_completion_without_callback(self, tracker):
        """Test completion handling without callback."""
        tracking_info = tracker.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )
        tracking_info.status = SSMCommandStatus.SUCCESS

        await tracker._handle_completion(tracking_info)

        assert "cmd-123" not in tracker.active_commands

    @pytest.mark.asyncio
    async def test_handle_completion_with_callback(self, tracker_with_callback, mock_callback):
        """Test completion handling with callback."""
        tracking_info = tracker_with_callback.track_command(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )
        tracking_info.status = SSMCommandStatus.SUCCESS

        await tracker_with_callback._handle_completion(tracking_info)

        assert len(mock_callback.command_completions) == 1
        completed_tracking, workflow = mock_callback.command_completions[0]
        assert completed_tracking.command_id == "cmd-123"
        assert workflow is None

    @pytest.mark.asyncio
    async def test_handle_completion_with_workflow(self, tracker_with_callback, mock_callback):
        """Test completion handling with workflow."""
        # Create workflow
        workflow = tracker_with_callback.create_workflow(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=2,
        )

        # Track first command
        tracking_info1 = tracker_with_callback.track_command(
            command_id="cmd-1",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            workflow_id="wf-123",
        )
        tracking_info1.status = SSMCommandStatus.SUCCESS

        # Complete first command
        await tracker_with_callback._handle_completion(tracking_info1)

        assert workflow.completed_count == 1
        assert workflow.success_count == 1
        assert workflow.failed_count == 0
        assert not workflow.is_complete()
        assert len(mock_callback.workflow_completions) == 0  # Workflow not done

        # Track second command
        tracking_info2 = tracker_with_callback.track_command(
            command_id="cmd-2",
            instance_id="i-1234567890abcdef1",
            document_name="AWS-RunShellScript",
            workflow_id="wf-123",
        )
        tracking_info2.status = SSMCommandStatus.SUCCESS

        # Complete second command
        await tracker_with_callback._handle_completion(tracking_info2)

        assert workflow.completed_count == 2
        assert workflow.success_count == 2
        assert workflow.is_complete()
        assert len(mock_callback.workflow_completions) == 1  # Workflow complete
        assert mock_callback.workflow_completions[0].workflow_id == "wf-123"

    @pytest.mark.asyncio
    async def test_handle_completion_workflow_with_failures(
        self, tracker_with_callback, mock_callback
    ):
        """Test workflow completion with mixed success and failures."""
        # Create workflow
        workflow = tracker_with_callback.create_workflow(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=3,
        )

        # Complete with success
        tracking_info1 = tracker_with_callback.track_command(
            command_id="cmd-1",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            workflow_id="wf-123",
        )
        tracking_info1.status = SSMCommandStatus.SUCCESS
        await tracker_with_callback._handle_completion(tracking_info1)

        # Complete with failure
        tracking_info2 = tracker_with_callback.track_command(
            command_id="cmd-2",
            instance_id="i-1234567890abcdef1",
            document_name="AWS-RunShellScript",
            workflow_id="wf-123",
        )
        tracking_info2.status = SSMCommandStatus.FAILED
        await tracker_with_callback._handle_completion(tracking_info2)

        # Complete with success
        tracking_info3 = tracker_with_callback.track_command(
            command_id="cmd-3",
            instance_id="i-1234567890abcdef2",
            document_name="AWS-RunShellScript",
            workflow_id="wf-123",
        )
        tracking_info3.status = SSMCommandStatus.SUCCESS
        await tracker_with_callback._handle_completion(tracking_info3)

        assert workflow.completed_count == 3
        assert workflow.success_count == 2
        assert workflow.failed_count == 1
        assert workflow.get_success_rate() == pytest.approx(66.67, rel=0.01)


class TestLifecycleManagement:
    """Test tracker lifecycle (start/stop)."""

    @pytest.mark.asyncio
    async def test_start_tracker(self, tracker):
        """Test starting the tracker."""
        await tracker.start()

        assert tracker._running is True
        assert tracker._polling_task is not None
        assert not tracker._polling_task.done()

        await tracker.stop()

    @pytest.mark.asyncio
    async def test_stop_tracker(self, tracker):
        """Test stopping the tracker."""
        await tracker.start()
        await tracker.stop()

        assert tracker._running is False
        assert tracker._polling_task.cancelled() or tracker._polling_task.done()

    @pytest.mark.asyncio
    async def test_start_already_running(self, tracker):
        """Test starting tracker when already running."""
        await tracker.start()
        first_task = tracker._polling_task

        await tracker.start()  # Should not create new task
        assert tracker._polling_task is first_task

        await tracker.stop()

    @pytest.mark.asyncio
    async def test_stop_not_running(self, tracker):
        """Test stopping tracker when not running."""
        # Should not raise
        await tracker.stop()
        assert tracker._polling_task is None
