"""Unit tests for command history in state storage.

This module tests the command history functionality in InMemoryStateStorage
and ConversationStateManager.
"""

import pytest

from ohlala_smartops.bot.state import ConversationStateManager, InMemoryStateStorage
from ohlala_smartops.models.command_history import CommandHistoryEntry


class TestInMemoryStateStorageCommandHistory:
    """Test suite for command history in InMemoryStateStorage."""

    @pytest.fixture
    def storage(self) -> InMemoryStateStorage:
        """Provide a fresh InMemoryStateStorage instance."""
        return InMemoryStateStorage()

    @pytest.mark.asyncio
    async def test_add_command_history(self, storage: InMemoryStateStorage) -> None:
        """Test adding a command to history."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        await storage.add_command_history(entry)

        # Verify entry was stored
        retrieved = await storage.get_command_history("cmd-123")
        assert retrieved is not None
        assert retrieved.command_id == "cmd-123"
        assert retrieved.user_id == "user@example.com"

    @pytest.mark.asyncio
    async def test_get_recent_commands_empty(self, storage: InMemoryStateStorage) -> None:
        """Test getting recent commands when history is empty."""
        commands = await storage.get_recent_commands("user@example.com", limit=10)

        assert commands == []

    @pytest.mark.asyncio
    async def test_get_recent_commands_single_user(self, storage: InMemoryStateStorage) -> None:
        """Test getting recent commands for a single user."""
        # Add multiple commands for one user
        for i in range(5):
            entry = CommandHistoryEntry.create(
                command_id=f"cmd-{i}",
                user_id="user@example.com",
                description=f"Command {i}",
            )
            await storage.add_command_history(entry)

        # Retrieve commands
        commands = await storage.get_recent_commands("user@example.com", limit=10)

        assert len(commands) == 5
        # Should be in reverse chronological order (most recent first)
        assert commands[0].command_id == "cmd-4"
        assert commands[4].command_id == "cmd-0"

    @pytest.mark.asyncio
    async def test_get_recent_commands_limit(self, storage: InMemoryStateStorage) -> None:
        """Test that limit parameter is respected."""
        # Add 10 commands
        for i in range(10):
            entry = CommandHistoryEntry.create(
                command_id=f"cmd-{i}",
                user_id="user@example.com",
                description=f"Command {i}",
            )
            await storage.add_command_history(entry)

        # Request only 3
        commands = await storage.get_recent_commands("user@example.com", limit=3)

        assert len(commands) == 3
        # Should be the 3 most recent
        assert commands[0].command_id == "cmd-9"
        assert commands[1].command_id == "cmd-8"
        assert commands[2].command_id == "cmd-7"

    @pytest.mark.asyncio
    async def test_get_recent_commands_user_isolation(self, storage: InMemoryStateStorage) -> None:
        """Test that commands are isolated per user."""
        # Add commands for user1
        for i in range(3):
            entry = CommandHistoryEntry.create(
                command_id=f"cmd-user1-{i}",
                user_id="user1@example.com",
                description=f"User1 Command {i}",
            )
            await storage.add_command_history(entry)

        # Add commands for user2
        for i in range(2):
            entry = CommandHistoryEntry.create(
                command_id=f"cmd-user2-{i}",
                user_id="user2@example.com",
                description=f"User2 Command {i}",
            )
            await storage.add_command_history(entry)

        # Retrieve for user1
        user1_commands = await storage.get_recent_commands("user1@example.com", limit=10)
        assert len(user1_commands) == 3
        assert all("user1" in cmd.command_id for cmd in user1_commands)

        # Retrieve for user2
        user2_commands = await storage.get_recent_commands("user2@example.com", limit=10)
        assert len(user2_commands) == 2
        assert all("user2" in cmd.command_id for cmd in user2_commands)

    @pytest.mark.asyncio
    async def test_command_history_limit_100_per_user(self, storage: InMemoryStateStorage) -> None:
        """Test that command history is limited to 100 entries per user."""
        # Add 150 commands
        for i in range(150):
            entry = CommandHistoryEntry.create(
                command_id=f"cmd-{i}",
                user_id="user@example.com",
                description=f"Command {i}",
            )
            await storage.add_command_history(entry)

        # Should only have 100 most recent
        commands = await storage.get_recent_commands("user@example.com", limit=150)
        assert len(commands) == 100

        # Should have commands 50-149 (most recent 100)
        assert commands[0].command_id == "cmd-149"
        assert commands[99].command_id == "cmd-50"

        # Oldest commands (0-49) should be gone
        old_command = await storage.get_command_history("cmd-0")
        assert old_command is None

    @pytest.mark.asyncio
    async def test_get_command_history_by_id(self, storage: InMemoryStateStorage) -> None:
        """Test retrieving specific command by ID."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-specific",
            user_id="user@example.com",
            description="Specific command",
            instance_ids=["i-abc123"],
        )
        await storage.add_command_history(entry)

        retrieved = await storage.get_command_history("cmd-specific")

        assert retrieved is not None
        assert retrieved.command_id == "cmd-specific"
        assert retrieved.instance_ids == ["i-abc123"]

    @pytest.mark.asyncio
    async def test_get_command_history_nonexistent(self, storage: InMemoryStateStorage) -> None:
        """Test getting non-existent command returns None."""
        retrieved = await storage.get_command_history("cmd-nonexistent")

        assert retrieved is None


class TestConversationStateManagerCommandHistory:
    """Test suite for command history in ConversationStateManager."""

    @pytest.fixture
    def manager(self) -> ConversationStateManager:
        """Provide a ConversationStateManager with in-memory storage."""
        storage = InMemoryStateStorage()
        return ConversationStateManager(storage)

    @pytest.mark.asyncio
    async def test_add_command_to_history(self, manager: ConversationStateManager) -> None:
        """Test adding command through manager."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-123",
            user_id="user@example.com",
            description="Test command",
        )

        await manager.add_command_to_history(entry)

        # Verify through manager
        retrieved = await manager.get_command_by_id("cmd-123")
        assert retrieved is not None
        assert retrieved.command_id == "cmd-123"

    @pytest.mark.asyncio
    async def test_get_user_command_history(self, manager: ConversationStateManager) -> None:
        """Test getting user command history through manager."""
        # Add commands
        for i in range(5):
            entry = CommandHistoryEntry.create(
                command_id=f"cmd-{i}",
                user_id="user@example.com",
                description=f"Command {i}",
            )
            await manager.add_command_to_history(entry)

        # Retrieve through manager
        commands = await manager.get_user_command_history("user@example.com", limit=10)

        assert len(commands) == 5
        assert commands[0].command_id == "cmd-4"  # Most recent first

    @pytest.mark.asyncio
    async def test_get_user_command_history_with_limit(
        self, manager: ConversationStateManager
    ) -> None:
        """Test limit parameter in manager."""
        # Add 10 commands
        for i in range(10):
            entry = CommandHistoryEntry.create(
                command_id=f"cmd-{i}",
                user_id="user@example.com",
                description=f"Command {i}",
            )
            await manager.add_command_to_history(entry)

        # Get only 3
        commands = await manager.get_user_command_history("user@example.com", limit=3)

        assert len(commands) == 3

    @pytest.mark.asyncio
    async def test_get_command_by_id(self, manager: ConversationStateManager) -> None:
        """Test getting command by ID through manager."""
        entry = CommandHistoryEntry.create(
            command_id="cmd-specific",
            user_id="user@example.com",
            description="Specific command",
        )
        await manager.add_command_to_history(entry)

        retrieved = await manager.get_command_by_id("cmd-specific")

        assert retrieved is not None
        assert retrieved.command_id == "cmd-specific"

    @pytest.mark.asyncio
    async def test_get_command_by_id_nonexistent(self, manager: ConversationStateManager) -> None:
        """Test getting nonexistent command returns None."""
        retrieved = await manager.get_command_by_id("cmd-nonexistent")

        assert retrieved is None
