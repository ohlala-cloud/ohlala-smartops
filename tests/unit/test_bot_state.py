"""Tests for conversation state management."""

from datetime import UTC, datetime

import pytest

from ohlala_smartops.bot.state import (
    ConversationStateManager,
    InMemoryStateStorage,
    create_state_manager,
)
from ohlala_smartops.models import (
    ApprovalRequest,
    ConversationContext,
    ConversationState,
    ConversationType,
    UserInfo,
)


class TestInMemoryStateStorage:
    """Test suite for InMemoryStateStorage."""

    @pytest.fixture
    def storage(self) -> InMemoryStateStorage:
        """Create an InMemoryStateStorage instance."""
        return InMemoryStateStorage()

    @pytest.fixture
    def sample_state(self) -> ConversationState:
        """Create a sample ConversationState."""
        return ConversationState(
            conversation_id="conv123",
            pending_command=None,
            turn_count=1,
        )

    async def test_set_and_get_state(
        self, storage: InMemoryStateStorage, sample_state: ConversationState
    ) -> None:
        """Test storing and retrieving state."""
        await storage.set_state(sample_state)

        retrieved = await storage.get_state("conv123")
        assert retrieved is not None
        assert retrieved.conversation_id == "conv123"
        assert retrieved.turn_count == 1

    async def test_get_nonexistent_state(self, storage: InMemoryStateStorage) -> None:
        """Test retrieving non-existent state returns None."""
        result = await storage.get_state("nonexistent")
        assert result is None

    async def test_delete_state(
        self, storage: InMemoryStateStorage, sample_state: ConversationState
    ) -> None:
        """Test deleting state."""
        await storage.set_state(sample_state)
        await storage.delete_state("conv123")

        result = await storage.get_state("conv123")
        assert result is None

    async def test_state_expiration(
        self, storage: InMemoryStateStorage, sample_state: ConversationState
    ) -> None:
        """Test that state expires after TTL."""
        import asyncio

        # Set state with very short TTL (1 millisecond)
        await storage.set_state(sample_state, ttl_seconds=0.001)

        # Wait for expiration
        await asyncio.sleep(0.01)

        # Should return None (expired)
        result = await storage.get_state("conv123")
        assert result is None


class TestConversationStateManager:
    """Test suite for ConversationStateManager."""

    @pytest.fixture
    def manager(self) -> ConversationStateManager:
        """Create a ConversationStateManager with in-memory storage."""
        return create_state_manager("memory")

    @pytest.fixture
    def sample_user(self) -> UserInfo:
        """Create a sample UserInfo."""
        return UserInfo(
            id="user123",
            name="Test User",
            tenant_id="tenant123",
        )

    @pytest.fixture
    def sample_context(self, sample_user: UserInfo) -> ConversationContext:
        """Create a sample ConversationContext."""
        return ConversationContext(
            conversation_id="conv123",
            conversation_type=ConversationType.PERSONAL,
            user=sample_user,
            service_url="https://example.com",
        )

    async def test_get_state_creates_new(
        self, manager: ConversationStateManager
    ) -> None:
        """Test that getting state for new conversation creates it."""
        state = await manager.get_state("new_conv")

        assert state is not None
        assert state.conversation_id == "new_conv"
        assert state.turn_count == 0

    async def test_save_and_get_state(
        self, manager: ConversationStateManager
    ) -> None:
        """Test saving and retrieving state."""
        state = ConversationState(
            conversation_id="conv123",
            pending_command="start instance",
            turn_count=5,
        )

        await manager.save_state(state)

        retrieved = await manager.get_state("conv123")
        assert retrieved.pending_command == "start instance"
        assert retrieved.turn_count == 5

    async def test_add_turn(self, manager: ConversationStateManager) -> None:
        """Test adding a turn to conversation state."""
        state = await manager.get_state("conv123")
        original_count = state.turn_count

        await manager.add_turn("conv123", "user", "Hello")

        updated_state = await manager.get_state("conv123")
        assert updated_state.turn_count == original_count + 1
        assert len(updated_state.history) == 1
        assert updated_state.history[0]["role"] == "user"
        assert updated_state.history[0]["content"] == "Hello"

    async def test_clear_state(self, manager: ConversationStateManager) -> None:
        """Test clearing conversation state."""
        state = ConversationState(
            conversation_id="conv123",
            pending_command="stop instance",
            pending_approval_id="approval123",
        )
        await manager.save_state(state)

        await manager.clear_state("conv123")

        # Should create new empty state
        new_state = await manager.get_state("conv123")
        assert new_state.pending_command is None
        assert new_state.pending_approval_id is None

    async def test_save_context(
        self,
        manager: ConversationStateManager,
        sample_context: ConversationContext,
    ) -> None:
        """Test saving conversation context."""
        await manager.save_context(sample_context)

        context = await manager.get_context("conv123")
        assert context is not None
        assert context.conversation_id == "conv123"
        assert context.user.id == "user123"

    async def test_get_approval(
        self, manager: ConversationStateManager
    ) -> None:
        """Test storing and retrieving approval requests."""
        approval = ApprovalRequest.create(
            command_type="stop_instance",
            command_parameters={"instance_id": "i-123"},
            requester_id="user123",
            requester_name="User",
            conversation_id="conv123",
        )

        await manager.save_approval(approval)

        retrieved = await manager.get_approval(approval.id)
        assert retrieved is not None
        assert retrieved.command_type == "stop_instance"


class TestStateManagerFactory:
    """Test the state manager factory function."""

    def test_create_memory_manager(self) -> None:
        """Test creating an in-memory state manager."""
        manager = create_state_manager("memory")

        assert isinstance(manager, ConversationStateManager)
        assert isinstance(manager.storage, InMemoryStateStorage)

    def test_create_invalid_type(self) -> None:
        """Test that invalid storage type raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported storage type"):
            create_state_manager("invalid")
