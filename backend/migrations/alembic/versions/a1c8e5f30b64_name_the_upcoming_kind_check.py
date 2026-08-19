"""name the upcoming_workouts kind CHECK

Revision ID: a1c8e5f30b64
Revises: d7e4f2a91b83
Create Date: 2026-08-19 12:00:00.000000

`alembic check` has failed since `c4a92f18de07`, and CI with it. The ORM
declares the constraint with a name:

    CheckConstraint("kind IN ('lifting', 'mobility')", name="ck_upcoming_kind")

while the migration added it as part of an `ALTER TABLE ... ADD COLUMN`, where
SQLite records the CHECK anonymously. Autogenerate compares by name, sees a
named constraint present in the models and absent from the database, and
reports a constraint to add — forever, because nothing about it ever changes.

This is the second and last case. `ck_exercises_rating` was the same bug and
was fixed in passing by `d7e4f2a91b83`, which had to rebuild `exercises`
anyway; this one needed a rebuild of its own, which is why it waited.

**A drift check that is permanently red is worse than no drift check**: it
trains everyone to ignore the one signal that catches the ORM and the schema
diverging, and the next divergence will be a real one hiding behind this noise.

SQLite cannot rename or re-declare a constraint in place, so the table is
rebuilt — by hand rather than through `batch_alter_table`, for the reason
`d7e4f2a91b83` records: batch mode rebuilds by *reflection*, and reflection
loses an inline unnamed column CHECK. Here that would silently drop the very
constraint being named. `upcoming_workouts` carries no triggers (0007's
`AUDITED` does not include it — planned rows are not history), so there is
nothing to drop and recreate around it.

The rebuild also normalises column order to match the ORM. `kind` was appended
by ADD COLUMN and sits last in the live table; nothing depends on the order,
but a rebuild is the one free chance to remove the discrepancy.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1c8e5f30b64"
down_revision: str | Sequence[str] | None = "d7e4f2a91b83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


COLUMNS = (
    "id, session, kind, exercise_id, category_id, weight, reps, distance, "
    "distance_unit, time, comment, created_at"
)

INDEXES = (
    "CREATE INDEX ix_upcoming_workouts_session ON upcoming_workouts (session)",
    "CREATE INDEX ix_upcoming_workouts_exercise_id "
    "ON upcoming_workouts (exercise_id)",
    "CREATE INDEX ix_upcoming_workouts_category_id "
    "ON upcoming_workouts (category_id)",
)


def _rebuild(kind_constraint: str) -> None:
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(f"""
        CREATE TABLE upcoming_workouts_new (
            id INTEGER NOT NULL,
            session INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'lifting' {kind_constraint},
            exercise_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            weight FLOAT,
            reps INTEGER,
            distance FLOAT,
            distance_unit VARCHAR(16),
            time VARCHAR(32),
            comment TEXT,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(exercise_id) REFERENCES exercises (id),
            FOREIGN KEY(category_id) REFERENCES categories (id)
        )
    """)
    op.execute(
        f"INSERT INTO upcoming_workouts_new ({COLUMNS}) "
        f"SELECT {COLUMNS} FROM upcoming_workouts"
    )
    op.execute("DROP TABLE upcoming_workouts")
    op.execute("ALTER TABLE upcoming_workouts_new RENAME TO upcoming_workouts")
    for statement in INDEXES:
        op.execute(statement)
    op.execute("PRAGMA foreign_keys = ON")


def upgrade() -> None:
    _rebuild(
        "CONSTRAINT ck_upcoming_kind CHECK (kind IN ('lifting', 'mobility'))"
    )


def downgrade() -> None:
    # Back to anonymous, which is what `c4a92f18de07` produced. The constraint
    # still bites; only its name goes, and with it `alembic check`.
    _rebuild("CHECK (kind IN ('lifting', 'mobility'))")
