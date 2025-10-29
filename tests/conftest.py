"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def sample_instance_id() -> str:
    """Provide a sample EC2 instance ID for testing.

    Returns:
        A valid-format EC2 instance ID.
    """
    return "i-1234567890abcdef0"


@pytest.fixture
def sample_region() -> str:
    """Provide a sample AWS region for testing.

    Returns:
        AWS region name.
    """
    return "us-east-1"
