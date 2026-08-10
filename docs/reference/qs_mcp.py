"""
qs_mcp.py — MCP server exposing the quantified-self SQLite DB to Hermes.

Design (see plan.md):
  - Two connections: read-only for `query`, read-write for the typed writers.
    The privilege boundary is the connection, not the tool name.
  - Read path: one generic `query(sql)` tool — read-only enforced at the
    connection (mode=ro), single statement (sqlite3.execute enforces it),
    row-capped, with a wall-clock query timeout.
  - Schema exposed as an MCP resource AND a `get_schema` tool, so the model can
    always read the DDL/views before writing SQL.
  - Write path: typed, parameterized tools (add_metric, add_note, log_food,
    log_workout) that validate before inserting. No raw write SQL is exposed.
  - Convenience read: daily_summary(start, end) over v_daily_summary.

Install:  pip install mcp        (pulls in pydantic)
Run:      QS_DB_PATH=/path/to/app.db python qs_mcp.py
          (or `python -m qs_mcp` if it's on your PYTHONPATH — match the path in
           the Hermes mcp_servers entry)
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP

DB_PATH = os.environ.get("QS_DB_PATH", os.path.expanduser("~/health/app.db"))

MAX_ROWS = 1000          # cap rows returned by `query`
QUERY_TIMEOUT_S = 5.0    # hard wall-clock cap for a single `query`

mcp = FastMCP("quantified-self")


# --------------------------------------------------------------------------
# Connections — opened per call (safe across the harness's worker threads).
# --------------------------------------------------------------------------
def _ro() -> sqlite3.Connection:
    # mode=ro: the engine itself refuses any write through this handle.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rw() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _collect(cur: sqlite3.Cursor, limit: int = MAX_ROWS) -> tuple[list[dict], bool]:
    rows = [dict(r) for r in cur.fetchmany(limit)]
    truncated = cur.fetchone() is not None
    return rows, truncated


# --------------------------------------------------------------------------
# Read path
# --------------------------------------------------------------------------
@mcp.tool()
def query(sql: str) -> dict:
    """Run a single read-only SELECT and return rows.

    Free-form SQL is allowed, but the connection is read-only so any write is
    rejected. Prefer the views: v_daily_summary, v_body_comp_daily,
    v_blood_results. Results are capped at 1000 rows (`truncated` flags more).
    Call get_schema() first if unsure of table/column names. On a SQL error the
    message is returned so you can fix the query and retry.
    """
    conn = _ro()
    deadline = time.monotonic() + QUERY_TIMEOUT_S
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cur = conn.execute(sql)  # raises sqlite3.ProgrammingError on >1 statement
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


@mcp.tool()
def get_schema() -> str:
    """Return the full DDL (tables + views) so you can write correct SQL."""
    conn = _ro()
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type IN ('table', 'view') AND sql IS NOT NULL "
            "ORDER BY type DESC, name"
        ).fetchall()
        return ";\n\n".join(r["sql"] for r in rows) + ";"
    finally:
        conn.close()


@mcp.resource("schema://main")
def schema_resource() -> str:
    """The database schema, exposed as an MCP resource."""
    return get_schema()


@mcp.tool()
def daily_summary(start: str, end: str) -> dict:
    """Holistic per-day rows (training volume, kcal, body weight, mood) for the
    inclusive date range [start, end]. Dates are 'YYYY-MM-DD'."""
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
# Write path — typed, validated, parameterized. (read-write connection)
# --------------------------------------------------------------------------
@mcp.tool()
def add_metric(
    name: str,
    value: Optional[float] = None,
    text_value: Optional[str] = None,
    unit: Optional[str] = None,
    observed_at: Optional[str] = None,
    source: str = "manual",
) -> dict:
    """Log a scalar measurement (e.g. alcohol_units, mood, sleep_hours,
    body_weight_kg). Log alcohol_units = 0 on dry days so streaks compute.
    Provide `value` (numeric) or `text_value`. `observed_at` defaults to now.
    Re-logging the same (observed_at, name, source) updates the existing row."""
    if value is None and text_value is None:
        return {"ok": False, "error": "provide value or text_value"}
    observed_at = observed_at or _now()
    warnings: list[str] = []
    conn = _rw()
    try:
        d = conn.execute(
            "SELECT canonical_unit FROM metric_def WHERE name = ?", (name,)
        ).fetchone()
        if d is None:
            warnings.append(f"'{name}' is not defined in metric_def (inserting anyway)")
        elif unit and d["canonical_unit"] and unit != d["canonical_unit"]:
            warnings.append(
                f"unit '{unit}' != canonical '{d['canonical_unit']}' for '{name}'"
            )
        cur = conn.execute(
            """INSERT INTO metric (observed_at, name, value, text_value, unit, source)
               VALUES (:o, :n, :v, :t, :u, :s)
               ON CONFLICT(observed_at, name, source) DO UPDATE SET
                 value = excluded.value,
                 text_value = excluded.text_value,
                 unit = excluded.unit""",
            {"o": observed_at, "n": name, "v": value, "t": text_value,
             "u": unit, "s": source},
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "warnings": warnings}
    finally:
        conn.close()


@mcp.tool()
def add_note(body: str, kind: Optional[str] = None, noted_at: Optional[str] = None) -> dict:
    """Save free text: kind is e.g. 'intention', 'review', 'journal', 'injury'.
    noted_at defaults to now."""
    noted_at = noted_at or _now()
    conn = _rw()
    try:
        cur = conn.execute(
            "INSERT INTO note (noted_at, kind, body) VALUES (?, ?, ?)",
            (noted_at, kind, body),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()


@mcp.tool()
def log_food(
    food_name: str,
    servings: float = 1.0,
    meal: Optional[str] = None,
    consumed_at: Optional[str] = None,
    brand: Optional[str] = None,
    kcal_per_serving: Optional[float] = None,
    protein_g: Optional[float] = None,
    carb_g: Optional[float] = None,
    fat_g: Optional[float] = None,
) -> dict:
    """Record a food consumption event. Resolves the food row (creating it if
    new), then logs the serving. Pass macros only when creating a new food.
    consumed_at defaults to now."""
    consumed_at = consumed_at or _now()
    # Brandless foods store '' and never NULL: SQLite treats NULLs as distinct
    # in a UNIQUE index, so a NULL brand would let unlimited duplicate
    # ('Chicken', NULL) rows past UNIQUE (name, brand). With '' the constraint
    # is real and the lookup below is a plain `=` (Plan 0005 §1).
    brand = brand or ""
    conn = _rw()
    try:
        row = conn.execute(
            "SELECT id FROM food WHERE name = ? AND brand = ?", (food_name, brand)
        ).fetchone()
        created = False
        if row is None:
            cur = conn.execute(
                """INSERT INTO food (name, brand, kcal_per_serving, protein_g, carb_g, fat_g)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (food_name, brand, kcal_per_serving, protein_g, carb_g, fat_g),
            )
            food_id = cur.lastrowid
            created = True
        else:
            food_id = row["id"]
        cur = conn.execute(
            "INSERT INTO food_log (consumed_at, food_id, servings, meal) VALUES (?, ?, ?, ?)",
            (consumed_at, food_id, servings, meal),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "food_id": food_id, "food_created": created}
    finally:
        conn.close()


class SetEntry(BaseModel):
    exercise: str
    reps: Optional[int] = None
    weight_kg: Optional[float] = None
    set_number: Optional[int] = None
    rpe: Optional[float] = None


@mcp.tool()
def log_workout(
    sets: list[SetEntry],
    started_at: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Log a training session in one transaction. `sets` is a list of
    {exercise, reps, weight_kg, set_number?, rpe?}. Weights are kg. Exercises
    not already in the catalog are created automatically. started_at -> now."""
    started_at = started_at or _now()
    created: list[str] = []
    conn = _rw()
    try:
        wid = conn.execute(
            "INSERT INTO workout (started_at, notes) VALUES (?, ?)", (started_at, notes)
        ).lastrowid
        for s in sets:
            ex = conn.execute(
                "SELECT id FROM exercise WHERE name = ?", (s.exercise,)
            ).fetchone()
            if ex is None:
                eid = conn.execute(
                    "INSERT INTO exercise (name) VALUES (?)", (s.exercise,)
                ).lastrowid
                created.append(s.exercise)
            else:
                eid = ex["id"]
            conn.execute(
                """INSERT INTO exercise_set
                   (workout_id, exercise_id, set_number, reps, weight_kg, rpe)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (wid, eid, s.set_number, s.reps, s.weight_kg, s.rpe),
            )
        conn.commit()
        return {
            "ok": True,
            "workout_id": wid,
            "sets_logged": len(sets),
            "exercises_created": created,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run()  # stdio transport
