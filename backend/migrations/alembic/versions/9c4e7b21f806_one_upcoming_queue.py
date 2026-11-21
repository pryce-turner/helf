"""one upcoming queue: mobility is a property of the planned set

Revision ID: 9c4e7b21f806
Revises: c4a1e8b93d07
Create Date: 2026-11-21 12:00:00.000000

Retires the `kind` split c4a92f18de07 added. That revision put two programs in
one table — Liftoscript-generated lifting sessions and agent-written mobility
sessions — and the price was that every query had to name its kind, because a
missing filter did not error, it mixed the two (Plan 0012 §2).

The split is gone because the distinction it encoded no longer exists: planned
work is one queue, and whether a prescribed set is mobility work is a property
of the set, exactly as `workouts.is_mobility` already records it for logged
work (d7e4f2a91b83). `upcoming_workouts.is_mobility` is that flag on the
planned row; transfer carries it onto the logged set, where the day-view
checkbox can still adjust it.

Three data moves, in order:

1. `is_mobility` is added and backfilled from `kind` before `kind` drops, so
   the fourteen prescribed mobility sets survive the column going.
2. **Mobility sessions are renumbered above the lifting max.** The two kinds
   numbered their sessions independently (mobility started at 1, lifting at
   whatever the generator produced), which was safe only because every query
   named its kind. In one namespace a session number must pick out one
   session — transfer and delete are keyed by it — so the mobility sessions
   slide up past the lifting max, and `mobility_plan.session` follows them.
3. `kind` is dropped. The CHECK dies with the column; there is nothing left
   to constrain.

No triggers to rebuild: `upcoming_workouts` is not an audited table (planned
work is rewritten wholesale; it becomes history at transfer). The named
constraint on the ADD COLUMN is deliberate — an anonymous CHECK added this way
is invisible to `alembic check` forever (see docs/plans/README.md).

Round-trip note: the downgrade restores `kind` but does not renumber mobility
sessions back down, so a downgrade followed by an upgrade slides them up a
second time (13 becomes 25 on the production data). Session numbers are
identifiers, not ordinals, and plan and rows move together — the invariant
that matters holds. Do not "fix" the drift by renumbering in the downgrade:
mapping old numbers to new across `mobility_plan` and `upcoming_workouts` is a
temp table of machinery to protect a number that means nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c4e7b21f806"
down_revision: str | Sequence[str] | None = "c4a1e8b93d07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE upcoming_workouts ADD COLUMN is_mobility BOOLEAN NOT NULL "
        "DEFAULT 0 CONSTRAINT ck_upcoming_is_mobility CHECK (is_mobility IN (0, 1))"
    )
    op.execute(
        "UPDATE upcoming_workouts SET is_mobility = 1 WHERE kind = 'mobility'"
    )

    # Merge the two session-number namespaces before dropping the column that
    # separated them. Mobility plans only ever name mobility sessions, so the
    # same offset applies to both tables. With no lifting rows the offset is 0
    # and both UPDATEs are no-ops.
    offset = op.get_bind().execute(
        sa.text(
            "SELECT COALESCE(MAX(session), 0) FROM upcoming_workouts "
            "WHERE kind = 'lifting'"
        )
    ).scalar()
    if offset:
        op.execute(
            f"UPDATE upcoming_workouts SET session = session + {offset} "
            "WHERE kind = 'mobility'"
        )
        op.execute(f"UPDATE mobility_plan SET session = session + {offset}")

    # Plain DROP COLUMN (SQLite 3.35+): no trigger names the column, and the
    # named CHECK is part of its definition, so both go together.
    op.execute("ALTER TABLE upcoming_workouts DROP COLUMN kind")


def downgrade() -> None:
    # The flag maps back onto the old discriminator: flagged rows become
    # mobility. A mixed session — some sets flagged, some not — cannot be one
    # kind, so downgrading one splits it across the two old pages. That shape
    # only exists if the new per-set flag was actually mixed, which the
    # pre-upgrade data never was.
    op.execute(
        "ALTER TABLE upcoming_workouts ADD COLUMN kind TEXT NOT NULL "
        "DEFAULT 'lifting' CONSTRAINT ck_upcoming_kind "
        "CHECK (kind IN ('lifting', 'mobility'))"
    )
    op.execute(
        "UPDATE upcoming_workouts SET kind = 'mobility' WHERE is_mobility = 1"
    )
    op.execute("ALTER TABLE upcoming_workouts DROP COLUMN is_mobility")
