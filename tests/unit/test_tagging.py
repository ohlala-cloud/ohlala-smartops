"""Tests for resource tagging utilities."""

from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError as PydanticValidationError

from ohlala_smartops.aws.exceptions import TaggingError, ValidationError
from ohlala_smartops.aws.tagging import ResourceTag, TaggingManager


class TestResourceTag:
    """Test suite for ResourceTag Pydantic model."""

    def test_valid_tag_creation(self) -> None:
        """Test creating a valid ResourceTag."""
        tag = ResourceTag(key="Environment", value="Production")

        assert tag.key == "Environment"
        assert tag.value == "Production"

    def test_tag_with_empty_value(self) -> None:
        """Test ResourceTag with empty value (valid in AWS)."""
        tag = ResourceTag(key="EmptyTag", value="")

        assert tag.key == "EmptyTag"
        assert tag.value == ""

    def test_tag_with_max_length_key(self) -> None:
        """Test ResourceTag with maximum length key (128 characters)."""
        key = "a" * 128
        tag = ResourceTag(key=key, value="test")

        assert tag.key == key
        assert len(tag.key) == 128

    def test_tag_with_max_length_value(self) -> None:
        """Test ResourceTag with maximum length value (256 characters)."""
        value = "b" * 256
        tag = ResourceTag(key="TestKey", value=value)

        assert tag.value == value
        assert len(tag.value) == 256

    def test_tag_key_too_long(self) -> None:
        """Test that tag key exceeding 128 characters raises validation error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            ResourceTag(key="a" * 129, value="test")

        assert "key" in str(exc_info.value).lower()

    def test_tag_value_too_long(self) -> None:
        """Test that tag value exceeding 256 characters raises validation error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            ResourceTag(key="TestKey", value="b" * 257)

        assert "value" in str(exc_info.value).lower()

    def test_tag_key_empty(self) -> None:
        """Test that empty tag key raises validation error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            ResourceTag(key="", value="test")

        assert "key" in str(exc_info.value).lower()

    def test_tag_key_with_aws_prefix(self) -> None:
        """Test that tag key starting with 'aws:' raises validation error."""
        with pytest.raises(ValueError, match="reserved prefix"):
            ResourceTag(key="aws:Name", value="test")

    def test_tag_key_with_aws_prefix_case_insensitive(self) -> None:
        """Test that aws: prefix validation is case-insensitive."""
        with pytest.raises(ValueError, match="reserved prefix"):
            ResourceTag(key="AWS:Name", value="test")

        with pytest.raises(ValueError, match="reserved prefix"):
            ResourceTag(key="AwS:Name", value="test")

    def test_tag_key_containing_aws_not_at_start(self) -> None:
        """Test that tag key containing 'aws' but not at start is valid."""
        tag = ResourceTag(key="myaws:tag", value="test")
        assert tag.key == "myaws:tag"


class TestTaggingManager:
    """Test suite for TaggingManager class."""

    @pytest.fixture
    def mock_ec2_client(self) -> Mock:
        """Fixture providing a mocked EC2 AWSClientWrapper."""
        client = Mock()
        client.call = AsyncMock()
        return client

    @pytest.fixture
    def mock_tagging_client(self) -> Mock:
        """Fixture providing a mocked Resource Groups Tagging API client."""
        client = Mock()
        client.call = AsyncMock()
        return client

    @pytest.fixture
    def tagging_manager(self, mock_ec2_client: Mock, mock_tagging_client: Mock) -> TaggingManager:
        """Fixture providing a TaggingManager with mocked clients."""
        manager = TaggingManager(region="us-east-1", client=mock_ec2_client)
        manager._tagging_client = mock_tagging_client
        return manager

    # Tests for tag_resources()

    @pytest.mark.asyncio
    async def test_tag_resources_with_dict(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test tagging resources with dictionary of tags."""
        resource_ids = ["i-123", "i-456"]
        tags = {"Environment": "Production", "Owner": "Alice"}

        mock_ec2_client.call.return_value = {}

        result = await tagging_manager.tag_resources(resource_ids, tags)

        assert result == {"i-123": True, "i-456": True}
        mock_ec2_client.call.assert_called_once()
        call_args = mock_ec2_client.call.call_args
        assert call_args[0][0] == "create_tags"
        assert call_args[1]["Resources"] == resource_ids
        assert len(call_args[1]["Tags"]) == 2

    @pytest.mark.asyncio
    async def test_tag_resources_with_resource_tag_list(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test tagging resources with list of ResourceTag objects."""
        resource_ids = ["i-123"]
        tags = [
            ResourceTag(key="Environment", value="Staging"),
            ResourceTag(key="Team", value="DevOps"),
        ]

        mock_ec2_client.call.return_value = {}

        result = await tagging_manager.tag_resources(resource_ids, tags)

        assert result == {"i-123": True}
        mock_ec2_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_tag_resources_empty_resource_ids(self, tagging_manager: TaggingManager) -> None:
        """Test that empty resource_ids raises ValidationError."""
        with pytest.raises(ValidationError, match="resource_ids cannot be empty"):
            await tagging_manager.tag_resources([], {"Key": "Value"})

    @pytest.mark.asyncio
    async def test_tag_resources_empty_tags(self, tagging_manager: TaggingManager) -> None:
        """Test that empty tags raises ValidationError."""
        with pytest.raises(ValidationError, match="tags cannot be empty"):
            await tagging_manager.tag_resources(["i-123"], {})

    @pytest.mark.asyncio
    async def test_tag_resources_invalid_tag_key(self, tagging_manager: TaggingManager) -> None:
        """Test that invalid tag key raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid tags"):
            await tagging_manager.tag_resources(["i-123"], {"aws:Reserved": "Value"})

    @pytest.mark.asyncio
    async def test_tag_resources_too_many_tags(self, tagging_manager: TaggingManager) -> None:
        """Test that more than 50 tags raises ValidationError."""
        tags = {f"Key{i}": f"Value{i}" for i in range(51)}

        with pytest.raises(ValidationError, match="Cannot add more than 50 tags"):
            await tagging_manager.tag_resources(["i-123"], tags)

    @pytest.mark.asyncio
    async def test_tag_resources_aws_error(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in TaggingError."""
        mock_ec2_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(TaggingError, match="Failed to tag resources"):
            await tagging_manager.tag_resources(["i-123"], {"Key": "Value"})

    @pytest.mark.asyncio
    async def test_tag_resources_multiple_resources(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test tagging multiple resources in batch."""
        resource_ids = [f"i-{i:03d}" for i in range(100)]
        tags = {"Environment": "Test"}

        mock_ec2_client.call.return_value = {}

        result = await tagging_manager.tag_resources(resource_ids, tags)

        assert len(result) == 100
        assert all(v is True for v in result.values())

    # Tests for get_resource_tags()

    @pytest.mark.asyncio
    async def test_get_resource_tags_success(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test retrieving tags for resources."""
        resource_ids = ["i-123", "i-456"]
        mock_ec2_client.call.return_value = {
            "Tags": [
                {"ResourceId": "i-123", "Key": "Environment", "Value": "Production"},
                {"ResourceId": "i-123", "Key": "Owner", "Value": "Alice"},
                {"ResourceId": "i-456", "Key": "Environment", "Value": "Staging"},
            ]
        }

        result = await tagging_manager.get_resource_tags(resource_ids)

        assert result == {
            "i-123": {"Environment": "Production", "Owner": "Alice"},
            "i-456": {"Environment": "Staging"},
        }
        mock_ec2_client.call.assert_called_once_with(
            "describe_tags",
            Filters=[{"Name": "resource-id", "Values": resource_ids}],
        )

    @pytest.mark.asyncio
    async def test_get_resource_tags_no_tags(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test retrieving tags for resources with no tags."""
        resource_ids = ["i-123"]
        mock_ec2_client.call.return_value = {"Tags": []}

        result = await tagging_manager.get_resource_tags(resource_ids)

        assert result == {"i-123": {}}

    @pytest.mark.asyncio
    async def test_get_resource_tags_empty_resource_ids(
        self, tagging_manager: TaggingManager
    ) -> None:
        """Test that empty resource_ids raises ValidationError."""
        with pytest.raises(ValidationError, match="resource_ids cannot be empty"):
            await tagging_manager.get_resource_tags([])

    @pytest.mark.asyncio
    async def test_get_resource_tags_aws_error(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in TaggingError."""
        mock_ec2_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(TaggingError, match="Failed to retrieve resource tags"):
            await tagging_manager.get_resource_tags(["i-123"])

    # Tests for remove_tags()

    @pytest.mark.asyncio
    async def test_remove_tags_success(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test removing tags from resources."""
        resource_ids = ["i-123", "i-456"]
        tag_keys = ["OldTag", "TempTag"]

        mock_ec2_client.call.return_value = {}

        result = await tagging_manager.remove_tags(resource_ids, tag_keys)

        assert result == {"i-123": True, "i-456": True}
        mock_ec2_client.call.assert_called_once()
        call_args = mock_ec2_client.call.call_args
        assert call_args[0][0] == "delete_tags"
        assert call_args[1]["Resources"] == resource_ids
        assert len(call_args[1]["Tags"]) == 2

    @pytest.mark.asyncio
    async def test_remove_tags_empty_resource_ids(self, tagging_manager: TaggingManager) -> None:
        """Test that empty resource_ids raises ValidationError."""
        with pytest.raises(ValidationError, match="resource_ids cannot be empty"):
            await tagging_manager.remove_tags([], ["Key"])

    @pytest.mark.asyncio
    async def test_remove_tags_empty_tag_keys(self, tagging_manager: TaggingManager) -> None:
        """Test that empty tag_keys raises ValidationError."""
        with pytest.raises(ValidationError, match="tag_keys cannot be empty"):
            await tagging_manager.remove_tags(["i-123"], [])

    @pytest.mark.asyncio
    async def test_remove_tags_aws_error(
        self, tagging_manager: TaggingManager, mock_ec2_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in TaggingError."""
        mock_ec2_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(TaggingError, match="Failed to remove tags"):
            await tagging_manager.remove_tags(["i-123"], ["Key"])

    # Tests for find_resources_by_tags()

    @pytest.mark.asyncio
    async def test_find_resources_by_tags_success(
        self, tagging_manager: TaggingManager, mock_tagging_client: Mock
    ) -> None:
        """Test finding resources by tags."""
        tag_filters = {"Environment": "Production", "Team": "Backend"}
        mock_tagging_client.call.return_value = {
            "ResourceTagMappingList": [
                {"ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"},
                {"ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"},
            ]
        }

        result = await tagging_manager.find_resources_by_tags(tag_filters)

        assert len(result) == 2
        assert "arn:aws:ec2:us-east-1:123456789012:instance/i-123" in result
        mock_tagging_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_resources_by_tags_with_resource_types(
        self, tagging_manager: TaggingManager, mock_tagging_client: Mock
    ) -> None:
        """Test finding resources by tags with resource type filter."""
        tag_filters = {"Environment": "Production"}
        resource_types = ["ec2:instance"]
        mock_tagging_client.call.return_value = {
            "ResourceTagMappingList": [
                {"ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"}
            ]
        }

        result = await tagging_manager.find_resources_by_tags(tag_filters, resource_types)

        assert len(result) == 1
        call_args = mock_tagging_client.call.call_args
        assert call_args[1]["ResourceTypeFilters"] == resource_types

    @pytest.mark.asyncio
    async def test_find_resources_by_tags_pagination(
        self, tagging_manager: TaggingManager, mock_tagging_client: Mock
    ) -> None:
        """Test finding resources by tags with pagination."""
        tag_filters = {"Environment": "Production"}

        # Mock paginated responses
        mock_tagging_client.call.side_effect = [
            {
                "ResourceTagMappingList": [
                    {"ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"}
                ],
                "PaginationToken": "token1",
            },
            {
                "ResourceTagMappingList": [
                    {"ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"}
                ],
            },
        ]

        result = await tagging_manager.find_resources_by_tags(tag_filters)

        assert len(result) == 2
        assert mock_tagging_client.call.call_count == 2

    @pytest.mark.asyncio
    async def test_find_resources_by_tags_no_results(
        self, tagging_manager: TaggingManager, mock_tagging_client: Mock
    ) -> None:
        """Test finding resources by tags with no matches."""
        tag_filters = {"Environment": "NonExistent"}
        mock_tagging_client.call.return_value = {"ResourceTagMappingList": []}

        result = await tagging_manager.find_resources_by_tags(tag_filters)

        assert result == []

    @pytest.mark.asyncio
    async def test_find_resources_by_tags_empty_filters(
        self, tagging_manager: TaggingManager
    ) -> None:
        """Test that empty tag_filters raises ValidationError."""
        with pytest.raises(ValidationError, match="tag_filters cannot be empty"):
            await tagging_manager.find_resources_by_tags({})

    @pytest.mark.asyncio
    async def test_find_resources_by_tags_aws_error(
        self, tagging_manager: TaggingManager, mock_tagging_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in TaggingError."""
        mock_tagging_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(TaggingError, match="Failed to find resources by tags"):
            await tagging_manager.find_resources_by_tags({"Environment": "Production"})

    # Tests for initialization

    def test_tagging_manager_with_region(self) -> None:
        """Test TaggingManager initialization with region."""
        manager = TaggingManager(region="us-west-2")

        assert manager.region == "us-west-2"
        assert manager.client is not None
        assert manager._tagging_client is not None

    def test_tagging_manager_with_client(self, mock_ec2_client: Mock) -> None:
        """Test TaggingManager initialization with pre-configured client."""
        manager = TaggingManager(client=mock_ec2_client)

        assert manager.client is mock_ec2_client
        assert manager._tagging_client is not None

    def test_tagging_manager_default_region(self) -> None:
        """Test TaggingManager initialization with default region."""
        manager = TaggingManager()

        assert manager.region is None
        assert manager.client is not None
