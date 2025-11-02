"""Tests for Bedrock AI client.

This module tests the BedrockClient class including:
- Basic Bedrock API calls
- Token tracking and budget limits
- Model fallback logic
- Guardrail handling
- Error handling and user-friendly messages
- Conversation context integration
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from botocore.exceptions import ClientError

from ohlala_smartops.ai.bedrock_client import (
    BedrockClient,
    BedrockClientError,
    BedrockGuardrailError,
    BedrockModelError,
)
from ohlala_smartops.bot.state import ConversationStateManager


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("ohlala_smartops.ai.bedrock_client.get_settings") as mock:
        settings = Mock()
        settings.aws_region = "us-east-1"
        settings.bedrock_guardrail_enabled = False
        settings.bedrock_guardrail_id = ""
        settings.bedrock_guardrail_version = "1"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_throttler():
    """Mock Bedrock throttler."""
    with patch("ohlala_smartops.ai.bedrock_client.BedrockThrottler") as mock:
        throttler = AsyncMock()
        throttler.__aenter__ = AsyncMock(return_value=throttler)
        throttler.__aexit__ = AsyncMock(return_value=None)
        mock.return_value = throttler
        yield throttler


@pytest.fixture
def mock_audit_logger():
    """Mock audit logger."""
    with patch("ohlala_smartops.ai.bedrock_client.AuditLogger") as mock:
        logger = Mock()
        mock.return_value = logger
        yield logger


@pytest.fixture
def mock_token_tracker():
    """Mock token tracker."""
    with patch("ohlala_smartops.ai.bedrock_client.TokenTracker") as mock:
        tracker = Mock()
        mock.return_value = tracker
        yield tracker


@pytest.fixture
def bedrock_client(mock_settings, mock_throttler, mock_audit_logger, mock_token_tracker):
    """Create a BedrockClient instance for testing."""
    return BedrockClient()


@pytest.fixture
def mock_bedrock_response():
    """Mock successful Bedrock response."""
    return {
        "content": [{"type": "text", "text": "This is a test response from Claude."}],
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "stop_reason": "end_turn",
    }


@pytest.fixture
def conversation_state():
    """Create a conversation state manager for testing."""
    return ConversationStateManager()


class TestBedrockClientInit:
    """Tests for BedrockClient initialization."""

    def test_init_with_defaults(self, mock_settings):
        """Test initialization with default parameters."""
        client = BedrockClient()

        assert client.settings == mock_settings.return_value
        assert client.model_selector is not None
        assert client.audit_logger is not None
        assert client.throttler is not None
        assert client.token_tracker is not None
        assert client.mcp_manager is None
        assert client._max_tool_attempts == 50

    def test_init_with_custom_components(self, mock_settings):
        """Test initialization with custom components."""
        custom_audit = Mock()
        custom_throttler = Mock()
        custom_tracker = Mock()
        custom_mcp = Mock()

        client = BedrockClient(
            mcp_manager=custom_mcp,
            audit_logger=custom_audit,
            throttler=custom_throttler,
            token_tracker=custom_tracker,
        )

        assert client.audit_logger == custom_audit
        assert client.throttler == custom_throttler
        assert client.token_tracker == custom_tracker
        assert client.mcp_manager == custom_mcp


class TestCallBedrock:
    """Tests for call_bedrock method."""

    @pytest.mark.asyncio
    async def test_simple_call_success(self, bedrock_client, mock_bedrock_response):
        """Test successful simple Bedrock call without context."""
        with (
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens", return_value=100
            ),
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
        ):
            mock_check.return_value = {
                "allowed": True,
                "warnings": [],
                "recommendations": [],
                "estimated_cost": 0.001,
            }

            with (
                patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation"),
                patch.object(bedrock_client, "_invoke_model_with_fallback") as mock_invoke,
            ):
                mock_invoke.return_value = mock_bedrock_response

                response = await bedrock_client.call_bedrock(prompt="Hello, Claude!")

                assert response == "This is a test response from Claude."
                mock_invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_with_conversation_context(
        self, bedrock_client, mock_bedrock_response, conversation_state
    ):
        """Test Bedrock call with conversation context."""
        # Add some conversation history
        conversation_state.add_message("user123", "user", "Previous message")
        conversation_state.add_message("user123", "assistant", "Previous response")

        with (
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens", return_value=150
            ),
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
        ):
            mock_check.return_value = {
                "allowed": True,
                "warnings": [],
                "recommendations": [],
                "estimated_cost": 0.002,
            }

            with (
                patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation"),
                patch.object(bedrock_client, "_invoke_model_with_fallback") as mock_invoke,
            ):
                mock_invoke.return_value = mock_bedrock_response

                response = await bedrock_client.call_bedrock(
                    prompt="Follow-up question",
                    user_id="user123",
                    conversation_state=conversation_state,
                )

                assert response == "This is a test response from Claude."
                # Verify conversation was updated
                assert len(conversation_state.get_messages("user123")) == 4

    @pytest.mark.asyncio
    async def test_call_blocked_by_token_limit(self, bedrock_client):
        """Test call blocked when model token limit exceeded."""
        with (
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens",
                return_value=300000,
            ),
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
        ):
            mock_check.return_value = {
                "allowed": False,
                "warnings": ["Input would exceed model limit of 200,000 tokens"],
                "recommendations": ["Try breaking your request into smaller parts"],
                "estimated_cost": 0.0,
            }

            with pytest.raises(BedrockClientError) as exc_info:
                await bedrock_client.call_bedrock(prompt="Very long prompt...")

            assert "Model Token Limit Exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_with_budget_warning(self, bedrock_client, mock_bedrock_response):
        """Test call proceeds with budget warning but doesn't block."""
        with (
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens", return_value=100
            ),
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
        ):
            mock_check.return_value = {
                "allowed": True,
                "warnings": ["Daily budget 90% consumed"],
                "recommendations": ["Monitor usage"],
                "estimated_cost": 0.001,
            }

            with (
                patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation"),
                patch.object(bedrock_client, "_invoke_model_with_fallback") as mock_invoke,
            ):
                mock_invoke.return_value = mock_bedrock_response

                # Should not raise, just log warning
                response = await bedrock_client.call_bedrock(prompt="Hello")

                assert response == "This is a test response from Claude."

    @pytest.mark.asyncio
    async def test_call_with_custom_parameters(self, bedrock_client, mock_bedrock_response):
        """Test call with custom max_tokens and temperature."""
        with (
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens", return_value=100
            ),
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
        ):
            mock_check.return_value = {
                "allowed": True,
                "warnings": [],
                "recommendations": [],
                "estimated_cost": 0.001,
            }

            with (
                patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation"),
                patch.object(bedrock_client, "_invoke_model_with_fallback") as mock_invoke,
            ):
                mock_invoke.return_value = mock_bedrock_response

                response = await bedrock_client.call_bedrock(
                    prompt="Test", max_tokens=500, temperature=0.5
                )

                assert response == "This is a test response from Claude."
                # Verify custom parameters were used
                call_args = mock_invoke.call_args[0][0]
                assert call_args["max_tokens"] == 500
                assert call_args["temperature"] == 0.5


class TestInvokeModelWithFallback:
    """Tests for _invoke_model_with_fallback method."""

    @pytest.mark.asyncio
    async def test_primary_model_success(self, bedrock_client, mock_bedrock_response):
        """Test successful invocation with primary model."""
        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.invoke_model = AsyncMock()

        # Mock the response
        mock_response = {"body": AsyncMock()}
        mock_response["body"].read = AsyncMock(
            return_value=json.dumps(mock_bedrock_response).encode()
        )
        mock_bedrock_client.invoke_model.return_value = mock_response

        with patch("aioboto3.Session") as mock_session:
            mock_session.return_value.client = AsyncMock()
            mock_session.return_value.client.return_value.__aenter__ = AsyncMock(
                return_value=mock_bedrock_client
            )
            mock_session.return_value.client.return_value.__aexit__ = AsyncMock()

            request = {"messages": [{"role": "user", "content": "test"}]}
            response = await bedrock_client._invoke_model_with_fallback(request)

            assert response == mock_bedrock_response
            mock_bedrock_client.invoke_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, bedrock_client, mock_bedrock_response):
        """Test fallback to secondary model when primary fails."""
        mock_bedrock_client = AsyncMock()

        # First call fails, second succeeds
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        mock_bedrock_client.invoke_model = AsyncMock(
            side_effect=[
                ClientError(error_response, "InvokeModel"),
                {
                    "body": AsyncMock(
                        read=AsyncMock(return_value=json.dumps(mock_bedrock_response).encode())
                    )
                },
            ]
        )

        with patch("aioboto3.Session") as mock_session:
            mock_session.return_value.client = AsyncMock()
            mock_session.return_value.client.return_value.__aenter__ = AsyncMock(
                return_value=mock_bedrock_client
            )
            mock_session.return_value.client.return_value.__aexit__ = AsyncMock()

            request = {"messages": [{"role": "user", "content": "test"}]}
            response = await bedrock_client._invoke_model_with_fallback(request)

            assert response == mock_bedrock_response
            assert mock_bedrock_client.invoke_model.call_count == 2

    @pytest.mark.asyncio
    async def test_all_models_fail(self, bedrock_client):
        """Test exception when all models fail."""
        mock_bedrock_client = AsyncMock()
        error_response = {"Error": {"Code": "ValidationException", "Message": "Invalid request"}}
        mock_bedrock_client.invoke_model = AsyncMock(
            side_effect=ClientError(error_response, "InvokeModel")
        )

        with patch("aioboto3.Session") as mock_session:
            mock_session.return_value.client = AsyncMock()
            mock_session.return_value.client.return_value.__aenter__ = AsyncMock(
                return_value=mock_bedrock_client
            )
            mock_session.return_value.client.return_value.__aexit__ = AsyncMock()

            request = {"messages": [{"role": "user", "content": "test"}]}

            with pytest.raises(BedrockModelError) as exc_info:
                await bedrock_client._invoke_model_with_fallback(request)

            assert "All Bedrock model attempts failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_guardrail_intervention(self, bedrock_client):
        """Test guardrail intervention detection."""
        mock_bedrock_client = AsyncMock()
        guardrail_response = {
            "content": [],
            "stop_reason": "guardrail_intervened",
            "usage": {"input_tokens": 10, "output_tokens": 0},
        }

        mock_response = {
            "body": AsyncMock(read=AsyncMock(return_value=json.dumps(guardrail_response).encode()))
        }
        mock_bedrock_client.invoke_model = AsyncMock(return_value=mock_response)

        with patch("aioboto3.Session") as mock_session:
            mock_session.return_value.client = AsyncMock()
            mock_session.return_value.client.return_value.__aenter__ = AsyncMock(
                return_value=mock_bedrock_client
            )
            mock_session.return_value.client.return_value.__aexit__ = AsyncMock()

            request = {"messages": [{"role": "user", "content": "test"}]}

            with pytest.raises(BedrockGuardrailError) as exc_info:
                await bedrock_client._invoke_model_with_fallback(request)

            assert "Content policy violation" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_guardrail_enabled_in_request(
        self, bedrock_client, mock_bedrock_response, mock_settings
    ):
        """Test that guardrails are added to request when enabled."""
        mock_settings.return_value.bedrock_guardrail_enabled = True
        mock_settings.return_value.bedrock_guardrail_id = "test-guardrail-id"
        mock_settings.return_value.bedrock_guardrail_version = "1"

        mock_bedrock_client = AsyncMock()
        mock_response = {
            "body": AsyncMock(
                read=AsyncMock(return_value=json.dumps(mock_bedrock_response).encode())
            )
        }
        mock_bedrock_client.invoke_model = AsyncMock(return_value=mock_response)

        with patch("aioboto3.Session") as mock_session:
            mock_session.return_value.client = AsyncMock()
            mock_session.return_value.client.return_value.__aenter__ = AsyncMock(
                return_value=mock_bedrock_client
            )
            mock_session.return_value.client.return_value.__aexit__ = AsyncMock()

            request = {"messages": [{"role": "user", "content": "test"}]}
            await bedrock_client._invoke_model_with_fallback(request)

            # Verify guardrail parameters were added
            call_args = mock_bedrock_client.invoke_model.call_args
            request_body = json.loads(call_args.kwargs["body"])
            assert "guardrailIdentifier" in request_body
            assert request_body["guardrailIdentifier"] == "test-guardrail-id"
            assert request_body["guardrailVersion"] == "1"


class TestExtractResponseText:
    """Tests for _extract_response_text method."""

    def test_extract_single_text_block(self, bedrock_client):
        """Test extracting text from single content block."""
        response = {"content": [{"type": "text", "text": "Hello, world!"}]}
        text = bedrock_client._extract_response_text(response)
        assert text == "Hello, world!"

    def test_extract_multiple_text_blocks(self, bedrock_client):
        """Test extracting and concatenating multiple text blocks."""
        response = {
            "content": [
                {"type": "text", "text": "First block. "},
                {"type": "text", "text": "Second block."},
            ]
        }
        text = bedrock_client._extract_response_text(response)
        assert text == "First block. Second block."

    def test_extract_with_non_text_blocks(self, bedrock_client):
        """Test extracting text when response has non-text blocks."""
        response = {
            "content": [
                {"type": "text", "text": "Text content"},
                {"type": "tool_use", "id": "tool1", "name": "some_tool"},
                {"type": "text", "text": " more text"},
            ]
        }
        text = bedrock_client._extract_response_text(response)
        assert text == "Text content more text"

    def test_extract_empty_content(self, bedrock_client):
        """Test error when response has no content."""
        response = {"content": []}
        with pytest.raises(BedrockClientError) as exc_info:
            bedrock_client._extract_response_text(response)
        assert "No content in Bedrock response" in str(exc_info.value)


class TestUserFriendlyErrors:
    """Tests for _get_user_friendly_error_message method."""

    def test_throttling_exception(self, bedrock_client):
        """Test user-friendly message for throttling."""
        error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "InvokeModel"
        )
        msg = bedrock_client._get_user_friendly_error_message(error)
        assert "AI service is currently busy" in msg
        assert "⏱️" in msg

    def test_access_denied_exception(self, bedrock_client):
        """Test user-friendly message for access denied."""
        error = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized"}}, "InvokeModel"
        )
        msg = bedrock_client._get_user_friendly_error_message(error)
        assert "Access denied" in msg
        assert "🔒" in msg

    def test_validation_exception(self, bedrock_client):
        """Test user-friendly message for validation error."""
        error = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Invalid"}}, "InvokeModel"
        )
        msg = bedrock_client._get_user_friendly_error_message(error)
        assert "Invalid request format" in msg
        assert "⚠️" in msg

    def test_service_unavailable_exception(self, bedrock_client):
        """Test user-friendly message for service unavailable."""
        error = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "Unavailable"}},
            "InvokeModel",
        )
        msg = bedrock_client._get_user_friendly_error_message(error)
        assert "temporarily unavailable" in msg
        assert "🔧" in msg

    def test_unknown_client_error(self, bedrock_client):
        """Test user-friendly message for unknown AWS error."""
        error = ClientError(
            {"Error": {"Code": "UnknownError", "Message": "Something went wrong"}}, "InvokeModel"
        )
        msg = bedrock_client._get_user_friendly_error_message(error)
        assert "UnknownError" in msg
        assert "❌" in msg

    def test_generic_exception(self, bedrock_client):
        """Test user-friendly message for non-AWS exception."""
        error = ValueError("Some random error")
        msg = bedrock_client._get_user_friendly_error_message(error)
        assert "unexpected error occurred" in msg
        assert "Some random error" in msg


class TestToolAttemptTracking:
    """Tests for tool attempt tracking methods."""

    def test_reset_tool_attempts(self, bedrock_client):
        """Test resetting tool attempts for a user."""
        bedrock_client._tool_attempt_counter["user1"] = 5
        bedrock_client._reset_tool_attempts("user1")
        assert bedrock_client._tool_attempt_counter["user1"] == 0

    def test_get_tool_attempts_existing(self, bedrock_client):
        """Test getting tool attempts for existing user."""
        bedrock_client._tool_attempt_counter["user1"] = 3
        attempts = bedrock_client._get_tool_attempts("user1")
        assert attempts == 3

    def test_get_tool_attempts_new_user(self, bedrock_client):
        """Test getting tool attempts for new user returns 0."""
        attempts = bedrock_client._get_tool_attempts("new_user")
        assert attempts == 0

    def test_increment_tool_attempts(self, bedrock_client):
        """Test incrementing tool attempts."""
        count = bedrock_client._increment_tool_attempts("user1")
        assert count == 1
        count = bedrock_client._increment_tool_attempts("user1")
        assert count == 2
        count = bedrock_client._increment_tool_attempts("user1")
        assert count == 3
