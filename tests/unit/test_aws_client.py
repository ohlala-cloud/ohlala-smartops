"""Tests for AWS client wrapper with throttling and error handling."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from ohlala_smartops.aws.client import (
    AWSClientWrapper,
    create_aws_client,
    execute_with_retry,
)
from ohlala_smartops.aws.exceptions import (
    EC2Error,
    PermissionError,
    ResourceNotFoundError,
    SSMError,
    ThrottlingError,
    TimeoutError,
    ValidationError,
)


class TestAWSClientWrapper:
    """Test suite for AWSClientWrapper class."""

    @pytest.fixture
    def mock_boto_client(self) -> Mock:
        """Fixture providing a mocked boto3 client."""
        return Mock()

    @pytest.fixture
    def wrapper(self, mock_boto_client: Mock) -> AWSClientWrapper:
        """Fixture providing an AWSClientWrapper with mocked boto3 client."""
        with patch("boto3.client", return_value=mock_boto_client):
            return AWSClientWrapper("ec2", region="us-east-1")

    def test_initialization(self, mock_boto_client: Mock) -> None:
        """Test AWSClientWrapper initialization."""
        with patch("boto3.client", return_value=mock_boto_client) as mock_create:
            wrapper = AWSClientWrapper("ec2", region="us-west-2")

            assert wrapper.service_name == "ec2"
            assert wrapper.region == "us-west-2"
            mock_create.assert_called_once_with("ec2", region_name="us-west-2")

    def test_initialization_with_kwargs(self, mock_boto_client: Mock) -> None:
        """Test initialization with additional boto3 client kwargs."""
        with patch("boto3.client", return_value=mock_boto_client) as mock_create:
            wrapper = AWSClientWrapper(
                "ssm",
                region="eu-west-1",
                endpoint_url="https://custom-endpoint.example.com",
            )

            assert wrapper.service_name == "ssm"
            assert wrapper.region == "eu-west-1"
            mock_create.assert_called_once_with(
                "ssm",
                region_name="eu-west-1",
                endpoint_url="https://custom-endpoint.example.com",
            )

    @pytest.mark.asyncio
    async def test_successful_call(self, wrapper: AWSClientWrapper, mock_boto_client: Mock) -> None:
        """Test successful AWS API call."""
        # Mock the operation response
        expected_response = {"Reservations": [{"Instances": [{"InstanceId": "i-123"}]}]}
        mock_operation = Mock(return_value=expected_response)
        mock_boto_client.describe_instances = mock_operation

        # Execute the call
        result = await wrapper.call("describe_instances", InstanceIds=["i-123"])

        # Verify result and call
        assert result == expected_response
        mock_operation.assert_called_once_with(InstanceIds=["i-123"])

    @pytest.mark.asyncio
    async def test_call_with_throttling_integration(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test that calls integrate with global throttler."""
        expected_response = {"Status": "success"}
        mock_operation = Mock(return_value=expected_response)
        mock_boto_client.some_operation = mock_operation

        with patch("ohlala_smartops.aws.client.throttled_aws_call") as mock_throttle:
            # Mock the throttle context manager
            mock_throttle.return_value.__aenter__ = AsyncMock()
            mock_throttle.return_value.__aexit__ = AsyncMock()

            result = await wrapper.call("some_operation", Param="value")

            # Verify throttling was used
            mock_throttle.assert_called_once_with("ec2:some_operation")
            assert result == expected_response

    @pytest.mark.asyncio
    async def test_throttling_error_conversion(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test conversion of AWS throttling errors."""
        mock_operation = Mock(
            side_effect=ClientError(
                error_response={
                    "Error": {"Code": "Throttling", "Message": "Rate exceeded"},
                    "ResponseMetadata": {"HTTPStatusCode": 429, "RequestId": "req-123"},
                },
                operation_name="DescribeInstances",
            )
        )
        mock_boto_client.describe_instances = mock_operation

        with pytest.raises(ThrottlingError) as exc_info:
            await wrapper.call("describe_instances")

        error = exc_info.value
        assert error.error_code == "Throttling"
        assert error.service == "ec2"
        assert error.operation == "describe_instances"
        assert "Rate exceeded" in error.message

    @pytest.mark.asyncio
    async def test_permission_error_conversion(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test conversion of AWS permission errors."""
        mock_operation = Mock(
            side_effect=ClientError(
                error_response={
                    "Error": {
                        "Code": "UnauthorizedOperation",
                        "Message": "You are not authorized",
                    },
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                operation_name="TerminateInstances",
            )
        )
        mock_boto_client.terminate_instances = mock_operation

        with pytest.raises(PermissionError) as exc_info:
            await wrapper.call("terminate_instances", InstanceIds=["i-123"])

        error = exc_info.value
        assert error.error_code == "UnauthorizedOperation"
        assert "not authorized" in error.message

    @pytest.mark.asyncio
    async def test_resource_not_found_error_conversion(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test conversion of resource not found errors."""
        mock_operation = Mock(
            side_effect=ClientError(
                error_response={
                    "Error": {
                        "Code": "InvalidInstanceID.NotFound",
                        "Message": "Instance not found",
                    },
                    "ResponseMetadata": {},
                },
                operation_name="DescribeInstances",
            )
        )
        mock_boto_client.describe_instances = mock_operation

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await wrapper.call("describe_instances", InstanceIds=["i-invalid"])

        error = exc_info.value
        assert error.error_code == "InvalidInstanceID.NotFound"

    @pytest.mark.asyncio
    async def test_validation_error_conversion(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test conversion of validation errors."""
        mock_operation = Mock(
            side_effect=ClientError(
                error_response={
                    "Error": {
                        "Code": "InvalidParameterValue",
                        "Message": "Invalid parameter",
                    },
                    "ResponseMetadata": {},
                },
                operation_name="RunInstances",
            )
        )
        mock_boto_client.run_instances = mock_operation

        with pytest.raises(ValidationError) as exc_info:
            await wrapper.call("run_instances", ImageId="invalid")

        error = exc_info.value
        assert error.error_code == "InvalidParameterValue"

    @pytest.mark.asyncio
    async def test_timeout_error_conversion(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test conversion of timeout errors."""

        # Create a BotoCoreError subclass with timeout message
        class TimeoutBotoCoreError(BotoCoreError):
            def __str__(self) -> str:
                return "Connection timed out"

        mock_operation = Mock(side_effect=TimeoutBotoCoreError())
        mock_boto_client.describe_instances = mock_operation

        with pytest.raises(TimeoutError) as exc_info:
            await wrapper.call("describe_instances")

        error = exc_info.value
        assert error.service == "ec2"
        assert "timed out" in error.message.lower()

    @pytest.mark.asyncio
    async def test_generic_ec2_error_conversion(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test conversion of generic EC2 errors."""
        mock_operation = Mock(
            side_effect=ClientError(
                error_response={
                    "Error": {
                        "Code": "SomeOtherError",
                        "Message": "Something went wrong",
                    },
                    "ResponseMetadata": {},
                },
                operation_name="DescribeInstances",
            )
        )
        mock_boto_client.describe_instances = mock_operation

        with pytest.raises(EC2Error) as exc_info:
            await wrapper.call("describe_instances")

        error = exc_info.value
        assert error.error_code == "SomeOtherError"
        assert error.service == "ec2"

    @pytest.mark.asyncio
    async def test_ssm_service_error_class(self, mock_boto_client: Mock) -> None:
        """Test that SSM service uses SSMError class for non-specific errors."""
        with patch("boto3.client", return_value=mock_boto_client):
            wrapper = AWSClientWrapper("ssm", region="us-east-1")

        # Use a non-specific error code that will fall through to service-specific error
        mock_operation = Mock(
            side_effect=ClientError(
                error_response={
                    "Error": {"Code": "InternalServerError", "Message": "Internal error"},
                    "ResponseMetadata": {},
                },
                operation_name="SendCommand",
            )
        )
        mock_boto_client.send_command = mock_operation

        with pytest.raises(SSMError) as exc_info:
            await wrapper.call("send_command", InstanceIds=["i-123"])

        error = exc_info.value
        assert isinstance(error, SSMError)
        assert error.service == "ssm"
        assert error.error_code == "InternalServerError"

    @pytest.mark.asyncio
    async def test_error_details_populated(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test that error details are properly populated."""
        mock_operation = Mock(
            side_effect=ClientError(
                error_response={
                    "Error": {"Code": "Throttling", "Message": "Rate exceeded"},
                    "ResponseMetadata": {"HTTPStatusCode": 429, "RequestId": "req-abc-123"},
                },
                operation_name="DescribeInstances",
            )
        )
        mock_boto_client.describe_instances = mock_operation

        with pytest.raises(ThrottlingError) as exc_info:
            await wrapper.call("describe_instances")

        error = exc_info.value
        assert error.details["error_code"] == "Throttling"
        assert error.details["http_status"] == 429
        assert error.details["request_id"] == "req-abc-123"

    @pytest.mark.asyncio
    async def test_batch_calls_context_manager(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test batch_calls context manager."""
        mock_op1 = Mock(return_value={"Result": "1"})
        mock_op2 = Mock(return_value={"Result": "2"})
        mock_boto_client.operation1 = mock_op1
        mock_boto_client.operation2 = mock_op2

        async with wrapper.batch_calls() as batch_wrapper:
            result1 = await batch_wrapper.call("operation1")
            result2 = await batch_wrapper.call("operation2")

        assert result1 == {"Result": "1"}
        assert result2 == {"Result": "2"}
        mock_op1.assert_called_once()
        mock_op2.assert_called_once()

    def test_get_client_returns_underlying_boto_client(
        self, wrapper: AWSClientWrapper, mock_boto_client: Mock
    ) -> None:
        """Test get_client returns the underlying boto3 client."""
        client = wrapper.get_client()

        assert client is mock_boto_client


class TestCreateAWSClient:
    """Test suite for create_aws_client factory function."""

    def test_creates_wrapper_with_defaults(self) -> None:
        """Test factory function creates wrapper with default settings."""
        with patch("boto3.client"):
            wrapper = create_aws_client("ec2")

            assert isinstance(wrapper, AWSClientWrapper)
            assert wrapper.service_name == "ec2"
            assert wrapper.region is None

    def test_creates_wrapper_with_region(self) -> None:
        """Test factory function creates wrapper with specified region."""
        with patch("boto3.client"):
            wrapper = create_aws_client("ssm", region="eu-west-1")

            assert wrapper.service_name == "ssm"
            assert wrapper.region == "eu-west-1"

    def test_creates_wrapper_with_kwargs(self) -> None:
        """Test factory function passes additional kwargs to boto3."""
        with patch("boto3.client") as mock_create:
            create_aws_client("s3", region="us-west-2", endpoint_url="https://custom.example.com")

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["endpoint_url"] == "https://custom.example.com"


class TestExecuteWithRetry:
    """Test suite for execute_with_retry utility function."""

    @pytest.mark.asyncio
    async def test_successful_operation_no_retry(self) -> None:
        """Test that successful operations don't retry."""
        operation = AsyncMock(return_value="success")

        result = await execute_with_retry(operation, max_retries=3)

        assert result == "success"
        operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_throttling_error_retries(self) -> None:
        """Test that throttling errors trigger retries."""
        operation = AsyncMock(
            side_effect=[
                ThrottlingError("Rate exceeded"),
                ThrottlingError("Rate exceeded"),
                "success",
            ]
        )

        result = await execute_with_retry(operation, max_retries=3, base_delay=0.01)

        assert result == "success"
        assert operation.call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self) -> None:
        """Test that max retries limit is respected."""
        operation = AsyncMock(side_effect=ThrottlingError("Rate exceeded"))

        with pytest.raises(ThrottlingError):
            await execute_with_retry(operation, max_retries=2, base_delay=0.01)

        # Should be called 3 times: initial + 2 retries
        assert operation.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_errors_fail_immediately(self) -> None:
        """Test that non-retryable errors don't retry."""
        operation = AsyncMock(side_effect=ResourceNotFoundError("Not found"))

        with pytest.raises(ResourceNotFoundError):
            await execute_with_retry(operation, max_retries=3)

        # Should only be called once - no retries
        operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_error_fails_immediately(self) -> None:
        """Test that timeout errors don't retry."""
        operation = AsyncMock(side_effect=TimeoutError("Timed out"))

        with pytest.raises(TimeoutError):
            await execute_with_retry(operation, max_retries=3)

        operation.assert_called_once()

    @pytest.mark.asyncio
    async def test_exponential_backoff(self) -> None:
        """Test exponential backoff behavior."""
        operation = AsyncMock(
            side_effect=[
                ThrottlingError("Rate exceeded"),
                ThrottlingError("Rate exceeded"),
                "success",
            ]
        )

        start_time = asyncio.get_event_loop().time()
        result = await execute_with_retry(
            operation, max_retries=3, base_delay=0.1, exponential_backoff=True
        )
        elapsed = asyncio.get_event_loop().time() - start_time

        assert result == "success"
        # With exponential backoff: 0.1 + 0.2 = 0.3 seconds minimum
        # Allow some margin for execution time
        assert elapsed >= 0.25

    @pytest.mark.asyncio
    async def test_linear_backoff(self) -> None:
        """Test linear backoff behavior."""
        operation = AsyncMock(
            side_effect=[
                ThrottlingError("Rate exceeded"),
                ThrottlingError("Rate exceeded"),
                "success",
            ]
        )

        start_time = asyncio.get_event_loop().time()
        result = await execute_with_retry(
            operation, max_retries=3, base_delay=0.1, exponential_backoff=False
        )
        elapsed = asyncio.get_event_loop().time() - start_time

        assert result == "success"
        # With linear backoff: 0.1 + 0.1 = 0.2 seconds
        assert elapsed >= 0.15
        assert elapsed < 0.35  # Should be less than exponential

    @pytest.mark.asyncio
    async def test_generic_exception_retries(self) -> None:
        """Test that generic exceptions trigger retries."""
        operation = AsyncMock(
            side_effect=[
                EC2Error("Temporary error"),
                EC2Error("Temporary error"),
                "success",
            ]
        )

        result = await execute_with_retry(operation, max_retries=3, base_delay=0.01)

        assert result == "success"
        assert operation.call_count == 3

    @pytest.mark.asyncio
    async def test_custom_max_retries(self) -> None:
        """Test custom max_retries value."""
        operation = AsyncMock(side_effect=ThrottlingError("Rate exceeded"))

        with pytest.raises(ThrottlingError):
            await execute_with_retry(operation, max_retries=5, base_delay=0.01)

        # Should be called 6 times: initial + 5 retries
        assert operation.call_count == 6
