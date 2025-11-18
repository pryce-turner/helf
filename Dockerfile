# Production-ready Dockerfile for Helf
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install UV for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependencies stage
FROM base AS dependencies

# Copy only dependency files for better layer caching
COPY pyproject.toml ./
COPY README.md ./

# Install dependencies to system Python (not venv)
RUN uv pip install --system --no-cache .

# Production stage
FROM base AS production

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# Copy application code
COPY app/ /app/app/
COPY run.py /app/

# Create data directory
RUN mkdir -p /app/data

# Set environment variables for production
ENV DATA_DIR=/app/data \
    PYTHONPATH=/app \
    PRODUCTION=true

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080').read()"

# Run the app - uses NiceGUI's built-in Uvicorn server with production settings
CMD ["python", "run.py"]
