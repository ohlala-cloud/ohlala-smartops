# Contributing to Ohlala SmartOps

Thank you for your interest in contributing to Ohlala SmartOps! We welcome contributions from the community.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

This project adheres to a Code of Conduct that all contributors are expected to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a new branch for your changes
5. Make your changes
6. Test your changes
7. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.13 or higher
- Git
- A GitHub account

### Installation

1. Clone your fork:

```bash
git clone https://github.com/YOUR-USERNAME/ohlala-smartops.git
cd ohlala-smartops
```

2. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install the package in development mode with all dependencies:

```bash
pip install -e ".[dev]"
```

4. Install pre-commit hooks:

```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

## Coding Standards

We maintain strict coding standards to ensure code quality and consistency. Please review [CLAUDE.md](CLAUDE.md) for detailed development guidelines.

### Key Requirements

- **Python Version**: 3.13+
- **Line Length**: 100 characters maximum
- **Formatting**: Black formatter (runs automatically via pre-commit)
- **Linting**: Ruff (configured in pyproject.toml)
- **Type Hints**: Required for all functions and methods
- **Type Checking**: MyPy in strict mode
- **Docstrings**: Google-style docstrings required for all public APIs

### Example Function

```python
def calculate_instance_cost(
    instance_type: str,
    hours: int,
    region: str = "us-east-1",
) -> float:
    """Calculate the cost of running an EC2 instance.

    Args:
        instance_type: The EC2 instance type (e.g., "t3.micro").
        hours: Number of hours to calculate cost for.
        region: AWS region for pricing. Defaults to "us-east-1".

    Returns:
        The calculated cost in USD.

    Raises:
        ValueError: If instance_type is not valid or hours is negative.
    """
    if hours < 0:
        raise ValueError("Hours must be non-negative")
    # Implementation here
    return 0.0
```

## Testing

All code contributions must include tests. We use pytest for testing.

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/test_ec2_manager.py

# Run tests matching a pattern
pytest -k test_instance_start
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files as `test_*.py`
- Name test functions as `test_*`
- Use descriptive test names that explain what is being tested
- Follow the Arrange-Act-Assert pattern
- Mock external services (AWS, Teams API, etc.)

Example:

```python
def test_start_instance_success(mock_ec2_client: Mock) -> None:
    """Test starting an EC2 instance successfully."""
    # Arrange
    instance_id = "i-1234567890abcdef0"
    mock_ec2_client.start_instances.return_value = {"StartingInstances": [...]}

    # Act
    result = start_instance(instance_id)

    # Assert
    assert result.success is True
    mock_ec2_client.start_instances.assert_called_once_with(InstanceIds=[instance_id])
```

## Submitting Changes

### Pull Request Process

1. **Update your fork** with the latest changes from the main repository:

   ```bash
   git remote add upstream https://github.com/ohlala-cloud/ohlala-smartops.git
   git fetch upstream
   git rebase upstream/main
   ```

2. **Create a feature branch**:

   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes** following the coding standards

4. **Run the full test suite**:

   ```bash
   pytest
   pre-commit run --all-files
   ```

5. **Commit your changes**:

   ```bash
   git add .
   git commit -m "feat: add feature description"
   ```

   We follow [Conventional Commits](https://www.conventionalcommits.org/) format:
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `test:` Test changes
   - `refactor:` Code refactoring
   - `style:` Code style changes
   - `chore:` Maintenance tasks

6. **Push to your fork**:

   ```bash
   git push origin feature/your-feature-name
   ```

7. **Open a Pull Request** on GitHub with:
   - Clear description of changes
   - Reference to any related issues
   - Screenshots (if applicable)
   - Confirmation that tests pass

### Pull Request Requirements

- All CI checks must pass
- Code coverage must not decrease
- All conversations must be resolved
- At least one approval from a maintainer
- Branch must be up to date with main

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

- Clear description of the issue
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or error messages

### Feature Requests

When requesting features, please include:

- Clear description of the feature
- Use case and motivation
- Proposed implementation (optional)
- Any relevant examples or references

## Questions?

If you have questions about contributing:

- Open an issue with the `question` label
- Check existing issues and discussions
- Review the documentation in [CLAUDE.md](CLAUDE.md)

Thank you for contributing to Ohlala SmartOps!
