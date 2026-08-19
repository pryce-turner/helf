"""split exercises.notes into form and application

Revision ID: e2b9c4d17a05
Revises: a1c8e5f30b64
Create Date: 2026-08-19 20:00:00.000000

`exercises.notes` held two different kinds of knowledge in one blob:

- **Form** — how to perform the movement. Reference material, written once,
  changing only when the movement itself is set up differently.
- **Application** — symptom → likely cause → what to change. What the mobility
  loop *learns*, and the layer that turns a comment on a set into a
  programming decision.

They have different authors and different lifetimes, and one field made that
dangerous rather than merely untidy. `update_mobility_movement` replaces the
whole field — "current state, not a log" — so every time the agent recorded
something it had learned about application, it had to re-emit the form
instructions verbatim from memory. Any drift there silently rewrites reference
material the agent never meant to touch, and nothing downstream can tell a
deliberate correction from a transcription slip. Two columns make that
impossible: writing `application` cannot damage `form`.

**The backfill needs no parsing.** All eight populated rows are pure form —
"Bar on 14, safeties on 7", "Foot quite far forward, emphasize the psoas
stretch at the bottom" — and not one contains an Application section. So
`form = notes` is exact, and `application` starts NULL, which is the honest
value: nothing has been learned and written down yet. Inventing an application
section by splitting on a heading that does not exist would have produced
guesses in the field the agent trusts most.

**The three `exercises` audit triggers are rebuilt** (0007 §AUDITED). They
enumerate their columns into `json_object`, so `notes` disappearing leaves a
trigger that will not compile, and the two new columns would otherwise be
absent from the log. SQLite also refuses to drop a column a trigger names, so
they come down first. No table rebuild is needed this time: `notes` carries no
CHECK and no index, so a plain DROP COLUMN suffices once the triggers are gone.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e2b9c4d17a05"
down_revision: str | Sequence[str] | None = "a1c8e5f30b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"
OPS = ("INSERT", "UPDATE", "DELETE")

BEFORE = ["name", "category_id", "notes", "rating"]
AFTER = ["name", "category_id", "form", "application", "rating"]


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
    op.execute("ALTER TABLE exercises ADD COLUMN form TEXT")
    op.execute("ALTER TABLE exercises ADD COLUMN application TEXT")
    op.execute("UPDATE exercises SET form = notes WHERE notes IS NOT NULL")

    _drop_triggers()
    op.execute("ALTER TABLE exercises DROP COLUMN notes")
    for statement in _triggers(AFTER):
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE exercises ADD COLUMN notes TEXT")
    # Lossy in the direction that matters: the two halves are concatenated back
    # into one blob, and nothing afterwards can tell where the seam was. That
    # is the whole reason for the forward migration.
    op.execute("""
        UPDATE exercises SET notes = TRIM(
            COALESCE(form, '') ||
            CASE
                WHEN application IS NOT NULL AND application <> ''
                THEN CASE WHEN form IS NOT NULL AND form <> ''
                          THEN char(10) || char(10) ELSE '' END
                     || '## Application' || char(10) || application
                ELSE ''
            END
        )
        WHERE form IS NOT NULL OR application IS NOT NULL
    """)
    op.execute("UPDATE exercises SET notes = NULL WHERE notes = ''")

    _drop_triggers()
    op.execute("ALTER TABLE exercises DROP COLUMN application")
    op.execute("ALTER TABLE exercises DROP COLUMN form")
    for statement in _triggers(BEFORE):
        op.execute(statement)
