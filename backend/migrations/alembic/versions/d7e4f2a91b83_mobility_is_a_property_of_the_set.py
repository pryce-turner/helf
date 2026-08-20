"""mobility is a property of the set, not of the movement or the day

Revision ID: d7e4f2a91b83
Revises: c4a92f18de07
Create Date: 2026-08-19 00:00:00.000000

`exercises.is_mobility` asked the wrong question. It marked a *movement* as
mobility work, but whether a movement is mobility work depends on what it was
being used for that day: a good morning is a hinge under load in one session
and a loaded stretch in the next, and the exercise row cannot hold both answers
at once. b3d1c07a4e21 argued the flag belonged on the exercise "rather than on
9,292 workout rows" because re-rating should not rewrite history. That reasoning
holds for `rating`, which is an opinion about the movement. It does not hold
here, because this is not an opinion about the movement at all - it is a fact
about one performance of it.

The day-level marker went the same way. A `note` row of kind `mobility_session`
stood in for "this day was a mobility session", which forced two facts into one
row: whether the day was mobility, and the agent's reasoning for it. Unticking
the box therefore destroyed the rationale. With the flag on the set, the day is
derived - a mobility day is a day with mobility sets - and the note goes back to
carrying only what it is good at, which is prose.

So:

- `workouts.is_mobility` is added, backfilled from the movements that carried
  the old flag. That is the only mapping the schema supports, and it is exact
  for every set of a movement that was only ever mobility work.
- `exercises.is_mobility` is dropped.
- `note` keeps kind `mobility_session`, now purely as the rationale for a
  session that was run. It no longer asserts anything; nothing reads it to
  decide whether a day happened.

`upcoming_workouts` needs no column: it already carries `kind`, which is
`lifting` or `mobility`, so transfer sets the flag from the kind it is copying.

**Both tables' audit triggers are rebuilt** (0007 §AUDITED, and the same note
b3d1c07a4e21 made when it added the column). The triggers enumerate their
columns into `json_object`, so a new column is silently absent from the log
until they are recreated, and a dropped one is a trigger that no longer
compiles. SQLite will not drop a column named in a trigger body, so on the
`exercises` side the triggers have to come down first and go back up describing
the new shape.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e4f2a91b83"
down_revision: str | Sequence[str] | None = "c4a92f18de07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"

EXERCISE_BEFORE = ["name", "category_id", "notes", "rating", "is_mobility"]
EXERCISE_AFTER = ["name", "category_id", "notes", "rating"]

WORKOUT_BEFORE = ["date", "exercise_id", "category_id", "weight", "reps",
                  "distance", "time", "comment", "order", "completed_at"]
WORKOUT_AFTER = WORKOUT_BEFORE + ["is_mobility"]


def _json_object(alias: str, columns: list[str]) -> str:
    """`order` is a reserved word, so every column is quoted (0007)."""
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _triggers(table: str, ops: list[str], columns: list[str]) -> list[str]:
    statements = []
    for op_name in ops:
        old = _json_object("old", columns) if op_name in ("UPDATE", "DELETE") else "NULL"
        new = _json_object("new", columns) if op_name in ("INSERT", "UPDATE") else "NULL"
        row = "old" if op_name == "DELETE" else "new"
        statements.append(f"""
CREATE TRIGGER audit_{table}_{op_name.lower()}
AFTER {op_name} ON {table}
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('{table}', {row}.id, '{op_name}', {ACTOR}, {old}, {new});
END
""")
    return statements


def _drop(table: str, ops: list[str]) -> None:
    for op_name in ops:
        op.execute(f"DROP TRIGGER IF EXISTS audit_{table}_{op_name.lower()}")



def _rebuild_exercises(with_mobility: bool) -> None:
    """Rebuild `exercises` by hand rather than through `batch_alter_table`.

    SQLite will not `DROP COLUMN` a column named in a CHECK constraint, and
    `is_mobility` carries its own, so the table has to be rebuilt either way.
    Alembic's batch mode does that by reflecting the table - and reflection
    loses an *inline, unnamed* column CHECK, which is how `rating` is written.
    The first attempt at this migration silently dropped
    `CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)`, the constraint ADR-0002
    calls the only rule both writers obey: the agent writes raw SQL and never
    passes through Pydantic, so losing it means nothing bounds a rating at all.

    Spelling the DDL out keeps every constraint visible in this file, and names
    the rating CHECK on the way past - it was anonymous, which is half of the
    standing `alembic check` drift.
    """
    mobility_col = (
        ",\n            is_mobility BOOLEAN NOT NULL DEFAULT 0 "
        "CONSTRAINT ck_exercises_is_mobility CHECK (is_mobility IN (0, 1))"
        if with_mobility
        else ""
    )
    columns = "id, name, category_id, last_used, use_count, created_at, notes, rating"
    if with_mobility:
        columns += ", is_mobility"

    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(f"""
        CREATE TABLE exercises_new (
            id INTEGER NOT NULL,
            name VARCHAR(150) NOT NULL,
            category_id INTEGER NOT NULL,
            last_used VARCHAR(10),
            use_count INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            notes TEXT,
            rating INTEGER CONSTRAINT ck_exercises_rating
                CHECK (rating IS NULL OR rating BETWEEN 1 AND 5){mobility_col},
            PRIMARY KEY (id),
            FOREIGN KEY(category_id) REFERENCES categories (id)
        )
    """)
    op.execute(
        f"INSERT INTO exercises_new ({columns}) SELECT {columns} FROM exercises"
    )
    op.execute("DROP TABLE exercises")
    op.execute("ALTER TABLE exercises_new RENAME TO exercises")
    op.execute("CREATE INDEX ix_exercises_last_used ON exercises (last_used)")
    op.execute("CREATE UNIQUE INDEX ix_exercises_name ON exercises (name)")
    op.execute("PRAGMA foreign_keys = ON")


EXERCISE_OPS = ["INSERT", "UPDATE", "DELETE"]
WORKOUT_OPS = ["UPDATE", "DELETE"]


def upgrade() -> None:
    # The CHECK is *named*. `ck_exercises_rating` and `ck_upcoming_kind` were
    # added as anonymous inline checks, so `alembic check` reports them as
    # missing against the named constraints the ORM declares and has failed
    # ever since. Naming this one keeps the drift from growing a third case.
    op.execute(
        "ALTER TABLE workouts ADD COLUMN is_mobility BOOLEAN NOT NULL DEFAULT 0 "
        "CONSTRAINT ck_workouts_is_mobility CHECK (is_mobility IN (0, 1))"
    )

    # The only mapping available: every set of a movement that carried the old
    # flag becomes a mobility set. Exact where a movement was only ever used as
    # mobility work, and an over-count where it was not - which is the same
    # ambiguity that motivated the move, now visible per set and correctable
    # one checkbox at a time instead of being unanswerable.
    op.execute(
        "UPDATE workouts SET is_mobility = 1 "
        "WHERE exercise_id IN (SELECT id FROM exercises WHERE is_mobility = 1)"
    )

    _drop("workouts", WORKOUT_OPS)
    for statement in _triggers("workouts", WORKOUT_OPS, WORKOUT_AFTER):
        op.execute(statement)

    # Must follow the backfill, which reads the column being dropped.
    _drop("exercises", EXERCISE_OPS)
    _rebuild_exercises(with_mobility=False)
    for statement in _triggers("exercises", EXERCISE_OPS, EXERCISE_AFTER):
        op.execute(statement)


def downgrade() -> None:
    _drop("exercises", EXERCISE_OPS)
    op.execute(
        "ALTER TABLE exercises ADD COLUMN is_mobility BOOLEAN NOT NULL DEFAULT 0 "
        "CONSTRAINT ck_exercises_is_mobility CHECK (is_mobility IN (0, 1))"
    )

    # Lossy in the direction that matters: per-set intent collapses back to a
    # property of the movement, so a movement used as mobility work once is
    # marked mobility work always. That loss is the whole reason for the
    # forward migration; the downgrade cannot invent the distinction back.
    op.execute(
        "UPDATE exercises SET is_mobility = 1 "
        "WHERE id IN (SELECT exercise_id FROM workouts WHERE is_mobility = 1)"
    )

    for statement in _triggers("exercises", EXERCISE_OPS, EXERCISE_BEFORE):
        op.execute(statement)

    _drop("workouts", WORKOUT_OPS)

    # `batch_alter_table` reflects the table and rebuilds it, and reflection
    # brings `ck_workouts_is_mobility` along - so the temp table was emitted
    # carrying a CHECK that names the very column being dropped, and every
    # downgrade past this revision died on `no such column: is_mobility`. The
    # upgrade never hit it because it hand-writes its rebuild
    # (`_rebuild_exercises`) and simply omits both the column and its CHECK.
    #
    # SQLite has no DROP CONSTRAINT, and it refuses to drop a column a CHECK
    # references, so the constraint has to leave in the same rebuild as the
    # column. Handing `copy_from` a reflected table with it discarded is how
    # that becomes one operation rather than two impossible ones.
    workouts = sa.Table("workouts", sa.MetaData(), autoload_with=op.get_bind())
    for constraint in list(workouts.constraints):
        if (
            isinstance(constraint, sa.CheckConstraint)
            and constraint.name == "ck_workouts_is_mobility"
        ):
            workouts.constraints.discard(constraint)

    # Second hazard in the same rebuild, and it only becomes reachable once the
    # CHECK above is fixed: batch drops and recreates `workouts`, and SQLite
    # validates every view against the new shape while it does so, so this died
    # on "error in view v_daily_summary: no such table: main.workouts". The
    # same shape of bug as 0011's rollback (docs/plans/README.md).
    #
    # Captured from `sqlite_master` rather than restated, so it cannot drift
    # from whatever definition the surrounding revisions left in place. The
    # view does not select `is_mobility`, so it is valid again verbatim - if a
    # later revision teaches it to, this has to become a real re-CREATE.
    view_sql = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'view' AND name = 'v_daily_summary'"
            )
        )
        .scalar()
    )
    if view_sql:
        op.execute("DROP VIEW v_daily_summary")

    with op.batch_alter_table("workouts", copy_from=workouts) as batch:
        batch.drop_column("is_mobility")

    if view_sql:
        op.execute(view_sql)
    for statement in _triggers("workouts", WORKOUT_OPS, WORKOUT_BEFORE):
        op.execute(statement)
