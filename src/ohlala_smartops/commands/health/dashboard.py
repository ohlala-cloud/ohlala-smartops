"""Enhanced health check command with comprehensive metrics and visualizations.

This module provides the main health dashboard command for displaying EC2 instance
health metrics. Supports both single-instance detailed dashboards and multi-instance
overview with batched processing for performance and rate limit management.
"""

import asyncio
from typing import Any, Final

import structlog

from ohlala_smartops.commands.base import BaseCommand
from ohlala_smartops.commands.health.card_builder import CardBuilder
from ohlala_smartops.commands.health.chart_builder import ChartBuilder
from ohlala_smartops.commands.health.metrics_collector import MetricsCollector
from ohlala_smartops.commands.health.system_inspector import SystemInspector

# Configure structured logging
logger: structlog.BoundLogger = structlog.get_logger(__name__)

# Batch processing configuration
BATCH_SIZE: Final[int] = 3  # Process 3 instances at a time
BATCH_DELAY_SECONDS: Final[float] = 2.0  # Delay between batches


class HealthDashboardCommand(BaseCommand):
    """Show comprehensive health dashboard with graphs and detailed metrics.

    This command provides:
    - Single instance: Detailed dashboard with CPU trends, memory, disk, logs
    - All instances: Overview with health status and drill-down capability

    The command uses batched processing for multi-instance requests to respect
    AWS API rate limits and provide better performance.

    Example:
        >>> # Show overview of all instances
        >>> /health
        >>>
        >>> # Show detailed dashboard for specific instance
        >>> /health i-1234567890abcdef0
    """

    def __init__(self) -> None:
        """Initialize command with component builders.

        Components (metrics_collector, system_inspector) are initialized
        on first use with services from context.
        """
        super().__init__()
        self.chart_builder = ChartBuilder()
        self.card_builder = CardBuilder(self.chart_builder)
        self.metrics_collector: MetricsCollector | None = None
        self.system_inspector: SystemInspector | None = None
        self.logger = logger.bind(component="health_dashboard_command")

    @property
    def name(self) -> str:
        """Command name: health."""
        return "health"

    @property
    def description(self) -> str:
        """Command description."""
        return "Show comprehensive health dashboard with CPU, memory, disk, and system logs"

    @property
    def usage(self) -> str:
        """Command usage examples."""
        return "/health [instance-id] - Show detailed health metrics with graphs"

    async def execute(self, args: list[str], context: dict[str, Any]) -> dict[str, Any]:
        """Execute health dashboard command.

        Args:
            args: Command arguments. If empty, shows overview of all instances.
                If contains instance ID, shows detailed dashboard for that instance.
            context: Execution context containing services and user info.

        Returns:
            Command result dictionary with:
                - success: bool
                - card: Adaptive card dict (if successful)
                - error: str (if failed)

        Example:
            >>> await cmd.execute([], context)  # Overview
            >>> await cmd.execute(["i-123"], context)  # Single instance
        """
        try:
            self.logger.info("health_command_execute", args=args)

            # Initialize components on first use
            if not self.metrics_collector:
                region = context.get("region", "us-east-1")
                self.metrics_collector = MetricsCollector(region=region)
                self.logger.info("metrics_collector_initialized", region=region)

            if not self.system_inspector:
                region = context.get("region", "us-east-1")
                self.system_inspector = SystemInspector(region=region)
                self.logger.info("system_inspector_initialized", region=region)

            # Parse instance ID from arguments
            instance_id = self.parse_instance_id(args)

            if instance_id:
                self.logger.info("single_instance_dashboard", instance_id=instance_id)
                return await self._single_instance_health_dashboard(instance_id, context)
            self.logger.info("all_instances_overview")
            return await self._all_instances_health_overview(context)

        except Exception as e:
            self.logger.error("health_command_error", error=str(e), exc_info=True)
            return {
                "success": False,
                "card": self.create_error_card("Health Check Failed", f"Error: {e!s}"),
            }

    async def _single_instance_health_dashboard(
        self,
        instance_id: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Create comprehensive health dashboard for a single instance.

        Collects metrics in parallel from multiple sources:
        - CloudWatch metrics (6 hours of CPU, network, EBS)
        - Real-time SSM metrics (current CPU, memory, processes)
        - Disk usage via SSM
        - Recent error logs
        - System information

        Args:
            instance_id: EC2 instance ID.
            context: Execution context.

        Returns:
            Command result with adaptive card dashboard.
        """
        try:
            self.logger.info("building_single_dashboard", instance_id=instance_id)

            # Send progress message for single instance dashboard
            await self._send_progress_message(
                context,
                f"🔄 Loading detailed health dashboard for {instance_id}. This may take 30-45 seconds...",
            )

            # Get instance details (need to call MCP manager from context)
            mcp_manager = context.get("mcp_manager")
            if not mcp_manager:
                return {
                    "success": False,
                    "error": "MCP manager not available in context",
                }

            instances_result = await mcp_manager.call_tool("list-instances", {})
            instances = instances_result.get("instances", [])

            # Find the specific instance
            instance_data = None
            for inst in instances:
                inst_id = inst.get("instance_id") or inst.get("InstanceId")
                if inst_id == instance_id:
                    instance_data = inst
                    break

            if not instance_data:
                return {
                    "success": False,
                    "error": f"Instance {instance_id} not found",
                }

            # Format instance details
            instance_details = {
                "instance_id": instance_id,
                "name": instance_data.get("name") or instance_data.get("Name", instance_id),
                "type": instance_data.get("instance_type")
                or instance_data.get("InstanceType", "Unknown"),
                "state": instance_data.get("state") or instance_data.get("State", "unknown"),
            }

            # Detect platform before starting parallel tasks
            platform = await self._detect_platform(instance_id, instance_data, context)
            self.logger.info("platform_detected", instance_id=instance_id, platform=platform)

            # Ensure platform detection completes
            await asyncio.sleep(0.1)

            # Gather all metrics in parallel
            self.logger.info("starting_parallel_metric_collection", instance_id=instance_id)

            tasks = [
                self.metrics_collector.get_cloudwatch_metrics(instance_id, hours=6),
                self.metrics_collector.get_realtime_system_metrics(instance_id, platform),
                self.system_inspector.get_disk_usage(instance_id, platform),
                self.system_inspector.get_recent_error_logs(instance_id, platform),
                self.system_inspector.get_system_info(instance_id, platform),
            ]

            task_names = [
                "cloudwatch_metrics",
                "system_metrics",
                "disk_usage",
                "system_logs",
                "system_info",
            ]

            # Execute all tasks in parallel
            task_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            results: dict[str, Any] = {}
            for name, result in zip(task_names, task_results, strict=False):
                if isinstance(result, Exception):
                    self.logger.warning("metric_collection_failed", metric=name, error=str(result))
                    results[name] = None
                else:
                    self.logger.info("metric_collected", metric=name)
                    results[name] = result

            # Build comprehensive dashboard card
            card = self.card_builder.build_health_dashboard_card(instance_details, results, context)

            return {
                "success": True,
                "card": card,
            }

        except Exception as e:
            self.logger.error(
                "single_dashboard_error", instance_id=instance_id, error=str(e), exc_info=True
            )
            return {
                "success": False,
                "error": f"Failed to create health dashboard: {e!s}",
            }

    async def _all_instances_health_overview(self, context: dict[str, Any]) -> dict[str, Any]:
        """Get health overview for all instances.

        Processes instances in batches to avoid overwhelming AWS APIs.
        Shows status summary and allows drill-down to individual dashboards.

        Args:
            context: Execution context.

        Returns:
            Command result with overview adaptive card.
        """
        try:
            self.logger.info("building_overview")

            # Get MCP manager from context
            mcp_manager = context.get("mcp_manager")
            if not mcp_manager:
                return {
                    "success": False,
                    "error": "MCP manager not available in context",
                }

            # Get all instances
            instances_result = await mcp_manager.call_tool("list-instances", {})
            instances = instances_result.get("instances", [])

            if not instances:
                return {
                    "success": True,
                    "message": "No EC2 instances found.",
                }

            instance_count = len(instances)
            self.logger.info("instances_found", count=instance_count)

            # Send progress message for large instance counts
            if instance_count > 5:
                if instance_count > 10:
                    msg = f"🔄 Checking health for {instance_count} instances... This may take a moment."
                else:
                    msg = f"🔄 Checking health for {instance_count} instances..."
                await self._send_progress_message(context, msg)

            # Get running instances
            running_instances: list[str] = []
            for instance in instances:
                state = instance.get("state") or instance.get("State", "unknown")
                instance_id = instance.get("instance_id") or instance.get("InstanceId")
                if state.lower() == "running" and instance_id:
                    running_instances.append(instance_id)

            self.logger.info("processing_running_instances", count=len(running_instances))

            # Process instances in batches
            summaries: list[dict[str, Any]] = []

            for i in range(0, len(running_instances), BATCH_SIZE):
                batch = running_instances[i : i + BATCH_SIZE]
                batch_num = i // BATCH_SIZE + 1
                total_batches = (len(running_instances) - 1) // BATCH_SIZE + 1

                self.logger.info(
                    "processing_batch", batch=batch_num, total=total_batches, instances=batch
                )

                # Process current batch in parallel
                batch_tasks = [
                    self.metrics_collector.get_instance_health_summary(inst_id) for inst_id in batch
                ]

                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                # Add results, handling exceptions
                for result in batch_results:
                    if isinstance(result, Exception):
                        self.logger.warning("health_summary_failed", error=str(result))
                        summaries.append({"status": "error", "error": str(result)})
                    else:
                        summaries.append(result)

                # Delay between batches (except after last batch)
                if i + BATCH_SIZE < len(running_instances):
                    self.logger.info("batch_delay", seconds=BATCH_DELAY_SECONDS)
                    await asyncio.sleep(BATCH_DELAY_SECONDS)

            # Build overview card
            card = self.card_builder.build_overview_card(instances, summaries, context)

            return {
                "success": True,
                "card": card,
            }

        except Exception as e:
            self.logger.error("overview_error", error=str(e), exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get health overview: {e!s}",
            }

    async def _detect_platform(
        self,
        instance_id: str,
        instance_data: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        """Detect instance platform (Windows or Linux).

        Uses SSM DescribeInstanceInformation for reliable platform detection.

        Args:
            instance_id: EC2 instance ID.
            instance_data: Instance data from list-instances.
            context: Execution context with MCP manager.

        Returns:
            Platform string: "windows" or "linux".
        """
        try:
            mcp_manager = context.get("mcp_manager")
            if not mcp_manager:
                self.logger.warning("no_mcp_manager", instance_id=instance_id)
                return "linux"

            # Use SSM for definitive platform detection
            ssm_info = await mcp_manager.call_tool(
                "describe-instance-information",
                {"InstanceIds": [instance_id]},
            )

            if ssm_info and ssm_info.get("InstanceInformationList"):
                instance_info = ssm_info["InstanceInformationList"][0]
                platform_type = instance_info.get("PlatformType", "").lower()
                platform_name = instance_info.get("PlatformName", "")

                if platform_type == "windows" or "windows" in platform_name.lower():
                    self.logger.info(
                        "platform_detected", instance_id=instance_id, platform="windows"
                    )
                    return "windows"
                if platform_type == "linux":
                    self.logger.info("platform_detected", instance_id=instance_id, platform="linux")
                    return "linux"

            self.logger.warning("platform_unknown", instance_id=instance_id, defaulting="linux")
            return "linux"

        except Exception as e:
            self.logger.warning("platform_detection_error", instance_id=instance_id, error=str(e))
            return "linux"

    async def _send_progress_message(self, context: dict[str, Any], message: str) -> None:
        """Send a progress message to the user.

        Args:
            context: Execution context with turn_context and bot_instance.
            message: Progress message to send.
        """
        try:
            turn_context = context.get("turn_context")
            bot_instance = context.get("bot_instance")

            if turn_context and bot_instance:
                await bot_instance._send_response(turn_context, message)
                self.logger.info("progress_message_sent", message=message)
        except Exception as e:
            self.logger.warning("progress_message_failed", error=str(e))
