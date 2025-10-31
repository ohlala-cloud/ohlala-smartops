"""Tests for Claude Sonnet 4 model selection utilities."""

import logging

import pytest

from ohlala_smartops.ai.model_selector import (
    ModelSelector,
    get_claude_sonnet4_models_for_region,
    validate_claude_sonnet4_region,
)
from ohlala_smartops.constants import (
    BEDROCK_FALLBACK_MODEL,
    BEDROCK_PRIMARY_MODEL_BY_REGION,
)


class TestModelSelector:
    """Test suite for ModelSelector class."""

    def test_initialization_default(self) -> None:
        """Test ModelSelector initialization with default region."""
        selector = ModelSelector()

        assert selector.aws_region == "us-east-1"
        assert selector.fallback_model == BEDROCK_FALLBACK_MODEL
        assert selector.model_candidates == BEDROCK_PRIMARY_MODEL_BY_REGION

    def test_initialization_custom_region(self) -> None:
        """Test ModelSelector initialization with custom region."""
        selector = ModelSelector("eu-west-3")

        assert selector.aws_region == "eu-west-3"
        assert selector.fallback_model == BEDROCK_FALLBACK_MODEL

    def test_get_optimized_model_list_eu_region(self) -> None:
        """Test getting optimized model list for EU region."""
        selector = ModelSelector("eu-west-1")
        models = selector.get_optimized_model_list()

        # Should return EU regional profile + global fallback
        assert len(models) == 2
        assert models[0] == "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
        assert models[1] == BEDROCK_FALLBACK_MODEL

    def test_get_optimized_model_list_us_region(self) -> None:
        """Test getting optimized model list for US region."""
        selector = ModelSelector("us-east-1")
        models = selector.get_optimized_model_list()

        # Should return US regional profile + global fallback
        assert len(models) == 2
        assert models[0] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        assert models[1] == BEDROCK_FALLBACK_MODEL

    def test_get_optimized_model_list_apac_region(self) -> None:
        """Test getting optimized model list for APAC region."""
        selector = ModelSelector("ap-northeast-1")
        models = selector.get_optimized_model_list()

        # Should return APAC regional profile + global fallback
        assert len(models) == 2
        assert models[0] == "apac.anthropic.claude-sonnet-4-5-20250929-v1:0"
        assert models[1] == BEDROCK_FALLBACK_MODEL

    def test_get_optimized_model_list_unknown_region(self) -> None:
        """Test getting optimized model list for unknown region."""
        selector = ModelSelector("unknown-region-1")
        models = selector.get_optimized_model_list()

        # Should return only global fallback
        assert len(models) == 1
        assert models[0] == BEDROCK_FALLBACK_MODEL

    def test_get_optimized_model_list_override_region(self) -> None:
        """Test getting optimized model list with region override."""
        selector = ModelSelector("us-east-1")
        models = selector.get_optimized_model_list("eu-west-2")

        # Should use the override region (EU), not the instance region (US)
        assert models[0].startswith("eu.")

    def test_get_optimized_model_list_no_duplicates(self) -> None:
        """Test that optimized model list doesn't contain duplicates."""
        selector = ModelSelector("unknown-region")
        models = selector.get_optimized_model_list()

        # When primary is already global, should only return it once
        assert len(models) == len(set(models))
        assert models.count(BEDROCK_FALLBACK_MODEL) == 1

    def test_get_best_model_for_region_eu(self) -> None:
        """Test getting best model for EU region."""
        selector = ModelSelector("eu-west-3")
        best_model = selector.get_best_model_for_region()

        assert best_model == "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_get_best_model_for_region_us(self) -> None:
        """Test getting best model for US region."""
        selector = ModelSelector("us-west-2")
        best_model = selector.get_best_model_for_region()

        assert best_model == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_get_best_model_for_region_apac(self) -> None:
        """Test getting best model for APAC region."""
        selector = ModelSelector("ap-southeast-1")
        best_model = selector.get_best_model_for_region()

        assert best_model == "apac.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_get_best_model_for_region_unknown(self) -> None:
        """Test getting best model for unknown region."""
        selector = ModelSelector("unknown-region")
        best_model = selector.get_best_model_for_region()

        assert best_model == BEDROCK_FALLBACK_MODEL

    def test_get_best_model_for_region_override(self) -> None:
        """Test getting best model with region override."""
        selector = ModelSelector("us-east-1")
        best_model = selector.get_best_model_for_region("eu-west-1")

        # Should use override region
        assert best_model.startswith("eu.")

    def test_is_inference_profile_global(self) -> None:
        """Test detection of global inference profile."""
        selector = ModelSelector()

        assert (
            selector.is_inference_profile("global.anthropic.claude-sonnet-4-5-20250929-v1:0")
            is True
        )

    def test_is_inference_profile_regional_us(self) -> None:
        """Test detection of US regional inference profile."""
        selector = ModelSelector()

        assert selector.is_inference_profile("us.anthropic.claude-sonnet-4-5-20250929-v1:0") is True

    def test_is_inference_profile_regional_eu(self) -> None:
        """Test detection of EU regional inference profile."""
        selector = ModelSelector()

        assert selector.is_inference_profile("eu.anthropic.claude-sonnet-4-5-20250929-v1:0") is True

    def test_is_inference_profile_regional_apac(self) -> None:
        """Test detection of APAC regional inference profile."""
        selector = ModelSelector()

        assert (
            selector.is_inference_profile("apac.anthropic.claude-sonnet-4-5-20250929-v1:0") is True
        )

    def test_is_inference_profile_direct_model(self) -> None:
        """Test detection of direct model (not inference profile)."""
        selector = ModelSelector()

        assert selector.is_inference_profile("anthropic.claude-sonnet-4-5-20250929-v1:0") is False

    def test_get_model_category_global(self) -> None:
        """Test model category detection for global profile."""
        selector = ModelSelector()

        category = selector.get_model_category("global.anthropic.claude-sonnet-4-5-20250929-v1:0")
        assert category == "global"

    def test_get_model_category_regional_us(self) -> None:
        """Test model category detection for US regional profile."""
        selector = ModelSelector()

        category = selector.get_model_category("us.anthropic.claude-sonnet-4-5-20250929-v1:0")
        assert category == "regional"

    def test_get_model_category_regional_eu(self) -> None:
        """Test model category detection for EU regional profile."""
        selector = ModelSelector()

        category = selector.get_model_category("eu.anthropic.claude-sonnet-4-5-20250929-v1:0")
        assert category == "regional"

    def test_get_model_category_regional_apac(self) -> None:
        """Test model category detection for APAC regional profile."""
        selector = ModelSelector()

        category = selector.get_model_category("apac.anthropic.claude-sonnet-4-5-20250929-v1:0")
        assert category == "regional"

    def test_get_model_category_direct(self) -> None:
        """Test model category detection for direct model."""
        selector = ModelSelector()

        category = selector.get_model_category("anthropic.claude-sonnet-4-5-20250929-v1:0")
        assert category == "direct"

    def test_get_regional_fallback_strategy_eu(self) -> None:
        """Test fallback strategy for EU region."""
        selector = ModelSelector("eu-west-1")
        strategy = selector.get_regional_fallback_strategy()

        # Should have 2 entries: regional + global
        assert len(strategy) == 2
        assert strategy[0][0].startswith("eu.")
        assert strategy[0][1] == "regional"
        assert strategy[1][0].startswith("global.")
        assert strategy[1][1] == "global"

    def test_get_regional_fallback_strategy_us(self) -> None:
        """Test fallback strategy for US region."""
        selector = ModelSelector("us-east-1")
        strategy = selector.get_regional_fallback_strategy()

        # Should have 2 entries: regional + global
        assert len(strategy) == 2
        assert strategy[0][0].startswith("us.")
        assert strategy[0][1] == "regional"
        assert strategy[1][1] == "global"

    def test_get_regional_fallback_strategy_unknown_region(self) -> None:
        """Test fallback strategy for unknown region."""
        selector = ModelSelector("unknown-region")
        strategy = selector.get_regional_fallback_strategy()

        # Should only have global fallback
        assert len(strategy) == 1
        assert strategy[0][1] == "global"

    def test_get_regional_fallback_strategy_override(self) -> None:
        """Test fallback strategy with region override."""
        selector = ModelSelector("us-east-1")
        strategy = selector.get_regional_fallback_strategy("eu-west-2")

        # Should use override region (EU)
        assert strategy[0][0].startswith("eu.")

    def test_get_inference_profile_arn_patterns(self) -> None:
        """Test generation of IAM ARN patterns."""
        selector = ModelSelector()
        patterns = selector.get_inference_profile_arn_patterns()

        # Should have multiple patterns
        assert len(patterns) > 0
        assert all(isinstance(p, str) for p in patterns)
        assert all("arn:aws:bedrock" in p for p in patterns)

    def test_get_inference_profile_arn_patterns_coverage(self) -> None:
        """Test that ARN patterns cover all profile types."""
        selector = ModelSelector()
        patterns = selector.get_inference_profile_arn_patterns()

        # Should include patterns for all regional prefixes
        patterns_str = " ".join(patterns)
        assert "global.anthropic.claude-sonnet-4" in patterns_str
        assert "us.anthropic.claude-sonnet-4" in patterns_str
        assert "eu.anthropic.claude-sonnet-4" in patterns_str
        assert "apac.anthropic.claude-sonnet-4" in patterns_str

        # Should include both direct models and inference profiles
        assert "foundation-model" in patterns_str
        assert "inference-profile" in patterns_str

    def test_validate_region_support_eu(self) -> None:
        """Test region validation for EU region."""
        selector = ModelSelector()
        is_supported, description = selector.validate_region_support("eu-west-1")

        assert is_supported is True
        assert "eu-west-1" in description
        assert "regional" in description.lower()

    def test_validate_region_support_us(self) -> None:
        """Test region validation for US region."""
        selector = ModelSelector()
        is_supported, description = selector.validate_region_support("us-west-2")

        assert is_supported is True
        assert "us-west-2" in description
        assert "regional" in description.lower()

    def test_validate_region_support_unknown(self) -> None:
        """Test region validation for unknown region."""
        selector = ModelSelector()
        is_supported, description = selector.validate_region_support("unknown-region")

        assert is_supported is True  # Still supported via global
        assert "unknown-region" in description
        assert "global" in description.lower()

    def test_get_error_guidance_invalid_model(self) -> None:
        """Test error guidance for invalid model identifier."""
        selector = ModelSelector("us-east-1")
        guidance = selector.get_error_guidance("The provided model identifier is invalid")

        assert "us-east-1" in guidance
        assert "enable" in guidance.lower()
        assert "Bedrock" in guidance

    def test_get_error_guidance_access_denied(self) -> None:
        """Test error guidance for access denied error."""
        selector = ModelSelector("eu-west-1")
        guidance = selector.get_error_guidance("You don't have access to this model")

        assert "eu-west-1" in guidance
        assert "permissions" in guidance.lower()
        assert "IAM" in guidance

    def test_get_error_guidance_access_denied_exception(self) -> None:
        """Test error guidance for AccessDeniedException."""
        selector = ModelSelector("ap-southeast-1")
        guidance = selector.get_error_guidance("AccessDeniedException: Model not accessible")

        assert "ap-southeast-1" in guidance
        assert "permissions" in guidance.lower()

    def test_get_error_guidance_throttling(self) -> None:
        """Test error guidance for throttling error."""
        selector = ModelSelector("us-west-2")
        guidance = selector.get_error_guidance("ThrottlingException: Rate exceeded")

        assert "us-west-2" in guidance
        assert "throttl" in guidance.lower()
        assert "retry" in guidance.lower()

    def test_get_error_guidance_unknown_error(self) -> None:
        """Test error guidance for unknown error."""
        selector = ModelSelector("eu-west-3")
        guidance = selector.get_error_guidance("Some unknown error occurred")

        assert "eu-west-3" in guidance
        assert "temporarily unavailable" in guidance.lower()
        assert "model variants" in guidance.lower()

    def test_get_error_guidance_with_region_override(self) -> None:
        """Test error guidance with region override."""
        selector = ModelSelector("us-east-1")
        guidance = selector.get_error_guidance("AccessDeniedException", "eu-west-1")

        # Should use override region
        assert "eu-west-1" in guidance
        assert "us-east-1" not in guidance

    def test_all_known_regions_have_models(self) -> None:
        """Test that all known AWS regions have model assignments."""
        known_regions = [
            "us-east-1",
            "us-east-2",
            "us-west-1",
            "us-west-2",
            "eu-west-1",
            "eu-west-2",
            "eu-west-3",
            "eu-central-1",
            "eu-north-1",
            "ap-northeast-1",
            "ap-northeast-2",
            "ap-southeast-1",
            "ap-southeast-2",
            "ap-south-1",
            "ca-central-1",
            "sa-east-1",
        ]

        selector = ModelSelector()

        for region in known_regions:
            models = selector.get_optimized_model_list(region)
            assert len(models) > 0, f"No models returned for region {region}"
            assert all(isinstance(m, str) for m in models)

    def test_logging_occurs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that appropriate logging occurs."""
        with caplog.at_level(logging.INFO):
            selector = ModelSelector("eu-west-1")
            selector.get_optimized_model_list()

        # Should have logged initialization and model selection
        assert any("Initialized ModelSelector" in record.message for record in caplog.records)
        assert any("Getting optimized" in record.message for record in caplog.records)


class TestConvenienceFunctions:
    """Test suite for module-level convenience functions."""

    def test_get_claude_sonnet4_models_for_region_with_region(self) -> None:
        """Test convenience function with explicit region."""
        models = get_claude_sonnet4_models_for_region("eu-west-1")

        assert len(models) > 0
        assert models[0].startswith("eu.")

    def test_get_claude_sonnet4_models_for_region_none(self) -> None:
        """Test convenience function with None region."""
        models = get_claude_sonnet4_models_for_region(None)

        # Should use default region (us-east-1)
        assert len(models) > 0
        assert models[0].startswith("us.")

    def test_get_claude_sonnet4_models_for_region_custom_default(self) -> None:
        """Test convenience function with custom default region."""
        models = get_claude_sonnet4_models_for_region(None, default_region="eu-west-2")

        # Should use custom default
        assert len(models) > 0
        assert models[0].startswith("eu.")

    def test_validate_claude_sonnet4_region_valid(self) -> None:
        """Test convenience function for valid region."""
        is_supported, description = validate_claude_sonnet4_region("us-east-1")

        assert is_supported is True
        assert isinstance(description, str)
        assert len(description) > 0

    def test_validate_claude_sonnet4_region_unknown(self) -> None:
        """Test convenience function for unknown region."""
        is_supported, description = validate_claude_sonnet4_region("unknown-region-123")

        assert is_supported is True  # Still supported via global fallback
        assert "global" in description.lower()

    def test_validate_claude_sonnet4_region_all_known(self) -> None:
        """Test validation for all known regions."""
        known_regions = [
            "us-east-1",
            "eu-west-1",
            "eu-west-3",
            "ap-northeast-1",
            "ca-central-1",
        ]

        for region in known_regions:
            is_supported, description = validate_claude_sonnet4_region(region)
            assert is_supported is True, f"Region {region} should be supported"
            assert region in description


class TestModelSelectorEdgeCases:
    """Test suite for edge cases and error conditions."""

    def test_empty_region_string(self) -> None:
        """Test handling of empty region string."""
        selector = ModelSelector("")
        models = selector.get_optimized_model_list()

        # Should return global fallback
        assert len(models) > 0

    def test_case_sensitivity(self) -> None:
        """Test that region names are case-sensitive."""
        selector = ModelSelector("US-EAST-1")  # Wrong case
        models = selector.get_optimized_model_list()

        # Should fall back to global (case mismatch)
        assert models[0] == BEDROCK_FALLBACK_MODEL

    def test_multiple_calls_same_instance(self) -> None:
        """Test that multiple calls to the same instance are consistent."""
        selector = ModelSelector("eu-west-1")

        models1 = selector.get_optimized_model_list()
        models2 = selector.get_optimized_model_list()

        assert models1 == models2

    def test_different_instances_same_region(self) -> None:
        """Test that different instances with same region return same results."""
        selector1 = ModelSelector("us-west-2")
        selector2 = ModelSelector("us-west-2")

        models1 = selector1.get_optimized_model_list()
        models2 = selector2.get_optimized_model_list()

        assert models1 == models2
