"""Tests for SSM command execution utilities."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ohlala_smartops.aws.exceptions import TimeoutError, ValidationError
from ohlala_smartops.aws.ssm_commands import (
    SSMCommand,
    SSMCommandInvocation,
    SSMCommandManager,
)


class TestSSMCommandInvocation:
    """Test suite for SSMCommandInvocation model."""

    def test_valid_invocation_creation(self) -> None:
        """Test creating a valid SSMCommandInvocation."""
        invocation = SSMCommandInvocation(
            command_id="cmd-123abc",
            instance_id="i-1234567890abcdef",
            status="Success",
            status_details="Command executed successfully",
            stdout="Hello World\n",
            stderr="",
            response_code=0,
        )

        assert invocation.command_id == "cmd-123abc"
        assert invocation.status == "Success"
        assert invocation.stdout == "Hello World\n"
        assert invocation.response_code == 0

    def test_invocation_with_minimal_fields(self) -> None:
        """Test SSMCommandInvocation with only required fields."""
        invocation = SSMCommandInvocation(
            command_id="cmd-456def",
            instance_id="i-abcdef1234567890",
            status="InProgress",
        )

        assert invocation.command_id == "cmd-456def"
        assert invocation.status == "InProgress"
        assert invocation.stdout is None
        assert invocation.stderr is None
        assert invocation.response_code is None


class TestSSMCommand:
    """Test suite for SSMCommand model."""

    def test_valid_command_creation(self) -> None:
        """Test creating a valid SSMCommand."""
        command = SSMCommand(
            command_id="cmd-789ghi",
            instance_ids=["i-1234567890abcdef", "i-abcdef1234567890"],
            document_name="AWS-RunShellScript",
            parameters={"commands": ["ls -la"]},
            status="Pending",
            requested_at="2024-01-15T10:30:00+00:00",
        )

        assert command.command_id == "cmd-789ghi"
        assert len(command.instance_ids) == 2
        assert command.document_name == "AWS-RunShellScript"
        assert command.status == "Pending"

    def test_command_defaults(self) -> None:
        """Test SSMCommand default values."""
        command = SSMCommand(
            command_id="cmd-abc",
            instance_ids=["i-1234567890abcdef"],
            document_name="AWS-RunShellScript",
            status="Success",
        )

        assert command.parameters == {}
        assert command.requested_at is None


class TestSSMCommandManager:
    """Test suite for SSMCommandManager class."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Fixture providing a mocked AWSClientWrapper."""
        client = Mock()
        client.call = AsyncMock()
        return client

    @pytest.fixture
    def manager(self, mock_client: Mock) -> SSMCommandManager:
        """Fixture providing an SSMCommandManager with mocked client."""
        return SSMCommandManager(region="us-east-1", client=mock_client)

    def test_initialization_with_region(self) -> None:
        """Test SSMCommandManager initialization with region."""
        with patch("ohlala_smartops.aws.ssm_commands.create_aws_client") as mock_create:
            manager = SSMCommandManager(region="us-west-2")

            assert manager.region == "us-west-2"
            mock_create.assert_called_once_with("ssm", region="us-west-2")

    def test_initialization_with_client(self, mock_client: Mock) -> None:
        """Test SSMCommandManager initialization with existing client."""
        manager = SSMCommandManager(client=mock_client)

        assert manager.client is mock_client
        assert manager.region is None

    @pytest.mark.asyncio
    async def test_send_command_single_string(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test sending a single command as a string."""
        mock_client.call.return_value = {
            "Command": {
                "CommandId": "cmd-test123",
                "InstanceIds": ["i-1234567890abcdef"],
                "DocumentName": "AWS-RunShellScript",
                "Parameters": {"commands": ["echo 'test'"]},
                "Status": "Pending",
                "RequestedDateTime": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            }
        }

        command = await manager.send_command(
            instance_ids=["i-1234567890abcdef"],
            commands="echo 'test'",
        )

        assert command.command_id == "cmd-test123"
        assert command.status == "Pending"
        assert len(command.instance_ids) == 1
        mock_client.call.assert_called_once()
        call_args = mock_client.call.call_args
        assert call_args[0][0] == "send_command"
        assert "InstanceIds" in call_args[1]
        assert "DocumentName" in call_args[1]

    @pytest.mark.asyncio
    async def test_send_command_list_of_commands(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test sending multiple commands as a list."""
        mock_client.call.return_value = {
            "Command": {
                "CommandId": "cmd-multi123",
                "InstanceIds": ["i-1234567890abcdef", "i-abcdef1234567890"],
                "DocumentName": "AWS-RunShellScript",
                "Parameters": {"commands": ["ls -la", "pwd", "whoami"]},
                "Status": "Pending",
            }
        }

        command = await manager.send_command(
            instance_ids=["i-1234567890abcdef", "i-abcdef1234567890"],
            commands=["ls -la", "pwd", "whoami"],
        )

        assert command.command_id == "cmd-multi123"
        assert len(command.instance_ids) == 2

    @pytest.mark.asyncio
    async def test_send_command_with_comment(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test sending command with a comment."""
        mock_client.call.return_value = {
            "Command": {
                "CommandId": "cmd-comment123",
                "InstanceIds": ["i-1234567890abcdef"],
                "DocumentName": "AWS-RunShellScript",
                "Parameters": {"commands": ["echo test"]},
                "Status": "Pending",
            }
        }

        await manager.send_command(
            instance_ids=["i-1234567890abcdef"],
            commands="echo test",
            comment="Test command execution",
        )

        call_args = mock_client.call.call_args
        assert "Comment" in call_args[1]
        assert call_args[1]["Comment"] == "Test command execution"

    @pytest.mark.asyncio
    async def test_send_command_with_custom_timeout(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test sending command with custom timeout."""
        mock_client.call.return_value = {
            "Command": {
                "CommandId": "cmd-timeout123",
                "InstanceIds": ["i-1234567890abcdef"],
                "DocumentName": "AWS-RunShellScript",
                "Parameters": {"commands": ["sleep 10"]},
                "Status": "Pending",
            }
        }

        await manager.send_command(
            instance_ids=["i-1234567890abcdef"],
            commands="sleep 10",
            timeout_seconds=600,
        )

        call_args = mock_client.call.call_args
        assert call_args[1]["TimeoutSeconds"] == 600

    @pytest.mark.asyncio
    async def test_send_command_empty_instance_ids_raises_error(
        self, manager: SSMCommandManager
    ) -> None:
        """Test that sending command with empty instance_ids raises ValidationError."""
        with pytest.raises(ValidationError, match="instance_ids cannot be empty"):
            await manager.send_command(instance_ids=[], commands="echo test")

    @pytest.mark.asyncio
    async def test_get_command_invocation_success(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test getting command invocation status successfully."""
        mock_client.call.return_value = {
            "CommandId": "cmd-test123",
            "InstanceId": "i-1234567890abcdef",
            "Status": "Success",
            "StatusDetails": "Success",
            "StandardOutputContent": "Hello World\n",
            "StandardErrorContent": "",
            "ResponseCode": 0,
        }

        invocation = await manager.get_command_invocation("cmd-test123", "i-1234567890abcdef")

        assert invocation.command_id == "cmd-test123"
        assert invocation.status == "Success"
        assert invocation.stdout == "Hello World\n"
        assert invocation.response_code == 0
        mock_client.call.assert_called_once_with(
            "get_command_invocation",
            CommandId="cmd-test123",
            InstanceId="i-1234567890abcdef",
        )

    @pytest.mark.asyncio
    async def test_get_command_invocation_in_progress(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test getting invocation status for in-progress command."""
        mock_client.call.return_value = {
            "CommandId": "cmd-inprogress",
            "InstanceId": "i-1234567890abcdef",
            "Status": "InProgress",
            "StatusDetails": "Running",
        }

        invocation = await manager.get_command_invocation("cmd-inprogress", "i-1234567890abcdef")

        assert invocation.status == "InProgress"
        assert invocation.stdout is None

    @pytest.mark.asyncio
    async def test_get_command_invocation_failed(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test getting invocation status for failed command."""
        mock_client.call.return_value = {
            "CommandId": "cmd-failed",
            "InstanceId": "i-1234567890abcdef",
            "Status": "Failed",
            "StatusDetails": "Command execution failed",
            "StandardOutputContent": "",
            "StandardErrorContent": "Error: command not found\n",
            "ResponseCode": 127,
        }

        invocation = await manager.get_command_invocation("cmd-failed", "i-1234567890abcdef")

        assert invocation.status == "Failed"
        assert invocation.response_code == 127
        assert "command not found" in invocation.stderr

    @pytest.mark.asyncio
    async def test_wait_for_completion_success(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test waiting for command to complete successfully."""
        # Simulate: Pending -> InProgress -> Success
        mock_client.call.side_effect = [
            {
                "CommandId": "cmd-wait",
                "InstanceId": "i-1234567890abcdef",
                "Status": "Pending",
                "StatusDetails": "Pending",
            },
            {
                "CommandId": "cmd-wait",
                "InstanceId": "i-1234567890abcdef",
                "Status": "InProgress",
                "StatusDetails": "Running",
            },
            {
                "CommandId": "cmd-wait",
                "InstanceId": "i-1234567890abcdef",
                "Status": "Success",
                "StatusDetails": "Success",
                "StandardOutputContent": "Done\n",
                "ResponseCode": 0,
            },
        ]

        invocation = await manager.wait_for_completion(
            "cmd-wait", "i-1234567890abcdef", timeout=30, poll_interval=0.1
        )

        assert invocation.status == "Success"
        assert invocation.stdout == "Done\n"
        assert mock_client.call.call_count == 3

    @pytest.mark.asyncio
    async def test_wait_for_completion_timeout(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test waiting for command that times out."""
        # Always return InProgress
        mock_client.call.return_value = {
            "CommandId": "cmd-timeout",
            "InstanceId": "i-1234567890abcdef",
            "Status": "InProgress",
            "StatusDetails": "Running",
        }

        with pytest.raises(TimeoutError, match="did not complete within"):
            await manager.wait_for_completion(
                "cmd-timeout", "i-1234567890abcdef", timeout=1, poll_interval=0.2
            )

    @pytest.mark.asyncio
    async def test_wait_for_completion_immediate_success(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test waiting for command that is already complete."""
        mock_client.call.return_value = {
            "CommandId": "cmd-done",
            "InstanceId": "i-1234567890abcdef",
            "Status": "Success",
            "StatusDetails": "Success",
            "StandardOutputContent": "Already done\n",
            "ResponseCode": 0,
        }

        invocation = await manager.wait_for_completion("cmd-done", "i-1234567890abcdef", timeout=30)

        assert invocation.status == "Success"
        mock_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_commands_all(self, manager: SSMCommandManager, mock_client: Mock) -> None:
        """Test listing all recent commands."""
        mock_client.call.return_value = {
            "Commands": [
                {
                    "CommandId": "cmd-1",
                    "InstanceIds": ["i-1234567890abcdef"],
                    "DocumentName": "AWS-RunShellScript",
                    "Status": "Success",
                    "Parameters": {"commands": ["ls"]},
                    "RequestedDateTime": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
                },
                {
                    "CommandId": "cmd-2",
                    "InstanceIds": ["i-abcdef1234567890"],
                    "DocumentName": "AWS-RunShellScript",
                    "Status": "InProgress",
                    "Parameters": {"commands": ["pwd"]},
                },
            ]
        }

        commands = await manager.list_commands()

        assert len(commands) == 2
        assert commands[0].command_id == "cmd-1"
        assert commands[0].status == "Success"
        assert commands[1].command_id == "cmd-2"
        assert commands[1].status == "InProgress"

    @pytest.mark.asyncio
    async def test_list_commands_filtered_by_instance(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test listing commands filtered by instance ID."""
        mock_client.call.return_value = {
            "Commands": [
                {
                    "CommandId": "cmd-filtered",
                    "InstanceIds": ["i-1234567890abcdef"],
                    "DocumentName": "AWS-RunShellScript",
                    "Status": "Success",
                }
            ]
        }

        await manager.list_commands(instance_id="i-1234567890abcdef")

        call_args = mock_client.call.call_args
        assert "InstanceId" in call_args[1]
        assert call_args[1]["InstanceId"] == "i-1234567890abcdef"

    @pytest.mark.asyncio
    async def test_list_commands_with_max_results(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test listing commands with max_results limit."""
        mock_client.call.return_value = {"Commands": []}

        await manager.list_commands(max_results=10)

        call_args = mock_client.call.call_args
        assert call_args[1]["MaxResults"] == 10

    @pytest.mark.asyncio
    async def test_cancel_command_all_instances(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test cancelling command on all instances."""
        mock_client.call.return_value = {}

        await manager.cancel_command("cmd-cancel123")

        mock_client.call.assert_called_once_with("cancel_command", CommandId="cmd-cancel123")

    @pytest.mark.asyncio
    async def test_cancel_command_specific_instances(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test cancelling command on specific instances."""
        mock_client.call.return_value = {}

        await manager.cancel_command(
            "cmd-cancel456", instance_ids=["i-1234567890abcdef", "i-abcdef1234567890"]
        )

        call_args = mock_client.call.call_args
        assert "InstanceIds" in call_args[1]
        assert len(call_args[1]["InstanceIds"]) == 2


class TestSSMCommandPreprocessing:
    """Test suite for SSM command preprocessing integration."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Fixture providing a mocked AWSClientWrapper."""
        client = Mock()
        client.call = AsyncMock()
        return client

    @pytest.fixture
    def manager(self, mock_client: Mock) -> SSMCommandManager:
        """Fixture providing an SSMCommandManager with mocked client."""
        return SSMCommandManager(region="us-east-1", client=mock_client)

    @pytest.mark.asyncio
    async def test_commands_are_preprocessed(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test that commands are preprocessed before sending."""
        mock_client.call.return_value = {
            "Command": {
                "CommandId": "cmd-preprocessed",
                "InstanceIds": ["i-1234567890abcdef"],
                "DocumentName": "AWS-RunShellScript",
                "Parameters": {"commands": ["ls -la"]},
                "Status": "Pending",
            }
        }

        # Send as string, should be converted to list
        await manager.send_command(instance_ids=["i-1234567890abcdef"], commands="ls -la")

        call_args = mock_client.call.call_args
        # Preprocessing should convert string to list
        assert isinstance(call_args[1]["Parameters"]["commands"], list)

    @pytest.mark.asyncio
    async def test_empty_commands_after_preprocessing_raises_error(
        self, manager: SSMCommandManager, mock_client: Mock
    ) -> None:
        """Test that empty commands after preprocessing raise ValidationError."""
        # The preprocess function should handle this, but test the validation
        with patch("ohlala_smartops.aws.ssm_commands.preprocess_ssm_commands") as mock_preprocess:
            mock_preprocess.return_value = []  # Empty after preprocessing

            with pytest.raises(ValidationError, match="cannot be empty after preprocessing"):
                await manager.send_command(instance_ids=["i-1234567890abcdef"], commands="")
