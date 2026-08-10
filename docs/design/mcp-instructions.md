# Server instructions for the Helf MCP server

Loaded verbatim at startup by `backend/app/mcp/qs_mcp.py` and handed to every
client as FastMCP `instructions`. This file is the source of record; editing it
changes what the model is told.

Everything here is a thing the tool signatures cannot express and that an agent
gets wrong by default. Keep it short — instructions that go unread protect
nothing.

---

You are querying Helf, a personal training and body-composition database. One
person, eight years of data, SQLite.

**Start with the views.** `v_daily_summary` joins training volume, calories,
macros, body weight, mood and notes on one day spine; `daily_summary(start,
end)` is the tool for it. `v_body_comp_daily`, `v_body_comp_series` and
`v_metric_coverage` cover the rest. The raw tables are available through
`query`, but the views encode decisions you would otherwise have to rediscover.

**Masses are pounds.** Stored and displayed, for body weight and for lifted
weight alike. BMI is kg/m² by definition and DEXA reports its masses in kg, so
several metrics are named `*_kg` — the *name* carries the unit, and no row has
a unit column. `metric_def` is the authority; do not infer a unit from context.

**Metric names are a fixed vocabulary.** `metric.name` is a foreign key to
`metric_def`, so an invented name fails rather than creating a new series. Call
`get_metric_names()` to see what exists.

**`v_metric_coverage`, not `metric_def`, tells you what data exists.** A metric
can be defined with nothing behind it — `mood`, `sleep_hours` and
`alcohol_units` currently are. `n_rows = 0` means never recorded, which is a
different fact from a series that has not changed.

**Never mix sources in one series.** Body composition comes from three
instruments — `openscale` (bioimpedance, near-daily), `bodyspec` and `dexafit`
(DEXA, quarterly) — recorded as `observation.source`. They measure the same
quantities and disagree by design: on 2026-03-10 the scale read 6.15 percentage
points of body fat above the DEXA scan taken hours later. Averaging across them,
or differencing them to compute a change, reports the gap between two machines
as a change in a body. Filter to one source, or keep them as separate series.

**A `workouts` row is one logged set, not a session.** A session is the set of
rows sharing a `date`, ordered by `order`. `reps` is an integer — compare and
aggregate it normally, and note there is no AMRAP notation anywhere in the data
model; that intent lives in `comment` as prose.

**`kcal_target` is measured, not assumed.** It is the last DEXA scan's
Katch-McArdle resting rate times an activity multiplier of 1.4, carried forward
from the most recent scan on or before that day. It is NULL before the first
scan. Do not substitute a formula of your own.

**Unshaped observations live in `note` and `document`.** Prose goes in `note`;
raw imported payloads stay whole in `document.raw` and can be mined with
`json_extract`. A named number over time belongs in `metric`, not in either of
them.

**`audit_log` is mutation history, not a data source.** It answers "what
changed and who changed it". It is not evidence about the body or about
training, and it is append-only — nothing can revise it, including you.

**Write tools, when you have them, are attributed to you.** Anything you write
is recorded in `audit_log` with `actor = 'agent'`. Say what you observed rather
than what you inferred, and use `source` to keep the two apart.
