"""Tests for health check endpoints."""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ohlala_smartops.bot.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    # Mock all initialization to avoid Bot Framework dependencies
    with (
        patch("ohlala_smartops.bot.app.Settings"),
        patch("ohlala_smartops.bot.app.create_adapter"),
        patch("ohlala_smartops.bot.app.create_state_manager"),
        patch("ohlala_smartops.bot.app.MCPManager"),
        patch("ohlala_smartops.bot.app.BedrockClient"),
        patch("ohlala_smartops.bot.app.WriteOperationManager"),
        patch("ohlala_smartops.bot.app.AsyncCommandTracker"),
        patch("ohlala_smartops.bot.app.OhlalaBot"),
    ):
        app = create_app()
        return TestClient(app)


class TestHealthEndpoints:
    """Test suite for health check endpoints."""

    def test_health_check(self, client: TestClient) -> None:
        """Test the main health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "checks" in data

        # Status should be degraded due to unimplemented checks
        assert data["status"] in ["degraded", "healthy", "unhealthy"]

        # Verify checks structure
        assert isinstance(data["checks"], dict)
        assert "configuration" in data["checks"]

    def test_liveness_check(self, client: TestClient) -> None:
        """Test the liveness probe endpoint."""
        response = client.get("/health/live")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "alive"
        assert "version" in data

    def test_readiness_check(self, client: TestClient) -> None:
        """Test the readiness probe endpoint."""
        response = client.get("/health/ready")

        # May return 200 or 503 depending on configuration
        assert response.status_code in [200, 503]
        data = response.json()

        assert "ready" in data
        assert "version" in data
        assert "timestamp" in data
        assert "components" in data

        # Verify components structure
        assert isinstance(data["components"], dict)
        assert "configuration" in data["components"]

    def test_startup_check(self, client: TestClient) -> None:
        """Test the startup probe endpoint."""
        response = client.get("/health/startup")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "started"
        assert "version" in data

    def test_version_info(self, client: TestClient) -> None:
        """Test the version information endpoint."""
        response = client.get("/version")

        assert response.status_code == 200
        data = response.json()

        assert "version" in data
        assert "name" in data
        assert "description" in data
        assert data["name"] == "Ohlala SmartOps"


class TestHealthStatusModel:
    """Test the health status response models."""

    def test_health_response_structure(self, client: TestClient) -> None:
        """Test that health response has correct structure."""
        response = client.get("/health")
        data = response.json()

        # Verify timestamp is a valid ISO format
        timestamp = data["timestamp"]
        assert datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Verify checks have status field
        for check_data in data["checks"].values():
            assert "status" in check_data
            assert check_data["status"] in [
                "healthy",
                "degraded",
                "unhealthy",
                "unknown",
            ]

    def test_readiness_response_structure(self, client: TestClient) -> None:
        """Test that readiness response has correct structure."""
        response = client.get("/health/ready")
        data = response.json()

        # Verify timestamp
        timestamp = data["timestamp"]
        assert datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        # Verify components are boolean
        for component_ready in data["components"].values():
            assert isinstance(component_ready, bool)
