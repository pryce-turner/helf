"""backfill metric from body_composition

Revision ID: de63ed0bc62d
Revises: 4de188592eb5
Create Date: 2026-08-08 09:00:00.000000

Copies the four populated body_composition columns into tall `metric` rows.

`body_composition` is NOT dropped and NOT stopped being written. Both paths stay
live until the view-backed path is verified against real numbers - losing scale
data to a migration bug is unrecoverable, because openScale does not
retransmit.

Every row is tagged source='openscale', which is what makes this reversible:
`DELETE FROM metric WHERE source = 'openscale'`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'de63ed0bc62d'
down_revision: str | Sequence[str] | None = '4de188592eb5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE = "openscale"

# (metric name, source column, unit)
#
# Only these four. The other five body_composition columns (bmi, bone_mass,
# visceral_fat, metabolic_age, protein_pct) are NULL in every row, so they
# produce no metrics and get no definitions until a source actually emits them.
#
# Note the third pair: the column is named muscle_mass but holds a PERCENTAGE
# (r = -0.985 against body weight, the signature of a fraction). The rename to
# muscle_pct happens here, and this is the only place the misnomer needs
# handling.
COLUMNS = [
    ("body_weight_lb", "weight", "lb"),
    ("body_fat_pct", "body_fat_pct", "%"),
    ("muscle_pct", "muscle_mass", "%"),
    ("water_pct", "water_pct", "%"),
]


def upgrade() -> None:
    """Copy body_composition into metric."""
    conn = op.get_bind()

    total = 0
    for metric_name, column, unit in COLUMNS:
        result = conn.execute(
            sa.text(
                "INSERT INTO metric (observed_at, name, value, unit, source) "
                f"SELECT timestamp, :name, {column}, :unit, :source "  # noqa: S608
                f"FROM body_composition WHERE {column} IS NOT NULL"  # noqa: S608
            ),
            {"name": metric_name, "unit": unit, "source": SOURCE},
        )
        print(f"  {metric_name}: {result.rowcount} rows")
        total += result.rowcount

    _verify(conn, total)


def downgrade() -> None:
    """Remove everything this revision inserted."""
    op.get_bind().execute(
        sa.text("DELETE FROM metric WHERE source = :source"), {"source": SOURCE}
    )


def _verify(conn, inserted: int) -> None:
    """Assert the backfill copied every source row and lost no values.

    A silent partial copy is the failure worth catching: the app keeps reading
    the old wide table, so nothing looks wrong until it is switched over.
    """
    for metric_name, column, _unit in COLUMNS:
        expected = conn.execute(
            sa.text(f"SELECT count({column}) FROM body_composition")  # noqa: S608
        ).scalar()
        got = conn.execute(
            sa.text("SELECT count(*) FROM metric WHERE name = :n AND source = :s"),
            {"n": metric_name, "s": SOURCE},
        ).scalar()
        if expected != got:
            raise RuntimeError(
                f"{metric_name}: expected {expected} rows from "
                f"body_composition.{column}, inserted {got}"
            )

        # Sums must agree to floating-point tolerance, which catches a column
        # being copied into the wrong metric name - a row-count check alone
        # would not, since all four columns have identical counts.
        src_sum = conn.execute(
            sa.text(f"SELECT coalesce(sum({column}), 0) FROM body_composition")  # noqa: S608
        ).scalar()
        dst_sum = conn.execute(
            sa.text(
                "SELECT coalesce(sum(value), 0) FROM metric "
                "WHERE name = :n AND source = :s"
            ),
            {"n": metric_name, "s": SOURCE},
        ).scalar()
        if abs(float(src_sum) - float(dst_sum)) > 1e-6:
            raise RuntimeError(
                f"{metric_name}: sum mismatch - source {src_sum}, metric {dst_sum}"
            )

    print(f"  verified {inserted} metric rows against body_composition")
