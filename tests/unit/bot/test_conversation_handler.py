"""Unit tests for ConversationHandler.

This module tests the conversation handler functionality including multi-turn
conversations, tool use, approval workflows, and state management.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from ohlala_smartops.bot.conversation_handler import ConversationHandler
from ohlala_smartops.models.conversation import ConversationState


@pytest.fixture
def mock_state_manager():
    """Create a mock ConversationStateManager."""
    manager = AsyncMock()
    manager.get_state = AsyncMock()
    manager.save_state = AsyncMock()
    manager.get_approval = AsyncMock()
    return manager


@pytest.fixture
def mock_bedrock_client():
    """Create a mock BedrockClient."""
    client = AsyncMock()
    client.call_bedrock_with_tools = AsyncMock()
    return client


@pytest.fixture
def mock_mcp_manager():
    """Create a mock MCPManager."""
    manager = AsyncMock()
    manager.call_aws_api_tool = AsyncMock()
    manager.get_tool_schema = AsyncMock()
    return manager


@pytest.fixture
def mock_command_tracker():
    """Create a mock AsyncCommandTracker."""
    tracker = Mock()
    tracker.get_command_status = Mock(return_value=None)
    tracker.track_command = AsyncMock()
    return tracker


@pytest.fixture
def conversation_handler(
    mock_state_manager, mock_bedrock_client, mock_mcp_manager, mock_command_tracker
):
    """Create a ConversationHandler instance with mocked dependencies."""
    return ConversationHandler(
        state_manager=mock_state_manager,
        bedrock_client=mock_bedrock_client,
        mcp_manager=mock_mcp_manager,
        command_tracker=mock_command_tracker,
        approval_callback=None,
    )


@pytest.fixture
def sample_conversation_state():
    """Create a sample conversation state for testing."""
    return ConversationState(
        conversation_id="test-conversation-123",
        pending_command=None,
        pending_approval_id=None,
        last_message_id=None,
        turn_count=0,
        iteration=0,
        original_prompt="Test prompt",
        handled_by_ssm_tracker=False,
    )


class TestConversationHandlerInit:
    """Test ConversationHandler initialization."""

    def test_init_with_all_dependencies(
        self,
        mock_state_manager,
        mock_bedrock_client,
        mock_mcp_manager,
        mock_command_tracker,
    ):
        """Test initialization with all dependencies."""
        handler = ConversationHandler(
            state_manager=mock_state_manager,
            bedrock_client=mock_bedrock_client,
            mcp_manager=mock_mcp_manager,
            command_tracker=mock_command_tracker,
            approval_callback=None,
        )

        assert handler.state_manager == mock_state_manager
        assert handler.bedrock_client == mock_bedrock_client
        assert handler.mcp_manager == mock_mcp_manager
        assert handler.command_tracker == mock_command_tracker

    def test_init_without_command_tracker(
        self, mock_state_manager, mock_bedrock_client, mock_mcp_manager
    ):
        """Test initialization without command tracker."""
        handler = ConversationHandler(
            state_manager=mock_state_manager,
            bedrock_client=mock_bedrock_client,
            mcp_manager=mock_mcp_manager,
            command_tracker=None,
            approval_callback=None,
        )

        assert handler.command_tracker is None


class TestStoreConversationState:
    """Test storing conversation state."""

    @pytest.mark.asyncio
    async def test_store_conversation_state_basic(
        self, conversation_handler, mock_state_manager, sample_conversation_state
    ):
        """Test storing basic conversation state."""
        mock_state_manager.get_state.return_value = sample_conversation_state

        messages = [{"role": "user", "content": "test"}]
        iteration = 1
        available_tools = ["list-instances"]
        pending_tool_uses = [{"id": "tool1", "name": "list-instances"}]

        await conversation_handler.store_conversation_state(
            user_id="user123",
            messages=messages,
            iteration=iteration,
            available_tools=available_tools,
            pending_tool_uses=pending_tool_uses,
        )

        mock_state_manager.get_state.assert_called_once_with("user123")
        mock_state_manager.save_state.assert_called_once()

        # Verify state was updated
        saved_state = mock_state_manager.save_state.call_args[0][0]
        assert saved_state.iteration == iteration
        assert saved_state.available_tools == available_tools

    @pytest.mark.asyncio
    async def test_store_conversation_state_with_platforms(
        self, conversation_handler, mock_state_manager, sample_conversation_state
    ):
        """Test storing conversation state with instance platforms."""
        mock_state_manager.get_state.return_value = sample_conversation_state

        instance_platforms = {"i-123": "linux", "i-456": "windows"}

        await conversation_handler.store_conversation_state(
            user_id="user123",
            messages=[],
            iteration=1,
            available_tools=[],
            pending_tool_uses=[],
            instance_platforms=instance_platforms,
        )

        saved_state = mock_state_manager.save_state.call_args[0][0]
        assert saved_state.instance_platforms == instance_platforms


class TestGetConversationState:
    """Test retrieving conversation state."""

    @pytest.mark.asyncio
    async def test_get_existing_state(
        self, conversation_handler, mock_state_manager, sample_conversation_state
    ):
        """Test retrieving existing conversation state."""
        mock_state_manager.get_state.return_value = sample_conversation_state

        state = await conversation_handler.get_conversation_state("user123")

        assert state == sample_conversation_state
        mock_state_manager.get_state.assert_called_once_with("user123")


class TestClearConversationState:
    """Test clearing conversation state."""

    @pytest.mark.asyncio
    async def test_clear_state(self, conversation_handler, mock_state_manager):
        """Test clearing conversation state."""
        await conversation_handler.clear_conversation_state("user123")

        mock_state_manager.clear_conversation.assert_called_once_with("user123")


class TestIsMultiInstanceRequest:
    """Test multi-instance request detection."""

    def test_detects_all_instances(self, conversation_handler):
        """Test detection of 'all instances' request."""
        messages = [{"role": "user", "content": "Stop all instances"}]

        result = conversation_handler._is_multi_instance_request(messages)

        assert result is True

    def test_detects_all_my_instances(self, conversation_handler):
        """Test detection of 'all my instances' request."""
        messages = [{"role": "user", "content": "Start all my instances"}]

        result = conversation_handler._is_multi_instance_request(messages)

        assert result is True

    def test_detects_every_instance(self, conversation_handler):
        """Test detection of 'every instance' request."""
        messages = [{"role": "user", "content": "Reboot every instance"}]

        result = conversation_handler._is_multi_instance_request(messages)

        assert result is True

    def test_single_instance_not_detected(self, conversation_handler):
        """Test single instance request is not detected as multi."""
        messages = [{"role": "user", "content": "Stop instance i-123"}]

        result = conversation_handler._is_multi_instance_request(messages)

        assert result is False

    def test_empty_messages(self, conversation_handler):
        """Test empty messages returns False."""
        result = conversation_handler._is_multi_instance_request([])

        assert result is False


class TestValidateMultiInstanceTools:
    """Test multi-instance tool validation."""

    def test_validates_multiple_instances_single_command(self, conversation_handler):
        """Test validation passes with multiple instances in one command."""
        tool_uses = [
            {
                "name": "send-command",
                "input": {"InstanceIds": ["i-123", "i-456"]},
            }
        ]

        result = conversation_handler._validate_multi_instance_tools(tool_uses, True)

        assert result is True

    def test_validates_multiple_commands(self, conversation_handler):
        """Test validation passes with multiple separate commands."""
        tool_uses = [
            {
                "name": "send-command",
                "input": {"InstanceIds": ["i-123"]},
            },
            {
                "name": "send-command",
                "input": {"InstanceIds": ["i-456"]},
            },
        ]

        result = conversation_handler._validate_multi_instance_tools(tool_uses, True)

        assert result is True

    def test_fails_single_instance_multi_request(self, conversation_handler):
        """Test validation fails when only one instance for multi request."""
        tool_uses = [
            {
                "name": "send-command",
                "input": {"InstanceIds": ["i-123"]},
            }
        ]

        result = conversation_handler._validate_multi_instance_tools(tool_uses, True)

        assert result is False

    def test_allows_list_instances_only(self, conversation_handler):
        """Test validation passes when only listing instances (discovery)."""
        tool_uses = [
            {
                "name": "list-instances",
                "input": {},
            }
        ]

        result = conversation_handler._validate_multi_instance_tools(tool_uses, True)

        assert result is True

    def test_skips_validation_for_non_multi(self, conversation_handler):
        """Test validation skipped for non-multi-instance requests."""
        tool_uses = [
            {
                "name": "send-command",
                "input": {"InstanceIds": ["i-123"]},
            }
        ]

        result = conversation_handler._validate_multi_instance_tools(tool_uses, False)

        assert result is True


class TestProcessToolUses:
    """Test processing tool uses."""

    @pytest.mark.asyncio
    async def test_process_list_instances_tool(self, conversation_handler, mock_mcp_manager):
        """Test processing list-instances tool."""
        tool_uses = [
            {
                "id": "tool1",
                "name": "list-instances",
                "input": {},
            }
        ]
        mock_mcp_manager.call_aws_api_tool.return_value = {"instances": []}

        results = await conversation_handler._process_tool_uses(tool_uses, None)

        assert len(results) == 1
        assert results[0]["type"] == "tool_result"
        assert results[0]["tool_use_id"] == "tool1"
        mock_mcp_manager.call_aws_api_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_tool_with_error(self, conversation_handler, mock_mcp_manager):
        """Test processing tool that raises an error."""
        tool_uses = [
            {
                "id": "tool1",
                "name": "list-instances",
                "input": {},
            }
        ]
        mock_mcp_manager.call_aws_api_tool.side_effect = Exception("API Error")

        results = await conversation_handler._process_tool_uses(tool_uses, None)

        assert len(results) == 1
        assert results[0]["type"] == "tool_result"
        assert "error" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_process_unknown_tool(self, conversation_handler):
        """Test processing unknown tool."""
        tool_uses = [
            {
                "id": "tool1",
                "name": "unknown-tool",
                "input": {},
            }
        ]

        results = await conversation_handler._process_tool_uses(tool_uses, None)

        assert len(results) == 1
        assert "error" in results[0]["content"]
        assert "Unknown tool" in results[0]["content"]


class TestExtractFinalResponse:
    """Test extracting final response from text responses."""

    def test_extract_plain_text(self, conversation_handler):
        """Test extracting plain text response."""
        text_responses = [{"text": "Hello world"}]

        result = conversation_handler._extract_final_response(text_responses)

        assert result == "Hello world"

    def test_extract_multiple_text_blocks(self, conversation_handler):
        """Test extracting multiple text blocks."""
        text_responses = [{"text": "Hello"}, {"text": " world"}]

        result = conversation_handler._extract_final_response(text_responses)

        assert result == "Hello  world"  # Space-separated by join

    def test_extract_adaptive_card(self, conversation_handler):
        """Test extracting adaptive card from response."""
        text_responses = [{"text": '{"adaptive_card": true, "type": "AdaptiveCard", "body": []}'}]

        result = conversation_handler._extract_final_response(text_responses)

        assert isinstance(result, dict)
        assert result["adaptive_card"] is True

    def test_extract_empty_returns_default(self, conversation_handler):
        """Test extracting from empty responses returns default message."""
        result = conversation_handler._extract_final_response([])

        assert "completed analyzing" in result.lower()


class TestResumeConversation:
    """Test resuming conversation from stored state."""

    @pytest.mark.asyncio
    async def test_resume_returns_none_for_ssm_tracker(
        self, conversation_handler, mock_state_manager, sample_conversation_state
    ):
        """Test resume returns None when SSM tracker is handling conversation."""
        sample_conversation_state.handled_by_ssm_tracker = True
        sample_conversation_state.messages = [{"role": "user", "content": "test"}]
        mock_state_manager.get_state.return_value = sample_conversation_state

        result = await conversation_handler.resume_conversation("user123", None)

        assert result is None

    @pytest.mark.asyncio
    async def test_resume_error_when_no_messages(
        self, conversation_handler, mock_state_manager, sample_conversation_state
    ):
        """Test resume returns error when no messages in state."""
        sample_conversation_state.messages = []
        mock_state_manager.get_state.return_value = sample_conversation_state

        result = await conversation_handler.resume_conversation("user123", None)

        assert "Error" in result
        assert "state not found" in result


class TestConversationStateModel:
    """Test ConversationState model extensions."""

    def test_store_conversation_for_resume(self):
        """Test storing conversation data for resume."""
        state = ConversationState(
            conversation_id="test-123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        messages = [{"role": "user", "content": "test"}]
        available_tools = ["list-instances"]
        pending_tool_uses = [{"id": "tool1"}]
        instance_platforms = {"i-123": "linux"}

        state.store_conversation_for_resume(
            messages=messages,
            iteration=1,
            available_tools=available_tools,
            pending_tool_uses=pending_tool_uses,
            original_prompt="test prompt",
            instance_platforms=instance_platforms,
        )

        assert state.iteration == 1
        assert state.messages == messages
        assert state.available_tools == available_tools
        assert state.pending_tool_uses == pending_tool_uses
        assert state.original_prompt == "test prompt"
        assert state.instance_platforms == instance_platforms

    def test_store_conversation_infers_prompt_from_messages(self):
        """Test storing conversation infers prompt from first message."""
        state = ConversationState(
            conversation_id="test-123",
            iteration=0,
            original_prompt=None,
            handled_by_ssm_tracker=False,
        )

        messages = [{"role": "user", "content": "inferred prompt"}]

        state.store_conversation_for_resume(
            messages=messages,
            iteration=1,
            available_tools=[],
            pending_tool_uses=[],
        )

        assert state.original_prompt == "inferred prompt"


class TestCallBedrockWithTools:
    """Test call_bedrock_with_tools method."""

    @pytest.mark.asyncio
    async def test_call_bedrock_with_tools_no_tool_uses(
        self, conversation_handler, mock_bedrock_client
    ):
        """Test calling Bedrock with tools when no tool uses are returned."""
        request = {
            "messages": [{"role": "user", "content": "Hello"}],
            "tools": [],
            "system": "Test system prompt",
        }

        mock_bedrock_client.call_bedrock_with_tools.return_value = {
            "content": [{"type": "text", "text": "Hello there"}],
            "stop_reason": "end_turn",
        }

        result = await conversation_handler.call_bedrock_with_tools(request, None, 0)

        assert result == "Hello there"
        mock_bedrock_client.call_bedrock_with_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_bedrock_with_tools_with_tool_use(
        self, conversation_handler, mock_bedrock_client, mock_mcp_manager
    ):
        """Test calling Bedrock with tools when tool uses are returned."""
        request = {
            "messages": [{"role": "user", "content": "List instances"}],
            "tools": [{"name": "list-instances"}],
            "system": "Test system prompt",
        }

        # First response with tool use
        mock_bedrock_client.call_bedrock_with_tools.side_effect = [
            {
                "content": [
                    {"type": "tool_use", "id": "tool1", "name": "list-instances", "input": {}}
                ],
                "stop_reason": "tool_use",
            },
            # Second response after tool result
            {
                "content": [{"type": "text", "text": "Here are your instances"}],
                "stop_reason": "end_turn",
            },
        ]

        mock_mcp_manager.call_aws_api_tool.return_value = {"instances": []}

        result = await conversation_handler.call_bedrock_with_tools(request, None, 0)

        assert result == "Here are your instances"
        assert mock_bedrock_client.call_bedrock_with_tools.call_count == 2

    @pytest.mark.asyncio
    async def test_call_bedrock_with_tools_max_iterations(
        self, conversation_handler, mock_bedrock_client
    ):
        """Test max iterations limit is enforced."""
        request = {
            "messages": [{"role": "user", "content": "Hello"}],
            "tools": [],
            "system": "Test system prompt",
        }

        # Always return tool use to force hitting max iterations
        mock_bedrock_client.call_bedrock_with_tools.return_value = {
            "content": [{"type": "tool_use", "id": "tool1", "name": "list-instances", "input": {}}],
            "stop_reason": "tool_use",
        }

        result = await conversation_handler.call_bedrock_with_tools(request, None, 0)

        assert "reached the processing limit" in result

    @pytest.mark.asyncio
    async def test_call_bedrock_with_tools_validation_failure_retries(
        self, conversation_handler, mock_bedrock_client, mock_mcp_manager
    ):
        """Test multi-instance validation failure triggers retry."""
        request = {
            "messages": [{"role": "user", "content": "Stop all instances"}],
            "tools": [{"name": "send-command"}],
            "system": "Test system prompt",
        }

        # First response with invalid single instance (should fail validation)
        # Then corrected response
        mock_bedrock_client.call_bedrock_with_tools.side_effect = [
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool1",
                        "name": "send-command",
                        "input": {"InstanceIds": ["i-123"]},
                    }
                ],
                "stop_reason": "tool_use",
            },
            # After correction
            {
                "content": [{"type": "text", "text": "Commands sent to all instances"}],
                "stop_reason": "end_turn",
            },
        ]

        result = await conversation_handler.call_bedrock_with_tools(request, None, 0)

        assert isinstance(result, str)
        assert mock_bedrock_client.call_bedrock_with_tools.call_count == 2

    @pytest.mark.asyncio
    async def test_call_bedrock_with_tools_error_handling(
        self, conversation_handler, mock_bedrock_client
    ):
        """Test error handling in call_bedrock_with_tools."""
        request = {
            "messages": [{"role": "user", "content": "Hello"}],
            "tools": [],
            "system": "Test system prompt",
        }

        mock_bedrock_client.call_bedrock_with_tools.side_effect = Exception("Bedrock error")

        result = await conversation_handler.call_bedrock_with_tools(request, None, 0)

        assert "error" in result.lower()
        assert "Bedrock error" in result


class TestResumeConversationFull:
    """Test resume_conversation with full flow."""

    @pytest.mark.asyncio
    async def test_resume_conversation_with_tool_execution(
        self,
        conversation_handler,
        mock_state_manager,
        sample_conversation_state,
        mock_mcp_manager,
        mock_bedrock_client,
    ):
        """Test resuming conversation with tool execution."""
        sample_conversation_state.messages = [{"role": "user", "content": "test"}]
        sample_conversation_state.pending_tool_uses = [
            {"id": "tool1", "name": "list-instances", "input": {}}
        ]
        sample_conversation_state.available_tools = ["list-instances"]
        mock_state_manager.get_state.return_value = sample_conversation_state

        mock_mcp_manager.call_aws_api_tool.return_value = {"instances": []}
        mock_mcp_manager.get_tool_schema.return_value = {"name": "list-instances"}
        mock_bedrock_client.call_bedrock_with_tools.return_value = {
            "content": [{"type": "text", "text": "Here are your instances"}],
            "stop_reason": "end_turn",
        }

        result = await conversation_handler.resume_conversation("user123", None)

        assert result == "Here are your instances"
        mock_mcp_manager.call_aws_api_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_conversation_with_missing_tool_info(
        self,
        conversation_handler,
        mock_state_manager,
        sample_conversation_state,
        mock_bedrock_client,
    ):
        """Test resuming conversation with missing tool name or ID."""
        sample_conversation_state.messages = [{"role": "user", "content": "test"}]
        sample_conversation_state.pending_tool_uses = [{"name": "list-instances"}]  # Missing ID
        sample_conversation_state.available_tools = ["list-instances"]
        mock_state_manager.get_state.return_value = sample_conversation_state

        mock_bedrock_client.call_bedrock_with_tools.return_value = {
            "content": [{"type": "text", "text": "Completed"}],
            "stop_reason": "end_turn",
        }

        result = await conversation_handler.resume_conversation("user123", None)

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_resume_conversation_tool_execution_error(
        self,
        conversation_handler,
        mock_state_manager,
        sample_conversation_state,
        mock_mcp_manager,
        mock_bedrock_client,
    ):
        """Test resuming conversation when tool execution fails."""
        sample_conversation_state.messages = [{"role": "user", "content": "test"}]
        sample_conversation_state.pending_tool_uses = [
            {"id": "tool1", "name": "list-instances", "input": {}}
        ]
        sample_conversation_state.available_tools = ["list-instances"]
        mock_state_manager.get_state.return_value = sample_conversation_state

        mock_mcp_manager.call_aws_api_tool.side_effect = Exception("Tool error")
        mock_mcp_manager.get_tool_schema.return_value = {"name": "list-instances"}
        mock_bedrock_client.call_bedrock_with_tools.return_value = {
            "content": [{"type": "text", "text": "Error handled"}],
            "stop_reason": "end_turn",
        }

        result = await conversation_handler.resume_conversation("user123", None)

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_resume_conversation_no_tool_results(
        self,
        conversation_handler,
        mock_state_manager,
        sample_conversation_state,
        mock_bedrock_client,
    ):
        """Test resuming conversation when no tool results are generated."""
        sample_conversation_state.messages = [{"role": "user", "content": "test"}]
        sample_conversation_state.pending_tool_uses = [
            {"id": "tool1"}  # Missing name - will be skipped
        ]
        sample_conversation_state.available_tools = []
        mock_state_manager.get_state.return_value = sample_conversation_state

        mock_bedrock_client.call_bedrock_with_tools.return_value = {
            "content": [{"type": "text", "text": "Handled placeholder"}],
            "stop_reason": "end_turn",
        }

        result = await conversation_handler.resume_conversation("user123", None)

        assert isinstance(result, str)


class TestExecuteApprovedTool:
    """Test _execute_approved_tool method."""

    @pytest.mark.asyncio
    async def test_execute_non_ssm_tool(
        self,
        conversation_handler,
        mock_mcp_manager,
        sample_conversation_state,
    ):
        """Test executing a non-SSM tool."""
        tool_result = await conversation_handler._execute_approved_tool(
            tool_name="list-instances",
            tool_input={},
            tool_id="tool1",
            user_id="user123",
            turn_context=None,
            state=sample_conversation_state,
        )

        assert tool_result is not None
        mock_mcp_manager.call_aws_api_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_approved_ssm_command(
        self,
        conversation_handler,
        mock_mcp_manager,
        mock_state_manager,
        sample_conversation_state,
    ):
        """Test executing an approved SSM command."""
        from unittest.mock import Mock

        from ohlala_smartops.models.approvals import ApprovalStatus

        # Mock the approval object
        approval = Mock()
        approval.status = ApprovalStatus.APPROVED
        mock_state_manager.get_approval.return_value = approval

        # Mock different responses for different calls
        async def mock_call_aws_api_tool(tool_name, tool_input, **kwargs):
            if tool_name == "execute_ssm_sync":
                return {
                    "CommandId": "cmd-123",
                    "Command": {"CommandId": "cmd-123"},
                }
            if tool_name == "get-command-invocation":
                # Return completed status immediately to avoid wait loop
                return {"Status": "Success", "CommandId": "cmd-123"}
            return {}

        mock_mcp_manager.call_aws_api_tool.side_effect = mock_call_aws_api_tool

        tool_result = await conversation_handler._execute_approved_tool(
            tool_name="execute_ssm_sync",
            tool_input={"Commands": ["echo test"], "InstanceIds": ["i-123"]},
            tool_id="tool1",
            user_id="user123",
            turn_context=None,
            state=sample_conversation_state,
        )

        assert tool_result is not None
        assert "CommandId" in tool_result

    @pytest.mark.asyncio
    async def test_execute_rejected_ssm_command(
        self,
        conversation_handler,
        mock_state_manager,
        sample_conversation_state,
    ):
        """Test executing a rejected SSM command."""
        from unittest.mock import Mock

        from ohlala_smartops.models.approvals import ApprovalStatus

        # Mock the approval object
        approval = Mock()
        approval.status = ApprovalStatus.REJECTED
        mock_state_manager.get_approval.return_value = approval

        tool_result = await conversation_handler._execute_approved_tool(
            tool_name="execute_ssm_sync",
            tool_input={"Commands": ["echo test"]},
            tool_id="tool1",
            user_id="user123",
            turn_context=None,
            state=sample_conversation_state,
        )

        assert tool_result is not None
        assert "denied" in tool_result
        assert tool_result["denied"] is True

    @pytest.mark.asyncio
    async def test_execute_ssm_command_needs_approval(
        self,
        conversation_handler,
        mock_state_manager,
        sample_conversation_state,
    ):
        """Test executing SSM command that still needs approval."""
        from unittest.mock import Mock

        from ohlala_smartops.models.approvals import ApprovalStatus

        # Mock the approval object
        approval = Mock()
        approval.status = ApprovalStatus.PENDING
        mock_state_manager.get_approval.return_value = approval

        tool_result = await conversation_handler._execute_approved_tool(
            tool_name="execute_ssm_sync",
            tool_input={"Commands": ["echo test"]},
            tool_id="tool1",
            user_id="user123",
            turn_context=None,
            state=sample_conversation_state,
        )

        assert tool_result is None


class TestInvokeBedrockModel:
    """Test _invoke_bedrock_model method."""

    @pytest.mark.asyncio
    async def test_invoke_bedrock_model_basic(self, conversation_handler, mock_bedrock_client):
        """Test basic Bedrock model invocation."""
        request = {
            "messages": [{"role": "user", "content": "Hello"}],
            "tools": [{"name": "list-instances"}],
            "system": "Test prompt",
        }

        mock_bedrock_client.call_bedrock_with_tools.return_value = {
            "content": [{"type": "text", "text": "Hello"}],
            "stop_reason": "end_turn",
        }

        result = await conversation_handler._invoke_bedrock_model(request)

        assert result is not None
        assert "content" in result
        mock_bedrock_client.call_bedrock_with_tools.assert_called_once()


class TestProcessToolUsesExtended:
    """Extended tests for _process_tool_uses method."""

    @pytest.mark.asyncio
    async def test_process_get_command_invocation_with_tracker(
        self, conversation_handler, mock_command_tracker, mock_mcp_manager
    ):
        """Test processing get-command-invocation with command tracker."""
        tool_uses = [
            {
                "id": "tool1",
                "name": "get-command-invocation",
                "input": {"command_id": "cmd-123"},
            }
        ]

        mock_command_tracker.get_command_status.return_value = {
            "Status": "Success",
            "CommandId": "cmd-123",
        }

        results = await conversation_handler._process_tool_uses(tool_uses, None)

        assert len(results) == 1
        assert results[0]["type"] == "tool_result"
        mock_command_tracker.get_command_status.assert_called_once_with("cmd-123")
        # Should not call MCP manager if tracker has status
        mock_mcp_manager.call_aws_api_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_get_command_invocation_without_tracker_status(
        self, conversation_handler, mock_command_tracker, mock_mcp_manager
    ):
        """Test get-command-invocation when tracker has no status."""
        tool_uses = [
            {
                "id": "tool1",
                "name": "get-command-invocation",
                "input": {"command_id": "cmd-123"},
            }
        ]

        mock_command_tracker.get_command_status.return_value = None
        mock_mcp_manager.call_aws_api_tool.return_value = {
            "Status": "Success",
            "CommandId": "cmd-123",
        }

        results = await conversation_handler._process_tool_uses(tool_uses, None)

        assert len(results) == 1
        mock_mcp_manager.call_aws_api_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_get_command_invocation_no_command_id(
        self, conversation_handler, mock_mcp_manager
    ):
        """Test get-command-invocation without command_id."""
        tool_uses = [
            {
                "id": "tool1",
                "name": "get-command-invocation",
                "input": {},
            }
        ]

        mock_mcp_manager.call_aws_api_tool.return_value = {"Status": "Unknown"}

        results = await conversation_handler._process_tool_uses(tool_uses, None)

        assert len(results) == 1
        mock_mcp_manager.call_aws_api_tool.assert_called_once()
