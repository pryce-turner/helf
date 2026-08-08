"""restrict body comp views to real measurements

Revision ID: 70709fd96184
Revises: 61ccf127e583
Create Date: 2026-08-08 14:31:52.117409

`v_body_comp_measurements` emits a row for *any* observation carrying *any*
metric, because when it was written every observation was a weigh-in. That is
no longer true, and it is about to be much less true: `metric_def` now defines
`mood`, `sleep_hours`, `alcohol_units` and eleven DEXA quantities.

An observation with no body weight surfaces as a measurement whose `weight` is
NULL, and `BodyComposition.weight` is a required `float`:

    doc_id 151 | source derived | weight (null)
    ValidationError: weight - Input should be a valid number, input_value=None

`GET /api/body-composition/` returns 500 - not for the offending row, for the
whole list. Logging a mood through the MCP write tool is enough to do it.

A body-composition measurement is one that has a body weight. Both views now
say so, which is also exactly the condition the response model requires.

`v_body_comp_series` additionally gains the three DEXA masses. Plan 0003 §4a
specified `lean_mass_kg` and `ffm_kg` for this view and they were never added,
since nothing produced them; `fat_mass_kg` joins them as the third term of the
decomposition BodySpec reports.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '70709fd96184'
down_revision: str | Sequence[str] | None = '61ccf127e583'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept identical to 7bba3fe3ee35's, which these definitions replace. Only the
# HAVING clause and the series membership differ.
PIVOT_COLUMNS = [
    ("body_weight_lb", "weight"),
    ("body_fat_pct", "body_fat_pct"),
    ("muscle_pct", "muscle_mass"),
    ("bmi", "bmi"),
    ("water_pct", "water_pct"),
    ("bone_mass_lb", "bone_mass"),
    ("visceral_fat", "visceral_fat"),
    ("metabolic_age", "metabolic_age"),
    ("protein_pct", "protein_pct"),
]

# What makes an observation a body-composition measurement. Expressed against
# the aggregate rather than as a WHERE, so an observation that carries a weight
# *and* other quantities keeps all of them.
HAS_A_BODY_WEIGHT = (
    "HAVING MAX(CASE WHEN m.name = 'body_weight_lb' THEN m.value END) IS NOT NULL"
)

SERIES_METRICS = (
    "'body_weight_lb', 'body_fat_pct', 'muscle_pct', 'water_pct', "
    "'fat_mass_kg', 'lean_mass_kg', 'ffm_kg'"
)


def _pivot(agg: str) -> str:
    return ",\n".join(
        f"    {agg}(CASE WHEN m.name = '{metric}' THEN m.value END) AS {alias}"
        for metric, alias in PIVOT_COLUMNS
    )


def _measurements(having: str) -> str:
    return f"""
CREATE VIEW v_body_comp_measurements AS
SELECT
    o.id          AS doc_id,
    o.observed_at,
    o.date,
    o.source,
    o.created_at,
    -- Not stored: the unit is encoded in the metric NAME (`body_weight_lb`),
    -- and pounds are canonical for body mass (ADR-0003). Emitted as a literal
    -- so the view is shape-compatible with the existing response model.
    'lbs'         AS weight_unit,
{_pivot("MAX")}
FROM observation o
JOIN metric m ON m.observation_id = o.id
GROUP BY o.id
{having}
"""


def _daily(having: str) -> str:
    return f"""
CREATE VIEW v_body_comp_daily AS
SELECT
    o.date,
    o.source,
{_pivot("AVG")},
    COUNT(DISTINCT o.observed_at) AS n_measurements
FROM observation o
JOIN metric m ON m.observation_id = o.id
GROUP BY o.date, o.source
{having}
"""


def _series(metrics: str) -> str:
    return f"""
CREATE VIEW v_body_comp_series AS
SELECT o.date, o.source, m.name, m.value, m.unit
FROM metric m
JOIN observation o ON o.id = m.observation_id
WHERE m.name IN ({metrics})
"""


REBUILT = ["v_body_comp_measurements", "v_body_comp_daily", "v_body_comp_series"]

PREVIOUS_SERIES_METRICS = (
    "'body_weight_lb', 'body_fat_pct', 'muscle_pct', 'water_pct'"
)


def _replace(measurements_having: str, daily_having: str, series: str) -> None:
    for name in REBUILT:
        op.execute(f"DROP VIEW IF EXISTS {name}")
    op.execute(_measurements(measurements_having))
    op.execute(_daily(daily_having))
    op.execute(_series(series))


def upgrade() -> None:
    conn = op.get_bind()

    # The premise: today every observation is a weigh-in, so the new HAVING
    # must not change a single row. If it does, something is already being
    # recorded that these views were silently reporting as a measurement, and
    # narrowing them would hide it rather than fix it.
    before = conn.execute(
        sa.text("SELECT count(*) FROM v_body_comp_measurements")
    ).scalar_one()
    weightless = conn.execute(
        sa.text(
            "SELECT o.id, o.observed_at, o.source FROM observation o "
            "JOIN metric m ON m.observation_id = o.id "
            "GROUP BY o.id "
            "HAVING MAX(CASE WHEN m.name = 'body_weight_lb' THEN m.value END) "
            "IS NULL"
        )
    ).all()
    if weightless:
        raise RuntimeError(
            f"{len(weightless)} observation(s) carry metrics but no "
            f"`body_weight_lb`, e.g. {[tuple(r) for r in weightless[:5]]!r}. "
            f"They are being served as body-composition measurements today "
            f"with a NULL weight. Decide what they are before narrowing the "
            f"view - this migration assumes there are none."
        )

    _replace(HAS_A_BODY_WEIGHT, HAS_A_BODY_WEIGHT, SERIES_METRICS)

    after = conn.execute(
        sa.text("SELECT count(*) FROM v_body_comp_measurements")
    ).scalar_one()
    if before != after:
        raise RuntimeError(
            f"v_body_comp_measurements returned {before} rows before and "
            f"{after} after. The HAVING clause was supposed to be a no-op "
            f"against existing data."
        )


def downgrade() -> None:
    _replace("", "", PREVIOUS_SERIES_METRICS)
