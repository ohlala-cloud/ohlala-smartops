"""SSM session management utilities.

This module provides high-level utilities for managing AWS Systems Manager (SSM)
sessions, including starting, terminating, and querying interactive sessions and
port forwarding sessions. All operations use the AWSClientWrapper for automatic
throttling and error handling.
"""

import logging
from typing import Any, Final

from pydantic import BaseModel, Field

from ohlala_smartops.aws.client import AWSClientWrapper, create_aws_client
from ohlala_smartops.aws.exceptions import SSMError, ValidationError

logger: Final = logging.getLogger(__name__)


class SSMSession(BaseModel):
    """Model representing an SSM session with validated data.

    This Pydantic model validates and structures SSM session data from AWS API responses.
    It provides type-safe access to session attributes.

    Attributes:
        session_id: SSM session ID (e.g., 'alice-0123456789abcdef0').
        target: Target instance ID or resource.
        status: Current session status (Active, Terminating, Terminated, etc.).
        start_date: Session start timestamp as ISO string (optional).
        end_date: Session end timestamp as ISO string (optional).
        owner: Session owner principal (optional).
        document_name: SSM document used for the session (optional).
        output_url: S3 URL for session output logs (optional).
    """

    session_id: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    status: str
    start_date: str | None = None
    end_date: str | None = None
    owner: str | None = None
    document_name: str | None = None
    output_url: str | None = None


class SSMSessionManager:
    """Manager for SSM session operations with automatic throttling.

    This class provides high-level methods for managing SSM sessions. It supports
    interactive shell sessions and port forwarding sessions. Note that this manager
    handles session lifecycle only - interactive shell access requires the AWS Session
    Manager plugin on the client side.

    All operations use the AWSClientWrapper for automatic rate limiting, error
    handling, and retries.

    Example:
        >>> manager = SSMSessionManager(region="us-east-1")
        >>> # Start an interactive session
        >>> session = await manager.start_session(
        ...     target="i-123",
        ...     document_name="SSM-SessionManagerRunShell"
        ... )
        >>> print(session.session_id)
        'alice-0123456789abcdef0'
        >>>
        >>> # Start a port forwarding session
        >>> session = await manager.start_session(
        ...     target="i-123",
        ...     document_name="AWS-StartPortForwardingSession",
        ...     parameters={"portNumber": ["3389"]}
        ... )
    """

    def __init__(self, region: str | None = None, client: AWSClientWrapper | None = None) -> None:
        """Initialize SSM session manager.

        Args:
            region: AWS region name. If None, uses default from environment/config.
                Defaults to None.
            client: Optional pre-configured AWSClientWrapper for SSM. If None, creates
                a new one. Defaults to None.

        Example:
            >>> manager = SSMSessionManager(region="us-west-2")
            >>> # Or with existing client:
            >>> client = create_aws_client("ssm", region="eu-west-1")
            >>> manager = SSMSessionManager(client=client)
        """
        self.region = region
        self.client = client or create_aws_client("ssm", region=region)
        logger.info(f"Initialized SSMSessionManager for region {region or 'default'}")

    async def start_session(
        self,
        target: str,
        document_name: str = "SSM-SessionManagerRunShell",
        parameters: dict[str, list[str]] | None = None,
        reason: str | None = None,
    ) -> SSMSession:
        """Start a new SSM session.

        This method starts an SSM session for interactive shell access or port forwarding.
        The session must be accessed using the AWS Session Manager plugin for interactive
        use.

        Args:
            target: Target instance ID or managed instance ID.
            document_name: SSM document name. Common values:
                - "SSM-SessionManagerRunShell": Interactive shell (default)
                - "AWS-StartPortForwardingSession": Port forwarding
                - "AWS-StartPortForwardingSessionToRemoteHost": Remote port forwarding
                Defaults to "SSM-SessionManagerRunShell".
            parameters: Document-specific parameters. For port forwarding, use:
                {"portNumber": ["3389"]} for RDP, {"portNumber": ["22"]} for SSH.
                Defaults to None.
            reason: Reason for starting the session (for audit). Defaults to None.

        Returns:
            SSMSession object with session details including session_id and token.

        Raises:
            ValidationError: If target is empty or document parameters are invalid.
            SSMError: If AWS API call fails.

        Example:
            >>> # Start shell session
            >>> session = await manager.start_session("i-123")
            >>>
            >>> # Start RDP port forwarding
            >>> session = await manager.start_session(
            ...     target="i-123",
            ...     document_name="AWS-StartPortForwardingSession",
            ...     parameters={"portNumber": ["3389"]},
            ...     reason="Remote desktop access for troubleshooting"
            ... )
        """
        if not target:
            raise ValidationError("target cannot be empty", service="ssm")

        logger.info(f"Starting SSM session for target {target} with document {document_name}")

        try:
            # Build API parameters
            kwargs: dict[str, Any] = {
                "Target": target,
                "DocumentName": document_name,
            }

            if parameters:
                kwargs["Parameters"] = parameters

            if reason:
                kwargs["Reason"] = reason

            response = await self.client.call("start_session", **kwargs)

            # Parse session from response
            session = SSMSession(
                session_id=response["SessionId"],
                target=target,
                status="Active",  # New sessions are always active
                document_name=document_name,
                owner=None,  # Owner not in start_session response
            )

            logger.info(f"Successfully started session {session.session_id}")
            return session

        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            if isinstance(e, ValidationError):
                raise
            raise SSMError(
                f"Failed to start session for target {target}: {e}",
                service="ssm",
                operation="start_session",
            ) from e

    async def terminate_session(self, session_id: str) -> None:
        """Terminate an active SSM session.

        Args:
            session_id: SSM session ID to terminate.

        Raises:
            ValidationError: If session_id is empty.
            SSMError: If AWS API call fails.

        Example:
            >>> await manager.terminate_session("alice-0123456789abcdef0")
        """
        if not session_id:
            raise ValidationError("session_id cannot be empty", service="ssm")

        logger.info(f"Terminating SSM session {session_id}")

        try:
            await self.client.call("terminate_session", SessionId=session_id)
            logger.info(f"Successfully terminated session {session_id}")

        except Exception as e:
            logger.error(f"Failed to terminate session: {e}")
            if isinstance(e, ValidationError):
                raise
            raise SSMError(
                f"Failed to terminate session {session_id}: {e}",
                service="ssm",
                operation="terminate_session",
            ) from e

    async def list_sessions(
        self,
        state: str = "Active",
        target: str | None = None,
        max_results: int = 50,
    ) -> list[SSMSession]:
        """List SSM sessions with optional filtering.

        Args:
            state: Session state to filter by. Valid values: "Active", "History" (all states).
                Defaults to "Active".
            target: Optional target instance ID to filter by. Defaults to None.
            max_results: Maximum number of sessions to return (1-200). Defaults to 50.

        Returns:
            List of SSMSession objects matching the filters.

        Raises:
            ValidationError: If state is invalid or max_results is out of range.
            SSMError: If AWS API call fails.

        Example:
            >>> # List all active sessions
            >>> sessions = await manager.list_sessions(state="Active")
            >>>
            >>> # List all sessions for a specific instance
            >>> sessions = await manager.list_sessions(
            ...     state="History",
            ...     target="i-123"
            ... )
        """
        if state not in ("Active", "History"):
            raise ValidationError(
                f"Invalid state: {state}. Must be 'Active' or 'History'",
                service="ssm",
            )

        if not 1 <= max_results <= 200:
            raise ValidationError(
                f"max_results must be between 1 and 200, got {max_results}",
                service="ssm",
            )

        logger.debug(f"Listing SSM sessions: state={state}, target={target}")

        try:
            # Build API parameters
            kwargs: dict[str, Any] = {
                "State": state,
                "MaxResults": max_results,
            }

            # Build filters
            filters: list[dict[str, Any]] = []
            if target:
                filters.append({"key": "Target", "value": target})

            if filters:
                kwargs["Filters"] = filters

            # Handle pagination
            sessions: list[SSMSession] = []
            next_token: str | None = None

            while True:
                if next_token:
                    kwargs["NextToken"] = next_token

                response = await self.client.call("describe_sessions", **kwargs)

                # Parse sessions from response
                for session_data in response.get("Sessions", []):
                    session = self._parse_session(session_data)
                    sessions.append(session)

                # Check for more results
                next_token = response.get("NextToken")
                if not next_token:
                    break

            logger.info(f"Found {len(sessions)} session(s)")
            return sessions

        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            if isinstance(e, ValidationError):
                raise
            raise SSMError(
                f"Failed to list sessions: {e}",
                service="ssm",
                operation="describe_sessions",
            ) from e

    async def get_session_details(self, session_id: str) -> SSMSession:
        """Get detailed information about a specific session.

        Args:
            session_id: SSM session ID to query.

        Returns:
            SSMSession object with session details.

        Raises:
            ValidationError: If session_id is empty.
            SSMError: If session not found or AWS API call fails.

        Example:
            >>> session = await manager.get_session_details("alice-0123456789abcdef0")
            >>> print(session.status)
            'Terminated'
        """
        if not session_id:
            raise ValidationError("session_id cannot be empty", service="ssm")

        logger.debug(f"Getting details for session {session_id}")

        try:
            # Use describe_sessions with session ID filter
            response = await self.client.call(
                "describe_sessions",
                State="History",  # Include all states
                Filters=[{"key": "SessionId", "value": session_id}],
            )

            sessions = response.get("Sessions", [])
            if not sessions:
                raise SSMError(
                    f"Session {session_id} not found",
                    service="ssm",
                    operation="describe_sessions",
                )

            session = self._parse_session(sessions[0])
            logger.info(f"Retrieved details for session {session_id}")
            return session

        except Exception as e:
            logger.error(f"Failed to get session details: {e}")
            if isinstance(e, ValidationError | SSMError):
                raise
            raise SSMError(
                f"Failed to get session details for {session_id}: {e}",
                service="ssm",
                operation="describe_sessions",
            ) from e

    async def resume_session(self, session_id: str) -> dict[str, Any]:
        """Resume an existing SSM session.

        This method retrieves the session token and other information needed to
        reconnect to an existing session using the AWS Session Manager plugin.

        Args:
            session_id: SSM session ID to resume.

        Returns:
            Dictionary containing session connection information including token.

        Raises:
            ValidationError: If session_id is empty.
            SSMError: If AWS API call fails or session cannot be resumed.

        Example:
            >>> connection_info = await manager.resume_session("alice-0123456789abcdef0")
            >>> print(connection_info["SessionId"])
            'alice-0123456789abcdef0'
        """
        if not session_id:
            raise ValidationError("session_id cannot be empty", service="ssm")

        logger.info(f"Resuming SSM session {session_id}")

        try:
            response = await self.client.call("resume_session", SessionId=session_id)

            logger.info(f"Successfully retrieved resume info for session {session_id}")
            return dict(response)

        except Exception as e:
            logger.error(f"Failed to resume session: {e}")
            if isinstance(e, ValidationError):
                raise
            raise SSMError(
                f"Failed to resume session {session_id}: {e}",
                service="ssm",
                operation="resume_session",
            ) from e

    def _parse_session(self, session_data: dict[str, Any]) -> SSMSession:
        """Parse AWS API session data into SSMSession model.

        Args:
            session_data: Raw session data from AWS API.

        Returns:
            Validated SSMSession object.

        Raises:
            ValidationError: If session data doesn't match schema.
        """
        try:
            return SSMSession(
                session_id=session_data["SessionId"],
                target=session_data["Target"],
                status=session_data["Status"],
                start_date=(
                    session_data.get("StartDate", "").isoformat()
                    if session_data.get("StartDate")
                    else None
                ),
                end_date=(
                    session_data.get("EndDate", "").isoformat()
                    if session_data.get("EndDate")
                    else None
                ),
                owner=session_data.get("Owner"),
                document_name=session_data.get("DocumentName"),
                output_url=session_data.get("OutputUrl", {}).get("S3OutputUrl"),
            )
        except Exception as e:
            logger.error(f"Failed to parse session data: {e}")
            raise ValidationError(
                f"Invalid session data: {e}",
                service="ssm",
                operation="parse_session",
            ) from e
