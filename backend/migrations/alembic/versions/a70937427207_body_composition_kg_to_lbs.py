"""body composition kg to lbs

Revision ID: a70937427207
Revises: fd709c41eb19
Create Date: 2026-08-08 08:40:20.417132

Pounds are canonical for body mass (ADR-0003). openScale reports kilograms, and
`mqtt_service.py` stored them verbatim under a hard-coded `weight_unit='kg'`,
leaving the frontend to convert on every render.

**Only `weight` converts.** `muscle_mass` and `body_fat_pct` are percentages,
not masses - converting them is the exact bug this migration must avoid. The
remaining six columns (`bmi`, `water_pct`, `bone_mass`, `visceral_fat`,
`metabolic_age`, `protein_pct`) are NULL in all 150 rows, so there is nothing to
convert even where the name implies a mass.

`muscle_mass` being a percentage is established, not assumed: it correlates with
body weight at r = -0.985 across 150 rows. A mass correlates positively with
weight; a near-perfect inverse is the signature of a fraction. See
docs/plans/0003-units-and-metrics.md §2.

This revision must ship together with the frontend change that removes
`kgToLbs`. Converting stored values while the client still multiplies would
double every displayed weight.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a70937427207'
down_revision: str | Sequence[str] | None = 'fd709c41eb19'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 1 kg in pounds, exact to the definition of the international pound.
KG_TO_LB = 2.20462262184878


def upgrade() -> None:
    """Convert kilogram weights to pounds."""
    conn = op.get_bind()

    # Guarded by weight_unit so a re-run is a no-op even if revision tracking
    # were bypassed. Rows already in lbs are left alone.
    result = conn.execute(
        sa.text(
            "UPDATE body_composition "
            "SET weight = weight * :factor, weight_unit = 'lbs' "
            "WHERE weight_unit = 'kg'"
        ),
        {"factor": KG_TO_LB},
    )
    print(f"  converted {result.rowcount} body_composition row(s) from kg to lbs")

    _assert_plausible(conn)


def downgrade() -> None:
    """Convert pounds back to kilograms."""
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE body_composition "
            "SET weight = weight / :factor, weight_unit = 'kg' "
            "WHERE weight_unit = 'lbs'"
        ),
        {"factor": KG_TO_LB},
    )


def _assert_plausible(conn) -> None:
    """Fail loudly if the result is not a human body weight in pounds.

    A double-applied conversion is the failure mode worth catching: it leaves
    values that are still numeric, still positive, and still sorted the same
    way, so nothing downstream complains. 88 kg doubled twice reads as 429 lb.
    """
    row = conn.execute(
        sa.text(
            "SELECT min(weight), max(weight) FROM body_composition "
            "WHERE weight IS NOT NULL AND weight_unit = 'lbs'"
        )
    ).one_or_none()
    if row is None or row[0] is None:
        return

    low, high = row
    if not (50 < low and high < 700):
        raise RuntimeError(
            f"body_composition weights are {low:.1f}-{high:.1f} lbs after "
            f"conversion, which is not a plausible human range. Refusing to "
            f"commit - the data may already have been in pounds."
        )
