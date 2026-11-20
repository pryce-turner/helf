"""exercise field configuration: four groups, and the movement break flag

Revision ID: a3f9c21d7e48
Revises: c8e1f4a7b293
Create Date: 2026-11-19 00:00:00.000000

`movement_break_seconds` carried two facts in one nullable number — pool
membership and the default bout — and the day view's set tiles need much more:
which of the four field groups (Reps, Weight, Distance, Time) a movement
offers at all, and what each offers as a default. Plan 0018 splits the two
facts apart (`movement_break_enabled` is the membership; the ordinary time
defaults are the bout) and adds the configuration around them.

The shape is a dozen typed columns, so the table is rebuilt by hand rather
than through `batch_alter_table`, for the reason `d7e4f2a91b83` records:
batch mode rebuilds by reflection, and reflection loses inline CHECKs. Every
bound is a **named** CHECK — an anonymous one is permanent `alembic check`
drift (see `a1c8e5f30b64`).

Backfill, from the plan:

- `movement_break_enabled` = the old column was not NULL.
- `time_enabled` = in the pool, **or** the movement has any timed history —
  a `workouts.time` value exists for it. Same for `distance_enabled` and
  `distance`.
- `reps_enabled` and `weight_enabled` are on for every existing movement,
  because that is what the day view's editor has always offered; anything
  else would silently shrink it.
- Pool members keep their bout as `default_work_seconds`, get the two-rep
  default the timer applied, and the rest the timer computed:
  `min(30, max(10, round(work / 2)))`.
- Every other default is NULL. Enabled-with-no-default means "offer the
  input, leave it blank".

The audit triggers are rebuilt with the new columns — they enumerate their
columns into `json_object`, so a new one is invisible to the log until they
are recreated, and the dropped one is a trigger that no longer compiles.

The downgrade restores the old column from `default_work_seconds` for pool
members. A member whose work default was cleared comes back with NULL, which
is the honest value — the old shape cannot represent "in the pool with no
bout", because that conflation is what this revision removes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a3f9c21d7e48"
down_revision: str | Sequence[str] | None = "c8e1f4a7b293"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"
OPS = ("INSERT", "UPDATE", "DELETE")

BASE = ["name", "category_id", "form", "application", "rating"]
# The order here is the order in the triggers' json_object; keep it stable so
# the payload diffs read the same way across revisions.
CONFIG = [
    "movement_break_enabled",
    "reps_enabled",
    "default_reps",
    "weight_enabled",
    "default_weight_lb",
    "distance_enabled",
    "default_distance",
    "default_distance_unit",
    "time_enabled",
    "default_work_seconds",
    "default_rest_seconds",
    "default_rest_after_seconds",
]

SHARED = "id, name, category_id, last_used, use_count, created_at, rating, form, application"


def _json_object(alias: str, columns: list[str]) -> str:
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _drop_triggers() -> None:
    for op_name in OPS:
        op.execute(f"DROP TRIGGER IF EXISTS audit_exercises_{op_name.lower()}")


def _create_triggers(columns: list[str]) -> None:
    for op_name in OPS:
        old = _json_object("old", columns) if op_name in ("UPDATE", "DELETE") else "NULL"
        new = _json_object("new", columns) if op_name in ("INSERT", "UPDATE") else "NULL"
        row = "old" if op_name == "DELETE" else "new"
        op.execute(f"""
CREATE TRIGGER audit_exercises_{op_name.lower()}
AFTER {op_name} ON exercises
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('exercises', {row}.id, '{op_name}', {ACTOR}, {old}, {new});
END
""")


def _flag_check(name: str) -> str:
    return (
        f"BOOLEAN NOT NULL {'DEFAULT 1' if name in ('reps_enabled', 'weight_enabled') else 'DEFAULT 0'} "
        f"CONSTRAINT ck_exercises_{name} CHECK ({name} IN (0, 1))"
    )


def upgrade() -> None:
    _drop_triggers()
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(f"""
        CREATE TABLE exercises_new (
            id INTEGER NOT NULL,
            name VARCHAR(150) NOT NULL,
            category_id INTEGER NOT NULL,
            last_used VARCHAR(10),
            use_count INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            rating INTEGER CONSTRAINT ck_exercises_rating
                CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
            form TEXT,
            application TEXT,
            movement_break_enabled {_flag_check("movement_break_enabled")},
            reps_enabled {_flag_check("reps_enabled")},
            default_reps INTEGER CONSTRAINT ck_exercises_default_reps
                CHECK (default_reps IS NULL OR default_reps BETWEEN 1 AND 500),
            weight_enabled {_flag_check("weight_enabled")},
            default_weight_lb FLOAT CONSTRAINT ck_exercises_default_weight_lb
                CHECK (default_weight_lb IS NULL OR default_weight_lb BETWEEN 0 AND 2000),
            distance_enabled {_flag_check("distance_enabled")},
            default_distance FLOAT CONSTRAINT ck_exercises_default_distance
                CHECK (default_distance IS NULL OR default_distance BETWEEN 0 AND 1000),
            default_distance_unit VARCHAR(16),
            time_enabled {_flag_check("time_enabled")},
            default_work_seconds INTEGER CONSTRAINT ck_exercises_default_work_seconds
                CHECK (default_work_seconds IS NULL OR default_work_seconds BETWEEN 1 AND 3600),
            default_rest_seconds INTEGER CONSTRAINT ck_exercises_default_rest_seconds
                CHECK (default_rest_seconds IS NULL OR default_rest_seconds BETWEEN 0 AND 3600),
            default_rest_after_seconds INTEGER CONSTRAINT ck_exercises_default_rest_after_seconds
                CHECK (default_rest_after_seconds IS NULL OR default_rest_after_seconds BETWEEN 0 AND 3600),
            PRIMARY KEY (id),
            FOREIGN KEY(category_id) REFERENCES categories (id)
        )
    """)
    # The backfill is part of the copy so it runs inside the same statement
    # and the same transaction as the rebuild. `x IS NOT NULL` is 1 or 0 in
    # SQLite, which is what the BOOLEAN flags hold.
    op.execute(f"""
        INSERT INTO exercises_new (
            {SHARED},
            movement_break_enabled, reps_enabled, default_reps,
            weight_enabled, default_weight_lb,
            distance_enabled, default_distance, default_distance_unit,
            time_enabled, default_work_seconds, default_rest_seconds,
            default_rest_after_seconds
        )
        SELECT
            {SHARED},
            movement_break_seconds IS NOT NULL,
            1,
            CASE WHEN movement_break_seconds IS NOT NULL THEN 2 END,
            1,
            NULL,
            EXISTS (
                SELECT 1 FROM workouts w
                WHERE w.exercise_id = exercises.id AND w.distance IS NOT NULL
            ),
            NULL,
            NULL,
            movement_break_seconds IS NOT NULL OR EXISTS (
                SELECT 1 FROM workouts w
                WHERE w.exercise_id = exercises.id AND w.time IS NOT NULL
            ),
            movement_break_seconds,
            CASE WHEN movement_break_seconds IS NOT NULL
                 THEN MIN(30, MAX(10, ROUND(movement_break_seconds / 2.0))) END,
            NULL
        FROM exercises
    """)
    op.execute("DROP TABLE exercises")
    op.execute("ALTER TABLE exercises_new RENAME TO exercises")
    op.execute("CREATE INDEX ix_exercises_last_used ON exercises (last_used)")
    op.execute("CREATE UNIQUE INDEX ix_exercises_name ON exercises (name)")
    op.execute("PRAGMA foreign_keys = ON")
    _create_triggers([*BASE, *CONFIG])


def downgrade() -> None:
    _drop_triggers()
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute("""
        CREATE TABLE exercises_new (
            id INTEGER NOT NULL,
            name VARCHAR(150) NOT NULL,
            category_id INTEGER NOT NULL,
            last_used VARCHAR(10),
            use_count INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            rating INTEGER CONSTRAINT ck_exercises_rating
                CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
            form TEXT,
            application TEXT,
            movement_break_seconds INTEGER CONSTRAINT ck_exercises_movement_break_seconds
                CHECK (movement_break_seconds IS NULL OR movement_break_seconds BETWEEN 5 AND 600),
            PRIMARY KEY (id),
            FOREIGN KEY(category_id) REFERENCES categories (id)
        )
    """)
    # Pool membership collapses back into the bout: a member contributes its
    # work default (which may be NULL - see the module docstring), and a
    # non-member is NULL by definition.
    op.execute(f"""
        INSERT INTO exercises_new ({SHARED}, movement_break_seconds)
        SELECT {SHARED},
               CASE WHEN movement_break_enabled AND default_work_seconds IS NOT NULL
                    THEN MIN(600, MAX(5, default_work_seconds)) END
        FROM exercises
    """)
    op.execute("DROP TABLE exercises")
    op.execute("ALTER TABLE exercises_new RENAME TO exercises")
    op.execute("CREATE INDEX ix_exercises_last_used ON exercises (last_used)")
    op.execute("CREATE UNIQUE INDEX ix_exercises_name ON exercises (name)")
    op.execute("PRAGMA foreign_keys = ON")
    _create_triggers([*BASE, "movement_break_seconds"])
