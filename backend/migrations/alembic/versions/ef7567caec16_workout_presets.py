"""workout presets

Revision ID: ef7567caec16
Revises: 9c4e7b21f806
Create Date: 2026-11-22 01:00:00

Plan 0020. A preset is a hand-built workout — tiles made on the day editor,
kept under a name, and applied to a date as planned sets.

**Two new tables, nothing else touched.** `workout_preset` holds the name;
`workout_preset_item` holds one row per tile with exactly the *target*
columns a planned `workouts` row carries, so the day editor renders both
with one card and applying a preset is a field-for-field copy.

Not `upcoming_workouts` with a preset key: that table is the queue, which the
Liftoscript generator clears wholesale (9c4e7b21f806), and a preset must
survive that. Not `workouts` with a sentinel date: those rows are history,
audited and counted.

Like a stack (9ffbe9c21a0f §2), applying writes ordinary rows and nothing
points back, so editing a preset cannot rewrite a past day. Unlike a stack it
is not audited — a plan that has not been run is not history, matching
`upcoming_workouts` and `mobility_plan`.

Additive: the running app never reads these tables until the code that does
is deployed, so the revision is safe to apply ahead of it.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ef7567caec16'
down_revision: str | Sequence[str] | None = '9c4e7b21f806'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workout_preset",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("trim(name) <> ''", name="ck_workout_preset_name"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "workout_preset_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("preset_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("distance", sa.Float(), nullable=True),
        sa.Column("distance_unit", sa.String(length=16), nullable=True),
        sa.Column("work_seconds", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("rest_after_seconds", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_mobility", sa.Boolean(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "is_mobility IN (0, 1)", name="ck_workout_preset_item_is_mobility"
        ),
        sa.CheckConstraint(
            "work_seconds IS NULL OR work_seconds BETWEEN 1 AND 3600",
            name="ck_workout_preset_item_work_seconds",
        ),
        sa.CheckConstraint(
            "rest_seconds IS NULL OR rest_seconds BETWEEN 0 AND 3600",
            name="ck_workout_preset_item_rest_seconds",
        ),
        sa.CheckConstraint(
            "rest_after_seconds IS NULL OR rest_after_seconds BETWEEN 0 AND 3600",
            name="ck_workout_preset_item_rest_after_seconds",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"]),
        sa.ForeignKeyConstraint(["preset_id"], ["workout_preset.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workout_preset_item_preset_order",
        "workout_preset_item",
        ["preset_id", "order"],
    )
    op.create_index(
        op.f("ix_workout_preset_item_exercise_id"), "workout_preset_item", ["exercise_id"]
    )
    op.create_index(
        op.f("ix_workout_preset_item_category_id"), "workout_preset_item", ["category_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workout_preset_item_category_id"), table_name="workout_preset_item")
    op.drop_index(op.f("ix_workout_preset_item_exercise_id"), table_name="workout_preset_item")
    op.drop_index("ix_workout_preset_item_preset_order", table_name="workout_preset_item")
    op.drop_table("workout_preset_item")
    op.drop_table("workout_preset")
