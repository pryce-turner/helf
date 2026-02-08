# Helf Backend API

FastAPI backend for the Helf health and fitness tracking application.

## Tech Stack

| Technology | Version | Purpose |
|---|---|---|
| FastAPI | 0.127+ | Web framework |
| SQLAlchemy | 2.x | ORM / database access |
| SQLite | 3 | Database |
| Pydantic | v2 | Request/response validation |
| Paho-MQTT | 2.1+ | Smart scale integration |
| Uvicorn | latest | ASGI server |
| UV | latest | Package manager |
| Python | 3.11+ | Runtime |

## Setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies (with dev extras)
uv pip install -e ".[dev]"

# Run development server
python -m uvicorn app.main:app --reload --port 8000

# Run tests
pytest
```

## API Documentation

Once running, interactive docs are available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Architecture

```
app/
├── main.py              # FastAPI app, lifespan, CORS, static files, SPA routing
├── config.py            # Pydantic BaseSettings (env vars)
├── database.py          # SQLAlchemy engine, session, init_db()
├── api/                 # Route handlers (thin controllers)
│   ├── workouts.py
│   ├── exercises.py
│   ├── progression.py
│   ├── upcoming.py
│   └── body_comp.py
├── db/
│   └── models.py        # SQLAlchemy ORM models (tables)
├── models/              # Pydantic request/response schemas
│   ├── workout.py
│   ├── exercise.py
│   ├── progression.py
│   ├── upcoming.py
│   └── body_composition.py
├── repositories/        # Data access layer (SQLAlchemy queries)
│   ├── workout_repo.py
│   ├── exercise_repo.py
│   ├── upcoming_repo.py
│   └── body_comp_repo.py
├── services/            # Business logic
│   ├── progression_service.py
│   ├── mqtt_service.py
│   ├── wendler_service.py
│   └── liftoscript_service.py
├── utils/               # Pure helper functions
│   ├── calculations.py
│   └── date_helpers.py
└── presets/              # Built-in workout program scripts
    ├── wendler_531.liftoscript
    └── stronglifts_5x5.liftoscript
```

### Layer Responsibilities

- **API routes** (`api/`): HTTP handling, request parsing, response formatting. No business logic.
- **Services** (`services/`): Business logic, calculations, external integrations (MQTT).
- **Repositories** (`repositories/`): Database queries via SQLAlchemy. Auto-creates exercises/categories on reference.
- **Models** (`models/`): Pydantic schemas for validation. Separate from ORM models.
- **DB models** (`db/models.py`): SQLAlchemy table definitions with relationships.

## API Endpoints

### Workouts `/api/workouts`

| Method | Path | Description |
|---|---|---|
| GET | `/` | List workouts (optional `?date=YYYY-MM-DD`, `?skip=`, `?limit=`) |
| GET | `/calendar?year=&month=` | Workout counts per day for calendar view |
| GET | `/{id}` | Get single workout |
| POST | `/` | Create workout |
| PUT | `/{id}` | Update workout |
| DELETE | `/{id}` | Delete workout |
| PATCH | `/reorder` | Bulk reorder (drag-and-drop) |
| PATCH | `/{id}/complete` | Toggle workout completion |
| POST | `/date/{source_date}/move` | Move all workouts to a different date |
| POST | `/date/{source_date}/copy` | Copy all workouts to a different date |

### Exercises `/api/exercises`

| Method | Path | Description |
|---|---|---|
| GET | `/` | List all exercises |
| GET | `/recent?limit=10` | Recently used exercises |
| GET | `/{name}` | Get exercise by name |
| POST | `/` | Create exercise |
| PUT | `/{id}` | Update exercise |
| DELETE | `/{id}` | Delete exercise |
| POST | `/seed` | Generate preset exercises (16 exercises across 6 categories) |
| GET | `/categories/` | List all categories |
| GET | `/categories/{name}` | Get category by name |
| GET | `/categories/{name}/exercises` | List exercises in category |
| POST | `/categories/` | Create category |

### Progression `/api/progression`

| Method | Path | Description |
|---|---|---|
| GET | `/` | Main lifts progression (Bench, Squat, Deadlift) |
| GET | `/{exercise}` | Single exercise progression with 1RM estimates |
| GET | `/exercises/list` | All exercises available for progression charts |

### Upcoming Workouts `/api/upcoming`

| Method | Path | Description |
|---|---|---|
| GET | `/` | List all upcoming workouts (grouped by session) |
| GET | `/session/{session}` | Get workouts for a specific session |
| POST | `/` | Create single upcoming workout |
| POST | `/bulk` | Create multiple upcoming workouts |
| DELETE | `/session/{session}` | Delete all workouts in a session |
| POST | `/session/{session}/transfer` | Transfer session to historical workouts |
| GET | `/wendler/maxes` | Get current estimated 1RM for main lifts |
| POST | `/liftoscript/generate` | Parse Liftoscript script and generate workouts |
| GET | `/presets` | List available workout presets |
| GET | `/presets/{name}` | Get preset script content |

### Body Composition `/api/body-composition`

| Method | Path | Description |
|---|---|---|
| GET | `/` | List measurements (optional date range filter) |
| GET | `/latest` | Most recent measurement |
| GET | `/stats` | Summary statistics (totals, changes, date range) |
| GET | `/trends?days=30` | Trend arrays for charting (1-365 days) |
| POST | `/` | Create measurement (manual or from MQTT) |
| DELETE | `/{id}` | Delete measurement |

### System

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check (`{"status": "healthy", "version": "2.0.0"}`) |
| GET | `/api/mqtt/status` | MQTT connection status |
| POST | `/api/mqtt/reconnect` | Trigger MQTT reconnection |

## Database Schema

SQLite database at `{DATA_DIR}/helf.db` with 5 tables:

### `categories`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| name | TEXT | Unique |
| created_at | TEXT | ISO timestamp |

### `exercises`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| name | TEXT | Unique, indexed |
| category_id | INTEGER | FK -> categories |
| notes | TEXT | Optional |
| last_used | TEXT | Date string |
| use_count | INTEGER | Default 0 |
| created_at | TEXT | ISO timestamp |

### `workouts`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| date | TEXT | Indexed (YYYY-MM-DD) |
| exercise_id | INTEGER | FK -> exercises |
| category_id | INTEGER | FK -> categories |
| weight | REAL | Optional |
| weight_unit | TEXT | "lbs" or "kg" |
| reps | TEXT | Supports AMRAP notation ("5+") |
| distance | REAL | Optional |
| distance_unit | TEXT | Optional |
| time | TEXT | Optional |
| comment | TEXT | Optional |
| order | INTEGER | For drag-reorder |
| completed_at | TEXT | Optional completion timestamp |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | ISO timestamp |

Composite index on `(date, order)`.

### `upcoming_workouts`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| session | INTEGER | Indexed (groups workouts into sessions) |
| exercise_id | INTEGER | FK -> exercises |
| category_id | INTEGER | FK -> categories |
| weight | REAL | Optional |
| weight_unit | TEXT | "lbs" or "kg" |
| reps | TEXT | Optional |
| distance | REAL | Optional |
| distance_unit | TEXT | Optional |
| time | TEXT | Optional |
| comment | TEXT | Optional |
| created_at | TEXT | ISO timestamp |

### `body_composition`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER | Primary key |
| timestamp | TEXT | Unique (ISO timestamp) |
| date | TEXT | Date portion |
| weight | REAL | Required |
| weight_unit | TEXT | "kg" or "lbs" |
| body_fat_pct | REAL | Optional |
| muscle_mass | REAL | Optional |
| bmi | REAL | Optional |
| water_pct | REAL | Optional |
| bone_mass | REAL | Optional |
| visceral_fat | REAL | Optional |
| metabolic_age | REAL | Optional |
| protein_pct | REAL | Optional |
| created_at | TEXT | ISO timestamp |

Composite index on `(date, timestamp)`.

## Services

### ProgressionService
Calculates 1RM estimates from historical workouts and projects future values from upcoming sessions.

- **1RM formula**: `(0.033 * reps * weight) + weight`
- Groups by date, keeps best set per day
- Projects upcoming sessions as future dates (every 2 days)

### MQTTService
Listens to `openScaleSync/measurements/last` and `openScaleSync/measurements/all` topics for automatic body composition data from smart scales. Converts timestamps to Pacific timezone. Deduplicates by timestamp.

### WendlerService
Provides estimated 1RM values for the main lifts (Squat, Bench, Deadlift) from the last 10 workouts per exercise. Used by the Liftoscript parser for percentage-based weight calculations.

### LiftoscriptParser
Parses a simplified Liftoscript syntax for defining workout programs:

```
// Squat 1RM: 315lb
// Bench Press 1RM: 225lb

## Week 1 Day 1
Squat / 3x5 65%
Bench Press / 3x5 65%
Pull Ups / 3x8 bodyweight

## Week 1 Day 2
Deadlift / 1x5 135lb
Overhead Press / 5x5 95lb
```

**Supported features**:
- `## Day Name` session headers
- `Exercise / sets x reps weight` format
- Weight formats: `135lb`, `60kg`, `65%` (of 1RM), `bodyweight`
- `progress: lp(5lb)` for linear progression
- AMRAP notation (`5+`) converted to comment
- `// Exercise 1RM: 225lb` or `// Exercise SW: 135lb` comments for percentage/progression base values
- Automatic kg-to-lbs conversion (factor: 2.20462)
- Rounds barbell weights to nearest 5 lbs
- Multi-cycle repetition

## Configuration

Environment variables (via Pydantic BaseSettings):

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `/app/data` | SQLite database directory |
| `HELF_DATA_PATH` | - | Alternative to DATA_DIR |
| `MQTT_BROKER_HOST` | `host.docker.internal` | MQTT broker hostname |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `PRODUCTION` | `true` | Production mode flag |
| `DEBUG` | `false` | Debug mode |

Timezone is hardcoded to `America/Los_Angeles` (Pacific).

## Testing

```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Single test file
pytest tests/test_services_liftoscript.py

# With coverage
pytest --cov=app
```

Tests use an **in-memory SQLite database** (configured in `tests/conftest.py`). Test categories:

- `test_api_*.py` - API endpoint integration tests
- `test_repositories_*.py` - Repository/database layer tests
- `test_services_*.py` - Business logic tests (Liftoscript, progression, MQTT, Wendler)
- `test_utils*.py` - Utility function tests (calculations, date helpers)
- `test_config.py` - Configuration tests
- `test_migration_script.py` - TinyDB migration test

## Migrations

### TinyDB to SQLite
```bash
python migrations/tinydb_to_sqlite.py
```
Converts legacy TinyDB JSON exports to the SQLite schema.

### Add Exercise Notes
```bash
python migrations/add_exercise_notes.py
```
Adds the `notes` column to the exercises table.

## Adding a New Endpoint

1. Define Pydantic schemas in `app/models/`
2. Add repository methods in `app/repositories/`
3. (Optional) Add service logic in `app/services/`
4. Create route handler in `app/api/`
5. Register router in `app/main.py`:
   ```python
   app.include_router(new_router, prefix="/api/new-resource", tags=["new-resource"])
   ```
6. Add tests in `tests/`
