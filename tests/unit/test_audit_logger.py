"""Unit tests for audit logger."""

import json
from unittest.mock import MagicMock, patch

import pytest

from ohlala_smartops.config.settings import Settings
from ohlala_smartops.utils.audit_logger import SENSITIVE_KEYS, AuditLogger, get_audit_logger


@pytest.fixture
def settings() -> Settings:
    """Create test settings with audit logging enabled."""
    return Settings(
        enable_audit_logging=True,
        audit_log_include_pii=False,
        aws_region="us-east-1",
        microsoft_app_id="test-app-id",
        microsoft_app_password="test-password",
        microsoft_app_tenant_id="test-tenant-id",
    )


@pytest.fixture
def settings_with_pii() -> Settings:
    """Create test settings with PII logging enabled."""
    return Settings(
        enable_audit_logging=True,
        audit_log_include_pii=True,
        aws_region="us-east-1",
        microsoft_app_id="test-app-id",
        microsoft_app_password="test-password",
        microsoft_app_tenant_id="test-tenant-id",
    )


@pytest.fixture
def settings_disabled() -> Settings:
    """Create test settings with audit logging disabled."""
    return Settings(
        enable_audit_logging=False,
        audit_log_include_pii=False,
        aws_region="us-east-1",
        microsoft_app_id="test-app-id",
        microsoft_app_password="test-password",
        microsoft_app_tenant_id="test-tenant-id",
    )


@pytest.fixture
def audit_logger(settings: Settings) -> AuditLogger:
    """Create audit logger instance for testing."""
    return AuditLogger(settings=settings)


class TestAuditLoggerInitialization:
    """Test audit logger initialization."""

    def test_init_with_settings(self, settings: Settings) -> None:
        """Test initialization with settings."""
        logger = AuditLogger(settings=settings)
        assert logger.enabled is True
        assert logger.include_pii is False
        assert logger.settings == settings

    def test_init_with_pii_enabled(self, settings_with_pii: Settings) -> None:
        """Test initialization with PII enabled."""
        logger = AuditLogger(settings=settings_with_pii)
        assert logger.enabled is True
        assert logger.include_pii is True

    def test_init_with_disabled(self, settings_disabled: Settings) -> None:
        """Test initialization with logging disabled."""
        logger = AuditLogger(settings=settings_disabled)
        assert logger.enabled is False
        assert logger.include_pii is False

    def test_init_without_settings(self) -> None:
        """Test initialization without explicit settings."""
        logger = AuditLogger()
        assert logger.settings is not None
        assert isinstance(logger.enabled, bool)


class TestCommandExecution:
    """Test command execution logging."""

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_command_execution_success(
        self, mock_logger: MagicMock, audit_logger: AuditLogger
    ) -> None:
        """Test logging successful command execution."""
        audit_logger.log_command_execution(
            user_id="user@example.com",
            user_name="John Doe",
            team_id="team-123",
            command="start_instance",
            arguments={"instance_id": "i-1234567890abcdef0"},
            result="instance started",
            success=True,
            execution_time_ms=1234.5,
        )

        # Verify info log was called
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]

        assert "AUDIT_COMMAND" in log_message
        assert "start_instance" in log_message
        assert "i-1234567890abcdef0" in log_message
        assert "user@example.com" in log_message
        assert "[REDACTED]" in log_message  # user_name should be redacted

        # Parse and verify JSON structure
        json_part = log_message.split("AUDIT_COMMAND: ")[1]
        log_data = json.loads(json_part)

        assert log_data["event_type"] == "command_execution"
        assert log_data["user"]["id"] == "user@example.com"
        assert log_data["user"]["name"] == "[REDACTED]"
        assert log_data["command"]["name"] == "start_instance"
        assert log_data["result"]["success"] is True
        assert log_data["result"]["execution_time_ms"] == 1234.5

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_command_execution_with_pii(
        self, mock_logger: MagicMock, settings_with_pii: Settings
    ) -> None:
        """Test logging with PII enabled."""
        logger = AuditLogger(settings=settings_with_pii)

        logger.log_command_execution(
            user_id="user@example.com",
            user_name="John Doe",
            team_id="team-123",
            command="stop_instance",
            arguments={"instance_id": "i-1234567890abcdef0"},
            result="instance stopped",
            success=True,
            execution_time_ms=2340.5,
        )

        log_message = mock_logger.info.call_args[0][0]
        json_part = log_message.split("AUDIT_COMMAND: ")[1]
        log_data = json.loads(json_part)

        # With PII enabled, user_name should not be redacted
        assert log_data["user"]["name"] == "John Doe"

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_command_execution_failure(
        self, mock_logger: MagicMock, audit_logger: AuditLogger
    ) -> None:
        """Test logging failed command execution."""
        audit_logger.log_command_execution(
            user_id="user@example.com",
            user_name="John Doe",
            team_id="team-123",
            command="terminate_instance",
            arguments={"instance_id": "i-1234567890abcdef0"},
            result="failed",
            success=False,
            execution_time_ms=500.0,
            error="Instance not found",
        )

        # Should use warning for failures
        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]

        assert "AUDIT_COMMAND_FAILED" in log_message
        json_part = log_message.split("AUDIT_COMMAND_FAILED: ")[1]
        log_data = json.loads(json_part)

        assert log_data["result"]["success"] is False
        assert log_data["result"]["error"] == "Instance not found"

    def test_log_command_execution_disabled(self, settings_disabled: Settings) -> None:
        """Test that logging is skipped when disabled."""
        logger = AuditLogger(settings=settings_disabled)

        with patch("ohlala_smartops.utils.audit_logger.logger") as mock_logger:
            logger.log_command_execution(
                user_id="user@example.com",
                user_name="John Doe",
                team_id="team-123",
                command="start_instance",
                arguments={},
                result="success",
                success=True,
                execution_time_ms=100.0,
            )

            # No logging should occur
            mock_logger.info.assert_not_called()
            mock_logger.warning.assert_not_called()


class TestMCPCall:
    """Test MCP call logging."""

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_mcp_call_success(self, mock_logger: MagicMock, audit_logger: AuditLogger) -> None:
        """Test logging successful MCP call."""
        audit_logger.log_mcp_call(
            tool_name="aws_ec2_describe_instances",
            arguments={"instance_ids": ["i-1234567890abcdef0"]},
            success=True,
            execution_time_ms=456.2,
        )

        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]

        assert "AUDIT_MCP" in log_message
        json_part = log_message.split("AUDIT_MCP: ")[1]
        log_data = json.loads(json_part)

        assert log_data["event_type"] == "mcp_tool_call"
        assert log_data["tool"] == "aws_ec2_describe_instances"
        assert log_data["success"] is True
        assert log_data["execution_time_ms"] == 456.2
        assert "error" not in log_data

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_mcp_call_with_error(
        self, mock_logger: MagicMock, audit_logger: AuditLogger
    ) -> None:
        """Test logging MCP call with error."""
        audit_logger.log_mcp_call(
            tool_name="aws_ec2_start_instances",
            arguments={"instance_ids": ["i-1234567890abcdef0"]},
            success=False,
            execution_time_ms=123.4,
            error="Rate limit exceeded",
        )

        # Failed MCP calls use warning level
        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        json_part = log_message.split("AUDIT_MCP_FAILED: ")[1]
        log_data = json.loads(json_part)

        assert log_data["success"] is False
        assert log_data["error"] == "Rate limit exceeded"


class TestBedrockCall:
    """Test Bedrock call logging."""

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_bedrock_call(self, mock_logger: MagicMock, audit_logger: AuditLogger) -> None:
        """Test logging Bedrock inference call."""
        audit_logger.log_bedrock_call(
            prompt_tokens=1500,
            completion_tokens=500,
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            guardrail_applied=True,
            execution_time_ms=3456.7,
        )

        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]

        assert "AUDIT_BEDROCK" in log_message
        json_part = log_message.split("AUDIT_BEDROCK: ")[1]
        log_data = json.loads(json_part)

        assert log_data["event_type"] == "bedrock_inference"
        assert log_data["model_id"] == "anthropic.claude-3-sonnet-20240229-v1:0"
        assert log_data["tokens"]["prompt"] == 1500
        assert log_data["tokens"]["completion"] == 500
        assert log_data["tokens"]["total"] == 2000
        assert log_data["guardrail_applied"] is True
        assert log_data["execution_time_ms"] == 3456.7


class TestSecurityEvent:
    """Test security event logging."""

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_security_event_info(
        self, mock_logger: MagicMock, audit_logger: AuditLogger
    ) -> None:
        """Test logging info-level security event."""
        audit_logger.log_security_event(
            event_name="successful_authentication",
            details={"user_id": "user@example.com", "method": "oauth"},
            severity="info",
        )

        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]

        assert "AUDIT_SECURITY" in log_message
        json_part = log_message.split("AUDIT_SECURITY: ")[1]
        log_data = json.loads(json_part)

        assert log_data["event_type"] == "security_event"
        assert log_data["event_name"] == "successful_authentication"
        assert log_data["severity"] == "info"

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_security_event_warning(
        self, mock_logger: MagicMock, audit_logger: AuditLogger
    ) -> None:
        """Test logging warning-level security event."""
        audit_logger.log_security_event(
            event_name="dangerous_command_blocked",
            details={"command": "rm -rf /", "user_id": "user@example.com"},
            severity="warning",
        )

        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        assert "AUDIT_SECURITY" in log_message

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_security_event_critical(
        self, mock_logger: MagicMock, audit_logger: AuditLogger
    ) -> None:
        """Test logging critical-level security event."""
        audit_logger.log_security_event(
            event_name="multiple_failed_auth_attempts",
            details={"user_id": "user@example.com", "attempts": 5},
            severity="critical",
        )

        mock_logger.critical.assert_called_once()
        log_message = mock_logger.critical.call_args[0][0]
        assert "AUDIT_SECURITY" in log_message


class TestWriteOperation:
    """Test write operation logging."""

    @patch("ohlala_smartops.utils.audit_logger.logger")
    def test_log_write_operation_confirmed(
        self, mock_logger: MagicMock, audit_logger: AuditLogger
    ) -> None:
        """Test logging confirmed write operation."""
        audit_logger.log_write_operation(
            operation="stop",
            resource_type="ec2_instance",
            resource_id="i-1234567890abcdef0",
            user_id="user@example.com",
            changes={"state": "running -> stopping"},
            confirmed=True,
        )

        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]

        assert "AUDIT_WRITE" in log_message
        json_part = log_message.split("AUDIT_WRITE: ")[1]
        log_data = json.loads(json_part)

        assert log_data["event_type"] == "write_operation"
        assert log_data["operation"] == "stop"
        assert log_data["resource"]["type"] == "ec2_instance"
        assert log_data["resource"]["id"] == "i-1234567890abcdef0"
        assert log_data["confirmed"] is True


class TestSanitization:
    """Test argument sanitization."""

    def test_sanitize_sensitive_keys(self, audit_logger: AuditLogger) -> None:
        """Test that sensitive keys are redacted."""
        arguments = {
            "instance_id": "i-1234567890abcdef0",
            "password": "super-secret",
            "api_token": "secret-token",
            "secret_key": "secret",
            "region": "us-east-1",  # Non-sensitive key
        }

        sanitized = audit_logger._sanitize_arguments(arguments)

        assert sanitized["instance_id"] == "i-1234567890abcdef0"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_token"] == "[REDACTED]"
        assert sanitized["secret_key"] == "[REDACTED]"
        assert sanitized["region"] == "us-east-1"

    def test_sanitize_nested_dict(self, audit_logger: AuditLogger) -> None:
        """Test sanitization of nested dictionaries."""
        arguments = {
            "settings": {
                "instance_id": "i-1234567890abcdef0",
                "user_info": {"name": "John Doe", "email": "john@example.com"},
                "password": "should-be-redacted",
            }
        }

        sanitized = audit_logger._sanitize_arguments(arguments)

        # Verify nested structure is preserved and sensitive data is redacted
        assert isinstance(sanitized["settings"], dict)
        assert sanitized["settings"]["instance_id"] == "i-1234567890abcdef0"
        # user_info should be recursively sanitized (not a sensitive key)
        assert isinstance(sanitized["settings"]["user_info"], dict)
        assert sanitized["settings"]["user_info"]["name"] == "John Doe"
        assert sanitized["settings"]["user_info"]["email"] == "john@example.com"
        # password should be redacted
        assert sanitized["settings"]["password"] == "[REDACTED]"

    def test_sanitize_list_of_dicts(self, audit_logger: AuditLogger) -> None:
        """Test sanitization of list containing dictionaries."""
        arguments = {
            "servers": [
                {"host": "server1", "password": "secret1"},
                {"host": "server2", "api_key": "secret2"},
            ]
        }

        sanitized = audit_logger._sanitize_arguments(arguments)

        assert sanitized["servers"][0]["host"] == "server1"
        assert sanitized["servers"][0]["password"] == "[REDACTED]"
        assert sanitized["servers"][1]["host"] == "server2"
        assert sanitized["servers"][1]["api_key"] == "[REDACTED]"

    def test_sanitize_with_pii_enabled(self, settings_with_pii: Settings) -> None:
        """Test that sanitization is skipped when PII is enabled."""
        logger = AuditLogger(settings=settings_with_pii)

        arguments = {"password": "should-not-be-redacted", "key": "also-visible"}

        sanitized = logger._sanitize_arguments(arguments)

        # With PII enabled, nothing should be redacted
        assert sanitized["password"] == "should-not-be-redacted"
        assert sanitized["key"] == "also-visible"

    def test_sensitive_keys_coverage(self) -> None:
        """Test that SENSITIVE_KEYS constant covers expected patterns."""
        assert "password" in SENSITIVE_KEYS
        assert "token" in SENSITIVE_KEYS
        assert "secret" in SENSITIVE_KEYS
        assert "key" in SENSITIVE_KEYS
        assert "credential" in SENSITIVE_KEYS
        assert "auth" in SENSITIVE_KEYS


class TestGetAuditLogger:
    """Test get_audit_logger factory function."""

    def test_get_audit_logger_singleton(self) -> None:
        """Test that get_audit_logger returns cached instance."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()

        # Should return same instance
        assert logger1 is logger2

    def test_get_audit_logger_returns_instance(self) -> None:
        """Test get_audit_logger returns AuditLogger instance."""
        logger = get_audit_logger()

        assert isinstance(logger, AuditLogger)
        assert isinstance(logger.settings, Settings)
