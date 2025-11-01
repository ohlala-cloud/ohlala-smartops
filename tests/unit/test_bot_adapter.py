"""Tests for Bot Framework adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ohlala_smartops.bot.adapter import OhlalaAdapter, create_adapter
from ohlala_smartops.config.settings import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings."""
    return Settings(
        microsoft_app_id="test-app-id",
        microsoft_app_password="test-password",
        microsoft_app_tenant_id="test-tenant-id",
    )


@pytest.fixture
def adapter(mock_settings: Settings) -> OhlalaAdapter:
    """Create an adapter instance."""
    with patch("ohlala_smartops.bot.adapter.ConfigurationBotFrameworkAuthentication"):
        return OhlalaAdapter(mock_settings)


class TestOhlalaAdapterInit:
    """Test suite for OhlalaAdapter initialization."""

    @patch("ohlala_smartops.bot.adapter.SimpleCredentialProvider")
    @patch("ohlala_smartops.bot.adapter.ConfigurationBotFrameworkAuthentication")
    def test_adapter_initialization(
        self,
        mock_auth: MagicMock,
        mock_creds: MagicMock,
        mock_settings: Settings,
    ) -> None:
        """Test adapter initializes correctly."""
        adapter = OhlalaAdapter(mock_settings)

        assert adapter.settings == mock_settings
        mock_creds.assert_called_once_with(app_id="test-app-id", password="test-password")
        mock_auth.assert_called_once()

    @patch("ohlala_smartops.bot.adapter.SimpleCredentialProvider")
    @patch("ohlala_smartops.bot.adapter.ConfigurationBotFrameworkAuthentication")
    def test_adapter_sets_error_handler(
        self,
        mock_auth: MagicMock,
        mock_creds: MagicMock,
        mock_settings: Settings,
    ) -> None:
        """Test adapter sets error handler."""
        adapter = OhlalaAdapter(mock_settings)

        assert adapter.on_turn_error is not None


class TestOnError:
    """Test suite for error handling."""

    @pytest.mark.asyncio
    async def test_on_error_sends_message(self, adapter: OhlalaAdapter) -> None:
        """Test error handler sends message to user."""
        mock_context = MagicMock()
        mock_context.send_activity = AsyncMock()
        mock_context.activity = MagicMock()
        mock_context.activity.type = "message"
        mock_context.activity.from_property = MagicMock()
        mock_context.activity.from_property.id = "user123"
        mock_context.activity.text = "test message"

        error = Exception("Test error")

        await adapter._on_error(mock_context, error)

        mock_context.send_activity.assert_called_once()
        call_args = mock_context.send_activity.call_args[0][0]
        assert "error occurred" in call_args.lower()

    @pytest.mark.asyncio
    async def test_on_error_handles_send_failure(self, adapter: OhlalaAdapter) -> None:
        """Test error handler when sending error message fails."""
        mock_context = MagicMock()
        mock_context.send_activity = AsyncMock(side_effect=Exception("Send failed"))
        mock_context.activity = MagicMock()
        mock_context.activity.type = "message"
        mock_context.activity.from_property = MagicMock()
        mock_context.activity.from_property.id = "user123"
        mock_context.activity.text = "test"

        error = Exception("Test error")

        # Should not raise exception
        await adapter._on_error(mock_context, error)

    @pytest.mark.asyncio
    async def test_on_error_logs_activity_details(self, adapter: OhlalaAdapter) -> None:
        """Test error handler logs activity details."""
        mock_context = MagicMock()
        mock_context.send_activity = AsyncMock()
        mock_context.activity = MagicMock()
        mock_context.activity.type = "message"
        mock_context.activity.text = "A" * 200  # Long text to test truncation
        mock_context.activity.from_property = MagicMock()
        mock_context.activity.from_property.id = "user123"

        error = Exception("Test error")

        await adapter._on_error(mock_context, error)

        # Should complete without error
        mock_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error_with_no_from_property(self, adapter: OhlalaAdapter) -> None:
        """Test error handler when from_property is None."""
        mock_context = MagicMock()
        mock_context.send_activity = AsyncMock()
        mock_context.activity = MagicMock()
        mock_context.activity.type = "message"
        mock_context.activity.from_property = None
        mock_context.activity.text = "test"

        error = Exception("Test error")

        # Should handle gracefully
        await adapter._on_error(mock_context, error)

        mock_context.send_activity.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_error_with_no_text(self, adapter: OhlalaAdapter) -> None:
        """Test error handler when activity has no text."""
        mock_context = MagicMock()
        mock_context.send_activity = AsyncMock()
        mock_context.activity = MagicMock()
        mock_context.activity.type = "message"
        mock_context.activity.from_property = MagicMock()
        mock_context.activity.from_property.id = "user123"
        mock_context.activity.text = None

        error = Exception("Test error")

        await adapter._on_error(mock_context, error)

        mock_context.send_activity.assert_called_once()


class TestSendProactiveMessage:
    """Test suite for send_proactive_message."""

    @pytest.mark.asyncio
    async def test_send_proactive_message_with_string(self, adapter: OhlalaAdapter) -> None:
        """Test sending proactive message with string."""
        mock_conversation_ref = MagicMock()
        mock_conversation_ref.conversation = MagicMock()
        mock_conversation_ref.conversation.id = "conv123"

        adapter.continue_conversation = AsyncMock()

        await adapter.send_proactive_message(mock_conversation_ref, "Hello from bot!")

        adapter.continue_conversation.assert_called_once()
        call_kwargs = adapter.continue_conversation.call_args[1]
        assert call_kwargs["reference"] == mock_conversation_ref
        assert call_kwargs["bot_app_id"] == adapter.settings.microsoft_app_id

    @pytest.mark.asyncio
    async def test_send_proactive_message_with_activity(self, adapter: OhlalaAdapter) -> None:
        """Test sending proactive message with Activity object."""
        mock_conversation_ref = MagicMock()
        mock_conversation_ref.conversation = MagicMock()
        mock_conversation_ref.conversation.id = "conv123"

        mock_activity = MagicMock()
        adapter.continue_conversation = AsyncMock()

        await adapter.send_proactive_message(mock_conversation_ref, mock_activity)

        adapter.continue_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_proactive_message_error(self, adapter: OhlalaAdapter) -> None:
        """Test error handling in send_proactive_message."""
        mock_conversation_ref = MagicMock()
        mock_conversation_ref.conversation = MagicMock()
        mock_conversation_ref.conversation.id = "conv123"

        adapter.continue_conversation = AsyncMock(side_effect=Exception("Send failed"))

        with pytest.raises(Exception, match="Send failed"):
            await adapter.send_proactive_message(mock_conversation_ref, "Hello")

    @pytest.mark.asyncio
    async def test_send_proactive_callback_sends_string(self, adapter: OhlalaAdapter) -> None:
        """Test that proactive callback sends string message."""
        mock_conversation_ref = MagicMock()
        mock_conversation_ref.conversation = MagicMock()
        mock_conversation_ref.conversation.id = "conv123"

        # Capture the callback
        callback_func = None

        async def capture_callback(reference, callback, bot_app_id):
            nonlocal callback_func
            callback_func = callback

        adapter.continue_conversation = AsyncMock(side_effect=capture_callback)

        await adapter.send_proactive_message(mock_conversation_ref, "Test message")

        # Now call the captured callback
        mock_turn_context = MagicMock()
        mock_turn_context.send_activity = AsyncMock()

        if callback_func:
            await callback_func(mock_turn_context)
            mock_turn_context.send_activity.assert_called_once_with("Test message")

    @pytest.mark.asyncio
    async def test_send_proactive_callback_sends_activity(self, adapter: OhlalaAdapter) -> None:
        """Test that proactive callback sends Activity object."""
        mock_conversation_ref = MagicMock()
        mock_conversation_ref.conversation = MagicMock()
        mock_conversation_ref.conversation.id = "conv123"

        mock_activity = MagicMock()

        # Capture the callback
        callback_func = None

        async def capture_callback(reference, callback, bot_app_id):
            nonlocal callback_func
            callback_func = callback

        adapter.continue_conversation = AsyncMock(side_effect=capture_callback)

        await adapter.send_proactive_message(mock_conversation_ref, mock_activity)

        # Now call the captured callback
        mock_turn_context = MagicMock()
        mock_turn_context.send_activity = AsyncMock()

        if callback_func:
            await callback_func(mock_turn_context)
            mock_turn_context.send_activity.assert_called_once_with(mock_activity)


class TestCreateAdapter:
    """Test suite for create_adapter factory function."""

    @patch("ohlala_smartops.bot.adapter.OhlalaAdapter")
    def test_create_adapter_with_settings(
        self, mock_adapter_class: MagicMock, mock_settings: Settings
    ) -> None:
        """Test creating adapter with provided settings."""
        create_adapter(mock_settings)

        mock_adapter_class.assert_called_once_with(mock_settings)

    @patch("ohlala_smartops.bot.adapter.OhlalaAdapter")
    @patch("ohlala_smartops.bot.adapter.Settings")
    def test_create_adapter_without_settings(
        self, mock_settings_class: MagicMock, mock_adapter_class: MagicMock
    ) -> None:
        """Test creating adapter without settings."""
        mock_settings_instance = MagicMock()
        mock_settings_class.return_value = mock_settings_instance

        create_adapter()

        mock_settings_class.assert_called_once()
        mock_adapter_class.assert_called_once_with(mock_settings_instance)
