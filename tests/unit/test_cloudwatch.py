"""Tests for CloudWatch metrics utilities."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from ohlala_smartops.aws.cloudwatch import (
    CloudWatchManager,
    CloudWatchMetric,
    MetricDataPoint,
)
from ohlala_smartops.aws.exceptions import CloudWatchError, ValidationError


class TestMetricDataPoint:
    """Test suite for MetricDataPoint Pydantic model."""

    def test_valid_datapoint_creation(self) -> None:
        """Test creating a valid MetricDataPoint."""
        timestamp = datetime.now(UTC)
        point = MetricDataPoint(timestamp=timestamp, value=45.5, unit="Percent")

        assert point.timestamp == timestamp
        assert point.value == 45.5
        assert point.unit == "Percent"

    def test_datapoint_with_all_fields(self) -> None:
        """Test MetricDataPoint with all optional fields."""
        timestamp = datetime.now(UTC)
        point = MetricDataPoint(
            timestamp=timestamp,
            value=75.0,
            unit="Percent",
            minimum=50.0,
            maximum=90.0,
            sample_count=10.0,
            sum=750.0,
        )

        assert point.minimum == 50.0
        assert point.maximum == 90.0
        assert point.sample_count == 10.0
        assert point.sum == 750.0


class TestCloudWatchMetric:
    """Test suite for CloudWatchMetric Pydantic model."""

    def test_valid_metric_creation(self) -> None:
        """Test creating a valid CloudWatchMetric."""
        metric = CloudWatchMetric(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions={"InstanceId": "i-123"},
        )

        assert metric.namespace == "AWS/EC2"
        assert metric.metric_name == "CPUUtilization"
        assert metric.dimensions == {"InstanceId": "i-123"}

    def test_metric_with_no_dimensions(self) -> None:
        """Test CloudWatchMetric with empty dimensions."""
        metric = CloudWatchMetric(namespace="AWS/S3", metric_name="BucketSize")

        assert metric.dimensions == {}

    def test_metric_namespace_too_long(self) -> None:
        """Test that namespace exceeding 256 characters raises validation error."""
        with pytest.raises(ValueError, match="Namespace cannot exceed 256 characters"):
            CloudWatchMetric(namespace="a" * 257, metric_name="Test")

    def test_metric_empty_namespace(self) -> None:
        """Test that empty namespace raises validation error."""
        with pytest.raises(PydanticValidationError):
            CloudWatchMetric(namespace="", metric_name="Test")

    def test_metric_empty_name(self) -> None:
        """Test that empty metric_name raises validation error."""
        with pytest.raises(PydanticValidationError):
            CloudWatchMetric(namespace="Custom/App", metric_name="")


class TestCloudWatchManager:
    """Test suite for CloudWatchManager class."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Fixture providing a mocked AWSClientWrapper."""
        client = Mock()
        client.call = AsyncMock()
        return client

    @pytest.fixture
    def cloudwatch_manager(self, mock_client: Mock) -> CloudWatchManager:
        """Fixture providing a CloudWatchManager with mocked client."""
        return CloudWatchManager(region="us-east-1", client=mock_client)

    # Tests for get_metric_statistics()

    @pytest.mark.asyncio
    async def test_get_metric_statistics_success(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test getting metric statistics successfully."""
        timestamp1 = datetime.now(UTC)
        timestamp2 = timestamp1 + timedelta(minutes=5)

        mock_client.call.return_value = {
            "Datapoints": [
                {"Timestamp": timestamp1, "Average": 45.5, "Unit": "Percent"},
                {"Timestamp": timestamp2, "Average": 50.2, "Unit": "Percent"},
            ]
        }

        start_time = timestamp1 - timedelta(hours=1)
        end_time = timestamp1 + timedelta(hours=1)

        datapoints = await cloudwatch_manager.get_metric_statistics(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions={"InstanceId": "i-123"},
            start_time=start_time,
            end_time=end_time,
            period=300,
            statistics=["Average"],
        )

        assert len(datapoints) == 2
        assert datapoints[0].value == 45.5
        assert datapoints[1].value == 50.2
        mock_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_metric_statistics_with_extended_stats(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test getting metric statistics with extended statistics."""
        timestamp = datetime.now(UTC)
        mock_client.call.return_value = {"Datapoints": [{"Timestamp": timestamp, "Average": 45.5}]}

        start_time = timestamp - timedelta(hours=1)
        end_time = timestamp + timedelta(hours=1)

        await cloudwatch_manager.get_metric_statistics(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions={"InstanceId": "i-123"},
            start_time=start_time,
            end_time=end_time,
            extended_statistics=["p99", "p95"],
        )

        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["ExtendedStatistics"] == ["p99", "p95"]

    @pytest.mark.asyncio
    async def test_get_metric_statistics_empty_result(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test getting metric statistics with no data."""
        mock_client.call.return_value = {"Datapoints": []}

        timestamp = datetime.now(UTC)
        datapoints = await cloudwatch_manager.get_metric_statistics(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions={"InstanceId": "i-123"},
            start_time=timestamp - timedelta(hours=1),
            end_time=timestamp,
        )

        assert datapoints == []

    @pytest.mark.asyncio
    async def test_get_metric_statistics_empty_namespace(
        self, cloudwatch_manager: CloudWatchManager
    ) -> None:
        """Test that empty namespace raises ValidationError."""
        timestamp = datetime.now(UTC)

        with pytest.raises(ValidationError, match="namespace and metric_name are required"):
            await cloudwatch_manager.get_metric_statistics(
                namespace="",
                metric_name="Test",
                dimensions={},
                start_time=timestamp - timedelta(hours=1),
                end_time=timestamp,
            )

    @pytest.mark.asyncio
    async def test_get_metric_statistics_invalid_time_range(
        self, cloudwatch_manager: CloudWatchManager
    ) -> None:
        """Test that invalid time range raises ValidationError."""
        timestamp = datetime.now(UTC)

        with pytest.raises(ValidationError, match="start_time must be before end_time"):
            await cloudwatch_manager.get_metric_statistics(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions={},
                start_time=timestamp,
                end_time=timestamp - timedelta(hours=1),
            )

    @pytest.mark.asyncio
    async def test_get_metric_statistics_invalid_period(
        self, cloudwatch_manager: CloudWatchManager
    ) -> None:
        """Test that invalid period raises ValidationError."""
        timestamp = datetime.now(UTC)

        with pytest.raises(ValidationError, match="period must be at least 1 second"):
            await cloudwatch_manager.get_metric_statistics(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions={},
                start_time=timestamp - timedelta(hours=1),
                end_time=timestamp,
                period=0,
            )

    @pytest.mark.asyncio
    async def test_get_metric_statistics_aws_error(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in CloudWatchError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        timestamp = datetime.now(UTC)

        with pytest.raises(CloudWatchError, match="Failed to get metric statistics"):
            await cloudwatch_manager.get_metric_statistics(
                namespace="AWS/EC2",
                metric_name="CPUUtilization",
                dimensions={},
                start_time=timestamp - timedelta(hours=1),
                end_time=timestamp,
            )

    # Tests for put_metric_data()

    @pytest.mark.asyncio
    async def test_put_metric_data_success(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test publishing metric data successfully."""
        mock_client.call.return_value = {}

        await cloudwatch_manager.put_metric_data(
            namespace="CustomApp/Performance",
            metric_name="RequestDuration",
            value=145.3,
            dimensions={"Endpoint": "/api/users"},
            unit="Milliseconds",
        )

        mock_client.call.assert_called_once()
        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["Namespace"] == "CustomApp/Performance"
        assert call_kwargs["MetricData"][0]["MetricName"] == "RequestDuration"
        assert call_kwargs["MetricData"][0]["Value"] == 145.3

    @pytest.mark.asyncio
    async def test_put_metric_data_with_timestamp(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test publishing metric data with timestamp."""
        mock_client.call.return_value = {}
        timestamp = datetime.now(UTC)

        await cloudwatch_manager.put_metric_data(
            namespace="Custom/App",
            metric_name="Requests",
            value=100,
            timestamp=timestamp,
        )

        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["MetricData"][0]["Timestamp"] == timestamp

    @pytest.mark.asyncio
    async def test_put_metric_data_high_resolution(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test publishing high-resolution metric data."""
        mock_client.call.return_value = {}

        await cloudwatch_manager.put_metric_data(
            namespace="Custom/App",
            metric_name="Latency",
            value=12.5,
            storage_resolution=1,
        )

        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["MetricData"][0]["StorageResolution"] == 1

    @pytest.mark.asyncio
    async def test_put_metric_data_aws_namespace(
        self, cloudwatch_manager: CloudWatchManager
    ) -> None:
        """Test that AWS namespace raises ValidationError."""
        with pytest.raises(ValidationError, match="cannot start with 'AWS/'"):
            await cloudwatch_manager.put_metric_data(
                namespace="AWS/Custom", metric_name="Test", value=1.0
            )

    @pytest.mark.asyncio
    async def test_put_metric_data_too_many_dimensions(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test that too many dimensions raises ValidationError."""
        mock_client.call.return_value = {}
        dimensions = {f"Dim{i}": f"Value{i}" for i in range(31)}

        with pytest.raises(ValidationError, match="Maximum 30 dimensions"):
            await cloudwatch_manager.put_metric_data(
                namespace="Custom/App",
                metric_name="Test",
                value=1.0,
                dimensions=dimensions,
            )

    @pytest.mark.asyncio
    async def test_put_metric_data_invalid_storage_resolution(
        self, cloudwatch_manager: CloudWatchManager
    ) -> None:
        """Test that invalid storage_resolution raises ValidationError."""
        with pytest.raises(ValidationError, match="storage_resolution must be"):
            await cloudwatch_manager.put_metric_data(
                namespace="Custom/App",
                metric_name="Test",
                value=1.0,
                storage_resolution=30,
            )

    @pytest.mark.asyncio
    async def test_put_metric_data_aws_error(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in CloudWatchError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(CloudWatchError, match="Failed to put metric data"):
            await cloudwatch_manager.put_metric_data(
                namespace="Custom/App", metric_name="Test", value=1.0
            )

    # Tests for list_metrics()

    @pytest.mark.asyncio
    async def test_list_metrics_all(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test listing all metrics."""
        mock_client.call.return_value = {
            "Metrics": [
                {
                    "Namespace": "AWS/EC2",
                    "MetricName": "CPUUtilization",
                    "Dimensions": [{"Name": "InstanceId", "Value": "i-123"}],
                },
                {
                    "Namespace": "AWS/EC2",
                    "MetricName": "NetworkIn",
                    "Dimensions": [{"Name": "InstanceId", "Value": "i-123"}],
                },
            ]
        }

        metrics = await cloudwatch_manager.list_metrics()

        assert len(metrics) == 2
        assert metrics[0].namespace == "AWS/EC2"
        assert metrics[0].metric_name == "CPUUtilization"

    @pytest.mark.asyncio
    async def test_list_metrics_filtered(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test listing metrics with filters."""
        mock_client.call.return_value = {
            "Metrics": [
                {
                    "Namespace": "AWS/EC2",
                    "MetricName": "CPUUtilization",
                    "Dimensions": [{"Name": "InstanceId", "Value": "i-123"}],
                }
            ]
        }

        metrics = await cloudwatch_manager.list_metrics(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimensions={"InstanceId": "i-123"},
        )

        assert len(metrics) == 1
        mock_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_metrics_pagination(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test listing metrics with pagination."""
        mock_client.call.side_effect = [
            {
                "Metrics": [
                    {
                        "Namespace": "AWS/EC2",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [],
                    }
                ],
                "NextToken": "token1",
            },
            {"Metrics": [{"Namespace": "AWS/EC2", "MetricName": "NetworkIn", "Dimensions": []}]},
        ]

        metrics = await cloudwatch_manager.list_metrics()

        assert len(metrics) == 2
        assert mock_client.call.call_count == 2

    @pytest.mark.asyncio
    async def test_list_metrics_empty_result(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test listing metrics with no results."""
        mock_client.call.return_value = {"Metrics": []}

        metrics = await cloudwatch_manager.list_metrics()

        assert metrics == []

    @pytest.mark.asyncio
    async def test_list_metrics_aws_error(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in CloudWatchError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(CloudWatchError, match="Failed to list metrics"):
            await cloudwatch_manager.list_metrics()

    # Tests for get_instance_metrics()

    @pytest.mark.asyncio
    async def test_get_instance_metrics_success(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test getting multiple instance metrics successfully."""
        timestamp = datetime.now(UTC)
        mock_client.call.return_value = {"Datapoints": [{"Timestamp": timestamp, "Average": 45.5}]}

        start_time = timestamp - timedelta(hours=1)
        end_time = timestamp

        metrics = await cloudwatch_manager.get_instance_metrics(
            instance_id="i-123",
            metric_names=["CPUUtilization", "NetworkIn"],
            start_time=start_time,
            end_time=end_time,
        )

        assert len(metrics) == 2
        assert "CPUUtilization" in metrics
        assert "NetworkIn" in metrics
        assert len(metrics["CPUUtilization"]) == 1

    @pytest.mark.asyncio
    async def test_get_instance_metrics_empty_instance_id(
        self, cloudwatch_manager: CloudWatchManager
    ) -> None:
        """Test that empty instance_id raises ValidationError."""
        timestamp = datetime.now(UTC)

        with pytest.raises(ValidationError, match="instance_id cannot be empty"):
            await cloudwatch_manager.get_instance_metrics(
                instance_id="",
                metric_names=["CPUUtilization"],
                start_time=timestamp - timedelta(hours=1),
                end_time=timestamp,
            )

    @pytest.mark.asyncio
    async def test_get_instance_metrics_empty_metric_names(
        self, cloudwatch_manager: CloudWatchManager
    ) -> None:
        """Test that empty metric_names raises ValidationError."""
        timestamp = datetime.now(UTC)

        with pytest.raises(ValidationError, match="metric_names cannot be empty"):
            await cloudwatch_manager.get_instance_metrics(
                instance_id="i-123",
                metric_names=[],
                start_time=timestamp - timedelta(hours=1),
                end_time=timestamp,
            )

    @pytest.mark.asyncio
    async def test_get_instance_metrics_partial_failure(
        self, cloudwatch_manager: CloudWatchManager, mock_client: Mock
    ) -> None:
        """Test get_instance_metrics with partial failures."""
        timestamp = datetime.now(UTC)

        # First call succeeds, second fails
        mock_client.call.side_effect = [
            {"Datapoints": [{"Timestamp": timestamp, "Average": 45.5}]},
            Exception("API Error"),
        ]

        start_time = timestamp - timedelta(hours=1)
        end_time = timestamp

        metrics = await cloudwatch_manager.get_instance_metrics(
            instance_id="i-123",
            metric_names=["CPUUtilization", "NetworkIn"],
            start_time=start_time,
            end_time=end_time,
        )

        assert len(metrics["CPUUtilization"]) == 1
        assert metrics["NetworkIn"] == []

    # Tests for initialization

    def test_cloudwatch_manager_with_region(self) -> None:
        """Test CloudWatchManager initialization with region."""
        manager = CloudWatchManager(region="us-west-2")

        assert manager.region == "us-west-2"
        assert manager.client is not None

    def test_cloudwatch_manager_with_client(self, mock_client: Mock) -> None:
        """Test CloudWatchManager initialization with pre-configured client."""
        manager = CloudWatchManager(client=mock_client)

        assert manager.client is mock_client

    def test_cloudwatch_manager_default_region(self) -> None:
        """Test CloudWatchManager initialization with default region."""
        with patch("ohlala_smartops.aws.cloudwatch.create_aws_client") as mock_create:
            manager = CloudWatchManager()

            assert manager.region is None
            mock_create.assert_called_once_with("cloudwatch", region=None)
