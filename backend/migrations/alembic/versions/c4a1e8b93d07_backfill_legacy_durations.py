"""backfill legacy h:mm:ss durations onto the set tiles

Revision ID: c4a1e8b93d07
Revises: b7e2d4f81a05
Create Date: 2026-11-20 00:00:00.000000

`b7e2d4f81a05` parsed only a plain `m:ss` when it moved legacy `time` values
onto the numeric target fields. Production's legacy values turned out to be
`h:mm:ss` — every one of the 35 is `0:00:30`, `0:00:45`, `0:00:55` or
`0:01:00` — so the first backfill parsed zero rows. This revision parses
**both** shapes by component, bounds them to the column CHECK (1..3600
seconds), and touches only rows still missing a `work_seconds` — anything
b7e2 already parsed, or a tile written since, is left alone.

The `workouts` audit triggers are dropped before the DML and recreated
after, the order b7e2 itself now follows: a backfill is schema maintenance,
not a mutation, and UPDATEs on this table are otherwise logged one-to-one.
The 9,487 rows the first production run wrote stay where they are —
`audit_log` is append-only and this migration does not pretend otherwise.

Downgrade is a no-op: the parsed values are data, and un-parsing them would
be exactly the kind of history edit this database does not do.
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a1e8b93d07"
down_revision: str | Sequence[str] | None = "b7e2d4f81a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"
WORKOUT_OPS = ("UPDATE", "DELETE")

TRIGGER_COLUMNS = [
    "date", "exercise_id", "category_id", "weight", "reps", "distance",
    "time", "comment", "order", "completed_at", "is_mobility",
    "work_seconds", "rest_seconds", "rest_after_seconds",
    "completed_reps", "actual_work_seconds", "actual_rest_seconds",
    "actual_rest_after_seconds", "ended_early",
]

#: h:mm:ss first — the two shapes share a suffix, so the longer pattern must
#: win. Bounds are enforced against the column CHECK rather than the pattern.
H_MM_SS_RE = re.compile(r"^(\d{1,4}):([0-5]\d):([0-5]\d)$")
M_SS_RE = re.compile(r"^(\d{1,4}):([0-5]\d)$")

MAX_SECONDS = 3600  # ck_workouts_work_seconds upper bound


def _parse_seconds(time_value: str) -> int | None:
    """Seconds from `h:mm:ss` or `m:ss`, or None when ambiguous or unbounded."""
    value = time_value.strip()
    match = H_MM_SS_RE.match(value)
    if match:
        seconds = (
            int(match.group(1)) * 3600
            + int(match.group(2)) * 60
            + int(match.group(3))
        )
    else:
        match = M_SS_RE.match(value)
        if not match:
            return None
        seconds = int(match.group(1)) * 60 + int(match.group(2))
    return seconds if 1 <= seconds <= MAX_SECONDS else None


def _json_object(alias: str, columns: list[str]) -> str:
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _drop_triggers() -> None:
    for op_name in WORKOUT_OPS:
        op.execute(f"DROP TRIGGER IF EXISTS audit_workouts_{op_name.lower()}")


def _create_triggers() -> None:
    for op_name in WORKOUT_OPS:
        old = _json_object("old", TRIGGER_COLUMNS) if op_name in ("UPDATE", "DELETE") else "NULL"
        new = _json_object("new", TRIGGER_COLUMNS) if op_name in ("INSERT", "UPDATE") else "NULL"
        row = "old" if op_name == "DELETE" else "new"
        op.execute(f"""
CREATE TRIGGER audit_workouts_{op_name.lower()}
AFTER {op_name} ON workouts
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('workouts', {row}.id, '{op_name}', {ACTOR}, {old}, {new});
END
""")


def upgrade() -> None:
    # Triggers down before any DML, and back up no matter how it ends. The
    # backfill UPDATEs are one transaction; a row-level failure must roll it
    # back *before* the triggers are recreated — recreated inside it, they
    # would roll back with it (see b7e2d4f81a05 for the full reasoning).
    _drop_triggers()
    try:
        bind = op.get_bind()
        rows = bind.execute(
            sa.text(
                "SELECT id, reps, time, completed_at FROM workouts "
                "WHERE time IS NOT NULL AND work_seconds IS NULL"
            )
        ).fetchall()
        for row_id, reps, time_value, completed_at in rows:
            seconds = _parse_seconds(time_value)
            if seconds is None:
                continue
            sets: dict[str, object] = {"work_seconds": seconds}
            # A completed row's duration was also its performed work — the
            # same claim b7e2 made for the rows it could read, as a TOTAL:
            # `seconds * (reps or 1)`, matching `_derive_actuals`.
            if completed_at is not None:
                sets["actual_work_seconds"] = seconds * (reps or 1)
            assignments = ", ".join(f"{name} = :{name}" for name in sets)
            bind.execute(
                sa.text(f"UPDATE workouts SET {assignments} WHERE id = :id"),
                {**sets, "id": row_id},
            )
    except Exception:
        op.get_bind().rollback()
        raise
    finally:
        _create_triggers()


def downgrade() -> None:
    # Deliberately a no-op: parsed durations are data now, and un-parsing
    # them would be a history edit, not a rollback.
    pass
