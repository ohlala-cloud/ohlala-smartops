"""AWS integration modules for Ohlala SmartOps.

This package provides AWS service integrations with:
- Boto3 client wrappers with automatic throttling
- Custom exception hierarchy for AWS errors
- Async/await support for all AWS operations
- Retry logic with exponential backoff
- Integration with GlobalThrottler for rate limiting
- EC2 instance management utilities

Example:
    >>> from ohlala_smartops.aws import EC2Manager, create_aws_client
    >>>
    >>> # High-level EC2 management
    >>> manager = EC2Manager(region="us-east-1")
    >>> instances = await manager.describe_instances(["i-123"])
    >>> await manager.start_instances(["i-123"])
    >>>
    >>> # Low-level client usage
    >>> ec2_client = create_aws_client("ec2", region="us-east-1")
    >>> result = await ec2_client.call("describe_instances")
"""

from ohlala_smartops.aws.client import (
    AWSClientWrapper,
    create_aws_client,
    execute_with_retry,
)
from ohlala_smartops.aws.ec2 import EC2Instance, EC2Manager
from ohlala_smartops.aws.exceptions import (
    AWSError,
    EC2Error,
    PermissionError,
    ResourceNotFoundError,
    SSMError,
    ThrottlingError,
    TimeoutError,
    ValidationError,
)

__all__ = [
    "AWSClientWrapper",
    "AWSError",
    "EC2Error",
    "EC2Instance",
    "EC2Manager",
    "PermissionError",
    "ResourceNotFoundError",
    "SSMError",
    "ThrottlingError",
    "TimeoutError",
    "ValidationError",
    "create_aws_client",
    "execute_with_retry",
]
