# Ohlala SmartOps - Deployment Guide

This guide covers deploying Ohlala SmartOps in various environments, from local development to production AWS ECS deployments.

## Table of Contents

- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Deployment Options](#deployment-options)
  - [Docker Run (Simple)](#docker-run-simple)
  - [Docker Compose (Local Development)](#docker-compose-local-development)
  - [AWS ECS Fargate (Production)](#aws-ecs-fargate-production)
- [Configuration](#configuration)
- [Health Checks and Monitoring](#health-checks-and-monitoring)
- [Troubleshooting](#troubleshooting)
- [Security Best Practices](#security-best-practices)

---

## Quick Start

The fastest way to run Ohlala SmartOps:

```bash
# Pull the latest image
docker pull ghcr.io/ohlala-cloud/ohlala-smartops:latest

# Run with environment variables
docker run -d \
  --name ohlala-smartops \
  -p 8000:8000 \
  -e TEAMS_APP_ID="your-app-id" \
  -e TEAMS_APP_PASSWORD="your-app-password" \
  -e AWS_REGION="us-east-1" \
  ghcr.io/ohlala-cloud/ohlala-smartops:latest
```

---

## Prerequisites

### Required

1. **Docker** (20.10+) or **Docker Desktop**
2. **Microsoft Teams App** registered in Azure
   - App ID
   - App Password
   - Bot endpoint configured
3. **AWS Account** with appropriate IAM permissions
4. **AWS Bedrock** access in your region

### Recommended

- Docker Compose (for local development)
- AWS CLI configured
- Basic understanding of container orchestration

---

## Deployment Options

### Docker Run (Simple)

Best for: Quick testing, single-host deployments

#### Step 1: Create environment file

Create a `.env` file with your configuration:

```bash
# Microsoft Teams Configuration
TEAMS_APP_ID=your-app-id-here
TEAMS_APP_PASSWORD=your-app-password-here
TEAMS_TENANT_ID=your-tenant-id-here

# AWS Configuration (optional if using IAM roles)
AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=your-access-key  # Optional
# AWS_SECRET_ACCESS_KEY=your-secret  # Optional

# Bedrock Configuration
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
BEDROCK_GUARDRAIL_ID=your-guardrail-id  # Optional
BEDROCK_GUARDRAIL_VERSION=1  # Optional

# Application Configuration
PORT=8000
LOG_LEVEL=INFO
```

#### Step 2: Run the container

```bash
docker run -d \
  --name ohlala-smartops \
  -p 8000:8000 \
  --env-file .env \
  --restart unless-stopped \
  ghcr.io/ohlala-cloud/ohlala-smartops:latest
```

#### Step 3: Verify deployment

```bash
# Check container status
docker ps | grep ohlala-smartops

# View logs
docker logs ohlala-smartops

# Test health endpoint
curl http://localhost:8000/health
```

#### Managing the container

```bash
# Stop the bot
docker stop ohlala-smartops

# Start the bot
docker start ohlala-smartops

# Restart the bot
docker restart ohlala-smartops

# Remove the container
docker rm -f ohlala-smartops

# View real-time logs
docker logs -f ohlala-smartops
```

---

### Docker Compose (Local Development)

Best for: Local development, testing, multi-service setups

#### Step 1: Clone the repository

```bash
git clone https://github.com/ohlala-cloud/ohlala-smartops.git
cd ohlala-smartops
```

#### Step 2: Create environment file

Copy the example and configure:

```bash
cp .env.example .env
# Edit .env with your credentials
```

#### Step 3: Start services

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

#### Development mode with hot reload

Uncomment the volume mount in `docker-compose.yml`:

```yaml
volumes:
  - ./src:/app/src:ro
```

Then restart:

```bash
docker-compose restart
```

---

### AWS ECS Fargate (Production)

Best for: Production deployments, scalability, managed infrastructure

#### Architecture Overview

```
┌─────────────────┐
│ Microsoft Teams │
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────────────────┐
│   Application Load Balancer │
│   (ALB)                     │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│   ECS Fargate Service       │
│   ┌─────────────────────┐   │
│   │  Ohlala SmartOps    │   │
│   │  Container          │   │
│   │  - FastAPI          │   │
│   │  - Bot Handler      │   │
│   │  - AWS Integration  │   │
│   └─────────────────────┘   │
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│   AWS Services              │
│   - Bedrock (Claude)        │
│   - EC2, SSM, CloudWatch    │
│   - IAM                     │
└─────────────────────────────┘
```

#### Prerequisites

1. **VPC** with at least 2 subnets in different AZs
2. **ECS Cluster** created
3. **IAM Role** for task execution
4. **IAM Role** for task (with EC2, Bedrock permissions)
5. **Application Load Balancer** (optional but recommended)
6. **Route53** or external DNS for custom domain

#### Step 1: Create IAM Roles

**Task Execution Role** (`ecsTaskExecutionRole`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Attach managed policy: `arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy`

**Task Role** (`ohlalaSmartOpsTaskRole`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:RebootInstances",
        "ec2:DescribeTags",
        "ec2:CreateTags",
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
        "ssm:DescribeInstanceInformation",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics",
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "*"
    }
  ]
}
```

#### Step 2: Store secrets in AWS Secrets Manager (Recommended)

```bash
# Store Teams App Password
aws secretsmanager create-secret \
  --name ohlala/teams-app-password \
  --secret-string "your-teams-app-password"

# Store other sensitive data as needed
aws secretsmanager create-secret \
  --name ohlala/teams-app-id \
  --secret-string "your-teams-app-id"
```

#### Step 3: Create ECS Task Definition

Save as `task-definition.json`:

```json
{
  "family": "ohlala-smartops",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ohlalaSmartOpsTaskRole",
  "containerDefinitions": [
    {
      "name": "ohlala-smartops",
      "image": "ghcr.io/ohlala-cloud/ohlala-smartops:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "AWS_REGION",
          "value": "us-east-1"
        },
        {
          "name": "BEDROCK_MODEL_ID",
          "value": "anthropic.claude-3-5-sonnet-20240620-v1:0"
        },
        {
          "name": "PORT",
          "value": "8000"
        },
        {
          "name": "LOG_LEVEL",
          "value": "INFO"
        }
      ],
      "secrets": [
        {
          "name": "TEAMS_APP_ID",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:ohlala/teams-app-id"
        },
        {
          "name": "TEAMS_APP_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:YOUR_ACCOUNT_ID:secret:ohlala/teams-app-password"
        }
      ],
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "curl -f http://localhost:8000/health || exit 1"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 40
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/ohlala-smartops",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs",
          "awslogs-create-group": "true"
        }
      }
    }
  ]
}
```

Register the task definition:

```bash
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

#### Step 4: Create ECS Service

```bash
aws ecs create-service \
  --cluster your-ecs-cluster \
  --service-name ohlala-smartops \
  --task-definition ohlala-smartops:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxx,subnet-yyy],
    securityGroups=[sg-xxx],
    assignPublicIp=ENABLED
  }" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:region:account-id:targetgroup/your-tg,
    containerName=ohlala-smartops,
    containerPort=8000" \
  --health-check-grace-period-seconds 60
```

#### Step 5: Configure Application Load Balancer

1. **Target Group**:
   - Protocol: HTTP
   - Port: 8000
   - Health check path: `/health`
   - Health check interval: 30 seconds

2. **Listener Rule**:
   - Port: 443 (HTTPS)
   - Forward to target group
   - SSL Certificate from ACM

#### Step 6: Update Microsoft Teams Bot Endpoint

In Azure Portal, update your bot's messaging endpoint:

```
https://your-alb-dns-name.region.elb.amazonaws.com/api/messages
```

Or with custom domain:

```
https://bot.yourdomain.com/api/messages
```

#### Scaling Configuration

Auto-scaling based on CPU/Memory:

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/your-cluster/ohlala-smartops \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# Create scaling policy
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/your-cluster/ohlala-smartops \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu-scaling \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

`scaling-policy.json`:

```json
{
  "TargetValue": 70.0,
  "PredefinedMetricSpecification": {
    "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
  },
  "ScaleInCooldown": 300,
  "ScaleOutCooldown": 60
}
```

---

## Configuration

### Environment Variables Reference

#### Required Variables

| Variable             | Description                  | Example                                |
| -------------------- | ---------------------------- | -------------------------------------- |
| `TEAMS_APP_ID`       | Microsoft Teams App ID       | `12345678-1234-1234-1234-123456789012` |
| `TEAMS_APP_PASSWORD` | Microsoft Teams App Password | `your-secret-password`                 |
| `AWS_REGION`         | AWS Region for operations    | `us-east-1`                            |

#### Optional Variables

| Variable                   | Description            | Default                                     |
| -------------------------- | ---------------------- | ------------------------------------------- |
| `BEDROCK_MODEL_ID`         | Claude model to use    | `anthropic.claude-3-5-sonnet-20240620-v1:0` |
| `PORT`                     | HTTP server port       | `8000`                                      |
| `LOG_LEVEL`                | Logging level          | `INFO`                                      |
| `BEDROCK_GUARDRAIL_ID`     | Bedrock guardrail ID   | None                                        |
| `MAX_CONCURRENT_AWS_CALLS` | Max parallel AWS calls | `10`                                        |
| `THROTTLE_RATE_LIMIT`      | Requests per second    | `5.0`                                       |

See `.env.example` for complete list of configuration options.

---

## Health Checks and Monitoring

### Health Endpoint

```bash
curl http://localhost:8000/health
```

Response:

```json
{
  "status": "healthy",
  "version": "1.1.0",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### CloudWatch Logs

When deployed on ECS, logs are available in CloudWatch:

```bash
# View logs
aws logs tail /ecs/ohlala-smartops --follow

# Search logs
aws logs filter-log-events \
  --log-group-name /ecs/ohlala-smartops \
  --filter-pattern "ERROR"
```

### Metrics to Monitor

- **Container CPU/Memory Usage**
- **Request count and latency**
- **Health check failures**
- **AWS API throttling errors**
- **Bedrock API call latency**

---

## Troubleshooting

### Container won't start

1. Check logs:

   ```bash
   docker logs ohlala-smartops
   ```

2. Verify environment variables:

   ```bash
   docker exec ohlala-smartops env | grep TEAMS
   ```

3. Test health endpoint:
   ```bash
   curl http://localhost:8000/health
   ```

### Teams bot not responding

1. Verify bot endpoint is accessible from internet
2. Check Azure Bot Service configuration
3. Verify TEAMS_APP_ID and TEAMS_APP_PASSWORD
4. Check application logs for authentication errors

### AWS permission errors

1. Verify IAM role has required permissions (see SECURITY.md)
2. Check AWS credentials are configured
3. Verify Bedrock access in your region
4. Test with AWS CLI from same environment

### High memory usage

1. Check number of concurrent conversations
2. Review LOG_LEVEL setting (DEBUG increases memory)
3. Consider increasing container memory
4. Monitor for memory leaks in logs

---

## Security Best Practices

### 1. Never commit secrets

- Use environment variables or AWS Secrets Manager
- Never hardcode credentials in images
- Use `.env` files locally (not in version control)

### 2. Use IAM roles in ECS

Prefer IAM roles over access keys:

```json
{
  "taskRoleArn": "arn:aws:iam::account:role/ohlalaSmartOpsTaskRole"
}
```

### 3. Enable HTTPS

- Always use HTTPS for Teams bot endpoint
- Use AWS Certificate Manager for SSL certs
- Configure ALB with SSL/TLS termination

### 4. Network security

- Use VPC with private subnets
- Configure security groups to allow only necessary traffic:
  - Inbound: Port 8000 from ALB only
  - Outbound: HTTPS to AWS services

### 5. Regular updates

```bash
# Pull latest security patches
docker pull ghcr.io/ohlala-cloud/ohlala-smartops:latest

# Restart container
docker restart ohlala-smartops
```

### 6. Audit logging

Enable audit logging for compliance:

```bash
ENABLE_AUDIT_LOGGING=true
AUDIT_LOG_LEVEL=INFO
```

---

## Next Steps

- Review [SECURITY.md](../SECURITY.md) for IAM permissions
- Check [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup
- See [README.md](../README.md) for architecture details

---

## Support

For issues and questions:

- GitHub Issues: https://github.com/ohlala-cloud/ohlala-smartops/issues
- Documentation: https://github.com/ohlala-cloud/ohlala-smartops

---

**Last Updated**: January 2025
**Version**: 1.1.0
