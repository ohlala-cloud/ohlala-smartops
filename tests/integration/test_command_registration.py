"""Integration tests for command registration.

This module tests that all commands are properly registered and accessible
through the bot's command registry.

Phase 6: Command Registration & Integration.
"""

import pytest

from ohlala_smartops.bot.message_handler import MessageHandler
from ohlala_smartops.bot.teams_bot import OhlalaBot
from ohlala_smartops.commands.registry import register_commands


class TestCommandRegistration:
    """Test suite for command registration."""

    def test_register_commands_populates_registry(self) -> None:
        """Test that register_commands populates the message handler registry."""
        # Create a message handler with minimal dependencies
        message_handler = MessageHandler(
            bedrock_client=None,  # type: ignore[arg-type]
            mcp_manager=None,  # type: ignore[arg-type]
        )

        # Initially, registry should be empty
        assert len(message_handler._command_registry) == 0

        # Register commands
        register_commands(message_handler)

        # After registration, registry should contain all 15 commands
        assert len(message_handler._command_registry) == 15

    def test_all_expected_commands_registered(self) -> None:
        """Test that all expected commands are registered with correct names."""
        message_handler = MessageHandler(
            bedrock_client=None,  # type: ignore[arg-type]
            mcp_manager=None,  # type: ignore[arg-type]
        )

        register_commands(message_handler)

        # List of all expected command names
        expected_commands = [
            # Phase 5A: Core Commands
            "help",
            "status",
            "history",
            # Phase 5B: Instance Lifecycle
            "list",
            "start",
            "stop",
            "reboot",
            # Phase 5C: Monitoring & Cost Analysis
            "details",
            "metrics",
            "costs",
            # Phase 5D: Advanced Operations
            "exec",
            "commands",
            # Phase 5E: Resource Tagging
            "tag",
            "untag",
            "find-tags",
        ]

        # Verify all expected commands are registered
        for command_name in expected_commands:
            assert (
                command_name in message_handler._command_registry
            ), f"Command '{command_name}' not registered"

    def test_registered_commands_are_callable(self) -> None:
        """Test that registered commands can be instantiated."""
        message_handler = MessageHandler(
            bedrock_client=None,  # type: ignore[arg-type]
            mcp_manager=None,  # type: ignore[arg-type]
        )

        register_commands(message_handler)

        # Try to instantiate each registered command
        for command_name, command_class in message_handler._command_registry.items():
            command_instance = command_class()
            assert command_instance is not None
            assert command_instance.name == command_name
            assert hasattr(command_instance, "execute")
            assert callable(command_instance.execute)

    def test_ohlala_bot_registers_commands_on_init(self) -> None:
        """Test that OhlalaBot automatically registers commands on initialization."""
        # Create OhlalaBot instance
        bot = OhlalaBot()

        # Verify commands are registered in the message handler
        assert len(bot.message_handler._command_registry) == 15

        # Verify specific commands are available
        assert "help" in bot.message_handler._command_registry
        assert "list" in bot.message_handler._command_registry
        assert "start" in bot.message_handler._command_registry
        assert "tag" in bot.message_handler._command_registry

    def test_command_registry_no_duplicates(self) -> None:
        """Test that command registration doesn't create duplicates."""
        message_handler = MessageHandler(
            bedrock_client=None,  # type: ignore[arg-type]
            mcp_manager=None,  # type: ignore[arg-type]
        )

        # Register commands twice
        register_commands(message_handler)
        register_commands(message_handler)

        # Should still have exactly 15 commands (no duplicates)
        assert len(message_handler._command_registry) == 15

    def test_command_classes_have_required_properties(self) -> None:
        """Test that all registered command classes have required properties."""
        message_handler = MessageHandler(
            bedrock_client=None,  # type: ignore[arg-type]
            mcp_manager=None,  # type: ignore[arg-type]
        )

        register_commands(message_handler)

        for command_class in message_handler._command_registry.values():
            command = command_class()

            # Verify required properties exist
            assert hasattr(command, "name"), f"{command_class} missing 'name' property"
            assert hasattr(command, "description"), f"{command_class} missing 'description'"
            assert hasattr(command, "usage"), f"{command_class} missing 'usage' property"
            assert hasattr(command, "execute"), f"{command_class} missing 'execute' method"

            # Verify property types
            assert isinstance(command.name, str)
            assert isinstance(command.description, str)
            assert isinstance(command.usage, str)


class TestCommandLookup:
    """Test suite for command lookup functionality."""

    @pytest.mark.asyncio
    async def test_help_command_lookup(self) -> None:
        """Test that help command can be looked up and has correct metadata."""
        bot = OhlalaBot()

        # Look up help command
        help_command_class = bot.message_handler._command_registry.get("help")
        assert help_command_class is not None

        # Instantiate and verify
        help_command = help_command_class()
        assert help_command.name == "help"
        assert "commands" in help_command.description.lower()

    @pytest.mark.asyncio
    async def test_tag_command_lookup(self) -> None:
        """Test that tag command can be looked up and has correct metadata."""
        bot = OhlalaBot()

        # Look up tag command
        tag_command_class = bot.message_handler._command_registry.get("tag")
        assert tag_command_class is not None

        # Instantiate and verify
        tag_command = tag_command_class()
        assert tag_command.name == "tag"
        assert "tag" in tag_command.description.lower()
        assert "instance" in tag_command.usage.lower()

    @pytest.mark.asyncio
    async def test_nonexistent_command_returns_none(self) -> None:
        """Test that looking up a non-existent command returns None."""
        bot = OhlalaBot()

        # Try to look up command that doesn't exist
        nonexistent = bot.message_handler._command_registry.get("nonexistent")
        assert nonexistent is None


class TestCommandRegistryIntegrity:
    """Test suite for command registry integrity."""

    def test_all_commands_unique_names(self) -> None:
        """Test that all commands have unique names."""
        message_handler = MessageHandler(
            bedrock_client=None,  # type: ignore[arg-type]
            mcp_manager=None,  # type: ignore[arg-type]
        )

        register_commands(message_handler)

        # Get all command names
        command_names = [
            command_class().name for command_class in message_handler._command_registry.values()
        ]

        # Verify no duplicates
        assert len(command_names) == len(set(command_names)), "Duplicate command names found"

    def test_registry_keys_match_command_names(self) -> None:
        """Test that registry keys match the actual command names."""
        message_handler = MessageHandler(
            bedrock_client=None,  # type: ignore[arg-type]
            mcp_manager=None,  # type: ignore[arg-type]
        )

        register_commands(message_handler)

        # Verify each registry key matches the command's name property
        for key, command_class in message_handler._command_registry.items():
            command = command_class()
            assert (
                key == command.name
            ), f"Registry key '{key}' doesn't match command name '{command.name}'"
