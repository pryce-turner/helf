"""cardio exercises carry a unit, and their sets carry time and an amount

Revision ID: a5f701728b12
Revises: b6f31a90c4de
Create Date: 2026-11-01 00:00:00.000000

Every exercise was implicitly resistance work: a set was weight x reps, and a
Stairmaster session had nowhere to put "20 minutes, 60 floors". Plan 0017.

- `exercises.cardio_unit` is the unit a cardio exercise is measured in. Being
  non-null **is** what makes an exercise cardio. There is no separate flag,
  because a flag and a unit could disagree and nothing here should be able to.
- `workouts.duration_s`, `workouts.amount`, `workouts.amount_unit` are the set.
  The unit is copied onto the set (prefilled from the exercise, editable), so
  changing an exercise's default later does not relabel its history.
  `duration_s` carries its unit in its name (ADR-0003 §4), and is whole seconds
  so it can be summed.

The legacy `distance`, `distance_unit` and `time` columns are left alone and
not reused. `distance` would hold floors and steps, which are not distances;
`time` is free text with 35 rows of unknown shape (0004's count), so it cannot
become seconds without someone looking at it; and `distance_unit` cannot gain
a CHECK without rebuilding `workouts`, which SQLite needs for any constraint
on an existing column. New columns take their CHECK in the ADD COLUMN, named,
so `alembic check` stays clean (docs/plans/README.md).

**The unit vocabulary is a CHECK, and is spelled out here rather than imported.**
The agent writes raw SQL and never passes through Pydantic (ADR-0002), so the
constraint is the only rule both writers obey. Adding a unit is a migration.

**Both tables' audit triggers are rebuilt**: they enumerate their columns into
`json_object`, so a new column is invisible to the log until they are.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a5f701728b12"
down_revision: str | Sequence[str] | None = "b6f31a90c4de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UNITS = ("miles", "km", "meters", "floors", "steps", "kcal")
_UNIT_LIST = ", ".join(f"'{u}'" for u in UNITS)

ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"

EXERCISE_OPS = ["INSERT", "UPDATE", "DELETE"]
WORKOUT_OPS = ["UPDATE", "DELETE"]

EXERCISE_BEFORE = ["name", "category_id", "form", "application", "rating"]
EXERCISE_AFTER = EXERCISE_BEFORE + ["cardio_unit"]

WORKOUT_BEFORE = ["date", "exercise_id", "category_id", "weight", "reps",
                  "distance", "time", "comment", "order", "completed_at",
                  "is_mobility"]
WORKOUT_AFTER = WORKOUT_BEFORE + ["duration_s", "amount", "amount_unit"]

COLUMNS = {
    "exercises": [
        ("cardio_unit",
         f"TEXT CONSTRAINT ck_exercises_cardio_unit "
         f"CHECK (cardio_unit IS NULL OR cardio_unit IN ({_UNIT_LIST}))"),
    ],
    "workouts": [
        ("duration_s",
         "INTEGER CONSTRAINT ck_workouts_duration_s "
         "CHECK (duration_s IS NULL OR duration_s >= 0)"),
        ("amount",
         "FLOAT CONSTRAINT ck_workouts_amount CHECK (amount IS NULL OR amount >= 0)"),
        ("amount_unit",
         f"TEXT CONSTRAINT ck_workouts_amount_unit "
         f"CHECK (amount_unit IS NULL OR amount_unit IN ({_UNIT_LIST}))"),
    ],
}


def _json_object(alias: str, columns: list[str]) -> str:
    """`order` is a reserved word, so every column is quoted (0007)."""
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _create_triggers(table: str, ops: list[str], columns: list[str]) -> None:
    for op_name in ops:
        old = _json_object("old", columns) if op_name in ("UPDATE", "DELETE") else "NULL"
        new = _json_object("new", columns) if op_name in ("INSERT", "UPDATE") else "NULL"
        row = "old" if op_name == "DELETE" else "new"
        op.execute(f"""
CREATE TRIGGER audit_{table}_{op_name.lower()}
AFTER {op_name} ON {table}
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('{table}', {row}.id, '{op_name}', {ACTOR}, {old}, {new});
END
""")


def _drop_triggers(table: str, ops: list[str]) -> None:
    for op_name in ops:
        op.execute(f"DROP TRIGGER IF EXISTS audit_{table}_{op_name.lower()}")


def upgrade() -> None:
    for table, columns in COLUMNS.items():
        for name, ddl in columns:
            op.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    _drop_triggers("exercises", EXERCISE_OPS)
    _create_triggers("exercises", EXERCISE_OPS, EXERCISE_AFTER)
    _drop_triggers("workouts", WORKOUT_OPS)
    _create_triggers("workouts", WORKOUT_OPS, WORKOUT_AFTER)


def downgrade() -> None:
    # SQLite will not drop a column a trigger names, so the triggers come down
    # first. A CHECK on the column itself does not block DROP COLUMN; only one
    # naming it from elsewhere would, and none does.
    _drop_triggers("exercises", EXERCISE_OPS)
    _drop_triggers("workouts", WORKOUT_OPS)

    for table, columns in COLUMNS.items():
        for name, _ in reversed(columns):
            op.execute(f"ALTER TABLE {table} DROP COLUMN {name}")

    _create_triggers("exercises", EXERCISE_OPS, EXERCISE_BEFORE)
    _create_triggers("workouts", WORKOUT_OPS, WORKOUT_BEFORE)
