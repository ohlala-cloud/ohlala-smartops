# Multi-stage build for Ohlala SmartOps
# AI-powered AWS EC2 management bot

# Stage 1: Builder
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package and dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# Stage 2: Runtime
FROM python:3.13-slim

# Add metadata labels
LABEL org.opencontainers.image.title="Ohlala SmartOps"
LABEL org.opencontainers.image.description="AI-powered AWS EC2 management bot using Claude (Bedrock) and Microsoft Teams"
LABEL org.opencontainers.image.version="1.1.0"
LABEL org.opencontainers.image.vendor="Ohlala Cloud"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/ohlala-cloud/ohlala-smartops"
LABEL org.opencontainers.image.documentation="https://github.com/ohlala-cloud/ohlala-smartops/blob/main/README.md"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r ohlala && useradd -r -g ohlala -u 1000 -m -s /bin/bash ohlala

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Switch to non-root user
USER ohlala

# Expose FastAPI port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Set environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Use entrypoint script for graceful startup/shutdown
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "ohlala_smartops.bot.app:app", "--host", "0.0.0.0", "--port", "8000"]
