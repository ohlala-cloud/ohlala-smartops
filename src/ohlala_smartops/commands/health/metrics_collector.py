"""CloudWatch and real-time metrics collection for EC2 instance health checks.

This module provides functionality to collect comprehensive health metrics from EC2 instances
using both AWS CloudWatch (historical metrics) and AWS Systems Manager (real-time OS metrics).
Supports both Windows and Linux platforms with platform-specific commands.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from pydantic import BaseModel, Field

from ohlala_smartops.aws.cloudwatch import CloudWatchManager
from ohlala_smartops.aws.ssm_commands import SSMCommandManager

# Configure structured logging with fallback for Python 3.13 compatibility
try:
    import structlog

    logger: structlog.BoundLogger = structlog.get_logger(__name__)
except (ImportError, Exception):
    # Fallback to standard logging if structlog has compatibility issues
    # Create a wrapper that provides structlog-like API
    class _LoggerAdapter:
        """Adapter to make standard logger compatible with structlog API."""

        def __init__(self, logger: logging.Logger) -> None:
            self._logger = logger

        def bind(self, **kwargs: Any) -> "_LoggerAdapter":
            """Return self for compatibility with structlog.bind()."""
            return self

        def info(self, msg: str, **kwargs: Any) -> None:
            """Log info message."""
            self._logger.info(msg)

        def warning(self, msg: str, **kwargs: Any) -> None:
            """Log warning message."""
            self._logger.warning(msg)

        def error(self, msg: str, **kwargs: Any) -> None:
            """Log error message."""
            self._logger.error(msg, exc_info=kwargs.get("exc_info", False))

        def debug(self, msg: str, **kwargs: Any) -> None:
            """Log debug message."""
            self._logger.debug(msg)

    logger = _LoggerAdapter(logging.getLogger(__name__))  # type: ignore[assignment]

# Delay between CloudWatch API calls to avoid throttling
CLOUDWATCH_DELAY_SECONDS: Final[float] = 0.5

# SSM command timeout and retries
SSM_COMMAND_TIMEOUT: Final[int] = 15  # seconds
SSM_MAX_RETRIES: Final[int] = 3


class HealthMetrics(BaseModel):
    """Model for aggregated health metrics from all sources.

    Attributes:
        cpu_graph: CPU utilization data points and statistics.
        network_in: Network input traffic data points.
        network_out: Network output traffic data points.
        memory_graph: Memory usage data points (if available).
        ebs_metrics: EBS volume I/O metrics (if available).
        success: Whether metrics collection was successful.
        error: Error message if collection failed (optional).
    """

    cpu_graph: dict[str, Any] = Field(default_factory=lambda: {"datapoints": []})
    network_in: dict[str, Any] = Field(default_factory=lambda: {"datapoints": []})
    network_out: dict[str, Any] = Field(default_factory=lambda: {"datapoints": []})
    memory_graph: dict[str, Any] = Field(default_factory=lambda: {"datapoints": []})
    ebs_metrics: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None


class RealtimeMetrics(BaseModel):
    """Model for real-time system metrics from SSM.

    Attributes:
        cpu_percent: Current CPU utilization percentage.
        memory_percent: Current memory utilization percentage.
        memory_used_mb: Memory used in MB.
        memory_total_mb: Total memory in MB.
        processes: Number of running processes.
        uptime_text: Human-readable uptime string.
        load_average: Load average (Linux only, optional).
        success: Whether metrics collection was successful.
        ssm_unavailable: Whether SSM commands are unavailable.
        error: Error message if collection failed (optional).
    """

    cpu_percent: float | str = 0
    memory_percent: float | str = 0
    memory_used_mb: float = 0
    memory_total_mb: float = 0
    processes: int | str = 0
    uptime_text: str = "Unknown"
    load_average: str | None = None
    success: bool = False
    ssm_unavailable: bool = False
    error: str | None = None


class MetricsCollector:
    """Handles CloudWatch and real-time metrics collection for EC2 instances.

    This class provides methods to collect both historical CloudWatch metrics
    and real-time operating system metrics via SSM commands. It handles platform
    detection, rate limiting, and graceful degradation when services are unavailable.

    Example:
        >>> collector = MetricsCollector()
        >>> # Get CloudWatch metrics
        >>> cw_metrics = await collector.get_cloudwatch_metrics("i-1234567890", hours=6)
        >>> # Get real-time OS metrics
        >>> rt_metrics = await collector.get_realtime_system_metrics("i-1234567890", "linux")
    """

    def __init__(
        self,
        cloudwatch_manager: CloudWatchManager | None = None,
        ssm_manager: SSMCommandManager | None = None,
        region: str = "us-east-1",
    ) -> None:
        """Initialize the metrics collector.

        Args:
            cloudwatch_manager: CloudWatch manager instance. Creates new if None.
            ssm_manager: SSM command manager instance. Creates new if None.
            region: AWS region for API calls. Defaults to "us-east-1".
        """
        self.cloudwatch = cloudwatch_manager or CloudWatchManager(region=region)
        self.ssm = ssm_manager or SSMCommandManager(region=region)
        self.region = region
        self.logger = logger.bind(component="metrics_collector", region=region)

    async def get_cloudwatch_metrics(self, instance_id: str, hours: int = 6) -> HealthMetrics:
        """Get CloudWatch metrics with data points for graphing.

        Collects CPU, network, and EBS metrics from CloudWatch for the specified
        time period. Uses sequential API calls with delays to avoid throttling.

        Args:
            instance_id: EC2 instance ID.
            hours: Number of hours of historical data to fetch. Defaults to 6.

        Returns:
            HealthMetrics object with collected data points and statistics.

        Example:
            >>> metrics = await collector.get_cloudwatch_metrics("i-1234567890", hours=6)
            >>> print(f"Avg CPU: {metrics.cpu_graph['avg']}%")
        """
        self.logger.info("fetching_cloudwatch_metrics", instance_id=instance_id, hours=hours)

        try:
            # Calculate time range
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(hours=hours)

            # Define metrics to collect
            metric_configs = [
                ("CPUUtilization", "cpu_graph", "Average"),
                ("NetworkIn", "network_in", "Sum"),
                ("NetworkOut", "network_out", "Sum"),
            ]

            # Sequential collection to respect rate limits
            results: list[dict[str, Any] | Exception] = []
            for i, (metric_name, _key, statistic) in enumerate(metric_configs):
                self.logger.debug(
                    "fetching_metric",
                    metric_name=metric_name,
                    index=i + 1,
                    total=len(metric_configs),
                )
                try:
                    datapoints = await self.cloudwatch.get_metric_statistics(
                        namespace="AWS/EC2",
                        metric_name=metric_name,
                        dimensions={"InstanceId": instance_id},
                        start_time=start_time,
                        end_time=end_time,
                        period=300,  # 5-minute intervals
                        statistics=[statistic],
                    )
                    results.append(
                        {
                            "metric_name": metric_name,
                            "datapoints": datapoints,
                            "statistic": statistic,
                        }
                    )
                except Exception as e:
                    self.logger.warning(
                        "metric_fetch_failed", metric_name=metric_name, error=str(e)
                    )
                    results.append(e)

                # Delay between requests to avoid throttling
                if i < len(metric_configs) - 1:
                    await asyncio.sleep(CLOUDWATCH_DELAY_SECONDS)

            # Process results into HealthMetrics structure
            metrics_data = HealthMetrics()

            for i, (metric_name, key, statistic) in enumerate(metric_configs):
                result = results[i]
                if isinstance(result, Exception):
                    self.logger.warning("skipping_failed_metric", metric_name=metric_name)
                    continue

                datapoints_list = result.get("datapoints", [])
                if not datapoints_list:
                    self.logger.warning("no_datapoints", metric_name=metric_name)
                    continue

                # Process datapoints for charting
                processed_datapoints: list[dict[str, Any]] = []
                total_value = 0.0
                max_value = 0.0
                current_value = 0.0

                for dp in datapoints_list:
                    # Get value based on statistic type
                    value = float(dp.value) if hasattr(dp, "value") else 0.0

                    # Convert network bytes to MB for better readability
                    if key in ["network_in", "network_out"] and value > 0:
                        value = value / (1024 * 1024)

                    timestamp = dp.timestamp.isoformat() if hasattr(dp, "timestamp") else ""

                    processed_datapoints.append(
                        {
                            "time": timestamp,
                            "value": round(value, 2),
                        }
                    )

                    total_value += value
                    max_value = max(max_value, value)
                    current_value = value

                # Sort by timestamp
                processed_datapoints.sort(key=lambda x: x["time"])

                # Store processed data
                avg = (
                    round(total_value / len(processed_datapoints), 2) if processed_datapoints else 0
                )

                if key == "cpu_graph":
                    metrics_data.cpu_graph = {
                        "datapoints": processed_datapoints,
                        "avg": avg,
                        "max": round(max_value, 2),
                        "current": round(current_value, 2),
                        "success": True,
                    }
                elif key == "network_in":
                    metrics_data.network_in = {
                        "datapoints": processed_datapoints,
                        "total_mb": round(total_value, 2),
                        "avg": avg,
                        "max": round(max_value, 2),
                        "current": round(current_value, 2),
                        "success": True,
                    }
                elif key == "network_out":
                    metrics_data.network_out = {
                        "datapoints": processed_datapoints,
                        "total_mb": round(total_value, 2),
                        "avg": avg,
                        "max": round(max_value, 2),
                        "current": round(current_value, 2),
                        "success": True,
                    }

            # Try to get EBS metrics
            await self._fetch_ebs_metrics(instance_id, hours, metrics_data, start_time, end_time)

            self.logger.info("cloudwatch_metrics_collected", instance_id=instance_id, success=True)
            return metrics_data

        except Exception as e:
            self.logger.error("cloudwatch_metrics_error", instance_id=instance_id, error=str(e))
            return HealthMetrics(success=False, error=str(e))

    async def _fetch_ebs_metrics(
        self,
        instance_id: str,
        hours: int,
        metrics_data: HealthMetrics,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Fetch EBS volume I/O metrics and add to metrics_data.

        Args:
            instance_id: EC2 instance ID.
            hours: Hours of historical data.
            metrics_data: HealthMetrics object to update.
            start_time: Start time for metrics.
            end_time: End time for metrics.
        """
        try:
            ebs_metric_configs = [
                ("VolumeReadOps", "read_ops", "Sum"),
                ("VolumeWriteOps", "write_ops", "Sum"),
                ("VolumeReadBytes", "read_bytes", "Sum"),
                ("VolumeWriteBytes", "write_bytes", "Sum"),
            ]

            self.logger.info(
                "fetching_ebs_metrics",
                instance_id=instance_id,
                metric_count=len(ebs_metric_configs),
            )

            ebs_results: list[dict[str, Any] | Exception] = []
            for i, (metric_name, key, statistic) in enumerate(ebs_metric_configs):
                self.logger.debug("fetching_ebs_metric", metric_name=metric_name, index=i + 1)
                try:
                    datapoints = await self.cloudwatch.get_metric_statistics(
                        namespace="AWS/EBS",
                        metric_name=metric_name,
                        dimensions={"InstanceId": instance_id},
                        start_time=start_time,
                        end_time=end_time,
                        period=300,
                        statistics=[statistic],
                    )
                    ebs_results.append({"metric_name": metric_name, "datapoints": datapoints})
                except Exception as e:
                    self.logger.warning(
                        "ebs_metric_fetch_failed", metric_name=metric_name, error=str(e)
                    )
                    ebs_results.append(e)

                if i < len(ebs_metric_configs) - 1:
                    await asyncio.sleep(CLOUDWATCH_DELAY_SECONDS)

            # Process EBS results
            ebs_data: dict[str, Any] = {"volumes": [], "aggregated": {}, "period_hours": hours}

            for i, (metric_name, key, statistic) in enumerate(ebs_metric_configs):
                result = ebs_results[i]
                if not isinstance(result, Exception) and result.get("datapoints"):
                    datapoints = result["datapoints"]
                    if datapoints:
                        avg_value = sum(
                            dp.value for dp in datapoints if hasattr(dp, "value")
                        ) / len(datapoints)
                        ebs_data["aggregated"][f"avg_{key}"] = avg_value

            if ebs_data["aggregated"]:
                metrics_data.ebs_metrics = ebs_data
                self.logger.info("ebs_metrics_collected", instance_id=instance_id)

        except Exception as e:
            self.logger.warning("ebs_metrics_error", instance_id=instance_id, error=str(e))

    async def get_realtime_system_metrics(self, instance_id: str, platform: str) -> RealtimeMetrics:
        """Get real-time system metrics via SSM commands.

        Executes platform-specific SSM commands to collect current operating system
        metrics including CPU, memory, processes, and uptime. Supports Windows and Linux.

        Args:
            instance_id: EC2 instance ID.
            platform: Platform type ("windows" or "linux").

        Returns:
            RealtimeMetrics object with current system metrics.

        Raises:
            ValueError: If platform is not "windows" or "linux".

        Example:
            >>> metrics = await collector.get_realtime_system_metrics("i-1234567890", "linux")
            >>> print(f"CPU: {metrics.cpu_percent}%, Memory: {metrics.memory_percent}%")
        """
        self.logger.info("get_realtime_metrics", instance_id=instance_id, platform=platform)

        # Validate platform
        if platform.lower() not in ["windows", "linux"]:
            raise ValueError(f"Invalid platform: {platform}. Must be 'windows' or 'linux'.")

        try:
            # Check SSM availability first
            ssm_available = await self._check_ssm_availability(instance_id)
            if not ssm_available:
                error_msg = await self._generate_ssm_unavailable_message(instance_id)
                self.logger.warning("ssm_unavailable", instance_id=instance_id, reason=error_msg)
                return RealtimeMetrics(
                    success=False,
                    ssm_unavailable=True,
                    error=error_msg,
                    cpu_percent="N/A",
                    memory_percent="N/A",
                    processes="N/A",
                )

            # Get platform-specific commands
            commands = self._get_platform_commands(platform)
            document_name = (
                "AWS-RunPowerShellScript" if platform.lower() == "windows" else "AWS-RunShellScript"
            )

            self.logger.info("sending_ssm_command", instance_id=instance_id, document=document_name)

            # Send command
            command = await self.ssm.send_command(
                instance_ids=[instance_id],
                commands=commands,
                document_name=document_name,
                comment="Ohlala SmartOps: Enhanced system metrics collection",
            )

            self.logger.info(
                "waiting_for_command", command_id=command.command_id, instance_id=instance_id
            )

            # Wait for command completion with retries
            invocation = await self.ssm.wait_for_completion(
                command_id=command.command_id,
                instance_id=instance_id,
                timeout=SSM_COMMAND_TIMEOUT,
            )

            if invocation.status == "Success" and invocation.stdout:
                # Parse JSON output
                try:
                    metrics_json = json.loads(invocation.stdout.strip())
                    self.logger.info(
                        "metrics_parsed",
                        instance_id=instance_id,
                        cpu=metrics_json.get("cpu_percent"),
                        memory=metrics_json.get("memory_percent"),
                    )
                    return RealtimeMetrics(**metrics_json, success=True)
                except json.JSONDecodeError as e:
                    self.logger.error(
                        "json_parse_error",
                        instance_id=instance_id,
                        error=str(e),
                        output=invocation.stdout[:200],
                    )
                    return RealtimeMetrics(success=False, error="Failed to parse metrics output")
            else:
                error_msg = invocation.stderr or invocation.status or "Command failed"
                self.logger.error(
                    "command_failed",
                    instance_id=instance_id,
                    status=invocation.status,
                    error=error_msg[:200],
                )
                return RealtimeMetrics(success=False, error=error_msg)

        except Exception as e:
            self.logger.error("realtime_metrics_error", instance_id=instance_id, error=str(e))
            return RealtimeMetrics(success=False, error=str(e))

    def _get_platform_commands(self, platform: str) -> list[str]:
        """Get platform-specific SSM commands for metrics collection.

        Args:
            platform: Platform type ("windows" or "linux").

        Returns:
            List of commands to execute on the instance.
        """
        if platform.lower() == "windows":
            return [self._get_windows_metrics_command()]
        return [self._get_linux_metrics_command()]

    def _get_windows_metrics_command(self) -> str:
        """Get PowerShell command for Windows metrics collection.

        Returns:
            PowerShell script as a string.
        """
        return """
# Get CPU with error handling
try {
    $cpu = (Get-Counter '\\Processor(_Total)\\% Processor Time' -ErrorAction SilentlyContinue).CounterSamples.CookedValue
    if (-not $cpu) { $cpu = 0 }
} catch {
    $cpu = 0
}

# Get memory info (WMI returns KB, convert to MB)
try {
    $mem = Get-WmiObject Win32_OperatingSystem -ErrorAction SilentlyContinue
    if ($mem) {
        $memUsedMB = [math]::Round((($mem.TotalVisibleMemorySize - $mem.FreePhysicalMemory) / 1024), 2)
        $memTotalMB = [math]::Round($mem.TotalVisibleMemorySize / 1024, 2)
        $memPercent = [math]::Round((($mem.TotalVisibleMemorySize - $mem.FreePhysicalMemory) / $mem.TotalVisibleMemorySize) * 100, 2)
    } else {
        $memUsedMB = 0
        $memTotalMB = 0
        $memPercent = 0
    }
} catch {
    $memUsedMB = 0
    $memTotalMB = 0
    $memPercent = 0
}

# Get process count
try {
    $processes = @(Get-Process -ErrorAction SilentlyContinue).Count
    if (-not $processes) { $processes = 0 }
} catch {
    $processes = 0
}

# Get uptime
try {
    $os = Get-WmiObject Win32_OperatingSystem -ErrorAction SilentlyContinue
    if ($os -and $os.LastBootUpTime) {
        $uptime = (Get-Date) - $os.ConvertToDateTime($os.LastBootUpTime)
        if ($uptime.Days -gt 0) {
            $uptime_text = "$($uptime.Days) days"
        } elseif ($uptime.Hours -gt 0) {
            $uptime_text = "$($uptime.Hours) hours"
        } else {
            $uptime_text = "$($uptime.Minutes) minutes"
        }
    } else {
        $uptime_text = "Unknown"
    }
} catch {
    $uptime_text = "Unknown"
}

# Output JSON
@{
    cpu_percent = [math]::Round($cpu, 2)
    memory_used_mb = $memUsedMB
    memory_total_mb = $memTotalMB
    memory_percent = $memPercent
    processes = $processes
    uptime_text = $uptime_text
    success = $true
} | ConvertTo-Json -Compress
"""

    def _get_linux_metrics_command(self) -> str:
        """Get shell script for Linux metrics collection.

        Returns:
            Shell script as a string.
        """
        return """
# Get comprehensive system metrics for Linux with enhanced JSON output

# CPU Usage - use vmstat as primary method for accuracy
cpu_idle=$(vmstat 1 2 | tail -1 | awk '{print $15}' 2>/dev/null)
if [ -n "$cpu_idle" ] && [ "$cpu_idle" -ge 0 ] 2>/dev/null; then
    cpu_percent=$(echo "100 - $cpu_idle" | bc 2>/dev/null || awk "BEGIN {print 100 - $cpu_idle}")
else
    # Fallback to top if vmstat fails
    cpu_percent=$(top -bn1 | grep -E "^(%)?Cpu" | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}' 2>/dev/null)
    if [ -z "$cpu_percent" ] || [ "$cpu_percent" = "100" ]; then
        cpu_percent="0"
    fi
fi

# Memory usage with detailed info
mem_info=$(free -m 2>/dev/null || echo "Mem: 0 0 0")
mem_total=$(echo "$mem_info" | grep Mem | awk '{print $2}' || echo "0")
mem_used=$(echo "$mem_info" | grep Mem | awk '{print $3}' || echo "0")
mem_percent=$(echo "$mem_info" | grep Mem | awk '{if($2>0) printf "%.1f", $3/$2*100; else print "0"}' || echo "0")

# Process count (exclude header)
processes=$(($(ps aux 2>/dev/null | wc -l) - 1))
[ $processes -lt 0 ] && processes=0

# Load average
load_avg=$(uptime | awk -F'load average:' '{print $2}' | sed 's/^ *//' | sed 's/,$//' || echo "0.00, 0.00, 0.00")

# Uptime information
uptime_info=$(uptime | sed 's/.*up \\([^,]*\\),.*/\\1/' | sed 's/^ *//' || echo "Unknown")

# Validate and default all values
cpu_percent=${cpu_percent:-0}
mem_percent=${mem_percent:-0}
mem_total=${mem_total:-0}
mem_used=${mem_used:-0}
processes=${processes:-0}
load_avg=${load_avg:-"0.00, 0.00, 0.00"}
uptime_info=${uptime_info:-"Unknown"}

# Output comprehensive JSON
echo "{\\"cpu_percent\\":$cpu_percent,\\"memory_percent\\":$mem_percent,\\"memory_total_mb\\":$mem_total,\\"memory_used_mb\\":$mem_used,\\"processes\\":$processes,\\"load_average\\":\\"$load_avg\\",\\"uptime_text\\":\\"$uptime_info\\",\\"success\\":true}"
"""

    async def _check_ssm_availability(self, instance_id: str) -> bool:
        """Check if SSM commands are available for the instance.

        Args:
            instance_id: EC2 instance ID.

        Returns:
            True if SSM is available, False otherwise.
        """
        try:
            # Try to get SSM instance information
            # This will fail if instance doesn't have SSM agent or proper IAM role
            from ohlala_smartops.aws.client import create_aws_client

            ssm_client = create_aws_client("ssm", region=self.region)
            response = await ssm_client.call_api(
                "describe_instance_information",
                Filters=[{"Key": "InstanceIds", "Values": [instance_id]}],
            )

            instance_list = response.get("InstanceInformationList", [])
            if not instance_list:
                self.logger.info("ssm_not_available", instance_id=instance_id, reason="not_in_ssm")
                return False

            # Instance is in SSM and available
            self.logger.info("ssm_available", instance_id=instance_id)
            return True

        except Exception as e:
            self.logger.warning(
                "ssm_availability_check_failed", instance_id=instance_id, error=str(e)
            )
            return False

    async def get_instance_health_summary(self, instance_id: str) -> dict[str, Any]:
        """Get a health summary for overview cards.

        Collects basic CPU and memory metrics for instance status summary.

        Args:
            instance_id: EC2 instance ID.

        Returns:
            Dictionary with health summary including cpu_percent, memory_percent, and status.
        """
        try:
            # Get basic metrics for summary
            metrics = await self.get_realtime_system_metrics(instance_id, "linux")

            if metrics.success:
                cpu = (
                    float(metrics.cpu_percent)
                    if isinstance(metrics.cpu_percent, int | float)
                    else 0
                )
                memory = (
                    float(metrics.memory_percent)
                    if isinstance(metrics.memory_percent, int | float)
                    else 0
                )

                # Determine status based on CPU
                if cpu >= 90:
                    status = "critical"
                elif cpu >= 80:
                    status = "warning"
                else:
                    status = "healthy"

                return {
                    "instance_id": instance_id,
                    "cpu_percent": cpu,
                    "memory_percent": memory,
                    "status": status,
                    "data_source": "ssm" if not metrics.ssm_unavailable else "cloudwatch",
                }

            # Fallback to CloudWatch if SSM unavailable
            cw_metrics = await self.get_cloudwatch_metrics(instance_id, hours=1)
            if cw_metrics.success and cw_metrics.cpu_graph.get("datapoints"):
                cpu = cw_metrics.cpu_graph.get("current", 0)

                # Determine status
                if cpu >= 90:
                    status = "critical"
                elif cpu >= 80:
                    status = "warning"
                else:
                    status = "healthy"

                return {
                    "instance_id": instance_id,
                    "cpu": cpu,
                    "cpu_percent": cpu,
                    "memory_percent": 0,
                    "status": status,
                    "data_source": "cloudwatch",
                }

            return {
                "instance_id": instance_id,
                "status": "unknown",
                "error": "Unable to fetch metrics",
            }

        except Exception as e:
            self.logger.error("health_summary_error", instance_id=instance_id, error=str(e))
            return {
                "instance_id": instance_id,
                "status": "error",
                "error": str(e),
            }

    async def _generate_ssm_unavailable_message(self, instance_id: str) -> str:
        """Generate a user-friendly message explaining why SSM is unavailable.

        Args:
            instance_id: EC2 instance ID.

        Returns:
            User-friendly error message.
        """
        try:
            from ohlala_smartops.aws.client import create_aws_client

            ec2_client = create_aws_client("ec2", region=self.region)
            response = await ec2_client.call_api("describe_instances", InstanceIds=[instance_id])

            instances = response.get("Reservations", [{}])[0].get("Instances", [])
            if not instances:
                return "⚠️ Instance not found or SSM commands not available."

            instance = instances[0]
            state = instance.get("State", {}).get("Name", "unknown")
            platform_details = instance.get("PlatformDetails", "Unknown")

            if state.lower() in ["stopped", "stopping", "terminated", "terminating"]:
                return f"⚠️ Instance is {state.lower()} and not available for monitoring"

            if "Amazon Linux AMI" in platform_details or "RHEL-6" in platform_details:
                return f"⚠️ Platform {platform_details} does not support SSM Agent.\\n\\nCloudWatch metrics will be used instead for basic monitoring."

            return f"""⚠️ SSM commands not supported on this instance ({platform_details}).

This could be due to:
• SSM agent not installed or not running
• Instance not configured for Systems Manager
• Missing IAM role or permissions
• Very old or unsupported platform

To enable detailed monitoring:
1. Install SSM agent on the instance
2. Attach the 'AmazonSSMManagedInstanceCore' policy to the instance role
3. Ensure the instance can reach SSM endpoints

CloudWatch metrics will be used for basic monitoring."""

        except Exception:
            return "⚠️ SSM commands not available. CloudWatch metrics will be used instead."
