"""mobility plans are a set, not a single rolling routine

Revision ID: b6f31a90c4de
Revises: e2b9c4d17a05
Create Date: 2026-08-20 10:00:00.000000

Plan 0012 §2 said "one rolling routine, not a queue", and that was right while
the routine was one thing. It is not: rehabbing a low back and a shoulder at
once means two prescriptions alive at the same time, adjusted on different
schedules, and a single pending session forces them into one list or makes
writing either one destroy the other.

**The items need no schema.** `upcoming_workouts.session` already distinguishes
sessions — the lifting planner is using 7 through 12 right now — and mobility
simply pinned itself to a constant 1. Several mobility sessions are several
values of a column that has always been there.

What was missing is per-session metadata. There was exactly one rationale, held
in a `note` of kind `mobility_plan`, and no name at all: two pending sessions
would have been indistinguishable on the page and unaddressable by the agent.
So `mobility_plan` becomes a table, one row per pending session:

- `label` is the **addressing key**. The agent writes "Low back" or "Shoulder";
  an existing label replaces that session and leaves the others alone. Unique,
  because a key that can repeat is not a key.
- `rationale` stays required. A session with no reasoning is a list.
- `session` maps to `upcoming_workouts.session` for `kind = 'mobility'`.

**Not audited**, deliberately, matching `upcoming_workouts`: 0007's AUDITED set
covers history, and a plan that has not been run yet is not history. Discarding
a session the user never ran is not a mutation worth keeping forever.

The single existing plan note is carried across as label 'Mobility', which is
what it was — the one rolling routine, now one of several. The `mobility_plan`
*note kind* is retired with it; `mobility_session` notes are untouched, since
those record sessions that actually happened.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6f31a90c4de"
down_revision: str | Sequence[str] | None = "e2b9c4d17a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mobility_plan",
        sa.Column("session", sa.Integer(), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False, unique=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("trim(label) <> ''", name="ck_mobility_plan_label"),
        sa.CheckConstraint(
            "trim(rationale) <> ''", name="ck_mobility_plan_rationale"
        ),
    )

    # Carry the one pending plan across. Its session number is whatever its
    # rows already use, so the items keep pointing at it without being touched.
    op.execute("""
        INSERT INTO mobility_plan (session, label, rationale, created_at)
        SELECT
            COALESCE(
                (SELECT MIN(session) FROM upcoming_workouts WHERE kind = 'mobility'),
                1
            ),
            'Mobility',
            n.body,
            n.noted_at
        FROM note n
        WHERE n.kind = 'mobility_plan'
          AND TRIM(COALESCE(n.body, '')) <> ''
        ORDER BY n.noted_at DESC
        LIMIT 1
    """)
    op.execute("DELETE FROM note WHERE kind = 'mobility_plan'")


def downgrade() -> None:
    # Back to one rolling routine: the oldest plan becomes the note, and any
    # others are dropped along with their items. Lossy on purpose — the single
    # note has nowhere to put a second prescription, and leaving orphaned
    # `upcoming_workouts` rows behind would be worse than losing them, because
    # they would silently join whichever session survived.
    op.execute("""
        INSERT INTO note (noted_at, kind, body, source)
        SELECT created_at, 'mobility_plan', rationale, 'agent'
        FROM mobility_plan
        ORDER BY session
        LIMIT 1
    """)
    op.execute("""
        DELETE FROM upcoming_workouts
        WHERE kind = 'mobility'
          AND session <> COALESCE((SELECT MIN(session) FROM mobility_plan), session)
    """)
    op.drop_table("mobility_plan")
