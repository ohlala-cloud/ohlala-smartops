"""Tests for SSM session management utilities."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError as PydanticValidationError

from ohlala_smartops.aws.exceptions import SSMError, ValidationError
from ohlala_smartops.aws.ssm_sessions import SSMSession, SSMSessionManager


class TestSSMSession:
    """Test suite for SSMSession Pydantic model."""

    def test_valid_session_creation(self) -> None:
        """Test creating a valid SSMSession."""
        session = SSMSession(
            session_id="alice-0123456789abcdef0",
            target="i-1234567890abcdef",
            status="Active",
            start_date="2024-01-15T10:30:00+00:00",
            owner="arn:aws:iam::123456789012:user/alice",
            document_name="SSM-SessionManagerRunShell",
        )

        assert session.session_id == "alice-0123456789abcdef0"
        assert session.target == "i-1234567890abcdef"
        assert session.status == "Active"
        assert session.owner == "arn:aws:iam::123456789012:user/alice"

    def test_session_with_minimal_fields(self) -> None:
        """Test SSMSession with only required fields."""
        session = SSMSession(
            session_id="bob-abcdef1234567890",
            target="mi-0123456789abcdef0",
            status="Terminated",
        )

        assert session.session_id == "bob-abcdef1234567890"
        assert session.status == "Terminated"
        assert session.start_date is None
        assert session.end_date is None
        assert session.owner is None

    def test_session_with_all_fields(self) -> None:
        """Test SSMSession with all optional fields populated."""
        session = SSMSession(
            session_id="charlie-fedcba9876543210",
            target="i-abcdef1234567890",
            status="Terminating",
            start_date="2024-01-15T10:30:00+00:00",
            end_date="2024-01-15T11:00:00+00:00",
            owner="arn:aws:iam::123456789012:user/charlie",
            document_name="AWS-StartPortForwardingSession",
            output_url="s3://bucket/session-logs/charlie-fedcba9876543210",
        )

        assert session.session_id == "charlie-fedcba9876543210"
        assert session.document_name == "AWS-StartPortForwardingSession"
        assert session.output_url is not None

    def test_empty_session_id_raises_error(self) -> None:
        """Test that empty session ID raises validation error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            SSMSession(session_id="", target="i-123", status="Active")

        assert "session_id" in str(exc_info.value).lower()

    def test_empty_target_raises_error(self) -> None:
        """Test that empty target raises validation error."""
        with pytest.raises(PydanticValidationError) as exc_info:
            SSMSession(session_id="test-123", target="", status="Active")

        assert "target" in str(exc_info.value).lower()


class TestSSMSessionManager:
    """Test suite for SSMSessionManager class."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Fixture providing a mocked AWSClientWrapper."""
        client = Mock()
        client.call = AsyncMock()
        return client

    @pytest.fixture
    def session_manager(self, mock_client: Mock) -> SSMSessionManager:
        """Fixture providing a SSMSessionManager with mocked client."""
        return SSMSessionManager(region="us-east-1", client=mock_client)

    # Tests for start_session()

    @pytest.mark.asyncio
    async def test_start_session_default_document(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test starting a session with default document (shell)."""
        mock_client.call.return_value = {
            "SessionId": "alice-0123456789abcdef0",
            "TokenValue": "token123",
            "StreamUrl": "wss://ssmmessages.us-east-1.amazonaws.com/v1/data-channel/...",
        }

        session = await session_manager.start_session(target="i-123")

        assert session.session_id == "alice-0123456789abcdef0"
        assert session.target == "i-123"
        assert session.status == "Active"
        mock_client.call.assert_called_once_with(
            "start_session",
            Target="i-123",
            DocumentName="SSM-SessionManagerRunShell",
        )

    @pytest.mark.asyncio
    async def test_start_session_port_forwarding(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test starting a port forwarding session."""
        mock_client.call.return_value = {
            "SessionId": "bob-abcdef1234567890",
            "TokenValue": "token456",
            "StreamUrl": "wss://ssmmessages.us-east-1.amazonaws.com/v1/data-channel/...",
        }

        session = await session_manager.start_session(
            target="i-456",
            document_name="AWS-StartPortForwardingSession",
            parameters={"portNumber": ["3389"]},
        )

        assert session.session_id == "bob-abcdef1234567890"
        assert session.document_name == "AWS-StartPortForwardingSession"
        mock_client.call.assert_called_once()
        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["Parameters"] == {"portNumber": ["3389"]}

    @pytest.mark.asyncio
    async def test_start_session_with_reason(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test starting a session with audit reason."""
        mock_client.call.return_value = {
            "SessionId": "charlie-fedcba9876543210",
            "TokenValue": "token789",
            "StreamUrl": "wss://ssmmessages.us-east-1.amazonaws.com/v1/data-channel/...",
        }

        reason = "Troubleshooting production issue #12345"
        session = await session_manager.start_session(target="i-789", reason=reason)

        assert session.session_id == "charlie-fedcba9876543210"
        mock_client.call.assert_called_once()
        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["Reason"] == reason

    @pytest.mark.asyncio
    async def test_start_session_empty_target(self, session_manager: SSMSessionManager) -> None:
        """Test that empty target raises ValidationError."""
        with pytest.raises(ValidationError, match="target cannot be empty"):
            await session_manager.start_session(target="")

    @pytest.mark.asyncio
    async def test_start_session_aws_error(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in SSMError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(SSMError, match="Failed to start session"):
            await session_manager.start_session(target="i-123")

    # Tests for terminate_session()

    @pytest.mark.asyncio
    async def test_terminate_session_success(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test terminating a session successfully."""
        mock_client.call.return_value = {"SessionId": "alice-0123456789abcdef0"}

        await session_manager.terminate_session("alice-0123456789abcdef0")

        mock_client.call.assert_called_once_with(
            "terminate_session", SessionId="alice-0123456789abcdef0"
        )

    @pytest.mark.asyncio
    async def test_terminate_session_empty_id(self, session_manager: SSMSessionManager) -> None:
        """Test that empty session_id raises ValidationError."""
        with pytest.raises(ValidationError, match="session_id cannot be empty"):
            await session_manager.terminate_session("")

    @pytest.mark.asyncio
    async def test_terminate_session_aws_error(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in SSMError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(SSMError, match="Failed to terminate session"):
            await session_manager.terminate_session("alice-0123456789abcdef0")

    # Tests for list_sessions()

    @pytest.mark.asyncio
    async def test_list_sessions_active_only(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test listing only active sessions."""
        start_time = datetime.now(UTC)
        mock_client.call.return_value = {
            "Sessions": [
                {
                    "SessionId": "alice-0123456789abcdef0",
                    "Target": "i-123",
                    "Status": "Active",
                    "StartDate": start_time,
                    "Owner": "arn:aws:iam::123456789012:user/alice",
                    "DocumentName": "SSM-SessionManagerRunShell",
                }
            ]
        }

        sessions = await session_manager.list_sessions(state="Active")

        assert len(sessions) == 1
        assert sessions[0].session_id == "alice-0123456789abcdef0"
        assert sessions[0].status == "Active"
        mock_client.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_sessions_with_target_filter(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test listing sessions filtered by target."""
        mock_client.call.return_value = {"Sessions": []}

        await session_manager.list_sessions(state="History", target="i-456")

        mock_client.call.assert_called_once()
        call_kwargs = mock_client.call.call_args[1]
        assert call_kwargs["Filters"] == [{"key": "Target", "value": "i-456"}]

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test listing sessions with pagination."""
        start_time = datetime.now(UTC)

        # Mock paginated responses
        mock_client.call.side_effect = [
            {
                "Sessions": [
                    {
                        "SessionId": "session-1",
                        "Target": "i-123",
                        "Status": "Active",
                        "StartDate": start_time,
                    }
                ],
                "NextToken": "token1",
            },
            {
                "Sessions": [
                    {
                        "SessionId": "session-2",
                        "Target": "i-456",
                        "Status": "Active",
                        "StartDate": start_time,
                    }
                ]
            },
        ]

        sessions = await session_manager.list_sessions(state="Active")

        assert len(sessions) == 2
        assert mock_client.call.call_count == 2

    @pytest.mark.asyncio
    async def test_list_sessions_empty_result(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test listing sessions with no results."""
        mock_client.call.return_value = {"Sessions": []}

        sessions = await session_manager.list_sessions(state="Active")

        assert sessions == []

    @pytest.mark.asyncio
    async def test_list_sessions_invalid_state(self, session_manager: SSMSessionManager) -> None:
        """Test that invalid state raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid state"):
            await session_manager.list_sessions(state="InvalidState")

    @pytest.mark.asyncio
    async def test_list_sessions_invalid_max_results(
        self, session_manager: SSMSessionManager
    ) -> None:
        """Test that invalid max_results raises ValidationError."""
        with pytest.raises(ValidationError, match="max_results must be between"):
            await session_manager.list_sessions(state="Active", max_results=250)

        with pytest.raises(ValidationError, match="max_results must be between"):
            await session_manager.list_sessions(state="Active", max_results=0)

    @pytest.mark.asyncio
    async def test_list_sessions_aws_error(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in SSMError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(SSMError, match="Failed to list sessions"):
            await session_manager.list_sessions(state="Active")

    # Tests for get_session_details()

    @pytest.mark.asyncio
    async def test_get_session_details_success(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test getting session details successfully."""
        start_time = datetime.now(UTC)
        end_time = datetime.now(UTC)

        mock_client.call.return_value = {
            "Sessions": [
                {
                    "SessionId": "alice-0123456789abcdef0",
                    "Target": "i-123",
                    "Status": "Terminated",
                    "StartDate": start_time,
                    "EndDate": end_time,
                    "Owner": "arn:aws:iam::123456789012:user/alice",
                    "DocumentName": "SSM-SessionManagerRunShell",
                    "OutputUrl": {"S3OutputUrl": "s3://bucket/logs/session"},
                }
            ]
        }

        session = await session_manager.get_session_details("alice-0123456789abcdef0")

        assert session.session_id == "alice-0123456789abcdef0"
        assert session.status == "Terminated"
        assert session.output_url == "s3://bucket/logs/session"

    @pytest.mark.asyncio
    async def test_get_session_details_not_found(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test getting details for non-existent session."""
        mock_client.call.return_value = {"Sessions": []}

        with pytest.raises(SSMError, match="not found"):
            await session_manager.get_session_details("nonexistent-session")

    @pytest.mark.asyncio
    async def test_get_session_details_empty_id(self, session_manager: SSMSessionManager) -> None:
        """Test that empty session_id raises ValidationError."""
        with pytest.raises(ValidationError, match="session_id cannot be empty"):
            await session_manager.get_session_details("")

    @pytest.mark.asyncio
    async def test_get_session_details_aws_error(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in SSMError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(SSMError, match="Failed to get session details"):
            await session_manager.get_session_details("alice-0123456789abcdef0")

    # Tests for resume_session()

    @pytest.mark.asyncio
    async def test_resume_session_success(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test resuming a session successfully."""
        mock_client.call.return_value = {
            "SessionId": "alice-0123456789abcdef0",
            "TokenValue": "resume-token-xyz",
            "StreamUrl": "wss://ssmmessages.us-east-1.amazonaws.com/v1/data-channel/...",
        }

        result = await session_manager.resume_session("alice-0123456789abcdef0")

        assert result["SessionId"] == "alice-0123456789abcdef0"
        assert "TokenValue" in result
        mock_client.call.assert_called_once_with(
            "resume_session", SessionId="alice-0123456789abcdef0"
        )

    @pytest.mark.asyncio
    async def test_resume_session_empty_id(self, session_manager: SSMSessionManager) -> None:
        """Test that empty session_id raises ValidationError."""
        with pytest.raises(ValidationError, match="session_id cannot be empty"):
            await session_manager.resume_session("")

    @pytest.mark.asyncio
    async def test_resume_session_aws_error(
        self, session_manager: SSMSessionManager, mock_client: Mock
    ) -> None:
        """Test that AWS API error is wrapped in SSMError."""
        mock_client.call.side_effect = Exception("AWS API Error")

        with pytest.raises(SSMError, match="Failed to resume session"):
            await session_manager.resume_session("alice-0123456789abcdef0")

    # Tests for initialization

    def test_session_manager_with_region(self) -> None:
        """Test SSMSessionManager initialization with region."""
        manager = SSMSessionManager(region="us-west-2")

        assert manager.region == "us-west-2"
        assert manager.client is not None

    def test_session_manager_with_client(self, mock_client: Mock) -> None:
        """Test SSMSessionManager initialization with pre-configured client."""
        manager = SSMSessionManager(client=mock_client)

        assert manager.client is mock_client

    def test_session_manager_default_region(self) -> None:
        """Test SSMSessionManager initialization with default region."""
        manager = SSMSessionManager()

        assert manager.region is None
        assert manager.client is not None

    # Tests for _parse_session()

    def test_parse_session_with_all_fields(self, session_manager: SSMSessionManager) -> None:
        """Test parsing session data with all fields."""
        start_time = datetime.now(UTC)
        end_time = datetime.now(UTC)

        session_data = {
            "SessionId": "alice-0123456789abcdef0",
            "Target": "i-123",
            "Status": "Terminated",
            "StartDate": start_time,
            "EndDate": end_time,
            "Owner": "arn:aws:iam::123456789012:user/alice",
            "DocumentName": "SSM-SessionManagerRunShell",
            "OutputUrl": {"S3OutputUrl": "s3://bucket/logs/session"},
        }

        session = session_manager._parse_session(session_data)

        assert session.session_id == "alice-0123456789abcdef0"
        assert session.status == "Terminated"
        assert session.output_url == "s3://bucket/logs/session"

    def test_parse_session_minimal_fields(self, session_manager: SSMSessionManager) -> None:
        """Test parsing session data with only required fields."""
        session_data = {
            "SessionId": "bob-abcdef1234567890",
            "Target": "i-456",
            "Status": "Active",
        }

        session = session_manager._parse_session(session_data)

        assert session.session_id == "bob-abcdef1234567890"
        assert session.start_date is None
        assert session.owner is None

    def test_parse_session_invalid_data(self, session_manager: SSMSessionManager) -> None:
        """Test that invalid session data raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid session data"):
            session_manager._parse_session({"InvalidKey": "value"})
