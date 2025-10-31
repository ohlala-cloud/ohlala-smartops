"""Tests for token consumption estimation utilities."""

import json
from unittest.mock import patch

import pytest

from ohlala_smartops.utils.token_estimator import TokenEstimator, main


class TestTokenEstimator:
    """Test suite for TokenEstimator class."""

    def test_pricing_constants(self) -> None:
        """Test that pricing constants are defined correctly."""
        assert "input_tokens_per_1k" in TokenEstimator.PRICING
        assert "output_tokens_per_1k" in TokenEstimator.PRICING
        assert TokenEstimator.PRICING["input_tokens_per_1k"] == 0.003
        assert TokenEstimator.PRICING["output_tokens_per_1k"] == 0.015

    def test_model_limits_constants(self) -> None:
        """Test that model limits are defined correctly."""
        assert "max_input_tokens" in TokenEstimator.MODEL_LIMITS
        assert "max_output_tokens" in TokenEstimator.MODEL_LIMITS
        assert "bedrock_max_tokens" in TokenEstimator.MODEL_LIMITS
        assert TokenEstimator.MODEL_LIMITS["max_input_tokens"] == 200000
        assert TokenEstimator.MODEL_LIMITS["max_output_tokens"] == 4096

    def test_operation_tokens_constants(self) -> None:
        """Test that operation token estimates are defined."""
        required_keys = [
            "system_prompt",
            "tool_definitions",
            "conversation_context",
            "instance_metadata",
            "health_check_output",
        ]
        for key in required_keys:
            assert key in TokenEstimator.OPERATION_TOKENS
            assert isinstance(TokenEstimator.OPERATION_TOKENS[key], int)
            assert TokenEstimator.OPERATION_TOKENS[key] > 0

    def test_estimate_tokens_basic(self) -> None:
        """Test basic token estimation for a simple scenario."""
        result = TokenEstimator.estimate_tokens(10, "health_check", include_analysis=True)

        # Check structure
        assert "instances" in result
        assert "command_type" in result
        assert "tokens" in result
        assert "costs" in result
        assert "limits" in result
        assert "throttling_risk" in result

        # Check values
        assert result["instances"] == 10
        assert result["command_type"] == "health_check"
        assert result["tokens"]["input"] > 0
        assert result["tokens"]["output"] > 0
        assert result["tokens"]["total"] > 0

    def test_estimate_tokens_without_analysis(self) -> None:
        """Test token estimation without analysis output."""
        with_analysis = TokenEstimator.estimate_tokens(10, "health_check", include_analysis=True)
        without_analysis = TokenEstimator.estimate_tokens(
            10, "health_check", include_analysis=False
        )

        # Without analysis should have fewer output tokens
        assert without_analysis["tokens"]["output"] < with_analysis["tokens"]["output"]

    def test_estimate_tokens_different_command_types(self) -> None:
        """Test token estimation for different command types."""
        disk_check = TokenEstimator.estimate_tokens(10, "disk_check")
        process_list = TokenEstimator.estimate_tokens(10, "process_list")

        # Process list should have more tokens (verbose output)
        assert process_list["tokens"]["input"] > disk_check["tokens"]["input"]

    def test_estimate_tokens_scales_with_instances(self) -> None:
        """Test that token usage scales with number of instances."""
        small = TokenEstimator.estimate_tokens(5, "health_check")
        large = TokenEstimator.estimate_tokens(20, "health_check")

        # More instances = more tokens
        assert large["tokens"]["input"] > small["tokens"]["input"]
        assert large["tokens"]["output"] > small["tokens"]["output"]

    def test_estimate_tokens_cost_calculation(self) -> None:
        """Test that costs are calculated correctly."""
        result = TokenEstimator.estimate_tokens(10, "health_check")

        # Check cost format
        assert result["costs"]["input_cost"].startswith("$")
        assert result["costs"]["output_cost"].startswith("$")
        assert result["costs"]["total_cost"].startswith("$")
        assert result["costs"]["cost_per_instance"].startswith("$")

        # Parse and verify costs
        total_cost = float(result["costs"]["total_cost"].replace("$", ""))
        per_instance = float(result["costs"]["cost_per_instance"].replace("$", ""))
        assert total_cost > 0
        assert per_instance > 0
        assert abs(total_cost - (per_instance * 10)) < 0.001  # Should be equal within rounding

    def test_estimate_tokens_within_limits(self) -> None:
        """Test limit checking for reasonable instance counts."""
        result = TokenEstimator.estimate_tokens(10, "health_check")

        assert result["limits"]["within_limits"] is True
        assert result["limits"]["tokens_remaining"] > 0
        assert len(result["warnings"]) == 0

    def test_estimate_tokens_exceeds_limits(self) -> None:
        """Test limit checking when exceeding token limits."""
        # Use very high instance count to exceed limits
        result = TokenEstimator.estimate_tokens(1000, "software_inventory")

        assert result["limits"]["within_limits"] is False
        assert len(result["warnings"]) > 0
        assert any("exceed model limit" in w for w in result["warnings"])
        assert len(result["recommendations"]) > 0

    def test_estimate_tokens_approaching_limits(self) -> None:
        """Test warning when approaching token limits."""
        # Find a number that gets us close to 80% of limit
        result = TokenEstimator.estimate_tokens(100, "process_list")

        # Should have some warnings about approaching limits
        if result["tokens"]["percentage_of_limit"] > 80:
            assert len(result["warnings"]) > 0
            assert len(result["recommendations"]) > 0

    def test_calculate_max_instances(self) -> None:
        """Test calculation of maximum instances for different command types."""
        max_health_check = TokenEstimator._calculate_max_instances("health_check")
        max_software = TokenEstimator._calculate_max_instances("software_inventory")

        # Both should be positive integers
        assert isinstance(max_health_check, int)
        assert isinstance(max_software, int)
        assert max_health_check > 0
        assert max_software > 0

        # Software inventory uses more tokens, so max should be lower
        assert max_software < max_health_check

    def test_calculate_max_instances_unknown_command(self) -> None:
        """Test max instances calculation with unknown command type."""
        # Should fall back to health_check default
        max_instances = TokenEstimator._calculate_max_instances("unknown_command")

        assert isinstance(max_instances, int)
        assert max_instances > 0

    def test_assess_throttling_risk_low(self) -> None:
        """Test throttling risk assessment for low instance counts."""
        risk = TokenEstimator._assess_throttling_risk(5, "health_check")

        assert risk["level"] == "Low"
        assert risk["score"] == 0.2
        assert risk["bedrock_api_calls"] > 0
        assert len(risk["mitigation"]) > 0

    def test_assess_throttling_risk_medium(self) -> None:
        """Test throttling risk assessment for medium instance counts."""
        risk = TokenEstimator._assess_throttling_risk(20, "health_check")

        assert risk["level"] == "Medium"
        assert risk["score"] == 0.5
        assert "delay" in str(risk["mitigation"]).lower()

    def test_assess_throttling_risk_high(self) -> None:
        """Test throttling risk assessment for high instance counts."""
        risk = TokenEstimator._assess_throttling_risk(40, "health_check")

        assert risk["level"] == "High"
        assert risk["score"] == 0.8
        assert "batch" in str(risk["mitigation"]).lower()

    def test_assess_throttling_risk_very_high(self) -> None:
        """Test throttling risk assessment for very high instance counts."""
        risk = TokenEstimator._assess_throttling_risk(100, "health_check")

        assert risk["level"] == "Very High"
        assert risk["score"] == 0.95
        assert "exponential backoff" in str(risk["mitigation"]).lower()

    def test_assess_throttling_risk_complex_command(self) -> None:
        """Test that complex commands increase throttling risk."""
        simple_risk = TokenEstimator._assess_throttling_risk(20, "health_check")
        complex_risk = TokenEstimator._assess_throttling_risk(20, "software_inventory_output")

        # Complex command should have higher risk score
        assert complex_risk["score"] > simple_risk["score"]

    def test_get_throttling_mitigation_all_levels(self) -> None:
        """Test mitigation strategies for all risk levels."""
        for level in ["Low", "Medium", "High", "Very High"]:
            mitigations = TokenEstimator._get_throttling_mitigation(level)

            assert isinstance(mitigations, list)
            assert len(mitigations) > 0
            assert all(isinstance(m, str) for m in mitigations)

    def test_get_throttling_mitigation_unknown_level(self) -> None:
        """Test mitigation for unknown risk level."""
        mitigations = TokenEstimator._get_throttling_mitigation("Unknown")

        assert isinstance(mitigations, list)
        assert len(mitigations) > 0
        assert "Unknown risk level" in mitigations[0]

    def test_generate_scaling_report(self) -> None:
        """Test generation of comprehensive scaling report."""
        report = TokenEstimator.generate_scaling_report()

        assert isinstance(report, str)
        assert len(report) > 0

        # Check for key sections
        assert "SMARTOPS AGENT TOKEN CONSUMPTION" in report
        assert "SCENARIO" in report
        assert "GENERAL RECOMMENDATIONS" in report
        assert "OPTIMAL OPERATING RANGES" in report

        # Check for specific scenarios
        assert "Small deployment" in report
        assert "Medium deployment" in report
        assert "Large deployment" in report
        assert "Enterprise" in report

    def test_generate_scaling_report_contains_estimates(self) -> None:
        """Test that scaling report contains actual estimates."""
        report = TokenEstimator.generate_scaling_report()

        # Should contain token counts
        assert "Input tokens:" in report
        assert "Output tokens:" in report
        assert "Total tokens:" in report

        # Should contain costs
        assert "$" in report
        assert "Estimated Costs:" in report

        # Should contain risk assessments
        assert "Throttling Risk:" in report

    def test_token_estimation_consistency(self) -> None:
        """Test that repeated estimations are consistent."""
        result1 = TokenEstimator.estimate_tokens(10, "health_check")
        result2 = TokenEstimator.estimate_tokens(10, "health_check")

        assert result1["tokens"]["input"] == result2["tokens"]["input"]
        assert result1["tokens"]["output"] == result2["tokens"]["output"]
        assert result1["costs"]["total_cost"] == result2["costs"]["total_cost"]

    def test_percentage_of_limit_calculation(self) -> None:
        """Test that percentage of limit is calculated correctly."""
        result = TokenEstimator.estimate_tokens(10, "health_check")

        percentage = result["tokens"]["percentage_of_limit"]
        input_tokens = result["tokens"]["input"]
        max_tokens = TokenEstimator.MODEL_LIMITS["max_input_tokens"]

        expected_percentage = (input_tokens / max_tokens) * 100
        assert abs(percentage - expected_percentage) < 0.01

    def test_tokens_remaining_calculation(self) -> None:
        """Test that tokens remaining is calculated correctly."""
        result = TokenEstimator.estimate_tokens(10, "health_check")

        tokens_remaining = result["limits"]["tokens_remaining"]
        input_tokens = result["tokens"]["input"]
        max_tokens = TokenEstimator.MODEL_LIMITS["max_input_tokens"]

        expected_remaining = max(0, max_tokens - input_tokens)
        assert tokens_remaining == expected_remaining

    def test_bedrock_api_calls_estimation(self) -> None:
        """Test that Bedrock API calls are estimated correctly."""
        # 10 instances should need 2 command batches (ceil(10/5))
        result = TokenEstimator.estimate_tokens(10, "health_check")
        assert result["throttling_risk"]["bedrock_api_calls"] == 3  # 1 initial + 2 batches

        # 5 instances should need 1 command batch
        result = TokenEstimator.estimate_tokens(5, "health_check")
        assert result["throttling_risk"]["bedrock_api_calls"] == 2  # 1 initial + 1 batch


class TestTokenEstimatorCLI:
    """Test suite for TokenEstimator CLI interface."""

    @patch("sys.argv", ["token_estimator.py", "--instances", "10", "--command", "health_check"])
    def test_main_basic_estimate(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test CLI basic estimation."""
        main()
        captured = capsys.readouterr()

        # Should output valid JSON
        output = json.loads(captured.out)
        assert output["instances"] == 10
        assert output["command_type"] == "health_check"

    @patch("sys.argv", ["token_estimator.py", "--report"])
    def test_main_scaling_report(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test CLI scaling report generation."""
        main()
        captured = capsys.readouterr()

        # Should contain report text
        assert "SMARTOPS AGENT TOKEN CONSUMPTION" in captured.out
        assert "SCENARIO" in captured.out

    @patch("sys.argv", ["token_estimator.py", "--instances", "25", "--command", "disk_check"])
    def test_main_custom_parameters(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test CLI with custom parameters."""
        main()
        captured = capsys.readouterr()

        output = json.loads(captured.out)
        assert output["instances"] == 25
        assert output["command_type"] == "disk_check"

    @patch("sys.argv", ["token_estimator.py"])
    def test_main_default_parameters(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test CLI with default parameters."""
        main()
        captured = capsys.readouterr()

        output = json.loads(captured.out)
        assert output["instances"] == 10  # default
        assert output["command_type"] == "health_check"  # default
