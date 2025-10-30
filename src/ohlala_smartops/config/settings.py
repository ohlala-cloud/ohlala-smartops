"""Application settings and configuration management.

This module provides Pydantic-based settings that load from environment
variables with validation and type safety. Settings follow the 12-factor
app methodology for configuration management.
"""

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ohlala_smartops.constants import (
    BEDROCK_ANTHROPIC_VERSION,
    BEDROCK_FALLBACK_MODEL,
    BEDROCK_MAX_TOKENS,
    BEDROCK_TEMPERATURE,
    get_bedrock_model_for_region,
)

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings can be overridden via environment variables. The class
    provides sensible defaults for development while enforcing required
    values for production deployment.

    Example:
        >>> settings = Settings()
        >>> print(settings.aws_region)
        'us-east-1'
        >>> print(settings.bedrock_model_id)
        'us.anthropic.claude-sonnet-4-5-20250929-v1:0'
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # AWS Configuration
    # =========================================================================

    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for deployment",
    )

    # =========================================================================
    # Microsoft Teams Bot Configuration
    # =========================================================================

    microsoft_app_id: str = Field(
        default="",
        description="Microsoft App ID for Teams Bot authentication",
    )

    microsoft_app_password: str = Field(
        default="",
        description="Microsoft App Password for Teams Bot authentication",
    )

    microsoft_app_type: Literal["SingleTenant", "MultiTenant", "UserAssignedMSI"] = Field(
        default="SingleTenant",
        description="Microsoft App Type",
    )

    microsoft_app_tenant_id: str = Field(
        default="",
        description="Microsoft Tenant ID (required for SingleTenant)",
    )

    # =========================================================================
    # Amazon Bedrock Configuration
    # =========================================================================

    bedrock_guardrail_enabled: bool = Field(
        default=False,
        description="Enable Bedrock Guardrails for content filtering",
    )

    bedrock_guardrail_id: str = Field(
        default="",
        description="Bedrock Guardrail ID (required if guardrails enabled)",
    )

    bedrock_guardrail_version: str = Field(
        default="1",
        description="Bedrock Guardrail Version",
    )

    bedrock_guardrail_version_override: str | None = Field(
        default=None,
        description="Override guardrail version for specific deployments",
    )

    bedrock_model_id: str | None = Field(
        default=None,
        description="Bedrock model ID (auto-selected based on region if not set)",
    )

    bedrock_max_tokens: int = Field(
        default=BEDROCK_MAX_TOKENS,
        ge=1,
        le=200000,
        description="Maximum tokens for Bedrock responses",
    )

    bedrock_temperature: float = Field(
        default=BEDROCK_TEMPERATURE,
        ge=0.0,
        le=1.0,
        description="Temperature for Bedrock model (0.0-1.0)",
    )

    bedrock_anthropic_version: str = Field(
        default=BEDROCK_ANTHROPIC_VERSION,
        description="Anthropic API version for Bedrock",
    )

    # =========================================================================
    # MCP (Model Context Protocol) Configuration
    # =========================================================================

    mcp_aws_api_url: str = Field(
        default="http://localhost:8080",
        description="MCP AWS API Server URL",
    )

    mcp_aws_knowledge_url: str = Field(
        default="https://knowledge-mcp.global.api.aws",
        description="MCP AWS Knowledge Server URL",
    )

    mcp_internal_api_key: str = Field(
        default="",
        description="MCP Internal API Key for service authentication",
    )

    mcp_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for MCP HTTP calls",
    )

    mcp_base_delay: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Base delay in seconds for MCP retry backoff",
    )

    mcp_max_delay: float = Field(
        default=16.0,
        ge=1.0,
        le=60.0,
        description="Maximum delay in seconds for MCP retry backoff",
    )

    mcp_backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=10.0,
        description="Exponential multiplier for MCP retry backoff",
    )

    # =========================================================================
    # Rate Limiting & Throttling Configuration
    # =========================================================================

    max_concurrent_aws_calls: int = Field(
        default=8,
        ge=1,
        le=100,
        description="Maximum concurrent AWS API calls",
    )

    aws_api_rate_limit: float = Field(
        default=15.0,
        ge=0.1,
        le=1000.0,
        description="Tokens per second for AWS API rate limiting",
    )

    aws_api_max_tokens: int = Field(
        default=30,
        ge=1,
        le=1000,
        description="Maximum tokens in AWS API rate limit bucket",
    )

    max_concurrent_bedrock_calls: int = Field(
        default=2,
        ge=1,
        le=20,
        description="Maximum concurrent Bedrock API calls",
    )

    bedrock_api_rate_limit: float = Field(
        default=0.5,
        ge=0.1,
        le=100.0,
        description="Tokens per second for Bedrock API rate limiting",
    )

    bedrock_api_max_tokens: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum tokens in Bedrock API rate limit bucket",
    )

    aws_circuit_breaker_enabled: bool = Field(
        default=False,
        description="Enable circuit breaker for AWS API calls",
    )

    aws_circuit_breaker_threshold: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Consecutive failures before circuit breaker opens",
    )

    aws_circuit_breaker_timeout: float = Field(
        default=10.0,
        ge=1.0,
        le=300.0,
        description="Seconds to keep circuit breaker open",
    )

    max_concurrent_requests: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Maximum concurrent HTTP requests to the bot",
    )

    # =========================================================================
    # Audit & Logging Configuration
    # =========================================================================

    enable_audit_logging: bool = Field(
        default=True,
        description="Enable audit logging for compliance and security",
    )

    audit_log_include_pii: bool = Field(
        default=False,
        description="Include PII in audit logs (requires proper controls)",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Application log level",
    )

    stack_name: str = Field(
        default="",
        description="CloudFormation stack name for metrics namespacing",
    )

    # =========================================================================
    # Application Configuration
    # =========================================================================

    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port for the FastAPI application",
    )

    @field_validator("bedrock_model_id", mode="after")
    @classmethod
    def set_bedrock_model_id(cls, v: str | None, info: ValidationInfo) -> str:
        """Auto-select Bedrock model based on AWS region if not explicitly set.

        Args:
            v: The bedrock_model_id value (may be None).
            info: ValidationInfo containing other field values.

        Returns:
            The validated or auto-selected model ID.
        """
        if v is not None:
            return v

        # Auto-select based on region
        aws_region = info.data.get("aws_region", "us-east-1")
        model_id = get_bedrock_model_for_region(aws_region)

        logger.info(f"Auto-selected Bedrock model for region {aws_region}: {model_id}")
        return model_id

    @model_validator(mode="after")
    def validate_teams_config(self) -> "Settings":
        """Validate that Teams configuration is complete if app_id is set.

        Returns:
            The validated Settings instance.

        Raises:
            ValueError: If app_id is set but password or tenant_id is missing.
        """
        if self.microsoft_app_id and not self.microsoft_app_password:
            raise ValueError("MICROSOFT_APP_PASSWORD is required when MICROSOFT_APP_ID is set")

        if (
            self.microsoft_app_id
            and self.microsoft_app_type == "SingleTenant"
            and not self.microsoft_app_tenant_id
        ):
            raise ValueError("MICROSOFT_APP_TENANT_ID is required for SingleTenant apps")

        return self

    @field_validator("bedrock_guardrail_id")
    @classmethod
    def validate_guardrail_config(cls, v: str, info: ValidationInfo) -> str:
        """Validate that guardrail ID is set if guardrails are enabled.

        Args:
            v: The bedrock_guardrail_id value.
            info: ValidationInfo containing other field values.

        Returns:
            The validated guardrail_id.

        Raises:
            ValueError: If guardrails are enabled but ID is not set.
        """
        if info.data.get("bedrock_guardrail_enabled", False) and not v:
            raise ValueError("BEDROCK_GUARDRAIL_ID is required when BEDROCK_GUARDRAIL_ENABLED=true")

        return v

    def get_effective_guardrail_version(self) -> str:
        """Get the effective guardrail version (considering override).

        Returns:
            The guardrail version to use (override takes precedence).
        """
        return self.bedrock_guardrail_version_override or self.bedrock_guardrail_version

    def get_bedrock_model_candidates(self) -> list[str]:
        """Get list of Bedrock model IDs to try in order.

        Returns a list with the primary region-optimized model and the
        global fallback model, with duplicates removed.

        Returns:
            List of model IDs to try in order of preference.
        """
        # bedrock_model_id is guaranteed to be str by validator
        assert self.bedrock_model_id is not None
        candidates: list[str] = [
            self.bedrock_model_id,
            BEDROCK_FALLBACK_MODEL,
        ]
        # Remove duplicates while preserving order
        return list(dict.fromkeys(candidates))


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Settings are cached to avoid repeated environment variable reads
    and validation. The cache is cleared on application restart.

    Returns:
        Validated Settings instance.

    Example:
        >>> settings = get_settings()
        >>> print(settings.aws_region)
        'us-east-1'
    """
    return Settings()
