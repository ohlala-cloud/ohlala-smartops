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

from ohlala_smartops.ai.bedrock_client import BedrockClient
from ohlala_smartops.bot.adapter import create_adapter
from ohlala_smartops.bot.health import router as health_router
from ohlala_smartops.bot.messages import router as messages_router
from ohlala_smartops.bot.state import create_state_manager
from ohlala_smartops.bot.teams_bot import OhlalaBot
from ohlala_smartops.config.settings import Settings
from ohlala_smartops.mcp.manager import MCPManager
from ohlala_smartops.version import __version__
from ohlala_smartops.workflow.command_tracker import AsyncCommandTracker
from ohlala_smartops.workflow.write_operations import WriteOperationManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Module-level storage for initialized components
# These will be initialized during application startup and accessed by route handlers
adapter: Any | None = None
bot: Any | None = None
state_manager: Any | None = None
mcp_manager: Any | None = None
bedrock_client: Any | None = None
write_op_manager: Any | None = None
command_tracker: Any | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:  # noqa: PLR0915
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

    # Load configuration settings
    settings = Settings()
    logger.info(f"AWS Region: {settings.aws_region}")
    logger.info(f"Teams App ID: {settings.microsoft_app_id}")
    logger.info(f"App Type: {settings.microsoft_app_type}")
    logger.info(f"MCP AWS API URL: {settings.mcp_aws_api_url}")
    logger.info(f"Bedrock Model: {settings.bedrock_model_id}")

    # Use global variables to store initialized components
    global adapter, bot, state_manager, mcp_manager, bedrock_client  # noqa: PLW0603
    global write_op_manager, command_tracker  # noqa: PLW0603

    # Initialize Bot Framework adapter
    logger.info("Initializing Bot Framework adapter...")
    adapter = create_adapter(settings)
    logger.info("Bot Framework adapter initialized successfully")

    # Initialize conversation state storage
    logger.info("Initializing conversation state storage...")
    state_manager = create_state_manager("memory")
    logger.info("Conversation state storage initialized (in-memory)")

    # Initialize MCP manager with graceful fallback
    logger.info("Attempting to initialize MCP manager...")
    mcp_manager = MCPManager()
    try:
        await mcp_manager.initialize()
        if mcp_manager._initialized:
            tools = await mcp_manager.list_available_tools()
            logger.info(f"MCP initialized successfully with {len(tools)} tools available")
        else:
            logger.warning("MCP initialization completed but manager not marked as initialized")
    except Exception as e:
        logger.error(f"Failed to initialize MCP: {e}", exc_info=True)
        logger.info("Application will continue without MCP - fallback mode available")

    # Initialize Bedrock client
    logger.info("Initializing Bedrock client...")
    bedrock_client = BedrockClient(mcp_manager=mcp_manager)
    logger.info("Bedrock client initialized successfully")

    # Initialize and start write operation manager
    logger.info("Starting write operation manager...")
    write_op_manager = WriteOperationManager()
    await write_op_manager.start()
    logger.info("Write operation manager started successfully")

    # Initialize and start async command tracker
    logger.info("Starting async command tracker...")
    command_tracker = AsyncCommandTracker(mcp_manager=mcp_manager)
    await command_tracker.start()
    logger.info("Async command tracker started successfully")

    # Initialize bot instance with all dependencies
    logger.info("Initializing Teams bot instance...")
    bot = OhlalaBot(
        bedrock_client=bedrock_client,
        mcp_manager=mcp_manager,
        state_manager=state_manager,
        write_op_manager=write_op_manager,
        command_tracker=command_tracker,
    )
    logger.info("Teams bot instance initialized successfully")

    logger.info("Startup completed successfully - all components initialized")

    yield

    # Shutdown
    logger.info("Shutting down Ohlala SmartOps")

    # Stop async command tracker
    if command_tracker:
        try:
            logger.info("Stopping async command tracker...")
            await command_tracker.stop()
            logger.info("Async command tracker stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping command tracker: {e}", exc_info=True)

    # Stop write operation manager
    if write_op_manager:
        try:
            logger.info("Stopping write operation manager...")
            await write_op_manager.stop()
            logger.info("Write operation manager stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping write operation manager: {e}", exc_info=True)

    # Close MCP manager
    if mcp_manager:
        try:
            logger.info("Closing MCP manager...")
            await mcp_manager.close()
            logger.info("MCP manager closed successfully")
        except Exception as e:
            logger.error(f"Error closing MCP manager: {e}", exc_info=True)

    logger.info("Shutdown completed successfully")


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
    async def global_exception_handler(_request: Any, exc: Exception) -> JSONResponse:
        """Handle uncaught exceptions globally.

        Args:
            _request: FastAPI request object (unused but required by FastAPI).
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
    app.include_router(health_router, tags=["health"])
    app.include_router(messages_router, prefix="/api/messages", tags=["messages"])

    return app


# Create the application instance
app = create_app()
