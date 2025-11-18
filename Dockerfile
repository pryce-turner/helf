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

# Install dependencies
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
    PYTHONPATH=/app

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "run.py"]
