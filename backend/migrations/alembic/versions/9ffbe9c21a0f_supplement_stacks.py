"""supplement stacks

Revision ID: 9ffbe9c21a0f
Revises: 86c8bbc9e2d7
Create Date: 2026-08-09 21:18:44.930712

Plan 0011. A named group of consumables that can be logged in one action -
"morning" is omega, vitamin D and CholestOff; "evening" is magnesium and omega.

**Supplements are `food` rows, not a new consumable table.** They are things
with a serving size that you swallow at a time, which is what `food` and
`food_log` already model, and whey protein is food by any definition - putting
it anywhere else would either duplicate it or hide 120 kcal a scoop from
`v_daily_summary`. The alternative was a parallel `supplement`/`supplement_log`
pair, which is `food`/`food_log` with the columns renamed, plus a second
logging path for the agent to learn, plus its own audit triggers, plus new
subqueries in the daily view.

What is genuinely new is only the *grouping*, so that is all this adds.

Three consequences worth stating up front:

1. **`food.kind`** separates a vitamin from a meal so neither page shows the
   other's rows. It also fixes a false alarm this migration would otherwise
   create: `foods_missing_macros` counts logged foods with an unknown macro, so
   without the filter every dose of creatine would report the day's totals as
   understated, forever.

2. **`food_log` gains no `stack_id`.** A logged row records what was consumed;
   the stack is the *input method*. Tying history to a preset that can be
   edited later is the same retroactive-rewrite hazard as editing a food's
   macros, except about what happened rather than what it contained. Adherence
   is still answerable - "are all of this stack's foods logged today?" - and
   that phrasing is truer, because it holds whether the button or manual entry
   was used.

3. **Deleting a stack deletes its items and nothing else.** `stack_item` goes
   by cascade; the `food` rows and every past `food_log` row are untouched,
   because they are history and the stack never owned them.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9ffbe9c21a0f'
down_revision: str | Sequence[str] | None = '86c8bbc9e2d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTIVITY_MULTIPLIER = 1.4

# Same shape as 7e8f2b1ca79b's. Editing a stack changes what a preset means for
# every future log, which is exactly the kind of quiet change 0007 exists for.
# Inserts are not audited: a stack that exists is its own record.
AUDITED = {
    "stack": ["name", "note", "order"],
    "stack_item": ["stack_id", "food_id", "servings", "order"],
}
ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"


def _json_object(alias: str, columns: list[str]) -> str:
    # Quoted because `order` is a reserved word.
    return ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)


def _audit_triggers(table: str, columns: list[str]) -> list[str]:
    old = f"json_object({_json_object('old', columns)})"
    new = f"json_object({_json_object('new', columns)})"
    return [
        f"""
CREATE TRIGGER audit_{table}_update AFTER UPDATE ON {table}
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('{table}', new.id, 'UPDATE', {ACTOR}, {old}, {new});
END
""",
        f"""
CREATE TRIGGER audit_{table}_delete AFTER DELETE ON {table}
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('{table}', old.id, 'DELETE', {ACTOR}, {old}, NULL);
END
""",
    ]


def _daily_summary(kind_filter: str, supplements_column: str) -> str:
    return f"""
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
      WHERE fl.date = d.date{kind_filter}
        AND (f.kcal_per_serving IS NULL OR f.protein_g IS NULL
             OR f.carb_g IS NULL OR f.fat_g IS NULL))
        AS foods_missing_macros,
{supplements_column}
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


# One column, not one per supplement. Which supplements were taken is a
# question for `food_log`; the daily row only has to say whether the day had
# any, so the column list cannot grow with the stack.
SUPPLEMENTS_COLUMN = """
    (SELECT COUNT(*)
       FROM food_log fl JOIN food f ON f.id = fl.food_id
      WHERE fl.date = d.date AND f.kind = 'supplement')
        AS supplements_taken,
"""


def upgrade() -> None:
    # ADD COLUMN with a CHECK is legal in SQLite and is enforced - verified
    # against a scratch database rather than assumed, because a silently
    # unenforced constraint here would let the agent invent a third kind.
    op.execute(
        "ALTER TABLE food ADD COLUMN kind TEXT NOT NULL DEFAULT 'food' "
        "CHECK (kind IN ('food','supplement'))"
    )

    op.create_table(
        "stack",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
    )

    op.create_table(
        "stack_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stack_id",
            sa.Integer(),
            sa.ForeignKey("stack.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # No cascade: removing a food from the catalog must not silently empty
        # a stack. The FK refuses the delete instead, which is the honest
        # outcome for something still in use.
        sa.Column("food_id", sa.Integer(), sa.ForeignKey("food.id"), nullable=False),
        sa.Column("servings", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("order", sa.Integer(), nullable=False, server_default="1"),
        # One entry per food per stack. Two rows for the same vitamin in one
        # group is always a mistake, and it would double the dose on every log.
        sa.UniqueConstraint("stack_id", "food_id", name="uq_stack_item_food"),
    )
    op.create_index("ix_stack_item_stack_id", "stack_item", ["stack_id"])

    for table, columns in AUDITED.items():
        for statement in _audit_triggers(table, columns):
            op.execute(statement)

    op.execute("DROP VIEW IF EXISTS v_daily_summary")
    op.execute(_daily_summary(" AND f.kind = 'food'", SUPPLEMENTS_COLUMN))


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_daily_summary")
    op.execute(_daily_summary("", ""))

    for table in AUDITED:
        op.execute(f"DROP TRIGGER IF EXISTS audit_{table}_update")
        op.execute(f"DROP TRIGGER IF EXISTS audit_{table}_delete")

    op.drop_index("ix_stack_item_stack_id", table_name="stack_item")
    op.drop_table("stack_item")
    op.drop_table("stack")

    # Supplements become ordinary foods again rather than disappearing - the
    # log rows referencing them are real consumption events either way.
    with op.batch_alter_table("food") as batch:
        batch.drop_column("kind")
