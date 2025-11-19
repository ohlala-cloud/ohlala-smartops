"""AWS client wrapper with throttling and error handling.

This module provides a wrapper around boto3 clients that automatically integrates
with the global throttling system and provides consistent error handling across
all AWS service operations.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Final, TypeVar

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from ohlala_smartops.aws.exceptions import (
    CloudWatchError,
    CostExplorerError,
    EC2Error,
    PermissionError,
    ResourceNotFoundError,
    SSMError,
    TaggingError,
    ThrottlingError,
    TimeoutError,
    ValidationError,
)
from ohlala_smartops.utils import throttled_aws_call

logger: Final = logging.getLogger(__name__)

T = TypeVar("T")


class AWSClientWrapper:
    """Wrapper for boto3 clients with throttling and error handling.

    This class wraps boto3 service clients to provide:
    - Automatic integration with GlobalThrottler for rate limiting
    - Consistent error handling with custom exception types
    - Async/await support for all operations
    - Automatic retry logic for transient errors
    - Detailed logging of all AWS operations

    The wrapper converts boto3's synchronous calls to async operations
    and ensures all calls respect the global rate limits.

    Example:
        >>> wrapper = AWSClientWrapper("ec2", region="us-east-1")
        >>> result = await wrapper.call("describe_instances", InstanceIds=["i-123"])
    """

    def __init__(self, service_name: str, region: str | None = None, **kwargs: Any) -> None:
        """Initialize AWS client wrapper.

        Args:
            service_name: AWS service name (e.g., 'ec2', 'ssm', 's3').
            region: AWS region name. If None, uses default from environment/config.
                Defaults to None.
            **kwargs: Additional arguments passed to boto3.client().

        Example:
            >>> client = AWSClientWrapper("ec2", region="us-west-2")
            >>> client = AWSClientWrapper("ssm", region="eu-west-1", endpoint_url="...")
        """
        self.service_name = service_name
        self.region = region
        self._client: BaseClient = boto3.client(  # type: ignore[call-overload]
            service_name, region_name=region, **kwargs
        )
        logger.info(f"Initialized AWS {service_name} client for region {region or 'default'}")

    async def call(self, operation: str, **kwargs: Any) -> Any:
        """Execute AWS operation with throttling and error handling.

        This method wraps any boto3 client operation, providing:
        - Rate limiting through GlobalThrottler
        - Automatic error classification and custom exceptions
        - Async execution in thread pool (boto3 is synchronous)
        - Operation logging for debugging

        Args:
            operation: AWS operation name (e.g., 'describe_instances', 'start_instances').
            **kwargs: Operation-specific parameters.

        Returns:
            The response from the AWS operation.

        Raises:
            ValidationError: For invalid parameters or input validation errors.
            ResourceNotFoundError: When requested resource doesn't exist.
            PermissionError: For IAM permission/authorization errors.
            ThrottlingError: When AWS rate limits are exceeded.
            TimeoutError: When operation exceeds timeout.
            EC2Error: For EC2-specific errors.
            SSMError: For SSM-specific errors.
            AWSError: For other AWS errors.

        Example:
            >>> wrapper = AWSClientWrapper("ec2")
            >>> result = await wrapper.call("describe_instances")
            >>> instances = result["Reservations"][0]["Instances"]
        """
        operation_name = f"{self.service_name}:{operation}"

        logger.debug(f"Calling {operation_name} with params: {list(kwargs.keys())}")

        try:
            async with throttled_aws_call(operation_name):
                # Execute boto3 call in thread pool (boto3 is synchronous)
                loop = asyncio.get_event_loop()
                client_method = getattr(self._client, operation)
                result = await loop.run_in_executor(None, lambda: client_method(**kwargs))

                logger.debug(f"Successfully completed {operation_name}")
                return result

        except ClientError as e:
            # Convert boto3 ClientError to our custom exceptions
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            logger.warning(f"{operation_name} failed with {error_code}: {error_message}")

            raise self._convert_client_error(e, operation, error_code, error_message) from e

        except BotoCoreError as e:
            # Handle botocore-level errors (network, timeout, etc.)
            logger.error(f"{operation_name} failed with BotoCoreError: {e}")

            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                raise TimeoutError(
                    f"Operation {operation} timed out",
                    service=self.service_name,
                    operation=operation,
                ) from e

            # Generic AWS error for other botocore errors
            error_class = self._get_service_error_class()
            raise error_class(
                f"AWS operation failed: {e}",
                service=self.service_name,
                operation=operation,
            ) from e

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"{operation_name} failed with unexpected error: {e}")
            error_class = self._get_service_error_class()
            raise error_class(
                f"Unexpected error during {operation}: {e}",
                service=self.service_name,
                operation=operation,
            ) from e

    def _convert_client_error(
        self, error: ClientError, operation: str, error_code: str, error_message: str
    ) -> Exception:
        """Convert boto3 ClientError to appropriate custom exception.

        Args:
            error: The original ClientError from boto3.
            operation: The AWS operation name.
            error_code: AWS error code from the response.
            error_message: AWS error message from the response.

        Returns:
            Custom exception instance matching the error type.
        """
        details = {
            "error_code": error_code,
            "http_status": error.response.get("ResponseMetadata", {}).get("HTTPStatusCode"),
            "request_id": error.response.get("ResponseMetadata", {}).get("RequestId"),
        }

        # Throttling errors
        if error_code in ("Throttling", "RequestLimitExceeded", "TooManyRequestsException"):
            return ThrottlingError(
                error_message,
                service=self.service_name,
                operation=operation,
                error_code=error_code,
                details=details,
            )

        # Permission errors
        if error_code in ("UnauthorizedOperation", "AccessDenied", "AccessDeniedException"):
            return PermissionError(
                error_message,
                service=self.service_name,
                operation=operation,
                error_code=error_code,
                details=details,
            )

        # Resource not found errors (must come before generic Invalid* check)
        if error_code.endswith("NotFound") or error_code in (
            "InvalidInstanceID.NotFound",
            "InvalidInstanceID.Malformed",
        ):
            return ResourceNotFoundError(
                error_message,
                service=self.service_name,
                operation=operation,
                error_code=error_code,
                details=details,
            )

        # Validation errors (check for specific validation codes and generic Invalid* patterns)
        if error_code in (
            "ValidationError",
            "InvalidParameterValue",
            "MissingParameter",
        ) or error_code.startswith("Invalid"):
            return ValidationError(
                error_message,
                service=self.service_name,
                operation=operation,
                error_code=error_code,
                details=details,
            )

        # Service-specific errors
        error_class = self._get_service_error_class()
        return error_class(
            error_message,
            service=self.service_name,
            operation=operation,
            error_code=error_code,
            details=details,
        )

    def _get_service_error_class(
        self,
    ) -> (
        type[EC2Error]
        | type[SSMError]
        | type[TaggingError]
        | type[CloudWatchError]
        | type[CostExplorerError]
    ):
        """Get the appropriate service-specific error class.

        Returns:
            EC2Error for EC2 service, SSMError for SSM, TaggingError for
            Resource Groups Tagging API, CloudWatchError for CloudWatch,
            CostExplorerError for Cost Explorer, etc.
        """
        if self.service_name == "ec2":
            return EC2Error
        if self.service_name == "ssm":
            return SSMError
        if self.service_name == "resourcegroupstaggingapi":
            return TaggingError
        if self.service_name == "cloudwatch":
            return CloudWatchError
        if self.service_name == "ce":
            return CostExplorerError
        # Add more services as needed
        return EC2Error  # Default fallback

    @asynccontextmanager
    async def batch_calls(self) -> Any:
        """Context manager for batching multiple AWS calls efficiently.

        This context manager allows multiple AWS operations to be executed
        efficiently, while still respecting rate limits and using the global
        throttler.

        Yields:
            Self, for chaining multiple calls.

        Example:
            >>> wrapper = AWSClientWrapper("ec2")
            >>> async with wrapper.batch_calls():
            ...     result1 = await wrapper.call("describe_instances")
            ...     result2 = await wrapper.call("describe_volumes")
        """
        # For now, this is a simple passthrough, but it can be enhanced
        # later with batching optimizations
        logger.debug(f"Starting batch operation for {self.service_name}")
        try:
            yield self
        finally:
            logger.debug(f"Completed batch operation for {self.service_name}")

    def get_client(self) -> BaseClient:
        """Get the underlying boto3 client for advanced use cases.

        Warning:
            Direct use of the boto3 client bypasses throttling and error
            handling. Use this only when necessary and ensure you handle
            errors and rate limiting appropriately.

        Returns:
            The underlying boto3 BaseClient instance.

        Example:
            >>> wrapper = AWSClientWrapper("ec2")
            >>> raw_client = wrapper.get_client()
            >>> # Use with caution - no throttling or error handling!
        """
        logger.warning(f"Direct access to {self.service_name} client requested - bypassing wrapper")
        return self._client


def create_aws_client(
    service_name: str, region: str | None = None, **kwargs: Any
) -> AWSClientWrapper:
    """Factory function to create AWS client wrapper.

    This is a convenience function for creating AWSClientWrapper instances
    with a cleaner syntax.

    Args:
        service_name: AWS service name (e.g., 'ec2', 'ssm').
        region: AWS region name. Defaults to None (uses default region).
        **kwargs: Additional arguments for boto3.client().

    Returns:
        Configured AWSClientWrapper instance.

    Example:
        >>> ec2_client = create_aws_client("ec2", region="us-east-1")
        >>> result = await ec2_client.call("describe_instances")
    """
    return AWSClientWrapper(service_name, region, **kwargs)


async def execute_with_retry(
    operation: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential_backoff: bool = True,
) -> T:
    """Execute an AWS operation with retry logic for transient errors.

    This utility function implements exponential backoff retry logic for
    AWS operations that may fail due to transient errors like throttling.

    Args:
        operation: Async callable that performs the AWS operation.
        max_retries: Maximum number of retry attempts. Defaults to 3.
        base_delay: Base delay in seconds between retries. Defaults to 1.0.
        exponential_backoff: If True, use exponential backoff. Defaults to True.

    Returns:
        The result from the successful operation.

    Raises:
        The last exception encountered if all retries fail.

    Example:
        >>> async def describe_instances():
        ...     wrapper = create_aws_client("ec2")
        ...     return await wrapper.call("describe_instances")
        >>> result = await execute_with_retry(describe_instances, max_retries=5)
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await operation()

        except ThrottlingError as e:
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt if exponential_backoff else 1)
                logger.warning(
                    f"Throttling error on attempt {attempt + 1}/{max_retries + 1}, "
                    f"retrying in {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {max_retries + 1} attempts failed due to throttling")
                raise

        except (TimeoutError, ResourceNotFoundError) as e:
            # Don't retry these errors
            logger.error(f"Non-retryable error: {e}")
            raise

        except Exception as e:
            # Retry other errors
            last_exception = e
            if attempt < max_retries:
                delay = base_delay * (2**attempt if exponential_backoff else 1)
                logger.warning(
                    f"Error on attempt {attempt + 1}/{max_retries + 1}, "
                    f"retrying in {delay:.1f}s: {e}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {max_retries + 1} attempts failed")
                raise

    # Should never reach here, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected state in retry logic")
