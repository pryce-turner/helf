"""upcoming set timing: work, rest and rest-after on the queue

Revision ID: 842c1976c18a
Revises: ef7567caec16
Create Date: 2026-11-22 03:00:00

Plan 0021. Liftoscript learns timing and distance (`3x6 10s rest 5s after
30s`, `1x1 400m`), and the queue needs somewhere to hold it until the session
is transferred onto a day. Distance already had columns; the timing did not —
`upcoming_workouts` predates plan 0018's set tiles and kept only the legacy
free-form `time`, which transfer could turn into work seconds but which has
no room for the two rests.

So the three target columns `workouts` gained in b7e2d4f81a05 land here with
the same names and the same named CHECKs, and transfer copies them field for
field. The legacy `time` stays read-only, as it is on `workouts`: transfer
still promotes it when `work_seconds` is empty, so older rows lose nothing.

Plain `ADD COLUMN`s, survivable on a re-run (b7e2d4f81a05's reasoning: SQLite
DDL is not transactional here). Not audited, like the rest of the queue.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '842c1976c18a'
down_revision: str | Sequence[str] | None = 'ef7567caec16'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_COLUMNS = [
    ("work_seconds", "INTEGER CONSTRAINT ck_upcoming_work_seconds "
     "CHECK (work_seconds IS NULL OR work_seconds BETWEEN 1 AND 3600)"),
    ("rest_seconds", "INTEGER CONSTRAINT ck_upcoming_rest_seconds "
     "CHECK (rest_seconds IS NULL OR rest_seconds BETWEEN 0 AND 3600)"),
    ("rest_after_seconds", "INTEGER CONSTRAINT ck_upcoming_rest_after_seconds "
     "CHECK (rest_after_seconds IS NULL OR rest_after_seconds BETWEEN 0 AND 3600)"),
]


def upgrade() -> None:
    existing = {
        row[1]
        for row in op.get_bind().execute(
            sa.text("PRAGMA table_info(upcoming_workouts)")
        ).fetchall()
    }
    for name, ddl in NEW_COLUMNS:
        if name not in existing:
            op.execute(f"ALTER TABLE upcoming_workouts ADD COLUMN {name} {ddl}")


def downgrade() -> None:
    # Plain DROP COLUMN, not a batch rebuild: each CHECK is a column
    # constraint on the column being dropped, which SQLite allows. A batch
    # copy would re-create the table with every column CHECK hoisted to table
    # level — including ck_upcoming_is_mobility — and 9c4e7b21f806's own
    # downgrade could then no longer drop `is_mobility`.
    existing = {
        row[1]
        for row in op.get_bind().execute(
            sa.text("PRAGMA table_info(upcoming_workouts)")
        ).fetchall()
    }
    for name, _ in reversed(NEW_COLUMNS):
        if name in existing:
            op.execute(f"ALTER TABLE upcoming_workouts DROP COLUMN {name}")
