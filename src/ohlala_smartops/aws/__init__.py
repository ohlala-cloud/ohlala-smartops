"""AWS integration modules for Ohlala SmartOps.

This package provides AWS service integrations with:
- Boto3 client wrappers with automatic throttling
- Custom exception hierarchy for AWS errors
- Async/await support for all AWS operations
- Retry logic with exponential backoff
- Integration with GlobalThrottler for rate limiting

Example:
    >>> from ohlala_smartops.aws import create_aws_client, execute_with_retry
    >>>
    >>> # Create an EC2 client
    >>> ec2_client = create_aws_client("ec2", region="us-east-1")
    >>>
    >>> # Make a call with automatic throttling
    >>> async def get_instances():
    ...     return await ec2_client.call("describe_instances")
    >>>
    >>> # Execute with retry logic
    >>> result = await execute_with_retry(get_instances, max_retries=3)
"""

from ohlala_smartops.aws.client import (
    AWSClientWrapper,
    create_aws_client,
    execute_with_retry,
)
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
    "PermissionError",
    "ResourceNotFoundError",
    "SSMError",
    "ThrottlingError",
    "TimeoutError",
    "ValidationError",
    "create_aws_client",
    "execute_with_retry",
]
