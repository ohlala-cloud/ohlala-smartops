"""EC2 instance management utilities.

This module provides high-level utilities for managing EC2 instances, including
starting, stopping, rebooting, terminating, and querying instance information.
All operations use the AWSClientWrapper for automatic throttling and error handling.
"""

import logging
from collections.abc import Sequence
from typing import Any, Final

from pydantic import BaseModel, Field, field_validator

from ohlala_smartops.aws.client import AWSClientWrapper, create_aws_client
from ohlala_smartops.aws.exceptions import EC2Error, ValidationError

logger: Final = logging.getLogger(__name__)


class EC2Instance(BaseModel):
    """Model representing an EC2 instance with validated data.

    This Pydantic model validates and structures EC2 instance data from AWS API responses.
    It provides type-safe access to common instance attributes.

    Attributes:
        instance_id: EC2 instance ID (e.g., 'i-1234567890abcdef0').
        instance_type: EC2 instance type (e.g., 't3.micro', 'm5.large').
        state: Current instance state.
        availability_zone: Availability zone where instance is running.
        private_ip: Private IP address (optional).
        public_ip: Public IP address (optional).
        launch_time: Instance launch timestamp as ISO string (optional).
        tags: Dictionary of instance tags (optional).
    """

    instance_id: str = Field(..., pattern=r"^i-[a-f0-9]{8,17}$")
    instance_type: str
    state: str
    availability_zone: str | None = None
    private_ip: str | None = None
    public_ip: str | None = None
    launch_time: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Validate instance state against known EC2 states.

        Args:
            v: Instance state string.

        Returns:
            Validated state string.

        Raises:
            ValueError: If state is not a valid EC2 instance state.
        """
        valid_states = {
            "pending",
            "running",
            "shutting-down",
            "terminated",
            "stopping",
            "stopped",
        }
        if v not in valid_states:
            raise ValueError(f"Invalid instance state: {v}. Must be one of {valid_states}")
        return v


class EC2Manager:
    """Manager for EC2 instance operations with automatic throttling.

    This class provides high-level methods for managing EC2 instances. All operations
    use the AWSClientWrapper for automatic rate limiting, error handling, and retries.

    Example:
        >>> manager = EC2Manager(region="us-east-1")
        >>> instances = await manager.describe_instances(["i-123", "i-456"])
        >>> await manager.start_instances(["i-123"])
        >>> await manager.stop_instances(["i-456"])
    """

    def __init__(self, region: str | None = None, client: AWSClientWrapper | None = None) -> None:
        """Initialize EC2 manager.

        Args:
            region: AWS region name. If None, uses default from environment/config.
                Defaults to None.
            client: Optional pre-configured AWSClientWrapper. If None, creates a new one.
                Defaults to None.

        Example:
            >>> manager = EC2Manager(region="us-west-2")
            >>> # Or with existing client:
            >>> client = create_aws_client("ec2", region="eu-west-1")
            >>> manager = EC2Manager(client=client)
        """
        self.region = region
        self.client = client or create_aws_client("ec2", region=region)
        logger.info(f"Initialized EC2Manager for region {region or 'default'}")

    async def describe_instances(
        self,
        instance_ids: Sequence[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
    ) -> list[EC2Instance]:
        """Describe EC2 instances with optional filtering.

        Args:
            instance_ids: Specific instance IDs to describe. If None, describes all
                instances matching filters. Defaults to None.
            filters: AWS API filters in the format [{"Name": "...", "Values": [...]}].
                Defaults to None.

        Returns:
            List of EC2Instance objects with validated data.

        Raises:
            ValidationError: If instance IDs are malformed.
            EC2Error: If AWS API call fails.

        Example:
            >>> # Describe specific instances
            >>> instances = await manager.describe_instances(["i-123", "i-456"])
            >>>
            >>> # Describe all running instances
            >>> filters = [{"Name": "instance-state-name", "Values": ["running"]}]
            >>> instances = await manager.describe_instances(filters=filters)
        """
        logger.debug(f"Describing instances: ids={instance_ids}, filters={filters is not None}")

        # Build API parameters
        kwargs: dict[str, Any] = {}
        if instance_ids:
            kwargs["InstanceIds"] = list(instance_ids)
        if filters:
            kwargs["Filters"] = filters

        try:
            response = await self.client.call("describe_instances", **kwargs)

            # Parse instances from response
            instances: list[EC2Instance] = []
            for reservation in response.get("Reservations", []):
                for instance_data in reservation.get("Instances", []):
                    instance = self._parse_instance(instance_data)
                    instances.append(instance)

            logger.info(f"Described {len(instances)} instance(s)")
            return instances

        except Exception as e:
            logger.error(f"Failed to describe instances: {e}")
            raise

    async def start_instances(
        self, instance_ids: Sequence[str], dry_run: bool = False
    ) -> dict[str, str]:
        """Start one or more EC2 instances.

        Args:
            instance_ids: Sequence of instance IDs to start.
            dry_run: If True, perform a dry run without actually starting instances.
                Defaults to False.

        Returns:
            Dictionary mapping instance IDs to their previous states.

        Raises:
            ValidationError: If instance IDs list is empty or malformed.
            EC2Error: If AWS API call fails.

        Example:
            >>> result = await manager.start_instances(["i-123", "i-456"])
            >>> print(result)
            {'i-123': 'stopped', 'i-456': 'stopped'}
        """
        if not instance_ids:
            raise ValidationError("instance_ids cannot be empty", service="ec2")

        logger.info(f"Starting {len(instance_ids)} instance(s): {instance_ids}")

        try:
            response = await self.client.call(
                "start_instances", InstanceIds=list(instance_ids), DryRun=dry_run
            )

            # Parse state changes
            state_changes: dict[str, str] = {}
            for instance in response.get("StartingInstances", []):
                instance_id = instance["InstanceId"]
                previous_state = instance["PreviousState"]["Name"]
                state_changes[instance_id] = previous_state

            logger.info(f"Successfully started {len(state_changes)} instance(s)")
            return state_changes

        except Exception as e:
            logger.error(f"Failed to start instances: {e}")
            raise

    async def stop_instances(
        self, instance_ids: Sequence[str], dry_run: bool = False, force: bool = False
    ) -> dict[str, str]:
        """Stop one or more EC2 instances.

        Args:
            instance_ids: Sequence of instance IDs to stop.
            dry_run: If True, perform a dry run without actually stopping instances.
                Defaults to False.
            force: If True, force stop the instances. Defaults to False.

        Returns:
            Dictionary mapping instance IDs to their previous states.

        Raises:
            ValidationError: If instance IDs list is empty or malformed.
            EC2Error: If AWS API call fails.

        Example:
            >>> result = await manager.stop_instances(["i-123", "i-456"])
            >>> print(result)
            {'i-123': 'running', 'i-456': 'running'}
        """
        if not instance_ids:
            raise ValidationError("instance_ids cannot be empty", service="ec2")

        logger.info(f"Stopping {len(instance_ids)} instance(s): {instance_ids} (force={force})")

        try:
            response = await self.client.call(
                "stop_instances", InstanceIds=list(instance_ids), DryRun=dry_run, Force=force
            )

            # Parse state changes
            state_changes: dict[str, str] = {}
            for instance in response.get("StoppingInstances", []):
                instance_id = instance["InstanceId"]
                previous_state = instance["PreviousState"]["Name"]
                state_changes[instance_id] = previous_state

            logger.info(f"Successfully stopped {len(state_changes)} instance(s)")
            return state_changes

        except Exception as e:
            logger.error(f"Failed to stop instances: {e}")
            raise

    async def reboot_instances(self, instance_ids: Sequence[str], dry_run: bool = False) -> None:
        """Reboot one or more EC2 instances.

        Args:
            instance_ids: Sequence of instance IDs to reboot.
            dry_run: If True, perform a dry run without actually rebooting instances.
                Defaults to False.

        Raises:
            ValidationError: If instance IDs list is empty or malformed.
            EC2Error: If AWS API call fails.

        Example:
            >>> await manager.reboot_instances(["i-123", "i-456"])
        """
        if not instance_ids:
            raise ValidationError("instance_ids cannot be empty", service="ec2")

        logger.info(f"Rebooting {len(instance_ids)} instance(s): {instance_ids}")

        try:
            await self.client.call(
                "reboot_instances", InstanceIds=list(instance_ids), DryRun=dry_run
            )
            logger.info(f"Successfully rebooted {len(instance_ids)} instance(s)")

        except Exception as e:
            logger.error(f"Failed to reboot instances: {e}")
            raise

    async def terminate_instances(
        self, instance_ids: Sequence[str], dry_run: bool = False
    ) -> dict[str, str]:
        """Terminate one or more EC2 instances.

        Warning:
            This operation is destructive and cannot be undone. Use with caution.

        Args:
            instance_ids: Sequence of instance IDs to terminate.
            dry_run: If True, perform a dry run without actually terminating instances.
                Defaults to False.

        Returns:
            Dictionary mapping instance IDs to their previous states.

        Raises:
            ValidationError: If instance IDs list is empty or malformed.
            EC2Error: If AWS API call fails.

        Example:
            >>> result = await manager.terminate_instances(["i-123"])
            >>> print(result)
            {'i-123': 'running'}
        """
        if not instance_ids:
            raise ValidationError("instance_ids cannot be empty", service="ec2")

        logger.warning(
            f"Terminating {len(instance_ids)} instance(s): {instance_ids} - THIS IS DESTRUCTIVE"
        )

        try:
            response = await self.client.call(
                "terminate_instances", InstanceIds=list(instance_ids), DryRun=dry_run
            )

            # Parse state changes
            state_changes: dict[str, str] = {}
            for instance in response.get("TerminatingInstances", []):
                instance_id = instance["InstanceId"]
                previous_state = instance["PreviousState"]["Name"]
                state_changes[instance_id] = previous_state

            logger.info(f"Successfully terminated {len(state_changes)} instance(s)")
            return state_changes

        except Exception as e:
            logger.error(f"Failed to terminate instances: {e}")
            raise

    async def get_instance_state(self, instance_id: str) -> str:
        """Get the current state of a specific instance.

        Args:
            instance_id: EC2 instance ID.

        Returns:
            Current state name (e.g., 'running', 'stopped').

        Raises:
            ValidationError: If instance ID is malformed.
            ResourceNotFoundError: If instance doesn't exist.
            EC2Error: If AWS API call fails.

        Example:
            >>> state = await manager.get_instance_state("i-123")
            >>> print(state)
            'running'
        """
        logger.debug(f"Getting state for instance {instance_id}")

        instances = await self.describe_instances(instance_ids=[instance_id])
        if not instances:
            raise EC2Error(
                f"Instance {instance_id} not found",
                service="ec2",
                operation="describe_instances",
            )

        return instances[0].state

    def _parse_instance(self, instance_data: dict[str, Any]) -> EC2Instance:
        """Parse AWS API instance data into EC2Instance model.

        Args:
            instance_data: Raw instance data from AWS API.

        Returns:
            Validated EC2Instance object.

        Raises:
            ValidationError: If instance data doesn't match schema.
        """
        # Extract tags
        tags: dict[str, str] = {}
        for tag in instance_data.get("Tags", []):
            tags[tag["Key"]] = tag["Value"]

        # Build EC2Instance from API data
        try:
            return EC2Instance(
                instance_id=instance_data["InstanceId"],
                instance_type=instance_data["InstanceType"],
                state=instance_data["State"]["Name"],
                availability_zone=instance_data.get("Placement", {}).get("AvailabilityZone"),
                private_ip=instance_data.get("PrivateIpAddress"),
                public_ip=instance_data.get("PublicIpAddress"),
                launch_time=(
                    instance_data.get("LaunchTime", "").isoformat()
                    if instance_data.get("LaunchTime")
                    else None
                ),
                tags=tags,
            )
        except Exception as e:
            logger.error(f"Failed to parse instance data: {e}")
            raise ValidationError(
                f"Invalid instance data: {e}",
                service="ec2",
                operation="parse_instance",
            ) from e
