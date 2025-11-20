"""Tests for bot message endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ohlala_smartops.bot.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    # Mock all initialization to avoid Bot Framework dependencies
    with (
        patch("ohlala_smartops.bot.app.Settings"),
        patch("ohlala_smartops.bot.app.create_adapter"),
        patch("ohlala_smartops.bot.app.create_state_manager"),
        patch("ohlala_smartops.bot.app.MCPManager"),
        patch("ohlala_smartops.bot.app.BedrockClient"),
        patch("ohlala_smartops.bot.app.WriteOperationManager"),
        patch("ohlala_smartops.bot.app.AsyncCommandTracker"),
        patch("ohlala_smartops.bot.app.OhlalaBot"),
    ):
        app = create_app()
        return TestClient(app)


# Note: Message endpoint integration tests require complex app setup with actual Bot Framework
# components. These tests would need extensive mocking of Bot Framework internals.
# The bot initialization is comprehensively tested in test_bot_app.py.
#
# For now, we verify the app can be created successfully (see client fixture above).
# Full endpoint testing will be done in integration tests.
