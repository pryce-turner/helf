"""add food, food_log, note and v_daily_summary

Revision ID: 12fed2487b4e
Revises: 70709fd96184
Create Date: 2026-08-09 19:21:04.882931

Plan 0005. Purely additive: three new tables and one view. Nothing existing is
read, rewritten or dropped, so the rollback is complete.

Three details where this diverges from the plan as written, because the plan
predates the schema it lands on:

1. **`document` is not created here.** Plan 0008 needed it first and built it
   to 0005's spec plus `external_id` (revision `61ccf127e583`). There are live
   rows in it. 0005 §1 says so explicitly; this migration only has to not
   forget.

2. **`food.brand` is `NOT NULL DEFAULT ''`, not nullable.** SQLite treats NULLs
   as distinct in a UNIQUE index, so a nullable `brand` would let
   `('Chicken', NULL)` be inserted without limit and `UNIQUE (name, brand)`
   would be decorative. 0005 §1 recommends the empty string; taking the
   recommendation makes the constraint real and the lookup a plain `=`.
   `docs/reference/qs_mcp.py` is updated to match.

3. **`v_daily_summary` joins `observation` for its metric columns.** The plan's
   draft reads `metric.date` and `w.reps` as a string needing `REPLACE(...,
   '+', '')`. Neither survives: Plan 0003 moved `date`/`source` onto
   `observation`, and ADR-0005 made `reps` an integer.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '12fed2487b4e'
down_revision: str | Sequence[str] | None = '70709fd96184'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Activity multiplier applied to the measured resting rate to get a daily
# intake target (Plan 0008 §8). 1.4 reflects a 3-day lifting split; the
# conventional 1.55 was calibrated on endurance work and overshoots for
# strength training, where most of a session is rest between sets.
#
# Deliberately in the view and not in the stored metric: `rmr_kcal_per_day`
# stays *resting* expenditure, and changing this number is a DROP VIEW /
# CREATE VIEW with no data to migrate.
ACTIVITY_MULTIPLIER = 1.4

V_DAILY_SUMMARY = f"""
CREATE VIEW v_daily_summary AS
WITH days AS (
    SELECT date FROM workouts
    UNION SELECT date FROM food_log
    UNION SELECT date FROM observation
    UNION SELECT date FROM note
)
SELECT
    d.date,

    (SELECT COUNT(*) FROM workouts w WHERE w.date = d.date)
        AS sets_logged,

    -- Uniformly pounds already (ADR-0003 chose the unit the data was in), so
    -- this needs no unit handling. `reps` is an INTEGER since ADR-0005.
    (SELECT SUM(w.weight * w.reps) FROM workouts w
      WHERE w.date = d.date AND w.weight IS NOT NULL AND w.reps IS NOT NULL)
        AS training_volume_lb,

    -- COALESCE, because SUM over a NULL macro yields NULL for the whole day:
    -- one food with unknown protein would blank a day that is otherwise fully
    -- logged. `foods_missing_macros` below is what keeps that visible rather
    -- than silently zeroed.
    (SELECT SUM(f.kcal_per_serving * fl.servings)
       FROM food_log fl JOIN food f ON f.id = fl.food_id
      WHERE fl.date = d.date)
        AS kcal,
    (SELECT SUM(COALESCE(f.protein_g, 0) * fl.servings)
       FROM food_log fl JOIN food f ON f.id = fl.food_id
      WHERE fl.date = d.date)
        AS protein_g,
    (SELECT SUM(COALESCE(f.carb_g, 0) * fl.servings)
       FROM food_log fl JOIN food f ON f.id = fl.food_id
      WHERE fl.date = d.date)
        AS carb_g,
    (SELECT SUM(COALESCE(f.fat_g, 0) * fl.servings)
       FROM food_log fl JOIN food f ON f.id = fl.food_id
      WHERE fl.date = d.date)
        AS fat_g,
    (SELECT COUNT(*)
       FROM food_log fl JOIN food f ON f.id = fl.food_id
      WHERE fl.date = d.date
        AND (f.kcal_per_serving IS NULL OR f.protein_g IS NULL
             OR f.carb_g IS NULL OR f.fat_g IS NULL))
        AS foods_missing_macros,

    -- The most recent reading of the day, whatever instrument produced it.
    -- That is the same rule `BodyCompositionStats.latest_weight` already
    -- follows: a DEXA scan taken today is the best available answer to "what
    -- do I weigh". It does cross sources, which is only safe because it picks
    -- *one* row - never an average or a difference across instruments, which
    -- disagree by design. `body_weight_source` names the instrument so a
    -- reader can see which one it was.
    (SELECT m.value FROM metric m JOIN observation o ON o.id = m.observation_id
      WHERE o.date = d.date AND m.name = 'body_weight_lb' AND m.value IS NOT NULL
      ORDER BY o.observed_at DESC LIMIT 1)
        AS body_weight_lb,
    (SELECT o.source FROM metric m JOIN observation o ON o.id = m.observation_id
      WHERE o.date = d.date AND m.name = 'body_weight_lb' AND m.value IS NOT NULL
      ORDER BY o.observed_at DESC LIMIT 1)
        AS body_weight_source,
    (SELECT m.value FROM metric m JOIN observation o ON o.id = m.observation_id
      WHERE o.date = d.date AND m.name = 'mood'
      ORDER BY o.observed_at DESC LIMIT 1)
        AS mood,

    -- Carried forward from the last DEXA scan on or before this day, not from
    -- the newest scan overall: a target for January must not be computed from
    -- a body composition measured in March. NULL before the first scan.
    (SELECT ROUND(m.value * {ACTIVITY_MULTIPLIER})
       FROM metric m JOIN observation o ON o.id = m.observation_id
      WHERE m.name = 'rmr_kcal_per_day' AND o.date <= d.date
      ORDER BY o.observed_at DESC LIMIT 1)
        AS kcal_target,

    (SELECT COUNT(*) FROM note n WHERE n.date = d.date)
        AS notes
FROM days d
"""


def upgrade() -> None:
    op.create_table(
        "food",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        # See the module docstring: '' rather than NULL is what makes
        # UNIQUE (name, brand) enforceable in SQLite.
        sa.Column("brand", sa.Text(), nullable=False, server_default=""),
        sa.Column("serving_desc", sa.Text(), nullable=True),
        sa.Column("kcal_per_serving", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carb_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.UniqueConstraint("name", "brand", name="uq_food_name_brand"),
    )

    op.create_table(
        "food_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consumed_at", sa.Text(), nullable=False),
        # STORED so it can be indexed. Same universal join key as
        # `observation.date` and `workouts.date`.
        sa.Column(
            "date",
            sa.Text(),
            sa.Computed("substr(consumed_at, 1, 10)", persisted=True),
            nullable=False,
        ),
        sa.Column("food_id", sa.Integer(), sa.ForeignKey("food.id"), nullable=False),
        sa.Column("servings", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("meal", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.CheckConstraint(
            "meal IN ('breakfast','lunch','dinner','snack') OR meal IS NULL",
            name="ck_food_log_meal",
        ),
    )
    op.create_index("ix_food_log_date", "food_log", ["date"])
    op.create_index("ix_food_log_food_id", "food_log", ["food_id"])

    op.create_table(
        "note",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("noted_at", sa.Text(), nullable=False),
        sa.Column(
            "date",
            sa.Text(),
            sa.Computed("substr(noted_at, 1, 10)", persisted=True),
            nullable=False,
        ),
        # Intentionally unconstrained: 'intention', 'review', 'workout',
        # 'injury' and whatever the coaching loop grows next. A CHECK here
        # would mean a migration per note type (Plan 0005 §1).
        sa.Column("kind", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        # Added at creation rather than as the ALTER the plan describes. Once
        # the agent can write notes (Plan 0006), "did I observe this or did the
        # model infer it?" is unanswerable without it, and it is cheaper now
        # than as a backfill.
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
    )
    op.create_index("ix_note_date_kind", "note", ["date", "kind"])

    op.execute(V_DAILY_SUMMARY)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_daily_summary")
    op.drop_index("ix_note_date_kind", table_name="note")
    op.drop_table("note")
    op.drop_index("ix_food_log_food_id", table_name="food_log")
    op.drop_index("ix_food_log_date", table_name="food_log")
    op.drop_table("food_log")
    op.drop_table("food")
