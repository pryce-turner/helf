# Helf Backend API

FastAPI backend for the Helf health and fitness tracking application.

## Setup

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run development server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
