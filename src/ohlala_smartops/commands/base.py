"""Base class for all Ohlala SmartOps slash commands.

This module provides the BaseCommand abstract class that all slash commands
inherit from. It includes helper methods for MCP integration, instance validation,
and adaptive card creation.

Phase 5A: Core command infrastructure with simplified pattern matching
CommandHandler protocol requirements.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Final, cast

logger: Final = logging.getLogger(__name__)


class BaseCommand(ABC):
    """Base class for all slash command handlers.

    This class provides common functionality for commands including:
    - MCP tool integration
    - Instance ID parsing and validation
    - Adaptive card creation with brand colors
    - Error handling

    All commands must implement the abstract properties and execute method
    to match the CommandHandler protocol.

    Example:
        >>> class MyCommand(BaseCommand):
        ...     @property
        ...     def name(self) -> str:
        ...         return "mycommand"
        ...
        ...     @property
        ...     def description(self) -> str:
        ...         return "My custom command"
        ...
        ...     async def execute(self, args: list[str], context: dict[str, Any]) -> dict[str, Any]:
        ...         return {"success": True, "message": "Done!"}
    """

    def __init__(self) -> None:
        """Initialize the command.

        Services are provided through the context dict during execute(),
        following dependency injection pattern.
        """
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name as it appears in Teams (without '/' prefix).

        Returns:
            Command name string.

        Example:
            >>> return "help"  # Invoked as /help
        """
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Command description for help text.

        Returns:
            Brief description of what the command does.

        Example:
            >>> return "Show available commands and usage"
        """
        ...

    @property
    def usage(self) -> str:
        """Usage examples for the command.

        Returns:
            Usage string with examples.

        Example:
            >>> return "/help [command]"
        """
        return f"/{self.name}"

    @property
    def visible_to_users(self) -> bool:
        """Whether this command should be visible in help listings.

        Returns:
            True if command should appear in help, False for hidden commands.
        """
        return True

    @abstractmethod
    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the command with given arguments.

        Args:
            args: Command arguments (excluding the command name itself).
            context: Execution context containing:
                - turn_context: Bot Framework TurnContext
                - mcp_manager: MCPManager instance (optional)
                - bedrock_client: BedrockClient instance (optional)
                - state_manager: ConversationStateManager (optional)
                - command_tracker: AsyncCommandTracker (optional)
                - user_id: User identifier
                - user_name: User display name
                - conversation_id: Conversation identifier

        Returns:
            Command result dictionary with:
                - success: bool - Whether command succeeded
                - message: str - Text message response (optional)
                - card: dict - Adaptive card content (optional)
                - error: str - Error message if success=False (optional)

        Example:
            >>> async def execute(self, args, context):
            ...     return {
            ...         "success": True,
            ...         "message": "Command completed",
            ...         "card": {"type": "AdaptiveCard", ...}
            ...     }
        """
        ...

    # Helper methods

    def parse_instance_id(self, args: list[str]) -> str | None:
        """Extract a single instance ID from arguments.

        Args:
            args: Command arguments.

        Returns:
            Instance ID if found, None otherwise.

        Example:
            >>> cmd.parse_instance_id(["i-1234567890abcdef0", "other"])
            'i-1234567890abcdef0'
        """
        if not args:
            return None

        for arg in args:
            if arg.startswith("i-") and len(arg) == 19:  # Valid EC2 instance ID
                return arg

        # If no valid ID found, try first arg as potential ID
        return args[0] if args else None

    def parse_instance_ids(self, args: list[str]) -> list[str]:
        """Parse multiple instance IDs from command arguments.

        Supports both space-separated and comma-separated IDs.

        Args:
            args: Command arguments.

        Returns:
            List of valid instance IDs.

        Example:
            >>> cmd.parse_instance_ids(["i-111", "i-222,i-333"])
            ['i-111', 'i-222', 'i-333']
        """
        instance_ids: list[str] = []

        for arg in args:
            if arg.startswith("i-") and len(arg) == 19:
                instance_ids.append(arg)
            else:
                # Try to parse as comma-separated list
                potential_ids = arg.split(",")
                for potential_id in potential_ids:
                    stripped_id = potential_id.strip()
                    if stripped_id.startswith("i-") and len(stripped_id) == 19:
                        instance_ids.append(stripped_id)

        return instance_ids

    def create_error_card(self, title: str, error_message: str) -> dict[str, Any]:
        """Create a standard error adaptive card.

        Args:
            title: Error title.
            error_message: Detailed error message.

        Returns:
            Adaptive card dictionary.

        Example:
            >>> card = cmd.create_error_card("Operation Failed", "Instance not found")
        """
        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "Container",
                    "style": "attention",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"❌ {title}",
                            "size": "Large",
                            "weight": "Bolder",
                            "color": "Attention",
                        },
                        {
                            "type": "TextBlock",
                            "text": error_message,
                            "wrap": True,
                            "spacing": "Small",
                        },
                    ],
                }
            ],
        }

    def create_success_card(self, title: str, message: str) -> dict[str, Any]:
        """Create a standard success adaptive card.

        Args:
            title: Success title.
            message: Success message.

        Returns:
            Adaptive card dictionary.

        Example:
            >>> card = cmd.create_success_card("Complete", "Operation succeeded")
        """
        return {
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": [
                {
                    "type": "Container",
                    "style": "good",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"✅ {title}",
                            "size": "Large",
                            "weight": "Bolder",
                            "color": "Good",
                        },
                        {
                            "type": "TextBlock",
                            "text": message,
                            "wrap": True,
                            "spacing": "Small",
                        },
                    ],
                }
            ],
        }

    def apply_brand_colors(self, card: dict[str, Any]) -> dict[str, Any]:
        """Apply AWS brand colors to an adaptive card.

        Recursively updates colors in chart elements to use AWS brand colors.

        Args:
            card: Adaptive card dictionary to modify in-place.

        Returns:
            Modified card dictionary (same object as input).

        Example:
            >>> card = {...}
            >>> cmd.apply_brand_colors(card)
        """

        def update_colors(obj: Any) -> None:
            """Recursively update colors in card structure."""
            if isinstance(obj, dict):
                # Special handling for Chart elements - they support hex colors
                if (
                    obj.get("type") in ["Chart.Line", "Chart.Pie", "Chart.Donut", "Chart.Bar"]
                    and "data" in obj
                    and isinstance(obj["data"], list)
                ):
                    # Update chart data colors
                    colors = [
                        "#FF9900",  # AWS Orange
                        "#232F3E",  # AWS Dark Blue
                        "#146EB4",  # AWS Blue
                        "#FF6600",  # AWS Red-Orange
                        "#00A1C9",  # AWS Light Blue
                    ]
                    for i, data_item in enumerate(obj["data"]):
                        if isinstance(data_item, dict) and "color" not in data_item:
                            data_item["color"] = colors[i % len(colors)]

                # Recurse through all values
                for value in obj.values():
                    update_colors(value)

            elif isinstance(obj, list):
                for item in obj:
                    update_colors(item)

        update_colors(card)
        return card

    async def call_mcp_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Call an MCP tool with error handling.

        Args:
            tool_name: Name of the MCP tool to call.
            arguments: Tool arguments.
            context: Execution context containing mcp_manager.

        Returns:
            Tool result dictionary.

        Raises:
            Exception: If MCP manager not available or tool call fails.

        Example:
            >>> result = await cmd.call_mcp_tool(
            ...     "describe-instances",
            ...     {"InstanceIds": ["i-123"]},
            ...     context
            ... )
        """
        try:
            mcp_manager = context.get("mcp_manager")
            if not mcp_manager:
                raise ValueError("MCP manager not available in context")

            turn_context = context.get("turn_context")

            return cast(
                dict[str, Any],
                await mcp_manager.call_aws_api_tool(
                    tool_name, arguments, turn_context=turn_context
                ),
            )

        except Exception as e:
            self.logger.error(f"Error calling MCP tool {tool_name}: {e}")
            raise

    async def validate_instances_exist(
        self,
        instance_ids: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate that instances exist and return their details.

        Args:
            instance_ids: List of instance IDs to validate.
            context: Execution context with MCP manager.

        Returns:
            Dictionary with 'success' boolean and either:
                - 'instances': List of instance dicts if success=True
                - 'error': Error message if success=False

        Example:
            >>> result = await cmd.validate_instances_exist(["i-123"], context)
            >>> if result["success"]:
            ...     instances = result["instances"]
        """
        try:
            if not instance_ids:
                return {"success": False, "error": "No instance IDs provided"}

            result = await self.call_mcp_tool(
                "describe-instances", {"InstanceIds": instance_ids}, context
            )

            instances = result.get("instances", [])

            if not instances:
                return {
                    "success": False,
                    "error": "No instances found with the provided IDs",
                }

            # Check if all requested instances were found
            found_ids = [inst.get("InstanceId") for inst in instances]
            missing_ids = [iid for iid in instance_ids if iid not in found_ids]

            if missing_ids:
                return {
                    "success": False,
                    "error": f"Instances not found: {', '.join(missing_ids)}",
                }

            return {"success": True, "instances": instances}

        except Exception as e:
            self.logger.error(f"Error validating instances: {e}")
            return {"success": False, "error": f"Error validating instances: {e!s}"}

    def filter_instances_by_state(
        self,
        instances: list[dict[str, Any]],
        required_states: list[str],
    ) -> dict[str, Any]:
        """Filter instances by their current state.

        Args:
            instances: List of instance dictionaries.
            required_states: List of acceptable states (e.g., ['running']).

        Returns:
            Dictionary with:
                - valid_instances: List of instances in required states
                - invalid_instances: List of dicts with id, state, name
                - error_message: Error message if any invalid instances

        Example:
            >>> result = cmd.filter_instances_by_state(instances, ['running'])
            >>> if result["error_message"]:
            ...     print(result["error_message"])
        """
        valid_instances: list[dict[str, Any]] = []
        invalid_instances: list[dict[str, str]] = []

        for instance in instances:
            current_state = instance.get("State", "unknown")
            if current_state in required_states:
                valid_instances.append(instance)
            else:
                invalid_instances.append(
                    {
                        "id": instance.get("InstanceId", ""),
                        "state": current_state,
                        "name": instance.get("Name", ""),
                    }
                )

        error_message = None
        if invalid_instances:
            invalid_list = [f"{inv['id']} ({inv['state']})" for inv in invalid_instances]
            error_message = (
                f"Some instances are not in required state {required_states}: "
                f"{', '.join(invalid_list)}"
            )

        return {
            "valid_instances": valid_instances,
            "invalid_instances": invalid_instances,
            "error_message": error_message,
        }
