"""Utility modules for Ohlala SmartOps.

This package provides common utilities for:
- PowerShell command validation and fixing
- SSM command validation and preprocessing
- Command formatting and sanitization
- Token estimation and cost tracking
- AWS API throttling and rate limiting
"""

from ohlala_smartops.utils.bedrock_throttler import (
    BedrockThrottler,
    get_bedrock_throttler,
    throttled_bedrock_call,
)
from ohlala_smartops.utils.global_throttler import (
    CircuitBreakerOpenError,
    CircuitBreakerTrippedError,
    GlobalThrottler,
    get_global_throttler,
    throttled_aws_call,
)
from ohlala_smartops.utils.powershell import (
    detect_powershell_syntax_errors,
    validate_and_fix_powershell,
)
from ohlala_smartops.utils.ssm import preprocess_ssm_commands
from ohlala_smartops.utils.ssm_validation import fix_common_issues, validate_ssm_commands
from ohlala_smartops.utils.token_estimator import TokenEstimator
from ohlala_smartops.utils.token_tracker import (
    TokenTracker,
    check_operation_limits,
    estimate_bedrock_input_tokens,
    get_token_tracker,
    get_usage_report,
    get_usage_summary,
    track_bedrock_operation,
)

__all__ = [
    "BedrockThrottler",
    "CircuitBreakerOpenError",
    "CircuitBreakerTrippedError",
    "GlobalThrottler",
    "TokenEstimator",
    "TokenTracker",
    "check_operation_limits",
    "detect_powershell_syntax_errors",
    "estimate_bedrock_input_tokens",
    "fix_common_issues",
    "get_bedrock_throttler",
    "get_global_throttler",
    "get_token_tracker",
    "get_usage_report",
    "get_usage_summary",
    "preprocess_ssm_commands",
    "throttled_aws_call",
    "throttled_bedrock_call",
    "track_bedrock_operation",
    "validate_and_fix_powershell",
    "validate_ssm_commands",
]
