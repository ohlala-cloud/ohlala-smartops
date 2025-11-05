"""Conversation state management for Ohlala SmartOps.

This module provides state management for tracking conversation context,
state, and approval workflows across multiple turns.
"""

import logging
from abc import abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ohlala_smartops.models import (
    ApprovalRequest,
    CommandHistoryEntry,
    ConversationContext,
    ConversationState,
)

logger = logging.getLogger(__name__)


class StateStorage(Protocol):
    """Protocol for state storage backends.

    This protocol defines the interface for storing and retrieving
    conversation state, context, and approval requests.
    """

    @abstractmethod
    async def get_state(self, conversation_id: str) -> ConversationState | None:
        """Get conversation state by ID.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            Conversation state if found, None otherwise.
        """
        ...

    @abstractmethod
    async def set_state(self, state: ConversationState, ttl_seconds: int = 3600) -> None:
        """Store conversation state.

        Args:
            state: Conversation state to store.
            ttl_seconds: Time-to-live in seconds (default: 1 hour).
        """
        ...

    @abstractmethod
    async def get_context(self, conversation_id: str) -> ConversationContext | None:
        """Get conversation context by ID.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            Conversation context if found, None otherwise.
        """
        ...

    @abstractmethod
    async def set_context(self, context: ConversationContext, ttl_seconds: int = 86400) -> None:
        """Store conversation context.

        Args:
            context: Conversation context to store.
            ttl_seconds: Time-to-live in seconds (default: 24 hours).
        """
        ...

    @abstractmethod
    async def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Get approval request by ID.

        Args:
            approval_id: Unique approval request identifier.

        Returns:
            Approval request if found, None otherwise.
        """
        ...

    @abstractmethod
    async def set_approval(self, approval: ApprovalRequest) -> None:
        """Store approval request.

        Args:
            approval: Approval request to store.
        """
        ...

    @abstractmethod
    async def list_pending_approvals(self, user_id: str) -> list[ApprovalRequest]:
        """List pending approvals for a user.

        Args:
            user_id: User ID to get approvals for.

        Returns:
            List of pending approval requests.
        """
        ...

    @abstractmethod
    async def delete_state(self, conversation_id: str) -> None:
        """Delete conversation state.

        Args:
            conversation_id: Conversation ID to delete state for.
        """
        ...

    @abstractmethod
    async def delete_context(self, conversation_id: str) -> None:
        """Delete conversation context.

        Args:
            conversation_id: Conversation ID to delete context for.
        """
        ...

    @abstractmethod
    async def add_command_history(self, entry: CommandHistoryEntry) -> None:
        """Add command to history.

        Args:
            entry: Command history entry to store.
        """
        ...

    @abstractmethod
    async def get_recent_commands(self, user_id: str, limit: int = 10) -> list[CommandHistoryEntry]:
        """Get recent command history for a user.

        Args:
            user_id: User ID to get history for.
            limit: Maximum number of entries to return.

        Returns:
            List of command history entries, most recent first.
        """
        ...

    @abstractmethod
    async def get_command_history(self, command_id: str) -> CommandHistoryEntry | None:
        """Get specific command history entry.

        Args:
            command_id: Command ID to retrieve.

        Returns:
            Command history entry if found, None otherwise.
        """
        ...


class InMemoryStateStorage:
    """In-memory state storage for development and testing.

    This storage backend keeps all state in memory. Data is lost when
    the application restarts. Use RedisStateStorage for production.

    Attributes:
        _states: Dictionary of conversation states.
        _contexts: Dictionary of conversation contexts.
        _approvals: Dictionary of approval requests.

    Example:
        >>> storage = InMemoryStateStorage()
        >>> await storage.set_state(state)
        >>> retrieved = await storage.get_state(conversation_id)
    """

    def __init__(self) -> None:
        """Initialize in-memory storage."""
        self._states: dict[str, ConversationState] = {}
        self._contexts: dict[str, ConversationContext] = {}
        self._approvals: dict[str, ApprovalRequest] = {}
        self._state_expiry: dict[str, datetime] = {}
        self._context_expiry: dict[str, datetime] = {}
        self._command_history: dict[str, CommandHistoryEntry] = {}
        self._user_command_ids: dict[str, list[str]] = {}
        logger.info("Initialized in-memory state storage")

    async def get_state(self, conversation_id: str) -> ConversationState | None:
        """Get conversation state by ID.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            Conversation state if found and not expired, None otherwise.
        """
        # Check if expired
        if (
            conversation_id in self._state_expiry
            and datetime.now(tz=UTC) > self._state_expiry[conversation_id]
        ):
            # Expired, remove it
            await self.delete_state(conversation_id)
            return None

        return self._states.get(conversation_id)

    async def set_state(self, state: ConversationState, ttl_seconds: int = 3600) -> None:
        """Store conversation state.

        Args:
            state: Conversation state to store.
            ttl_seconds: Time-to-live in seconds (default: 1 hour).
        """
        self._states[state.conversation_id] = state
        self._state_expiry[state.conversation_id] = datetime.now(tz=UTC) + timedelta(
            seconds=ttl_seconds
        )
        logger.debug(f"Stored state for conversation {state.conversation_id}")

    async def get_context(self, conversation_id: str) -> ConversationContext | None:
        """Get conversation context by ID.

        Args:
            conversation_id: Unique conversation identifier.

        Returns:
            Conversation context if found and not expired, None otherwise.
        """
        # Check if expired
        if (
            conversation_id in self._context_expiry
            and datetime.now(tz=UTC) > self._context_expiry[conversation_id]
        ):
            # Expired, remove it
            await self.delete_context(conversation_id)
            return None

        return self._contexts.get(conversation_id)

    async def set_context(self, context: ConversationContext, ttl_seconds: int = 86400) -> None:
        """Store conversation context.

        Args:
            context: Conversation context to store.
            ttl_seconds: Time-to-live in seconds (default: 24 hours).
        """
        self._contexts[context.conversation_id] = context
        self._context_expiry[context.conversation_id] = datetime.now(tz=UTC) + timedelta(
            seconds=ttl_seconds
        )
        logger.debug(f"Stored context for conversation {context.conversation_id}")

    async def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Get approval request by ID.

        Args:
            approval_id: Unique approval request identifier.

        Returns:
            Approval request if found, None otherwise.
        """
        approval = self._approvals.get(approval_id)

        # Check if expired
        if approval and approval.is_expired():
            approval.mark_expired()
            await self.set_approval(approval)

        return approval

    async def set_approval(self, approval: ApprovalRequest) -> None:
        """Store approval request.

        Args:
            approval: Approval request to store.
        """
        self._approvals[approval.id] = approval
        logger.debug(f"Stored approval request {approval.id}")

    async def list_pending_approvals(self, user_id: str) -> list[ApprovalRequest]:
        """List pending approvals for a user.

        Args:
            user_id: User ID to get approvals for.

        Returns:
            List of pending approval requests where user can approve.
        """
        pending: list[ApprovalRequest] = []

        for approval in self._approvals.values():
            # Check if expired
            if approval.is_expired():
                approval.mark_expired()
                await self.set_approval(approval)
                continue

            # Check if pending and user can approve
            if approval.can_approve(user_id):
                pending.append(approval)

        return pending

    async def delete_state(self, conversation_id: str) -> None:
        """Delete conversation state.

        Args:
            conversation_id: Conversation ID to delete state for.
        """
        self._states.pop(conversation_id, None)
        self._state_expiry.pop(conversation_id, None)
        logger.debug(f"Deleted state for conversation {conversation_id}")

    async def delete_context(self, conversation_id: str) -> None:
        """Delete conversation context.

        Args:
            conversation_id: Conversation ID to delete context for.
        """
        self._contexts.pop(conversation_id, None)
        self._context_expiry.pop(conversation_id, None)
        logger.debug(f"Deleted context for conversation {conversation_id}")

    async def add_command_history(self, entry: CommandHistoryEntry) -> None:
        """Add command to history.

        Args:
            entry: Command history entry to store.
        """
        self._command_history[entry.command_id] = entry

        # Track command IDs by user for efficient lookup
        if entry.user_id not in self._user_command_ids:
            self._user_command_ids[entry.user_id] = []
        self._user_command_ids[entry.user_id].insert(0, entry.command_id)  # Most recent first

        # Limit history per user to 100 entries (prevent memory growth)
        if len(self._user_command_ids[entry.user_id]) > 100:
            old_command_id = self._user_command_ids[entry.user_id].pop()
            self._command_history.pop(old_command_id, None)

        logger.debug(f"Added command {entry.command_id} to history for user {entry.user_id}")

    async def get_recent_commands(self, user_id: str, limit: int = 10) -> list[CommandHistoryEntry]:
        """Get recent command history for a user.

        Args:
            user_id: User ID to get history for.
            limit: Maximum number of entries to return.

        Returns:
            List of command history entries, most recent first.
        """
        command_ids = self._user_command_ids.get(user_id, [])[:limit]
        return [self._command_history[cid] for cid in command_ids if cid in self._command_history]

    async def get_command_history(self, command_id: str) -> CommandHistoryEntry | None:
        """Get specific command history entry.

        Args:
            command_id: Command ID to retrieve.

        Returns:
            Command history entry if found, None otherwise.
        """
        return self._command_history.get(command_id)


class ConversationStateManager:
    """Manager for conversation state and context.

    This manager provides a high-level interface for managing conversation
    state, context, and approval workflows. It handles serialization,
    caching, and storage backend interactions.

    Attributes:
        storage: Storage backend for state persistence.

    Example:
        >>> manager = ConversationStateManager(InMemoryStateStorage())
        >>> await manager.save_context(context)
        >>> context = await manager.get_context(conversation_id)
    """

    def __init__(self, storage: StateStorage) -> None:
        """Initialize state manager with storage backend.

        Args:
            storage: Storage backend to use.
        """
        self.storage = storage
        logger.info(f"Initialized conversation state manager with {type(storage).__name__}")

    async def get_state(self, conversation_id: str) -> ConversationState:
        """Get or create conversation state.

        Args:
            conversation_id: Conversation ID to get state for.

        Returns:
            Conversation state (creates new if not found).
        """
        state = await self.storage.get_state(conversation_id)

        if state is None:
            # Create new state
            state = ConversationState(
                conversation_id=conversation_id,
                pending_command=None,
                pending_approval_id=None,
                last_message_id=None,
                turn_count=0,
                iteration=0,
                original_prompt=None,
                handled_by_ssm_tracker=False,
            )
            await self.storage.set_state(state)
            logger.info(f"Created new state for conversation {conversation_id}")

        return state

    async def save_state(self, state: ConversationState, ttl_seconds: int = 3600) -> None:
        """Save conversation state.

        Args:
            state: Conversation state to save.
            ttl_seconds: Time-to-live in seconds.
        """
        state.updated_at = datetime.now(tz=UTC)
        await self.storage.set_state(state, ttl_seconds)

    async def get_context(self, conversation_id: str) -> ConversationContext | None:
        """Get conversation context.

        Args:
            conversation_id: Conversation ID to get context for.

        Returns:
            Conversation context if found, None otherwise.
        """
        return await self.storage.get_context(conversation_id)

    async def save_context(self, context: ConversationContext, ttl_seconds: int = 86400) -> None:
        """Save conversation context.

        Args:
            context: Conversation context to save.
            ttl_seconds: Time-to-live in seconds.
        """
        context.update_timestamp()
        await self.storage.set_context(context, ttl_seconds)

    async def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Get approval request.

        Args:
            approval_id: Approval request ID.

        Returns:
            Approval request if found, None otherwise.
        """
        return await self.storage.get_approval(approval_id)

    async def save_approval(self, approval: ApprovalRequest) -> None:
        """Save approval request.

        Args:
            approval: Approval request to save.
        """
        await self.storage.set_approval(approval)

    async def list_pending_approvals(self, user_id: str) -> list[ApprovalRequest]:
        """List pending approvals for a user.

        Args:
            user_id: User ID to get approvals for.

        Returns:
            List of pending approval requests.
        """
        return await self.storage.list_pending_approvals(user_id)

    async def clear_conversation(self, conversation_id: str) -> None:
        """Clear all data for a conversation.

        Args:
            conversation_id: Conversation ID to clear.
        """
        await self.storage.delete_state(conversation_id)
        await self.storage.delete_context(conversation_id)
        logger.info(f"Cleared all data for conversation {conversation_id}")

    async def add_command_to_history(self, entry: CommandHistoryEntry) -> None:
        """Add command to history.

        Args:
            entry: Command history entry to store.
        """
        await self.storage.add_command_history(entry)

    async def get_user_command_history(
        self, user_id: str, limit: int = 10
    ) -> list[CommandHistoryEntry]:
        """Get recent command history for a user.

        Args:
            user_id: User ID to get history for.
            limit: Maximum number of entries to return.

        Returns:
            List of command history entries, most recent first.
        """
        return await self.storage.get_recent_commands(user_id, limit)

    async def get_command_by_id(self, command_id: str) -> CommandHistoryEntry | None:
        """Get specific command history entry.

        Args:
            command_id: Command ID to retrieve.

        Returns:
            Command history entry if found, None otherwise.
        """
        return await self.storage.get_command_history(command_id)


def create_state_manager(storage_type: str = "memory") -> ConversationStateManager:
    """Create a conversation state manager with the specified storage backend.

    Args:
        storage_type: Type of storage backend ("memory" or "redis").

    Returns:
        Configured ConversationStateManager instance.

    Raises:
        ValueError: If storage_type is not supported.

    Example:
        >>> manager = create_state_manager("memory")
        >>> # Use for development and testing
    """
    if storage_type == "memory":
        storage = InMemoryStateStorage()
    elif storage_type == "redis":
        # TODO: Implement RedisStateStorage
        raise NotImplementedError("Redis storage not yet implemented. Use 'memory' for now.")
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")

    return ConversationStateManager(storage)
