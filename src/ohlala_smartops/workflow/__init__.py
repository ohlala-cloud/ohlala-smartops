"""Workflow management for operations requiring user approval.

This package provides components for managing write operations that require
user confirmation before execution.
"""

from ohlala_smartops.workflow.write_operations import WriteOperationManager

__all__ = [
    "WriteOperationManager",
]
