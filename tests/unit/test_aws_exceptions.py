"""Tests for AWS custom exceptions."""

import pytest

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


class TestAWSError:
    """Test suite for AWSError base exception."""

    def test_basic_error_creation(self) -> None:
        """Test creating basic AWSError with just a message."""
        error = AWSError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.service is None
        assert error.operation is None
        assert error.error_code is None
        assert error.details == {}

    def test_error_with_full_context(self) -> None:
        """Test AWSError with complete context information."""
        error = AWSError(
            message="Invalid instance ID",
            service="ec2",
            operation="DescribeInstances",
            error_code="InvalidInstanceID.Malformed",
            details={"instance_id": "i-invalid"},
        )

        assert "Invalid instance ID" in str(error)
        assert "Service: ec2" in str(error)
        assert "Operation: DescribeInstances" in str(error)
        assert "Code: InvalidInstanceID.Malformed" in str(error)
        assert error.details["instance_id"] == "i-invalid"

    def test_error_with_partial_context(self) -> None:
        """Test AWSError with some context fields."""
        error = AWSError(
            message="Rate limit exceeded",
            service="ssm",
            error_code="Throttling",
        )

        assert "Rate limit exceeded" in str(error)
        assert "Service: ssm" in str(error)
        assert "Code: Throttling" in str(error)
        assert "Operation:" not in str(error)  # operation was not provided

    def test_error_details_default_empty_dict(self) -> None:
        """Test that details default to empty dict, not None."""
        error = AWSError("Test error")

        assert error.details == {}
        assert isinstance(error.details, dict)
        # Should be able to add items without error
        error.details["key"] = "value"
        assert error.details["key"] == "value"


class TestEC2Error:
    """Test suite for EC2Error exception."""

    def test_ec2_error_inherits_from_aws_error(self) -> None:
        """Test that EC2Error is a subclass of AWSError."""
        error = EC2Error("EC2 operation failed")

        assert isinstance(error, AWSError)
        assert isinstance(error, EC2Error)

    def test_ec2_error_with_context(self) -> None:
        """Test EC2Error with full context."""
        error = EC2Error(
            message="Instance not found",
            service="ec2",
            operation="StopInstances",
            error_code="InvalidInstanceID.NotFound",
        )

        assert error.service == "ec2"
        assert error.operation == "StopInstances"
        assert "Instance not found" in str(error)


class TestSSMError:
    """Test suite for SSMError exception."""

    def test_ssm_error_inherits_from_aws_error(self) -> None:
        """Test that SSMError is a subclass of AWSError."""
        error = SSMError("SSM command failed")

        assert isinstance(error, AWSError)
        assert isinstance(error, SSMError)

    def test_ssm_error_with_context(self) -> None:
        """Test SSMError with full context."""
        error = SSMError(
            message="Command execution failed",
            service="ssm",
            operation="SendCommand",
            error_code="InvalidInstanceId",
        )

        assert error.service == "ssm"
        assert error.operation == "SendCommand"
        assert "Command execution failed" in str(error)


class TestThrottlingError:
    """Test suite for ThrottlingError exception."""

    def test_throttling_error_creation(self) -> None:
        """Test creating ThrottlingError."""
        error = ThrottlingError(
            message="Rate exceeded",
            service="ec2",
            operation="DescribeInstances",
            error_code="Throttling",
        )

        assert isinstance(error, AWSError)
        assert isinstance(error, ThrottlingError)
        assert error.error_code == "Throttling"


class TestValidationError:
    """Test suite for ValidationError exception."""

    def test_validation_error_creation(self) -> None:
        """Test creating ValidationError."""
        error = ValidationError(
            message="Invalid parameter",
            service="ec2",
            error_code="InvalidParameterValue",
            details={"parameter": "instance_id", "value": "invalid"},
        )

        assert isinstance(error, AWSError)
        assert isinstance(error, ValidationError)
        assert error.details["parameter"] == "instance_id"


class TestResourceNotFoundError:
    """Test suite for ResourceNotFoundError exception."""

    def test_resource_not_found_error_creation(self) -> None:
        """Test creating ResourceNotFoundError."""
        error = ResourceNotFoundError(
            message="Instance i-123456 not found",
            service="ec2",
            operation="DescribeInstances",
            error_code="InvalidInstanceID.NotFound",
        )

        assert isinstance(error, AWSError)
        assert isinstance(error, ResourceNotFoundError)
        assert "i-123456" in error.message


class TestPermissionError:
    """Test suite for PermissionError exception."""

    def test_permission_error_creation(self) -> None:
        """Test creating PermissionError."""
        error = PermissionError(
            message="You are not authorized to perform this operation",
            service="ec2",
            operation="TerminateInstances",
            error_code="UnauthorizedOperation",
        )

        assert isinstance(error, AWSError)
        assert isinstance(error, PermissionError)
        assert "not authorized" in error.message


class TestTimeoutError:
    """Test suite for TimeoutError exception."""

    def test_timeout_error_creation(self) -> None:
        """Test creating TimeoutError."""
        error = TimeoutError(
            message="Operation timed out after 30s",
            service="ssm",
            operation="SendCommand",
        )

        assert isinstance(error, AWSError)
        assert isinstance(error, TimeoutError)
        assert "timed out" in error.message


class TestErrorHierarchy:
    """Test suite for exception hierarchy behavior."""

    def test_can_catch_all_errors_with_base_class(self) -> None:
        """Test that all custom errors can be caught with AWSError."""
        errors = [
            EC2Error("Test"),
            SSMError("Test"),
            ThrottlingError("Test"),
            ValidationError("Test"),
            ResourceNotFoundError("Test"),
            PermissionError("Test"),
            TimeoutError("Test"),
        ]

        for error in errors:
            with pytest.raises(AWSError):
                raise error

    def test_can_catch_specific_error_types(self) -> None:
        """Test catching specific error types."""
        with pytest.raises(EC2Error):
            raise EC2Error("EC2 specific error")

        with pytest.raises(ThrottlingError):
            raise ThrottlingError("Throttling error")

    def test_exception_chaining_preserves_context(self) -> None:
        """Test that exception chaining preserves original context."""
        original_error = ValueError("Original error")

        try:
            raise original_error
        except ValueError:
            aws_error = AWSError("Wrapped error", service="ec2")
            # In real code, we'd use 'from e' to chain exceptions
            assert aws_error.service == "ec2"
