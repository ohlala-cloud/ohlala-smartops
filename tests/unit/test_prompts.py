"""Unit tests for AI prompts module."""

from ohlala_smartops.ai.prompts import get_available_tools_section, get_system_prompt


def test_get_available_tools_section_few_tools() -> None:
    """Test formatting with fewer than 10 tools."""
    tools = ["list-instances", "send-command", "describe-instances"]
    result = get_available_tools_section(tools)
    assert result == "Available AWS tools: list-instances, send-command, describe-instances"


def test_get_available_tools_section_many_tools() -> None:
    """Test formatting with more than 10 tools (shows first 10 + ellipsis)."""
    tools = [f"tool-{i}" for i in range(15)]
    result = get_available_tools_section(tools)
    expected_tools = ", ".join(tools[:10]) + "..."
    expected = f"Available AWS tools: {expected_tools}"
    assert result == expected
    assert "tool-9" in result
    assert "tool-10" not in result


def test_get_system_prompt_basic() -> None:
    """Test basic system prompt generation with tools."""
    tools = ["list-instances", "send-command"]
    prompt = get_system_prompt(tools)

    # Verify key components are present
    assert "Ohlala SmartOps" in prompt
    assert len(prompt) > 1000  # Should be substantial


def test_get_system_prompt_with_context() -> None:
    """Test prompt generation with conversation context."""
    tools = ["list-instances"]
    context = "User previously asked about web servers"
    prompt = get_system_prompt(tools, conversation_context=context)

    assert "Ohlala SmartOps" in prompt
    assert "## Conversation Context" in prompt
    assert context in prompt


def test_get_system_prompt_with_instance_id() -> None:
    """Test prompt generation with last instance ID context."""
    tools = ["list-instances"]
    instance_id = "i-0abc123def456789"
    prompt = get_system_prompt(
        tools, conversation_context="Some context", last_instance_id=instance_id
    )

    assert "Ohlala SmartOps" in prompt
    assert "## Conversation Context" in prompt
    assert instance_id in prompt


def test_module_exports() -> None:
    """Test that the prompts module exports expected functions."""
    from ohlala_smartops.ai import prompts

    assert hasattr(prompts, "get_system_prompt")
    assert hasattr(prompts, "get_available_tools_section")
