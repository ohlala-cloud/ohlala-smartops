"""Custom exceptions for AWS operations.

This module defines a hierarchy of exceptions for AWS service operations,
providing clear error categorization and context for error handling.
"""

from typing import Any


class AWSError(Exception):
    """Base exception for all AWS-related errors.

    This is the base class for all AWS operation errors. It can be used
    to catch any AWS-related error in the application.

    Attributes:
        message: Human-readable error message.
        service: AWS service name (e.g., 'ec2', 'ssm').
        operation: AWS operation name (e.g., 'DescribeInstances').
        error_code: AWS error code if available (e.g., 'InvalidInstanceID.NotFound').
        details: Additional error context as dictionary.
    """

    def __init__(
        self,
        message: str,
        service: str | None = None,
        operation: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize AWS error with context.

        Args:
            message: Human-readable error message.
            service: AWS service name (e.g., 'ec2', 'ssm'). Defaults to None.
            operation: AWS operation name (e.g., 'DescribeInstances'). Defaults to None.
            error_code: AWS error code if available. Defaults to None.
            details: Additional error context. Defaults to None.
        """
        super().__init__(message)
        self.message = message
        self.service = service
        self.operation = operation
        self.error_code = error_code
        self.details = details or {}

    def __str__(self) -> str:
        """Return formatted error string with context."""
        parts = [self.message]
        if self.service:
            parts.append(f"Service: {self.service}")
        if self.operation:
            parts.append(f"Operation: {self.operation}")
        if self.error_code:
            parts.append(f"Code: {self.error_code}")
        return " | ".join(parts)


class EC2Error(AWSError):
    """Exception raised for EC2 service errors.

    Raised when EC2 operations fail, such as instance management,
    volume operations, or networking operations.
    """


class SSMError(AWSError):
    """Exception raised for Systems Manager service errors.

    Raised when SSM operations fail, such as command execution,
    session management, or parameter store operations.
    """


class TaggingError(AWSError):
    """Exception raised for resource tagging errors.

    Raised when tagging operations fail, such as adding tags,
    removing tags, or querying resources by tags.
    """


class CloudWatchError(AWSError):
    """Exception raised for CloudWatch service errors.

    Raised when CloudWatch operations fail, such as getting metrics,
    putting metric data, or listing metrics.
    """


class CostExplorerError(AWSError):
    """Exception raised for Cost Explorer service errors.

    Raised when Cost Explorer operations fail, such as getting cost data,
    forecasting costs, or retrieving recommendations.
    """


class ThrottlingError(AWSError):
    """Exception raised when AWS API rate limits are exceeded.

    This exception indicates that the request was throttled by AWS.
    The caller should implement exponential backoff and retry logic.
    """


class ValidationError(AWSError):
    """Exception raised for input validation errors.

    Raised when the provided parameters fail validation before
    making the AWS API call. This includes invalid instance IDs,
    malformed inputs, or missing required parameters.
    """


class ResourceNotFoundError(AWSError):
    """Exception raised when an AWS resource is not found.

    Raised when attempting to access or operate on a resource
    that doesn't exist or is not accessible with the current credentials.
    """


class PermissionError(AWSError):
    """Exception raised for AWS permission/authorization errors.

    Raised when the current IAM credentials lack the necessary
    permissions to perform the requested operation.
    """


class TimeoutError(AWSError):
    """Exception raised when an AWS operation times out.

    Raised when an operation exceeds the configured timeout period.
    This may indicate slow AWS API response or network issues.
    """
