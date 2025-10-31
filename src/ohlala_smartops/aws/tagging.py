"""Resource tagging utilities for AWS resources.

This module provides high-level utilities for managing tags on AWS resources,
including adding, removing, and querying tags. All operations use the AWSClientWrapper
for automatic throttling and error handling.
"""

import logging
from collections.abc import Sequence
from typing import Any, Final

from pydantic import BaseModel, Field, field_validator

from ohlala_smartops.aws.client import AWSClientWrapper, create_aws_client
from ohlala_smartops.aws.exceptions import TaggingError, ValidationError

logger: Final = logging.getLogger(__name__)


class ResourceTag(BaseModel):
    """Model representing an AWS resource tag with validated data.

    This Pydantic model validates tag key-value pairs according to AWS tagging
    requirements. AWS imposes strict limits on tag keys and values.

    Attributes:
        key: Tag key (1-128 characters, case-sensitive).
        value: Tag value (0-256 characters, case-sensitive).
    """

    key: str = Field(..., min_length=1, max_length=128)
    value: str = Field("", max_length=256)

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Validate tag key against AWS requirements.

        Args:
            v: Tag key string.

        Returns:
            Validated key string.

        Raises:
            ValueError: If key contains invalid characters or patterns.
        """
        # AWS tag keys can't start with "aws:" (reserved prefix)
        if v.lower().startswith("aws:"):
            raise ValueError("Tag keys cannot start with 'aws:' (reserved prefix)")

        return v


class TaggingManager:
    """Manager for AWS resource tagging operations with automatic throttling.

    This class provides high-level methods for managing tags on AWS resources.
    It supports both EC2-specific tagging operations and cross-service tag queries
    using the Resource Groups Tagging API.

    All operations use the AWSClientWrapper for automatic rate limiting, error
    handling, and retries.

    Example:
        >>> manager = TaggingManager(region="us-east-1")
        >>> tags = {"Environment": "Production", "Owner": "DataTeam"}
        >>> await manager.tag_resources(["i-123", "i-456"], tags)
        >>> results = await manager.find_resources_by_tags({"Environment": "Production"})
    """

    def __init__(self, region: str | None = None, client: AWSClientWrapper | None = None) -> None:
        """Initialize tagging manager.

        Args:
            region: AWS region name. If None, uses default from environment/config.
                Defaults to None.
            client: Optional pre-configured AWSClientWrapper for EC2. If None, creates
                a new one. Defaults to None.

        Example:
            >>> manager = TaggingManager(region="us-west-2")
            >>> # Or with existing client:
            >>> client = create_aws_client("ec2", region="eu-west-1")
            >>> manager = TaggingManager(client=client)
        """
        self.region = region
        self.client = client or create_aws_client("ec2", region=region)
        # Resource Groups Tagging API client for cross-service queries
        self._tagging_client = create_aws_client("resourcegroupstaggingapi", region=region)
        logger.info(f"Initialized TaggingManager for region {region or 'default'}")

    async def tag_resources(
        self,
        resource_ids: Sequence[str],
        tags: dict[str, str] | list[ResourceTag],
    ) -> dict[str, bool]:
        """Add or update tags on AWS resources.

        This method adds tags to resources, creating new tags or updating existing ones.
        AWS allows up to 50 tags per resource, and this method can tag up to 1000
        resources in a single call.

        Args:
            resource_ids: Sequence of resource IDs (e.g., EC2 instance IDs).
            tags: Tags to add, either as a dictionary or list of ResourceTag objects.

        Returns:
            Dictionary mapping resource IDs to success status (True if tagged successfully).

        Raises:
            ValidationError: If resource IDs are empty or tags are invalid.
            TaggingError: If AWS API call fails.

        Example:
            >>> tags = {"Environment": "Production", "Owner": "Alice"}
            >>> result = await manager.tag_resources(["i-123", "i-456"], tags)
            >>> print(result)
            {'i-123': True, 'i-456': True}
        """
        if not resource_ids:
            raise ValidationError("resource_ids cannot be empty", service="ec2")

        if not tags:
            raise ValidationError("tags cannot be empty", service="ec2")

        logger.info(f"Tagging {len(resource_ids)} resource(s) with {len(tags)} tag(s)")

        # Convert tags to ResourceTag objects for validation
        tag_objects: list[ResourceTag]
        if isinstance(tags, dict):
            try:
                tag_objects = [ResourceTag(key=k, value=v) for k, v in tags.items()]
            except Exception as e:
                logger.error(f"Tag validation failed: {e}")
                raise ValidationError(f"Invalid tags: {e}", service="ec2") from e
        else:
            tag_objects = list(tags)

        # Validate AWS tag limit (50 tags per resource)
        if len(tag_objects) > 50:
            raise ValidationError(
                f"Cannot add more than 50 tags per resource (got {len(tag_objects)})",
                service="ec2",
            )

        # Convert to AWS API format
        aws_tags = [{"Key": tag.key, "Value": tag.value} for tag in tag_objects]

        try:
            # Batch tagging (up to 1000 resources per call)
            await self.client.call(
                "create_tags",
                Resources=list(resource_ids),
                Tags=aws_tags,
            )

            logger.info(f"Successfully tagged {len(resource_ids)} resource(s)")

            # Return success for all resources
            return dict.fromkeys(resource_ids, True)

        except Exception as e:
            logger.error(f"Failed to tag resources: {e}")
            if isinstance(e, ValidationError):
                raise
            raise TaggingError(
                f"Failed to tag resources: {e}",
                service="ec2",
                operation="create_tags",
            ) from e

    async def get_resource_tags(
        self,
        resource_ids: Sequence[str],
    ) -> dict[str, dict[str, str]]:
        """Retrieve tags for specified resources.

        Args:
            resource_ids: Sequence of resource IDs to query.

        Returns:
            Dictionary mapping resource IDs to their tag dictionaries.

        Raises:
            ValidationError: If resource IDs are empty.
            TaggingError: If AWS API call fails.

        Example:
            >>> tags = await manager.get_resource_tags(["i-123", "i-456"])
            >>> print(tags["i-123"])
            {'Environment': 'Production', 'Owner': 'Alice'}
        """
        if not resource_ids:
            raise ValidationError("resource_ids cannot be empty", service="ec2")

        logger.debug(f"Retrieving tags for {len(resource_ids)} resource(s)")

        try:
            response = await self.client.call(
                "describe_tags",
                Filters=[
                    {
                        "Name": "resource-id",
                        "Values": list(resource_ids),
                    }
                ],
            )

            # Parse tags from response
            resource_tags: dict[str, dict[str, str]] = {rid: {} for rid in resource_ids}

            for tag_data in response.get("Tags", []):
                resource_id = tag_data["ResourceId"]
                key = tag_data["Key"]
                value = tag_data["Value"]

                if resource_id in resource_tags:
                    resource_tags[resource_id][key] = value

            logger.info(f"Retrieved tags for {len(resource_tags)} resource(s)")
            return resource_tags

        except Exception as e:
            logger.error(f"Failed to retrieve resource tags: {e}")
            if isinstance(e, ValidationError):
                raise
            raise TaggingError(
                f"Failed to retrieve resource tags: {e}",
                service="ec2",
                operation="describe_tags",
            ) from e

    async def remove_tags(
        self,
        resource_ids: Sequence[str],
        tag_keys: Sequence[str],
    ) -> dict[str, bool]:
        """Remove tags from AWS resources.

        This method removes specified tags from resources by their keys. If a tag
        key doesn't exist on a resource, the operation still succeeds.

        Args:
            resource_ids: Sequence of resource IDs.
            tag_keys: Sequence of tag keys to remove.

        Returns:
            Dictionary mapping resource IDs to success status.

        Raises:
            ValidationError: If resource IDs or tag keys are empty.
            TaggingError: If AWS API call fails.

        Example:
            >>> result = await manager.remove_tags(["i-123"], ["OldTag", "TempTag"])
            >>> print(result)
            {'i-123': True}
        """
        if not resource_ids:
            raise ValidationError("resource_ids cannot be empty", service="ec2")

        if not tag_keys:
            raise ValidationError("tag_keys cannot be empty", service="ec2")

        logger.info(f"Removing {len(tag_keys)} tag(s) from {len(resource_ids)} resource(s)")

        # Convert to AWS API format
        aws_tags = [{"Key": key} for key in tag_keys]

        try:
            await self.client.call(
                "delete_tags",
                Resources=list(resource_ids),
                Tags=aws_tags,
            )

            logger.info(f"Successfully removed tags from {len(resource_ids)} resource(s)")

            # Return success for all resources
            return dict.fromkeys(resource_ids, True)

        except Exception as e:
            logger.error(f"Failed to remove tags: {e}")
            if isinstance(e, ValidationError):
                raise
            raise TaggingError(
                f"Failed to remove tags: {e}",
                service="ec2",
                operation="delete_tags",
            ) from e

    async def find_resources_by_tags(
        self,
        tag_filters: dict[str, str],
        resource_types: Sequence[str] | None = None,
    ) -> list[str]:
        """Find AWS resources matching specified tag filters.

        This method uses the Resource Groups Tagging API to search for resources
        across services that match the specified tag filters. By default, it searches
        all resource types, but you can limit the search to specific types.

        Args:
            tag_filters: Dictionary of tag key-value pairs to match (AND logic).
            resource_types: Optional sequence of resource type filters (e.g., ["ec2:instance"]).
                If None, searches all resource types. Defaults to None.

        Returns:
            List of resource ARNs matching the tag filters.

        Raises:
            ValidationError: If tag filters are empty.
            TaggingError: If AWS API call fails.

        Example:
            >>> # Find all production EC2 instances
            >>> arns = await manager.find_resources_by_tags(
            ...     {"Environment": "Production"},
            ...     resource_types=["ec2:instance"]
            ... )
            >>> print(arns)
            ['arn:aws:ec2:us-east-1:123456789012:instance/i-123']
        """
        if not tag_filters:
            raise ValidationError("tag_filters cannot be empty", service="resourcegroupstaggingapi")

        logger.info(f"Searching for resources with tag filters: {tag_filters}")

        # Convert tag filters to AWS API format
        aws_tag_filters = [{"Key": k, "Values": [v]} for k, v in tag_filters.items()]

        try:
            # Build API parameters
            kwargs: dict[str, Any] = {"TagFilters": aws_tag_filters}
            if resource_types:
                kwargs["ResourceTypeFilters"] = list(resource_types)

            # Handle pagination
            resource_arns: list[str] = []
            pagination_token: str | None = None

            while True:
                if pagination_token:
                    kwargs["PaginationToken"] = pagination_token

                response = await self._tagging_client.call("get_resources", **kwargs)

                # Extract ARNs from response
                resource_arns.extend(
                    resource["ResourceARN"]
                    for resource in response.get("ResourceTagMappingList", [])
                )

                # Check for more results
                pagination_token = response.get("PaginationToken")
                if not pagination_token:
                    break

            logger.info(f"Found {len(resource_arns)} resource(s) matching tag filters")
            return resource_arns

        except Exception as e:
            logger.error(f"Failed to find resources by tags: {e}")
            if isinstance(e, ValidationError):
                raise
            raise TaggingError(
                f"Failed to find resources by tags: {e}",
                service="resourcegroupstaggingapi",
                operation="get_resources",
            ) from e
