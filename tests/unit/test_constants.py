"""Tests for the constants module."""

import pytest

from ohlala_smartops import constants


class TestSSMConstants:
    """Tests for SSM-related constants."""

    def test_ssm_document_names(self) -> None:
        """Test that SSM document names are correct."""
        assert constants.SSM_DOCUMENT_LINUX == "AWS-RunShellScript"
        assert constants.SSM_DOCUMENT_WINDOWS == "AWS-RunPowerShellScript"

    def test_ssm_limits(self) -> None:
        """Test SSM limit constants are defined and reasonable."""
        assert constants.SSM_OUTPUT_LIMIT == 24000
        assert constants.SSM_OUTPUT_LIMIT > 0

        assert constants.SSM_SYNC_TIMEOUT == 60
        assert constants.SSM_SYNC_TIMEOUT > 0

        assert constants.SSM_ASYNC_TIMEOUT == 300
        assert constants.SSM_ASYNC_TIMEOUT > constants.SSM_SYNC_TIMEOUT

        assert constants.SSM_POLL_INTERVAL == 2
        assert constants.SSM_POLL_INTERVAL > 0


class TestSecurityConstants:
    """Tests for security-related constants."""

    def test_dangerous_command_patterns_is_tuple(self) -> None:
        """Test that dangerous patterns is an immutable tuple."""
        assert isinstance(constants.DANGEROUS_COMMAND_PATTERNS, tuple)

    def test_dangerous_command_patterns_not_empty(self) -> None:
        """Test that dangerous patterns list is not empty."""
        assert len(constants.DANGEROUS_COMMAND_PATTERNS) > 0

    def test_dangerous_patterns_include_common_destructive_commands(self) -> None:
        """Test that common destructive commands are in the list."""
        patterns = constants.DANGEROUS_COMMAND_PATTERNS
        assert "rm -rf /" in patterns
        assert "shutdown" in patterns
        assert "poweroff" in patterns

    def test_dangerous_patterns_include_windows_commands(self) -> None:
        """Test that Windows destructive commands are included."""
        patterns = constants.DANGEROUS_COMMAND_PATTERNS
        assert any("del" in p for p in patterns)
        assert any("format" in p for p in patterns)
        assert "diskpart" in patterns


class TestPlatformDetection:
    """Tests for platform detection constants."""

    def test_windows_platform_indicators_is_tuple(self) -> None:
        """Test that Windows indicators is an immutable tuple."""
        assert isinstance(constants.WINDOWS_PLATFORM_INDICATORS, tuple)

    def test_windows_platform_indicators(self) -> None:
        """Test that Windows platform indicators are defined."""
        assert "PowerShell" in constants.WINDOWS_PLATFORM_INDICATORS
        assert "Windows" in constants.WINDOWS_PLATFORM_INDICATORS

    def test_placeholder_instance_patterns_is_tuple(self) -> None:
        """Test that placeholder patterns is an immutable tuple."""
        assert isinstance(constants.PLACEHOLDER_INSTANCE_PATTERNS, tuple)

    def test_placeholder_patterns_are_example_ids(self) -> None:
        """Test that placeholder patterns contain example IDs."""
        patterns = constants.PLACEHOLDER_INSTANCE_PATTERNS
        assert any("i-0123456789abcdef0" in p for p in patterns)
        assert any("xxxxx" in p for p in patterns)


class TestAdaptiveCardConstants:
    """Tests for Microsoft Teams Adaptive Card constants."""

    def test_card_version(self) -> None:
        """Test that card version is defined."""
        assert constants.CARD_VERSION == "1.5"
        assert constants.TEAMS_ADAPTIVE_CARD_VERSION == "1.5"

    def test_card_colors(self) -> None:
        """Test that all card color constants are defined."""
        assert constants.CARD_COLOR_ACCENT == "Accent"
        assert constants.CARD_COLOR_WARNING == "Warning"
        assert constants.CARD_COLOR_GOOD == "Good"
        assert constants.CARD_COLOR_ATTENTION == "Attention"

    def test_card_sizes(self) -> None:
        """Test that card size constants are defined."""
        assert constants.CARD_SIZE_LARGE == "Large"
        assert constants.CARD_SIZE_SMALL == "Small"
        assert constants.CARD_WEIGHT_BOLDER == "Bolder"


class TestTeamsActivityTypes:
    """Tests for Microsoft Teams activity type constants."""

    def test_activity_types(self) -> None:
        """Test that Teams activity types are defined."""
        assert constants.TEAMS_INVOKE_ACTIVITY == "invoke"
        assert constants.TEAMS_MESSAGE_ACTIVITY == "message"

    def test_teams_message_update_flag(self) -> None:
        """Test that Teams message update reliability flag is set."""
        assert constants.TEAMS_MESSAGE_UPDATE_UNRELIABLE is True


class TestCardActionTypes:
    """Tests for card action type constants."""

    def test_ssm_action_types(self) -> None:
        """Test that SSM action types are defined."""
        assert constants.ACTION_SSM_APPROVE == "ssm_command_approve"
        assert constants.ACTION_SSM_DENY == "ssm_command_deny"
        assert constants.ACTION_BATCH_SSM_APPROVE == "batch_ssm_approve"
        assert constants.ACTION_BATCH_SSM_DENY == "batch_ssm_deny"

    def test_health_action_type(self) -> None:
        """Test that health action type is defined."""
        assert constants.ACTION_SHOW_HEALTH == "show_health"


class TestChartTypes:
    """Tests for chart and visualization type constants."""

    def test_chart_types(self) -> None:
        """Test that chart type constants are defined."""
        assert constants.CHART_GAUGE == "Chart.Gauge"
        assert constants.CHART_DONUT == "Chart.Donut"
        assert constants.CHART_LINE == "Chart.Line"


class TestSSMStatusConstants:
    """Tests for SSM command status constants."""

    def test_status_values(self) -> None:
        """Test that all status values are defined."""
        assert constants.STATUS_SUCCESS == "Success"
        assert constants.STATUS_FAILED == "Failed"
        assert constants.STATUS_CANCELLED == "Cancelled"
        assert constants.STATUS_TERMINATED == "Terminated"
        assert constants.STATUS_IN_PROGRESS == "InProgress"
        assert constants.STATUS_PENDING == "Pending"

    def test_completion_statuses_is_tuple(self) -> None:
        """Test that completion statuses is an immutable tuple."""
        assert isinstance(constants.COMPLETION_STATUSES, tuple)

    def test_completion_statuses_content(self) -> None:
        """Test that completion statuses contains terminal states."""
        completion = constants.COMPLETION_STATUSES
        assert constants.STATUS_SUCCESS in completion
        assert constants.STATUS_FAILED in completion
        assert constants.STATUS_CANCELLED in completion
        assert constants.STATUS_TERMINATED in completion

    def test_non_completion_statuses_excluded(self) -> None:
        """Test that non-terminal states are not in completion statuses."""
        completion = constants.COMPLETION_STATUSES
        assert constants.STATUS_IN_PROGRESS not in completion
        assert constants.STATUS_PENDING not in completion


class TestCloudWatchDefaults:
    """Tests for CloudWatch metric default constants."""

    def test_metric_defaults(self) -> None:
        """Test that CloudWatch metric defaults are reasonable."""
        assert constants.DEFAULT_METRIC_HOURS == 1
        assert constants.DEFAULT_METRIC_HOURS > 0

        assert constants.DEFAULT_METRIC_PERIOD == 300
        assert constants.DEFAULT_METRIC_PERIOD > 0

        assert constants.DEFAULT_MAX_TOOLS_DISPLAY == 10
        assert constants.DEFAULT_MAX_TOOLS_DISPLAY > 0


class TestBedrockModelConfiguration:
    """Tests for Bedrock model configuration constants."""

    def test_bedrock_primary_models_by_region_is_dict(self) -> None:
        """Test that model mapping is a dictionary."""
        assert isinstance(constants.BEDROCK_PRIMARY_MODEL_BY_REGION, dict)

    def test_bedrock_models_for_major_regions(self) -> None:
        """Test that major AWS regions have model mappings."""
        models = constants.BEDROCK_PRIMARY_MODEL_BY_REGION

        # Test US regions
        assert "us-east-1" in models
        assert "us-west-2" in models

        # Test EU regions
        assert "eu-west-1" in models
        assert "eu-central-1" in models

        # Test APAC regions
        assert "ap-northeast-1" in models
        assert "ap-southeast-1" in models

    def test_bedrock_regional_models_have_correct_prefix(self) -> None:
        """Test that regional models have appropriate prefixes."""
        models = constants.BEDROCK_PRIMARY_MODEL_BY_REGION

        # EU regions should use eu. prefix
        assert models["eu-west-1"].startswith("eu.anthropic.claude")

        # US regions should use us. prefix
        assert models["us-east-1"].startswith("us.anthropic.claude")

        # APAC regions should use apac. prefix
        assert models["ap-northeast-1"].startswith("apac.anthropic.claude")

    def test_bedrock_fallback_model(self) -> None:
        """Test that fallback model is global and properly formatted."""
        fallback = constants.BEDROCK_FALLBACK_MODEL
        assert fallback.startswith("global.anthropic.claude")
        assert "sonnet-4-5" in fallback.lower()

    def test_bedrock_parameters(self) -> None:
        """Test that Bedrock parameters are reasonable."""
        assert constants.BEDROCK_MAX_TOKENS == 4000
        assert constants.BEDROCK_MAX_TOKENS > 0

        assert constants.BEDROCK_TEMPERATURE == 0.3
        assert 0.0 <= constants.BEDROCK_TEMPERATURE <= 1.0

        assert constants.BEDROCK_ANTHROPIC_VERSION == "bedrock-2023-05-31"


class TestGetBedrockModelForRegion:
    """Tests for get_bedrock_model_for_region function."""

    def test_returns_regional_model_for_known_region(self) -> None:
        """Test that function returns regional model for known regions."""
        model = constants.get_bedrock_model_for_region("us-east-1")
        assert model == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

        model = constants.get_bedrock_model_for_region("eu-west-1")
        assert model == "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"

    def test_returns_fallback_for_unknown_region(self) -> None:
        """Test that function returns fallback model for unknown regions."""
        model = constants.get_bedrock_model_for_region("unknown-region-1")
        assert model == constants.BEDROCK_FALLBACK_MODEL

    def test_returns_fallback_for_empty_region(self) -> None:
        """Test that function handles empty region string."""
        model = constants.get_bedrock_model_for_region("")
        assert model == constants.BEDROCK_FALLBACK_MODEL

    def test_all_mapped_regions_return_valid_model_ids(self) -> None:
        """Test that all regions in the mapping return valid model IDs."""
        for region in constants.BEDROCK_PRIMARY_MODEL_BY_REGION:
            model = constants.get_bedrock_model_for_region(region)
            assert model.startswith(("us.", "eu.", "apac.", "global."))
            assert "anthropic.claude" in model


class TestConstantsImmutability:
    """Tests to ensure constants are properly immutable."""

    def test_tuples_are_immutable(self) -> None:
        """Test that tuple constants cannot be modified."""
        # This should raise TypeError if attempted
        with pytest.raises(TypeError):
            constants.DANGEROUS_COMMAND_PATTERNS[0] = "test"  # type: ignore[index]

        with pytest.raises(TypeError):
            constants.WINDOWS_PLATFORM_INDICATORS[0] = "test"  # type: ignore[index]

        with pytest.raises(TypeError):
            constants.COMPLETION_STATUSES[0] = "test"  # type: ignore[index]

    def test_dict_values_are_strings(self) -> None:
        """Test that all model mapping values are strings."""
        for region, model_id in constants.BEDROCK_PRIMARY_MODEL_BY_REGION.items():
            assert isinstance(region, str)
            assert isinstance(model_id, str)
            assert len(model_id) > 0
