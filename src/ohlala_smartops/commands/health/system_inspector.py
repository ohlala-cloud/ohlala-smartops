"""System information, disk usage, and log collection for EC2 instance health checks.

This module provides functionality to collect detailed system information from EC2 instances
via AWS Systems Manager (SSM) commands. Supports both Windows and Linux platforms with
platform-specific commands for disk analysis, error logs, and system details.
"""

import json
import logging
from typing import Any, Final

from pydantic import BaseModel

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

# SSM command timeout
SSM_COMMAND_TIMEOUT: Final[int] = 15  # seconds


class DiskInfo(BaseModel):
    """Model for disk usage information.

    Attributes:
        Device: Device name (e.g., "/dev/sda1" or "C:").
        Mount: Mount point (e.g., "/" or "C:\\").
        SizeGB: Total disk size in GB.
        UsedGB: Used disk space in GB.
        FreeGB: Free disk space in GB.
        UsedPercent: Percentage of disk space used.
    """

    Device: str
    Mount: str = "/"
    SizeGB: float
    UsedGB: float
    FreeGB: float
    UsedPercent: float


class SystemInfo(BaseModel):
    """Model for system information.

    Attributes:
        OSVersion: Operating system version string.
        LastBoot: Last boot time as string.
        CPUName: CPU model name.
        CPUCores: Number of CPU cores.
        RunningServices: Number of running services.
        FailedServices: Comma-separated list of failed services.
        UptimeText: Human-readable uptime (optional, Windows only).
    """

    OSVersion: str = "Unknown"
    LastBoot: str = "Unknown"
    CPUName: str = "Unknown"
    CPUCores: int = 0
    RunningServices: int = 0
    FailedServices: str = ""
    UptimeText: str | None = None


class ErrorLog(BaseModel):
    """Model for error log entry.

    Attributes:
        Time: Timestamp of the error.
        Message: Error message (truncated to 200 chars).
        Source: Source of the error (optional, Windows only).
    """

    Time: str
    Message: str
    Source: str | None = None


class SystemInspector:
    """Handles system inspection including disk usage, logs, and system information.

    This class provides methods to collect detailed system information from EC2 instances
    using AWS Systems Manager (SSM) commands. It supports both Windows and Linux platforms
    with platform-specific command generation.

    Example:
        >>> inspector = SystemInspector()
        >>> disk_info = await inspector.get_disk_usage("i-1234567890", "linux")
        >>> print(disk_info["disks"][0].Device)
        /dev/xvda1
    """

    def __init__(
        self, ssm_manager: SSMCommandManager | None = None, region: str = "us-east-1"
    ) -> None:
        """Initialize the system inspector.

        Args:
            ssm_manager: SSM command manager instance. Creates new if None.
            region: AWS region for API calls. Defaults to "us-east-1".
        """
        self.ssm = ssm_manager or SSMCommandManager(region=region)
        self.region = region
        self.logger = logger.bind(component="system_inspector", region=region)

    async def get_disk_usage(self, instance_id: str, platform: str) -> dict[str, Any]:
        """Get detailed disk usage information for all mounted filesystems.

        Executes platform-specific commands to retrieve disk usage information including
        total size, used space, free space, and usage percentage for each mounted filesystem.

        Args:
            instance_id: EC2 instance ID.
            platform: Platform type ("windows" or "linux").

        Returns:
            Dictionary with "disks" key containing list of DiskInfo objects.
            Returns empty dict on failure.

        Example:
            >>> disk_info = await inspector.get_disk_usage("i-1234567890", "linux")
            >>> for disk in disk_info["disks"]:
            ...     print(f"{disk.Device}: {disk.UsedPercent}% used")
        """
        self.logger.info("get_disk_usage", instance_id=instance_id, platform=platform)

        try:
            commands, document_name = self._get_disk_usage_commands(platform)

            # Send SSM command
            command = await self.ssm.send_command(
                instance_ids=[instance_id],
                commands=commands,
                document_name=document_name,
                comment="Ohlala SmartOps: Disk usage analysis",
            )

            # Wait for completion
            invocation = await self.ssm.wait_for_completion(
                command_id=command.command_id,
                instance_id=instance_id,
                timeout=SSM_COMMAND_TIMEOUT,
            )

            if invocation.status == "Success" and invocation.stdout:
                try:
                    disks_data = json.loads(invocation.stdout.strip())
                    # Ensure it's a list
                    if not isinstance(disks_data, list):
                        disks_data = [disks_data]
                    # Validate with Pydantic
                    validated_disks = [DiskInfo(**disk) for disk in disks_data]
                    self.logger.info(
                        "disk_usage_collected",
                        instance_id=instance_id,
                        disk_count=len(validated_disks),
                    )
                    return {"disks": validated_disks}
                except (json.JSONDecodeError, ValueError) as e:
                    self.logger.warning(
                        "disk_usage_parse_error", instance_id=instance_id, error=str(e)
                    )
                    return {}
            else:
                self.logger.warning(
                    "disk_usage_failed", instance_id=instance_id, status=invocation.status
                )
                return {}

        except Exception as e:
            self.logger.error("disk_usage_error", instance_id=instance_id, error=str(e))
            return {}

    async def get_recent_error_logs(self, instance_id: str, platform: str) -> dict[str, Any]:
        """Get recent error logs from the system.

        Retrieves the last 10 error entries from system logs (Windows Event Viewer
        or Linux syslog/messages). Useful for identifying recent system issues.

        Args:
            instance_id: EC2 instance ID.
            platform: Platform type ("windows" or "linux").

        Returns:
            Dictionary with "error_logs" key containing list of ErrorLog objects.
            Returns empty dict on failure.

        Example:
            >>> logs = await inspector.get_recent_error_logs("i-1234567890", "linux")
            >>> for log in logs["error_logs"]:
            ...     print(f"{log.Time}: {log.Message}")
        """
        self.logger.info("get_error_logs", instance_id=instance_id, platform=platform)

        try:
            commands, document_name = self._get_error_logs_commands(platform)

            # Send SSM command
            command = await self.ssm.send_command(
                instance_ids=[instance_id],
                commands=commands,
                document_name=document_name,
                comment="Ohlala SmartOps: Error log analysis",
            )

            # Wait for completion
            invocation = await self.ssm.wait_for_completion(
                command_id=command.command_id,
                instance_id=instance_id,
                timeout=SSM_COMMAND_TIMEOUT,
            )

            if invocation.status == "Success" and invocation.stdout:
                try:
                    logs_data = json.loads(invocation.stdout.strip())
                    # Ensure it's a list
                    if not isinstance(logs_data, list):
                        logs_data = []
                    # Validate with Pydantic
                    validated_logs = [ErrorLog(**log) for log in logs_data]
                    self.logger.info(
                        "error_logs_collected",
                        instance_id=instance_id,
                        log_count=len(validated_logs),
                    )
                    return {"error_logs": validated_logs}
                except (json.JSONDecodeError, ValueError) as e:
                    self.logger.warning(
                        "error_logs_parse_error", instance_id=instance_id, error=str(e)
                    )
                    # Fallback to plain text
                    return {"error_logs_text": invocation.stdout.strip()}
            else:
                self.logger.warning(
                    "error_logs_failed", instance_id=instance_id, status=invocation.status
                )
                return {}

        except Exception as e:
            self.logger.error("error_logs_error", instance_id=instance_id, error=str(e))
            return {}

    async def get_system_info(self, instance_id: str, platform: str) -> SystemInfo | dict[str, Any]:
        """Get additional system information.

        Collects detailed system information including OS version, CPU details,
        service counts, and last boot time.

        Args:
            instance_id: EC2 instance ID.
            platform: Platform type ("windows" or "linux").

        Returns:
            SystemInfo object with system details, or empty dict on failure.

        Example:
            >>> info = await inspector.get_system_info("i-1234567890", "linux")
            >>> print(f"OS: {info.OSVersion}, CPU: {info.CPUName}")
        """
        self.logger.info("get_system_info", instance_id=instance_id, platform=platform)

        try:
            commands, document_name = self._get_system_info_commands(platform)

            # Send SSM command
            command = await self.ssm.send_command(
                instance_ids=[instance_id],
                commands=commands,
                document_name=document_name,
                comment="Ohlala SmartOps: System information collection",
            )

            # Wait for completion (system info can take longer)
            invocation = await self.ssm.wait_for_completion(
                command_id=command.command_id,
                instance_id=instance_id,
                timeout=SSM_COMMAND_TIMEOUT,
            )

            if invocation.status == "Success" and invocation.stdout:
                try:
                    info_data = json.loads(invocation.stdout.strip())
                    # Validate with Pydantic
                    validated_info = SystemInfo(**info_data)
                    self.logger.info(
                        "system_info_collected",
                        instance_id=instance_id,
                        os=validated_info.OSVersion,
                    )
                    return validated_info
                except (json.JSONDecodeError, ValueError) as e:
                    self.logger.warning(
                        "system_info_parse_error", instance_id=instance_id, error=str(e)
                    )
                    return {}
            else:
                self.logger.warning(
                    "system_info_failed", instance_id=instance_id, status=invocation.status
                )
                return {}

        except Exception as e:
            self.logger.error("system_info_error", instance_id=instance_id, error=str(e))
            return {}

    def _get_disk_usage_commands(self, platform: str) -> tuple[list[str], str]:
        """Get platform-specific disk usage commands.

        Args:
            platform: Platform type ("windows" or "linux").

        Returns:
            Tuple of (commands list, document name).
        """
        if platform.lower() == "windows":
            commands = [
                """
Get-WmiObject -Class Win32_LogicalDisk | Where-Object {$_.DriveType -eq 3} |
Select-Object DeviceID,
    @{Name='SizeGB';Expression={[math]::Round($_.Size/1GB,2)}},
    @{Name='FreeGB';Expression={[math]::Round($_.FreeSpace/1GB,2)}},
    @{Name='UsedGB';Expression={[math]::Round(($_.Size-$_.FreeSpace)/1GB,2)}},
    @{Name='UsedPercent';Expression={if($_.Size -gt 0){[math]::Round((($_.Size-$_.FreeSpace)/$_.Size)*100,2)}else{0}}},
    @{Name='Mount';Expression={$_.DeviceID}} |
ConvertTo-Json -Compress
"""
            ]
            document_name = "AWS-RunPowerShellScript"
        else:
            commands = [
                """
df -BG | grep -E '^/dev/' | awk '{
    gsub(/G/, "", $2); gsub(/G/, "", $3); gsub(/G/, "", $4); gsub(/%/, "", $5);
    printf "{\\"Device\\":\\"%s\\",\\"SizeGB\\":%s,\\"UsedGB\\":%s,\\"FreeGB\\":%s,\\"UsedPercent\\":%s,\\"Mount\\":\\"%s\\"}\\n",
    $1, $2, $3, $4, $5, $6
}' | jq -s '.'
"""
            ]
            document_name = "AWS-RunShellScript"

        return commands, document_name

    def _get_error_logs_commands(self, platform: str) -> tuple[list[str], str]:
        """Get platform-specific error logs commands.

        Args:
            platform: Platform type ("windows" or "linux").

        Returns:
            Tuple of (commands list, document name).
        """
        if platform.lower() == "windows":
            commands = [
                """
try {
    $events = @()

    # Try to get System errors
    try {
        $system_errors = Get-WinEvent -LogName System -MaxEvents 5 -ErrorAction SilentlyContinue | Where-Object {$_.LevelDisplayName -eq "Error"}
        $events += $system_errors
    } catch { }

    # Try to get Application errors
    try {
        $app_errors = Get-WinEvent -LogName Application -MaxEvents 5 -ErrorAction SilentlyContinue | Where-Object {$_.LevelDisplayName -eq "Error"}
        $events += $app_errors
    } catch { }

    if ($events.Count -eq 0) {
        Write-Output "[]"
    } else {
        $events | Sort-Object TimeCreated -Descending | Select-Object -First 10 | ForEach-Object {
            @{
                Time = $_.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                Source = $_.ProviderName
                Message = $_.Message.Substring(0, [Math]::Min(200, $_.Message.Length))
            }
        } | ConvertTo-Json -Compress
    }
} catch {
    Write-Output "[]"
}
"""
            ]
            document_name = "AWS-RunPowerShellScript"
        else:
            commands = [
                """
if [ -f /var/log/syslog ]; then
    LOG_FILE="/var/log/syslog"
elif [ -f /var/log/messages ]; then
    LOG_FILE="/var/log/messages"
else
    echo "[]"
    exit 0
fi

# Check if jq is available
if command -v jq >/dev/null 2>&1; then
    # Use jq for proper JSON escaping
    grep -i "error\\|fail\\|critical" "$LOG_FILE" 2>/dev/null | tail -10 | \
    jq -R -s 'split("\\n") | map(select(length > 0)) | map({
        Time: (. | split(" ") | .[0:3] | join(" ")),
        Message: (. | split(" ") | .[3:] | join(" ") | .[0:200])
    })'
else
    # Fallback without jq - build JSON manually
    echo "["
    grep -i "error\\|fail\\|critical" "$LOG_FILE" 2>/dev/null | tail -10 | head -9 | while IFS= read -r line; do
        timestamp=$(echo "$line" | awk '{print $1" "$2" "$3}')
        message=$(echo "$line" | cut -d' ' -f4- | head -c 200 | sed 's/"/\\\\"/g' | sed "s/'/\\\\'/g")
        echo "  {\\"Time\\": \\"$timestamp\\", \\"Message\\": \\"$message\\"},"
    done
    # Last line without comma
    grep -i "error\\|fail\\|critical" "$LOG_FILE" 2>/dev/null | tail -1 | while IFS= read -r line; do
        timestamp=$(echo "$line" | awk '{print $1" "$2" "$3}')
        message=$(echo "$line" | cut -d' ' -f4- | head -c 200 | sed 's/"/\\\\"/g' | sed "s/'/\\\\'/g")
        echo "  {\\"Time\\": \\"$timestamp\\", \\"Message\\": \\"$message\\"}"
    done
    echo "]"
fi
"""
            ]
            document_name = "AWS-RunShellScript"

        return commands, document_name

    def _get_system_info_commands(self, platform: str) -> tuple[list[str], str]:
        """Get platform-specific system info commands.

        Args:
            platform: Platform type ("windows" or "linux").

        Returns:
            Tuple of (commands list, document name).
        """
        if platform.lower() == "windows":
            commands = [
                """
# Simple approach with better error handling
$ErrorActionPreference = "SilentlyContinue"

# Initialize all variables
$osVersion = "Unknown"
$lastBoot = "Unknown"
$cpuName = "Unknown"
$cpuCores = 0
$runningServices = 0
$failedServices = ""
$uptimeText = "Unknown"

# Get OS information
$os = Get-WmiObject Win32_OperatingSystem
if ($os) {
    $osVersion = $os.Caption

    # Get last boot time using simpler method
    $bootTime = $os.LastBootUpTime
    if ($bootTime) {
        $lastBoot = [System.Management.ManagementDateTimeConverter]::ToDateTime($bootTime).ToString("yyyy-MM-dd HH:mm:ss")

        # Calculate uptime
        $uptime = (Get-Date) - [System.Management.ManagementDateTimeConverter]::ToDateTime($bootTime)
        if ($uptime.Days -gt 1) {
            $uptimeText = "$($uptime.Days) days"
        } elseif ($uptime.Days -eq 1) {
            $uptimeText = "1 day"
        } elseif ($uptime.Hours -gt 1) {
            $uptimeText = "$($uptime.Hours) hours"
        } elseif ($uptime.Hours -eq 1) {
            $uptimeText = "1 hour"
        } else {
            $uptimeText = "$($uptime.Minutes) minutes"
        }
    }
}

# Get CPU information
$cpu = Get-WmiObject Win32_Processor | Select-Object -First 1
if ($cpu) {
    $cpuName = $cpu.Name
    $cpuCores = $cpu.NumberOfCores
}

# Get running services count
$services = Get-Service | Where-Object {$_.Status -eq 'Running'}
if ($services) {
    $runningServices = $services.Count
}

# Check critical services (simplified)
$criticalServices = @("W32Time", "EventLog", "RpcSs")
$failed = @()
foreach ($serviceName in $criticalServices) {
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service -and $service.Status -ne 'Running') {
        $failed += $service.DisplayName
    }
}
if ($failed.Count -gt 0) {
    $failedServices = $failed -join ", "
}

# Output JSON
@{
    OSVersion = $osVersion
    LastBoot = $lastBoot
    CPUName = $cpuName
    CPUCores = $cpuCores
    RunningServices = $runningServices
    FailedServices = $failedServices
    UptimeText = $uptimeText
} | ConvertTo-Json -Compress
"""
            ]
            document_name = "AWS-RunPowerShellScript"
        else:
            commands = [
                """
os_version=$(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)
last_boot=$(who -b | awk '{print $3" "$4}')
cpu_info=$(lscpu | grep "Model name" | cut -d':' -f2 | xargs)
cpu_cores=$(nproc)
running_services=$(systemctl list-units --type=service --state=running | wc -l)
failed_services=$(systemctl list-units --type=service --state=failed --no-legend | awk '{print $1}' | tr '\\n' ' ' | sed 's/[[:space:]]*$//')

# Use jq to properly create JSON with escaped strings
jq -n \\
  --arg os_version "$os_version" \\
  --arg last_boot "$last_boot" \\
  --arg cpu_info "$cpu_info" \\
  --argjson cpu_cores "$cpu_cores" \\
  --argjson running_services "$running_services" \\
  --arg failed_services "$failed_services" \\
  '{
    "OSVersion": $os_version,
    "LastBoot": $last_boot,
    "CPUName": $cpu_info,
    "CPUCores": $cpu_cores,
    "RunningServices": $running_services,
    "FailedServices": $failed_services
  }'
"""
            ]
            document_name = "AWS-RunShellScript"

        return commands, document_name
