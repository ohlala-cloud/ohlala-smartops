# Security Policy

## Supported Versions

We release patches for security vulnerabilities. Currently supported versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.1.x   | :white_check_mark: |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability in Ohlala SmartOps, please report it to us privately:

- **Email**: contact@ohlala.cloud
- **Subject**: [SECURITY] Brief description of the issue

### What to Include

Please include the following information in your report:

- Type of vulnerability (e.g., SQL injection, XSS, authentication bypass)
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the vulnerability, including how an attacker might exploit it

### Response Timeline

- **Initial Response**: Within 48 hours of receiving your report
- **Assessment**: We will assess the vulnerability within 5 business days
- **Fix Timeline**: Critical vulnerabilities will be patched within 7 days; others within 30 days
- **Disclosure**: We will coordinate disclosure timing with you after a fix is available

## Security Best Practices

### For Users

When deploying Ohlala SmartOps:

1. **Use IAM Roles**: Deploy on ECS/EC2 with IAM roles instead of access keys
2. **Private Subnets**: Deploy containers in private subnets with no direct internet access
3. **Secrets Management**: Store credentials in AWS Secrets Manager, not environment variables
4. **Enable Audit Logging**: Set `ENABLE_AUDIT_LOGGING=true` for compliance tracking
5. **Least Privilege**: Grant only minimum required IAM permissions
6. **Enable Guardrails**: Use Bedrock Guardrails to filter sensitive content
7. **Network Security**: Use security groups to restrict access
8. **Regular Updates**: Keep dependencies and the application updated

### IAM Permissions

Required minimum IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ssm:DescribeInstanceInformation",
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
        "bedrock:InvokeModel",
        "cloudwatch:GetMetricStatistics"
      ],
      "Resource": "*"
    }
  ]
}
```

Avoid using `"Action": "*"` or `"Resource": "*"` without proper conditions.

## Security Features

Ohlala SmartOps includes the following security features:

### Authentication & Authorization

- Microsoft Teams OAuth authentication via Bot Framework
- Azure AD integration for user identity
- Team-based access control via CODEOWNERS

### Data Protection

- No persistent storage of conversation data (in-memory only)
- PII filtering in audit logs (configurable via `AUDIT_LOG_INCLUDE_PII`)
- Bedrock Guardrails support for content filtering

### Network Security

- Designed for private subnet deployment
- API Gateway with optional WAF protection
- Internal service-to-service authentication via API keys

### Audit & Monitoring

- Comprehensive audit logging for all operations
- CloudWatch metrics for monitoring
- Command execution tracking and history

### Input Validation

- All user inputs validated via Pydantic models
- SSM command validation and sanitization
- Dangerous command pattern detection

### Rate Limiting

- Built-in throttling for AWS API calls
- Circuit breaker pattern for fault tolerance
- Configurable rate limits to prevent abuse

## Known Security Considerations

### Command Execution

- SSM commands are executed with the EC2 instance's IAM role permissions
- Approval workflows required for sensitive commands
- Output limited to 24,000 characters to prevent information disclosure

### AI Model Usage

- Claude Sonnet 4.5 processes user messages via AWS Bedrock
- Messages are not stored by Ohlala SmartOps (see AWS Bedrock data policies)
- Use Bedrock Guardrails to filter sensitive content if required

### Secrets

- Microsoft Teams credentials must be stored securely
- Use AWS Secrets Manager for production deployments
- Never commit credentials to version control

## Third-Party Dependencies

We regularly update dependencies to address security vulnerabilities:

- Dependabot alerts enabled
- Automated security scanning via Bandit in CI/CD
- Monthly dependency review and updates

## Security Updates

Security updates are released as soon as possible after a vulnerability is confirmed. Subscribe to:

- GitHub Security Advisories: https://github.com/ohlala-cloud/ohlala-smartops/security/advisories
- Watch releases: https://github.com/ohlala-cloud/ohlala-smartops/releases

## Compliance

Ohlala SmartOps is designed to support:

- AWS Well-Architected Framework security pillar
- Principle of least privilege (IAM)
- Audit logging for compliance requirements
- Data residency (all processing in your AWS account)

## Questions?

For security-related questions that are not vulnerabilities, please open a GitHub Discussion or contact us at contact@ohlala.cloud.

---

**Thank you for helping keep Ohlala SmartOps and our users safe!**
