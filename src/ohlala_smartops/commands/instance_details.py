"""Instance details command - Show comprehensive instance information.

This module provides the InstanceDetailsCommand that displays detailed information
about a specific EC2 instance including metrics, SSM sessions, and recent commands.

Phase 5C: Monitoring & Information commands.
"""

import logging
from typing import Any, Final

from ohlala_smartops.commands.adaptive_cards import CardTemplates
from ohlala_smartops.commands.base import BaseCommand

logger: Final = logging.getLogger(__name__)


class InstanceDetailsCommand(BaseCommand):
    """Handler for /details command - Show comprehensive instance information.

    Displays detailed information including:
    - Instance overview (ID, type, state, IPs, AZ, launch time, tags)
    - Recent CloudWatch metrics (last hour: CPU, network, disk)
    - Active SSM sessions
    - Recent SSM commands (last 5)
    - Quick action buttons based on current state

    Example:
        >>> cmd = InstanceDetailsCommand()
        >>> result = await cmd.execute(["i-1234567890abcdef0"], context)
        >>> print(result["card"])  # Comprehensive instance details card
    """

    @property
    def name(self) -> str:
        """Command name as it appears in Teams."""
        return "details"

    @property
    def description(self) -> str:
        """Command description for help text."""
        return "Show detailed information about a specific EC2 instance"

    @property
    def usage(self) -> str:
        """Usage examples for the command."""
        return "/details <instance-id> - Show detailed instance information"

    async def execute(
        self,
        args: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute instance details command.

        Args:
            args: Command arguments (instance ID required).
            context: Execution context containing:
                - mcp_manager: MCPManager instance

        Returns:
            Command result with adaptive card showing instance details.

        Example:
            >>> result = await cmd.execute(["i-1234567890abcdef0"], context)
            >>> if result["success"]:
            ...     print("Instance details retrieved")
        """
        try:
            # Parse instance ID
            instance_id = self.parse_instance_id(args)

            if not instance_id:
                return {
                    "success": False,
                    "message": "❌ Please provide an instance ID.\n\n" f"Usage: {self.usage}",
                }

            # Validate instance exists
            validation_result = await self.validate_instances_exist([instance_id], context)

            if not validation_result["success"]:
                return {
                    "success": False,
                    "message": f"❌ {validation_result['error']}",
                }

            instance = validation_result["instances"][0]

            # Gather additional data in parallel
            try:
                # Get recent metrics (last hour)
                metrics_data = await self._get_instance_metrics(instance_id, context)
            except Exception as e:
                self.logger.warning(f"Failed to get metrics for {instance_id}: {e}")
                metrics_data = None

            try:
                # Get recent SSM commands
                commands_data = await self._get_recent_commands(instance_id, context)
            except Exception as e:
                self.logger.warning(f"Failed to get SSM commands for {instance_id}: {e}")
                commands_data = []

            try:
                # Get active SSM sessions
                sessions_data = await self._get_active_sessions(instance_id, context)
            except Exception as e:
                self.logger.warning(f"Failed to get SSM sessions for {instance_id}: {e}")
                sessions_data = []

            # Build comprehensive card
            card = self._build_details_card(instance, metrics_data, commands_data, sessions_data)

            return {
                "success": True,
                "message": f"Instance details for {instance_id}",
                "card": card,
            }

        except Exception as e:
            self.logger.error(f"Error getting instance details: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get instance details: {e!s}",
                "card": self.create_error_card(
                    "Failed to Get Instance Details",
                    f"Unable to retrieve instance information: {e!s}",
                ),
            }

    async def _get_instance_metrics(
        self, instance_id: str, context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Get recent CloudWatch metrics for instance.

        Args:
            instance_id: EC2 instance ID.
            context: Execution context.

        Returns:
            Dictionary with metric data or None if unavailable.
        """
        try:
            # Call MCP get-instance-metrics tool for last hour
            result = await self.call_mcp_tool(
                "get-instance-metrics",
                {
                    "InstanceId": instance_id,
                    "Period": 3600,  # 1 hour
                    "Statistics": ["Average", "Maximum"],
                },
                context,
            )

            metrics = result.get("metrics", {})
            return metrics if isinstance(metrics, dict) else {}

        except Exception as e:
            self.logger.debug(f"Metrics not available for {instance_id}: {e}")
            return None

    async def _get_recent_commands(
        self, instance_id: str, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get recent SSM commands for instance.

        Args:
            instance_id: EC2 instance ID.
            context: Execution context.

        Returns:
            List of recent command dictionaries.
        """
        try:
            result = await self.call_mcp_tool(
                "list-commands",
                {"InstanceId": instance_id, "MaxResults": 5},
                context,
            )

            commands = result.get("commands", [])
            return commands if isinstance(commands, list) else []

        except Exception as e:
            self.logger.debug(f"Commands not available for {instance_id}: {e}")
            return []

    async def _get_active_sessions(
        self, instance_id: str, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get active SSM sessions for instance.

        Args:
            instance_id: EC2 instance ID.
            context: Execution context.

        Returns:
            List of active session dictionaries.
        """
        try:
            result = await self.call_mcp_tool(
                "list-sessions",
                {"Target": instance_id, "State": "Active"},
                context,
            )

            sessions = result.get("sessions", [])
            return sessions if isinstance(sessions, list) else []

        except Exception as e:
            self.logger.debug(f"Sessions not available for {instance_id}: {e}")
            return []

    def _build_details_card(
        self,
        instance: dict[str, Any],
        metrics: dict[str, Any] | None,
        commands: list[dict[str, Any]],
        sessions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build comprehensive details card.

        Args:
            instance: Instance dictionary from EC2.
            metrics: CloudWatch metrics data (optional).
            commands: Recent SSM commands.
            sessions: Active SSM sessions.

        Returns:
            Adaptive card dictionary.
        """
        instance_id = instance.get("InstanceId", "Unknown")
        name = instance.get("Name", instance_id)
        state = instance.get("State", "unknown")
        instance_type = instance.get("InstanceType", "Unknown")
        platform = instance.get("Platform", "Linux")
        private_ip = instance.get("PrivateIpAddress")
        public_ip = instance.get("PublicIpAddress")
        az = instance.get("AvailabilityZone", "Unknown")
        launch_time = instance.get("LaunchTime", "Unknown")

        card_body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"🔍 Instance Details: {name}",
                "size": "Large",
                "weight": "Bolder",
                "color": "Accent",
            }
        ]

        # Instance overview section
        card_body.append(
            CardTemplates.create_instance_card(
                instance_id, name, instance_type, state, platform, private_ip
            )
        )

        # Instance information fact set
        facts: dict[str, str | int | float] = {
            "Instance ID": instance_id,
            "Instance Type": instance_type,
            "State": state.upper(),
            "Platform": platform,
            "Availability Zone": az,
            "Launch Time": str(launch_time),
        }

        if private_ip:
            facts["Private IP"] = private_ip
        if public_ip:
            facts["Public IP"] = public_ip

        card_body.append(
            {
                "type": "Container",
                "spacing": "Medium",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "📋 Instance Information",
                        "weight": "Bolder",
                        "size": "Medium",
                    },
                    CardTemplates.create_fact_set(facts),
                ],
            }
        )

        # Tags section (if available)
        tags = instance.get("Tags", {})
        if tags and isinstance(tags, dict):
            card_body.append(
                {
                    "type": "Container",
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "🏷️ Tags",
                            "weight": "Bolder",
                            "size": "Medium",
                        },
                        CardTemplates.create_fact_set(tags),
                    ],
                }
            )

        # Metrics section
        if metrics:
            card_body.append(self._build_metrics_section(metrics))

        # SSM Sessions section
        if sessions:
            card_body.append(self._build_sessions_section(sessions))

        # Recent commands section
        if commands:
            card_body.append(self._build_commands_section(commands))

        # Quick actions based on state
        actions = self._build_actions(instance_id, state)
        if actions:
            card_body.append(
                {
                    "type": "ActionSet",
                    "separator": True,
                    "spacing": "Large",
                    "actions": actions,
                }
            )

        return {"type": "AdaptiveCard", "version": "1.5", "body": card_body}

    def _build_metrics_section(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Build metrics section of the card.

        Args:
            metrics: CloudWatch metrics data.

        Returns:
            Container with metrics visualization.
        """
        # Extract metric values (average over last hour)
        cpu_avg = metrics.get("CPUUtilization", {}).get("Average", 0.0)
        network_in = metrics.get("NetworkIn", {}).get("Average", 0.0)
        network_out = metrics.get("NetworkOut", {}).get("Average", 0.0)

        metric_columns: list[dict[str, Any]] = []

        # CPU gauge
        if cpu_avg > 0:
            metric_columns.append(CardTemplates.create_metric_gauge("CPU", cpu_avg))

        # Network in (convert bytes to Mbps estimate)
        if network_in > 0:
            network_in_mbps = (network_in * 8) / (1024 * 1024)  # bytes to Mbps
            metric_columns.append(
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "Network In",
                            "weight": "Bolder",
                            "horizontalAlignment": "Center",
                            "size": "Small",
                        },
                        {
                            "type": "TextBlock",
                            "text": f"{network_in_mbps:.2f} Mbps",
                            "horizontalAlignment": "Center",
                            "color": "Good",
                            "size": "Medium",
                            "weight": "Bolder",
                        },
                    ],
                }
            )

        # Network out
        if network_out > 0:
            network_out_mbps = (network_out * 8) / (1024 * 1024)
            metric_columns.append(
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": "Network Out",
                            "weight": "Bolder",
                            "horizontalAlignment": "Center",
                            "size": "Small",
                        },
                        {
                            "type": "TextBlock",
                            "text": f"{network_out_mbps:.2f} Mbps",
                            "horizontalAlignment": "Center",
                            "color": "Good",
                            "size": "Medium",
                            "weight": "Bolder",
                        },
                    ],
                }
            )

        if not metric_columns:
            return {
                "type": "Container",
                "spacing": "Medium",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "📊 Recent Metrics (Last Hour)",
                        "weight": "Bolder",
                        "size": "Medium",
                    },
                    {
                        "type": "TextBlock",
                        "text": "No metric data available",
                        "isSubtle": True,
                    },
                ],
            }

        return {
            "type": "Container",
            "spacing": "Medium",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "📊 Recent Metrics (Last Hour)",
                    "weight": "Bolder",
                    "size": "Medium",
                },
                {"type": "ColumnSet", "columns": metric_columns},
            ],
        }

    def _build_sessions_section(self, sessions: list[dict[str, Any]]) -> dict[str, Any]:
        """Build SSM sessions section.

        Args:
            sessions: List of active session dictionaries.

        Returns:
            Container with sessions information.
        """
        session_items: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"💻 Active SSM Sessions ({len(sessions)})",
                "weight": "Bolder",
                "size": "Medium",
            }
        ]

        for session in sessions[:5]:  # Show max 5 sessions
            session_id = session.get("SessionId", "Unknown")
            status = session.get("Status", "Unknown")
            start_time = session.get("StartDate", "Unknown")

            session_items.append(
                {
                    "type": "TextBlock",
                    "text": f"• {session_id} - {status}",
                    "spacing": "Small",
                    "size": "Small",
                }
            )
            session_items.append(
                {
                    "type": "TextBlock",
                    "text": f"  Started: {start_time}",
                    "spacing": "None",
                    "size": "Small",
                    "isSubtle": True,
                }
            )

        return {"type": "Container", "spacing": "Medium", "items": session_items}

    def _build_commands_section(self, commands: list[dict[str, Any]]) -> dict[str, Any]:
        """Build recent commands section.

        Args:
            commands: List of recent command dictionaries.

        Returns:
            Container with commands information.
        """
        command_items: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": f"⚙️ Recent SSM Commands ({len(commands)})",
                "weight": "Bolder",
                "size": "Medium",
            }
        ]

        for command in commands[:5]:  # Show max 5 commands
            command_id = command.get("CommandId", "Unknown")
            status = command.get("Status", "Unknown")
            document_name = command.get("DocumentName", "Unknown")

            # Determine status color
            if status == "Success":
                status_icon = "✅"
            elif status == "Failed":
                status_icon = "❌"
            elif status in ["Pending", "InProgress"]:
                status_icon = "⏳"
            else:
                status_icon = "⚪"

            command_items.append(
                {
                    "type": "TextBlock",
                    "text": f"{status_icon} {document_name}",
                    "spacing": "Small",
                    "weight": "Bolder",
                    "size": "Small",
                }
            )
            command_items.append(
                {
                    "type": "TextBlock",
                    "text": f"  ID: {command_id} • Status: {status}",
                    "spacing": "None",
                    "size": "Small",
                    "isSubtle": True,
                }
            )

        return {"type": "Container", "spacing": "Medium", "items": command_items}

    def _build_actions(self, instance_id: str, state: str) -> list[dict[str, Any]]:
        """Build quick action buttons based on instance state.

        Args:
            instance_id: EC2 instance ID.
            state: Instance state.

        Returns:
            List of action button dictionaries.
        """
        actions: list[dict[str, Any]] = []

        if state == "stopped":
            actions.append(
                CardTemplates.create_action_button(
                    "Start",
                    "start_instance",
                    instance_id,
                    style="positive",
                    icon="▶️",
                )
            )
        elif state == "running":
            actions.append(
                CardTemplates.create_action_button(
                    "Stop",
                    "stop_instance",
                    instance_id,
                    style="destructive",
                    icon="⏹️",
                )
            )
            actions.append(
                CardTemplates.create_action_button(
                    "Reboot",
                    "reboot_instance",
                    instance_id,
                    style="default",
                    icon="🔄",
                )
            )

        # Always add refresh button
        actions.append(
            {
                "type": "Action.Submit",
                "title": "🔄 Refresh",
                "data": {"action": "details", "instanceId": instance_id},
            }
        )

        return actions
