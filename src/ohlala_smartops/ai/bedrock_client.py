"""Bedrock AI client for handling LLM interactions.

This module provides the BedrockClient class for interacting with Amazon Bedrock's
Claude models. It handles:
- Bedrock API calls with retry logic and fallback
- Token tracking and budget monitoring
- Guardrail integration
- Conversation context management
- Error handling and user-friendly messages

Example:
    Basic usage::

        from ohlala_smartops.ai.bedrock_client import BedrockClient

        # Initialize client
        client = BedrockClient()

        # Make a call
        response = await client.call_bedrock(
            prompt="List all running EC2 instances",
            user_id="user123"
        )

Note:
    This is Phase 2B of the migration. MCP tool orchestration, approval workflows,
    and async command tracking will be added in Phase 3 when those components are migrated.
"""

import json
import logging
from typing import Any, Final

import aioboto3
from botocore.exceptions import ClientError

from ohlala_smartops.ai.model_selector import ModelSelector
from ohlala_smartops.ai.prompts import get_system_prompt
from ohlala_smartops.config import get_settings
from ohlala_smartops.constants import (
    BEDROCK_ANTHROPIC_VERSION,
    BEDROCK_MAX_TOKENS,
    BEDROCK_TEMPERATURE,
)
from ohlala_smartops.utils.audit_logger import AuditLogger
from ohlala_smartops.utils.bedrock_throttler import BedrockThrottler
from ohlala_smartops.utils.token_tracker import TokenTracker

logger: Final = logging.getLogger(__name__)


class BedrockClientError(Exception):
    """Base exception for Bedrock client errors."""


class BedrockModelError(BedrockClientError):
    """Exception raised when all Bedrock models fail."""


class BedrockGuardrailError(BedrockClientError):
    """Exception raised when guardrail intervenes."""


class BedrockClient:
    """Client for Amazon Bedrock AI interactions.

    This client provides high-level access to Claude models via AWS Bedrock,
    with built-in token tracking, rate limiting, and error handling.

    Attributes:
        model_selector: ModelSelector instance for choosing appropriate models.
        throttler: BedrockThrottler for rate limiting API calls.
        audit_logger: AuditLogger for compliance and security auditing.
        token_tracker: TokenTracker for monitoring token usage and costs.

    Example:
        >>> client = BedrockClient()
        >>> response = await client.call_bedrock(
        ...     prompt="What is the status of my instances?",
        ...     user_id="user123"
        ... )
        'You have 3 running instances: ...'

    Note:
        Phase 2B: MCP tool integration will be added in Phase 3.
    """

    def __init__(
        self,
        mcp_manager: Any | None = None,
        audit_logger: AuditLogger | None = None,
        throttler: BedrockThrottler | None = None,
        token_tracker: TokenTracker | None = None,
    ) -> None:
        """Initialize Bedrock client.

        Args:
            mcp_manager: Optional MCP manager for tool orchestration (Phase 3).
            audit_logger: Optional custom audit logger. If None, creates default.
            throttler: Optional custom throttler. If None, creates default.
            token_tracker: Optional custom token tracker. If None, creates default.
        """
        self.settings = get_settings()
        self.model_selector = ModelSelector()
        self.mcp_manager = mcp_manager  # Will be used in Phase 3

        # Initialize components
        self.audit_logger = audit_logger or AuditLogger()
        self.throttler = throttler or BedrockThrottler()
        self.token_tracker = token_tracker or TokenTracker()

        # Tool attempt tracking (for future MCP integration)
        self._tool_attempt_counter: dict[str, int] = {}
        self._max_tool_attempts: int = 50

        logger.info("BedrockClient initialized for region %s", self.settings.aws_region)

    async def call_bedrock(
        self,
        prompt: str,
        user_id: str | None = None,
        conversation_state: Any | None = None,  # noqa: ARG002 - Phase 3
        allowed_tools: list[str] | None = None,  # noqa: ARG002 - Phase 3: MCP integration
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Call Bedrock with a prompt and return the response.

        This method handles the complete flow of calling Claude via Bedrock:
        1. Token estimation and budget checking
        2. Conversation context retrieval
        3. System prompt generation
        4. Model invocation with fallback
        5. Token tracking and auditing
        6. Error handling

        Args:
            prompt: The user prompt to send to Claude.
            user_id: Optional user ID for conversation context and tracking.
            conversation_state: Optional conversation state (Phase 3 - integration pending).
            allowed_tools: Optional list of allowed tools (Phase 3 - MCP integration).
            max_tokens: Optional max tokens override. Defaults to settings value.
            temperature: Optional temperature override. Defaults to settings value.

        Returns:
            The text response from Claude.

        Raises:
            BedrockModelError: If all model invocation attempts fail.
            BedrockGuardrailError: If guardrails block the request.
            BedrockClientError: For other client errors.

        Example:
            >>> client = BedrockClient()
            >>> response = await client.call_bedrock(
            ...     prompt="List running instances",
            ...     user_id="user123"
            ... )
            'Here are your running instances: ...'

        Note:
            Phase 2B: Tool execution will be added in Phase 3 with MCP Manager.
        """
        logger.info(
            "Starting Bedrock call for user=%s, prompt_length=%d",
            user_id or "anonymous",
            len(prompt),
        )

        # Phase 3 TODO: Get conversation context when API is available
        conversation_context = ""
        last_instance_id = None

        # Phase 3 TODO: Get available tools from MCP manager
        # For now, no tools available until MCP Manager is migrated
        available_tools: list[str] = []
        if self.mcp_manager:
            logger.warning("MCP Manager integration not yet implemented (Phase 3)")

        # Generate system prompt with context
        system_prompt = get_system_prompt(
            available_tools=available_tools,
            conversation_context=conversation_context,
            last_instance_id=last_instance_id,
        )

        # Prepare messages
        messages = [{"role": "user", "content": prompt}]

        # Phase 3 TODO: Token estimation and budget checking
        # Will be implemented when token_estimator functions are migrated
        estimated_input_tokens = 100  # Placeholder
        logger.info("Token estimation placeholder - will be implemented in Phase 3")

        # Build Bedrock request
        request: dict[str, Any] = {
            "anthropic_version": BEDROCK_ANTHROPIC_VERSION,
            "max_tokens": max_tokens or BEDROCK_MAX_TOKENS,
            "temperature": temperature or BEDROCK_TEMPERATURE,
            "system": system_prompt,
            "messages": messages,
        }

        # Phase 3 TODO: Add tools to request from MCP manager
        # Implementation will call: self._prepare_tools_for_bedrock(available_tools)

        # Invoke model with fallback
        try:
            async with self.throttler.throttled_bedrock_request("call_bedrock"):
                response_body = await self._invoke_model_with_fallback(request)

            # Extract usage statistics
            usage = response_body.get("usage", {})
            actual_input_tokens = usage.get("input_tokens", estimated_input_tokens)
            actual_output_tokens = usage.get("output_tokens", 0)

            # Phase 3 TODO: Track the operation with token_tracker
            # Phase 3 TODO: Audit log the call with correct parameters
            logger.info(
                "Bedrock call completed: input_tokens=%d, output_tokens=%d",
                actual_input_tokens,
                actual_output_tokens,
            )

            # Extract and return response text
            final_text = self._extract_response_text(response_body)

            # Phase 3 TODO: Process tool uses from response when MCP Manager is integrated

            # Phase 3 TODO: Update conversation state when API is available
            # conversation_state will be integrated in Phase 3

            logger.info("Bedrock call completed successfully, response_length=%d", len(final_text))
            return final_text

        except BedrockGuardrailError:
            raise
        except Exception as e:
            logger.error("Error in Bedrock call: %s", e, exc_info=True)
            user_friendly_msg = self._get_user_friendly_error_message(e)
            raise BedrockClientError(user_friendly_msg) from e

    async def call_bedrock_with_tools(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Call Bedrock with full control over messages, system prompt, and tools.

        This method is designed for tool-enabled multi-turn conversations where
        the caller manages the conversation state and tool use iterations.

        Args:
            messages: List of conversation messages in Claude format.
            system_prompt: System prompt for Claude.
            tools: List of tool definitions in Claude format.
            max_tokens: Optional max tokens override. Defaults to settings value.
            temperature: Optional temperature override. Defaults to settings value.

        Returns:
            The raw response body from Bedrock including content and tool_uses.

        Raises:
            BedrockModelError: If all model invocation attempts fail.
            BedrockGuardrailError: If guardrails block the request.
            BedrockClientError: For other client errors.

        Example:
            >>> client = BedrockClient()
            >>> response = await client.call_bedrock_with_tools(
            ...     messages=[{"role": "user", "content": "List instances"}],
            ...     system_prompt="You are an AWS assistant",
            ...     tools=[list_instances_tool_schema],
            ... )
            {'content': [...], 'stop_reason': 'tool_use', ...}
        """
        try:
            # Prepare Bedrock request
            request = {
                "anthropic_version": BEDROCK_ANTHROPIC_VERSION,
                "max_tokens": max_tokens or self.settings.bedrock_max_tokens,
                "temperature": (
                    temperature if temperature is not None else self.settings.bedrock_temperature
                ),
                "system": system_prompt,
                "messages": messages,
            }

            # Only add tools if provided
            if tools:
                request["tools"] = tools

            logger.info(
                "Calling Bedrock with tools, messages=%d, tools=%d",
                len(messages),
                len(tools) if tools else 0,
            )

            # Invoke model with fallback
            return await self._invoke_model_with_fallback(request)

        except BedrockGuardrailError:
            raise
        except Exception as e:
            logger.error("Error in Bedrock call with tools: %s", e, exc_info=True)
            user_friendly_msg = self._get_user_friendly_error_message(e)
            raise BedrockClientError(user_friendly_msg) from e

    async def _invoke_model_with_fallback(self, request: dict[str, Any]) -> dict[str, Any]:
        """Invoke Bedrock model with fallback logic.

        Tries primary model first, then falls back to alternative models if needed.

        Args:
            request: The Bedrock API request parameters.

        Returns:
            The response body from successful model invocation.

        Raises:
            BedrockModelError: If all model attempts fail.
            BedrockGuardrailError: If guardrails block the request.
        """
        # Get model candidates
        primary_model = self.model_selector.get_best_model_for_region()
        fallback_model = self.model_selector.fallback_model
        all_models = (
            [primary_model, fallback_model] if primary_model != fallback_model else [primary_model]
        )

        logger.info("Attempting Bedrock invocation with %d model candidates", len(all_models))

        errors: list[tuple[str, Exception]] = []

        # Create aioboto3 session
        session = aioboto3.Session()

        for attempt, model_id in enumerate(all_models, 1):
            try:
                logger.info("Attempt %d/%d: Trying model %s", attempt, len(all_models), model_id)

                async with session.client(
                    "bedrock-runtime", region_name=self.settings.aws_region
                ) as bedrock_client:
                    # Add guardrails if enabled
                    if self.settings.bedrock_guardrail_enabled:
                        request_with_guardrail = request.copy()
                        request_with_guardrail["guardrailIdentifier"] = (
                            self.settings.bedrock_guardrail_id
                        )
                        request_with_guardrail["guardrailVersion"] = (
                            self.settings.bedrock_guardrail_version
                        )
                        response = await bedrock_client.invoke_model(
                            modelId=model_id, body=json.dumps(request_with_guardrail)
                        )
                    else:
                        response = await bedrock_client.invoke_model(
                            modelId=model_id, body=json.dumps(request)
                        )

                    # Read response body
                    response_body: dict[str, Any] = json.loads(await response["body"].read())

                    # Check for guardrail intervention
                    if response_body.get("stop_reason") == "guardrail_intervened":
                        msg = (
                            "Content policy violation: The request was blocked by "
                            "Bedrock guardrails. Please rephrase your question or ask "
                            "about EC2 management topics."
                        )
                        raise BedrockGuardrailError(msg)

                    logger.info("Successfully invoked model %s", model_id)
                    return response_body

            except BedrockGuardrailError:
                # Don't retry on guardrail errors
                raise
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_msg = e.response.get("Error", {}).get("Message", str(e))
                logger.warning("Model %s failed with %s: %s", model_id, error_code, error_msg)
                errors.append((model_id, e))
            except Exception as e:
                logger.warning("Model %s failed with error: %s", model_id, str(e))
                errors.append((model_id, e))

        # All models failed
        error_summary = "\n".join(f"- {model}: {error!s}" for model, error in errors)
        error_msg = f"All Bedrock model attempts failed:\n{error_summary}"
        logger.error(error_msg)
        raise BedrockModelError(error_msg)

    def _extract_response_text(self, response_body: dict[str, Any]) -> str:
        """Extract text content from Bedrock response.

        Args:
            response_body: The Bedrock API response body.

        Returns:
            The extracted text content.

        Raises:
            BedrockClientError: If response format is invalid.
        """
        content_items = response_body.get("content", [])
        if not content_items:
            raise BedrockClientError("No content in Bedrock response")

        final_text = ""
        for item in content_items:
            if item.get("type") == "text":
                final_text += item.get("text", "")

        return final_text.strip()

    def _get_user_friendly_error_message(self, error: Exception) -> str:
        """Convert exception to user-friendly error message.

        Args:
            error: The exception that occurred.

        Returns:
            A user-friendly error message.
        """
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "Unknown")

            if error_code == "ThrottlingException":
                return (
                    "⏱️ The AI service is currently busy. Please wait a moment and try again. "
                    "If this persists, contact your administrator."
                )
            if error_code == "AccessDeniedException":
                return (
                    "🔒 Access denied to the AI service. Please check your AWS permissions. "
                    "Contact your administrator if you believe this is an error."
                )
            if error_code == "ValidationException":
                return (
                    "⚠️ Invalid request format. This might be due to a very long "
                    "prompt or invalid parameters. Try shortening your request or rephrasing."
                )
            if error_code == "ServiceUnavailableException":
                return (
                    "🔧 The AI service is temporarily unavailable. Please try "
                    "again in a few moments. If this issue persists, contact support."
                )
            return (
                f"❌ An error occurred while processing your request: {error_code}. "
                "Please try again."
            )

        return f"❌ An unexpected error occurred: {error!s}. Please try again or contact support."

    def _reset_tool_attempts(self, user_id: str) -> None:
        """Reset tool attempt counter for a user.

        Args:
            user_id: The user ID.
        """
        self._tool_attempt_counter[user_id] = 0

    def _get_tool_attempts(self, user_id: str) -> int:
        """Get current tool attempt count for a user.

        Args:
            user_id: The user ID.

        Returns:
            The current attempt count.
        """
        return self._tool_attempt_counter.get(user_id, 0)

    def _increment_tool_attempts(self, user_id: str) -> int:
        """Increment and return tool attempt counter for a user.

        Args:
            user_id: The user ID.

        Returns:
            The new attempt count.
        """
        self._tool_attempt_counter[user_id] = self._tool_attempt_counter.get(user_id, 0) + 1
        return self._tool_attempt_counter[user_id]
