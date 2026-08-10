"""append-only audit log

Revision ID: 7e8f2b1ca79b
Revises: 12fed2487b4e
Create Date: 2026-08-09 20:14:33.201884

Plan 0007. Provenance and recovery, not a security control: it answers "what
changed and who changed it" for a single-user database, and nothing at this
layer is tamper-proof against someone holding the file.

Everything here is triggers rather than application code, for one reason. There
are two writers (ADR-0002) — SQLAlchemy for the app, raw `sqlite3` for the
agent — and application-level auditing would cover exactly one of them. A
trigger fires whichever process issued the statement, which is the only place
the guarantee can live.

**Plan 0007 §3's option A is not implementable in SQLite.** It proposes a
per-connection `TEMP` marker table that the trigger reads. Two things break it,
both confirmed against a scratch database:

    CREATE TRIGGER t ... SELECT actor FROM temp.session_actor ...
    Error: in prepare, trigger t cannot reference objects in database temp

and an unqualified name does *not* resolve to a connection's temp shadow at
trigger-fire time — it binds to `main` when the trigger is compiled, so every
write is labelled with the main-schema default no matter what the connection
created.

So the marker is a permanent one-row table, `audit_actor`, and the isolation
comes from SQLite's write model instead of from `TEMP`: there is one writer at
a time, so a writer that sets the actor inside its own write transaction cannot
have another writer's rows attributed to it. The requirement this places on the
agent is written on the table itself, and is the whole reason
`set_actor`/`BEGIN IMMEDIATE` exists in `docs/reference/qs_mcp.py`.

The default is `'app'` and it is never wrong by accident: a writer that says
nothing is the PWA, which is true today and stays true, because the only other
writer has to opt in explicitly.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7e8f2b1ca79b'
down_revision: str | Sequence[str] | None = '12fed2487b4e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTOR = "(SELECT actor FROM audit_actor WHERE id = 1)"

# Which mutations are worth recording. Deliberately not everything: auditing
# high-volume inserts doubles write cost to record something already evident
# from the row's own existence.
#
# The interesting event for most tables is a *change*, because a change
# destroys what was there before and an insert does not.
#
#   metric      INSERT included, because the agent's `add_metric` upserts on
#               conflict (`qs_mcp.py`) - an "insert" can silently replace a
#               measurement.
#   food        an edit retroactively rewrites every past log entry that
#               references it (Plan 0005 §1). This is the single most invisible
#               mutation in the schema.
#   exercises   INSERT included, because the repositories auto-create rows on
#               reference and so will the agent - a typo becomes a new
#               exercise, silently.
AUDITED: dict[str, tuple[list[str], list[str]]] = {
    # table: (ops, columns captured)
    "metric": (
        ["INSERT", "UPDATE", "DELETE"],
        ["observation_id", "name", "value", "text_value", "unit", "document_id"],
    ),
    "food": (
        ["UPDATE", "DELETE"],
        ["name", "brand", "serving_desc", "kcal_per_serving", "protein_g",
         "carb_g", "fat_g"],
    ),
    "food_log": (
        ["UPDATE", "DELETE"],
        ["consumed_at", "food_id", "servings", "meal"],
    ),
    "note": (
        ["UPDATE", "DELETE"],
        ["noted_at", "kind", "body", "source"],
    ),
    "workouts": (
        ["UPDATE", "DELETE"],
        ["date", "exercise_id", "category_id", "weight", "reps", "distance",
         "time", "comment", "order", "completed_at"],
    ),
    "exercises": (
        ["INSERT", "UPDATE", "DELETE"],
        ["name", "category_id", "notes"],
    ),
}


def _json_object(alias: str, columns: list[str]) -> str:
    """`json_object('col', old.col, ...)` for one side of a change.

    Column names are quoted because `workouts` has an `order` column, which is
    a reserved word and produces a syntax error unquoted.
    """
    pairs = ", ".join(f"'{c}', {alias}.\"{c}\"" for c in columns)
    return f"json_object({pairs})"


def _trigger(table: str, op_name: str, columns: list[str]) -> str:
    old = _json_object("old", columns) if op_name in ("UPDATE", "DELETE") else "NULL"
    new = _json_object("new", columns) if op_name in ("INSERT", "UPDATE") else "NULL"
    return f"""
CREATE TRIGGER audit_{table}_{op_name.lower()}
AFTER {op_name} ON {table}
BEGIN
    INSERT INTO audit_log (table_name, row_id, op, actor, old_values, new_values)
    VALUES ('{table}', {'old' if op_name == 'DELETE' else 'new'}.id, '{op_name}',
            {ACTOR}, {old}, {new});
END
"""


def upgrade() -> None:
    op.create_table(
        "audit_actor",
        # One row, enforced. A marker table that can hold two rows is a marker
        # table that will eventually hold two rows.
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.Text(), nullable=False, server_default="app"),
        sa.CheckConstraint("id = 1", name="ck_audit_actor_single_row"),
    )
    op.execute("INSERT INTO audit_actor (id, actor) VALUES (1, 'app')")

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "changed_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("op", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False, server_default="app"),
        sa.Column("old_values", sa.Text(), nullable=True),
        sa.Column("new_values", sa.Text(), nullable=True),
        sa.CheckConstraint("op IN ('INSERT','UPDATE','DELETE')", name="ck_audit_log_op"),
        sa.CheckConstraint(
            "old_values IS NULL OR json_valid(old_values)",
            name="ck_audit_log_old_is_json",
        ),
        sa.CheckConstraint(
            "new_values IS NULL OR json_valid(new_values)",
            name="ck_audit_log_new_is_json",
        ),
    )
    op.create_index("ix_audit_log_table_row", "audit_log", ["table_name", "row_id"])
    op.create_index("ix_audit_log_changed_at", "audit_log", ["changed_at"])

    # The crux. Without these the table is merely a log; with them it is a
    # record, and the difference is that nothing - including this application -
    # can quietly revise it.
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only');
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only');
        END
        """
    )

    for table, (ops, columns) in AUDITED.items():
        for op_name in ops:
            op.execute(_trigger(table, op_name, columns))

    _assert_append_only(op.get_bind())


def _assert_append_only(conn) -> None:
    """Prove the guarantee holds against the database this just ran on.

    A `CREATE TRIGGER` that was accepted is not evidence that the trigger
    fires, and an audit log whose immutability was never tested is a log that
    will be discovered to be mutable at the worst moment.

    The whole probe runs inside a savepoint that is rolled back, because the
    test row cannot be deleted afterwards - which is precisely what is being
    verified. Each expected abort gets its own savepoint too: SQLAlchemy marks
    a connection as needing rollback after a failed statement, and the
    remaining checks would fail for the wrong reason without it.
    """
    probe = conn.begin_nested()
    try:
        conn.execute(
            sa.text(
                "INSERT INTO audit_log (table_name, row_id, op) "
                "VALUES ('__selftest__', 0, 'INSERT')"
            )
        )
        for statement in (
            "UPDATE audit_log SET op = 'DELETE' WHERE table_name = '__selftest__'",
            "DELETE FROM audit_log WHERE table_name = '__selftest__'",
        ):
            attempt = conn.begin_nested()
            try:
                conn.execute(sa.text(statement))
            except Exception as exc:  # noqa: BLE001 - the abort is the pass condition
                attempt.rollback()
                if "append-only" not in str(exc):
                    raise
            else:
                attempt.rollback()
                raise RuntimeError(
                    f"`{statement}` was allowed. The append-only triggers are "
                    f"not in force, which makes audit_log a suggestion rather "
                    f"than a record."
                )
    finally:
        probe.rollback()


def downgrade() -> None:
    for table, (ops, _columns) in AUDITED.items():
        for op_name in ops:
            op.execute(f"DROP TRIGGER IF EXISTS audit_{table}_{op_name.lower()}")
    # Must precede dropping the table, which is itself a small demonstration
    # that the enforcement is real.
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update")
    op.drop_index("ix_audit_log_changed_at", table_name="audit_log")
    op.drop_index("ix_audit_log_table_row", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("audit_actor")
