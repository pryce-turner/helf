"""workout programs: programs of yours, kept as script

Revision ID: 47920bce115b
Revises: 842c1976c18a
Create Date: 2026-11-22 05:00:00

Plan 0022. The library unifies blocks and programs as script: built-in ones
are files in the repo, yours live in the database. Your blocks already had a
home (`workout_preset`, ef7567caec16); your programs had none - the program
editor kept only the last generated script, as a `document`. This is that home:
a name, the script, and the program builder's model when the builder wrote it.

One table, nothing else touched. Not audited, like the queue and the presets:
a plan is not history.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '47920bce115b'
down_revision: str | Sequence[str] | None = '842c1976c18a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workout_program",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("builder", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("trim(name) <> ''", name="ck_workout_program_name"),
        sa.CheckConstraint(
            "builder IS NULL OR json_valid(builder)", name="ck_workout_program_builder"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("workout_program")
