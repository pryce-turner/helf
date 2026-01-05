# SQL Migration Plan (TinyDB -> SQLite + SQLAlchemy)

## Implementation Status
- Completed: SQLAlchemy dependency swap, ORM models, repository rewrites, config default DB path.
- Completed: TinyDB JSON migration script, removal of CSV migration/tests/UI copy.
- Remaining: Validate API behavior and smoke-test endpoints.

## 1) Current JSON Schema Analysis (from `data/helf.json` + code)

### Tables and fields observed in `data/helf.json`
- `categories`
  - `name` (str)
  - `created_at` (ISO str)
- `exercises`
  - `name` (str)
  - `category` (str)
  - `last_used` (null in sample, intended ISO date string)
  - `use_count` (int)
  - `created_at` (ISO str)
- `workouts`
  - `date` (YYYY-MM-DD str)
  - `exercise` (str)
  - `category` (str)
  - `weight` (float | null)
  - `weight_unit` (str, default "lbs")
  - `reps` (int | str like "5+" | null)
  - `distance` (float | null)
  - `distance_unit` (str | null)
  - `time` (str | null, e.g. "30:00")
  - `comment` (str | null)
  - `order` (int, non-null in sample, repo guards against null)
  - `created_at` (ISO str)
  - `updated_at` (ISO str)
  - `completed_at` (ISO str | null)
- `upcoming_workouts`
  - Empty in sample JSON, schema inferred from models/migrations:
  - `session` (int)
  - `exercise`, `category`, `weight`, `weight_unit`, `reps`, `distance`, `distance_unit`, `time`, `comment`
  - `created_at` (ISO str)
- `body_composition`
  - Empty in sample JSON, schema inferred from models/migrations:
  - `timestamp` (ISO str)
  - `date` (YYYY-MM-DD str)
  - `weight` (float)
  - `weight_unit` (str, default "kg")
  - `body_fat_pct`, `muscle_mass`, `bmi`, `water_pct`, `bone_mass`, `visceral_fat` (float | null)
  - `metabolic_age` (int | null)
  - `protein_pct` (float | null)
  - `created_at` (ISO str)

### Data quirks/constraints to preserve
- `reps` can be int or string with `+` (e.g. "5+"); calculations parse numeric from string.
- `completed_at` is present on some workouts; nullable.
- `order` is used for per-day sequencing; repo fills missing order with 0/1.
- `exercise` and `category` are denormalized strings; exercises table is derived but may not include all workout exercise names (e.g. ad-hoc/test entries).
- Timestamps are stored as ISO strings, sometimes with timezone offsets.

## 2) Proposed SQL Schema (SQLite + SQLAlchemy ORM)

### Tables
- `categories`
  - `id` INTEGER PK
  - `name` TEXT UNIQUE NOT NULL
  - `created_at` DATETIME NOT NULL

- `exercises`
  - `id` INTEGER PK
  - `name` TEXT UNIQUE NOT NULL
  - `category_id` INTEGER FK -> `categories.id` NOT NULL
  - `last_used` DATE NULL
  - `use_count` INTEGER NOT NULL DEFAULT 0
  - `created_at` DATETIME NOT NULL

- `workouts`
  - `id` INTEGER PK
  - `date` DATE NOT NULL (store as ISO date string or DATE)
  - `exercise_id` INTEGER FK -> `exercises.id` NOT NULL
  - `category_id` INTEGER FK -> `categories.id` NOT NULL
  - `weight` REAL NULL
  - `weight_unit` TEXT NOT NULL
  - `reps` TEXT NULL (store ints as text to preserve "5+")
  - `distance` REAL NULL
  - `distance_unit` TEXT NULL
  - `time` TEXT NULL
  - `comment` TEXT NULL
  - `order` INTEGER NOT NULL DEFAULT 1
  - `created_at` DATETIME NOT NULL
  - `updated_at` DATETIME NOT NULL
  - `completed_at` DATETIME NULL

- `upcoming_workouts`
  - `id` INTEGER PK
  - `session` INTEGER NOT NULL
  - `exercise_id` INTEGER FK -> `exercises.id` NOT NULL
  - `category_id` INTEGER FK -> `categories.id` NOT NULL
  - `weight` REAL NULL
  - `weight_unit` TEXT NOT NULL
  - `reps` TEXT NULL
  - `distance` REAL NULL
  - `distance_unit` TEXT NULL
  - `time` TEXT NULL
  - `comment` TEXT NULL
  - `created_at` DATETIME NOT NULL

- `body_composition`
  - `id` INTEGER PK
  - `timestamp` DATETIME NOT NULL UNIQUE
  - `date` DATE NOT NULL
  - `weight` REAL NOT NULL
  - `weight_unit` TEXT NOT NULL
  - `body_fat_pct` REAL NULL
  - `muscle_mass` REAL NULL
  - `bmi` REAL NULL
  - `water_pct` REAL NULL
  - `bone_mass` REAL NULL
  - `visceral_fat` REAL NULL
  - `metabolic_age` INTEGER NULL
  - `protein_pct` REAL NULL
  - `created_at` DATETIME NOT NULL

### Indexes
- `workouts`: (`date`, `order`), `exercise_id`, `category_id`
- `upcoming_workouts`: `session`, `exercise_id`
- `body_composition`: `date`, `timestamp`
- `exercises`: `category_id`, `last_used`
- `categories`: `name` unique index

## 3) Data Migration Strategy

### Input
- Primary source: `data/helf.json` (TinyDB export).
- Use existing exercises/categories tables, but reconcile with workouts/upcoming data to capture missing names.

### Steps
1. Parse JSON, load all tables into memory.
2. Seed `categories` from JSON categories + categories inferred from workouts/upcoming/exercises (dedupe by name).
3. Seed `exercises` from JSON exercises + any missing exercise names found in workouts/upcoming, linking to category by name (create category if missing).
4. Insert `workouts`, mapping `exercise`/`category` strings to IDs. If `exercise` missing from exercises, create it on the fly with `last_used`/`use_count` defaults.
5. Insert `upcoming_workouts` similarly.
6. Insert `body_composition` rows, enforcing unique `timestamp` (skip duplicates).
7. Validate counts and spot-check anomalies (e.g., workouts referencing unknown categories) with a migration summary.

### Transformation rules
- `reps`: store as text; convert numeric reps to string during migration to keep a single column type.
- `date`: keep as ISO date string; SQLite DATE or TEXT field with ISO format for ordering.
- `created_at`/`updated_at`/`completed_at`/`timestamp`: parse ISO strings into `datetime` when possible; store in DB as DATETIME.

## 4) Code Changes (High-Level)

### Dependencies
- Add `sqlalchemy>=2.x` to `backend/pyproject.toml`.
- Remove TinyDB dependency after migration is in place.

### Database layer
- Replace `app/database.py` TinyDB helpers with SQLAlchemy engine/session setup:
  - `engine = create_engine(f"sqlite:///{settings.db_path}")`
  - `SessionLocal = sessionmaker(...)`
  - `Base = declarative_base()`
  - `get_db()` yields a session (FastAPI dependency pattern).
- Ensure `close_db()` disposes the engine (used in `main.py` shutdown).

### ORM models
- Create `app/db/models.py` (or similar) with SQLAlchemy models for all tables.
- Add relationships for `Category` <-> `Exercise`, and `Exercise`/`Category` <-> `Workout`/`UpcomingWorkout`.

### Repository updates
- Rewrite repositories to use SQLAlchemy sessions:
  - `get_all`, `get_by_id`, `create`, `update`, `delete` using ORM queries.
  - Replace TinyDB `doc_id` with primary key `id` and keep response model compatibility (Pydantic alias `doc_id`).
  - Use SQL `ORDER BY` for sorting and `LIMIT/OFFSET` for pagination.
  - Implement aggregation (`get_workout_counts_by_date`) via `GROUP BY` query.
- Ensure `reorder`, `bulk_reorder`, and `move_to_date` operate in a transaction.

### Config update
- Default `settings.db_path` to `data/helf.db` instead of `helf.json`.
- Preserve env overrides (`DATA_DIR` / `HELF_DATA_PATH`).

## 5) Migration Tooling
- Add a new script, `backend/migrations/tinydb_to_sqlite.py`:
  - Reads TinyDB JSON, writes SQLite DB using SQLAlchemy models.
  - Provides `--force` for overwrite and emits a summary of counts.
- CSV migration is no longer needed and should be removed.

## 6) Cleanup
- Remove legacy CSV tests and UI copy that reference CSV import. (done)

## 7) Validation & Testing
- Add a minimal sanity check script or test to compare row counts per table.
- Manual verification:
  - Run API endpoints for workouts/exercises/upcoming/body composition and confirm responses match pre-migration output.
  - Validate that progression and Wendler services still compute correctly with `reps` stored as text.

## 8) Rollout Checklist
1. Implement SQLAlchemy models + session management. (done)
2. Update repositories and services. (done)
3. Add migration script and update config defaults. (done)
4. Run migration on `data/helf.json` to generate `data/helf.db`. (done)
   - Output: 7 categories, 28 exercises, 248 workouts, 0 upcoming, 0 body composition.
5. Smoke test API endpoints. (pending)
6. Remove TinyDB dependency and any unused TinyDB helpers. (done)

---

If this plan looks good, I will proceed with the implementation steps in order, starting with the SQLAlchemy database layer and models.
