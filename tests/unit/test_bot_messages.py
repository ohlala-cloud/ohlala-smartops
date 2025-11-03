"""Tests for bot message endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ohlala_smartops.bot.app import create_app
from ohlala_smartops.bot.messages import (
    get_adapter,
    get_handler,
    get_state_manager,
    initialize_bot_services,
)
from ohlala_smartops.config.settings import Settings


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    # Mock the adapter and OhlalaBot creation to avoid Bot Framework initialization
    with (
        patch("ohlala_smartops.bot.messages.create_adapter", return_value=MagicMock()),
        patch("ohlala_smartops.bot.messages.OhlalaBot"),
    ):
        app = create_app()
        return TestClient(app)


# Note: Message endpoint integration tests require complex app setup
# These are better tested as integration tests with actual Bot Framework
# For now, we focus on unit testing the helper functions


class TestGetterFunctions:
    """Test suite for getter functions."""

    @patch("ohlala_smartops.bot.messages._ensure_initialized")
    @patch("ohlala_smartops.bot.messages._adapter")
    def test_get_adapter(self, mock_adapter: MagicMock, mock_ensure: MagicMock) -> None:
        """Test get_adapter function."""
        mock_adapter_instance = MagicMock()
        mock_adapter.__bool__ = MagicMock(return_value=True)
        mock_adapter.return_value = mock_adapter_instance

        # Since we patched _adapter directly, it should return it
        get_adapter()

        mock_ensure.assert_called_once()

    @patch("ohlala_smartops.bot.messages._ensure_initialized")
    @patch("ohlala_smartops.bot.messages._handler")
    def test_get_handler(self, mock_handler: MagicMock, mock_ensure: MagicMock) -> None:
        """Test get_handler function."""
        get_handler()

        mock_ensure.assert_called_once()

    @patch("ohlala_smartops.bot.messages._ensure_initialized")
    @patch("ohlala_smartops.bot.messages._handler")
    def test_get_state_manager(self, mock_handler: MagicMock, mock_ensure: MagicMock) -> None:
        """Test get_state_manager function."""
        # Mock the handler to have a state_manager attribute
        mock_state_manager = MagicMock()
        mock_handler.state_manager = mock_state_manager
        mock_handler.__bool__ = MagicMock(return_value=True)

        result = get_state_manager()

        mock_ensure.assert_called_once()
        assert result == mock_state_manager


class TestInitializeBotServices:
    """Test suite for initialize_bot_services function."""

    @patch("ohlala_smartops.bot.messages.create_adapter")
    @patch("ohlala_smartops.bot.messages.OhlalaBot")
    def test_initialize_bot_services_with_settings(
        self,
        mock_bot_class: MagicMock,
        mock_create_adapter: MagicMock,
    ) -> None:
        """Test initializing bot services with custom settings."""
        settings = Settings()

        initialize_bot_services(settings)

        mock_create_adapter.assert_called_once_with(settings)
        mock_bot_class.assert_called_once()

    @patch("ohlala_smartops.bot.messages.create_adapter")
    @patch("ohlala_smartops.bot.messages.OhlalaBot")
    @patch("ohlala_smartops.bot.messages.Settings")
    def test_initialize_bot_services_without_settings(
        self,
        mock_settings_class: MagicMock,
        mock_bot_class: MagicMock,
        mock_create_adapter: MagicMock,
    ) -> None:
        """Test initializing bot services without settings."""
        # Should create Settings if None provided
        initialize_bot_services(None)

        mock_create_adapter.assert_called_once()
        mock_bot_class.assert_called_once()
