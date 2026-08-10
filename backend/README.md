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
│   ├── body_comp.py
│   ├── food.py
│   ├── notes.py
│   └── stacks.py
├── mcp/
│   └── qs_mcp.py        # Stdio MCP server — separate process, read-only
├── db/
│   └── models.py        # SQLAlchemy ORM models (tables)
├── models/              # Pydantic request/response schemas
│   ├── workout.py
│   ├── exercise.py
│   ├── progression.py
│   ├── upcoming.py
│   ├── body_composition.py
│   ├── food.py
│   ├── note.py
│   └── stack.py
├── repositories/        # Data access layer (SQLAlchemy queries)
│   ├── workout_repo.py
│   ├── exercise_repo.py
│   ├── upcoming_repo.py
│   ├── body_comp_repo.py
│   ├── food_repo.py
│   ├── note_repo.py
│   └── stack_repo.py
├── services/            # Business logic
│   ├── progression_service.py
│   ├── mqtt_service.py
│   ├── wendler_service.py
│   ├── liftoscript_service.py
│   ├── bodyspec_client.py
│   └── bodyspec_sync.py
├── utils/               # Pure helper functions
│   ├── calculations.py
│   ├── date_helpers.py
│   └── units.py
└── presets/              # Built-in workout program scripts
    ├── wendler_531.liftoscript
    └── stronglifts_5x5.liftoscript
```

### Layer Responsibilities

- **API routes** (`api/`): HTTP handling, request parsing, response formatting. No business logic.
- **Services** (`services/`): Business logic, calculations, external integrations (MQTT).
- **Repositories** (`repositories/`): Database queries via SQLAlchemy. Auto-creates exercises/categories on reference.
- **Models** (`models/`): Pydantic schemas for validation. **Deliberately
  separate from the ORM models** — they are the HTTP contract, not the storage
  shape, and the two have diverged. The body-composition response has no table
  behind it at all; it is assembled from a view over the tall `metric` store,
  which is why dropping the old wide table changed nothing for the frontend.
- **DB models** (`db/models.py`): SQLAlchemy table definitions. Every table
  carries a docstring explaining what it is for and why it is shaped that way —
  this is the closest thing to a schema reference, and `alembic check` fails if
  it drifts from the migrations.
- **MCP server** (`mcp/qs_mcp.py`): **not** part of these layers. It is a
  separate process that opens the same SQLite file with raw SQL (ADR-0002) and
  imports nothing from the app but `config`.

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
| GET | `/trends?days=30&source=` | Trend arrays for charting (1-365 days); omit `source` to get every point with a parallel `sources` array |
| POST | `/` | Create measurement (manual or from MQTT) |
| POST | `/sync/bodyspec` | Import DEXA scans. Token in the `Authorization` header, used for one request and stored nowhere |
| DELETE | `/{id}` | Delete measurement. **`{id}` is an `observation.id`** — what the read path returns |

### Food `/api/food`

| Method | Path | Description |
|---|---|---|
| GET | `/day?date=` | One day's totals *and* entries, read together so the running total cannot disagree with the list |
| GET | `/log?date=` | Entries for a day |
| GET | `/log/summary?start&end` | Daily kcal and macro totals. Days with nothing logged are **absent, not zero** |
| POST | `/log` | Log a consumption event, by `food_id` or by naming the food |
| DELETE | `/log/{id}` | Delete a logged entry |
| GET | `/?q=&kind=` | Search the catalog; `kind` is `food` or `supplement` |
| POST | `/` | Create a food, or return the existing `(name, brand)` match |
| GET / PUT | `/{id}` | Read / edit macros. **Editing is retroactive** across every past entry |

### Stacks `/api/stacks`

| Method | Path | Description |
|---|---|---|
| GET | `/` | All stacks, each with `taken_today` and `last_taken` |
| POST | `/` | Create a stack; items naming an unknown food create it |
| GET / PUT / DELETE | `/{id}` | `items` on PUT **replaces** the membership wholesale |
| POST | `/{id}/log` | Write one `food_log` row per item, at one instant |

### Notes `/api/notes`

| Method | Path | Description |
|---|---|---|
| GET | `/?kind=&start=&end=` | Notes, most recent first |
| GET | `/kinds` | Counts and date spans per kind, across notes and documents |
| POST | `/` | Write a note |
| GET / DELETE | `/{id}` | Read / delete one |

### System

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check (`{"status": "healthy", "version": "2.0.0"}`) |
| GET | `/api/mqtt/status` | MQTT connection status |
| POST | `/api/mqtt/reconnect` | Trigger MQTT reconnection |

## Database Schema

**Not written out here, on purpose.** A schema in prose goes stale and is then
believed — this section used to document five tables with `weight_unit` columns
and a `reps TEXT` holding AMRAP notation, none of which had existed for several
revisions. There are now thirteen tables and five views.

| Want | Look at |
|---|---|
| What each table is *for* | `app/db/models.py` — a docstring per table, kept honest by `alembic check` |
| Why it is shaped that way | The plan that created it, in `../docs/plans/` |
| The authoritative DDL | `sqlite3 $DATA_DIR/helf.db .schema` |
| A short orientation | `../docs/design/mcp-instructions.md` |

The shape, which does not go stale:

- **Training is flat.** A `workouts` row is one logged set; a session is the
  rows sharing a `date`, ordered by `order`. `reps` is an `INTEGER` and there is
  no AMRAP notation anywhere in the data model (ADR-0005).
- **Everything measured is tall.** An `observation` is one act of measuring — a
  time and an instrument — carrying `metric` rows whose names come from a fixed
  vocabulary in `metric_def`. Adding a quantity is a row, not a migration.
  Adding a *name* is a migration, on purpose.
- **Units live in names.** `body_weight_lb`, `bone_mass_kg`. Pounds are
  canonical for body mass (ADR-0003) and no row carries a unit column.
- **Intake is `food` + `food_log`**, with supplements stored as foods
  (`food.kind`) and `stack`/`stack_item` grouping them for one-tap logging.
  Macros live on the food, so correcting one corrects every past entry.
- **The journal is `note` + `document`** — prose and raw payloads with no
  settled shape yet, expected to be promoted into real columns later.
- **`audit_log` is append-only**, enforced by triggers, and is mutation history
  rather than a data source.

## Services

### ProgressionService
Calculates 1RM estimates from historical workouts and projects future values from upcoming sessions.

- **1RM formula**: `(0.033 * reps * weight) + weight`
- Groups by date, keeps best set per day
- Projects upcoming sessions as future dates (every 2 days)

### MQTTService
Listens to `openScaleSync/measurements/last` and `openScaleSync/measurements/all`
for body composition from the smart scale. Converts timestamps to Pacific.

Only `weight` is converted from kilograms; every other field is a percentage, an
index, an age, or — in the case of bone — a mass that is stored in the unit it
arrived in as `bone_mass_kg`. In particular `muscle` is a **percentage** despite
being named `muscle_mass` in the API: it correlates with body weight at
r = −0.985 across the existing 150 rows, which is the signature of a fraction.

Readings are tagged `source='openscale'` and deduplicated per instrument, so a
manual entry at the same instant is a second measurement rather than a
collision.

### BodySpec sync (`bodyspec_client.py`, `bodyspec_sync.py`)
Pulls DEXA scans on demand. The access token arrives in a request header, is
forwarded upstream, and is written nowhere — no config, no database, no log. It
exists inside Helf for the duration of one request. The raw payload is kept
whole in `document`, and thirteen scalars are promoted to `metric` rows with the
scan's `document_id` for provenance, including a locally computed Katch-McArdle
RMR that BodySpec does not offer.

### WendlerService
Provides estimated 1RM values for the main lifts (Squat, Bench, Deadlift) from the last 10 workouts per exercise. Used by the Liftoscript parser for percentage-based weight calculations.

### MCP server (`app/mcp/qs_mcp.py`)
**Not a service** — a separate process, run as `python -m app.mcp.qs_mcp`, that
opens the same SQLite file directly (ADR-0002) and imports nothing from the app
but `config`. Read tools run on a `mode=ro` connection so the engine itself
refuses a write; write tools are simply **not registered** unless
`QS_MCP_MODE=read-write`, because a tool that does not exist cannot be argued
with. Server instructions load from `../docs/design/mcp-instructions.md`.

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

Fixtures build the database **by running the real migrations** against a
temporary file (`tests/conftest.py`) — not `Base.metadata.create_all()`, and not
in memory. The read path queries views and `metric_def` carries a seeded
vocabulary, neither of which exists in ORM metadata, so `create_all()` would
produce a database the application cannot run against. New tables and seeds must
therefore arrive via a migration.

One trap worth naming: `from app.database import SessionLocal` at module scope
binds the *production* engine, and is only safe if `conftest`'s patch list names
that module. Reference `database.SessionLocal` through the module instead — a
test that gets this wrong writes to `data/helf.db`.

Test categories:

- `test_api_*.py` - API endpoint integration tests
- `test_repositories_*.py` - Repository/database layer tests
- `test_services_*.py` - Business logic tests (Liftoscript, progression, MQTT, Wendler)
- `test_utils*.py` - Utility function tests (calculations, date helpers)
- `test_config.py` - Configuration tests
- `test_migration_script.py` - TinyDB migration test
- `test_db_*.py` - Schema-level behaviour: the tall `metric` model, the daily
  summary view, the audit log's append-only triggers
- `test_mcp_server.py` - The agent's tools and the read-only privilege boundary

## Migrations

Schema is managed by [Alembic](https://alembic.sqlalchemy.org/). The app runs
`upgrade head` at startup (`init_db()`), so no manual step is normally needed.

```bash
alembic current                              # revision the database is on
alembic history                              # all revisions
alembic upgrade head                         # apply pending migrations
alembic downgrade -1                         # undo the last one
alembic check                                # fail if models have drifted
alembic revision --autogenerate -m "message" # write a new revision
```

`env.py` takes the database URL from `app.config.settings.db_path`, so
`DATA_DIR` / `HELF_DATA_PATH` stay the single source of truth — `alembic.ini`
deliberately has no `sqlalchemy.url`.

A database created before Alembic was adopted is stamped at the baseline
automatically on first startup rather than having the baseline replayed against
it. The baseline includes the `exercises.notes` column, which the standalone
`add_exercise_notes.py` script used to add; that script has been removed.

### TinyDB to SQLite
```bash
python migrations/tinydb_to_sqlite.py
```
Converts legacy TinyDB JSON exports to the SQLite schema. A one-shot import, not
part of the Alembic history.

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
