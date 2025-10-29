# Ohlala SmartOps

> AI-powered AWS EC2 management bot using Claude (Bedrock) and Microsoft Teams

[![CI](https://github.com/ohlala-cloud/ohlala-smartops/workflows/CI/badge.svg)](https://github.com/ohlala-cloud/ohlala-smartops/actions)
[![codecov](https://codecov.io/gh/ohlala-cloud/ohlala-smartops/branch/main/graph/badge.svg)](https://codecov.io/gh/ohlala-cloud/ohlala-smartops)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Overview

[TODO: Add project overview and key features]

## Features

- **Natural Language Interface**: Interact with AWS EC2 using natural language via Microsoft Teams
- **AI-Powered**: Leverages Claude (via AWS Bedrock) for intelligent command interpretation
- **Secure**: Built with security best practices and IAM role-based access control
- **Type-Safe**: Fully typed Python codebase with strict MyPy checking
- **Well-Tested**: Comprehensive test suite with high coverage requirements

## Quick Start

[TODO: Add quick start instructions]

## Installation

### Prerequisites

- Python 3.13 or higher
- AWS Account with Bedrock access
- Microsoft Teams workspace

### Development Setup

1. Clone the repository:

```bash
git clone https://github.com/ohlala-cloud/ohlala-smartops.git
cd ohlala-smartops
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -e ".[dev]"
```

4. Install pre-commit hooks:

```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

5. Configure environment variables:

```bash
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

[TODO: Add configuration details]

## Usage

[TODO: Add usage examples]

### Basic Commands

[TODO: Add command examples]

### Advanced Features

[TODO: Add advanced features documentation]

## Architecture

[TODO: Add architecture diagram and explanation]

## Development

### Code Quality

This project maintains strict code quality standards:

- **Black** for code formatting (100 char line length)
- **Ruff** for fast linting
- **MyPy** for strict type checking
- **Pytest** for testing with >80% coverage requirement
- **Pre-commit hooks** for automated quality checks

See [CLAUDE.md](CLAUDE.md) for detailed development guidelines.

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/test_ec2_manager.py
```

### Code Style

```bash
# Format code
black .

# Lint code
ruff check .

# Type check
mypy src/ --strict

# Run all checks
pre-commit run --all-files
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this project.

### Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Security

[TODO: Add security policy and reporting instructions]

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [Claude](https://www.anthropic.com/claude) by Anthropic
- Powered by [AWS Bedrock](https://aws.amazon.com/bedrock/)
- Integrated with [Microsoft Teams](https://www.microsoft.com/microsoft-teams/)

## Support

[TODO: Add support information]

## Roadmap

[TODO: Add project roadmap]

---

Made with ❤️ by the Ohlala SmartOps team
