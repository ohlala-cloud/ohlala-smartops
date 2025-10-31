"""Approval workflow models for Ohlala SmartOps.

This module defines Pydantic models for approval workflows, including
approval requests, approval decisions, and workflow state tracking.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalAction(str, Enum):
    """Actions that can be taken on an approval request."""

    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


class ApprovalLevel(str, Enum):
    """Level of approval required for an operation."""

    NONE = "none"  # No approval required
    SINGLE = "single"  # Single approver required
    MULTIPLE = "multiple"  # Multiple approvers required
    ADMIN_ONLY = "admin_only"  # Admin approval only


class ApprovalRequest(BaseModel):
    """Request for approval of a dangerous or sensitive operation.

    Attributes:
        id: Unique identifier for the approval request.
        command_type: Type of command requiring approval.
        command_parameters: Parameters for the command.
        requester_id: ID of the user who requested the operation.
        requester_name: Name of the user who requested the operation.
        conversation_id: ID of the conversation where the request was made.
        approval_level: Level of approval required.
        approvers_required: Number of approvers required.
        approvers: List of user IDs who have approved.
        rejectors: List of user IDs who have rejected.
        status: Current status of the approval request.
        reason: Reason for the request (provided by requester).
        rejection_reason: Reason for rejection (if rejected).
        created_at: When the approval request was created.
        expires_at: When the approval request expires.
        approved_at: When the request was approved.
        rejected_at: When the request was rejected.
        metadata: Additional metadata.
    """

    id: str = Field(..., min_length=1, description="Approval request ID")
    command_type: str = Field(..., description="Command type requiring approval")
    command_parameters: dict[str, Any] = Field(..., description="Command parameters")
    requester_id: str = Field(..., min_length=1, description="Requester user ID")
    requester_name: str = Field(..., min_length=1, description="Requester name")
    conversation_id: str = Field(..., min_length=1, description="Conversation ID")
    approval_level: ApprovalLevel = Field(..., description="Approval level required")
    approvers_required: int = Field(1, ge=1, description="Number of approvers required")
    approvers: list[str] = Field(default_factory=list, description="User IDs who approved")
    rejectors: list[str] = Field(default_factory=list, description="User IDs who rejected")
    status: ApprovalStatus = Field(ApprovalStatus.PENDING, description="Approval status")
    reason: str | None = Field(None, description="Reason for the request")
    rejection_reason: str | None = Field(None, description="Reason for rejection")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    approved_at: datetime | None = Field(None, description="Approval timestamp")
    rejected_at: datetime | None = Field(None, description="Rejection timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, v: datetime) -> datetime:
        """Validate that expiration is in the future.

        Args:
            v: Expiration timestamp.

        Returns:
            Validated expiration timestamp.

        Raises:
            ValueError: If expiration is in the past.
        """
        if v <= datetime.utcnow():
            raise ValueError("Expiration time must be in the future")
        return v

    @classmethod
    def create(
        cls,
        command_type: str,
        command_parameters: dict[str, Any],
        requester_id: str,
        requester_name: str,
        conversation_id: str,
        approval_level: ApprovalLevel = ApprovalLevel.SINGLE,
        approvers_required: int = 1,
        reason: str | None = None,
        expiration_minutes: int = 30,
    ) -> "ApprovalRequest":
        """Create a new approval request.

        Args:
            command_type: Type of command requiring approval.
            command_parameters: Parameters for the command.
            requester_id: ID of the user requesting approval.
            requester_name: Name of the user requesting approval.
            conversation_id: ID of the conversation.
            approval_level: Level of approval required.
            approvers_required: Number of approvers required.
            reason: Reason for the request.
            expiration_minutes: Minutes until the request expires.

        Returns:
            New approval request instance.
        """
        import uuid

        return cls(
            id=str(uuid.uuid4()),
            command_type=command_type,
            command_parameters=command_parameters,
            requester_id=requester_id,
            requester_name=requester_name,
            conversation_id=conversation_id,
            approval_level=approval_level,
            approvers_required=approvers_required,
            reason=reason,
            expires_at=datetime.utcnow() + timedelta(minutes=expiration_minutes),
            status=ApprovalStatus.PENDING,
            rejection_reason=None,
            approved_at=None,
            rejected_at=None,
        )

    def is_expired(self) -> bool:
        """Check if the approval request has expired.

        Returns:
            True if the request has expired.
        """
        return datetime.utcnow() >= self.expires_at

    def can_approve(self, user_id: str) -> bool:
        """Check if a user can approve this request.

        Args:
            user_id: ID of the user attempting to approve.

        Returns:
            True if the user can approve.
        """
        # Cannot approve if not pending
        if self.status != ApprovalStatus.PENDING:
            return False

        # Cannot approve if expired
        if self.is_expired():
            return False

        # Cannot approve own request
        if user_id == self.requester_id:
            return False

        # Cannot approve if already approved
        if user_id in self.approvers:
            return False

        # Cannot approve if already rejected
        return user_id not in self.rejectors

    def can_reject(self, user_id: str) -> bool:
        """Check if a user can reject this request.

        Args:
            user_id: ID of the user attempting to reject.

        Returns:
            True if the user can reject.
        """
        # Cannot reject if not pending
        if self.status != ApprovalStatus.PENDING:
            return False

        # Cannot reject if expired
        if self.is_expired():
            return False

        # Cannot reject if already rejected
        return user_id not in self.rejectors

    def approve(self, user_id: str) -> bool:
        """Approve the request.

        Args:
            user_id: ID of the user approving.

        Returns:
            True if the request is now fully approved.
        """
        if not self.can_approve(user_id):
            return False

        self.approvers.append(user_id)

        # Check if we have enough approvals
        if len(self.approvers) >= self.approvers_required:
            self.status = ApprovalStatus.APPROVED
            self.approved_at = datetime.utcnow()
            return True

        return False

    def reject(self, user_id: str, reason: str | None = None) -> None:
        """Reject the request.

        Args:
            user_id: ID of the user rejecting.
            reason: Reason for rejection.
        """
        if not self.can_reject(user_id):
            return

        self.rejectors.append(user_id)
        self.status = ApprovalStatus.REJECTED
        self.rejected_at = datetime.utcnow()
        if reason:
            self.rejection_reason = reason

    def cancel(self) -> None:
        """Cancel the approval request."""
        if self.status == ApprovalStatus.PENDING:
            self.status = ApprovalStatus.CANCELLED

    def mark_expired(self) -> None:
        """Mark the request as expired."""
        if self.status == ApprovalStatus.PENDING and self.is_expired():
            self.status = ApprovalStatus.EXPIRED


class ApprovalDecision(BaseModel):
    """Decision made on an approval request.

    Attributes:
        approval_id: ID of the approval request.
        action: Action taken (approve, reject, cancel).
        user_id: ID of the user who made the decision.
        user_name: Name of the user who made the decision.
        reason: Reason for the decision.
        timestamp: When the decision was made.
    """

    approval_id: str = Field(..., min_length=1, description="Approval request ID")
    action: ApprovalAction = Field(..., description="Action taken")
    user_id: str = Field(..., min_length=1, description="User ID")
    user_name: str = Field(..., min_length=1, description="User name")
    reason: str | None = Field(None, description="Reason for the decision")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Decision timestamp")


class ApprovalWorkflow(BaseModel):
    """Workflow configuration for approval requirements.

    Attributes:
        command_type: Type of command this workflow applies to.
        approval_level: Level of approval required.
        approvers_required: Number of approvers required.
        expiration_minutes: Minutes until approval requests expire.
        allowed_roles: Roles allowed to approve (empty means all).
        auto_approve_for_roles: Roles that bypass approval.
    """

    command_type: str = Field(..., description="Command type")
    approval_level: ApprovalLevel = Field(..., description="Approval level")
    approvers_required: int = Field(1, ge=1, description="Approvers required")
    expiration_minutes: int = Field(30, ge=1, le=1440, description="Expiration time in minutes")
    allowed_roles: list[str] = Field(default_factory=list, description="Roles allowed to approve")
    auto_approve_for_roles: list[str] = Field(
        default_factory=list, description="Roles that bypass approval"
    )

    def requires_approval(self, user_role: str) -> bool:
        """Check if approval is required for a user role.

        Args:
            user_role: Role of the user requesting the operation.

        Returns:
            True if approval is required.
        """
        # No approval needed if role bypasses approval
        if user_role in self.auto_approve_for_roles:
            return False

        # No approval needed if level is NONE
        return self.approval_level != ApprovalLevel.NONE

    def can_user_approve(self, user_role: str) -> bool:
        """Check if a user role can approve requests for this workflow.

        Args:
            user_role: Role of the user.

        Returns:
            True if the user role can approve.
        """
        # Admin-only approval requires admin role
        if self.approval_level == ApprovalLevel.ADMIN_ONLY:
            return user_role == "admin"

        # If allowed_roles is empty, any role can approve
        if not self.allowed_roles:
            return True

        return user_role in self.allowed_roles
