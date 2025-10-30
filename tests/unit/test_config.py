"""Tests for the configuration module."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from ohlala_smartops.config import Settings, get_settings
from ohlala_smartops.constants import BEDROCK_FALLBACK_MODEL


class TestSettingsDefaults:
    """Tests for Settings default values."""

    def test_aws_region_default(self) -> None:
        """Test that AWS region has a default value."""
        settings = Settings()
        assert settings.aws_region == "us-east-1"

    def test_port_default(self) -> None:
        """Test that port has a default value."""
        settings = Settings()
        assert settings.port == 8000

    def test_log_level_default(self) -> None:
        """Test that log level has a default value."""
        settings = Settings()
        assert settings.log_level == "INFO"

    def test_enable_audit_logging_default(self) -> None:
        """Test that audit logging is enabled by default."""
        settings = Settings()
        assert settings.enable_audit_logging is True

    def test_audit_log_include_pii_default(self) -> None:
        """Test that PII is not included in audit logs by default."""
        settings = Settings()
        assert settings.audit_log_include_pii is False


class TestBedrockConfiguration:
    """Tests for Bedrock-related configuration."""

    def test_bedrock_model_id_auto_selected_for_us_east_1(self) -> None:
        """Test that Bedrock model is auto-selected for us-east-1."""
        settings = Settings(aws_region="us-east-1")
        assert settings.bedrock_model_id == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_bedrock_model_id_auto_selected_for_eu_west_1(self) -> None:
        """Test that Bedrock model is auto-selected for eu-west-1."""
        settings = Settings(aws_region="eu-west-1")
        assert settings.bedrock_model_id == "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_bedrock_model_id_can_be_explicitly_set(self) -> None:
        """Test that Bedrock model ID can be explicitly overridden."""
        custom_model = "custom-model-id"
        settings = Settings(bedrock_model_id=custom_model)
        assert settings.bedrock_model_id == custom_model

    def test_bedrock_max_tokens_validation(self) -> None:
        """Test that max tokens is validated."""
        # Should accept valid value
        settings = Settings(bedrock_max_tokens=1000)
        assert settings.bedrock_max_tokens == 1000

        # Should reject value too low
        with pytest.raises(ValidationError) as exc_info:
            Settings(bedrock_max_tokens=0)
        assert "greater than or equal to 1" in str(exc_info.value)

        # Should reject value too high
        with pytest.raises(ValidationError) as exc_info:
            Settings(bedrock_max_tokens=300000)
        assert "less than or equal to 200000" in str(exc_info.value)

    def test_bedrock_temperature_validation(self) -> None:
        """Test that temperature is validated."""
        # Should accept valid values
        settings = Settings(bedrock_temperature=0.5)
        assert settings.bedrock_temperature == 0.5

        # Should reject value below 0
        with pytest.raises(ValidationError) as exc_info:
            Settings(bedrock_temperature=-0.1)
        assert "greater than or equal to 0" in str(exc_info.value)

        # Should reject value above 1
        with pytest.raises(ValidationError) as exc_info:
            Settings(bedrock_temperature=1.5)
        assert "less than or equal to 1" in str(exc_info.value)

    def test_bedrock_guardrail_defaults(self) -> None:
        """Test Bedrock guardrail default settings."""
        settings = Settings()
        assert settings.bedrock_guardrail_enabled is False
        assert settings.bedrock_guardrail_version == "1"

    def test_bedrock_guardrail_validation_requires_id(self) -> None:
        """Test that enabling guardrails requires an ID."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(bedrock_guardrail_enabled=True, bedrock_guardrail_id="")
        assert "BEDROCK_GUARDRAIL_ID is required" in str(exc_info.value)

    def test_bedrock_guardrail_validation_passes_with_id(self) -> None:
        """Test that guardrails can be enabled with a valid ID."""
        settings = Settings(
            bedrock_guardrail_enabled=True, bedrock_guardrail_id="test-guardrail-id"
        )
        assert settings.bedrock_guardrail_enabled is True
        assert settings.bedrock_guardrail_id == "test-guardrail-id"


class TestMCPConfiguration:
    """Tests for MCP-related configuration."""

    def test_mcp_defaults(self) -> None:
        """Test MCP configuration defaults."""
        settings = Settings()
        assert settings.mcp_aws_api_url == "http://localhost:8080"
        assert settings.mcp_aws_knowledge_url == "https://knowledge-mcp.global.api.aws"
        assert settings.mcp_max_retries == 3
        assert settings.mcp_base_delay == 1.0
        assert settings.mcp_max_delay == 16.0
        assert settings.mcp_backoff_multiplier == 2.0

    def test_mcp_retry_validation(self) -> None:
        """Test that MCP retry parameters are validated."""
        # Should accept valid values
        settings = Settings(mcp_max_retries=5)
        assert settings.mcp_max_retries == 5

        # Should reject negative retries
        with pytest.raises(ValidationError):
            Settings(mcp_max_retries=-1)

        # Should reject excessive retries
        with pytest.raises(ValidationError):
            Settings(mcp_max_retries=20)


class TestRateLimitingConfiguration:
    """Tests for rate limiting configuration."""

    def test_aws_rate_limiting_defaults(self) -> None:
        """Test AWS rate limiting defaults."""
        settings = Settings()
        assert settings.max_concurrent_aws_calls == 8
        assert settings.aws_api_rate_limit == 15.0
        assert settings.aws_api_max_tokens == 30

    def test_bedrock_rate_limiting_defaults(self) -> None:
        """Test Bedrock rate limiting defaults."""
        settings = Settings()
        assert settings.max_concurrent_bedrock_calls == 2
        assert settings.bedrock_api_rate_limit == 0.5
        assert settings.bedrock_api_max_tokens == 5

    def test_circuit_breaker_defaults(self) -> None:
        """Test circuit breaker defaults."""
        settings = Settings()
        assert settings.aws_circuit_breaker_enabled is False
        assert settings.aws_circuit_breaker_threshold == 100
        assert settings.aws_circuit_breaker_timeout == 10.0

    def test_max_concurrent_requests_validation(self) -> None:
        """Test that concurrent request limits are validated."""
        # Should accept valid value
        settings = Settings(max_concurrent_requests=50)
        assert settings.max_concurrent_requests == 50

        # Should reject value too low
        with pytest.raises(ValidationError):
            Settings(max_concurrent_requests=0)


class TestMicrosoftTeamsConfiguration:
    """Tests for Microsoft Teams Bot configuration."""

    def test_teams_defaults(self) -> None:
        """Test Teams configuration defaults."""
        settings = Settings()
        assert settings.microsoft_app_id == ""
        assert settings.microsoft_app_password == ""
        assert settings.microsoft_app_type == "SingleTenant"
        assert settings.microsoft_app_tenant_id == ""

    def test_teams_app_type_validation(self) -> None:
        """Test that app type is validated."""
        # Should accept valid types
        settings = Settings(microsoft_app_type="SingleTenant")
        assert settings.microsoft_app_type == "SingleTenant"

        settings = Settings(microsoft_app_type="MultiTenant")
        assert settings.microsoft_app_type == "MultiTenant"

        settings = Settings(microsoft_app_type="UserAssignedMSI")
        assert settings.microsoft_app_type == "UserAssignedMSI"

        # Should reject invalid types
        with pytest.raises(ValidationError):
            Settings(microsoft_app_type="InvalidType")  # type: ignore[arg-type]

    def test_teams_validation_requires_password_with_app_id(self) -> None:
        """Test that app password is required when app ID is set."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(microsoft_app_id="test-app-id", microsoft_app_password="")
        assert "MICROSOFT_APP_PASSWORD is required" in str(exc_info.value)

    def test_teams_validation_passes_with_both_id_and_password(self) -> None:
        """Test that validation passes with both app ID and password."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                microsoft_app_id="test-app-id",
                microsoft_app_password="test-password",
                microsoft_app_tenant_id="test-tenant-id",
            )
            assert settings.microsoft_app_id == "test-app-id"
            assert settings.microsoft_app_password == "test-password"

    def test_single_tenant_requires_tenant_id(self) -> None:
        """Test that SingleTenant apps require tenant ID."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(
                    microsoft_app_id="test-app-id",
                    microsoft_app_password="test-password",
                    microsoft_app_type="SingleTenant",
                    microsoft_app_tenant_id="",
                )
            assert "MICROSOFT_APP_TENANT_ID is required" in str(exc_info.value)

    def test_multi_tenant_does_not_require_tenant_id(self) -> None:
        """Test that MultiTenant apps don't require tenant ID."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                microsoft_app_id="test-app-id",
                microsoft_app_password="test-password",
                microsoft_app_type="MultiTenant",
                microsoft_app_tenant_id="",
            )
            assert settings.microsoft_app_type == "MultiTenant"


class TestPortValidation:
    """Tests for port configuration validation."""

    def test_port_within_valid_range(self) -> None:
        """Test that ports within valid range are accepted."""
        settings = Settings(port=3000)
        assert settings.port == 3000

        settings = Settings(port=65535)
        assert settings.port == 65535

    def test_port_below_range_rejected(self) -> None:
        """Test that ports below valid range are rejected."""
        with pytest.raises(ValidationError):
            Settings(port=0)

    def test_port_above_range_rejected(self) -> None:
        """Test that ports above valid range are rejected."""
        with pytest.raises(ValidationError):
            Settings(port=70000)


class TestSettingsHelperMethods:
    """Tests for Settings helper methods."""

    def test_get_effective_guardrail_version_without_override(self) -> None:
        """Test getting guardrail version when no override is set."""
        settings = Settings(bedrock_guardrail_version="2")
        assert settings.get_effective_guardrail_version() == "2"

    def test_get_effective_guardrail_version_with_override(self) -> None:
        """Test that override takes precedence."""
        settings = Settings(bedrock_guardrail_version="2", bedrock_guardrail_version_override="3")
        assert settings.get_effective_guardrail_version() == "3"

    def test_get_bedrock_model_candidates(self) -> None:
        """Test getting list of model candidates."""
        settings = Settings(aws_region="us-east-1")
        candidates = settings.get_bedrock_model_candidates()

        assert isinstance(candidates, list)
        assert len(candidates) >= 1
        assert "us.anthropic.claude-sonnet-4-5-20250929-v1:0" in candidates

    def test_get_bedrock_model_candidates_removes_duplicates(self) -> None:
        """Test that duplicate models are removed from candidates."""
        settings = Settings(bedrock_model_id=BEDROCK_FALLBACK_MODEL)
        candidates = settings.get_bedrock_model_candidates()

        # Should only contain fallback once, not twice
        assert candidates.count(BEDROCK_FALLBACK_MODEL) == 1

    def test_get_bedrock_model_candidates_preserves_order(self) -> None:
        """Test that primary model comes before fallback."""
        settings = Settings(aws_region="us-east-1")
        candidates = settings.get_bedrock_model_candidates()

        # Primary should be first
        assert candidates[0] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        # Fallback should be last
        assert candidates[-1] == BEDROCK_FALLBACK_MODEL


class TestEnvironmentVariableLoading:
    """Tests for loading settings from environment variables."""

    def test_loads_from_environment(self) -> None:
        """Test that settings are loaded from environment variables."""
        with patch.dict(os.environ, {"AWS_REGION": "eu-central-1"}):
            settings = Settings()
            assert settings.aws_region == "eu-central-1"

    def test_environment_overrides_defaults(self) -> None:
        """Test that environment variables override defaults."""
        with patch.dict(os.environ, {"PORT": "3000", "LOG_LEVEL": "DEBUG"}):
            settings = Settings()
            assert settings.port == 3000
            assert settings.log_level == "DEBUG"

    def test_case_insensitive_environment_variables(self) -> None:
        """Test that environment variable names are case insensitive."""
        with patch.dict(os.environ, {"aws_region": "ap-northeast-1"}):
            settings = Settings()
            assert settings.aws_region == "ap-northeast-1"


class TestGetSettingsCaching:
    """Tests for the get_settings caching function."""

    def test_get_settings_returns_settings_instance(self) -> None:
        """Test that get_settings returns a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_is_cached(self) -> None:
        """Test that get_settings returns the same instance on repeated calls."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_with_environment_changes(self) -> None:
        """Test behavior when environment changes (cache persists)."""
        # Clear the cache first
        get_settings.cache_clear()

        with patch.dict(os.environ, {"AWS_REGION": "us-west-2"}):
            settings1 = get_settings()
            assert settings1.aws_region == "us-west-2"

        # Even after env change, cache returns same instance
        with patch.dict(os.environ, {"AWS_REGION": "eu-west-1"}):
            settings2 = get_settings()
            assert settings2 is settings1
            assert settings2.aws_region == "us-west-2"  # Still the cached value


class TestLogLevelValidation:
    """Tests for log level validation."""

    def test_valid_log_levels(self) -> None:
        """Test that all standard log levels are accepted."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(log_level=level)  # type: ignore[arg-type]
            assert settings.log_level == level

    def test_invalid_log_level_rejected(self) -> None:
        """Test that invalid log levels are rejected."""
        with pytest.raises(ValidationError):
            Settings(log_level="INVALID")  # type: ignore[arg-type]


class TestSettingsImmutability:
    """Tests to ensure settings follow Pydantic immutability patterns."""

    def test_settings_model_config(self) -> None:
        """Test that settings has correct model configuration."""
        settings = Settings()
        config = settings.model_config

        assert config["env_file"] == ".env"
        assert config["case_sensitive"] is False
        assert config["extra"] == "ignore"
