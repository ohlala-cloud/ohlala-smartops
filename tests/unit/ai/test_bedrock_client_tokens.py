"""Unit tests for TokenTracker integration in BedrockClient.

This module tests the token tracking functionality integrated into the
BedrockClient for monitoring Claude API usage and costs.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ohlala_smartops.ai.bedrock_client import BedrockClient, BedrockClientError


class TestBedrockClientTokenIntegration:
    """Test suite for BedrockClient token tracking integration."""

    @pytest.fixture
    def bedrock_client(self) -> BedrockClient:
        """Provide a BedrockClient with default dependencies."""
        return BedrockClient()

    @pytest.mark.asyncio
    async def test_pre_operation_token_estimation(self, bedrock_client: BedrockClient) -> None:
        """Test token estimation before Bedrock API call."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation"),
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            # Verify token estimation was called
            mock_estimate.assert_called_once()
            call_args = mock_estimate.call_args
            assert "system_prompt" in call_args.kwargs
            assert "user_message" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_pre_operation_limit_checking(self, bedrock_client: BedrockClient) -> None:
        """Test limit checking before Bedrock API call."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation"),
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            # Verify limit checking was called
            mock_check.assert_called_once()
            call_args = mock_check.call_args
            assert call_args.kwargs["estimated_input_tokens"] == 1000
            assert call_args.kwargs["operation_type"] == "bedrock_call"

    @pytest.mark.asyncio
    async def test_limit_exceeded_blocks_operation(self, bedrock_client: BedrockClient) -> None:
        """Test that exceeding limits blocks the operation."""
        with (
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
        ):
            # Configure tracker to block operation
            mock_estimate.return_value = 250000
            mock_check.return_value = {
                "allowed": False,
                "warnings": ["Token limit exceeded: 250,000 tokens requested"],
                "recommendations": [],
            }

            with pytest.raises(BedrockClientError) as exc_info:
                await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            assert "Token limit exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_warnings_logged_but_not_blocking(
        self,
        bedrock_client: BedrockClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that warnings are logged but don't block operations."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation"),
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            mock_estimate.return_value = 1000
            # Configure tracker with warnings but allowed=True
            mock_check.return_value = {
                "allowed": True,
                "estimated_input_tokens": 1000,
                "warnings": ["Approaching daily budget limit"],
                "recommendations": [],
            }

            await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            # Check that warning was logged
            assert any("Approaching daily budget limit" in rec.message for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_post_operation_token_tracking(self, bedrock_client: BedrockClient) -> None:
        """Test token tracking after Bedrock API response."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1200, "output_tokens": 600},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            # Verify tracking was called with actual token counts
            mock_track.assert_called_once()
            call_args = mock_track.call_args
            assert call_args.kwargs["operation_type"] == "bedrock_call"
            assert call_args.kwargs["input_tokens"] == 1200
            assert call_args.kwargs["output_tokens"] == 600

    @pytest.mark.asyncio
    async def test_tracking_includes_metadata(self, bedrock_client: BedrockClient) -> None:
        """Test that tracking includes metadata about the operation."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            prompt = "Test prompt that is quite long and should be truncated in metadata"
            await bedrock_client.call_bedrock(prompt=prompt, user_id="user123")

            # Verify metadata was included
            call_args = mock_track.call_args
            metadata = call_args.kwargs["metadata"]
            assert "prompt_preview" in metadata
            assert "stop_reason" in metadata
            assert metadata["stop_reason"] == "end_turn"

    @pytest.mark.asyncio
    async def test_anonymous_user_handling(self, bedrock_client: BedrockClient) -> None:
        """Test handling of calls without user_id."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            await bedrock_client.call_bedrock(prompt="Test prompt")

            # Verify "anonymous" is used when user_id is None
            call_args = mock_track.call_args
            assert call_args.kwargs["metadata"]["user_id"] == "anonymous"

    @pytest.mark.asyncio
    async def test_usage_extraction_from_response(self, bedrock_client: BedrockClient) -> None:
        """Test extraction of usage statistics from Bedrock response."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            # Response with usage data
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 2500, "output_tokens": 1500},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            # Verify actual token counts were used
            call_args = mock_track.call_args
            assert call_args.kwargs["input_tokens"] == 2500
            assert call_args.kwargs["output_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_missing_usage_in_response(self, bedrock_client: BedrockClient) -> None:
        """Test handling of response without usage statistics."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            # Response without usage data
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            # Verify estimated tokens are used as fallback
            call_args = mock_track.call_args
            assert call_args.kwargs["input_tokens"] == 1000  # estimated value
            assert call_args.kwargs["output_tokens"] == 0  # default

    @pytest.mark.asyncio
    async def test_tracking_on_operation_error(self, bedrock_client: BedrockClient) -> None:
        """Test that tracking doesn't occur if operation fails."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            mock_invoke.side_effect = Exception("API Error")
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            with pytest.raises(BedrockClientError):
                await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            # Verify tracking was NOT called on error
            mock_track.assert_not_called()

    @pytest.mark.asyncio
    async def test_long_prompt_truncation_in_metadata(self, bedrock_client: BedrockClient) -> None:
        """Test that long prompts are truncated in metadata."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            # Very long prompt
            long_prompt = "A" * 200
            await bedrock_client.call_bedrock(prompt=long_prompt, user_id="user123")

            # Verify prompt is truncated to 100 characters
            call_args = mock_track.call_args
            metadata = call_args.kwargs["metadata"]
            assert len(metadata["prompt_preview"]) == 100

    @pytest.mark.asyncio
    async def test_short_prompt_not_truncated(self, bedrock_client: BedrockClient) -> None:
        """Test that short prompts are not truncated."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            short_prompt = "Short prompt"
            await bedrock_client.call_bedrock(prompt=short_prompt, user_id="user123")

            # Verify full prompt is preserved
            call_args = mock_track.call_args
            metadata = call_args.kwargs["metadata"]
            assert metadata["prompt_preview"] == short_prompt

    @pytest.mark.asyncio
    async def test_tools_count_phase_3_placeholder(self, bedrock_client: BedrockClient) -> None:
        """Test that tools_count is 0 (Phase 3 placeholder)."""
        with (
            patch.object(
                bedrock_client, "_invoke_model_with_fallback", new_callable=AsyncMock
            ) as mock_invoke,
            patch(
                "ohlala_smartops.ai.bedrock_client.estimate_bedrock_input_tokens"
            ) as mock_estimate,
            patch("ohlala_smartops.ai.bedrock_client.check_operation_limits") as mock_check,
            patch("ohlala_smartops.ai.bedrock_client.track_bedrock_operation") as mock_track,
        ):
            mock_invoke.return_value = {
                "content": [{"type": "text", "text": "Response"}],
                "stopReason": "end_turn",
                "usage": {"input_tokens": 1000, "output_tokens": 500},
            }
            mock_estimate.return_value = 1000
            mock_check.return_value = {"allowed": True, "warnings": []}

            await bedrock_client.call_bedrock(prompt="Test prompt", user_id="user123")

            # Verify tools_count is 0 (Phase 3 integration pending)
            call_args = mock_track.call_args
            metadata = call_args.kwargs["metadata"]
            assert metadata["tools_count"] == 0
