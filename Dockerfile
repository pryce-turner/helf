# Multi-stage Dockerfile for Helf: FastAPI + React PWA
# Stage 1: Build frontend (React + Vite)
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci --silent

# Copy frontend source
COPY frontend/ ./

# Build for production
RUN npm run build

# Stage 2: Python dependencies
FROM python:3.12-slim AS backend-deps

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install UV for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy backend dependency files
COPY backend/pyproject.toml backend/README.md ./

# Install dependencies to system Python
RUN uv pip install --system --no-cache .

# Stage 3: Production
FROM python:3.12-slim AS production

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    PYTHONPATH=/app \
    PRODUCTION=true

WORKDIR /app

# Copy Python packages from dependencies stage
COPY --from=backend-deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy backend code
COPY backend/app /app/app

# Copy frontend build
COPY --from=frontend-build /app/frontend/dist /app/static

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health').read()"

# Run FastAPI with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
