"""drop redundant weight_unit columns

Revision ID: e96bd4b90873
Revises: 7bba3fe3ee35
Create Date: 2026-08-08 11:47:34.076668

Pounds are canonical for all mass (ADR-0003), so a per-row unit label records
the same string 9,472 times and invites the belief that some other value is
possible. The unit is a property of the schema; the API still reports it, from
`app.utils.units.CANONICAL_WEIGHT_UNIT`.

Every row in all three tables is already 'lbs' - `a1` converted the only
kilogram data there was.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e96bd4b90873'
down_revision: str | Sequence[str] | None = '7bba3fe3ee35'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("body_composition", "upcoming_workouts", "workouts")
CANONICAL = "lbs"


def upgrade() -> None:
    """Drop the column, but only if it says what we think it says."""
    conn = op.get_bind()

    # Dropping a column is irreversible in the sense that matters: the values
    # are gone. If anything is not 'lbs' then either a1 missed it or a new
    # writer has appeared, and in both cases dropping silently discards the only
    # evidence of it.
    for table in TABLES:
        offenders = conn.execute(
            sa.text(
                f"SELECT DISTINCT weight_unit FROM {table} "  # noqa: S608
                "WHERE weight_unit IS NOT :canonical"
            ),
            {"canonical": CANONICAL},
        ).scalars().all()
        if offenders:
            raise RuntimeError(
                f"{table}.weight_unit contains {offenders!r}, not just "
                f"'{CANONICAL}'. Convert those rows before dropping the column - "
                f"once it is gone there is no record of what unit they were in."
            )

    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("weight_unit")


def downgrade() -> None:
    """Restore the column, populated with the canonical unit.

    `server_default` is required, not cosmetic: the column is NOT NULL and the
    tables have rows, so a batch rebuild without a default fails outright.
    """
    for table, length in (
        ("workouts", 16),
        ("upcoming_workouts", 16),
        ("body_composition", 8),
    ):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "weight_unit",
                    sa.VARCHAR(length=length),
                    nullable=False,
                    server_default=CANONICAL,
                )
            )
