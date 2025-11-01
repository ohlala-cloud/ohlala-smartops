"""Health check endpoints for Ohlala SmartOps.

This module provides health check endpoints for monitoring the bot's status
and readiness for handling requests.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from ohlala_smartops.config.settings import Settings
from ohlala_smartops.version import __version__

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthStatus(BaseModel):
    """Health check response model.

    Attributes:
        status: Overall health status (healthy, degraded, unhealthy).
        version: Application version.
        timestamp: Current timestamp.
        checks: Individual component health checks.
    """

    status: str = Field(..., description="Overall health status")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Current timestamp"
    )
    checks: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Individual component health checks"
    )


class ReadinessStatus(BaseModel):
    """Readiness check response model.

    Attributes:
        ready: Whether the service is ready to handle requests.
        version: Application version.
        timestamp: Current timestamp.
        components: Component readiness status.
    """

    ready: bool = Field(..., description="Service readiness status")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Current timestamp"
    )
    components: dict[str, bool] = Field(default_factory=dict, description="Component readiness")


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Health check endpoint.

    This endpoint returns the overall health status of the application,
    including checks for critical components like AWS connectivity,
    Bot Framework adapter, and MCP clients.

    Returns:
        Health status with component checks.

    Example:
        >>> response = client.get("/health")
        >>> assert response.json()["status"] == "healthy"
    """
    checks: dict[str, dict[str, Any]] = {}

    # Check configuration
    try:
        settings = Settings()
        checks["configuration"] = {
            "status": "healthy",
            "aws_region": settings.aws_region,
        }
    except Exception as e:
        logger.error(f"Configuration check failed: {e}")
        checks["configuration"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # TODO: Check AWS connectivity
    checks["aws"] = {
        "status": "unknown",
        "message": "AWS health check not implemented",
    }

    # TODO: Check Bot Framework adapter
    checks["bot_framework"] = {
        "status": "unknown",
        "message": "Bot Framework health check not implemented",
    }

    # TODO: Check MCP clients
    checks["mcp"] = {
        "status": "unknown",
        "message": "MCP health check not implemented",
    }

    # TODO: Check conversation state storage
    checks["state_storage"] = {
        "status": "unknown",
        "message": "State storage health check not implemented",
    }

    # Determine overall status
    statuses = [check["status"] for check in checks.values()]
    if "unhealthy" in statuses:
        overall_status = "unhealthy"
    elif "degraded" in statuses or "unknown" in statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return HealthStatus(
        status=overall_status,
        version=__version__,
        checks=checks,
    )


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check() -> dict[str, str]:
    """Liveness check endpoint.

    This endpoint returns a simple 200 OK if the application is running.
    Used by Kubernetes or container orchestrators for liveness probes.

    Returns:
        Simple status message.

    Example:
        >>> response = client.get("/health/live")
        >>> assert response.status_code == 200
    """
    return {"status": "alive", "version": __version__}


@router.get("/health/ready")
async def readiness_check(response: Response) -> ReadinessStatus:
    """Readiness check endpoint.

    This endpoint returns whether the service is ready to handle requests.
    Used by Kubernetes or load balancers to determine if traffic should be routed.

    Args:
        response: FastAPI response object for setting status code.

    Returns:
        Readiness status with component checks.

    Example:
        >>> response = client.get("/health/ready")
        >>> assert response.json()["ready"] is True
    """
    components: dict[str, bool] = {}

    # Check critical components
    try:
        Settings()
        components["configuration"] = True
    except Exception as e:
        logger.error(f"Configuration not ready: {e}")
        components["configuration"] = False

    # TODO: Check if AWS clients are initialized
    components["aws"] = False  # Not yet implemented

    # TODO: Check if Bot Framework adapter is initialized
    components["bot_framework"] = False  # Not yet implemented

    # TODO: Check if MCP clients are initialized
    components["mcp"] = False  # Not yet implemented

    # Determine overall readiness
    # For now, only require configuration to be ready
    # Once other components are implemented, require them all
    ready = components["configuration"]

    # Set appropriate HTTP status code
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessStatus(
        ready=ready,
        version=__version__,
        components=components,
    )


@router.get("/health/startup", status_code=status.HTTP_200_OK)
async def startup_check() -> dict[str, str]:
    """Startup check endpoint.

    This endpoint is used by Kubernetes startup probes to determine
    if the application has started successfully.

    Returns:
        Simple status message.

    Example:
        >>> response = client.get("/health/startup")
        >>> assert response.status_code == 200
    """
    return {"status": "started", "version": __version__}


@router.get("/version", status_code=status.HTTP_200_OK)
async def version_info() -> dict[str, str]:
    """Version information endpoint.

    Returns the application version and build information.

    Returns:
        Version information.

    Example:
        >>> response = client.get("/version")
        >>> assert "version" in response.json()
    """
    return {
        "version": __version__,
        "name": "Ohlala SmartOps",
        "description": "AI-powered AWS EC2 management bot for Microsoft Teams",
    }
