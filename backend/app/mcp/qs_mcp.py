"""MCP server over `helf.db` — client-agnostic, stdio transport.

Plan 0006. Descends from `docs/reference/qs_mcp.py`, which was written against
the design doc's schema rather than the one these plans built; §2 of the plan
lists the gaps and every one of them is closed here.

**Two processes, one file (ADR-0002).** This runs on the host, beside the
container rather than inside it, and opens `data/helf.db` directly. That is
what makes WAL and `busy_timeout` load-bearing rather than decorative.

**Nothing is imported from the application except `config`.** No repositories,
no ORM models. The boundary that matters is not sharing a code path; reading
one setting to find the same file is not a code path.

The tool functions in this module are plain functions with no decorators, and
the FastMCP server is assembled in `build_server()`. That keeps the whole write
path testable without `mcp` installed, which matters because the write path is
where the interesting failures are.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def _default_db_path() -> Path:
    """Where the application keeps the database, asked lazily.

    Deliberately not a module-level `from app.config import settings`. A stdio
    server is launched by a client with an arbitrary working directory, and
    `Settings` reads a relative `.env` and *creates* `../data` on import - so
    an unqualified import would either explode on someone else's `.env` or
    quietly scatter empty data directories around the filesystem. Reached only
    when `QS_DB_PATH` is unset, which the documented client config always sets.
    """
    from app.config import settings

    return Path(settings.db_path)


# G1: the reference defaulted to `~/health/app.db`, which SQLite would happily
# create as an empty file - the agent would then report, confidently, that
# there is no training history. The default is the real database and a missing
# file is fatal.
_configured = os.environ.get("QS_DB_PATH")
DB_PATH = Path(_configured) if _configured else _default_db_path()

# §4: the default is the safe mode. Forgetting the variable must not be what
# grants write access.
READ_ONLY = os.environ.get("QS_MCP_MODE", "read-only") != "read-write"

MAX_ROWS = 1000
QUERY_TIMEOUT_S = 5.0
# G5. Two processes on one file contend constantly; without this, the loser of
# a race gets "database is locked" instead of waiting a few milliseconds.
BUSY_TIMEOUT_MS = 5000

INSTRUCTIONS_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "design" / "mcp-instructions.md"
)

# Exercises the agent invents need a home, and `exercises.category_id` is NOT
# NULL with foreign keys enforced (G7) - the reference's auto-create would have
# failed on its first call.
UNCATEGORIZED = "Uncategorized"


class ConfigurationError(RuntimeError):
    """Raised at startup for a problem no tool call can recover from."""


# --------------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------------
def _ro() -> sqlite3.Connection:
    """Read-only at the *engine*, not by convention.

    ADR-0004: the privilege boundary is the connection, not the tool name.
    `mode=ro` means SQLite itself refuses a write through this handle, so a
    model that talks its way into calling `query` with an UPDATE still cannot
    change anything.
    """
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


@contextmanager
def _rw() -> Iterator[sqlite3.Connection]:
    """A write transaction the audit log will attribute to the agent.

    The order is the design (Plan 0007 §9):

    1. `BEGIN IMMEDIATE` takes the write lock **first**. `audit_actor` is a
       permanent one-row table, because SQLite forbids a trigger from reading
       `temp`; the isolation therefore comes from there being one writer at a
       time. Claiming the actor without holding the lock is what would let the
       PWA's concurrent writes be recorded as the agent's.
    2. The writes happen.
    3. The actor is reset **inside the same transaction**, so an exception
       rolls the claim back with everything else. An actor left set to 'agent'
       would silently misattribute every later write the app made.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE audit_actor SET actor = 'agent' WHERE id = 1")
    try:
        yield conn
        conn.execute("UPDATE audit_actor SET actor = 'app' WHERE id = 1")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _collect(cur: sqlite3.Cursor) -> tuple[list[dict], bool]:
    """Rows up to the cap, plus whether there were more.

    `MAX_ROWS` is read here rather than bound as a default argument, so the cap
    is the module's current value and not whatever it was at import.
    """
    rows = [dict(r) for r in cur.fetchmany(MAX_ROWS)]
    truncated = cur.fetchone() is not None
    return rows, truncated


# --------------------------------------------------------------------------
# Read path
# --------------------------------------------------------------------------
def query(sql: str) -> dict:
    """Run a single read-only SELECT and return rows.

    Free-form SQL is allowed because the connection is read-only, so any write
    is rejected by SQLite itself. Prefer the views - v_daily_summary,
    v_body_comp_daily, v_body_comp_series, v_metric_coverage. Results are
    capped at 1000 rows (`truncated` flags more). Call get_schema() first if
    unsure of names. SQL errors come back as text so you can fix and retry.
    """
    conn = _ro()
    deadline = time.monotonic() + QUERY_TIMEOUT_S
    # A runaway query on a personal database is a mistake, not an attack, but
    # it still has to end - stdio gives the client no way to cancel one.
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cur = conn.execute(sql)  # raises on more than one statement
        rows, truncated = _collect(cur)
        return {
            "columns": [d[0] for d in cur.description] if cur.description else [],
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }
    except (sqlite3.Error, sqlite3.Warning) as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()


def get_schema() -> str:
    """Return the full DDL (tables and views) so you can write correct SQL."""
    conn = _ro()
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND sql IS NOT NULL "
            "AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type DESC, name"
        ).fetchall()
        return ";\n\n".join(r["sql"] for r in rows) + ";"
    finally:
        conn.close()


def daily_summary(start: str, end: str) -> dict:
    """Per-day rows joining training, intake, body composition and notes, for
    the inclusive date range [start, end]. Dates are 'YYYY-MM-DD'.

    This is the object to reach for first. It is a view over the day spine, so
    a day appears if anything at all happened on it.
    """
    conn = _ro()
    try:
        cur = conn.execute(
            "SELECT * FROM v_daily_summary WHERE date BETWEEN ? AND ? ORDER BY date",
            (start, end),
        )
        rows, truncated = _collect(cur)
        return {"rows": rows, "row_count": len(rows), "truncated": truncated}
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Write path — typed, validated, parameterised
# --------------------------------------------------------------------------
def _known_metrics(conn: sqlite3.Connection) -> list[str]:
    return [r["name"] for r in conn.execute("SELECT name FROM metric_def ORDER BY name")]


def add_metric(
    name: str,
    value: float | None = None,
    text_value: str | None = None,
    unit: str | None = None,
    observed_at: str | None = None,
    source: str = "manual",
) -> dict:
    """Record a scalar measurement - mood, sleep_hours, alcohol_units, a weight.

    Log alcohol_units = 0 on dry days, so a streak query can tell a dry day
    from an unrecorded one. Provide `value` or `text_value`. `observed_at`
    defaults to now. `source` names the instrument or the observer; re-logging
    the same (observed_at, source, name) updates in place.

    Call get_metric_names() if unsure - the name must already be defined.
    """
    if value is None and text_value is None:
        return {"ok": False, "error": "provide value or text_value"}

    observed_at = observed_at or _now()
    warnings: list[str] = []

    with _rw() as conn:
        # G3. `metric.name` is a foreign key to `metric_def` since Plan 0003,
        # so the reference's "warn and insert anyway" now fails with an opaque
        # FOREIGN KEY constraint error. Checked up front instead, and the
        # answer to "then what may I write?" comes back in the same response
        # rather than needing another round trip.
        definition = conn.execute(
            "SELECT canonical_unit FROM metric_def WHERE name = ?", (name,)
        ).fetchone()
        if definition is None:
            return {
                "ok": False,
                "error": f"'{name}' is not a defined metric",
                "valid_names": _known_metrics(conn),
                "hint": "Metric names are a fixed vocabulary. Adding one is a "
                        "migration, not a write.",
            }
        if unit and definition["canonical_unit"] and unit != definition["canonical_unit"]:
            warnings.append(
                f"unit '{unit}' is not the canonical "
                f"'{definition['canonical_unit']}' for '{name}'"
            )

        # An observation is one act of measuring and owns the instant and the
        # source; several metrics hang off it. Plan 0003 moved both columns
        # here, which is why this is a two-step insert rather than the
        # reference's single ON CONFLICT (observed_at, name, source).
        observation = conn.execute(
            "SELECT id FROM observation WHERE observed_at = ? AND source = ?",
            (observed_at, source),
        ).fetchone()
        if observation is None:
            observation_id = conn.execute(
                "INSERT INTO observation (observed_at, source, created_at) "
                "VALUES (?, ?, ?)",
                (observed_at, source, _now()),
            ).lastrowid
        else:
            observation_id = observation["id"]

        cur = conn.execute(
            """INSERT INTO metric (observation_id, name, value, text_value, unit)
               VALUES (:o, :n, :v, :t, :u)
               ON CONFLICT(observation_id, name) DO UPDATE SET
                 value = excluded.value,
                 text_value = excluded.text_value,
                 unit = excluded.unit""",
            {"o": observation_id, "n": name, "v": value, "t": text_value, "u": unit},
        )
        return {
            "ok": True,
            "id": cur.lastrowid,
            "observation_id": observation_id,
            "warnings": warnings,
        }


def get_metric_names() -> dict:
    """List the metrics that may be written, and how much of each exists.

    Reads `v_metric_coverage`, not `metric_def`, because the two answer
    different questions: a metric can be defined with nothing behind it, and
    `n_rows = 0` is what distinguishes "never recorded" from "flat".
    """
    conn = _ro()
    try:
        rows = conn.execute(
            "SELECT * FROM v_metric_coverage ORDER BY n_rows DESC, name"
        ).fetchall()
        return {"rows": [dict(r) for r in rows], "row_count": len(rows)}
    finally:
        conn.close()


def add_note(
    body: str,
    kind: str | None = None,
    noted_at: str | None = None,
    source: str = "agent",
) -> dict:
    """Save free text: `kind` is e.g. 'intention', 'review', 'injury'.

    For prose with no fixed shape. A named number over time is *not* a note -
    it has a shape already, and belongs in add_metric.

    `source` defaults to 'agent' here rather than 'manual', because a note
    written through this tool was written by a model.
    """
    with _rw() as conn:
        cur = conn.execute(
            "INSERT INTO note (noted_at, kind, body, source) VALUES (?, ?, ?, ?)",
            (noted_at or _now(), kind, body, source),
        )
        return {"ok": True, "id": cur.lastrowid}


def log_food(
    food_name: str,
    servings: float = 1.0,
    meal: str | None = None,
    consumed_at: str | None = None,
    brand: str | None = None,
    kcal_per_serving: float | None = None,
    protein_g: float | None = None,
    carb_g: float | None = None,
    fat_g: float | None = None,
) -> dict:
    """Record a food consumption event.

    Resolves the food by (name, brand), creating it if new, then logs the
    serving. Pass macros only when creating a new food - to correct an existing
    food's macros, say so rather than re-passing them, because the correction
    is retroactive across every past entry.
    """
    if meal is not None and meal not in ("breakfast", "lunch", "dinner", "snack"):
        return {
            "ok": False,
            "error": f"'{meal}' is not a meal",
            "valid_meals": ["breakfast", "lunch", "dinner", "snack"],
        }

    # G4. Brandless foods store '' and never NULL: SQLite treats NULLs as
    # distinct in a UNIQUE index, so `brand IS NULL` matching would let
    # unlimited duplicate ('Chicken', NULL) rows past UNIQUE (name, brand).
    brand = brand or ""

    with _rw() as conn:
        row = conn.execute(
            "SELECT id FROM food WHERE name = ? AND brand = ?", (food_name, brand)
        ).fetchone()
        created = row is None
        if created:
            food_id = conn.execute(
                """INSERT INTO food (name, brand, kcal_per_serving, protein_g,
                                     carb_g, fat_g, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (food_name, brand, kcal_per_serving, protein_g, carb_g, fat_g, _now()),
            ).lastrowid
        else:
            food_id = row["id"]

        cur = conn.execute(
            "INSERT INTO food_log (consumed_at, food_id, servings, meal, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (consumed_at or _now(), food_id, servings, meal, _now()),
        )
        return {
            "ok": True,
            "id": cur.lastrowid,
            "food_id": food_id,
            "food_created": created,
        }


def _resolve_exercise(conn: sqlite3.Connection, name: str) -> tuple[int, int, bool]:
    """Find an exercise by name, case-insensitively, creating it if new.

    G6: the reference matched exactly, so "bench press", "Bench Press" and
    "Benchpress" became three exercises and three progression charts, silently.
    `exercises.name` is UNIQUE but SQLite's default collation is case-sensitive,
    so the constraint would not have caught it either.

    G7: a created exercise needs a `category_id`, which is NOT NULL with
    foreign keys enforced. The reference supplied none, so its very first
    auto-create would have raised a FOREIGN KEY constraint failure.
    """
    found = conn.execute(
        "SELECT id, category_id FROM exercises WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if found is not None:
        return found["id"], found["category_id"], False

    category = conn.execute(
        "SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (UNCATEGORIZED,)
    ).fetchone()
    category_id = (
        category["id"]
        if category is not None
        else conn.execute(
            "INSERT INTO categories (name, created_at) VALUES (?, ?)",
            (UNCATEGORIZED, _now()),
        ).lastrowid
    )
    exercise_id = conn.execute(
        "INSERT INTO exercises (name, category_id, use_count, created_at) "
        "VALUES (?, ?, 0, ?)",
        (name, category_id, _now()),
    ).lastrowid
    return exercise_id, category_id, True


def log_workout(
    sets: list[dict],
    date: str | None = None,
    notes: str | None = None,
) -> dict:
    """Log a training session. `sets` is a list of
    {exercise, reps, weight_lb, comment?}, in the order performed.

    **Weights are pounds** (ADR-0003), not kilograms.

    Exercises not already in the catalog are created and named back in
    `exercises_created` - check that list, because a name that appears there
    unexpectedly is a typo that has just become a permanent exercise.
    """
    date = (date or _now())[:10]
    created: list[str] = []
    written: list[int] = []

    for index, entry in enumerate(sets):
        if not entry.get("exercise"):
            return {"ok": False, "error": f"sets[{index}] has no exercise"}

    with _rw() as conn:
        # Plan 0004 §4's adapter: the tool speaks sessions and sets, storage
        # stays flat. `workouts` is one row per logged set, and the hierarchy
        # is not observable through the views, so the regrain stays deferred.
        start_order = conn.execute(
            'SELECT COALESCE(MAX("order"), 0) FROM workouts WHERE date = ?', (date,)
        ).fetchone()[0]

        for offset, entry in enumerate(sets, start=1):
            exercise_id, category_id, was_created = _resolve_exercise(
                conn, entry["exercise"]
            )
            if was_created:
                created.append(entry["exercise"])

            # `reps` is an INTEGER (ADR-0005). No AMRAP notation, ever - the
            # intent goes in `comment` as prose.
            written.append(
                conn.execute(
                    """INSERT INTO workouts (date, exercise_id, category_id, weight,
                                             reps, comment, "order", created_at,
                                             updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        date,
                        exercise_id,
                        category_id,
                        entry.get("weight_lb"),
                        entry.get("reps"),
                        entry.get("comment"),
                        start_order + offset,
                        _now(),
                        _now(),
                    ),
                ).lastrowid
            )

        if notes:
            conn.execute(
                "INSERT INTO note (noted_at, kind, body, source) VALUES (?, ?, ?, ?)",
                (f"{date}T12:00:00", "workout", notes, "agent"),
            )

    return {
        "ok": True,
        "date": date,
        "sets_logged": len(written),
        "workout_ids": written,
        "exercises_created": created,
    }


# --------------------------------------------------------------------------
# Server assembly
# --------------------------------------------------------------------------
READ_TOOLS = (query, get_schema, daily_summary, get_metric_names)
WRITE_TOOLS = (add_metric, add_note, log_food, log_workout)


def load_instructions() -> str:
    """Judgment the tool signatures cannot encode (Plan 0006 §5).

    Kept in `docs/design/mcp-instructions.md` and loaded at startup rather than
    inlined, so it is reviewable in git as prose instead of buried in a string
    literal. Missing is fatal: a server that starts without them hands the
    model a database it will misread confidently.
    """
    if not INSTRUCTIONS_PATH.exists():
        raise ConfigurationError(
            f"Server instructions not found at {INSTRUCTIONS_PATH}. They are "
            f"the difference between an agent that reads this database and one "
            f"that guesses at it - refusing to start rather than shipping "
            f"without them."
        )
    return INSTRUCTIONS_PATH.read_text()


def check_database() -> None:
    """Fail at startup rather than at the first tool call.

    G1: SQLite creates a missing database silently, and the agent would then
    report an empty training history as fact.
    """
    if not DB_PATH.exists():
        raise ConfigurationError(
            f"No database at {DB_PATH}. Set QS_DB_PATH to the host path of "
            f"data/helf.db - the same file docker-compose bind-mounts. It is "
            f"not created on demand: an empty database is indistinguishable "
            f"from a lost one once the agent starts answering from it."
        )
    conn = _ro()
    try:
        missing = [
            name
            for name in ("v_daily_summary", "v_metric_coverage", "audit_log")
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name = ?", (name,)
            ).fetchone()
            is None
        ]
    finally:
        conn.close()
    if missing:
        raise ConfigurationError(
            f"{DB_PATH} is missing {', '.join(missing)}. Run `alembic upgrade "
            f"head` against it first."
        )


def build_server():
    """Assemble the MCP server.

    Write tools are **not registered** in read-only mode rather than registered
    and refusing (§4). A tool that does not exist cannot be attempted, argued
    with, or retried; a tool that answers "not permitted" invites all three.
    Registration is the gate because no client-side allowlist can be relied on
    when the client is unknown.
    """
    # `FastMCP` was renamed `MCPServer` in mcp 2.0. Same `.tool()` and `.run()`
    # API; the plan and the reference file both predate the rename.
    from mcp.server import MCPServer

    check_database()
    server = MCPServer("helf", instructions=load_instructions())

    for tool in READ_TOOLS:
        server.tool()(tool)
    if not READ_ONLY:
        for tool in WRITE_TOOLS:
            server.tool()(tool)

    return server


def main() -> None:
    build_server().run()  # stdio


if __name__ == "__main__":
    main()
