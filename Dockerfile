# ==============================================================================
# Dawaiflow / ExpiryGuard - Production Multi-Stage Dockerfile
# Python 3.13 Hardened Non-Root Runtime Container with Virtualenv
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Dependency Builder
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS builder

WORKDIR /install

# Install build tools and PostgreSQL development headers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create self-contained Python virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install pinned production requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: Hardened Runtime
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS runner

WORKDIR /app

# Install runtime PostgreSQL client library and networking tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Activate virtual environment in runner's PATH and set python environment
ENV PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV="/opt/venv" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app" \
    PORT=8000

# Create unprivileged system user for secure application execution
RUN groupadd -g 10001 dawaiflow && \
    useradd -u 10001 -g dawaiflow -s /bin/bash -m dawaiflow

# Copy application source code (ignoring caches & local venvs via .dockerignore)
COPY . /app

# Ensure correct file permissions
RUN chown -R dawaiflow:dawaiflow /app && \
    mkdir -p /app/uploads /app/backups && \
    chown -R dawaiflow:dawaiflow /app/uploads /app/backups

# Switch to non-root execution
USER dawaiflow

EXPOSE 8000

# Health check against dedicated health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production entrypoint using Uvicorn ASGI server (dynamically respects Railway $PORT)
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --proxy-headers --forwarded-allow-ips '*'"]
