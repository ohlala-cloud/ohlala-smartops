"""Unit tests for command tracking models.

This module tests the Pydantic models used for command tracking:
CommandTrackingInfo, WorkflowInfo, and SSMCommandStatus.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ohlala_smartops.models.command_tracking import (
    CommandTrackingInfo,
    SSMCommandStatus,
    WorkflowInfo,
)


class TestSSMCommandStatus:
    """Test SSM Command Status enum."""

    def test_all_statuses_defined(self):
        """Test that all AWS SSM statuses are defined."""
        expected_statuses = {
            "Pending",
            "InProgress",
            "Delayed",
            "Success",
            "DeliveryTimedOut",
            "ExecutionTimedOut",
            "Failed",
            "Cancelled",
            "Undeliverable",
            "Terminated",
            "Cancelling",
        }

        actual_statuses = {status.value for status in SSMCommandStatus}
        assert actual_statuses == expected_statuses

    def test_status_string_conversion(self):
        """Test converting string to SSMCommandStatus."""
        assert SSMCommandStatus("Success") == SSMCommandStatus.SUCCESS
        assert SSMCommandStatus("Pending") == SSMCommandStatus.PENDING
        assert SSMCommandStatus("Failed") == SSMCommandStatus.FAILED

    def test_invalid_status_raises_error(self):
        """Test that invalid status raises ValueError."""
        with pytest.raises(ValueError, match="InvalidStatus"):
            SSMCommandStatus("InvalidStatus")


class TestCommandTrackingInfo:
    """Test CommandTrackingInfo model."""

    def test_create_basic(self):
        """Test creating a basic CommandTrackingInfo."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        assert info.command_id == "cmd-123"
        assert info.instance_id == "i-1234567890abcdef0"
        assert info.document_name == "AWS-RunShellScript"
        assert info.status == SSMCommandStatus.PENDING
        assert info.workflow_id is None
        assert info.parameters == {}
        assert info.poll_count == 0
        assert info.next_poll_delay == 3.0
        assert info.last_polled_at is None
        assert info.completed_at is None
        assert info.error_message is None
        assert info.output_url is None

    def test_create_with_parameters(self):
        """Test creating CommandTrackingInfo with parameters."""
        params = {"commands": ["uptime", "hostname"]}
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            parameters=params,
        )

        assert info.parameters == params

    def test_create_with_workflow(self):
        """Test creating CommandTrackingInfo with workflow ID."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            workflow_id="wf-456",
        )

        assert info.workflow_id == "wf-456"

    def test_create_with_custom_timeout(self):
        """Test creating CommandTrackingInfo with custom timeout."""
        before = datetime.now(UTC) + timedelta(minutes=30)
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            timeout_minutes=30,
        )
        after = datetime.now(UTC) + timedelta(minutes=30)

        assert before <= info.timeout_at <= after

    def test_sanitize_parameters(self):
        """Test parameter sanitization removes sensitive data."""
        params = {
            "commands": ["echo test"],
            "password": "secret123",
            "api_key": "key123",
            "token": "token123",
            "secret_value": "secret",
            "normal_param": "normal",
        }

        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            parameters=params,
        )

        assert info.parameters["commands"] == ["echo test"]
        assert info.parameters["password"] == "***REDACTED***"
        assert info.parameters["api_key"] == "***REDACTED***"
        assert info.parameters["token"] == "***REDACTED***"
        assert info.parameters["secret_value"] == "***REDACTED***"
        assert info.parameters["normal_param"] == "normal"

    def test_is_terminal_state_success(self):
        """Test terminal state detection for success."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )
        info.status = SSMCommandStatus.SUCCESS
        assert info.is_terminal_state() is True

    def test_is_terminal_state_failed(self):
        """Test terminal state detection for failure."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )
        info.status = SSMCommandStatus.FAILED
        assert info.is_terminal_state() is True

    def test_is_terminal_state_cancelled(self):
        """Test terminal state detection for cancelled."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )
        info.status = SSMCommandStatus.CANCELLED
        assert info.is_terminal_state() is True

    def test_is_terminal_state_timeouts(self):
        """Test terminal state detection for timeout states."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        info.status = SSMCommandStatus.EXECUTION_TIMED_OUT
        assert info.is_terminal_state() is True

        info.status = SSMCommandStatus.DELIVERY_TIMED_OUT
        assert info.is_terminal_state() is True

    def test_is_not_terminal_state(self):
        """Test non-terminal state detection."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Test non-terminal states
        for status in [
            SSMCommandStatus.PENDING,
            SSMCommandStatus.IN_PROGRESS,
            SSMCommandStatus.DELAYED,
            SSMCommandStatus.CANCELLING,
        ]:
            info.status = status
            assert info.is_terminal_state() is False

    def test_is_timed_out_false(self):
        """Test timeout detection when not timed out."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            timeout_minutes=15,
        )
        assert info.is_timed_out() is False

    def test_is_timed_out_true(self):
        """Test timeout detection when timed out."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
            timeout_minutes=15,
        )

        # Manually set timeout to past
        info.timeout_at = datetime.now(UTC) - timedelta(minutes=1)
        assert info.is_timed_out() is True

    def test_update_status_basic(self):
        """Test updating command status."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        before = datetime.now(UTC)
        info.update_status(SSMCommandStatus.IN_PROGRESS)
        after = datetime.now(UTC)

        assert info.status == SSMCommandStatus.IN_PROGRESS
        assert before <= info.last_polled_at <= after
        assert info.completed_at is None

    def test_update_status_terminal(self):
        """Test updating to terminal status sets completed_at."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        before = datetime.now(UTC)
        info.update_status(SSMCommandStatus.SUCCESS)
        after = datetime.now(UTC)

        assert info.status == SSMCommandStatus.SUCCESS
        assert before <= info.completed_at <= after

    def test_update_status_with_error(self):
        """Test updating status with error message."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        info.update_status(SSMCommandStatus.FAILED, "Command execution failed")

        assert info.status == SSMCommandStatus.FAILED
        assert info.error_message == "Command execution failed"

    def test_calculate_next_poll_delay_exponential(self):
        """Test exponential backoff calculation."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Initial delay is 3.0
        assert info.next_poll_delay == 3.0

        # First calculation: 3.0 * 1.2^1 = 3.6
        delay1 = info.calculate_next_poll_delay()
        assert info.poll_count == 1
        assert delay1 == pytest.approx(3.6, rel=0.01)

        # Second calculation: 3.0 * 1.2^2 = 4.32
        delay2 = info.calculate_next_poll_delay()
        assert info.poll_count == 2
        assert delay2 == pytest.approx(4.32, rel=0.01)

        # Third calculation: 3.0 * 1.2^3 = 5.184
        delay3 = info.calculate_next_poll_delay()
        assert info.poll_count == 3
        assert delay3 == pytest.approx(5.184, rel=0.01)

    def test_calculate_next_poll_delay_cap(self):
        """Test that polling delay is capped at 10 seconds."""
        info = CommandTrackingInfo.create(
            command_id="cmd-123",
            instance_id="i-1234567890abcdef0",
            document_name="AWS-RunShellScript",
        )

        # Calculate many times to exceed cap
        for _ in range(20):
            delay = info.calculate_next_poll_delay()

        # Should be capped at 10.0
        assert delay == 10.0
        assert info.next_poll_delay == 10.0

    def test_invalid_instance_id_format(self):
        """Test validation of instance ID format."""
        with pytest.raises(ValidationError):
            CommandTrackingInfo(
                command_id="cmd-123",
                instance_id="invalid-id",  # Not i-xxx format
                document_name="AWS-RunShellScript",
                timeout_at=datetime.now(UTC) + timedelta(minutes=15),
            )

    def test_empty_command_id(self):
        """Test validation of empty command ID."""
        with pytest.raises(ValidationError):
            CommandTrackingInfo(
                command_id="",  # Empty string
                instance_id="i-1234567890abcdef0",
                document_name="AWS-RunShellScript",
                timeout_at=datetime.now(UTC) + timedelta(minutes=15),
            )


class TestWorkflowInfo:
    """Test WorkflowInfo model."""

    def test_create_basic(self):
        """Test creating a basic WorkflowInfo."""
        workflow = WorkflowInfo(
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
        assert workflow.completed_at is None

    def test_is_complete_false(self):
        """Test workflow completion detection when not complete."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=5,
        )

        assert workflow.is_complete() is False

        workflow.completed_count = 3
        assert workflow.is_complete() is False

    def test_is_complete_true(self):
        """Test workflow completion detection when complete."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=5,
        )

        workflow.completed_count = 5
        assert workflow.is_complete() is True

        workflow.completed_count = 6  # More than expected
        assert workflow.is_complete() is True

    def test_record_completion_success(self):
        """Test recording successful command completion."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=3,
        )

        workflow.record_completion(success=True)

        assert workflow.completed_count == 1
        assert workflow.success_count == 1
        assert workflow.failed_count == 0
        assert workflow.completed_at is None  # Not yet complete

    def test_record_completion_failure(self):
        """Test recording failed command completion."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=3,
        )

        workflow.record_completion(success=False)

        assert workflow.completed_count == 1
        assert workflow.success_count == 0
        assert workflow.failed_count == 1
        assert workflow.completed_at is None  # Not yet complete

    def test_record_completion_sets_completed_at(self):
        """Test that workflow completion sets completed_at timestamp."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=2,
        )

        workflow.record_completion(success=True)
        assert workflow.completed_at is None

        before = datetime.now(UTC)
        workflow.record_completion(success=True)
        after = datetime.now(UTC)

        assert before <= workflow.completed_at <= after

    def test_get_success_rate_zero(self):
        """Test success rate calculation with no completions."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=5,
        )

        assert workflow.get_success_rate() == 0.0

    def test_get_success_rate_all_success(self):
        """Test success rate with all successful."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=5,
        )

        for _ in range(5):
            workflow.record_completion(success=True)

        assert workflow.get_success_rate() == 100.0

    def test_get_success_rate_all_failed(self):
        """Test success rate with all failed."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=5,
        )

        for _ in range(5):
            workflow.record_completion(success=False)

        assert workflow.get_success_rate() == 0.0

    def test_get_success_rate_mixed(self):
        """Test success rate with mixed results."""
        workflow = WorkflowInfo(
            workflow_id="wf-123",
            operation_type="stop-instances",
            expected_count=5,
        )

        workflow.record_completion(success=True)
        workflow.record_completion(success=True)
        workflow.record_completion(success=True)
        workflow.record_completion(success=False)
        workflow.record_completion(success=False)

        # 3 out of 5 = 60%
        assert workflow.get_success_rate() == pytest.approx(60.0, rel=0.01)

    def test_invalid_expected_count(self):
        """Test validation of expected count."""
        with pytest.raises(ValidationError):
            WorkflowInfo(
                workflow_id="wf-123",
                operation_type="stop-instances",
                expected_count=0,  # Must be >= 1
            )

    def test_empty_workflow_id(self):
        """Test validation of empty workflow ID."""
        with pytest.raises(ValidationError):
            WorkflowInfo(
                workflow_id="",  # Empty string
                operation_type="stop-instances",
                expected_count=5,
            )
