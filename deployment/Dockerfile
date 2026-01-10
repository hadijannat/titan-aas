# Titan-AAS Dockerfile
# Multi-stage build for minimal production image

# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files, README, and LICENSE (required by hatchling for metadata)
COPY pyproject.toml uv.lock README.md LICENSE ./

# Create virtual environment and install dependencies
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv export --frozen --no-dev --no-hashes --no-editable -o /tmp/requirements.txt && \
    uv pip install --no-cache -r /tmp/requirements.txt && \
    python -c "import fastapi, uvicorn"

# Copy source code
COPY src/ ./src/

# Install the package
RUN . /opt/venv/bin/activate && \
    uv pip install --no-deps .

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Create non-root user
RUN groupadd -r titan && useradd -r -g titan titan

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Titan defaults
    TITAN_HOST=0.0.0.0 \
    TITAN_PORT=8080 \
    TITAN_ENV=production

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()"

# Switch to non-root user
USER titan

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "-m", "uvicorn", "titan.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
