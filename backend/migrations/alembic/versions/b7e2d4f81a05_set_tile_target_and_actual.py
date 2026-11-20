"""set tiles: target times, actual performance, and performed-only counts

Revision ID: b7e2d4f81a05
Revises: a3f9c21d7e48
Create Date: 2026-11-19 00:00:00.000000

A `workouts` row stops being only a record of what happened and becomes a
set *tile* that can also hold what is planned (plan 0018). The distinction is
the whole design: **target** values (what the tile asks for) sit beside
**actual** values (what the day player measured), so a tile can be played
without pretending the plan was the performance.

- Targets: `work_seconds`, `rest_seconds`, `rest_after_seconds` join the
  existing `reps`/`weight`/`distance`. Rest-after lives on the *preceding*
  tile — the day view renders it as a divider, and no rest row is invented.
- Actuals: `completed_reps`, `actual_work_seconds`, `actual_rest_seconds`,
  `actual_rest_after_seconds`, and `ended_early` (natural completion vs
  Stop). NULL until performed. The work/rest actuals are REAL: a partial rep
  measures in wall-clock seconds, not whole ones.

Backfill: a completed row's `completed_reps` is its `reps`; a plain `m:ss`
`time` parses into `work_seconds`, and for a completed row into
`actual_work_seconds` too — that is what the row always claimed happened.
Anything else (`'5+'`, NULL) is left alone rather than guessed at. Existing
movement-break history stays as separate timed sets; no rest or round
structure is invented for it.

`time` is **not** dropped here. The API and frontend move to the numeric
fields in this same plan, but dropping the column is a follow-up so there is
never two writable representations at once — from this revision it is
read-only legacy.

The `workouts` audit triggers are rebuilt with the new columns (they
enumerate their columns into `json_object`). `v_daily_summary` is recreated
counting **performed** tiles (`completed_at IS NOT NULL`) for `sets_logged`
and volume, which now uses `COALESCE(completed_reps, reps)`: a suggestion is
not training, and a stopped tile counts what was done, not what was planned.

The columns are plain `ADD COLUMN`s with **named** CHECKs (the anonymous-
CHECK drift lesson from `a1c8e5f30b64`), so no table rebuild is needed on the
way up. The downgrade drops them the way `d7e4f2a91b83`'s downgrade does:
triggers down, view down, batch drop against a reflection with the named
CHECKs discarded, view and triggers back.
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2d4f81a05"
down_revision: str | Sequence[str] | None = "a3f9c21d7e48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"
WORKOUT_OPS = ("UPDATE", "DELETE")

TRIGGER_BEFORE = [
    "date", "exercise_id", "category_id", "weight", "reps", "distance",
    "time", "comment", "order", "completed_at", "is_mobility",
]
TRIGGER_AFTER = TRIGGER_BEFORE + [
    "work_seconds", "rest_seconds", "rest_after_seconds",
    "completed_reps", "actual_work_seconds", "actual_rest_seconds",
    "actual_rest_after_seconds", "ended_early",
]

NEW_CHECKS = [
    "ck_workouts_work_seconds",
    "ck_workouts_rest_seconds",
    "ck_workouts_rest_after_seconds",
    "ck_workouts_completed_reps",
    "ck_workouts_actual_work_seconds",
    "ck_workouts_actual_rest_seconds",
    "ck_workouts_actual_rest_after_seconds",
    "ck_workouts_ended_early",
]

#: Unambiguous means a plain m:ss — '0:30', '12:05'. Anything else ('5+',
#: 'hold', '1:2:3') is prose and stays only in `time`.
TIME_RE = re.compile(r"^(\d{1,4}):([0-5]\d)$")

#: The view as `a3f9c21d7e48` leaves it — `12fed2487b4e`'s original plus
#: 0016's `supplements_taken` and meals-only macro counting — restated
#: verbatim so the downgrade cannot drift from what was actually there.
V_DAILY_SUMMARY_BEFORE = """
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

    -- SUM skips NULL terms, so a supplement with unknown calories contributes
    -- nothing rather than blanking the day. The macro totals COALESCE instead,
    -- and `foods_missing_macros` is what keeps that visible.
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
    -- Meals only. A vitamin has no macros to be missing, and counting it here
    -- would warn that every fully logged day is understated.
    (SELECT COUNT(*)
       FROM food_log fl JOIN food f ON f.id = fl.food_id
      WHERE fl.date = d.date AND f.kind = 'food'
        AND (f.kcal_per_serving IS NULL OR f.protein_g IS NULL
             OR f.carb_g IS NULL OR f.fat_g IS NULL))
        AS foods_missing_macros,

    (SELECT COUNT(*)
       FROM food_log fl JOIN food f ON f.id = fl.food_id
      WHERE fl.date = d.date AND f.kind = 'supplement')
        AS supplements_taken,

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
    (SELECT ROUND(m.value * 1.4)
       FROM metric m JOIN observation o ON o.id = m.observation_id
      WHERE m.name = 'rmr_kcal_per_day' AND o.date <= d.date
      ORDER BY o.observed_at DESC LIMIT 1)
        AS kcal_target,

    (SELECT COUNT(*) FROM note n WHERE n.date = d.date)
        AS notes
FROM days d
"""

#: Performed tiles only, and volume off what was actually done. The day spine
#: still comes from every `workouts` row: a day of planned tiles exists, it
#: just reports zero work. Identical to BEFORE outside the two training
#: expressions.
V_DAILY_SUMMARY_AFTER = V_DAILY_SUMMARY_BEFORE.replace(
    """    (SELECT COUNT(*) FROM workouts w WHERE w.date = d.date)
        AS sets_logged,""",
    """    (SELECT COUNT(*) FROM workouts w
      WHERE w.date = d.date AND w.completed_at IS NOT NULL)
        AS sets_logged,""",
).replace(
    """    -- Uniformly pounds already (ADR-0003 chose the unit the data was in), so
    -- this needs no unit handling. `reps` is an INTEGER since ADR-0005.
    (SELECT SUM(w.weight * w.reps) FROM workouts w
      WHERE w.date = d.date AND w.weight IS NOT NULL AND w.reps IS NOT NULL)
        AS training_volume_lb,""",
    """    -- Performed tiles only: a suggestion is not training. Volume uses
    -- `completed_reps` — what was actually done — falling back to `reps` for
    -- rows the agent writes completed over raw SQL, which never sees the
    -- derivation.
    (SELECT SUM(w.weight * COALESCE(w.completed_reps, w.reps)) FROM workouts w
      WHERE w.date = d.date AND w.completed_at IS NOT NULL
        AND w.weight IS NOT NULL
        AND COALESCE(w.completed_reps, w.reps) IS NOT NULL)
        AS training_volume_lb,""",
)


def _json_object(alias: str, columns: list[str]) -> str:
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _drop_triggers() -> None:
    for op_name in WORKOUT_OPS:
        op.execute(f"DROP TRIGGER IF EXISTS audit_workouts_{op_name.lower()}")


def _create_triggers(columns: list[str]) -> None:
    for op_name in WORKOUT_OPS:
        old = _json_object("old", columns) if op_name in ("UPDATE", "DELETE") else "NULL"
        new = _json_object("new", columns) if op_name in ("INSERT", "UPDATE") else "NULL"
        row = "old" if op_name == "DELETE" else "new"
        op.execute(f"""
CREATE TRIGGER audit_workouts_{op_name.lower()}
AFTER {op_name} ON workouts
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('workouts', {row}.id, '{op_name}', {ACTOR}, {old}, {new});
END
""")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE workouts ADD COLUMN work_seconds INTEGER "
        "CONSTRAINT ck_workouts_work_seconds "
        "CHECK (work_seconds IS NULL OR work_seconds BETWEEN 1 AND 3600)"
    )
    op.execute(
        "ALTER TABLE workouts ADD COLUMN rest_seconds INTEGER "
        "CONSTRAINT ck_workouts_rest_seconds "
        "CHECK (rest_seconds IS NULL OR rest_seconds BETWEEN 0 AND 3600)"
    )
    op.execute(
        "ALTER TABLE workouts ADD COLUMN rest_after_seconds INTEGER "
        "CONSTRAINT ck_workouts_rest_after_seconds "
        "CHECK (rest_after_seconds IS NULL OR rest_after_seconds BETWEEN 0 AND 3600)"
    )
    op.execute(
        "ALTER TABLE workouts ADD COLUMN completed_reps INTEGER "
        "CONSTRAINT ck_workouts_completed_reps "
        "CHECK (completed_reps IS NULL OR completed_reps >= 0)"
    )
    op.execute(
        "ALTER TABLE workouts ADD COLUMN actual_work_seconds FLOAT "
        "CONSTRAINT ck_workouts_actual_work_seconds "
        "CHECK (actual_work_seconds IS NULL OR actual_work_seconds >= 0)"
    )
    op.execute(
        "ALTER TABLE workouts ADD COLUMN actual_rest_seconds FLOAT "
        "CONSTRAINT ck_workouts_actual_rest_seconds "
        "CHECK (actual_rest_seconds IS NULL OR actual_rest_seconds >= 0)"
    )
    op.execute(
        "ALTER TABLE workouts ADD COLUMN actual_rest_after_seconds FLOAT "
        "CONSTRAINT ck_workouts_actual_rest_after_seconds "
        "CHECK (actual_rest_after_seconds IS NULL OR actual_rest_after_seconds >= 0)"
    )
    op.execute(
        "ALTER TABLE workouts ADD COLUMN ended_early BOOLEAN NOT NULL DEFAULT 0 "
        "CONSTRAINT ck_workouts_ended_early CHECK (ended_early IN (0, 1))"
    )

    # The backfill is data-shaped, so it is Python rather than SQL: a plain
    # m:ss parses, everything else is left alone (see TIME_RE).
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, reps, time, completed_at FROM workouts")
    ).fetchall()
    for row_id, reps, time_value, completed_at in rows:
        sets: dict[str, object] = {}
        if completed_at is not None and reps is not None:
            sets["completed_reps"] = reps
        if time_value:
            match = TIME_RE.match(time_value.strip())
            if match:
                seconds = int(match.group(1)) * 60 + int(match.group(2))
                sets["work_seconds"] = seconds
                if completed_at is not None:
                    sets["actual_work_seconds"] = seconds
        if sets:
            assignments = ", ".join(f"{name} = :{name}" for name in sets)
            bind.execute(
                sa.text(f"UPDATE workouts SET {assignments} WHERE id = :id"),
                {**sets, "id": row_id},
            )

    _drop_triggers()
    _create_triggers(TRIGGER_AFTER)

    op.execute("DROP VIEW v_daily_summary")
    op.execute(V_DAILY_SUMMARY_AFTER)


def downgrade() -> None:
    _drop_triggers()
    op.execute("DROP VIEW v_daily_summary")

    # Same dance as d7e4f2a91b83's downgrade: SQLite refuses to drop a column
    # a CHECK references, so the reflected table the batch copies from has
    # the new CHECKs discarded first.
    workouts = sa.Table("workouts", sa.MetaData(), autoload_with=op.get_bind())
    for constraint in list(workouts.constraints):
        if (
            isinstance(constraint, sa.CheckConstraint)
            and constraint.name in NEW_CHECKS
        ):
            workouts.constraints.discard(constraint)

    with op.batch_alter_table("workouts", copy_from=workouts) as batch:
        for column in (
            "work_seconds", "rest_seconds", "rest_after_seconds",
            "completed_reps", "actual_work_seconds", "actual_rest_seconds",
            "actual_rest_after_seconds", "ended_early",
        ):
            batch.drop_column(column)

    op.execute(V_DAILY_SUMMARY_BEFORE)
    _create_triggers(TRIGGER_BEFORE)
