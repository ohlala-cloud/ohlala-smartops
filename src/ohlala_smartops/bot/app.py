"""FastAPI application for Ohlala SmartOps Teams bot.

This module sets up the FastAPI application with health endpoints,
Bot Framework message endpoint, and middleware.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from ohlala_smartops.config.settings import Settings
from ohlala_smartops.version import __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifespan events.

    This context manager handles startup and shutdown events for the FastAPI application,
    including initializing connections, loading resources, and cleanup.

    Args:
        app: FastAPI application instance.

    Yields:
        None during application runtime.
    """
    # Startup
    logger.info(f"Starting Ohlala SmartOps v{__version__}")

    settings = Settings()
    logger.info(f"AWS Region: {settings.aws_region}")
    logger.info(f"Teams App ID: {settings.microsoft_app_id}")

    # TODO: Initialize Bot Framework adapter
    # TODO: Initialize conversation state storage
    # TODO: Initialize MCP clients
    # TODO: Initialize AWS clients

    yield

    # Shutdown
    logger.info("Shutting down Ohlala SmartOps")

    # TODO: Close connections
    # TODO: Cleanup resources


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.

    Example:
        >>> app = create_app()
        >>> # Run with: uvicorn ohlala_smartops.bot.app:app
    """
    app = FastAPI(
        title="Ohlala SmartOps",
        description="AI-powered AWS EC2 management bot for Microsoft Teams",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add GZip middleware for response compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Add custom exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Any, exc: Exception) -> JSONResponse:
        """Handle uncaught exceptions globally.

        Args:
            request: FastAPI request object.
            exc: Exception that was raised.

        Returns:
            JSON response with error details.
        """
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": "An unexpected error occurred. Please try again later.",
            },
        )

    # Register routers
    from ohlala_smartops.bot.health import router as health_router
    from ohlala_smartops.bot.messages import router as messages_router

    app.include_router(health_router, tags=["health"])
    app.include_router(messages_router, prefix="/api/messages", tags=["messages"])

    return app


# Create the application instance
app = create_app()
