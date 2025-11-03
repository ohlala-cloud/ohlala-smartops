"""Microsoft Teams bot implementation for Ohlala SmartOps.

This package contains the FastAPI application, Bot Framework adapter,
activity handlers, and conversation state management.
"""

from ohlala_smartops.bot.adapter import OhlalaAdapter, create_adapter
from ohlala_smartops.bot.app import app, create_app
from ohlala_smartops.bot.handlers import OhlalaActivityHandler
from ohlala_smartops.bot.messages import (
    get_adapter,
    get_handler,
    get_state_manager,
    initialize_bot_services,
)
from ohlala_smartops.bot.state import (
    ConversationStateManager,
    InMemoryStateStorage,
    StateStorage,
    create_state_manager,
)
from ohlala_smartops.bot.teams_bot import OhlalaBot

__all__ = [
    # State management
    "ConversationStateManager",
    "InMemoryStateStorage",
    "OhlalaActivityHandler",
    # Bot Framework components
    "OhlalaAdapter",
    # Bot orchestrator
    "OhlalaBot",
    "StateStorage",
    # FastAPI app
    "app",
    "create_adapter",
    "create_app",
    "create_state_manager",
    # Service accessors
    "get_adapter",
    "get_handler",
    "get_state_manager",
    "initialize_bot_services",
]
