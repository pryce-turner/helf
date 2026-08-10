"""retire body_composition

Revision ID: 86c8bbc9e2d7
Revises: 7e8f2b1ca79b
Create Date: 2026-08-09 20:41:07.554120

Plan 0010, closing the item Plan 0003 §9 left open. `body_composition` has been
written and not read since `7bba3fe3ee35`; the only consumers left were the
dual write, the duplicate check, and the reconciliation that watched the dual
write.

Three things happen here, and the middle one is the reason this is not a
one-line drop.

1. **Five `metric_def` entries** for the quantities the wide table accepted and
   the tall one had no name for. They are all zero across 150 rows, but they
   are not inert: `mqtt_service` maps every one of them off the openScale
   payload and the POST endpoint accepts all five. Dropping the table without
   these would leave the API taking data it silently discards.

   `bone_mass_kg` already exists (Plan 0008, for DEXA) and openScale reports
   bone in kg, so bone is *not* given a second name in pounds - one quantity
   under two names is what ADR-0003's naming rule exists to prevent, and Plan
   0008 already filed every DEXA sub-mass in kg.

2. **The views are rebuilt** to pivot `bone_mass_kg` rather than the
   `bone_mass_lb` that was never defined and could never have been written.

3. **The table is dropped - but only after the migration re-verifies the
   mirror itself.** `reconcile_mirror()` reporting `in_sync` in some earlier
   session is not evidence about the database being migrated now.

`downgrade()` recreates the table **and backfills it**. A plain CREATE TABLE
would restore an empty one and call that a rollback.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '86c8bbc9e2d7'
down_revision: str | Sequence[str] | None = '7e8f2b1ca79b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_METRIC_DEFS = [
    ("bmi", "kg/m2", "Body mass index. kg/m2 by definition - the one quantity "
                     "here that is not in pounds, because the formula is."),
    ("visceral_fat", "index",
     "Visceral fat rating from a bioimpedance scale. A manufacturer index, not "
     "a mass, and not comparable to a DEXA vat_mass_kg."),
    ("metabolic_age", "years",
     "Bioimpedance 'metabolic age'. A vendor construct with no clinical "
     "definition; recorded because the scale reports it, not because it means "
     "much."),
    ("protein_pct", "%", "Protein as a percentage of body mass, from a "
                         "bioimpedance scale."),
]

# The four quantities that actually have history, plus the five that only ever
# could have. `bone_mass_kg` is already defined (Plan 0008).
PIVOT_COLUMNS = [
    ("body_weight_lb", "weight"),
    ("body_fat_pct", "body_fat_pct"),
    ("muscle_pct", "muscle_mass"),
    ("bmi", "bmi"),
    ("water_pct", "water_pct"),
    # Was `bone_mass_lb`, which has never existed in `metric_def` and so could
    # never have produced a value.
    ("bone_mass_kg", "bone_mass_kg"),
    ("visceral_fat", "visceral_fat"),
    ("metabolic_age", "metabolic_age"),
    ("protein_pct", "protein_pct"),
]

PREVIOUS_PIVOT_COLUMNS = [
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

HAS_A_BODY_WEIGHT = (
    "HAVING MAX(CASE WHEN m.name = 'body_weight_lb' THEN m.value END) IS NOT NULL"
)

SERIES_METRICS = (
    "'body_weight_lb', 'body_fat_pct', 'muscle_pct', 'water_pct', "
    "'fat_mass_kg', 'lean_mass_kg', 'ffm_kg'"
)

# What the mirror was: wide column -> metric name. Used by the pre-drop check
# and by the downgrade backfill, which are the same mapping read in opposite
# directions.
MIRRORED = [
    ("weight", "body_weight_lb"),
    ("body_fat_pct", "body_fat_pct"),
    ("muscle_mass", "muscle_pct"),
    ("water_pct", "water_pct"),
]
MIRROR_SOURCES = ("manual", "openscale")


def _pivot(agg: str, columns) -> str:
    return ",\n".join(
        f"    {agg}(CASE WHEN m.name = '{metric}' THEN m.value END) AS {alias}"
        for metric, alias in columns
    )


def _replace_views(columns) -> None:
    for name in ("v_body_comp_measurements", "v_body_comp_daily", "v_body_comp_series"):
        op.execute(f"DROP VIEW IF EXISTS {name}")

    op.execute(f"""
CREATE VIEW v_body_comp_measurements AS
SELECT
    o.id          AS doc_id,
    o.observed_at,
    o.date,
    o.source,
    o.created_at,
    -- Not stored: the unit is in the metric NAME, and pounds are canonical for
    -- body mass (ADR-0003). A literal, so the view stays shape-compatible with
    -- the response model.
    'lbs'         AS weight_unit,
{_pivot("MAX", columns)}
FROM observation o
JOIN metric m ON m.observation_id = o.id
GROUP BY o.id
{HAS_A_BODY_WEIGHT}
""")

    op.execute(f"""
CREATE VIEW v_body_comp_daily AS
SELECT
    o.date,
    o.source,
{_pivot("AVG", columns)},
    COUNT(DISTINCT o.observed_at) AS n_measurements
FROM observation o
JOIN metric m ON m.observation_id = o.id
GROUP BY o.date, o.source
{HAS_A_BODY_WEIGHT}
""")

    op.execute(f"""
CREATE VIEW v_body_comp_series AS
SELECT o.date, o.source, m.name, m.value, m.unit
FROM metric m
JOIN observation o ON o.id = m.observation_id
WHERE m.name IN ({SERIES_METRICS})
""")


def _assert_mirror_complete(conn) -> None:
    """Refuse to drop the table if the mirror is missing anything.

    `reconcile_mirror()` reporting `in_sync` in some earlier session says
    nothing about the database being migrated right now, and the whole
    justification for the drop is that the mirror already holds everything.
    This is that justification, checked at the moment it is relied on.
    """
    expected: dict[tuple[str, str], float] = {}
    for column, metric_name in MIRRORED:
        rows = conn.execute(
            sa.text(
                f"SELECT timestamp, {column} FROM body_composition "  # noqa: S608
                f"WHERE {column} IS NOT NULL"
            )
        ).all()
        for timestamp, value in rows:
            expected[(timestamp, metric_name)] = float(value)

    actual = {
        (observed_at, name): float(value)
        for observed_at, name, value in conn.execute(
            sa.text(
                "SELECT o.observed_at, m.name, m.value "
                "FROM metric m JOIN observation o ON o.id = m.observation_id "
                "WHERE m.value IS NOT NULL AND o.source IN ('manual', 'openscale')"
            )
        ).all()
    }

    missing = sorted(k for k in expected if k not in actual)
    # Tolerance, not equality: the values round-trip through SQLite REAL.
    mismatched = sorted(
        k for k, v in expected.items() if k in actual and abs(actual[k] - v) > 1e-9
    )
    if missing or mismatched:
        raise RuntimeError(
            f"Refusing to drop body_composition: the mirror is missing "
            f"{len(missing)} value(s) and disagrees on {len(mismatched)}. "
            f"e.g. missing={missing[:3]!r} mismatched={mismatched[:3]!r}. "
            f"Re-run the backfill before retiring the table - after the DROP "
            f"these values exist nowhere."
        )


def upgrade() -> None:
    conn = op.get_bind()

    for name, unit, description in NEW_METRIC_DEFS:
        conn.execute(
            sa.text(
                "INSERT OR IGNORE INTO metric_def (name, canonical_unit, description) "
                "VALUES (:n, :u, :d)"
            ),
            {"n": name, "u": unit, "d": description},
        )

    _replace_views(PIVOT_COLUMNS)

    before = conn.execute(
        sa.text("SELECT count(*) FROM v_body_comp_measurements")
    ).scalar_one()

    _assert_mirror_complete(conn)

    op.drop_index("ix_body_composition_date", table_name="body_composition")
    op.drop_index("ix_body_composition_date_timestamp", table_name="body_composition")
    op.drop_table("body_composition")

    after = conn.execute(
        sa.text("SELECT count(*) FROM v_body_comp_measurements")
    ).scalar_one()
    if before != after:
        raise RuntimeError(
            f"The read path returned {before} measurements before the drop and "
            f"{after} after. It was supposed to be reading the views already."
        )


def downgrade() -> None:
    op.create_table(
        "body_composition",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, unique=True),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("body_fat_pct", sa.Float(), nullable=True),
        sa.Column("muscle_mass", sa.Float(), nullable=True),
        sa.Column("bmi", sa.Float(), nullable=True),
        sa.Column("water_pct", sa.Float(), nullable=True),
        sa.Column("bone_mass", sa.Float(), nullable=True),
        sa.Column("visceral_fat", sa.Float(), nullable=True),
        sa.Column("metabolic_age", sa.Integer(), nullable=True),
        sa.Column("protein_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_body_composition_date", "body_composition", ["date"])
    op.create_index(
        "ix_body_composition_date_timestamp", "body_composition", ["date", "timestamp"]
    )

    # A rollback that restores an empty table is not a rollback. The five
    # columns that never held a value come back NULL, which is what they were.
    op.execute(
        """
        INSERT INTO body_composition
            (timestamp, date, weight, body_fat_pct, muscle_mass, water_pct,
             created_at)
        SELECT o.observed_at,
               o.date,
               MAX(CASE WHEN m.name = 'body_weight_lb' THEN m.value END),
               MAX(CASE WHEN m.name = 'body_fat_pct'   THEN m.value END),
               MAX(CASE WHEN m.name = 'muscle_pct'     THEN m.value END),
               MAX(CASE WHEN m.name = 'water_pct'      THEN m.value END),
               o.created_at
        FROM observation o
        JOIN metric m ON m.observation_id = o.id
        WHERE o.source IN ('manual', 'openscale')
        GROUP BY o.id
        HAVING MAX(CASE WHEN m.name = 'body_weight_lb' THEN m.value END) IS NOT NULL
        """
    )

    _replace_views(PREVIOUS_PIVOT_COLUMNS)
