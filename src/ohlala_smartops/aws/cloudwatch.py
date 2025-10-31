"""CloudWatch metrics utilities.

This module provides high-level utilities for working with AWS CloudWatch metrics,
including retrieving metric statistics, publishing custom metrics, and listing
available metrics. All operations use the AWSClientWrapper for automatic throttling
and error handling.
"""

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

from pydantic import BaseModel, Field, field_validator

from ohlala_smartops.aws.client import AWSClientWrapper, create_aws_client
from ohlala_smartops.aws.exceptions import CloudWatchError, ValidationError

logger: Final = logging.getLogger(__name__)


class MetricDataPoint(BaseModel):
    """Model representing a CloudWatch metric data point.

    Attributes:
        timestamp: Data point timestamp.
        value: Metric value.
        unit: Metric unit (e.g., "Bytes", "Percent", "Count"). Optional.
        minimum: Minimum value for the time period (optional).
        maximum: Maximum value for the time period (optional).
        sample_count: Number of samples (optional).
        sum: Sum of all values (optional).
    """

    timestamp: datetime
    value: float
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    sample_count: float | None = None
    sum: float | None = None


class CloudWatchMetric(BaseModel):
    """Model representing a CloudWatch metric.

    Attributes:
        namespace: CloudWatch namespace (e.g., "AWS/EC2", "CustomApp").
        metric_name: Metric name (e.g., "CPUUtilization", "NetworkIn").
        dimensions: Metric dimensions as key-value pairs. Defaults to empty dict.
    """

    namespace: str = Field(..., min_length=1)
    metric_name: str = Field(..., min_length=1)
    dimensions: dict[str, str] = Field(default_factory=dict)

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, v: str) -> str:
        """Validate namespace format.

        Args:
            v: Namespace string.

        Returns:
            Validated namespace string.

        Raises:
            ValueError: If namespace exceeds max length or has invalid format.
        """
        if len(v) > 256:
            raise ValueError("Namespace cannot exceed 256 characters")
        return v


class CloudWatchManager:
    """Manager for CloudWatch metrics operations with automatic throttling.

    This class provides high-level methods for working with CloudWatch metrics.
    It supports retrieving metric statistics, publishing custom metrics, and
    discovering available metrics.

    All operations use the AWSClientWrapper for automatic rate limiting, error
    handling, and retries.

    Example:
        >>> manager = CloudWatchManager(region="us-east-1")
        >>> # Get EC2 instance CPU metrics
        >>> from datetime import datetime, timedelta
        >>> end_time = datetime.now()
        >>> start_time = end_time - timedelta(hours=1)
        >>> datapoints = await manager.get_metric_statistics(
        ...     namespace="AWS/EC2",
        ...     metric_name="CPUUtilization",
        ...     dimensions={"InstanceId": "i-123"},
        ...     start_time=start_time,
        ...     end_time=end_time,
        ...     period=300,
        ...     statistics=["Average", "Maximum"]
        ... )
    """

    def __init__(self, region: str | None = None, client: AWSClientWrapper | None = None) -> None:
        """Initialize CloudWatch manager.

        Args:
            region: AWS region name. If None, uses default from environment/config.
                Defaults to None.
            client: Optional pre-configured AWSClientWrapper for CloudWatch. If None,
                creates a new one. Defaults to None.

        Example:
            >>> manager = CloudWatchManager(region="us-west-2")
            >>> # Or with existing client:
            >>> client = create_aws_client("cloudwatch", region="eu-west-1")
            >>> manager = CloudWatchManager(client=client)
        """
        self.region = region
        self.client = client or create_aws_client("cloudwatch", region=region)
        logger.info(f"Initialized CloudWatchManager for region {region or 'default'}")

    async def get_metric_statistics(
        self,
        namespace: str,
        metric_name: str,
        dimensions: dict[str, str],
        start_time: datetime,
        end_time: datetime,
        period: int = 300,
        statistics: Sequence[str] = ("Average",),
        extended_statistics: Sequence[str] | None = None,
        unit: str | None = None,
    ) -> list[MetricDataPoint]:
        """Get statistics for a CloudWatch metric.

        Args:
            namespace: CloudWatch namespace (e.g., "AWS/EC2").
            metric_name: Metric name (e.g., "CPUUtilization").
            dimensions: Dimensions to filter by (e.g., {"InstanceId": "i-123"}).
            start_time: Start of time range (inclusive).
            end_time: End of time range (exclusive).
            period: Granularity in seconds (60, 300, 3600, etc.). Must align with
                CloudWatch retention policies. Defaults to 300 (5 minutes).
            statistics: Statistics to retrieve (Average, Sum, Min, Max, SampleCount).
                Defaults to ("Average",).
            extended_statistics: Extended statistics (percentiles like p99, p95).
                Defaults to None.
            unit: Filter results by unit (Bytes, Percent, etc.). Defaults to None.

        Returns:
            List of MetricDataPoint objects with requested statistics.

        Raises:
            ValidationError: If parameters are invalid.
            CloudWatchError: If AWS API call fails.

        Example:
            >>> from datetime import datetime, timedelta
            >>> end = datetime.now()
            >>> start = end - timedelta(hours=1)
            >>> points = await manager.get_metric_statistics(
            ...     namespace="AWS/EC2",
            ...     metric_name="CPUUtilization",
            ...     dimensions={"InstanceId": "i-123"},
            ...     start_time=start,
            ...     end_time=end,
            ...     period=300,
            ...     statistics=["Average", "Maximum"],
            ...     extended_statistics=["p99"]
            ... )
        """
        if not namespace or not metric_name:
            raise ValidationError("namespace and metric_name are required", service="cloudwatch")

        if start_time >= end_time:
            raise ValidationError("start_time must be before end_time", service="cloudwatch")

        if period < 1:
            raise ValidationError("period must be at least 1 second", service="cloudwatch")

        logger.debug(
            f"Getting statistics for {namespace}/{metric_name} from " f"{start_time} to {end_time}"
        )

        try:
            # Build dimensions in AWS format
            aws_dimensions = [{"Name": k, "Value": v} for k, v in dimensions.items()]

            # Build API parameters
            kwargs: dict[str, Any] = {
                "Namespace": namespace,
                "MetricName": metric_name,
                "Dimensions": aws_dimensions,
                "StartTime": start_time,
                "EndTime": end_time,
                "Period": period,
            }

            if statistics:
                kwargs["Statistics"] = list(statistics)

            if extended_statistics:
                kwargs["ExtendedStatistics"] = list(extended_statistics)

            if unit:
                kwargs["Unit"] = unit

            response = await self.client.call("get_metric_statistics", **kwargs)

            # Parse datapoints from response
            datapoints: list[MetricDataPoint] = []
            for point_data in response.get("Datapoints", []):
                # CloudWatch returns different fields based on statistics requested
                value = (
                    point_data.get("Average")
                    or point_data.get("Sum")
                    or point_data.get("Maximum")
                    or point_data.get("Minimum")
                    or 0.0
                )

                datapoint = MetricDataPoint(
                    timestamp=point_data["Timestamp"],
                    value=value,
                    unit=point_data.get("Unit"),
                    minimum=point_data.get("Minimum"),
                    maximum=point_data.get("Maximum"),
                    sample_count=point_data.get("SampleCount"),
                    sum=point_data.get("Sum"),
                )
                datapoints.append(datapoint)

            # Sort by timestamp
            datapoints.sort(key=lambda d: d.timestamp)

            logger.info(f"Retrieved {len(datapoints)} data point(s) for {metric_name}")
            return datapoints

        except Exception as e:
            logger.error(f"Failed to get metric statistics: {e}")
            if isinstance(e, ValidationError):
                raise
            raise CloudWatchError(
                f"Failed to get metric statistics: {e}",
                service="cloudwatch",
                operation="get_metric_statistics",
            ) from e

    async def put_metric_data(
        self,
        namespace: str,
        metric_name: str,
        value: float,
        dimensions: dict[str, str] | None = None,
        timestamp: datetime | None = None,
        unit: str | None = None,
        storage_resolution: int = 60,
    ) -> None:
        """Publish a custom metric data point to CloudWatch.

        Args:
            namespace: CloudWatch namespace (cannot start with "AWS/").
            metric_name: Metric name.
            value: Metric value.
            dimensions: Optional dimensions (up to 30). Defaults to None.
            timestamp: Data point timestamp. If None, uses current time. Defaults to None.
            unit: Metric unit (Seconds, Bytes, Percent, Count, etc.). Defaults to None.
            storage_resolution: Storage resolution in seconds (1 or 60). High-resolution
                metrics use 1. Defaults to 60.

        Raises:
            ValidationError: If parameters are invalid.
            CloudWatchError: If AWS API call fails.

        Example:
            >>> from datetime import datetime
            >>> await manager.put_metric_data(
            ...     namespace="CustomApp/Performance",
            ...     metric_name="RequestDuration",
            ...     value=145.3,
            ...     dimensions={"Endpoint": "/api/users", "Method": "GET"},
            ...     unit="Milliseconds"
            ... )
        """
        if not namespace or not metric_name:
            raise ValidationError("namespace and metric_name are required", service="cloudwatch")

        if namespace.startswith("AWS/"):
            raise ValidationError(
                "Custom namespaces cannot start with 'AWS/'", service="cloudwatch"
            )

        if storage_resolution not in (1, 60):
            raise ValidationError(
                "storage_resolution must be 1 (high-resolution) or 60 (standard)",
                service="cloudwatch",
            )

        logger.debug(f"Publishing metric data: {namespace}/{metric_name} = {value}")

        try:
            # Build metric datum
            metric_datum: dict[str, Any] = {
                "MetricName": metric_name,
                "Value": value,
                "StorageResolution": storage_resolution,
            }

            if timestamp:
                metric_datum["Timestamp"] = timestamp

            if unit:
                metric_datum["Unit"] = unit

            if dimensions:
                if len(dimensions) > 30:
                    raise ValidationError(
                        "Maximum 30 dimensions allowed per metric", service="cloudwatch"
                    )
                metric_datum["Dimensions"] = [
                    {"Name": k, "Value": v} for k, v in dimensions.items()
                ]

            await self.client.call(
                "put_metric_data", Namespace=namespace, MetricData=[metric_datum]
            )

            logger.info(f"Successfully published metric {namespace}/{metric_name}")

        except Exception as e:
            logger.error(f"Failed to put metric data: {e}")
            if isinstance(e, ValidationError):
                raise
            raise CloudWatchError(
                f"Failed to put metric data: {e}",
                service="cloudwatch",
                operation="put_metric_data",
            ) from e

    async def list_metrics(
        self,
        namespace: str | None = None,
        metric_name: str | None = None,
        dimensions: dict[str, str] | None = None,
    ) -> list[CloudWatchMetric]:
        """List available CloudWatch metrics with optional filtering.

        Args:
            namespace: Filter by namespace. Defaults to None (all namespaces).
            metric_name: Filter by metric name. Defaults to None (all metrics).
            dimensions: Filter by dimensions. Defaults to None (all dimensions).

        Returns:
            List of CloudWatchMetric objects.

        Raises:
            CloudWatchError: If AWS API call fails.

        Example:
            >>> # List all EC2 metrics
            >>> metrics = await manager.list_metrics(namespace="AWS/EC2")
            >>>
            >>> # List specific metric for an instance
            >>> metrics = await manager.list_metrics(
            ...     namespace="AWS/EC2",
            ...     metric_name="CPUUtilization",
            ...     dimensions={"InstanceId": "i-123"}
            ... )
        """
        logger.debug(
            f"Listing metrics: namespace={namespace}, metric_name={metric_name}, "
            f"dimensions={dimensions is not None}"
        )

        try:
            # Build API parameters
            kwargs: dict[str, Any] = {}

            if namespace:
                kwargs["Namespace"] = namespace

            if metric_name:
                kwargs["MetricName"] = metric_name

            if dimensions:
                kwargs["Dimensions"] = [{"Name": k, "Value": v} for k, v in dimensions.items()]

            # Handle pagination
            metrics: list[CloudWatchMetric] = []
            next_token: str | None = None

            while True:
                if next_token:
                    kwargs["NextToken"] = next_token

                response = await self.client.call("list_metrics", **kwargs)

                # Parse metrics from response
                for metric_data in response.get("Metrics", []):
                    # Parse dimensions
                    dims = {d["Name"]: d["Value"] for d in metric_data.get("Dimensions", [])}

                    metric = CloudWatchMetric(
                        namespace=metric_data["Namespace"],
                        metric_name=metric_data["MetricName"],
                        dimensions=dims,
                    )
                    metrics.append(metric)

                # Check for more results
                next_token = response.get("NextToken")
                if not next_token:
                    break

            logger.info(f"Found {len(metrics)} metric(s)")
            return metrics

        except Exception as e:
            logger.error(f"Failed to list metrics: {e}")
            raise CloudWatchError(
                f"Failed to list metrics: {e}",
                service="cloudwatch",
                operation="list_metrics",
            ) from e

    async def get_instance_metrics(
        self,
        instance_id: str,
        metric_names: Sequence[str],
        start_time: datetime,
        end_time: datetime,
        period: int = 300,
        statistics: Sequence[str] = ("Average",),
    ) -> dict[str, list[MetricDataPoint]]:
        """Get multiple EC2 instance metrics in a single call.

        This is a convenience method that retrieves multiple metrics for an EC2
        instance simultaneously.

        Args:
            instance_id: EC2 instance ID.
            metric_names: List of metric names (CPUUtilization, NetworkIn, etc.).
            start_time: Start of time range.
            end_time: End of time range.
            period: Granularity in seconds. Defaults to 300.
            statistics: Statistics to retrieve. Defaults to ("Average",).

        Returns:
            Dictionary mapping metric names to lists of data points.

        Raises:
            ValidationError: If instance_id or metric_names are empty.
            CloudWatchError: If AWS API call fails.

        Example:
            >>> from datetime import datetime, timedelta
            >>> end = datetime.now()
            >>> start = end - timedelta(hours=1)
            >>> metrics = await manager.get_instance_metrics(
            ...     instance_id="i-123",
            ...     metric_names=["CPUUtilization", "NetworkIn", "DiskReadBytes"],
            ...     start_time=start,
            ...     end_time=end
            ... )
            >>> cpu_metrics = metrics['CPUUtilization']
            >>> avg_cpu = sum(p.value for p in cpu_metrics) / len(cpu_metrics)
            >>> print(f"Average CPU: {avg_cpu}")
        """
        if not instance_id:
            raise ValidationError("instance_id cannot be empty", service="cloudwatch")

        if not metric_names:
            raise ValidationError("metric_names cannot be empty", service="cloudwatch")

        logger.info(f"Getting {len(metric_names)} metric(s) for instance {instance_id}")

        result: dict[str, list[MetricDataPoint]] = {}

        for metric_name in metric_names:
            try:
                datapoints = await self.get_metric_statistics(
                    namespace="AWS/EC2",
                    metric_name=metric_name,
                    dimensions={"InstanceId": instance_id},
                    start_time=start_time,
                    end_time=end_time,
                    period=period,
                    statistics=statistics,
                )
                result[metric_name] = datapoints

            except Exception as e:
                logger.warning(f"Failed to get {metric_name} for {instance_id}: {e}")
                result[metric_name] = []

        logger.info(
            f"Retrieved metrics for {instance_id}: "
            f"{sum(len(v) for v in result.values())} total data points"
        )
        return result
