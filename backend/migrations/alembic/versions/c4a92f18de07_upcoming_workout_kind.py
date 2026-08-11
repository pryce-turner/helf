"""upcoming workout kind: lifting or mobility

Revision ID: c4a92f18de07
Revises: b3d1c07a4e21
Create Date: 2026-08-10 21:10:00.000000

A second kind of planned session lands in the table that already models planned
sessions, rather than in a parallel pair of tables of its own (Plan 0012 §2).

The two are the same shape — an ordered list of prescribed sets waiting to be
copied onto a date — and they differ only in who writes them and what the page
around them looks like. A `mobility_session`/`mobility_item` pair would have
duplicated the exercise/category resolution, the transfer-to-a-date path and
the serialiser, to gain columns that `comment` already carries as prose.

**The default is `'lifting'`, and that is the load-bearing part.** Thirty rows
already exist and every one of them is a lifting row; a NULLable column or a
default of anything else would have made "which kind is this?" a question the
existing data could not answer. The CHECK is duplicated from the Pydantic
`Literal` on purpose — the agent writes raw SQL over MCP and never passes
through Pydantic (ADR-0002), so the constraint is the only rule both writers
obey.

No index. The table holds tens of rows and is read whole; an index on `kind`
would be two values over thirty rows, which SQLite would decline to use anyway.

`upcoming_workouts` is not an audited table (0007 §"AUDITED" covers `metric`,
`food`, `food_log`, `note`, `workouts`, `exercises`, `stack`, `stack_item`), so
unlike `b3d1c07a4e21` there are no triggers here to rebuild. Planned work is
not history — it is rewritten wholesale every time a program is generated, and
logging it into `workouts` is the moment it becomes something worth auditing.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4a92f18de07"
down_revision: str | Sequence[str] | None = "b3d1c07a4e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN rather than a batch rebuild: recreating the table would
    # drop and restore two foreign keys and three indexes to add one column.
    op.execute(
        "ALTER TABLE upcoming_workouts ADD COLUMN kind TEXT NOT NULL "
        "DEFAULT 'lifting' CHECK (kind IN ('lifting', 'mobility'))"
    )


def downgrade() -> None:
    # Mobility rows are *planned* work, so dropping the column loses a
    # prescription that has not happened yet rather than a record of one that
    # has. They are deleted instead of being silently relabelled as lifting,
    # which would put mobility work into the lifting planner on the next load.
    op.execute("DELETE FROM upcoming_workouts WHERE kind = 'mobility'")

    with op.batch_alter_table("upcoming_workouts") as batch:
        batch.drop_column("kind")
