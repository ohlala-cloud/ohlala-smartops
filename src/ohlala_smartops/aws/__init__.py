"""AWS integration modules for Ohlala SmartOps.

This package provides AWS service integrations with:
- Boto3 client wrappers with automatic throttling
- Custom exception hierarchy for AWS errors
- Async/await support for all AWS operations
- Retry logic with exponential backoff
- Integration with GlobalThrottler for rate limiting
- EC2 instance management utilities
- SSM command execution and tracking

Example:
    >>> from ohlala_smartops.aws import EC2Manager, SSMCommandManager
    >>>
    >>> # High-level EC2 management
    >>> ec2_mgr = EC2Manager(region="us-east-1")
    >>> instances = await ec2_mgr.describe_instances(["i-123"])
    >>> await ec2_mgr.start_instances(["i-123"])
    >>>
    >>> # SSM command execution
    >>> ssm_mgr = SSMCommandManager(region="us-east-1")
    >>> cmd = await ssm_mgr.send_command(
    ...     instance_ids=["i-123"],
    ...     commands=["ls -la"],
    ... )
    >>> result = await ssm_mgr.wait_for_completion(cmd.command_id, "i-123")
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
from ohlala_smartops.aws.ssm_commands import (
    SSMCommand,
    SSMCommandInvocation,
    SSMCommandManager,
)

__all__ = [
    "AWSClientWrapper",
    "AWSError",
    "EC2Error",
    "EC2Instance",
    "EC2Manager",
    "PermissionError",
    "ResourceNotFoundError",
    "SSMCommand",
    "SSMCommandInvocation",
    "SSMCommandManager",
    "SSMError",
    "ThrottlingError",
    "TimeoutError",
    "ValidationError",
    "create_aws_client",
    "execute_with_retry",
]
