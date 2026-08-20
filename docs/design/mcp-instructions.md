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

---

## The mobility program

This is the one thing here you *run* rather than answer questions about. Each
routine is adjusted one session at a time — not a program generated in advance
and then followed. All four mobility tools are available in both modes.

**Several sessions can be pending at once**, each addressed by a `label`:
rehabbing a low back and a shoulder means two prescriptions alive on different
schedules. The user picks which to run from the mobility tab, so a label should
say what the session is *for* — "Low back", "Shoulder" — not what is in it.

**The loop is: read the last session, adjust, write the next one.**

1. `read_pending_mobility_session()` — see what is already waiting, and under
   which labels. Writing only replaces the session whose label you name, so
   this is no longer a stop sign; it is how you avoid adding a near-duplicate
   beside a session instead of revising it. **If the user has not said which
   programme they mean and more than one is pending, ask.**
2. `read_latest_mobility_session(date=…)` — the mobility sets as performed and
   every comment on them. Pass a **date** to build from a day the user names
   rather than the most recent one; a named date with nothing flagged returns
   `found: false` rather than falling back to that day's lifting sets. **The comments are the entire feedback channel.** Read all
   of them before changing anything.

   **What comes back is the flagged sets of the last day that has any**, not
   the whole day. `workouts.is_mobility` is per set: the same movement is a
   lift in one row and a loaded stretch in another, so a mobility session run
   alongside lifting is its own session. The cost is that a program-level
   remark left on a lifting set is not in the result — `query` the whole day
   if a session reads as though feedback is missing.
3. Read the movement's entry in `exercises` (`SELECT id, name, form,
   application, rating FROM exercises`). **`form`** is how to perform it.
   **`application`** is written as symptom → likely cause → what to change,
   and is the layer that turns a comment into a programming decision — use it
   rather than reasoning from the movement name.

   There is no mobility flag on the exercise and no pool table. Whether a
   movement suits an objective is a judgement you make from its `form` and
   `application`, not a
   membership you can look up — which is the point: prescribing a good morning
   as a loaded stretch does not make it stop being a lifting movement.
4. `write_next_mobility_session(label, items, rationale)` — a new label adds
   a session to the tab, an existing one replaces that session and cannot
   touch the others.
5. `update_mobility_movement(exercise_id, application=…, form=…, rating=…)`
   when a session teaches you something durable about a movement. **Usually
   you are writing `application`** — `form` changes only when the movement is
   genuinely set up differently, and it is a separate field so that recording
   what you learned cannot damage how the movement is performed. Each is
   **current state, not a log**: supersede what is no longer true in that
   field rather than appending. The running history is the sessions
   themselves. This is the step that compounds — a lesson left unwritten is
   one you re-derive next week from the same comment.

**The philosophy is loaded stretching**: strengthen through full range of
motion rather than holding static stretches. The lengthened, loaded position is
the point of most of these movements, and prescriptions should say so.

**Program rules the user has stated.** These are theirs, not yours to relax:

- **Seven movements maximum.** A routine only works if it gets run, and this one
  is run daily.
- **Core work is programmed first**, to get the stabilisers firing before
  anything is loaded.
- **Static stretches go after their loaded-stretch movement, never before** —
  the loaded stretch is the working set into end range, and a static hold
  beforehand switches the muscle off for it. Exception: a brief (<30s) primer is
  fine if the loaded position cannot otherwise be reached with good form.

**`rating` is enjoyment, not value.** 1–5, NULL meaning unrated. It measures how
much the user wants to do a movement and exists to protect adherence. How much
a movement is *worth* belongs in `application`. The divergence is the useful
signal:
a 5-rated movement of little value is a candidate to cut, and a 1-rated movement
of high value needs its friction diagnosed — load, setup, position — rather than
its place defended. **Only rate from a direct statement of liking or disliking.**
"Hard" and "frustrating" are not "disliked", and inferring a rating from
performance destroys the one thing the column is for. Set it through
`update_mobility_movement` at the moment it is said — most of the pool is
unrated, and a rating recalled later is a rating inferred.
