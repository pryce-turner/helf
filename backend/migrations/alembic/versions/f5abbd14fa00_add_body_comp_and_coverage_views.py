"""add body comp and coverage views

Revision ID: f5abbd14fa00
Revises: de63ed0bc62d
Create Date: 2026-08-08 09:01:00.000000

Two views over the tall `metric` table:

- `v_body_comp_daily` pivots it back into the wide shape the existing repository
  already returns, so the API contract does not change.
- `v_metric_coverage` publishes what is actually recorded, so a definition with
  no rows behind it reads as "never recorded" rather than as a flat series.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5abbd14fa00'
down_revision: str | Sequence[str] | None = 'de63ed0bc62d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Column aliases are deliberate: `body_weight_lb` -> `weight`, `muscle_pct` ->
# `muscle_mass`. They reproduce BodyCompositionRepository._serialize exactly, so
# nothing in Python changes when the read path is switched over.
#
# `muscle_mass` is fed from `muscle_pct`, NOT from a mass. The legacy column
# holds a percentage; the view preserves the legacy *name* while the metric
# carries the honest one. An earlier draft of the plan mapped it from
# `muscle_mass_lb`, a metric nothing seeds - the column would have been silently
# NULL for every row.
#
# `bmi`, `bone_mass`, `visceral_fat`, `metabolic_age` and `protein_pct` resolve
# to NULL today because no source emits them. They are listed anyway so the view
# is shape-compatible the moment one does (BodySpec, Plan 0008).
#
# GROUPING INCLUDES `source`. Without it, the aggregate would merge a
# bioimpedance estimate and a DEXA measurement of the same quantity on the same
# day into one value. Callers must filter to a single source.
#
# AVG, not MAX. This is a per-DAY view over per-MEASUREMENT data, and the
# existing history weighs in more than once on 30 days - 13 of them with
# genuinely different readings, spanning up to 4.06 lb. MAX would report the
# heaviest reading of each of those days, biasing every daily summary upward.
# Repeated readings from one instrument within one day are repeated measures of
# the same quantity, so averaging them is sound; averaging ACROSS sources is not,
# which is what the source grouping prevents.
#
# Use v_body_comp_measurements below where individual weigh-ins matter.
V_BODY_COMP_DAILY = """
CREATE VIEW v_body_comp_daily AS
SELECT
    date,
    source,
    AVG(CASE WHEN name = 'body_weight_lb' THEN value END) AS weight,
    AVG(CASE WHEN name = 'body_fat_pct'   THEN value END) AS body_fat_pct,
    AVG(CASE WHEN name = 'muscle_pct'     THEN value END) AS muscle_mass,
    AVG(CASE WHEN name = 'bmi'            THEN value END) AS bmi,
    AVG(CASE WHEN name = 'water_pct'      THEN value END) AS water_pct,
    AVG(CASE WHEN name = 'bone_mass_lb'   THEN value END) AS bone_mass,
    AVG(CASE WHEN name = 'visceral_fat'   THEN value END) AS visceral_fat,
    AVG(CASE WHEN name = 'metabolic_age'  THEN value END) AS metabolic_age,
    AVG(CASE WHEN name = 'protein_pct'    THEN value END) AS protein_pct,
    COUNT(DISTINCT observed_at)                           AS n_measurements
FROM metric
GROUP BY date, source
"""

# Full grain: one row per weigh-in, not per day. `body_composition` is
# per-measurement (its `timestamp` is unique), so this is the view that
# reproduces it exactly - 150 rows, not 107. Detail and list endpoints read this;
# only summaries read the daily view.
V_BODY_COMP_MEASUREMENTS = """
CREATE VIEW v_body_comp_measurements AS
SELECT
    observed_at,
    date,
    source,
    MAX(CASE WHEN name = 'body_weight_lb' THEN value END) AS weight,
    MAX(CASE WHEN name = 'body_fat_pct'   THEN value END) AS body_fat_pct,
    MAX(CASE WHEN name = 'muscle_pct'     THEN value END) AS muscle_mass,
    MAX(CASE WHEN name = 'bmi'            THEN value END) AS bmi,
    MAX(CASE WHEN name = 'water_pct'      THEN value END) AS water_pct,
    MAX(CASE WHEN name = 'bone_mass_lb'   THEN value END) AS bone_mass,
    MAX(CASE WHEN name = 'visceral_fat'   THEN value END) AS visceral_fat,
    MAX(CASE WHEN name = 'metabolic_age'  THEN value END) AS metabolic_age,
    MAX(CASE WHEN name = 'protein_pct'    THEN value END) AS protein_pct
FROM metric
GROUP BY observed_at, source
"""

# n_rows = 0 distinguishes "defined, never recorded" from "recorded and
# unchanged" - the difference between an agent reporting "no data" and it
# reporting "no change". Self-maintaining: no flag to keep in sync as metrics
# start and stop being collected.
V_METRIC_COVERAGE = """
CREATE VIEW v_metric_coverage AS
SELECT d.name,
       d.canonical_unit,
       d.description,
       count(m.id)  AS n_rows,
       count(DISTINCT m.source) AS n_sources,
       min(m.date)  AS first_seen,
       max(m.date)  AS last_seen
FROM metric_def d
LEFT JOIN metric m ON m.name = d.name
GROUP BY d.name, d.canonical_unit, d.description
"""

# Both series for a dual-sourced quantity, already split by source so no
# consumer has to group - and so nothing accidentally averages across
# instruments of different accuracy.
V_BODY_COMP_SERIES = """
CREATE VIEW v_body_comp_series AS
SELECT date, source, name, value, unit
FROM metric
WHERE name IN ('body_weight_lb', 'body_fat_pct', 'muscle_pct', 'water_pct')
"""

VIEWS = {
    "v_body_comp_measurements": V_BODY_COMP_MEASUREMENTS,
    "v_body_comp_daily": V_BODY_COMP_DAILY,
    "v_metric_coverage": V_METRIC_COVERAGE,
    "v_body_comp_series": V_BODY_COMP_SERIES,
}


def upgrade() -> None:
    for ddl in VIEWS.values():
        op.execute(ddl)


def downgrade() -> None:
    for name in VIEWS:
        op.execute(f"DROP VIEW IF EXISTS {name}")
