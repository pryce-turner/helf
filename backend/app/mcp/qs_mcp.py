"""MCP server over `helf.db` — client-agnostic, stdio transport.

Plan 0006. Descends from `docs/reference/qs_mcp.py`, which was written against
the design doc's schema rather than the one these plans built; §2 of the plan
lists the gaps and every one of them is closed here.

**Two processes, one file (ADR-0002).** This opens `data/helf.db` directly and
never goes through the app: as the `helf-mcp` compose service over
`streamable-http` for clients that cannot spawn a process on this host, and
spawned per-client over stdio for those that can. Either way it is a second
writer on the same file, which is what makes WAL and `busy_timeout`
load-bearing rather than decorative.

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

def _find_instructions() -> Path:
    """Locate `mcp-instructions.md` without hard-coding a directory depth.

    This was `parents[3]`, which is correct in the repo
    (`<root>/backend/app/mcp/`) and wrong in the container (`/app/app/mcp/`, one
    level shallower) — it resolved to `/docs/design/...` and the server, for
    which missing instructions are fatal, could not start in production at all.

    Walking up until the file appears is layout-independent, so the same module
    works checked out, installed, or copied into an image. `QS_MCP_INSTRUCTIONS`
    overrides for anything neither layout anticipates.
    """
    override = os.environ.get("QS_MCP_INSTRUCTIONS")
    if override:
        return Path(override)

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "design" / "mcp-instructions.md"
        if candidate.exists():
            return candidate

    # Nothing found: return the repo-layout guess so the startup error names a
    # plausible path rather than `/docs/...`.
    return here.parents[3] / "docs" / "design" / "mcp-instructions.md"


INSTRUCTIONS_PATH = _find_instructions()

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


def _resolve_exercise(
    conn: sqlite3.Connection, name: str, category: str | None = None
) -> tuple[int, int, bool]:
    """Find an exercise by name, case-insensitively, creating it if new.

    G6: the reference matched exactly, so "bench press", "Bench Press" and
    "Benchpress" became three exercises and three progression charts, silently.
    `exercises.name` is UNIQUE but SQLite's default collation is case-sensitive,
    so the constraint would not have caught it either.

    G7: a created exercise needs a `category_id`, which is NOT NULL with
    foreign keys enforced. The reference supplied none, so its very first
    auto-create would have raised a FOREIGN KEY constraint failure.

    `category` names the category a *newly created* exercise lands in and is
    ignored for one that already exists — recategorising a movement because it
    turned up in a routine would overwrite a decision made on /exercises.
    """
    found = conn.execute(
        "SELECT id, category_id FROM exercises WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if found is not None:
        return found["id"], found["category_id"], False

    category_name = category or UNCATEGORIZED
    existing = conn.execute(
        "SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (category_name,)
    ).fetchone()
    category_id = (
        existing["id"]
        if existing is not None
        else conn.execute(
            "INSERT INTO categories (name, created_at) VALUES (?, ?)",
            (category_name, _now()),
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
# Mobility — the one loop the agent drives rather than assists
# --------------------------------------------------------------------------
# A mobility program is one rolling routine, so its planned rows always share
# this session number (Plan 0012 §2). Mirrors `MOBILITY_SESSION` in
# `app/repositories/upcoming_repo.py`; duplicated rather than imported, because
# this process imports nothing from `app` except `config` (ADR-0002).
MOBILITY_SESSION = 1
PLAN_KIND = "mobility_plan"
SESSION_KIND = "mobility_session"


def read_latest_mobility_session() -> dict:
    """Read the last mobility session that was actually performed, and what was
    said about it. Call this **before** write_next_mobility_session — it is the
    entire input to the next prescription.

    The session is **the mobility-flagged sets of the most recent day that has
    any**. `workouts.is_mobility` is per set, not per movement: the same
    exercise is a lift in one row and a loaded stretch in another, so a
    mobility session run alongside lifting comes back as its own sets rather
    than as the whole day. Sets the user did not flag are not part of it.

    Returns those sets in performed order with their `comment` fields. The
    comments are the user's feedback and the only feedback channel there is, so
    read every one: some describe the movement they hang off ("failed right
    side at 7"), and some are about the program as a whole ("keep this to 7
    movements max") and are attached to whichever set was on screen at the
    time. That last case is the cost of returning the subset — a program-level
    remark left on a lifting set is not here, so `query` the day if a session
    reads as though feedback is missing.

    `rationale` is what the previous session was written to achieve, so you can
    tell an instruction that worked from one that was never tried. It is null
    for a session the user assembled by hand, because nothing prescribed it.
    """
    conn = _ro()
    try:
        day = conn.execute(
            "SELECT date FROM workouts WHERE is_mobility = 1 "
            "ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if day is None:
            return {
                "ok": True,
                "found": False,
                "hint": "No mobility set has been logged yet. Movements and "
                        "their notes are in `exercises`; a movement is not "
                        "mobility work in itself, so read the notes and pick "
                        "for the objective when writing a first session.",
            }

        date = day["date"]
        sets = conn.execute(
            """SELECT e.name AS exercise, w.weight, w.reps, w.time, w.comment,
                      w."order", w.completed_at IS NOT NULL AS completed
               FROM workouts w JOIN exercises e ON e.id = w.exercise_id
               WHERE w.date = ? AND w.is_mobility = 1
               ORDER BY w."order", w.id""",
            (date,),
        ).fetchall()

        note = conn.execute(
            "SELECT body FROM note WHERE kind = ? AND date = ? "
            "ORDER BY noted_at DESC, id DESC LIMIT 1",
            (SESSION_KIND, date),
        ).fetchone()

        return {
            "ok": True,
            "found": True,
            "date": date,
            "rationale": (note["body"] or None) if note else None,
            "sets": [dict(r) for r in sets],
        }
    finally:
        conn.close()


def read_pending_mobility_session() -> dict:
    """Read the session that is on deck — written, but not yet run.

    Distinct from `read_latest_mobility_session`, which reads the last session
    *performed*. Check this **before** writing: `write_next_mobility_session`
    replaces the pending session wholesale, so writing while one is already
    waiting discards a routine the user has not had the chance to run.

    Rows come back one per set, as they are stored — `sets: 2` on the way in is
    two identical rows on the way out, in prescribed order. `pending` is false
    when nothing is waiting, and a rationale with no items is a leftover rather
    than a plan, so it is not reported on its own.
    """
    conn = _ro()
    try:
        rows = conn.execute(
            """SELECT e.name AS exercise, u.weight, u.reps, u.time, u.comment
               FROM upcoming_workouts u JOIN exercises e ON e.id = u.exercise_id
               WHERE u.kind = 'mobility' AND u.session = ?
               ORDER BY u.id""",
            (MOBILITY_SESSION,),
        ).fetchall()
        if not rows:
            return {"ok": True, "pending": False}

        note = conn.execute(
            "SELECT noted_at, body FROM note WHERE kind = ? "
            "ORDER BY noted_at DESC LIMIT 1",
            (PLAN_KIND,),
        ).fetchone()

        return {
            "ok": True,
            "pending": True,
            "items": [dict(r) for r in rows],
            "rationale": note["body"] if note else None,
            "generated_at": note["noted_at"] if note else None,
        }
    finally:
        conn.close()


def write_next_mobility_session(items: list[dict], rationale: str) -> dict:
    """Write the next mobility session, replacing whatever was pending.

    `items` is the routine in the order it is to be performed. Each is
    {exercise, sets?, reps?, weight_lb?, comment?, category?}:

    - **`sets` expands into rows**, one per set, because that is how the user
      logs — "8 and then 10 reps" is two different numbers and needs two rows
      to land in. `sets: 2, reps: 8` becomes two rows of 8.
    - **`comment` is the cue** ("each side", "soft knees — not stiff-leg", the
      setup detail). It travels onto the logged set and is then *overwritten*
      by the user's feedback, which is how the note comes back to you.
    - **`weight_lb` is pounds** (ADR-0003).

    `rationale` is what you changed and why. The user reads it on the mobility
    tab before running the session, so write it to them, not to yourself.

    Replaces the pending session wholesale — there is one rolling routine, not
    a queue. Anything already pending and not yet run is discarded.
    """
    if not items:
        return {"ok": False, "error": "a session needs at least one item"}
    if not rationale or not rationale.strip():
        return {
            "ok": False,
            "error": "rationale is required",
            "hint": "It is what the user reads to know why today differs from "
                    "last time. A session with no reasoning is a list.",
        }

    for index, item in enumerate(items):
        if not item.get("exercise"):
            return {"ok": False, "error": f"items[{index}] has no exercise"}
        if item.get("sets") is not None and int(item["sets"]) < 1:
            return {"ok": False, "error": f"items[{index}] has sets < 1"}

    created: list[str] = []
    written: list[int] = []

    with _rw() as conn:
        replaced = conn.execute(
            "DELETE FROM upcoming_workouts WHERE kind = 'mobility'"
        ).rowcount

        for item in items:
            exercise_id, category_id, was_created = _resolve_exercise(
                conn, item["exercise"], category=item.get("category")
            )
            if was_created:
                created.append(item["exercise"])

            for _ in range(int(item.get("sets") or 1)):
                written.append(
                    conn.execute(
                        """INSERT INTO upcoming_workouts
                             (session, kind, exercise_id, category_id, weight,
                              reps, comment, created_at)
                           VALUES (?, 'mobility', ?, ?, ?, ?, ?, ?)""",
                        (
                            MOBILITY_SESSION,
                            exercise_id,
                            category_id,
                            item.get("weight_lb"),
                            item.get("reps"),
                            item.get("comment"),
                            _now(),
                        ),
                    ).lastrowid
                )

        # The rationale replaces its predecessor rather than accumulating: it
        # describes the session that is pending, and only one ever is.
        conn.execute("DELETE FROM note WHERE kind = ?", (PLAN_KIND,))
        conn.execute(
            "INSERT INTO note (noted_at, kind, body, source) VALUES (?, ?, ?, 'agent')",
            (_now(), PLAN_KIND, rationale),
        )

    return {
        "ok": True,
        "sets_written": len(written),
        "movements": len(items),
        "replaced_pending_rows": replaced,
        "exercises_created": created,
    }


def update_mobility_movement(
    exercise_id: int,
    notes: str | None = None,
    rating: int | None = None,
) -> dict:
    """Record what a session taught you about a movement — the write-back step
    of the loop, after the next session has been prescribed.

    `notes` is **current state, not a log.** It replaces what is there, so
    carry forward everything still true and supersede only what is not. The
    running history is the sessions themselves; a notes field that accumulates
    becomes a changelog nobody reads, including you. The **Application**
    section and its symptom → cause → change *Reads* are the part that earns
    its keep — that is what turns next session's comment into a decision.

    `rating` is 1-5 enjoyment and exists to protect adherence, so set it
    **only from a direct statement of liking or disliking**. "Hard" and
    "frustrating" are not "disliked", and inferring it from performance
    destroys the one thing the column is for.

    Omit a field to leave it alone. Restricted to movements that have actually
    been performed as mobility work — at least one logged set with
    `is_mobility = 1`. This is the mobility loop's tool, not an exercise
    editor, and since d7e4f2a91b83 there is no flag on the exercise to gate on:
    a movement earns its place in the pool by having been used that way, which
    is the user's judgement expressed in the log rather than in a checkbox.
    Returns the previous values so you can see what you superseded.
    """
    if notes is None and rating is None:
        return {"ok": False, "error": "provide notes or rating"}
    if notes is not None and not notes.strip():
        return {
            "ok": False,
            "error": "notes cannot be blank",
            "hint": "notes replaces what is there, so blanking it discards how "
                    "the movement is performed. Omit the field to leave it "
                    "alone.",
        }
    if rating is not None and not 1 <= int(rating) <= 5:
        return {
            "ok": False,
            "error": f"rating {rating} is outside 1-5",
            "hint": "1-5 is enjoyment, NULL is unrated. There is no zero.",
        }

    with _rw() as conn:
        found = conn.execute(
            """SELECT e.name, e.notes, e.rating,
                      EXISTS (SELECT 1 FROM workouts w
                              WHERE w.exercise_id = e.id AND w.is_mobility = 1)
                          AS used_as_mobility
               FROM exercises e WHERE e.id = ?""",
            (exercise_id,),
        ).fetchone()
        if found is None:
            return {"ok": False, "error": f"no exercise with id {exercise_id}"}
        if not found["used_as_mobility"]:
            return {
                "ok": False,
                "error": f"'{found['name']}' has never been logged as mobility work",
                "hint": "This tool edits movements the mobility loop actually "
                        "uses. A movement joins that set by being performed as "
                        "mobility work - prescribe it, or the user flags the "
                        "set on the day view.",
            }

        # Column names come from this fixed mapping and never from the caller,
        # so the interpolation below has no injection surface; the values stay
        # parameterised.
        fields = {
            "notes": notes,
            "rating": int(rating) if rating is not None else None,
        }
        changed = [name for name, value in fields.items() if value is not None]
        conn.execute(
            f"UPDATE exercises SET {', '.join(f'{name} = ?' for name in changed)} "
            f"WHERE id = ?",
            [fields[name] for name in changed] + [exercise_id],
        )

        return {
            "ok": True,
            "exercise": found["name"],
            "updated": changed,
            "previous": {"notes": found["notes"], "rating": found["rating"]},
        }


# --------------------------------------------------------------------------
# Server assembly
# --------------------------------------------------------------------------
READ_TOOLS = (query, get_schema, daily_summary, get_metric_names,
              read_latest_mobility_session, read_pending_mobility_session)
WRITE_TOOLS = (add_metric, add_note, log_food, log_workout)

# Registered in **both** modes, unlike everything in WRITE_TOOLS.
#
# This is a deliberate hole in the §4 rule that the mode is the whole gate, and
# it is worth being honest about the cost: after this, "read-only" describes
# the default set of tools rather than the process. The reason it is worth it
# is that the mobility loop is the one feature whose entire value is the agent
# writing — a read-only mobility server can describe the next session but not
# produce one, which leaves the user copying a routine out of a chat window by
# hand, which is the thing this replaces.
#
# `update_mobility_movement` widens the hole from one tool to two, and the
# argument is the same one: the documented loop ends in *write down what this
# session taught you about the movement*, and without a tool for it the
# instructions were asking for something no client could perform. The pool's
# `notes` are where a comment becomes a programming decision, so a loop that
# cannot update them re-derives the same lesson every week.
#
# Both are scoped as narrowly as the idea allows. Between them they write
# planned rows for one session, its rationale, and the `notes`/`rating` of a
# movement already performed as mobility work. Neither can log a workout, record a
# measurement, add a movement to the pool, or touch anything already in the
# calendar. ADR-0004's real claim — that the *connection* is the privilege
# boundary — is untouched: `query` is still `mode=ro`, so no amount of talking
# gets a write through it.
ALWAYS_TOOLS = (write_next_mobility_session, update_mobility_movement)


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
        # `write_next_mobility_session` is registered in read-only mode too, so
        # a database predating c4a92f18de07 would fail at the first call with an
        # opaque "no such column: kind" rather than at startup.
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(upcoming_workouts)")
        }
        if columns and "kind" not in columns:
            missing.append("upcoming_workouts.kind")
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

    `ALWAYS_TOOLS` is the one exception and is argued for where it is defined.
    Note what it means for the mode: `QS_MCP_MODE=read-only` no longer implies
    the process cannot write, only that the general-purpose write tools are
    absent. `query` remains `mode=ro` either way, which is the guarantee
    ADR-0004 actually makes.
    """
    # `FastMCP` was renamed `MCPServer` in mcp 2.0. Same `.tool()` and `.run()`
    # API; the plan and the reference file both predate the rename.
    from mcp.server import MCPServer

    check_database()
    server = MCPServer("helf", instructions=load_instructions())

    for tool in READ_TOOLS + ALWAYS_TOOLS:
        server.tool()(tool)
    if not READ_ONLY:
        for tool in WRITE_TOOLS:
            server.tool()(tool)

    return server


def main() -> None:
    """Run the server on the transport `QS_MCP_TRANSPORT` names.

    Defaults to `stdio`, which is what `.mcp.json` and every local client use,
    and what ADR-0004's "separate process" means in practice. `streamable-http`
    exists for clients that cannot spawn a process on this host — an agent
    elsewhere on the tailnet.

    The transport is not a privilege boundary and must not be read as one. The
    connection still is: `query` is `mode=ro` on either transport, and the tool
    set is still chosen by `QS_MCP_MODE`. What HTTP changes is *reachability* —
    stdio is reachable by whoever can run the command, HTTP by whoever can reach
    the socket. That is why it binds `QS_MCP_HOST` (default loopback) rather
    than `0.0.0.0`: a container publishing a port is an explicit act, not a
    default.
    """
    transport = os.environ.get("QS_MCP_TRANSPORT", "stdio")
    server = build_server()

    if transport == "stdio":
        server.run()
        return

    if transport not in ("streamable-http", "sse"):
        raise ConfigurationError(
            f"Unknown QS_MCP_TRANSPORT {transport!r}. "
            f"Expected 'stdio', 'streamable-http' or 'sse'."
        )

    server.run(
        transport,
        host=os.environ.get("QS_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("QS_MCP_PORT", "8081")),
    )


if __name__ == "__main__":
    main()
