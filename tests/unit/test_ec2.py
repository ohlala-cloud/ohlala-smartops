"""Tests for EC2 instance management utilities."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from ohlala_smartops.aws.ec2 import EC2Instance, EC2Manager
from ohlala_smartops.aws.exceptions import EC2Error, ValidationError


class TestEC2Instance:
    """Test suite for EC2Instance Pydantic model."""

    def test_valid_instance_creation(self) -> None:
        """Test creating a valid EC2Instance."""
        instance = EC2Instance(
            instance_id="i-1234567890abcdef",
            instance_type="t3.micro",
            state="running",
            availability_zone="us-east-1a",
            private_ip="10.0.1.5",
            public_ip="54.123.45.67",
            launch_time="2024-01-15T10:30:00+00:00",
            tags={"Name": "web-server", "Environment": "production"},
        )

        assert instance.instance_id == "i-1234567890abcdef"
        assert instance.instance_type == "t3.micro"
        assert instance.state == "running"
        assert instance.availability_zone == "us-east-1a"
        assert instance.tags["Name"] == "web-server"

    def test_instance_with_minimal_fields(self) -> None:
        """Test EC2Instance with only required fields."""
        instance = EC2Instance(
            instance_id="i-abcdef1234567890",
            instance_type="m5.large",
            state="stopped",
        )

        assert instance.instance_id == "i-abcdef1234567890"
        assert instance.state == "stopped"
        assert instance.private_ip is None
        assert instance.public_ip is None
        assert instance.tags == {}

    def test_invalid_instance_id_format(self) -> None:
        """Test that invalid instance ID format raises validation error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            EC2Instance(
                instance_id="invalid-id",
                instance_type="t3.micro",
                state="running",
            )

        assert "instance_id" in str(exc_info.value)

    def test_invalid_instance_state(self) -> None:
        """Test that invalid instance state raises validation error."""
        with pytest.raises(ValueError, match="Invalid instance state"):
            EC2Instance(
                instance_id="i-1234567890abcdef",
                instance_type="t3.micro",
                state="invalid-state",
            )

    def test_valid_instance_states(self) -> None:
        """Test all valid instance states."""
        valid_states = ["pending", "running", "shutting-down", "terminated", "stopping", "stopped"]

        for state in valid_states:
            instance = EC2Instance(
                instance_id="i-1234567890abcdef",
                instance_type="t3.micro",
                state=state,
            )
            assert instance.state == state

    def test_tags_default_to_empty_dict(self) -> None:
        """Test that tags default to empty dict."""
        instance = EC2Instance(
            instance_id="i-1234567890abcdef",
            instance_type="t3.micro",
            state="running",
        )

        assert instance.tags == {}
        assert isinstance(instance.tags, dict)


class TestEC2Manager:
    """Test suite for EC2Manager class."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Fixture providing a mocked AWSClientWrapper."""
        client = Mock()
        client.call = AsyncMock()
        return client

    @pytest.fixture
    def manager(self, mock_client: Mock) -> EC2Manager:
        """Fixture providing an EC2Manager with mocked client."""
        return EC2Manager(region="us-east-1", client=mock_client)

    def test_initialization_with_region(self) -> None:
        """Test EC2Manager initialization with region."""
        with patch("ohlala_smartops.aws.ec2.create_aws_client") as mock_create:
            manager = EC2Manager(region="us-west-2")

            assert manager.region == "us-west-2"
            mock_create.assert_called_once_with("ec2", region="us-west-2")

    def test_initialization_with_client(self, mock_client: Mock) -> None:
        """Test EC2Manager initialization with existing client."""
        manager = EC2Manager(client=mock_client)

        assert manager.client is mock_client
        assert manager.region is None

    @pytest.mark.asyncio
    async def test_describe_instances_with_ids(
        self, manager: EC2Manager, mock_client: Mock
    ) -> None:
        """Test describing specific instances by ID."""
        mock_client.call.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-1234567890abcdef",
                            "InstanceType": "t3.micro",
                            "State": {"Name": "running"},
                            "Placement": {"AvailabilityZone": "us-east-1a"},
                            "PrivateIpAddress": "10.0.1.5",
                            "Tags": [{"Key": "Name", "Value": "test-server"}],
                        }
                    ]
                }
            ]
        }

        instances = await manager.describe_instances(instance_ids=["i-1234567890abcdef"])

        assert len(instances) == 1
        assert instances[0].instance_id == "i-1234567890abcdef"
        assert instances[0].instance_type == "t3.micro"
        assert instances[0].state == "running"
        assert instances[0].tags["Name"] == "test-server"
        mock_client.call.assert_called_once_with("describe_instances", InstanceIds=["i-1234567890abcdef"])

    @pytest.mark.asyncio
    async def test_describe_instances_with_filters(
        self, manager: EC2Manager, mock_client: Mock
    ) -> None:
        """Test describing instances with filters."""
        mock_client.call.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-abcdef1234567890",
                            "InstanceType": "m5.large",
                            "State": {"Name": "stopped"},
                        }
                    ]
                }
            ]
        }

        filters = [{"Name": "instance-state-name", "Values": ["stopped"]}]
        instances = await manager.describe_instances(filters=filters)

        assert len(instances) == 1
        assert instances[0].state == "stopped"
        mock_client.call.assert_called_once_with("describe_instances", Filters=filters)

    @pytest.mark.asyncio
    async def test_describe_instances_multiple_reservations(
        self, manager: EC2Manager, mock_client: Mock
    ) -> None:
        """Test describing instances across multiple reservations."""
        mock_client.call.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-111111111111111a",
                            "InstanceType": "t3.micro",
                            "State": {"Name": "running"},
                        }
                    ]
                },
                {
                    "Instances": [
                        {
                            "InstanceId": "i-222222222222222b",
                            "InstanceType": "t3.micro",
                            "State": {"Name": "running"},
                        },
                        {
                            "InstanceId": "i-333333333333333c",
                            "InstanceType": "m5.large",
                            "State": {"Name": "stopped"},
                        },
                    ]
                },
            ]
        }

        instances = await manager.describe_instances()

        assert len(instances) == 3
        assert instances[0].instance_id == "i-111111111111111a"
        assert instances[1].instance_id == "i-222222222222222b"
        assert instances[2].instance_id == "i-333333333333333c"

    @pytest.mark.asyncio
    async def test_describe_instances_empty_result(
        self, manager: EC2Manager, mock_client: Mock
    ) -> None:
        """Test describing instances with no results."""
        mock_client.call.return_value = {"Reservations": []}

        instances = await manager.describe_instances(instance_ids=["i-nonexistent"])

        assert len(instances) == 0
        assert instances == []

    @pytest.mark.asyncio
    async def test_start_instances_success(self, manager: EC2Manager, mock_client: Mock) -> None:
        """Test starting instances successfully."""
        mock_client.call.return_value = {
            "StartingInstances": [
                {"InstanceId": "i-1234567890abcdef", "PreviousState": {"Name": "stopped"}},
                {"InstanceId": "i-abcdef1234567890", "PreviousState": {"Name": "stopped"}},
            ]
        }

        result = await manager.start_instances(["i-1234567890abcdef", "i-abcdef1234567890"])

        assert result == {"i-1234567890abcdef": "stopped", "i-abcdef1234567890": "stopped"}
        mock_client.call.assert_called_once_with(
            "start_instances", InstanceIds=["i-1234567890abcdef", "i-abcdef1234567890"], DryRun=False
        )

    @pytest.mark.asyncio
    async def test_start_instances_with_dry_run(
        self, manager: EC2Manager, mock_client: Mock
    ) -> None:
        """Test starting instances with dry run."""
        mock_client.call.return_value = {"StartingInstances": []}

        await manager.start_instances(["i-1234567890abcdef"], dry_run=True)

        mock_client.call.assert_called_once_with(
            "start_instances", InstanceIds=["i-1234567890abcdef"], DryRun=True
        )

    @pytest.mark.asyncio
    async def test_start_instances_empty_list_raises_error(self, manager: EC2Manager) -> None:
        """Test that starting with empty list raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            await manager.start_instances([])

        assert "cannot be empty" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_stop_instances_success(self, manager: EC2Manager, mock_client: Mock) -> None:
        """Test stopping instances successfully."""
        mock_client.call.return_value = {
            "StoppingInstances": [
                {"InstanceId": "i-1234567890abcdef", "PreviousState": {"Name": "running"}},
            ]
        }

        result = await manager.stop_instances(["i-1234567890abcdef"])

        assert result == {"i-1234567890abcdef": "running"}
        mock_client.call.assert_called_once_with(
            "stop_instances", InstanceIds=["i-1234567890abcdef"], DryRun=False, Force=False
        )

    @pytest.mark.asyncio
    async def test_stop_instances_with_force(self, manager: EC2Manager, mock_client: Mock) -> None:
        """Test stopping instances with force flag."""
        mock_client.call.return_value = {
            "StoppingInstances": [
                {"InstanceId": "i-1234567890abcdef", "PreviousState": {"Name": "running"}},
            ]
        }

        await manager.stop_instances(["i-1234567890abcdef"], force=True)

        mock_client.call.assert_called_once_with(
            "stop_instances", InstanceIds=["i-1234567890abcdef"], DryRun=False, Force=True
        )

    @pytest.mark.asyncio
    async def test_stop_instances_empty_list_raises_error(self, manager: EC2Manager) -> None:
        """Test that stopping with empty list raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            await manager.stop_instances([])

        assert "cannot be empty" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_reboot_instances_success(self, manager: EC2Manager, mock_client: Mock) -> None:
        """Test rebooting instances successfully."""
        mock_client.call.return_value = {}

        await manager.reboot_instances(["i-1234567890abcdef", "i-abcdef1234567890"])

        mock_client.call.assert_called_once_with(
            "reboot_instances", InstanceIds=["i-1234567890abcdef", "i-abcdef1234567890"], DryRun=False
        )

    @pytest.mark.asyncio
    async def test_reboot_instances_with_dry_run(
        self, manager: EC2Manager, mock_client: Mock
    ) -> None:
        """Test rebooting instances with dry run."""
        mock_client.call.return_value = {}

        await manager.reboot_instances(["i-1234567890abcdef"], dry_run=True)

        mock_client.call.assert_called_once_with(
            "reboot_instances", InstanceIds=["i-1234567890abcdef"], DryRun=True
        )

    @pytest.mark.asyncio
    async def test_reboot_instances_empty_list_raises_error(self, manager: EC2Manager) -> None:
        """Test that rebooting with empty list raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            await manager.reboot_instances([])

        assert "cannot be empty" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_terminate_instances_success(
        self, manager: EC2Manager, mock_client: Mock
    ) -> None:
        """Test terminating instances successfully."""
        mock_client.call.return_value = {
            "TerminatingInstances": [
                {"InstanceId": "i-1234567890abcdef", "PreviousState": {"Name": "running"}},
            ]
        }

        result = await manager.terminate_instances(["i-1234567890abcdef"])

        assert result == {"i-1234567890abcdef": "running"}
        mock_client.call.assert_called_once_with(
            "terminate_instances", InstanceIds=["i-1234567890abcdef"], DryRun=False
        )

    @pytest.mark.asyncio
    async def test_terminate_instances_empty_list_raises_error(self, manager: EC2Manager) -> None:
        """Test that terminating with empty list raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            await manager.terminate_instances([])

        assert "cannot be empty" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_instance_state_success(self, manager: EC2Manager, mock_client: Mock) -> None:
        """Test getting instance state successfully."""
        mock_client.call.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-1234567890abcdef",
                            "InstanceType": "t3.micro",
                            "State": {"Name": "running"},
                        }
                    ]
                }
            ]
        }

        state = await manager.get_instance_state("i-1234567890abcdef")

        assert state == "running"

    @pytest.mark.asyncio
    async def test_get_instance_state_not_found(
        self, manager: EC2Manager, mock_client: Mock
    ) -> None:
        """Test getting state for non-existent instance."""
        mock_client.call.return_value = {"Reservations": []}

        with pytest.raises(EC2Error) as exc_info:
            await manager.get_instance_state("i-nonexistent")

        assert "not found" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_parse_instance_with_launch_time(self, manager: EC2Manager) -> None:
        """Test parsing instance with launch_time datetime object."""
        instance_data = {
            "InstanceId": "i-1234567890abcdef",
            "InstanceType": "t3.micro",
            "State": {"Name": "running"},
            "LaunchTime": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "Tags": [],
        }

        instance = manager._parse_instance(instance_data)

        assert instance.instance_id == "i-1234567890abcdef"
        assert instance.launch_time == "2024-01-15T10:30:00+00:00"

    @pytest.mark.asyncio
    async def test_parse_instance_without_optional_fields(self, manager: EC2Manager) -> None:
        """Test parsing instance with minimal data."""
        instance_data = {
            "InstanceId": "i-1234567890abcdef",
            "InstanceType": "t3.micro",
            "State": {"Name": "stopped"},
        }

        instance = manager._parse_instance(instance_data)

        assert instance.instance_id == "i-1234567890abcdef"
        assert instance.private_ip is None
        assert instance.public_ip is None
        assert instance.availability_zone is None
        assert instance.launch_time is None

    @pytest.mark.asyncio
    async def test_parse_instance_with_all_fields(self, manager: EC2Manager) -> None:
        """Test parsing instance with all fields populated."""
        instance_data = {
            "InstanceId": "i-1234567890abcdef",
            "InstanceType": "m5.xlarge",
            "State": {"Name": "running"},
            "Placement": {"AvailabilityZone": "us-east-1b"},
            "PrivateIpAddress": "10.0.2.15",
            "PublicIpAddress": "54.123.45.67",
            "LaunchTime": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "Tags": [
                {"Key": "Name", "Value": "web-server"},
                {"Key": "Environment", "Value": "production"},
                {"Key": "Owner", "Value": "devops-team"},
            ],
        }

        instance = manager._parse_instance(instance_data)

        assert instance.instance_id == "i-1234567890abcdef"
        assert instance.instance_type == "m5.xlarge"
        assert instance.state == "running"
        assert instance.availability_zone == "us-east-1b"
        assert instance.private_ip == "10.0.2.15"
        assert instance.public_ip == "54.123.45.67"
        assert instance.launch_time == "2024-01-15T10:30:00+00:00"
        assert instance.tags["Name"] == "web-server"
        assert instance.tags["Environment"] == "production"
        assert instance.tags["Owner"] == "devops-team"

    @pytest.mark.asyncio
    async def test_parse_instance_invalid_data_raises_error(self, manager: EC2Manager) -> None:
        """Test that invalid instance data raises ValidationError."""
        instance_data = {
            "InstanceId": "invalid-id",  # Invalid format
            "InstanceType": "t3.micro",
            "State": {"Name": "running"},
        }

        with pytest.raises(ValidationError) as exc_info:
            manager._parse_instance(instance_data)

        assert "Invalid instance data" in exc_info.value.message
