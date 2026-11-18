"""rename popcorn_seconds to movement_break_seconds

Revision ID: c8e1f4a7b293
Revises: 5d1a7c3e8f02
Create Date: 2026-11-18 12:00:00.000000

"Popcorn" was a codename, and the UI now calls the feature a **movement
break**. Leaving the old word in the schema would mean that the one place the
agent reads directly, the database (it writes raw SQL, ADR-0002), is the place
that still uses a name nothing on screen does. So the column, its CHECK and the
audit triggers' JSON keys all follow the UI.

**The table is rebuilt, not `RENAME COLUMN`ed.** `ALTER TABLE ... RENAME
COLUMN` would rewrite the CHECK expression and the trigger bodies, but it
leaves two things behind. The first is the constraint *name*,
`ck_exercises_popcorn_seconds`. SQLite cannot rename a constraint, and a name
that disagrees with the ORM's keeps `alembic check` red, which is the
`ck_upcoming_kind` / `ck_exercises_rating` bug again (see `a1c8e5f30b64`). The
second is the `'popcorn_seconds'` string keys inside the triggers'
`json_object`, which are literals rather than column references. The rebuild
is written out by hand rather than done with `batch_alter_table`, for the
reason `d7e4f2a91b83` records: batch mode rebuilds by reflection, and
reflection loses inline CHECKs.

The triggers are dropped before the rebuild and recreated after it. `DROP
TABLE` would take them with it anyway, but dropping them explicitly makes the
order visible and matches the earlier exercises rebuilds.

**Audit history is not rewritten.** Rows logged before this revision carry
`popcorn_seconds` in their JSON. `audit_log` is append-only by design (0007),
and a log that renames its own past is not a log. Anyone reading the history
across this revision should treat the two keys as the same field.

No view selects from `exercises`, so nothing has to be re-validated around the
`DROP TABLE`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c8e1f4a7b293"
down_revision: str | Sequence[str] | None = "5d1a7c3e8f02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"
OPS = ("INSERT", "UPDATE", "DELETE")

BASE = ["name", "category_id", "form", "application", "rating"]
OLD_COLUMN = "popcorn_seconds"
NEW_COLUMN = "movement_break_seconds"

SHARED = "id, name, category_id, last_used, use_count, created_at, rating, form, application"


def _json_object(alias: str, columns: list[str]) -> str:
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _drop_triggers() -> None:
    for op_name in OPS:
        op.execute(f"DROP TRIGGER IF EXISTS audit_exercises_{op_name.lower()}")


def _create_triggers(columns: list[str]) -> None:
    for op_name in OPS:
        old = _json_object("old", columns) if op_name in ("UPDATE", "DELETE") else "NULL"
        new = _json_object("new", columns) if op_name in ("INSERT", "UPDATE") else "NULL"
        row = "old" if op_name == "DELETE" else "new"
        op.execute(f"""
CREATE TRIGGER audit_exercises_{op_name.lower()}
AFTER {op_name} ON exercises
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('exercises', {row}.id, '{op_name}', {ACTOR}, {old}, {new});
END
""")


def _rebuild(from_column: str, to_column: str) -> None:
    """Rebuild `exercises` with the bout column under `to_column`.

    Same DDL the live table has (columns, both named CHECKs, both indexes),
    with only the bout column's name and its constraint's name changed.
    """
    _drop_triggers()
    op.execute("PRAGMA foreign_keys = OFF")
    op.execute(f"""
        CREATE TABLE exercises_new (
            id INTEGER NOT NULL,
            name VARCHAR(150) NOT NULL,
            category_id INTEGER NOT NULL,
            last_used VARCHAR(10),
            use_count INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            rating INTEGER CONSTRAINT ck_exercises_rating
                CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
            form TEXT,
            application TEXT,
            {to_column} INTEGER CONSTRAINT ck_exercises_{to_column}
                CHECK ({to_column} IS NULL OR {to_column} BETWEEN 5 AND 600),
            PRIMARY KEY (id),
            FOREIGN KEY(category_id) REFERENCES categories (id)
        )
    """)
    op.execute(
        f"INSERT INTO exercises_new ({SHARED}, {to_column}) "
        f"SELECT {SHARED}, {from_column} FROM exercises"
    )
    op.execute("DROP TABLE exercises")
    op.execute("ALTER TABLE exercises_new RENAME TO exercises")
    op.execute("CREATE INDEX ix_exercises_last_used ON exercises (last_used)")
    op.execute("CREATE UNIQUE INDEX ix_exercises_name ON exercises (name)")
    op.execute("PRAGMA foreign_keys = ON")
    _create_triggers([*BASE, to_column])


def upgrade() -> None:
    _rebuild(OLD_COLUMN, NEW_COLUMN)


def downgrade() -> None:
    _rebuild(NEW_COLUMN, OLD_COLUMN)
