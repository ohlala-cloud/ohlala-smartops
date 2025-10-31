"""Tests for AWS Cost Explorer utilities."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from ohlala_smartops.aws.cost_explorer import (
    CostDataPoint,
    CostExplorerManager,
    CostFilter,
)
from ohlala_smartops.aws.exceptions import CostExplorerError, ValidationError


class TestCostDataPoint:
    """Test suite for CostDataPoint Pydantic model."""

    def test_valid_cost_datapoint_creation(self) -> None:
        """Test creating a valid CostDataPoint."""
        start = datetime.now(UTC)
        end = start + timedelta(days=1)
        point = CostDataPoint(
            time_period_start=start,
            time_period_end=end,
            amount=Decimal("123.45"),
            unit="USD",
        )

        assert point.time_period_start == start
        assert point.time_period_end == end
        assert point.amount == Decimal("123.45")
        assert point.unit == "USD"
        assert point.estimated is False

    def test_cost_datapoint_with_float_amount(self) -> None:
        """Test that float amount is converted to Decimal."""
        start = datetime.now(UTC)
        end = start + timedelta(days=1)
        point = CostDataPoint(time_period_start=start, time_period_end=end, amount=123.45)

        assert isinstance(point.amount, Decimal)
        assert point.amount == Decimal("123.45")

    def test_cost_datapoint_with_string_amount(self) -> None:
        """Test that string amount is converted to Decimal."""
        start = datetime.now(UTC)
        end = start + timedelta(days=1)
        point = CostDataPoint(time_period_start=start, time_period_end=end, amount="456.78")

        assert isinstance(point.amount, Decimal)
        assert point.amount == Decimal("456.78")

    def test_cost_datapoint_estimated(self) -> None:
        """Test CostDataPoint with estimated flag."""
        start = datetime.now(UTC)
        end = start + timedelta(days=1)
        point = CostDataPoint(
            time_period_start=start,
            time_period_end=end,
            amount=Decimal("100.00"),
            estimated=True,
        )

        assert point.estimated is True


class TestCostFilter:
    """Test suite for CostFilter Pydantic model."""

    def test_valid_cost_filter_creation(self) -> None:
        """Test creating a valid CostFilter."""
        filter_obj = CostFilter(
            service="Amazon Elastic Compute Cloud",
            instance_types=["t3.micro", "t3.small"],
            tags={"Environment": "Production"},
        )

        assert filter_obj.service == "Amazon Elastic Compute Cloud"
        assert len(filter_obj.instance_types) == 2
        assert filter_obj.tags == {"Environment": "Production"}

    def test_cost_filter_with_defaults(self) -> None:
        """Test CostFilter with default values."""
        filter_obj = CostFilter()

        assert filter_obj.service is None
        assert filter_obj.instance_types == []
        assert filter_obj.tags == {}


class TestCostExplorerManager:
    """Test suite for CostExplorerManager class."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Fixture providing a mocked AWSClientWrapper."""
        client = Mock()
        client.call = AsyncMock()
        return client

    @pytest.fixture
    def cost_manager(self, mock_client: Mock) -> CostExplorerManager:
        """Fixture providing a CostExplorerManager with mocked client."""
        return CostExplorerManager(region="us-east-1", client=mock_client)

    # Tests for get_cost_and_usage()

    @pytest.mark.asyncio
    async def test_get_cost_and_usage_success(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test getting cost and usage data successfully."""
        mock_client.call.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-02"},
                    "Total": {"UnblendedCost": {"Amount": "123.45", "Unit": "USD"}},
                    "Estimated": False,
                }
            ]
        }

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        datapoints = await cost_manager.get_cost_and_usage(
            start_date=start, end_date=end, granularity="DAILY"
        )

        assert len(datapoints) == 1
        assert datapoints[0].amount == Decimal("123.45")
        assert datapoints[0].unit == "USD"
        mock_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cost_and_usage_with_grouping(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test getting cost and usage with grouping."""
        mock_client.call.return_value = {"ResultsByTime": []}

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        await cost_manager.get_cost_and_usage(
            start_date=start,
            end_date=end,
            group_by=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["GroupBy"] == [{"Type": "DIMENSION", "Key": "SERVICE"}]

    @pytest.mark.asyncio
    async def test_get_cost_and_usage_pagination(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test getting cost and usage with pagination."""
        mock_client.call.side_effect = [
            {
                "ResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-02"},
                        "Total": {"UnblendedCost": {"Amount": "100.00", "Unit": "USD"}},
                    }
                ],
                "NextPageToken": "token1",
            },
            {
                "ResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2024-01-02", "End": "2024-01-03"},
                        "Total": {"UnblendedCost": {"Amount": "150.00", "Unit": "USD"}},
                    }
                ]
            },
        ]

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 3, tzinfo=UTC)

        datapoints = await cost_manager.get_cost_and_usage(start_date=start, end_date=end)

        assert len(datapoints) == 2
        assert mock_client.call.call_count == 2

    @pytest.mark.asyncio
    async def test_get_cost_and_usage_invalid_dates(
        self, cost_manager: CostExplorerManager
    ) -> None:
        """Test that invalid date range raises ValidationError."""
        start = datetime(2024, 1, 2, tzinfo=UTC)
        end = datetime(2024, 1, 1, tzinfo=UTC)

        with pytest.raises(ValidationError, match="start_date must be before end_date"):
            await cost_manager.get_cost_and_usage(start_date=start, end_date=end)

    @pytest.mark.asyncio
    async def test_get_cost_and_usage_invalid_granularity(
        self, cost_manager: CostExplorerManager
    ) -> None:
        """Test that invalid granularity raises ValidationError."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        with pytest.raises(ValidationError, match="granularity must be"):
            await cost_manager.get_cost_and_usage(
                start_date=start, end_date=end, granularity="WEEKLY"
            )

    @pytest.mark.asyncio
    async def test_get_cost_and_usage_aws_error(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in CostExplorerError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        with pytest.raises(CostExplorerError, match="Failed to get cost and usage"):
            await cost_manager.get_cost_and_usage(start_date=start, end_date=end)

    # Tests for get_instance_costs()

    @pytest.mark.asyncio
    async def test_get_instance_costs_success(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test getting instance costs successfully."""
        mock_client.call.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-02"},
                    "Total": {"UnblendedCost": {"Amount": "10.50", "Unit": "USD"}},
                }
            ]
        }

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        costs = await cost_manager.get_instance_costs(
            instance_ids=["i-123"], start_date=start, end_date=end
        )

        assert "i-123" in costs
        assert len(costs["i-123"]) == 1
        assert costs["i-123"][0].amount == Decimal("10.50")

    @pytest.mark.asyncio
    async def test_get_instance_costs_multiple_instances(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test getting costs for multiple instances."""
        mock_client.call.return_value = {"ResultsByTime": []}

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        costs = await cost_manager.get_instance_costs(
            instance_ids=["i-123", "i-456"], start_date=start, end_date=end
        )

        assert len(costs) == 2
        assert "i-123" in costs
        assert "i-456" in costs

    @pytest.mark.asyncio
    async def test_get_instance_costs_empty_instance_ids(
        self, cost_manager: CostExplorerManager
    ) -> None:
        """Test that empty instance_ids raises ValidationError."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        with pytest.raises(ValidationError, match="instance_ids cannot be empty"):
            await cost_manager.get_instance_costs(instance_ids=[], start_date=start, end_date=end)

    # Tests for forecast_cost()

    @pytest.mark.asyncio
    async def test_forecast_cost_success(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test forecasting costs successfully."""
        mock_client.call.return_value = {
            "ForecastResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-02-01", "End": "2024-02-02"},
                    "MeanValue": "125.00",
                }
            ]
        }

        start = datetime(2024, 2, 1, tzinfo=UTC)
        end = datetime(2024, 2, 2, tzinfo=UTC)

        forecast = await cost_manager.forecast_cost(start_date=start, end_date=end)

        assert len(forecast) == 1
        assert forecast[0].amount == Decimal("125.00")
        assert forecast[0].estimated is True

    @pytest.mark.asyncio
    async def test_forecast_cost_invalid_dates(self, cost_manager: CostExplorerManager) -> None:
        """Test that invalid date range raises ValidationError."""
        start = datetime(2024, 2, 2, tzinfo=UTC)
        end = datetime(2024, 2, 1, tzinfo=UTC)

        with pytest.raises(ValidationError, match="start_date must be before end_date"):
            await cost_manager.forecast_cost(start_date=start, end_date=end)

    @pytest.mark.asyncio
    async def test_forecast_cost_invalid_granularity(
        self, cost_manager: CostExplorerManager
    ) -> None:
        """Test that invalid forecast granularity raises ValidationError."""
        start = datetime(2024, 2, 1, tzinfo=UTC)
        end = datetime(2024, 2, 2, tzinfo=UTC)

        with pytest.raises(ValidationError, match="forecast granularity must be DAILY or MONTHLY"):
            await cost_manager.forecast_cost(start_date=start, end_date=end, granularity="HOURLY")

    @pytest.mark.asyncio
    async def test_forecast_cost_aws_error(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in CostExplorerError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        start = datetime(2024, 2, 1, tzinfo=UTC)
        end = datetime(2024, 2, 2, tzinfo=UTC)

        with pytest.raises(CostExplorerError, match="Failed to forecast costs"):
            await cost_manager.forecast_cost(start_date=start, end_date=end)

    # Tests for get_cost_by_tag()

    @pytest.mark.asyncio
    async def test_get_cost_by_tag_success(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test getting costs by tag successfully."""
        mock_client.call.return_value = {
            "ResultsByTime": [
                {
                    "Groups": [
                        {
                            "Keys": ["Environment$Production"],
                            "Metrics": {"UnblendedCost": {"Amount": "500.00"}},
                        },
                        {
                            "Keys": ["Environment$Development"],
                            "Metrics": {"UnblendedCost": {"Amount": "200.00"}},
                        },
                    ]
                }
            ]
        }

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        costs = await cost_manager.get_cost_by_tag(
            tag_key="Environment", start_date=start, end_date=end
        )

        assert len(costs) == 2
        assert costs["Production"] == Decimal("500.00")
        assert costs["Development"] == Decimal("200.00")

    @pytest.mark.asyncio
    async def test_get_cost_by_tag_empty_key(self, cost_manager: CostExplorerManager) -> None:
        """Test that empty tag_key raises ValidationError."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        with pytest.raises(ValidationError, match="tag_key cannot be empty"):
            await cost_manager.get_cost_by_tag(tag_key="", start_date=start, end_date=end)

    @pytest.mark.asyncio
    async def test_get_cost_by_tag_aws_error(
        self, cost_manager: CostExplorerManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in CostExplorerError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        with pytest.raises(CostExplorerError, match="Failed to get cost by tag"):
            await cost_manager.get_cost_by_tag(
                tag_key="Environment", start_date=start, end_date=end
            )

    # Tests for _build_filter()

    def test_build_filter_service(self, cost_manager: CostExplorerManager) -> None:
        """Test building filter with service."""
        filter_obj = CostFilter(service="Amazon Elastic Compute Cloud")
        result = cost_manager._build_filter(filter_obj)

        assert result == {
            "Dimensions": {
                "Key": "SERVICE",
                "Values": ["Amazon Elastic Compute Cloud"],
            }
        }

    def test_build_filter_multiple_criteria(self, cost_manager: CostExplorerManager) -> None:
        """Test building filter with multiple criteria."""
        filter_obj = CostFilter(
            service="Amazon Elastic Compute Cloud",
            instance_types=["t3.micro"],
        )
        result = cost_manager._build_filter(filter_obj)

        assert "And" in result
        assert len(result["And"]) == 2

    def test_build_filter_empty(self, cost_manager: CostExplorerManager) -> None:
        """Test building filter with no criteria."""
        filter_obj = CostFilter()
        result = cost_manager._build_filter(filter_obj)

        assert result == {}

    # Tests for initialization

    def test_cost_manager_with_region(self) -> None:
        """Test CostExplorerManager initialization with region."""
        manager = CostExplorerManager(region="us-east-1")

        assert manager.region == "us-east-1"
        assert manager.client is not None

    def test_cost_manager_with_client(self, mock_client: Mock) -> None:
        """Test CostExplorerManager initialization with pre-configured client."""
        manager = CostExplorerManager(client=mock_client)

        assert manager.client is mock_client

    def test_cost_manager_default_region(self) -> None:
        """Test CostExplorerManager initialization with default region."""
        manager = CostExplorerManager()

        assert manager.region is None
        assert manager.client is not None
