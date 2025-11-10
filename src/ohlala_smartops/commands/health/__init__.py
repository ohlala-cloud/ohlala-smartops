"""Health dashboard command package for EC2 instance monitoring.

This package provides comprehensive health monitoring and visualization for EC2 instances
including CPU trends, memory usage, disk analysis, system logs, and more.
"""

from ohlala_smartops.commands.health.dashboard import HealthDashboardCommand

__all__ = ["HealthDashboardCommand"]
