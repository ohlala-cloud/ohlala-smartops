# Development Guidelines for Claude Code

This document provides comprehensive development guidelines and coding standards for the Ohlala SmartOps project, optimized for AI-assisted development with Claude Code.

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture Guidelines](#architecture-guidelines)
- [Coding Standards](#coding-standards)
- [Testing Strategy](#testing-strategy)
- [Documentation Requirements](#documentation-requirements)
- [Security Best Practices](#security-best-practices)
- [Performance Guidelines](#performance-guidelines)

## Project Overview

Ohlala SmartOps is an AI-powered AWS EC2 management bot that integrates with Microsoft Teams. The bot uses Claude (via AWS Bedrock) to interpret natural language commands and manage EC2 instances.

### Core Technologies

- **Python 3.13+**: Modern Python with latest type hints and features
- **AWS Bedrock**: Claude API for natural language understanding
- **Boto3**: AWS SDK for EC2 management
- **Microsoft Teams**: Bot interface for user interaction
- **Pydantic**: Data validation and settings management

## Architecture Guidelines

### Project Structure

```
ohlala-smartops/
├── src/
│   └── ohlala_smartops/
│       ├── __init__.py
│       ├── bot/                 # Teams bot implementation
│       ├── aws/                 # AWS EC2 management
│       ├── ai/                  # Claude/Bedrock integration
│       ├── models/              # Pydantic models
│       ├── config/              # Configuration management
│       └── utils/               # Utility functions
├── tests/
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── fixtures/                # Test fixtures
├── docs/                        # Documentation
└── scripts/                     # Utility scripts
```

### Design Principles

1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **Dependency Injection**: Use dependency injection for testability
3. **Interface Segregation**: Define clear interfaces (Protocols) for components
4. **Error Handling**: Explicit error handling with custom exceptions
5. **Configuration**: Use Pydantic Settings for configuration management

## Coding Standards

### Python Version and Features

- **Minimum Version**: Python 3.13
- **Type Hints**: Required for all functions, methods, and variables
- **Modern Syntax**: Use Python 3.13+ features where appropriate

### Code Formatting

```python
# Line length: 100 characters maximum
# Use Black formatter (automatically applied via pre-commit)
# Double quotes for strings (Black default)
```

### Type Hints

All code must include comprehensive type hints:

```python
from typing import Protocol
from collections.abc import Sequence


# Good: Complete type hints
def process_instances(
    instance_ids: Sequence[str],
    action: str,
    dry_run: bool = False,
) -> dict[str, bool]:
    """Process EC2 instances with the specified action.

    Args:
        instance_ids: Sequence of EC2 instance IDs.
        action: Action to perform (start, stop, terminate).
        dry_run: If True, perform a dry run. Defaults to False.

    Returns:
        Dictionary mapping instance IDs to success status.

    Raises:
        ValueError: If action is not valid.
        EC2Error: If AWS API call fails.
    """
    results: dict[str, bool] = {}
    # Implementation
    return results


# Use Protocol for interfaces
class CloudProvider(Protocol):
    """Protocol for cloud provider implementations."""

    def start_instance(self, instance_id: str) -> None:
        """Start a cloud instance."""
        ...

    def stop_instance(self, instance_id: str) -> None:
        """Stop a cloud instance."""
        ...
```

### Docstrings

Use Google-style docstrings for all public APIs:

```python
def calculate_cost(
    instance_type: str,
    hours: float,
    region: str = "us-east-1",
) -> float:
    """Calculate the cost of running an EC2 instance.

    This function calculates the estimated cost based on current
    on-demand pricing for the specified instance type and region.

    Args:
        instance_type: EC2 instance type (e.g., "t3.micro", "m5.large").
        hours: Number of hours to calculate cost for.
        region: AWS region for pricing. Defaults to "us-east-1".

    Returns:
        The calculated cost in USD.

    Raises:
        ValueError: If instance_type is invalid or hours is negative.
        PricingAPIError: If AWS pricing API is unavailable.

    Example:
        >>> cost = calculate_cost("t3.micro", 24)
        >>> print(f"${cost:.2f}")
        $0.24
    """
    if hours < 0:
        raise ValueError("Hours must be non-negative")
    # Implementation
    return 0.0
```

### Error Handling

Define custom exceptions and handle errors explicitly:

```python
# Custom exceptions in models/exceptions.py
class OhlalaSmartOpsError(Exception):
    """Base exception for all Ohlala SmartOps errors."""


class EC2ManagerError(OhlalaSmartOpsError):
    """Exception raised for EC2 management errors."""


class ClaudeAPIError(OhlalaSmartOpsError):
    """Exception raised for Claude API errors."""


# Usage in code
def start_instance(instance_id: str) -> None:
    """Start an EC2 instance.

    Args:
        instance_id: The EC2 instance ID.

    Raises:
        EC2ManagerError: If instance cannot be started.
    """
    try:
        # AWS API call
        response = ec2_client.start_instances(InstanceIds=[instance_id])
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        raise EC2ManagerError(
            f"Failed to start instance {instance_id}: {error_code}"
        ) from e
```

### Pydantic Models

Use Pydantic for data validation and configuration:

```python
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


class EC2Instance(BaseModel):
    """Model for EC2 instance data."""

    instance_id: str = Field(..., pattern=r"^i-[a-f0-9]{8,17}$")
    instance_type: str
    state: str
    region: str = "us-east-1"

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Validate instance state."""
        valid_states = {"pending", "running", "stopping", "stopped", "terminated"}
        if v not in valid_states:
            raise ValueError(f"Invalid state: {v}")
        return v


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    aws_region: str = "us-east-1"
    aws_access_key_id: str
    aws_secret_access_key: str
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    teams_webhook_url: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### Naming Conventions

```python
# Constants: UPPER_CASE_WITH_UNDERSCORES
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# Classes: PascalCase
class EC2Manager:
    pass

# Functions and variables: snake_case
def get_instance_status(instance_id: str) -> str:
    current_state = "running"
    return current_state

# Private attributes/methods: _leading_underscore
class BotHandler:
    def _parse_command(self, message: str) -> dict[str, str]:
        pass

# Type variables: PascalCase with _T suffix
from typing import TypeVar
T = TypeVar("T")
InstanceT = TypeVar("InstanceT", bound="EC2Instance")
```

## Testing Strategy

### Test Organization

```python
# tests/unit/test_ec2_manager.py
from unittest.mock import Mock, patch
import pytest
from ohlala_smartops.aws.ec2_manager import EC2Manager


class TestEC2Manager:
    """Test suite for EC2Manager class."""

    @pytest.fixture
    def ec2_manager(self) -> EC2Manager:
        """Fixture providing an EC2Manager instance."""
        return EC2Manager(region="us-east-1")

    def test_start_instance_success(
        self,
        ec2_manager: EC2Manager,
        mock_ec2_client: Mock,
    ) -> None:
        """Test starting an instance successfully."""
        # Arrange
        instance_id = "i-1234567890abcdef0"
        mock_ec2_client.start_instances.return_value = {
            "StartingInstances": [{"InstanceId": instance_id}]
        }

        # Act
        result = ec2_manager.start_instance(instance_id)

        # Assert
        assert result is True
        mock_ec2_client.start_instances.assert_called_once_with(
            InstanceIds=[instance_id]
        )
```

### Test Coverage Requirements

- Minimum coverage: 80%
- All public APIs must have tests
- Edge cases and error paths must be tested
- Integration tests for external service interactions (mocked)

## Documentation Requirements

### Code Documentation

1. **Module Docstrings**: Every module must have a docstring
2. **Class Docstrings**: Describe purpose and usage
3. **Function Docstrings**: Google-style with Args, Returns, Raises
4. **Inline Comments**: For complex logic only, prefer self-documenting code

### README Structure

- Clear project description
- Quick start guide
- Installation instructions
- Usage examples
- Configuration guide
- Contributing guidelines
- License information

## Security Best Practices

### Credentials Management

```python
# DO: Use environment variables and Pydantic Settings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    aws_access_key_id: str
    aws_secret_access_key: str

    class Config:
        env_file = ".env"


# DON'T: Hardcode credentials
aws_access_key = "AKIAIOSFODNN7EXAMPLE"  # NEVER DO THIS
```

### Input Validation

```python
# Always validate user input
from pydantic import BaseModel, Field

class CommandRequest(BaseModel):
    """User command request."""

    command: str = Field(..., min_length=1, max_length=500)
    instance_id: str = Field(..., pattern=r"^i-[a-f0-9]{8,17}$")

# Validate before processing
def process_command(request: CommandRequest) -> None:
    """Process a validated command."""
    # Request is already validated by Pydantic
    pass
```

### AWS Permissions

- Follow principle of least privilege
- Use IAM roles instead of access keys when possible
- Document required IAM permissions
- Implement resource tagging for access control

## Performance Guidelines

### Async/Await for I/O Operations

```python
import asyncio
from collections.abc import Sequence


async def get_multiple_instances(
    instance_ids: Sequence[str]
) -> list[dict[str, str]]:
    """Fetch multiple instance details concurrently.

    Args:
        instance_ids: List of instance IDs to fetch.

    Returns:
        List of instance detail dictionaries.
    """
    tasks = [get_instance_details(iid) for iid in instance_ids]
    return await asyncio.gather(*tasks)
```

### Caching

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_pricing_data(instance_type: str, region: str) -> float:
    """Get pricing data with caching.

    Args:
        instance_type: EC2 instance type.
        region: AWS region.

    Returns:
        Hourly price in USD.
    """
    # Expensive API call
    return 0.0
```

### Resource Cleanup

```python
from contextlib import contextmanager
from typing import Generator


@contextmanager
def ec2_client(region: str) -> Generator[EC2Client, None, None]:
    """Context manager for EC2 client with automatic cleanup.

    Args:
        region: AWS region.

    Yields:
        Configured EC2 client.
    """
    client = boto3.client("ec2", region_name=region)
    try:
        yield client
    finally:
        # Cleanup if needed
        pass
```

## Code Review Checklist

Before submitting code, verify:

- [ ] All functions have type hints
- [ ] All public APIs have docstrings
- [ ] Tests are included and passing
- [ ] Pre-commit hooks pass
- [ ] No hardcoded credentials or secrets
- [ ] Error handling is comprehensive
- [ ] Code follows naming conventions
- [ ] Pydantic models used for validation
- [ ] Documentation is updated

## Tools and Automation

### Pre-commit Hooks

The following tools run automatically on commit:

- **Black**: Code formatting (100 char line length)
- **Ruff**: Fast linting and import sorting
- **MyPy**: Strict type checking
- **Bandit**: Security scanning
- **Prettier**: Markdown/YAML formatting

### Running Tools Manually

```bash
# Format code
black .

# Lint code
ruff check .

# Type check
mypy src/ --strict

# Run all pre-commit hooks
pre-commit run --all-files

# Run tests
pytest

# Run tests with coverage
pytest --cov --cov-report=html
```

## Additional Resources

- [Python Type Hints Documentation](https://docs.python.org/3/library/typing.html)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [AWS Boto3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [Black Code Style](https://black.readthedocs.io/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)

---

This document should be updated as the project evolves and new patterns emerge.
