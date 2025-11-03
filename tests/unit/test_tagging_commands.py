"""Tests for Phase 5E resource tagging commands.

This test suite covers the three tagging commands:
- TagCommand (/tag)
- UntagCommand (/untag)
- FindByTagsCommand (/find-tags)

Tests include success cases, error handling, edge cases, and confirmation workflow.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ohlala_smartops.commands.find_by_tags import FindByTagsCommand
from ohlala_smartops.commands.tag import TagCommand
from ohlala_smartops.commands.untag import UntagCommand


class TestTagCommand:
    """Test suite for TagCommand."""

    @pytest.fixture
    def command(self) -> TagCommand:
        """Create command instance."""
        return TagCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context with user info."""
        return {
            "mcp_manager": AsyncMock(),
            "user_id": "user-123",
            "user_name": "Test User",
        }

    def test_name_property(self, command: TagCommand) -> None:
        """Test command name."""
        assert command.name == "tag"

    def test_description_property(self, command: TagCommand) -> None:
        """Test command description."""
        assert "tag" in command.description.lower()

    def test_usage_property(self, command: TagCommand) -> None:
        """Test command usage."""
        assert command.usage.startswith("/tag")

    @pytest.mark.asyncio
    async def test_execute_no_args(self, command: TagCommand, mock_context: dict[str, Any]) -> None:
        """Test execute without arguments."""
        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "provide instance id" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_no_tags(self, command: TagCommand, mock_context: dict[str, Any]) -> None:
        """Test execute with instance but no tags."""
        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False
        assert "tag" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_no_user_id(self, command: TagCommand) -> None:
        """Test execute without user ID in context."""
        context = {"mcp_manager": AsyncMock()}
        result = await command.execute(["i-1234567890abcdef0", "Env=Prod"], context)

        assert result["success"] is False
        assert "unable to identify user" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_instance(
        self, command: TagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with invalid instance ID."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("Instance not found")

        result = await command.execute(["i-1234567890abcdef0", "Env=Prod"], mock_context)

        assert result["success"] is False

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.tag.confirmation_manager")
    async def test_execute_success_creates_confirmation(
        self, mock_conf_mgr: MagicMock, command: TagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test successful execution creates confirmation request."""
        mock_mcp = mock_context["mcp_manager"]

        def mock_call_side_effect(tool_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if tool_name == "describe-instances":
                return {
                    "instances": [
                        {
                            "InstanceId": "i-1234567890abcdef0",
                            "Name": "test-instance",
                            "State": "running",
                        }
                    ]
                }
            if tool_name == "get-resource-tags":
                return {"tags": {"i-1234567890abcdef0": {"OldTag": "OldValue"}}}
            return {}

        mock_mcp.call_aws_api_tool.side_effect = mock_call_side_effect

        # Mock confirmation manager
        mock_operation = MagicMock()
        mock_operation.id = "op-123"
        mock_operation.user_name = "Test User"
        mock_conf_mgr.create_confirmation_request.return_value = mock_operation

        result = await command.execute(
            ["i-1234567890abcdef0", "Environment=Production"], mock_context
        )

        assert result["success"] is True
        assert "card" in result
        mock_conf_mgr.create_confirmation_request.assert_called_once()

        # Verify confirmation request parameters
        call_args = mock_conf_mgr.create_confirmation_request.call_args
        assert call_args.kwargs["operation_type"] == "tag-resources"
        assert call_args.kwargs["resource_ids"] == ["i-1234567890abcdef0"]
        assert "Environment" in call_args.kwargs["additional_data"]["tags"]

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.tag.confirmation_manager")
    async def test_execute_multiple_tags(
        self, mock_conf_mgr: MagicMock, command: TagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with multiple tags."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {"InstanceId": "i-1234567890abcdef0", "Name": "test", "State": "running"}
            ],
            "tags": {},
        }

        mock_operation = MagicMock()
        mock_operation.id = "op-123"
        mock_operation.user_name = "Test User"
        mock_conf_mgr.create_confirmation_request.return_value = mock_operation

        result = await command.execute(
            ["i-1234567890abcdef0", "Env=Prod", "Team=Ops", "Version=1.0"], mock_context
        )

        assert result["success"] is True
        call_args = mock_conf_mgr.create_confirmation_request.call_args
        tags = call_args.kwargs["additional_data"]["tags"]
        assert len(tags) == 3
        assert tags["Env"] == "Prod"
        assert tags["Team"] == "Ops"
        assert tags["Version"] == "1.0"

    def test_parse_tag_args_no_args(self, command: TagCommand) -> None:
        """Test parsing with no arguments."""
        result = command._parse_tag_args([])
        assert result["success"] is False

    def test_parse_tag_args_success(self, command: TagCommand) -> None:
        """Test successful argument parsing."""
        result = command._parse_tag_args(["i-1234567890abcdef0", "Env=Prod", "Team=Dev"])
        assert result["success"] is True
        assert result["instance_ids"] == ["i-1234567890abcdef0"]
        assert result["tags"] == {"Env": "Prod", "Team": "Dev"}

    def test_parse_tag_args_aws_prefix(self, command: TagCommand) -> None:
        """Test parsing rejects aws: prefix."""
        result = command._parse_tag_args(["i-1234567890abcdef0", "aws:test=value"])
        assert result["success"] is False
        assert "aws:" in result["error"].lower()

    def test_parse_tag_args_key_too_long(self, command: TagCommand) -> None:
        """Test parsing rejects key over 128 characters."""
        long_key = "a" * 129
        result = command._parse_tag_args(["i-1234567890abcdef0", f"{long_key}=value"])
        assert result["success"] is False
        assert "too long" in result["error"].lower()

    def test_parse_tag_args_value_too_long(self, command: TagCommand) -> None:
        """Test parsing rejects value over 256 characters."""
        long_value = "v" * 257
        result = command._parse_tag_args(["i-1234567890abcdef0", f"key={long_value}"])
        assert result["success"] is False
        assert "too long" in result["error"].lower()

    def test_parse_tag_args_multiple_instances(self, command: TagCommand) -> None:
        """Test parsing multiple instance IDs."""
        result = command._parse_tag_args(["i-1234567890abcdef0,i-1234567890abcdef1", "Env=Prod"])
        assert result["success"] is True
        assert len(result["instance_ids"]) == 2


class TestUntagCommand:
    """Test suite for UntagCommand."""

    @pytest.fixture
    def command(self) -> UntagCommand:
        """Create command instance."""
        return UntagCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context with user info."""
        return {
            "mcp_manager": AsyncMock(),
            "user_id": "user-123",
            "user_name": "Test User",
        }

    def test_name_property(self, command: UntagCommand) -> None:
        """Test command name."""
        assert command.name == "untag"

    def test_description_property(self, command: UntagCommand) -> None:
        """Test command description."""
        assert "remove" in command.description.lower() or "untag" in command.description.lower()

    def test_usage_property(self, command: UntagCommand) -> None:
        """Test command usage."""
        assert command.usage.startswith("/untag")

    @pytest.mark.asyncio
    async def test_execute_no_args(
        self, command: UntagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute without arguments."""
        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "provide instance id" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_no_keys(
        self, command: UntagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with instance but no tag keys."""
        result = await command.execute(["i-1234567890abcdef0"], mock_context)

        assert result["success"] is False
        assert "tag" in result["message"].lower()

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.untag.confirmation_manager")
    async def test_execute_success_creates_confirmation(
        self, mock_conf_mgr: MagicMock, command: UntagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test successful execution creates confirmation request."""
        mock_mcp = mock_context["mcp_manager"]

        def mock_call_side_effect(tool_name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            if tool_name == "describe-instances":
                return {
                    "instances": [
                        {"InstanceId": "i-1234567890abcdef0", "Name": "test", "State": "running"}
                    ]
                }
            if tool_name == "get-resource-tags":
                return {"tags": {"i-1234567890abcdef0": {"Environment": "Dev", "TempTag": "X"}}}
            return {}

        mock_mcp.call_aws_api_tool.side_effect = mock_call_side_effect

        mock_operation = MagicMock()
        mock_operation.id = "op-123"
        mock_operation.user_name = "Test User"
        mock_conf_mgr.create_confirmation_request.return_value = mock_operation

        result = await command.execute(["i-1234567890abcdef0", "TempTag"], mock_context)

        assert result["success"] is True
        assert "card" in result
        mock_conf_mgr.create_confirmation_request.assert_called_once()

        call_args = mock_conf_mgr.create_confirmation_request.call_args
        assert call_args.kwargs["operation_type"] == "remove-tags"
        assert "TempTag" in call_args.kwargs["additional_data"]["tag_keys"]

    @pytest.mark.asyncio
    @patch("ohlala_smartops.commands.untag.confirmation_manager")
    async def test_execute_multiple_keys(
        self, mock_conf_mgr: MagicMock, command: UntagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with multiple tag keys."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {"InstanceId": "i-1234567890abcdef0", "Name": "test", "State": "running"}
            ],
            "tags": {},
        }

        mock_operation = MagicMock()
        mock_operation.id = "op-123"
        mock_operation.user_name = "Test User"
        mock_conf_mgr.create_confirmation_request.return_value = mock_operation

        result = await command.execute(
            ["i-1234567890abcdef0", "OldTag", "TempTag", "BadTag"], mock_context
        )

        assert result["success"] is True
        call_args = mock_conf_mgr.create_confirmation_request.call_args
        tag_keys = call_args.kwargs["additional_data"]["tag_keys"]
        assert len(tag_keys) == 3

    def test_parse_untag_args_success(self, command: UntagCommand) -> None:
        """Test successful argument parsing."""
        result = command._parse_untag_args(["i-1234567890abcdef0", "OldTag", "TempTag"])
        assert result["success"] is True
        assert result["instance_ids"] == ["i-1234567890abcdef0"]
        assert "OldTag" in result["tag_keys"]
        assert "TempTag" in result["tag_keys"]

    def test_parse_untag_args_aws_prefix(self, command: UntagCommand) -> None:
        """Test parsing rejects aws: prefix."""
        result = command._parse_untag_args(["i-1234567890abcdef0", "aws:test"])
        assert result["success"] is False
        assert "aws" in result["error"].lower()


class TestFindByTagsCommand:
    """Test suite for FindByTagsCommand."""

    @pytest.fixture
    def command(self) -> FindByTagsCommand:
        """Create command instance."""
        return FindByTagsCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context."""
        return {"mcp_manager": AsyncMock()}

    def test_name_property(self, command: FindByTagsCommand) -> None:
        """Test command name."""
        assert command.name == "find-tags"

    def test_description_property(self, command: FindByTagsCommand) -> None:
        """Test command description."""
        assert "find" in command.description.lower() or "search" in command.description.lower()

    def test_usage_property(self, command: FindByTagsCommand) -> None:
        """Test command usage."""
        assert command.usage.startswith("/find-tags")

    @pytest.mark.asyncio
    async def test_execute_no_filters(
        self, command: FindByTagsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute without filters."""
        result = await command.execute([], mock_context)

        assert result["success"] is False
        assert "provide tag filter" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_execute_no_matches(
        self, command: FindByTagsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute when no instances match."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-123",
                    "Name": "test",
                    "State": "running",
                    "Tags": {"Environment": "Dev"},
                }
            ]
        }

        result = await command.execute(["Environment=Production"], mock_context)

        assert result["success"] is True
        assert (
            "0" in result["message"]
            or "no" in result["card"]["body"][2]["items"][0]["text"].lower()
        )

    @pytest.mark.asyncio
    async def test_execute_with_matches(
        self, command: FindByTagsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with matching instances."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-123",
                    "Name": "prod-1",
                    "State": "running",
                    "InstanceType": "t3.micro",
                    "PrivateIpAddress": "10.0.1.5",
                    "Tags": {"Environment": "Production", "Team": "DevOps"},
                },
                {
                    "InstanceId": "i-456",
                    "Name": "dev-1",
                    "State": "running",
                    "InstanceType": "t3.micro",
                    "PrivateIpAddress": "10.0.1.6",
                    "Tags": {"Environment": "Dev", "Team": "DevOps"},
                },
            ]
        }

        result = await command.execute(["Environment=Production"], mock_context)

        assert result["success"] is True
        assert "1" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_multiple_filters(
        self, command: FindByTagsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with multiple filters (AND logic)."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-123",
                    "Name": "prod-1",
                    "State": "running",
                    "InstanceType": "t3.micro",
                    "PrivateIpAddress": "10.0.1.5",
                    "Tags": {"Environment": "Production", "Team": "DevOps"},
                },
                {
                    "InstanceId": "i-456",
                    "Name": "prod-2",
                    "State": "running",
                    "InstanceType": "t3.micro",
                    "PrivateIpAddress": "10.0.1.6",
                    "Tags": {"Environment": "Production", "Team": "Platform"},
                },
            ]
        }

        result = await command.execute(["Environment=Production", "Team=DevOps"], mock_context)

        assert result["success"] is True
        assert "1" in result["message"]  # Only one instance matches both

    @pytest.mark.asyncio
    async def test_execute_key_only_filter(
        self, command: FindByTagsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with key-only filter (any value)."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {
            "instances": [
                {
                    "InstanceId": "i-123",
                    "Name": "inst-1",
                    "State": "running",
                    "InstanceType": "t3.micro",
                    "PrivateIpAddress": "10.0.1.5",
                    "Tags": {"Project": "WebApp"},
                },
                {
                    "InstanceId": "i-456",
                    "Name": "inst-2",
                    "State": "running",
                    "InstanceType": "t3.micro",
                    "PrivateIpAddress": "10.0.1.6",
                    "Tags": {"Environment": "Dev"},
                },
            ]
        }

        result = await command.execute(["Project"], mock_context)

        assert result["success"] is True
        assert "1" in result["message"]  # Only i-123 has Project tag

    def test_parse_tag_filters_key_value(self, command: FindByTagsCommand) -> None:
        """Test parsing key=value filters."""
        result = command._parse_tag_filters(["Environment=Production", "Team=DevOps"])
        assert result["success"] is True
        assert result["tag_filters"]["Environment"] == "Production"
        assert result["tag_filters"]["Team"] == "DevOps"

    def test_parse_tag_filters_key_only(self, command: FindByTagsCommand) -> None:
        """Test parsing key-only filters."""
        result = command._parse_tag_filters(["Project", "Owner"])
        assert result["success"] is True
        assert result["tag_filters"]["Project"] is None
        assert result["tag_filters"]["Owner"] is None

    def test_parse_tag_filters_mixed(self, command: FindByTagsCommand) -> None:
        """Test parsing mixed filters."""
        result = command._parse_tag_filters(["Environment=Production", "Project"])
        assert result["success"] is True
        assert result["tag_filters"]["Environment"] == "Production"
        assert result["tag_filters"]["Project"] is None

    def test_parse_tag_filters_empty_key(self, command: FindByTagsCommand) -> None:
        """Test parsing with empty key in key=value."""
        result = command._parse_tag_filters(["=Value"])
        assert result["success"] is False
        assert "cannot be empty" in result["error"]

    def test_parse_tag_filters_only_whitespace(self, command: FindByTagsCommand) -> None:
        """Test parsing with only whitespace keys."""
        result = command._parse_tag_filters(["  ", "\t"])
        assert result["success"] is False
        assert "No valid tag filters" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_mcp_tool_failure(
        self, command: FindByTagsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execution when MCP tool call fails."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("MCP call failed")

        result = await command.execute(["Environment=Production"], mock_context)

        assert result["success"] is False
        assert "Failed to search instances" in result["error"]
        assert "card" in result

    @pytest.mark.asyncio
    async def test_execute_general_exception(
        self, command: FindByTagsCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test general exception handling in execute."""
        # Cause an exception by making _parse_tag_filters fail unexpectedly
        with patch.object(
            command, "_parse_tag_filters", side_effect=RuntimeError("Unexpected error")
        ):
            result = await command.execute(["Environment=Production"], mock_context)

            assert result["success"] is False
            assert "Failed to find instances" in result["error"]
            assert "card" in result


# Additional tests for TagCommand - Error paths and callbacks
class TestTagCommandAdditional:
    """Additional tests for TagCommand to improve coverage."""

    @pytest.fixture
    def command(self) -> TagCommand:
        """Create command instance."""
        return TagCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context with user info."""
        return {
            "mcp_manager": AsyncMock(),
            "user_id": "user-123",
            "user_name": "Test User",
        }

    @pytest.mark.asyncio
    async def test_parse_tag_args_with_whitespace_keys(self, command: TagCommand) -> None:
        """Test parsing tags with whitespace-only keys are skipped."""
        result = command._parse_tag_args(["i-1234567890abcdef0", "  ", "\t", "Valid=Value"])

        assert result["success"] is True
        assert len(result["tags"]) == 1
        assert result["tags"]["Valid"] == "Value"

    @pytest.mark.asyncio
    async def test_execute_general_exception(
        self, command: TagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test general exception handling in execute."""
        with patch.object(command, "_parse_tag_args", side_effect=RuntimeError("Unexpected error")):
            result = await command.execute(["i-123", "Environment=Production"], mock_context)

            assert result["success"] is False
            assert "Failed to tag instances" in result["error"]
            assert "card" in result

    def test_parse_tag_args_too_many_tags(self, command: TagCommand) -> None:
        """Test parsing when more than 50 tags provided."""
        # Create instance ID + 51 tags
        args = ["i-1234567890abcdef0"] + [f"Tag{i}=Value{i}" for i in range(51)]
        result = command._parse_tag_args(args)

        assert result["success"] is False
        assert "Too many tags" in result["error"]
        assert "50" in result["error"]

    def test_parse_tag_args_empty_key(self, command: TagCommand) -> None:
        """Test parsing with empty tag key."""
        result = command._parse_tag_args(["i-1234567890abcdef0", "=Value"])

        assert result["success"] is False
        assert "key cannot be empty" in result["error"]

    def test_parse_tag_args_no_instance_ids(self, command: TagCommand) -> None:
        """Test parsing with no instance IDs."""
        # With less than 2 args
        result = command._parse_tag_args(["Environment=Production"])

        assert result["success"] is False
        assert "both instance ID(s) and tag(s)" in result["error"]

    @pytest.mark.asyncio
    async def test_get_current_tags_exception(
        self, command: TagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test _get_current_tags when MCP call fails."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("MCP failed")

        result = await command._get_current_tags(["i-123"], mock_context)

        # Should return empty dict on error
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_current_tags_invalid_response(
        self, command: TagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test _get_current_tags with invalid response format."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {"tags": "not-a-dict"}

        result = await command._get_current_tags(["i-123"], mock_context)

        # Should return empty dict for invalid format
        assert result == {}


# Additional tests for UntagCommand - Error paths and callbacks
class TestUntagCommandAdditional:
    """Additional tests for UntagCommand to improve coverage."""

    @pytest.fixture
    def command(self) -> UntagCommand:
        """Create command instance."""
        return UntagCommand()

    @pytest.fixture
    def mock_context(self) -> dict[str, Any]:
        """Create mock context with user info."""
        return {
            "mcp_manager": AsyncMock(),
            "user_id": "user-123",
            "user_name": "Test User",
        }

    @pytest.mark.asyncio
    async def test_execute_general_exception(
        self, command: UntagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test general exception handling in execute."""
        with patch.object(
            command, "_parse_untag_args", side_effect=RuntimeError("Unexpected error")
        ):
            result = await command.execute(["i-123", "TempTag"], mock_context)

            assert result["success"] is False
            assert "Failed to remove tags" in result["error"]
            assert "card" in result

    @pytest.mark.asyncio
    async def test_execute_no_user_id(
        self, command: UntagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute when user_id is missing."""
        mock_context["user_id"] = None

        result = await command.execute(["i-123", "TempTag"], mock_context)

        assert result["success"] is False
        assert "Unable to identify user" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_invalid_instance(
        self, command: UntagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test execute with invalid instance ID."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.return_value = {"instances": []}

        result = await command.execute(["i-1234567890abcdef0", "TempTag"], mock_context)

        assert result["success"] is False
        # Instance validation will fail if instance not found
        assert "No instances found" in result["message"]

    def test_parse_untag_args_no_instance_ids(self, command: UntagCommand) -> None:
        """Test parsing with no valid instance IDs."""
        result = command._parse_untag_args(["TempTag", "OldTag"])

        assert result["success"] is False
        assert "No valid instance IDs found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_current_tags_exception(
        self, command: UntagCommand, mock_context: dict[str, Any]
    ) -> None:
        """Test _get_current_tags when MCP call fails."""
        mock_mcp = mock_context["mcp_manager"]
        mock_mcp.call_aws_api_tool.side_effect = Exception("MCP failed")

        result = await command._get_current_tags(["i-123"], mock_context)

        # Should return empty dict on error
        assert result == {}
