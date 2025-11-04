"""Conversation handler for managing multi-turn Claude conversations with tool use.

This module provides the ConversationHandler class which manages complex multi-turn
conversations with Claude, including tool use, approval workflows, and state resumption.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from botbuilder.core import TurnContext
from botbuilder.core import TurnContext as TurnContextRef  # For conversation references

from ohlala_smartops.ai.prompts import get_system_prompt
from ohlala_smartops.bot.state import ConversationStateManager
from ohlala_smartops.constants import (
    BEDROCK_ANTHROPIC_VERSION,
    BEDROCK_MAX_TOKENS,
    BEDROCK_TEMPERATURE,
    COMPLETION_STATUSES,
    SSM_POLL_INTERVAL,
    SSM_SYNC_TIMEOUT,
)
from ohlala_smartops.models.approvals import ApprovalStatus
from ohlala_smartops.models.conversation import ConversationState
from ohlala_smartops.utils.ssm import preprocess_ssm_commands

logger = logging.getLogger(__name__)


class ConversationHandler:
    """Handles multi-turn conversations with Claude including tool use and approvals.

    This handler manages the complexity of Claude conversations that involve:
    - Multiple tool use iterations
    - Approval workflows for sensitive operations
    - State persistence and resumption
    - Multi-instance request validation
    - SSM command tracking integration

    Attributes:
        state_manager: Manager for conversation state persistence.
        bedrock_client: Client for AWS Bedrock API calls.
        mcp_manager: Manager for Model Context Protocol tool calls.
        command_tracker: Optional tracker for async SSM commands.
        approval_callback: Optional callback for tool approval requests.
    """

    def __init__(
        self,
        state_manager: ConversationStateManager,
        bedrock_client: Any,  # BedrockClient type
        mcp_manager: Any,  # MCPManager type
        command_tracker: Any | None = None,  # AsyncCommandTracker type
        approval_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Initialize the conversation handler.

        Args:
            state_manager: Manager for conversation state persistence.
            bedrock_client: Client for AWS Bedrock API calls.
            mcp_manager: Manager for MCP tool calls.
            command_tracker: Optional async command tracker for SSM commands.
            approval_callback: Optional callback for tool approval requests.
        """
        self.state_manager = state_manager
        self.bedrock_client = bedrock_client
        self.mcp_manager = mcp_manager
        self.command_tracker = command_tracker
        self.approval_callback = approval_callback
        logger.info("Initialized conversation handler")

    async def store_conversation_state(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        iteration: int,
        available_tools: list[str],
        pending_tool_uses: list[dict[str, Any]],
        original_prompt: str | None = None,
        instance_platforms: dict[str, str] | None = None,
    ) -> None:
        """Store conversation state for resuming after approval.

        Args:
            user_id: Unique user identifier.
            messages: Claude conversation messages.
            iteration: Current tool use iteration count.
            available_tools: List of available tool names.
            pending_tool_uses: Tool uses awaiting approval.
            original_prompt: Original user prompt for context.
            instance_platforms: Mapping of instance IDs to platforms.
        """
        state = await self.state_manager.get_state(user_id)
        state.store_conversation_for_resume(
            messages=messages,
            iteration=iteration,
            available_tools=available_tools,
            pending_tool_uses=pending_tool_uses,
            original_prompt=original_prompt,
            instance_platforms=instance_platforms,
        )
        await self.state_manager.save_state(state)
        logger.info(f"Stored conversation state for user {user_id} at iteration {iteration}")

    async def get_conversation_state(self, user_id: str) -> ConversationState:
        """Get stored conversation state for user.

        Args:
            user_id: Unique user identifier.

        Returns:
            Conversation state (creates new if not found).
        """
        return await self.state_manager.get_state(user_id)

    async def clear_conversation_state(self, user_id: str) -> None:
        """Clear conversation state for user.

        Args:
            user_id: Unique user identifier.
        """
        await self.state_manager.clear_conversation(user_id)
        logger.info(f"Cleared conversation state for user {user_id}")

    def _is_multi_instance_request(self, messages: list[dict[str, Any]]) -> bool:
        """Check if the user's request is asking for operations on all instances.

        Args:
            messages: List of conversation messages.

        Returns:
            True if this appears to be a multi-instance request.
        """
        if not messages:
            return False

        # Check the most recent user message
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str):
                    content_lower = content.lower()
                    multi_instance_keywords = [
                        "all instances",
                        "all my instances",
                        "every instance",
                        "all servers",
                        "all my servers",
                        "every server",
                        "on all",
                        "across all",
                    ]
                    return any(keyword in content_lower for keyword in multi_instance_keywords)
        return False

    def _validate_multi_instance_tools(
        self, tool_uses: list[dict[str, Any]], is_multi_instance_request: bool
    ) -> bool:
        """Validate that multi-instance requests actually target multiple instances.

        Args:
            tool_uses: List of tool uses to validate.
            is_multi_instance_request: Whether this is a multi-instance request.

        Returns:
            True if validation passes, False otherwise.
        """
        if not is_multi_instance_request:
            return True

        send_command_tools = []
        list_instance_tools = []

        for tool_use in tool_uses:
            tool_name = tool_use.get("name", "")
            if "send-command" in tool_name:
                send_command_tools.append(tool_use)
            elif "list-instances" in tool_name:
                list_instance_tools.append(tool_use)

        # If user asked for all instances but only list-instances was called,
        # that's fine (discovery phase)
        if list_instance_tools and not send_command_tools:
            return True

        # If there are send-command calls, validate they cover multiple instances or platforms
        if send_command_tools:
            total_instances = 0
            unique_instance_ids = set()

            for tool_use in send_command_tools:
                tool_input = tool_use.get("input", {})
                instance_ids = tool_input.get("InstanceIds", [])
                total_instances += len(instance_ids)
                unique_instance_ids.update(instance_ids)

            # For multi-instance requests, we expect either:
            # 1. Multiple instances in a single command, OR
            # 2. Multiple separate commands (for different platforms)
            if len(unique_instance_ids) >= 2 or len(send_command_tools) >= 2:
                return True
            logger.warning(
                f"Multi-instance request detected but only {len(unique_instance_ids)} "
                f"instance(s) targeted in {len(send_command_tools)} command(s)"
            )
            return False

        return True

    async def call_bedrock_with_tools(
        self,
        request: dict[str, Any],
        turn_context: TurnContext | None = None,
        iteration: int = 0,
    ) -> str | dict[str, Any]:
        """Continue a Bedrock conversation with tools from a saved state.

        Args:
            request: Bedrock API request with messages and tools.
            turn_context: Optional Teams turn context for sending typing indicators.
            iteration: Starting iteration number.

        Returns:
            Final text response or adaptive card dictionary.

        Raises:
            Exception: If Bedrock API call fails after retries.
        """
        try:
            # Extract messages from request
            messages = request.get("messages", [])
            request.get("tools", [])

            # Start from the provided iteration
            max_iterations = 10

            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Resumed tool use iteration {iteration}")

                # Call Bedrock using the bedrock client
                response_body = await self._invoke_bedrock_model(request)

                # Process the response
                content = response_body.get("content", [])
                text_responses = [item for item in content if item.get("type") == "text"]
                tool_uses = [item for item in content if item.get("type") == "tool_use"]

                if tool_uses:
                    # Check if this is a multi-instance request and validate
                    is_multi_instance_request = self._is_multi_instance_request(messages)

                    if is_multi_instance_request:
                        logger.info(
                            f"Multi-instance request detected. "
                            f"Validating {len(tool_uses)} tool uses..."
                        )
                        is_valid = self._validate_multi_instance_tools(
                            tool_uses, is_multi_instance_request
                        )

                        if not is_valid:
                            # Add corrective message to guide the LLM
                            correction_text = (
                                "⚠️ VALIDATION ERROR: You were asked to execute commands "
                                "on ALL instances, but you only targeted one instance. "
                                "Please list all available instances first, then create "
                                "separate send-command tool calls for each platform "
                                "(Linux instances using AWS-RunShellScript, Windows instances "
                                "using AWS-RunPowerShellScript). Each tool call should target "
                                "all instances of that platform type."
                            )
                            correction_message = {
                                "role": "user",
                                "content": [{"type": "text", "text": correction_text}],
                            }
                            messages.append(correction_message)
                            request["messages"] = messages

                            # Retry with corrected instructions
                            logger.info("Retrying with multi-instance validation correction...")
                            return await self.call_bedrock_with_tools(
                                request, turn_context, iteration
                            )

                    # Process tool uses
                    new_tool_results = await self._process_tool_uses(tool_uses, turn_context)

                    # Add tool results to messages
                    messages.append({"role": "user", "content": new_tool_results})

                    # Update request for next iteration
                    request["messages"] = messages
                else:
                    # No more tool uses, return the response
                    return self._extract_final_response(text_responses)

            # Max iterations reached
            return "I've analyzed the command results but reached the processing limit."

        except Exception as e:
            logger.error(f"Error in call_bedrock_with_tools: {e}", exc_info=True)
            return f"I encountered an error while analyzing the results: {e!s}"

    async def _invoke_bedrock_model(self, request: dict[str, Any]) -> dict[str, Any]:
        """Invoke the Bedrock model with the given request.

        Args:
            request: Bedrock API request dictionary.

        Returns:
            Response body from Bedrock.

        Raises:
            Exception: If Bedrock API call fails.
        """
        # Use the bedrock client's tool-enabled method
        tools = request.get("tools", [])
        tool_names = [tool.get("name", "") for tool in tools]
        response: dict[str, Any] = await self.bedrock_client.call_bedrock_with_tools(
            messages=request.get("messages", []),
            system_prompt=request.get("system", get_system_prompt(available_tools=tool_names)),
            tools=tools,
            max_tokens=request.get("max_tokens", BEDROCK_MAX_TOKENS),
            temperature=request.get("temperature", BEDROCK_TEMPERATURE),
        )
        return response

    async def _process_tool_uses(
        self,
        tool_uses: list[dict[str, Any]],
        turn_context: TurnContext | None = None,  # noqa: ARG002 - reserved for future use
    ) -> list[dict[str, Any]]:
        """Process a list of tool uses and return tool results.

        Args:
            tool_uses: List of tool use dictionaries from Claude.
            turn_context: Optional Teams turn context.

        Returns:
            List of tool result dictionaries.
        """
        new_tool_results = []

        for tool_use in tool_uses:
            tool_name = tool_use.get("name")
            tool_input = tool_use.get("input", {})
            tool_id = tool_use.get("id")

            try:
                # Call the appropriate tool
                if tool_name in ["list-instances", "describe-instances", "get-instance-status"]:
                    tool_result = await self.mcp_manager.call_aws_api_tool(tool_name, tool_input)
                elif tool_name == "get-command-invocation":
                    # Check with command tracker first
                    command_id = tool_input.get("command_id")
                    if command_id and self.command_tracker:
                        tracker_status = self.command_tracker.get_command_status(command_id)
                        if tracker_status:
                            tool_result = tracker_status
                        else:
                            tool_result = await self.mcp_manager.call_aws_api_tool(
                                tool_name, tool_input
                            )
                    else:
                        tool_result = await self.mcp_manager.call_aws_api_tool(
                            tool_name, tool_input
                        )
                else:
                    tool_result = {"error": f"Unknown tool: {tool_name}"}

                new_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps(tool_result),
                    }
                )
            except Exception as tool_error:
                logger.error(f"Error calling tool {tool_name}: {tool_error}")
                new_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps({"error": str(tool_error)}),
                    }
                )

        return new_tool_results

    def _extract_final_response(self, text_responses: list[dict[str, Any]]) -> str | dict[str, Any]:
        """Extract final response from text responses.

        Args:
            text_responses: List of text response blocks from Claude.

        Returns:
            Final text response or adaptive card dictionary.
        """
        final_text = " ".join([t.get("text", "") for t in text_responses])

        # Check if the response contains an adaptive card
        if final_text and '"adaptive_card"' in final_text and "true" in final_text:
            try:
                # Extract JSON from response
                json_start = final_text.find('{"adaptive_card": true')
                if json_start == -1:
                    json_start = final_text.find('{\n  "adaptive_card": true')

                if json_start != -1:
                    # Find matching closing brace
                    brace_count = 0
                    end_idx = json_start
                    for i in range(json_start, len(final_text)):
                        if final_text[i] == "{":
                            brace_count += 1
                        elif final_text[i] == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break

                    json_str = final_text[json_start:end_idx]
                    response_data = json.loads(json_str)
                    if isinstance(response_data, dict) and response_data.get("adaptive_card"):
                        return response_data
            except Exception as e:
                logger.error(f"Failed to parse adaptive card: {e}")

        return final_text if final_text else "I've completed analyzing the command results."

    async def resume_conversation(
        self, user_id: str, turn_context: TurnContext | None = None
    ) -> str | dict[str, Any] | None:
        """Resume conversation from stored state after approval.

        Args:
            user_id: Unique user identifier.
            turn_context: Optional Teams turn context.

        Returns:
            Final response text or None if conversation is handled by SSM tracker.

        Raises:
            Exception: If resume fails.
        """
        state = await self.get_conversation_state(user_id)

        # Check if conversation is being handled by SSM tracker
        if state.handled_by_ssm_tracker:
            logger.info(
                f"Conversation for user {user_id} is being handled by SSM tracker - skipping resume"
            )
            return None

        if not state.messages:
            logger.error(f"No conversation state found for user {user_id}")
            return "❌ Error: Unable to continue conversation - state not found."

        try:
            logger.info(
                f"Resuming conversation for user {user_id} from iteration {state.iteration}"
            )

            # Process pending tool uses with approved tools
            new_tool_results = []
            for tool_use in state.pending_tool_uses:
                tool_name = tool_use.get("name")
                tool_id = tool_use.get("id")

                # Skip if tool_name or tool_id is missing
                if not tool_name or not tool_id:
                    logger.warning(f"Skipping tool use with missing name or ID: {tool_use}")
                    continue

                # Try to get tool_input from stored inputs first (to avoid Teams corruption)
                tool_input = state.pending_tool_inputs.get(tool_id)
                if tool_input is None:
                    # Fallback to the input from the tool_use
                    tool_input = tool_use.get("input", {})
                    logger.info(f"Using tool_use input for {tool_id}")
                else:
                    logger.info(f"Using stored tool input for {tool_id}")

                logger.info(f"Processing resumed tool: {tool_name} with ID: {tool_id}")

                try:
                    tool_result = await self._execute_approved_tool(
                        tool_name, tool_input, tool_id, user_id, turn_context, state
                    )

                    tool_result_entry = {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": json.dumps(tool_result)
                        if tool_result
                        else "Tool execution completed",
                    }
                    logger.info(
                        f"Adding tool result for {tool_id}: {str(tool_result_entry)[:200]}..."
                    )
                    new_tool_results.append(tool_result_entry)

                except Exception as e:
                    logger.error(f"Error executing resumed tool {tool_name}: {e}", exc_info=True)
                    new_tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": json.dumps({"error": str(e)}),
                        }
                    )

            # Add tool results to conversation
            if new_tool_results:
                logger.info(f"Adding {len(new_tool_results)} tool results to conversation")
                state.messages.append({"role": "user", "content": new_tool_results})
            # If no tool results but we had pending tool uses, add placeholder
            elif state.pending_tool_uses:
                logger.warning("No tool results generated for pending tool uses")
                state.messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": state.pending_tool_uses[0].get("id", "unknown"),
                                "content": json.dumps(
                                    {"error": "Tool execution failed or produced no results"}
                                ),
                            }
                        ],
                    }
                )

            # Continue with Claude using the conversation
            return await self._continue_claude_conversation(
                state.messages, state.available_tools, state.iteration, turn_context, user_id
            )

        except Exception as e:
            logger.error(f"Error resuming conversation: {e}", exc_info=True)
            return f"❌ Error resuming conversation: {e!s}"

    async def _execute_approved_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_id: str,
        user_id: str,
        turn_context: TurnContext | None,
        state: ConversationState,
    ) -> dict[str, Any] | None:
        """Execute an approved tool and handle the result.

        Args:
            tool_name: Name of the tool to execute.
            tool_input: Input parameters for the tool.
            tool_id: Unique tool invocation ID.
            user_id: User identifier.
            turn_context: Optional Teams turn context.
            state: Current conversation state.

        Returns:
            Tool execution result dictionary or None.
        """
        tool_result: dict[str, Any] | None = None

        # Check if this is an SSM command that has been approved
        if tool_name in ["execute_ssm_sync", "execute_ssm_async"]:
            # Get approval from state manager
            approval = await self.state_manager.get_approval(tool_id)

            if approval and approval.status == ApprovalStatus.APPROVED:
                # Command was approved - execute it
                logger.info(f"Executing approved SSM command: {tool_id}")

                # Preprocess tool_input to handle JSON string Commands
                if "Commands" in tool_input:
                    commands = tool_input.get("Commands", [])
                    logger.info(
                        f"Original Commands before preprocessing: {json.dumps(commands)[:500]}"
                    )
                    tool_input["Commands"] = preprocess_ssm_commands(commands)
                    logger.info(f"Preprocessed commands: {len(tool_input['Commands'])} command(s)")

                tool_result = await self.mcp_manager.call_aws_api_tool(
                    tool_name, tool_input, turn_context=turn_context, user_id=user_id
                )

                # Clean up stored tool input after use
                if tool_id in state.pending_tool_inputs:
                    del state.pending_tool_inputs[tool_id]
                    await self.state_manager.save_state(state)

                # Handle sync command completion
                if tool_name == "execute_ssm_sync" and tool_result and "CommandId" in tool_result:
                    await self._wait_for_sync_command_completion(tool_input, tool_result)

            elif approval and approval.status == ApprovalStatus.REJECTED:
                # Command was denied
                logger.info(f"SSM command denied: {tool_id}")
                tool_result = {"error": "Command execution was denied by the user.", "denied": True}
            else:
                # Still needs approval - this shouldn't happen in resume context
                logger.warning(f"Tool {tool_id} still needs approval during resume")
                return None
        else:
            # Non-SSM tool - execute directly
            tool_result = await self.mcp_manager.call_aws_api_tool(
                tool_name, tool_input, turn_context=turn_context, user_id=user_id
            )

        # Handle async tracking for executed SSM commands
        if (
            tool_name in ["execute_ssm_sync", "execute_ssm_async"]
            and tool_result
            and "CommandId" in tool_result
        ):
            await self._handle_async_ssm_tracking(
                tool_name, tool_input, tool_result, turn_context, state, user_id
            )

        return tool_result

    async def _wait_for_sync_command_completion(
        self, tool_input: dict[str, Any], tool_result: dict[str, Any]
    ) -> None:
        """Wait for a synchronous SSM command to complete.

        Args:
            tool_input: Tool input parameters.
            tool_result: Tool result dictionary to update with completion status.
        """
        command_id = tool_result.get("Command", {}).get("CommandId") or tool_result.get("CommandId")
        if command_id:
            # Poll for command completion
            logger.info(f"Waiting for SSM command {command_id} to complete...")
            start_time = asyncio.get_event_loop().time()
            max_wait = SSM_SYNC_TIMEOUT

            while (asyncio.get_event_loop().time() - start_time) < max_wait:
                await asyncio.sleep(SSM_POLL_INTERVAL)

                # Get command status for first instance
                instance_ids = tool_input.get("InstanceIds", [])
                if instance_ids:
                    try:
                        status_result = await self.mcp_manager.call_aws_api_tool(
                            "get-command-invocation",
                            {"CommandId": command_id, "InstanceId": instance_ids[0]},
                        )

                        status = status_result.get("Status", "Unknown")
                        if status in COMPLETION_STATUSES:
                            # Command completed - add output to result
                            tool_result["Status"] = status
                            tool_result["StandardOutputContent"] = status_result.get(
                                "StandardOutputContent", ""
                            )
                            tool_result["StandardErrorContent"] = status_result.get(
                                "StandardErrorContent", ""
                            )
                            logger.info(f"SSM command {command_id} completed with status: {status}")
                            break
                    except Exception as e:
                        logger.warning(f"Error polling command status: {e}")

            if (asyncio.get_event_loop().time() - start_time) >= max_wait:
                logger.warning(f"SSM command {command_id} timed out after {max_wait} seconds")
                tool_result["note"] = "Command execution timed out. It may still be running."

    async def _handle_async_ssm_tracking(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_result: dict[str, Any],
        turn_context: TurnContext | None,
        state: ConversationState,
        user_id: str,
    ) -> None:
        """Handle async tracking for SSM commands.

        Args:
            tool_name: Name of the SSM tool.
            tool_input: Tool input parameters.
            tool_result: Tool result dictionary.
            turn_context: Optional Teams turn context.
            state: Current conversation state.
            user_id: User identifier.
        """
        commands = tool_input.get("Commands", [])

        # Handle case where Commands might be a JSON string
        if isinstance(commands, str):
            try:
                commands = json.loads(commands)
            except Exception:
                commands = [commands]

        # For execute_ssm_async, always use async tracking
        if self.command_tracker and tool_name == "execute_ssm_async":
            command_id = tool_result.get("Command", {}).get("CommandId") or tool_result.get(
                "CommandId"
            )
            instance_ids = tool_input.get("InstanceIds", [])

            # Get conversation reference for proactive messages
            if turn_context:
                conversation_ref = TurnContextRef.get_conversation_reference(turn_context.activity)

                # Extract command description
                command_desc = (
                    commands[0][:50] + "..."
                    if commands and len(commands[0]) > 50
                    else (commands[0] if commands else "SSM Command")
                )

                # Start async tracking
                tracking_info = await self.command_tracker.track_command(
                    command_id=command_id,
                    instance_ids=instance_ids,
                    conversation_reference=conversation_ref,
                    command_description=command_desc,
                    original_prompt=state.original_prompt or user_id,
                    auto_send_results=False,  # Claude will handle the results
                )

                # Add tracking info to result
                tool_result["async_tracking"] = True
                tool_result["tracking_message"] = tracking_info["message"]

    async def _continue_claude_conversation(
        self,
        messages: list[dict[str, Any]],
        available_tools: list[str],
        iteration: int,
        turn_context: TurnContext | None,
        user_id: str,  # noqa: ARG002 - reserved for future use
    ) -> str | dict[str, Any]:
        """Continue the Claude conversation with updated messages.

        Args:
            messages: Updated conversation messages.
            available_tools: List of available tool names.
            iteration: Current iteration count.
            turn_context: Optional Teams turn context.
            user_id: User identifier.

        Returns:
            Final response text or adaptive card dictionary.
        """
        try:
            # Prepare the request for Claude
            tools_for_claude = []
            if available_tools and isinstance(available_tools[0], str):
                # Convert tool names to tool objects
                for tool_name in available_tools:
                    tool_schema = await self.mcp_manager.get_tool_schema(tool_name)
                    if tool_schema:
                        tools_for_claude.append(tool_schema)
            else:
                tools_for_claude = available_tools

            request = {
                "anthropic_version": BEDROCK_ANTHROPIC_VERSION,
                "max_tokens": BEDROCK_MAX_TOKENS,
                "temperature": BEDROCK_TEMPERATURE,
                "system": get_system_prompt(available_tools=available_tools),
                "messages": messages,
                "tools": tools_for_claude,
            }

            # Continue the conversation
            return await self.call_bedrock_with_tools(request, turn_context, iteration)

        except Exception as e:
            logger.error(f"Error continuing Claude conversation: {e}", exc_info=True)
            return f"❌ Error processing your request: {e!s}"
