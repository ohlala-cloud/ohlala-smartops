"""Claude Sonnet 4 model selection for cross-region inference profiles.

This module provides intelligent selection of Claude Sonnet 4 models and inference profiles
based on the deployment region, ensuring optimal performance and availability across all
AWS regions including those without native Claude Sonnet 4 support.
"""

import logging
from typing import Final

from ohlala_smartops.constants import (
    BEDROCK_FALLBACK_MODEL,
    BEDROCK_PRIMARY_MODEL_BY_REGION,
    get_bedrock_model_for_region,
)

logger: Final = logging.getLogger(__name__)


class ModelSelector:
    """Intelligent selector for Claude Sonnet 4 models and inference profiles.

    This class provides methods to select the optimal Claude Sonnet 4 model
    for a given AWS region, manage fallback strategies, and validate region support.
    """

    def __init__(self, aws_region: str = "us-east-1") -> None:
        """Initialize the Claude Sonnet 4 model selector.

        Args:
            aws_region: AWS region for deployment. Defaults to "us-east-1".
        """
        self.aws_region = aws_region
        self.model_candidates = BEDROCK_PRIMARY_MODEL_BY_REGION
        self.fallback_model = BEDROCK_FALLBACK_MODEL
        logger.info(
            f"Initialized ModelSelector for region {aws_region} with "
            f"{len(self.model_candidates)} regional models"
        )

    def get_optimized_model_list(self, deployment_region: str | None = None) -> list[str]:
        """Get an optimized list of Claude Sonnet 4 models for the given region.

        Uses hardcoded region-based mapping for immediate optimal selection.
        Returns a 2-model strategy: primary for the region + global fallback.

        Args:
            deployment_region: AWS region for deployment. If None, uses the instance's region.

        Returns:
            List of model IDs/inference profiles in priority order (max 2 models).

        Example:
            >>> selector = ModelSelector("eu-west-3")
            >>> models = selector.get_optimized_model_list()
            >>> print(models)
            ['eu.anthropic.claude-sonnet-4-5-20250929-v1:0',
             'global.anthropic.claude-sonnet-4-5-20250929-v1:0']
        """
        region = deployment_region or self.aws_region
        logger.info(f"Getting optimized Claude Sonnet 4 model list for region: {region}")

        # Use hardcoded primary model for region (immediate success expected)
        primary_model = get_bedrock_model_for_region(region)

        # Simple 2-model strategy: primary + global fallback
        if primary_model == self.fallback_model:
            # If primary is already global, just use it
            final_list = [primary_model]
        else:
            # Primary regional + global fallback
            final_list = [primary_model, self.fallback_model]

        logger.info(f"Optimized model list for {region}: {final_list} (primary: {primary_model})")
        return final_list

    def get_best_model_for_region(self, deployment_region: str | None = None) -> str:
        """Get the best Claude Sonnet 4 model for the given region.

        Uses hardcoded mapping for immediate optimal selection.

        Args:
            deployment_region: AWS region for deployment. If None, uses the instance's region.

        Returns:
            The best model ID/inference profile for the region.

        Example:
            >>> selector = ModelSelector("us-east-1")
            >>> model = selector.get_best_model_for_region()
            >>> print(model)
            'us.anthropic.claude-sonnet-4-5-20250929-v1:0'
        """
        region = deployment_region or self.aws_region
        best_model = get_bedrock_model_for_region(region)
        logger.info(f"Best Claude Sonnet 4 model for {region}: {best_model}")
        return best_model

    def is_inference_profile(self, model_id: str) -> bool:
        """Check if a model ID is an inference profile.

        Args:
            model_id: The model identifier to check.

        Returns:
            True if it's an inference profile (has regional prefix), False if direct model.

        Example:
            >>> selector = ModelSelector()
            >>> selector.is_inference_profile("global.anthropic.claude-sonnet-4-5-20250929-v1:0")
            True
            >>> selector.is_inference_profile("anthropic.claude-sonnet-4-5-20250929-v1:0")
            False
        """
        inference_profile_prefixes = ("global.", "us.", "eu.", "apac.")
        is_profile = any(model_id.startswith(prefix) for prefix in inference_profile_prefixes)

        if is_profile:
            logger.debug(f"Model {model_id} is an inference profile")
        else:
            logger.debug(f"Model {model_id} is a direct model")

        return is_profile

    def get_model_category(self, model_id: str) -> str:
        """Get the category of a model (global, regional, or direct).

        Args:
            model_id: The model identifier to categorize.

        Returns:
            Category string: 'global', 'regional', or 'direct'.

        Example:
            >>> selector = ModelSelector()
            >>> selector.get_model_category("global.anthropic.claude-sonnet-4-5-20250929-v1:0")
            'global'
            >>> selector.get_model_category("eu.anthropic.claude-sonnet-4-5-20250929-v1:0")
            'regional'
        """
        if model_id.startswith("global."):
            return "global"
        if any(model_id.startswith(f"{region}.") for region in ("us", "eu", "apac")):
            return "regional"
        return "direct"

    def get_regional_fallback_strategy(
        self, deployment_region: str | None = None
    ) -> list[tuple[str, str]]:
        """Get detailed fallback strategy with model categories.

        Simplified to primary + global fallback only.

        Args:
            deployment_region: AWS region for deployment. If None, uses the instance's region.

        Returns:
            List of (model_id, category) tuples in priority order (max 2 items).

        Example:
            >>> selector = ModelSelector("eu-west-1")
            >>> strategy = selector.get_regional_fallback_strategy()
            >>> for i, (model, category) in enumerate(strategy, 1):
            ...     print(f"{i}. {category}: {model}")
            1. regional: eu.anthropic.claude-sonnet-4-5-20250929-v1:0
            2. global: global.anthropic.claude-sonnet-4-5-20250929-v1:0
        """
        region = deployment_region or self.aws_region
        optimized_list = self.get_optimized_model_list(region)

        strategy = [(model, self.get_model_category(model)) for model in optimized_list]

        logger.info(f"Simplified Claude Sonnet 4 strategy for {region}:")
        for i, (model, category) in enumerate(strategy, 1):
            logger.info(f"  {i}. {model} ({category}) - {'Primary' if i == 1 else 'Fallback'}")

        return strategy

    def get_inference_profile_arn_patterns(self) -> list[str]:
        """Get ARN patterns for IAM policies to support inference profiles.

        Returns:
            List of ARN patterns for IAM resource permissions.

        Example:
            >>> selector = ModelSelector()
            >>> patterns = selector.get_inference_profile_arn_patterns()
            >>> print(patterns[0])
            'arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-*'
        """
        patterns = [
            # Direct Claude Sonnet 4 and 4.5 models
            "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-*",
            "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-*",
            # All Claude Sonnet 4 and 4.5 inference profiles
            "arn:aws:bedrock:*:*:inference-profile/global.anthropic.claude-sonnet-4-*",
            "arn:aws:bedrock:*:*:inference-profile/global.anthropic.claude-sonnet-4-5-*",
            "arn:aws:bedrock:*:*:inference-profile/us.anthropic.claude-sonnet-4-*",
            "arn:aws:bedrock:*:*:inference-profile/us.anthropic.claude-sonnet-4-5-*",
            "arn:aws:bedrock:*:*:inference-profile/eu.anthropic.claude-sonnet-4-*",
            "arn:aws:bedrock:*:*:inference-profile/eu.anthropic.claude-sonnet-4-5-*",
            "arn:aws:bedrock:*:*:inference-profile/apac.anthropic.claude-sonnet-4-*",
            "arn:aws:bedrock:*:*:inference-profile/apac.anthropic.claude-sonnet-4-5-*",
            # Broad pattern for any future Claude Sonnet 4/4.5 inference profiles
            "arn:aws:bedrock:*:*:inference-profile/*.anthropic.claude-sonnet-4-*",
        ]

        logger.debug(
            f"Generated {len(patterns)} ARN patterns for Claude Sonnet 4 inference profiles"
        )
        return patterns

    def validate_region_support(self, deployment_region: str) -> tuple[bool, str]:
        """Validate that Claude Sonnet 4 is supported in the given region.

        Args:
            deployment_region: AWS region to validate.

        Returns:
            Tuple of (is_supported, strategy_description).

        Example:
            >>> selector = ModelSelector()
            >>> is_supported, description = selector.validate_region_support("eu-west-3")
            >>> print(f"Supported: {is_supported}")
            Supported: True
            >>> print(description)
            Region eu-west-3 supported via regional inference profile
        """
        optimized_models = self.get_optimized_model_list(deployment_region)

        if not optimized_models:
            return False, f"No Claude Sonnet 4 models available for region {deployment_region}"

        # Check if region has regional optimization
        has_regional_optimization = deployment_region in self.model_candidates

        if has_regional_optimization:
            primary_strategy = self.get_model_category(optimized_models[0])
            strategy_desc = (
                f"Region {deployment_region} supported via {primary_strategy} inference profile"
            )
        else:
            strategy_desc = f"Region {deployment_region} supported via global inference profile"

        logger.info(f"Region validation for {deployment_region}: {strategy_desc}")
        return True, strategy_desc

    def get_error_guidance(self, error_message: str, deployment_region: str | None = None) -> str:
        """Get specific guidance based on Claude Sonnet 4 errors.

        Args:
            error_message: The error message from Bedrock.
            deployment_region: AWS region where error occurred. If None, uses the instance's region.

        Returns:
            Human-readable guidance for resolving the error.

        Example:
            >>> selector = ModelSelector("us-east-1")
            >>> guidance = selector.get_error_guidance("AccessDeniedException")
            >>> print(guidance)
            Missing permissions for Claude Sonnet 4 inference profiles in us-east-1...
        """
        region = deployment_region or self.aws_region
        lower_error = error_message.lower()

        if "provided model identifier is invalid" in lower_error:
            return (
                f"Claude Sonnet 4 model not available in {region}. "
                f"This application requires global inference profile access. "
                f"Please enable Claude Sonnet 4 access in Amazon Bedrock console."
            )

        if "you don't have access" in lower_error or "accessdeniedexception" in lower_error:
            return (
                f"Missing permissions for Claude Sonnet 4 inference profiles in {region}. "
                f"Please enable model access in Bedrock console and verify IAM permissions "
                f"include inference profile ARNs."
            )

        if "throttling" in lower_error:
            return (
                f"Claude Sonnet 4 requests are being throttled in {region}. "
                f"The application will automatically retry with exponential backoff."
            )

        fallback_strategy = self.get_regional_fallback_strategy(region)
        models_tried = len(fallback_strategy)
        return (
            f"Claude Sonnet 4 is temporarily unavailable in {region}. "
            f"Tried {models_tried} model variants including inference profiles. "
            f"Please check AWS Bedrock status and model access settings."
        )


def get_claude_sonnet4_models_for_region(
    region: str | None = None, default_region: str = "us-east-1"
) -> list[str]:
    """Convenience function to get Claude Sonnet 4 models for a region.

    Args:
        region: AWS region. If None, uses default_region.
        default_region: Default AWS region if region is None. Defaults to "us-east-1".

    Returns:
        List of Claude Sonnet 4 model IDs in priority order.

    Example:
        >>> models = get_claude_sonnet4_models_for_region("eu-west-1")
        >>> print(models)
        ['eu.anthropic.claude-sonnet-4-5-20250929-v1:0',
         'global.anthropic.claude-sonnet-4-5-20250929-v1:0']
    """
    selector = ModelSelector(region or default_region)
    return selector.get_optimized_model_list()


def validate_claude_sonnet4_region(region: str) -> tuple[bool, str]:
    """Convenience function to validate Claude Sonnet 4 support for a region.

    Args:
        region: AWS region to validate.

    Returns:
        Tuple of (is_supported, description).

    Example:
        >>> is_supported, desc = validate_claude_sonnet4_region("us-west-2")
        >>> print(f"{is_supported}: {desc}")
        True: Region us-west-2 supported via regional inference profile
    """
    selector = ModelSelector(region)
    return selector.validate_region_support(region)
