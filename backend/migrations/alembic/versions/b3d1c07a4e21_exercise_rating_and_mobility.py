"""exercise rating and mobility flag

Revision ID: b3d1c07a4e21
Revises: 9ffbe9c21a0f
Create Date: 2026-08-10 18:45:00.000000

Two judgements about an exercise, kept on the exercise rather than on the sets
that use it.

`rating` is how good the movement is *for this person* — 1 to 5, nullable,
where NULL means unrated rather than bad. It is an opinion about the exercise,
so it belongs beside the name and not on 9,292 workout rows; re-rating a
movement is one edit and does not rewrite any history, because no logged set
carries a copy.

`is_mobility` marks a movement that is also mobility work. It is a flag, not a
category: `category_id` already says *what part of the body* a movement trains
and an exercise has exactly one of those, while "is also mobility" cuts across
categories — a hip airplane is Legs and mobility both. Modelling it as a second
category would have forced a choice between the two, or a second category
column, which is the point at which categories stop being a tree.

Both are `exercises` columns, so **the three audit triggers have to be rebuilt**
(0007 §"AUDITED"). Those triggers enumerate their columns into `json_object`,
so a new column is silently absent from the log until they are recreated — an
"immutable forever" record that quietly stops recording the thing you just
added is worse than no record. Dropped and recreated here with the two new
columns included.

The CHECK on `rating` is deliberate duplication of the Pydantic bound: the
agent writes raw SQL over MCP and never passes through Pydantic (ADR-0002), so
the constraint is the only rule both writers obey.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3d1c07a4e21"
down_revision: str | Sequence[str] | None = "9ffbe9c21a0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"

# 0007 captured name/category_id/notes. Ratings and the mobility flag are
# exactly the kind of quiet, opinion-shaped edit the log exists for.
BEFORE = ["name", "category_id", "notes"]
AFTER = ["name", "category_id", "notes", "rating", "is_mobility"]


def _json_object(alias: str, columns: list[str]) -> str:
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _exercise_triggers(columns: list[str]) -> list[str]:
    old = _json_object("old", columns)
    new = _json_object("new", columns)
    return [
        f"""
CREATE TRIGGER audit_exercises_insert
AFTER INSERT ON exercises
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('exercises', new.id, 'INSERT', {ACTOR}, NULL, {new});
END
""",
        f"""
CREATE TRIGGER audit_exercises_update
AFTER UPDATE ON exercises
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('exercises', new.id, 'UPDATE', {ACTOR}, {old}, {new});
END
""",
        f"""
CREATE TRIGGER audit_exercises_delete
AFTER DELETE ON exercises
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('exercises', old.id, 'DELETE', {ACTOR}, {old}, NULL);
END
""",
    ]


def _drop_triggers() -> None:
    for op_name in ("insert", "update", "delete"):
        op.execute(f"DROP TRIGGER IF EXISTS audit_exercises_{op_name}")


def upgrade() -> None:
    # Plain ADD COLUMN rather than a batch rebuild: recreating `exercises`
    # would drop and restore a table that 9,292 workout rows and every upcoming
    # row point at by foreign key, to add two nullable-ish columns.
    op.execute(
        "ALTER TABLE exercises ADD COLUMN rating INTEGER "
        "CHECK (rating IS NULL OR rating BETWEEN 1 AND 5)"
    )
    op.execute(
        "ALTER TABLE exercises ADD COLUMN is_mobility BOOLEAN NOT NULL DEFAULT 0 "
        "CHECK (is_mobility IN (0, 1))"
    )

    _drop_triggers()
    for statement in _exercise_triggers(AFTER):
        op.execute(statement)


def downgrade() -> None:
    # SQLite can drop a column, but not one named in a trigger body — the
    # triggers have to go first and come back describing the old shape.
    _drop_triggers()

    with op.batch_alter_table("exercises") as batch:
        batch.drop_column("is_mobility")
        batch.drop_column("rating")

    for statement in _exercise_triggers(BEFORE):
        op.execute(statement)
