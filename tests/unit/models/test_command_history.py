"""Unit tests for CommandHistoryEntry model.

This module tests the CommandHistoryEntry Pydantic model for tracking
command execution history.
"""

from datetime import UTC, datetime

from ohlala_smartops.models.command_history import CommandHistoryEntry, CommandHistoryStatus


class TestCommandHistoryEntry:
    """Test suite for CommandHistoryEntry model."""

    def test_create_basic_entry(self) -> None:
        """Test creating a basic command history entry."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Start instance i-abc123",
        )

        assert entry.command_id == "cmd-123"
        assert entry.user_id == "user@example.com"
        assert entry.description == "Start instance i-abc123"
        assert entry.status == CommandHistoryStatus.PENDING
        assert entry.instance_ids == []
        assert entry.results == {}
        assert entry.completion_time is None
        assert entry.approved_by is None

    def test_create_with_instances(self) -> None:
        """Test creating entry with instance IDs."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-456",
            user_id="user@example.com",
            description="Stop instances",
            instance_ids=["i-abc123", "i-def456"],
        )

        assert len(entry.instance_ids) == 2
        assert "i-abc123" in entry.instance_ids
        assert "i-def456" in entry.instance_ids

    def test_create_with_context(self) -> None:
        """Test creating entry with user context."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-789",
            user_id="user@example.com",
            description="Reboot instance",
            user_context="Team: Engineering",
        )

        assert entry.user_context == "Team: Engineering"

    def test_create_with_region(self) -> None:
        """Test creating entry with custom AWS region."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-abc",
            user_id="user@example.com",
            description="List instances",
            aws_region="us-west-2",
        )

        assert entry.aws_region == "us-west-2"

    def test_mark_completed_without_results(self) -> None:
        """Test marking command as completed without results."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        entry.mark_completed()

        assert entry.status == CommandHistoryStatus.COMPLETED
        assert entry.completion_time is not None
        assert entry.completion_time.tzinfo == UTC

    def test_mark_completed_with_results(self) -> None:
        """Test marking command as completed with results."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        results = {
            "i-abc123": {"status": "Success", "output": "Command executed"},
            "i-def456": {"status": "Failed", "error": "Permission denied"},
        }

        entry.mark_completed(results)

        assert entry.status == CommandHistoryStatus.COMPLETED
        assert entry.results == results
        assert len(entry.results) == 2

    def test_mark_failed(self) -> None:
        """Test marking command as failed."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        entry.mark_failed("Instance not found")

        assert entry.status == CommandHistoryStatus.FAILED
        assert entry.completion_time is not None
        assert "error" in entry.results
        assert entry.results["error"]["message"] == "Instance not found"

    def test_mark_cancelled(self) -> None:
        """Test marking command as cancelled."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        entry.mark_cancelled()

        assert entry.status == CommandHistoryStatus.CANCELLED
        assert entry.completion_time is not None

    def test_set_approval(self) -> None:
        """Test recording command approval."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Dangerous command",
        )

        entry.set_approval("approver@example.com")

        assert entry.approved_by == "approver@example.com"

    def test_add_result(self) -> None:
        """Test adding individual instance result."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        entry.add_result("i-abc123", {"status": "Success", "output": "OK"})

        assert "i-abc123" in entry.results
        assert entry.results["i-abc123"]["status"] == "Success"

    def test_is_completed_for_completed_status(self) -> None:
        """Test is_completed returns True for completed status."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        entry.mark_completed()

        assert entry.is_completed() is True

    def test_is_completed_for_failed_status(self) -> None:
        """Test is_completed returns True for failed status."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        entry.mark_failed("Error occurred")

        assert entry.is_completed() is True

    def test_is_completed_for_cancelled_status(self) -> None:
        """Test is_completed returns True for cancelled status."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        entry.mark_cancelled()

        assert entry.is_completed() is True

    def test_is_completed_for_pending_status(self) -> None:
        """Test is_completed returns False for pending status."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        assert entry.is_completed() is False

    def test_timestamp_auto_generated(self) -> None:
        """Test that timestamp is automatically set to current time."""
        before = datetime.now(UTC)
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )
        after = datetime.now(UTC)

        assert before <= entry.timestamp <= after
        assert entry.timestamp.tzinfo == UTC

    def test_completion_time_set_on_mark_completed(self) -> None:
        """Test that completion_time is set when marking completed."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        assert entry.completion_time is None

        before = datetime.now(UTC)
        entry.mark_completed()
        after = datetime.now(UTC)

        assert entry.completion_time is not None
        assert before <= entry.completion_time <= after

    def test_multiple_status_transitions(self) -> None:
        """Test multiple status transitions."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        # Start pending
        assert entry.status == CommandHistoryStatus.PENDING

        # Mark as completed
        entry.mark_completed()
        assert entry.status == CommandHistoryStatus.COMPLETED

        # Can be marked failed afterward (e.g., async completion check)
        entry.mark_failed("Actually failed")
        assert entry.status == CommandHistoryStatus.FAILED


class TestCommandHistoryStatus:
    """Test suite for CommandHistoryStatus enum."""

    def test_status_values(self) -> None:
        """Test that all status values are correct."""
        assert CommandHistoryStatus.PENDING.value == "pending"
        assert CommandHistoryStatus.COMPLETED.value == "completed"
        assert CommandHistoryStatus.FAILED.value == "failed"
        assert CommandHistoryStatus.CANCELLED.value == "cancelled"

    def test_status_comparison(self) -> None:
        """Test status comparison."""
        assert CommandHistoryStatus.PENDING == CommandHistoryStatus.PENDING
        assert CommandHistoryStatus.PENDING != CommandHistoryStatus.COMPLETED
