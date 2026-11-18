"""popcorn: the equipment-free movement pool on `exercises`

Revision ID: 5d1a7c3e8f02
Revises: b6f31a90c4de
Create Date: 2026-11-12 15:00:00.000000

`exercises.popcorn_seconds` — NULL is "not in the pool", a number is both
membership and that movement's default interval. One column rather than a
boolean plus a duration because the two are never wanted apart: a movement is
in the pool *as* a 30-second movement or a 40-second one, and a boolean would
need a second column free to disagree with the first.

**This is not the `exercises.is_mobility` that d7e4f2a91b83 dropped.** That
flag claimed a movement *was* mobility work, which is a fact about a
performance and not about the movement — a good morning is a loaded hinge in
one session and a loaded stretch in the next, and one exercise row cannot hold
both answers. Popcorn claims only that a movement can be done **with no
equipment, for a timed bout**: a property of its setup, in the same family as
`form`. A pushup is in the pool and is still a lift, and nothing here stops it
being logged as one.

**The CHECK is named in the ADD COLUMN itself.** An anonymous CHECK added by
`ALTER TABLE` compares unequal to the ORM's named `CheckConstraint` and leaves
`alembic check` permanently red — it happened twice (`ck_exercises_rating`,
`ck_upcoming_kind`) and cost nine days.

**The three `exercises` audit triggers are rebuilt.** They enumerate their
columns into `json_object`, so the new column would otherwise be absent from
the log while everything kept working (0007 §AUDITED). SQLite will not drop a
column a trigger names, but `popcorn_seconds` is only being added, so the
order here is: add the column, then replace the triggers.

**The movements themselves are not seeded here.** `seed_popcorn_pool.py` does
that, by hand, against a real database. Two reasons, and the first is the
existing precedent: `import_mobility_pool.py` is a script rather than a
migration because the tests migrate a temporary database from scratch, and a
migration carrying movement data would inject all of it into every test run.
The second is that inserting into `exercises` fires the audit triggers, so a
migration-seeded pool would write eighteen audit rows on every fresh install,
attributed to whoever happened to run the migration. Nothing in the read path
depends on the pool having members — unlike the `metric_def` vocabulary, which
is why *that* is seeded by migration.

The downgrade drops the column and leaves the movements. Deleting seeded
exercises would take with them anything already logged against them, and the
rows are worth more than the symmetry.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "5d1a7c3e8f02"
down_revision: str | Sequence[str] | None = "b6f31a90c4de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"
OPS = ("INSERT", "UPDATE", "DELETE")

BEFORE = ["name", "category_id", "form", "application", "rating"]
AFTER = [*BEFORE, "popcorn_seconds"]


def _json_object(alias: str, columns: list[str]) -> str:
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _triggers(columns: list[str]) -> list[str]:
    statements = []
    for op_name in OPS:
        old = _json_object("old", columns) if op_name in ("UPDATE", "DELETE") else "NULL"
        new = _json_object("new", columns) if op_name in ("INSERT", "UPDATE") else "NULL"
        row = "old" if op_name == "DELETE" else "new"
        statements.append(f"""
CREATE TRIGGER audit_exercises_{op_name.lower()}
AFTER {op_name} ON exercises
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('exercises', {row}.id, '{op_name}', {ACTOR}, {old}, {new});
END
""")
    return statements


def _drop_triggers() -> None:
    for op_name in OPS:
        op.execute(f"DROP TRIGGER IF EXISTS audit_exercises_{op_name.lower()}")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE exercises ADD COLUMN popcorn_seconds INTEGER "
        "CONSTRAINT ck_exercises_popcorn_seconds "
        "CHECK (popcorn_seconds IS NULL OR popcorn_seconds BETWEEN 5 AND 600)"
    )

    _drop_triggers()
    for statement in _triggers(AFTER):
        op.execute(statement)


def downgrade() -> None:
    _drop_triggers()
    op.execute("ALTER TABLE exercises DROP COLUMN popcorn_seconds")
    for statement in _triggers(BEFORE):
        op.execute(statement)
