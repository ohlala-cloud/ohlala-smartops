"""AI modules for Ohlala SmartOps.

This package provides AI-related utilities for:
- Claude model selection and configuration
- AWS Bedrock integration
- System prompts and conversation guidance
"""

from ohlala_smartops.ai.model_selector import ModelSelector
from ohlala_smartops.ai.prompts import get_available_tools_section, get_system_prompt

__all__ = [
    "ModelSelector",
    "get_available_tools_section",
    "get_system_prompt",
]
