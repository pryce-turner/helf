# Use Python 3.12 slim image as base
FROM python:3.12-slim AS builder

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using UV
RUN uv pip install --system --no-cache -r pyproject.toml

# Final stage
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files
COPY workout_tracker.py .
COPY workout_data.py .

# Create volume mount point for persistent data
VOLUME ["/app/data"]

# Expose the port NiceGUI runs on
EXPOSE 8080

# Set environment variable for data directory
ENV DATA_DIR=/app/data

# Run the application
CMD ["python", "workout_tracker.py"]
