"""extract observation from metric

Revision ID: 7bba3fe3ee35
Revises: f5abbd14fa00
Create Date: 2026-08-08 09:30:00.000000

Gives the tall model a concept of a *measurement*.

`metric` alone could not support the read path: a body-composition measurement
is four metric rows, so there was no row to take `doc_id` from, nowhere to put
`created_at`, and nothing for `DELETE /{id}` to name. `observation` holds the
identity, the instant, the instrument and the ingestion time; `metric` becomes
purely name-and-value.

`observed_at`, `source` and the generated `date` move from `metric` to
`observation`. UNIQUE(observation_id, name) replaces UNIQUE(observed_at, name,
source) and is equivalent, since `observation` is itself unique on
(observed_at, source).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7bba3fe3ee35'
down_revision: str | Sequence[str] | None = 'f5abbd14fa00'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Recreated at the end of both directions, since they reference the columns
# being moved. Kept in sync with f5abbd14fa00 by construction: that revision
# creates them, this one replaces them, and only the joins differ.
VIEW_NAMES = [
    "v_body_comp_measurements",
    "v_body_comp_daily",
    "v_metric_coverage",
    "v_body_comp_series",
]

# (metric name, column alias). Aliases reproduce
# BodyCompositionRepository._serialize exactly, so the response shape is
# unchanged. `muscle_mass` is fed from `muscle_pct`: the legacy column name is
# preserved while the metric carries the honest one.
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


def _pivot(agg: str) -> str:
    return ",\n".join(
        f"    {agg}(CASE WHEN m.name = '{metric}' THEN m.value END) AS {alias}"
        for metric, alias in PIVOT_COLUMNS
    )


# Now carries `doc_id` and `created_at`, which is the whole point of the
# refactor - this view can finally back the read path.
NEW_VIEWS = {
    "v_body_comp_measurements": f"""
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
""",
    # AVG, not MAX: 30 days in the history hold more than one weigh-in, 13 of
    # them with genuinely different readings spanning up to 4.06 lb. MAX would
    # report the heaviest of each and bias every daily summary upward.
    "v_body_comp_daily": f"""
CREATE VIEW v_body_comp_daily AS
SELECT
    o.date,
    o.source,
{_pivot("AVG")},
    COUNT(DISTINCT o.observed_at) AS n_measurements
FROM observation o
JOIN metric m ON m.observation_id = o.id
GROUP BY o.date, o.source
""",
    "v_metric_coverage": """
CREATE VIEW v_metric_coverage AS
SELECT d.name,
       d.canonical_unit,
       d.description,
       count(m.id)              AS n_rows,
       count(DISTINCT o.source) AS n_sources,
       min(o.date)              AS first_seen,
       max(o.date)              AS last_seen
FROM metric_def d
LEFT JOIN metric m ON m.name = d.name
LEFT JOIN observation o ON o.id = m.observation_id
GROUP BY d.name, d.canonical_unit, d.description
""",
    "v_body_comp_series": """
CREATE VIEW v_body_comp_series AS
SELECT o.date, o.source, m.name, m.value, m.unit
FROM metric m
JOIN observation o ON o.id = m.observation_id
WHERE m.name IN ('body_weight_lb', 'body_fat_pct', 'muscle_pct', 'water_pct')
""",
}


def _drop_views() -> None:
    for name in VIEW_NAMES:
        op.execute(f"DROP VIEW IF EXISTS {name}")


def upgrade() -> None:
    conn = op.get_bind()
    _drop_views()

    op.create_table(
        "observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.String(length=32), nullable=False),
        sa.Column(
            "date",
            sa.String(length=10),
            sa.Computed("substr(observed_at, 1, 10)", persisted=True),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observed_at", "source", name="uq_observation_instant"),
    )
    op.create_index("ix_observation_date", "observation", ["date"])

    # One observation per distinct (instant, instrument) already in `metric`.
    # created_at comes from body_composition where the measurement came from
    # there, so ingestion time survives the move; otherwise fall back to the
    # observation instant rather than inventing "now".
    conn.execute(
        sa.text(
            """
            INSERT INTO observation (observed_at, source, created_at)
            SELECT m.observed_at,
                   m.source,
                   COALESCE(
                       (SELECT b.created_at FROM body_composition b
                        WHERE b.timestamp = m.observed_at),
                       m.observed_at
                   )
            FROM metric m
            GROUP BY m.observed_at, m.source
            """
        )
    )

    # SQLite cannot add a NOT NULL foreign key and drop three columns in place,
    # so rebuild. Built with op.create_table rather than raw DDL: SQLAlchemy's
    # SQLite reflection does not recognise ON DELETE on an inline column-level
    # REFERENCES, so hand-written DDL creates a working cascade that
    # `alembic check` nonetheless reports as drift forever.
    op.create_table(
        "metric_new",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["observation.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["name"], ["metric_def.name"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id", "name", name="uq_metric_observation"),
        sa.CheckConstraint(
            "value IS NOT NULL OR text_value IS NOT NULL",
            name="ck_metric_has_a_value",
        ),
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO metric_new (id, observation_id, name, value, text_value, unit)
            SELECT m.id, o.id, m.name, m.value, m.text_value, m.unit
            FROM metric m
            JOIN observation o
              ON o.observed_at = m.observed_at AND o.source = m.source
            """
        )
    )

    before = conn.execute(sa.text("SELECT count(*) FROM metric")).scalar()
    after = conn.execute(sa.text("SELECT count(*) FROM metric_new")).scalar()
    if before != after:
        raise RuntimeError(
            f"rebuild lost rows: {before} in metric, {after} in metric_new. "
            "Most likely an observation failed to match on (observed_at, source)."
        )

    op.execute("DROP TABLE metric")
    op.execute("ALTER TABLE metric_new RENAME TO metric")
    op.create_index("ix_metric_name", "metric", ["name"])
    op.create_index("ix_metric_observation_id", "metric", ["observation_id"])

    for ddl in NEW_VIEWS.values():
        op.execute(ddl)

    print(f"  {after} metric rows across "
          f"{conn.execute(sa.text('SELECT count(*) FROM observation')).scalar()} observations")


def downgrade() -> None:
    conn = op.get_bind()
    _drop_views()

    op.execute(
        """
        CREATE TABLE metric_old (
            id          INTEGER NOT NULL,
            observed_at VARCHAR(32) NOT NULL,
            date        VARCHAR(10) GENERATED ALWAYS AS (substr(observed_at, 1, 10)) STORED NOT NULL,
            name        VARCHAR(64) NOT NULL REFERENCES metric_def(name),
            value       FLOAT,
            text_value  TEXT,
            unit        VARCHAR(32),
            source      VARCHAR(32) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_metric_observation UNIQUE (observed_at, name, source),
            CONSTRAINT ck_metric_has_a_value CHECK (value IS NOT NULL OR text_value IS NOT NULL)
        )
        """
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO metric_old (id, observed_at, name, value, text_value, unit, source)
            SELECT m.id, o.observed_at, m.name, m.value, m.text_value, m.unit, o.source
            FROM metric m
            JOIN observation o ON o.id = m.observation_id
            """
        )
    )
    op.execute("DROP TABLE metric")
    op.execute("ALTER TABLE metric_old RENAME TO metric")
    op.create_index("ix_metric_date_name", "metric", ["date", "name"])

    op.drop_index("ix_observation_date", table_name="observation")
    op.drop_table("observation")

    # The pre-refactor definitions, restated rather than imported from
    # f5abbd14fa00: a migration must keep working even if an earlier one is
    # later edited or squashed away.
    old_pivot = ",\n".join(
        f"    {{agg}}(CASE WHEN name = '{metric}' THEN value END) AS {alias}"
        for metric, alias in PIVOT_COLUMNS
    )
    op.execute(
        "CREATE VIEW v_body_comp_measurements AS SELECT observed_at, date, source,\n"
        + old_pivot.format(agg="MAX")
        + "\nFROM metric GROUP BY observed_at, source"
    )
    op.execute(
        "CREATE VIEW v_body_comp_daily AS SELECT date, source,\n"
        + old_pivot.format(agg="AVG")
        + ",\n    COUNT(DISTINCT observed_at) AS n_measurements"
        + "\nFROM metric GROUP BY date, source"
    )
    op.execute(
        """
        CREATE VIEW v_metric_coverage AS
        SELECT d.name, d.canonical_unit, d.description,
               count(m.id) AS n_rows,
               count(DISTINCT m.source) AS n_sources,
               min(m.date) AS first_seen,
               max(m.date) AS last_seen
        FROM metric_def d
        LEFT JOIN metric m ON m.name = d.name
        GROUP BY d.name, d.canonical_unit, d.description
        """
    )
    op.execute(
        """
        CREATE VIEW v_body_comp_series AS
        SELECT date, source, name, value, unit FROM metric
        WHERE name IN ('body_weight_lb', 'body_fat_pct', 'muscle_pct', 'water_pct')
        """
    )
