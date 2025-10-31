"""AWS Cost Explorer utilities.

This module provides high-level utilities for tracking and analyzing AWS costs using
the Cost Explorer API. All operations use the AWSClientWrapper for automatic throttling
and error handling.

Note: Cost Explorer API must be enabled in the AWS account before use.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, Field, field_validator

from ohlala_smartops.aws.client import AWSClientWrapper, create_aws_client
from ohlala_smartops.aws.exceptions import CostExplorerError, ValidationError

logger: Final = logging.getLogger(__name__)


class CostDataPoint(BaseModel):
    """Model representing a cost data point.

    Attributes:
        time_period_start: Start of the time period.
        time_period_end: End of the time period.
        amount: Cost amount using Decimal for currency precision.
        unit: Currency unit (e.g., "USD"). Defaults to "USD".
        estimated: Whether this is an estimated cost. Defaults to False.
    """

    time_period_start: datetime
    time_period_end: datetime
    amount: Decimal
    unit: str = "USD"
    estimated: bool = False

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: Any) -> Decimal:
        """Convert amount to Decimal for precise currency handling.

        Args:
            v: Amount value (can be string, float, or Decimal).

        Returns:
            Decimal value.
        """
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class CostFilter(BaseModel):
    """Model for cost filtering criteria.

    Attributes:
        service: Filter by AWS service (e.g., "Amazon Elastic Compute Cloud").
        instance_types: Filter by EC2 instance types.
        tags: Filter by resource tags.
    """

    service: str | None = None
    instance_types: list[str] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class CostExplorerManager:
    """Manager for AWS Cost Explorer operations with automatic throttling.

    This class provides high-level methods for tracking and analyzing AWS costs.
    Note that Cost Explorer data has a 24-48 hour latency.

    Important: The Cost Explorer API must be enabled in your AWS account before use.
    This can be done through the AWS Console or CLI.

    All operations use the AWSClientWrapper for automatic rate limiting, error
    handling, and retries.

    Example:
        >>> from datetime import datetime, timedelta
        >>> from decimal import Decimal
        >>> manager = CostExplorerManager(region="us-east-1")
        >>>
        >>> # Get cost for last 7 days
        >>> end = datetime.now()
        >>> start = end - timedelta(days=7)
        >>> costs = await manager.get_cost_and_usage(
        ...     start_date=start,
        ...     end_date=end,
        ...     granularity="DAILY",
        ...     metrics=["UnblendedCost"]
        ... )
    """

    def __init__(self, region: str | None = None, client: AWSClientWrapper | None = None) -> None:
        """Initialize Cost Explorer manager.

        Args:
            region: AWS region name. Cost Explorer is a global service but
                requires a region for authentication. Defaults to None.
            client: Optional pre-configured AWSClientWrapper. If None, creates
                a new one. Defaults to None.

        Example:
            >>> manager = CostExplorerManager(region="us-east-1")
            >>> # Or with existing client:
            >>> client = create_aws_client("ce", region="us-east-1")
            >>> manager = CostExplorerManager(client=client)
        """
        self.region = region
        self.client = client or create_aws_client("ce", region=region)
        logger.info(f"Initialized CostExplorerManager for region {region or 'default'}")

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
        metrics: Sequence[str] = ("UnblendedCost",),
        group_by: list[dict[str, str]] | None = None,
        filter_criteria: CostFilter | None = None,
    ) -> list[CostDataPoint]:
        """Get cost and usage data for a time period.

        Args:
            start_date: Start of time period (inclusive).
            end_date: End of time period (exclusive).
            granularity: Time granularity - "DAILY", "MONTHLY", or "HOURLY".
                Hourly data is only available for the last 14 days. Defaults to "DAILY".
            metrics: Cost metrics to retrieve (UnblendedCost, BlendedCost, etc.).
                Defaults to ("UnblendedCost",).
            group_by: Group results by dimensions (e.g., [{"Type": "DIMENSION",
                "Key": "SERVICE"}]). Defaults to None.
            filter_criteria: Filter criteria for costs. Defaults to None.

        Returns:
            List of CostDataPoint objects.

        Raises:
            ValidationError: If parameters are invalid.
            CostExplorerError: If AWS API call fails or API is not enabled.

        Example:
            >>> from datetime import datetime, timedelta
            >>> end = datetime.now()
            >>> start = end - timedelta(days=7)
            >>> costs = await manager.get_cost_and_usage(
            ...     start_date=start,
            ...     end_date=end,
            ...     granularity="DAILY"
            ... )
        """
        if start_date >= end_date:
            raise ValidationError("start_date must be before end_date", service="ce")

        if granularity not in ("DAILY", "MONTHLY", "HOURLY"):
            raise ValidationError(
                f"granularity must be DAILY, MONTHLY, or HOURLY, got {granularity}",
                service="ce",
            )

        logger.info(f"Getting cost and usage from {start_date} to {end_date}")

        try:
            # Build API parameters
            kwargs: dict[str, Any] = {
                "TimePeriod": {
                    "Start": start_date.strftime("%Y-%m-%d"),
                    "End": end_date.strftime("%Y-%m-%d"),
                },
                "Granularity": granularity,
                "Metrics": list(metrics),
            }

            if group_by:
                kwargs["GroupBy"] = group_by

            if filter_criteria:
                kwargs["Filter"] = self._build_filter(filter_criteria)

            # Handle pagination
            datapoints: list[CostDataPoint] = []
            next_token: str | None = None

            while True:
                if next_token:
                    kwargs["NextPageToken"] = next_token

                response = await self.client.call("get_cost_and_usage", **kwargs)

                # Parse cost data from response
                for result in response.get("ResultsByTime", []):
                    start = datetime.fromisoformat(result["TimePeriod"]["Start"])
                    end = datetime.fromisoformat(result["TimePeriod"]["End"])
                    estimated = result.get("Estimated", False)

                    # Get the first metric value
                    total = result.get("Total", {})
                    if total:
                        metric_key = next(iter(total.keys()))
                        amount_str = total[metric_key]["Amount"]
                        unit = total[metric_key]["Unit"]

                        datapoint = CostDataPoint(
                            time_period_start=start,
                            time_period_end=end,
                            amount=Decimal(amount_str),
                            unit=unit,
                            estimated=estimated,
                        )
                        datapoints.append(datapoint)

                # Check for more results
                next_token = response.get("NextPageToken")
                if not next_token:
                    break

            logger.info(f"Retrieved {len(datapoints)} cost data point(s)")
            return datapoints

        except Exception as e:
            logger.error(f"Failed to get cost and usage: {e}")
            if isinstance(e, ValidationError):
                raise
            raise CostExplorerError(
                f"Failed to get cost and usage: {e}",
                service="ce",
                operation="get_cost_and_usage",
            ) from e

    async def get_instance_costs(
        self,
        instance_ids: Sequence[str],
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
    ) -> dict[str, list[CostDataPoint]]:
        """Get costs for specific EC2 instances.

        This method retrieves cost data for EC2 instances by filtering with
        resource tags or IDs.

        Args:
            instance_ids: List of EC2 instance IDs.
            start_date: Start of time period.
            end_date: End of time period.
            granularity: Time granularity. Defaults to "DAILY".

        Returns:
            Dictionary mapping instance IDs to their cost data points.

        Raises:
            ValidationError: If instance_ids is empty or parameters are invalid.
            CostExplorerError: If AWS API call fails.

        Example:
            >>> from datetime import datetime, timedelta
            >>> end = datetime.now()
            >>> start = end - timedelta(days=7)
            >>> costs = await manager.get_instance_costs(
            ...     instance_ids=["i-123", "i-456"],
            ...     start_date=start,
            ...     end_date=end
            ... )
        """
        if not instance_ids:
            raise ValidationError("instance_ids cannot be empty", service="ce")

        logger.info(f"Getting costs for {len(instance_ids)} instance(s)")

        result: dict[str, list[CostDataPoint]] = {iid: [] for iid in instance_ids}

        for instance_id in instance_ids:
            try:
                # Build filter for this instance
                filter_dict = {"Dimensions": {"Key": "RESOURCE_ID", "Values": [instance_id]}}

                kwargs: dict[str, Any] = {
                    "TimePeriod": {
                        "Start": start_date.strftime("%Y-%m-%d"),
                        "End": end_date.strftime("%Y-%m-%d"),
                    },
                    "Granularity": granularity,
                    "Metrics": ["UnblendedCost"],
                    "Filter": filter_dict,
                }

                response = await self.client.call("get_cost_and_usage", **kwargs)

                # Parse cost data
                for time_result in response.get("ResultsByTime", []):
                    start = datetime.fromisoformat(time_result["TimePeriod"]["Start"])
                    end = datetime.fromisoformat(time_result["TimePeriod"]["End"])

                    total = time_result.get("Total", {})
                    if total and "UnblendedCost" in total:
                        amount_str = total["UnblendedCost"]["Amount"]
                        unit = total["UnblendedCost"]["Unit"]

                        datapoint = CostDataPoint(
                            time_period_start=start,
                            time_period_end=end,
                            amount=Decimal(amount_str),
                            unit=unit,
                            estimated=time_result.get("Estimated", False),
                        )
                        result[instance_id].append(datapoint)

            except Exception as e:
                logger.warning(f"Failed to get costs for {instance_id}: {e}")

        logger.info(f"Retrieved costs for {len(result)} instance(s)")
        return result

    async def forecast_cost(
        self,
        start_date: datetime,
        end_date: datetime,
        metric: str = "UNBLENDED_COST",
        granularity: str = "DAILY",
    ) -> list[CostDataPoint]:
        """Forecast future costs based on historical usage.

        Args:
            start_date: Start of forecast period.
            end_date: End of forecast period.
            metric: Cost metric to forecast (UNBLENDED_COST, BLENDED_COST, etc.).
                Defaults to "UNBLENDED_COST".
            granularity: Time granularity. Defaults to "DAILY".

        Returns:
            List of forecasted cost data points.

        Raises:
            ValidationError: If parameters are invalid.
            CostExplorerError: If AWS API call fails.

        Example:
            >>> from datetime import datetime, timedelta
            >>> start = datetime.now()
            >>> end = start + timedelta(days=30)
            >>> forecast = await manager.forecast_cost(
            ...     start_date=start,
            ...     end_date=end
            ... )
        """
        if start_date >= end_date:
            raise ValidationError("start_date must be before end_date", service="ce")

        if granularity not in ("DAILY", "MONTHLY"):
            raise ValidationError(
                f"forecast granularity must be DAILY or MONTHLY, got {granularity}",
                service="ce",
            )

        logger.info(f"Forecasting costs from {start_date} to {end_date}")

        try:
            response = await self.client.call(
                "get_cost_forecast",
                TimePeriod={
                    "Start": start_date.strftime("%Y-%m-%d"),
                    "End": end_date.strftime("%Y-%m-%d"),
                },
                Metric=metric,
                Granularity=granularity,
            )

            # Parse forecast data
            datapoints: list[CostDataPoint] = []
            for forecast in response.get("ForecastResultsByTime", []):
                start = datetime.fromisoformat(forecast["TimePeriod"]["Start"])
                end = datetime.fromisoformat(forecast["TimePeriod"]["End"])
                amount_str = forecast["MeanValue"]

                datapoint = CostDataPoint(
                    time_period_start=start,
                    time_period_end=end,
                    amount=Decimal(amount_str),
                    unit="USD",
                    estimated=True,
                )
                datapoints.append(datapoint)

            logger.info(f"Retrieved {len(datapoints)} forecast data point(s)")
            return datapoints

        except Exception as e:
            logger.error(f"Failed to forecast costs: {e}")
            if isinstance(e, ValidationError):
                raise
            raise CostExplorerError(
                f"Failed to forecast costs: {e}",
                service="ce",
                operation="get_cost_forecast",
            ) from e

    async def get_cost_by_tag(
        self,
        tag_key: str,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, Decimal]:
        """Get cost aggregated by tag values.

        Note: Cost allocation tags must be activated in AWS for this to work.

        Args:
            tag_key: Tag key to group by (e.g., "Environment", "Team").
            start_date: Start of time period.
            end_date: End of time period.

        Returns:
            Dictionary mapping tag values to total costs.

        Raises:
            ValidationError: If tag_key is empty or parameters are invalid.
            CostExplorerError: If AWS API call fails.

        Example:
            >>> from datetime import datetime, timedelta
            >>> end = datetime.now()
            >>> start = end - timedelta(days=30)
            >>> costs = await manager.get_cost_by_tag(
            ...     tag_key="Environment",
            ...     start_date=start,
            ...     end_date=end
            ... )
            >>> print(f"Production cost: ${costs['Production']}")
        """
        if not tag_key:
            raise ValidationError("tag_key cannot be empty", service="ce")

        logger.info(f"Getting costs by tag: {tag_key}")

        try:
            response = await self.client.call(
                "get_cost_and_usage",
                TimePeriod={
                    "Start": start_date.strftime("%Y-%m-%d"),
                    "End": end_date.strftime("%Y-%m-%d"),
                },
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "TAG", "Key": tag_key}],
            )

            # Aggregate costs by tag value
            costs: dict[str, Decimal] = {}

            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    key = group["Keys"][0]
                    tag_value = key.split("$")[1] if "$" in key else key
                    amount_str = group["Metrics"]["UnblendedCost"]["Amount"]
                    amount = Decimal(amount_str)

                    if tag_value in costs:
                        costs[tag_value] += amount
                    else:
                        costs[tag_value] = amount

            logger.info(f"Found costs for {len(costs)} tag value(s)")
            return costs

        except Exception as e:
            logger.error(f"Failed to get cost by tag: {e}")
            if isinstance(e, ValidationError):
                raise
            raise CostExplorerError(
                f"Failed to get cost by tag: {e}",
                service="ce",
                operation="get_cost_and_usage",
            ) from e

    def _build_filter(self, filter_criteria: CostFilter) -> dict[str, Any]:
        """Build AWS Cost Explorer filter from filter criteria.

        Args:
            filter_criteria: Filter criteria object.

        Returns:
            AWS API filter dictionary.
        """
        filters: list[dict[str, Any]] = []

        if filter_criteria.service:
            filters.append({"Dimensions": {"Key": "SERVICE", "Values": [filter_criteria.service]}})

        if filter_criteria.instance_types:
            filters.append(
                {"Dimensions": {"Key": "INSTANCE_TYPE", "Values": filter_criteria.instance_types}}
            )

        if filter_criteria.tags:
            for key, value in filter_criteria.tags.items():
                filters.append({"Tags": {"Key": key, "Values": [value]}})

        if len(filters) == 0:
            return {}
        if len(filters) == 1:
            return filters[0]

        # Multiple filters - use AND logic
        return {"And": filters}
