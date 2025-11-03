"""Command registry module - Register all bot commands.

This module provides the central command registration functionality for the bot.
It imports all command classes and registers them with the message handler.

Phase 6: Command Registration & Integration.
"""

import logging
from typing import TYPE_CHECKING, Final

from ohlala_smartops.commands.commands_list import CommandsListCommand
from ohlala_smartops.commands.costs import CostsCommand
from ohlala_smartops.commands.exec import ExecCommand
from ohlala_smartops.commands.find_by_tags import FindByTagsCommand
from ohlala_smartops.commands.help import HelpCommand
from ohlala_smartops.commands.instance_details import InstanceDetailsCommand
from ohlala_smartops.commands.list_instances import ListInstancesCommand
from ohlala_smartops.commands.metrics import MetricsCommand
from ohlala_smartops.commands.reboot import RebootInstanceCommand
from ohlala_smartops.commands.start import StartInstanceCommand
from ohlala_smartops.commands.status import StatusCommand
from ohlala_smartops.commands.stop import StopInstanceCommand
from ohlala_smartops.commands.tag import TagCommand
from ohlala_smartops.commands.untag import UntagCommand

if TYPE_CHECKING:
    from ohlala_smartops.bot.message_handler import MessageHandler

logger: Final = logging.getLogger(__name__)


def register_commands(message_handler: "MessageHandler") -> None:
    """Register all bot commands with the message handler.

    This function instantiates and registers all available commands with the
    message handler's command registry. Each command is registered using its
    name property as the lookup key.

    Args:
        message_handler: The MessageHandler instance to register commands with.

    Example:
        >>> from ohlala_smartops.bot.message_handler import MessageHandler
        >>> handler = MessageHandler(turn_context, mcp_manager, bedrock_client)
        >>> register_commands(handler)
        >>> # All 14 commands are now registered and available

    Note:
        Commands are registered by their class type, not instances. The message
        handler will instantiate them as needed during command execution.
    """
    # Define all command classes to register
    command_classes = [
        # Phase 5A: Core Commands
        HelpCommand,
        StatusCommand,
        # Phase 5B: Instance Lifecycle
        ListInstancesCommand,
        StartInstanceCommand,
        StopInstanceCommand,
        RebootInstanceCommand,
        # Phase 5C: Monitoring & Cost Analysis
        InstanceDetailsCommand,
        MetricsCommand,
        CostsCommand,
        # Phase 5D: Advanced Operations
        ExecCommand,
        CommandsListCommand,
        # Phase 5E: Resource Tagging
        TagCommand,
        UntagCommand,
        FindByTagsCommand,
    ]

    logger.info(f"Registering {len(command_classes)} commands with message handler")

    # Register each command
    for command_class in command_classes:
        # Instantiate command to get its name
        command_instance = command_class()  # type: ignore[abstract]
        command_name = command_instance.name

        # Register the class (not instance) with the handler
        message_handler._command_registry[command_name] = command_class  # type: ignore[type-abstract]

        logger.debug(f"Registered command: /{command_name} -> {command_class.__name__}")

    logger.info(
        f"Command registration complete. "
        f"Available commands: {list(message_handler._command_registry.keys())}"
    )
