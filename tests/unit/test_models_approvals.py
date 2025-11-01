"""Tests for approval workflow models."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ohlala_smartops.models.approvals import (
    ApprovalAction,
    ApprovalDecision,
    ApprovalLevel,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalWorkflow,
)


class TestApprovalRequest:
    """Test suite for ApprovalRequest model."""

    def test_approval_request_creation(self) -> None:
        """Test creating an ApprovalRequest."""
        request = ApprovalRequest.create(
            command_type="stop_instance",
            command_parameters={"instance_id": "i-123"},
            requester_id="user123",
            requester_name="John Doe",
            conversation_id="conv123",
        )

        assert request.id is not None
        assert request.command_type == "stop_instance"
        assert request.status == ApprovalStatus.PENDING
        assert len(request.approvers) == 0
        assert request.expires_at > datetime.now(tz=UTC)

    def test_expiration_validation(self) -> None:
        """Test that expiration must be in the future."""
        with pytest.raises(ValidationError):
            ApprovalRequest(
                id="req123",
                command_type="stop",
                command_parameters={},
                requester_id="user123",
                requester_name="User",
                conversation_id="conv123",
                approval_level=ApprovalLevel.SINGLE,
                expires_at=datetime.now(tz=UTC) - timedelta(hours=1),
            )

    def test_is_expired(self) -> None:
        """Test checking if request is expired."""
        # Not expired
        request = ApprovalRequest.create(
            command_type="stop",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
            expiration_minutes=30,
        )
        assert not request.is_expired()

        # Expired
        expired_request = ApprovalRequest(
            id="req123",
            command_type="stop",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
            approval_level=ApprovalLevel.SINGLE,
            expires_at=datetime.now(tz=UTC) + timedelta(milliseconds=1),
        )
        # Wait a tiny bit and it should be expired
        time.sleep(0.01)
        assert expired_request.is_expired()

    def test_can_approve(self) -> None:
        """Test approval eligibility checks."""
        request = ApprovalRequest.create(
            command_type="stop",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
        )

        # Can approve as different user
        assert request.can_approve("user456")

        # Cannot approve own request
        assert not request.can_approve("user123")

        # Cannot approve if already approved
        request.approvers.append("user456")
        assert not request.can_approve("user456")

        # Cannot approve if already rejected
        request.rejectors.append("user789")
        assert not request.can_approve("user789")

    def test_can_reject(self) -> None:
        """Test rejection eligibility checks."""
        request = ApprovalRequest.create(
            command_type="stop",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
        )

        # Can reject
        assert request.can_reject("user456")

        # Cannot reject if already rejected
        request.rejectors.append("user456")
        assert not request.can_reject("user456")

        # Cannot reject if not pending
        request.status = ApprovalStatus.APPROVED
        assert not request.can_reject("user789")

    def test_approve_single_approver(self) -> None:
        """Test approving with single approver required."""
        request = ApprovalRequest.create(
            command_type="stop",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
            approvers_required=1,
        )

        # First approval should complete the request
        result = request.approve("user456")
        assert result is True
        assert request.status == ApprovalStatus.APPROVED
        assert request.approved_at is not None
        assert "user456" in request.approvers

    def test_approve_multiple_approvers(self) -> None:
        """Test approving with multiple approvers required."""
        request = ApprovalRequest.create(
            command_type="terminate",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
            approvers_required=2,
        )

        # First approval shouldn't complete
        result = request.approve("user456")
        assert result is False
        assert request.status == ApprovalStatus.PENDING
        assert len(request.approvers) == 1

        # Second approval should complete
        result = request.approve("user789")
        assert result is True
        assert request.status == ApprovalStatus.APPROVED
        assert len(request.approvers) == 2

    def test_reject(self) -> None:
        """Test rejecting an approval request."""
        request = ApprovalRequest.create(
            command_type="stop",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
        )

        request.reject("user456", "Too risky")

        assert request.status == ApprovalStatus.REJECTED
        assert request.rejected_at is not None
        assert request.rejection_reason == "Too risky"
        assert "user456" in request.rejectors

    def test_cancel(self) -> None:
        """Test cancelling an approval request."""
        request = ApprovalRequest.create(
            command_type="stop",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
        )

        request.cancel()
        assert request.status == ApprovalStatus.CANCELLED

    def test_mark_expired(self) -> None:
        """Test marking a request as expired."""
        request = ApprovalRequest(
            id="req123",
            command_type="stop",
            command_parameters={},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
            approval_level=ApprovalLevel.SINGLE,
            expires_at=datetime.now(tz=UTC) + timedelta(milliseconds=1),
        )

        time.sleep(0.01)

        request.mark_expired()
        assert request.status == ApprovalStatus.EXPIRED


class TestApprovalDecision:
    """Test suite for ApprovalDecision model."""

    def test_approval_decision_creation(self) -> None:
        """Test creating an ApprovalDecision."""
        decision = ApprovalDecision(
            approval_id="req123",
            action=ApprovalAction.APPROVE,
            user_id="user456",
            user_name="Jane Doe",
            reason="Looks good",
        )

        assert decision.approval_id == "req123"
        assert decision.action == ApprovalAction.APPROVE
        assert decision.user_id == "user456"
        assert decision.reason == "Looks good"
        assert decision.timestamp is not None


class TestApprovalWorkflow:
    """Test suite for ApprovalWorkflow model."""

    def test_approval_workflow_creation(self) -> None:
        """Test creating an ApprovalWorkflow."""
        workflow = ApprovalWorkflow(
            command_type="stop_instance",
            approval_level=ApprovalLevel.SINGLE,
            approvers_required=1,
            expiration_minutes=30,
        )

        assert workflow.command_type == "stop_instance"
        assert workflow.approval_level == ApprovalLevel.SINGLE
        assert workflow.approvers_required == 1
        assert workflow.expiration_minutes == 30

    def test_requires_approval(self) -> None:
        """Test checking if approval is required."""
        workflow = ApprovalWorkflow(
            command_type="stop",
            approval_level=ApprovalLevel.SINGLE,
            auto_approve_for_roles=["admin"],
        )

        # Admin bypasses approval
        assert not workflow.requires_approval("admin")

        # Operator requires approval
        assert workflow.requires_approval("operator")

        # No approval workflow
        no_approval_workflow = ApprovalWorkflow(
            command_type="list",
            approval_level=ApprovalLevel.NONE,
        )
        assert not no_approval_workflow.requires_approval("operator")

    def test_can_user_approve(self) -> None:
        """Test checking if user can approve."""
        # Admin-only workflow
        admin_workflow = ApprovalWorkflow(
            command_type="terminate",
            approval_level=ApprovalLevel.ADMIN_ONLY,
        )

        assert admin_workflow.can_user_approve("admin")
        assert not admin_workflow.can_user_approve("operator")

        # Any role can approve
        open_workflow = ApprovalWorkflow(
            command_type="stop",
            approval_level=ApprovalLevel.SINGLE,
        )

        assert open_workflow.can_user_approve("admin")
        assert open_workflow.can_user_approve("operator")

        # Specific roles only
        restricted_workflow = ApprovalWorkflow(
            command_type="stop",
            approval_level=ApprovalLevel.SINGLE,
            allowed_roles=["admin", "operator"],
        )

        assert restricted_workflow.can_user_approve("admin")
        assert restricted_workflow.can_user_approve("operator")
        assert not restricted_workflow.can_user_approve("viewer")
