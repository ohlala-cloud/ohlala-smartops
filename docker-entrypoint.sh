#!/bin/bash
set -e

# Ohlala SmartOps Docker Entrypoint Script
# Handles startup validation and graceful shutdown

echo "==================================="
echo "Ohlala SmartOps - Starting up..."
echo "==================================="

# Function for logging
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

# Function for error handling
error_exit() {
    log "ERROR: $1"
    exit 1
}

# Validate required environment variables
log "Validating configuration..."

# AWS Configuration (optional if using IAM roles)
if [ -z "$AWS_REGION" ]; then
    log "WARNING: AWS_REGION not set, will use default region"
fi

# Microsoft Teams Configuration (required)
if [ -z "$TEAMS_APP_ID" ] || [ -z "$TEAMS_APP_PASSWORD" ]; then
    error_exit "TEAMS_APP_ID and TEAMS_APP_PASSWORD are required"
fi

# Bedrock Configuration (required)
if [ -z "$BEDROCK_MODEL_ID" ]; then
    log "WARNING: BEDROCK_MODEL_ID not set, using default"
fi

log "Configuration validation complete"

# Display startup information
log "Starting Ohlala SmartOps Bot"
log "Python version: $(python --version)"
log "Port: ${PORT:-8000}"
log "AWS Region: ${AWS_REGION:-default}"
log "Bedrock Model: ${BEDROCK_MODEL_ID:-anthropic.claude-3-5-sonnet-20240620-v1:0}"

# Handle graceful shutdown
trap 'log "Received SIGTERM, shutting down gracefully..."; exit 0' SIGTERM
trap 'log "Received SIGINT, shutting down gracefully..."; exit 0' SIGINT

# Execute the main command
log "Executing: $*"
exec "$@"
