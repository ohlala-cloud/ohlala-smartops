# Ohlala SmartOps

> AI-powered AWS EC2 management bot using Claude (Bedrock) and Microsoft Teams

[![CI](https://github.com/ohlala-cloud/ohlala-smartops/workflows/CI/badge.svg)](https://github.com/ohlala-cloud/ohlala-smartops/actions)
[![codecov](https://codecov.io/gh/ohlala-cloud/ohlala-smartops/branch/main/graph/badge.svg)](https://codecov.io/gh/ohlala-cloud/ohlala-smartops)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Overview

Ohlala SmartOps is an AI-powered EC2 instance management bot that integrates with Microsoft Teams to provide comprehensive monitoring, troubleshooting, and management capabilities for your AWS infrastructure. Using Claude (via AWS Bedrock), the bot interprets natural language commands and executes them securely via AWS Systems Manager.

Perfect for DevOps teams, system administrators, and cloud engineers who want to manage EC2 instances directly from their chat platform without switching context to the AWS Console.

## Features

- **Natural Language Interface**: Interact with AWS EC2 using natural language via Microsoft Teams
- **AI-Powered**: Leverages Claude Sonnet 4.5 via AWS Bedrock for intelligent command interpretation
- **Automatic Discovery**: Finds all SSM-enabled EC2 instances across regions
- **Health Monitoring**: Real-time CPU, RAM, and disk metrics with visual charts
- **Remote Management**: Execute shell/PowerShell commands via SSM with approval workflows
- **Multi-Language Support**: Available in English, French, German, and Spanish
- **MCP Integration**: Uses Model Context Protocol for AWS operations and documentation access
- **Secure**: Built with security best practices, IAM role-based access control, and audit logging
- **Type-Safe**: Fully typed Python 3.13+ codebase with strict MyPy checking
- **Well-Tested**: Comprehensive test suite with 80%+ coverage requirements

## Quick Start

### Prerequisites

- Python 3.13 or higher
- AWS Account with Bedrock access (Claude model access required)
- Microsoft Teams workspace with app installation permissions
- Azure Bot registration (for Teams integration)

## Installation

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

See `.env.example` for all configuration options. Key settings include:

- **AWS Configuration**: Region, credentials (or use IAM roles)
- **Microsoft Teams**: App ID, password, tenant ID
- **Bedrock**: Guardrails configuration (optional)
- **MCP Servers**: URLs for AWS API and knowledge servers
- **Rate Limiting**: Throttling settings to prevent API quota exhaustion
- **Audit Logging**: Compliance and security logging options

All configuration is loaded from environment variables for 12-factor app compliance.

## Usage

### Basic Commands

Once deployed and added to your Teams workspace, you can interact with the bot:

```
@Ohlala SmartOps help
@Ohlala SmartOps list instances
@Ohlala SmartOps show i-1234567890abcdef0
@Ohlala SmartOps health i-1234567890abcdef0
```

### Natural Language Commands

The bot understands natural language through Claude:

```
@Ohlala SmartOps what instances are running in us-east-1?
@Ohlala SmartOps show me the CPU usage for my web servers
@Ohlala SmartOps check disk space on i-1234567890abcdef0
@Ohlala SmartOps restart the nginx service on the production server
```

### Approval Workflows

Sensitive operations (like executing commands) require approval:

1. User requests command execution
2. Bot sends approval card to Teams channel
3. Authorized user approves/denies
4. Bot executes and reports results

## Architecture

The bot uses a multi-container architecture designed for deployment on AWS ECS:

```
┌─────────────────┐
│ Microsoft Teams │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  API Gateway    │  (Optional WAF protection)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         ECS Cluster                 │
│  ┌─────────────────────────────┐   │
│  │  Main Bot Container         │   │
│  │  - FastAPI app              │   │
│  │  - Teams Bot Framework      │   │
│  │  - Bedrock client           │   │
│  │  - Command orchestration    │   │
│  └───────┬─────────────────────┘   │
│          │                          │
│  ┌───────▼─────────────────────┐   │
│  │  MCP AWS API Container      │   │
│  │  - AWS API operations       │   │
│  │  - EC2, SSM, CloudWatch     │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│   AWS Services  │
│  - EC2          │
│  - SSM          │
│  - Bedrock      │
│  - CloudWatch   │
└─────────────────┘
```

**Key Components:**

- **Main Bot Container**: Handles Teams webhooks, orchestrates commands, manages conversations
- **MCP AWS API Server**: Provides secure AWS API access via Model Context Protocol
- **Bedrock Integration**: Uses Claude for natural language understanding and response generation
- **In-Memory Storage**: Conversation state and command history (current session only)
- **CloudWatch**: Comprehensive metrics and logging

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

Security is a top priority for Ohlala SmartOps:

- **Least Privilege IAM**: All AWS operations use least-privilege IAM policies
- **Approval Workflows**: Sensitive commands require explicit approval
- **Audit Logging**: All actions are logged for compliance and security review
- **Secrets Management**: Credentials stored in AWS Secrets Manager (not in code)
- **Network Security**: Designed for deployment in private subnets with security groups
- **Input Validation**: All user inputs validated and sanitized
- **Rate Limiting**: Built-in throttling to prevent abuse and quota exhaustion

For security issues, please email contact@ohlala-cloud.com or open a confidential security advisory on GitHub.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [Claude](https://www.anthropic.com/claude) by Anthropic
- Powered by [AWS Bedrock](https://aws.amazon.com/bedrock/)
- Integrated with [Microsoft Teams](https://www.microsoft.com/microsoft-teams/)

## Support

- **Documentation**: Check [CLAUDE.md](CLAUDE.md) for development guidelines
- **Issues**: Report bugs or request features via [GitHub Issues](https://github.com/ohlala-cloud/ohlala-smartops/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/ohlala-cloud/ohlala-smartops/discussions)
- **Contributing**: See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines

## Roadmap

- [x] Core EC2 instance management
- [x] Health monitoring with metrics
- [x] SSM command execution with approvals
- [x] Multi-language support (EN, FR, DE, ES)
- [x] MCP integration for AWS operations
- [x] Support for additional AWS services (RDS, Lambda, etc.)
- [ ] Cost optimization recommendations (basic)
- [ ] Google integration
- [ ] Automated remediation actions

---

Made with ❤️ by the Ohlala SmartOps team
