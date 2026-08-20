# 0016 — Supplements leave the food page

**Status**: Implemented 2026-08-20 · no migration

Narrows plan 0011 and plan 0005 §3 at the **read** layer only. The storage
decision they argue for — a supplement is a `food` row with `kind =
'supplement'` — is unchanged and is not to be reopened on the strength of this.

## 1. What was wrong

0005 §3 kept one table on the grounds that the boundary between a food and a
supplement is not somewhere a schema can put it: *"whey is food by any
definition at 120 kcal a scoop"*. That argument is about **storage**, and it is
still right. It was quietly taken to settle the **presentation** too, and there
it is wrong.

What the food page actually showed: a "supplements" group holding four rows
that carry no meal, no macros and no calories, sitting under breakfast, lunch
and dinner and moving no total on the page. They are not food that was eaten,
they are doses that were swallowed, and the day's entry count counted them —
so a day on which nothing was eaten but the morning stack was taken read as a
logged food day with three entries.

The boundary that could not be put in the schema turns out to be one the user
draws by hand, and says so: **anything carrying calories gets logged as
`kind='food'`**. Whey goes in as food. What is left under `kind='supplement'`
is by construction the zero-calorie half, and it has no business on a page
about intake.

## 2. Why the tables did not move

The obvious reading of "separate them" is `supplement` + `supplement_log`
tables. Rejected, and the reason is worth keeping:

- `stack_item.food_id` would have to be repointed, `v_daily_summary` rewritten
  and every historical `food_log` row for a supplement moved across — a
  migration over live data to change what a page lists.
- `POST /api/stacks/{id}/log` writing `food_log` rows is what makes
  `taken_today` derivable from the log rather than from the button (0011). A
  second log table means a second derivation, and two places for "was this
  taken today" to disagree.
- The boundary would then be enforced by the schema, at exactly the point where
  0005 §3 showed there is no defensible place to put it. A product that turns
  out to have calories would need a migration rather than an edit.

So: one table, two reads. `kind` was already the discriminator and already
filtered the catalog typeahead (0011 §4). It now filters the log reads too.

## 3. What changed

**Reads narrowed to meals.**

- `GET /api/food/day` returns `kind='food'` entries only. It is the food page's
  read and nothing else uses it.
- `totals.entries` counts meals, in both `DAILY_TOTALS_SQL` and
  `ONE_DAY_TOTALS_SQL`, via a shared `_MEAL_ENTRIES` subquery so the two cannot
  drift apart.
- `GET /api/food/log/summary` skips a day whose only rows are supplements. Same
  rule as before — days with nothing logged are absent rather than zero — with
  "logged" now meaning "eaten".

**Reads added.**

- `GET /api/food/log?date=&kind=` — the whole log for a date, optionally one
  kind. Unfiltered it still returns both, because it is the log for a date.
- `GET /api/food/log/recent?kind=&limit=` — entries across days, newest first.

**The supplements page grew a log.** `Recent doses`, at the bottom of
`/supplements`, modelled on the body page's measurement log: flat, newest
first, 50 rows, two-tap delete. Deliberately **not** date-scoped — the mistake
it exists to catch is a dose filed against the wrong day, which is precisely
what a per-day view cannot show. Deleting a row invalidates `["stacks"]` as
well as `["food"]`, because `taken_today` is derived from exactly those rows
and a stale badge is how a stack gets taken twice.

**Nothing about adherence moved.** `supplements_taken` still counts them,
`v_daily_summary` is untouched, `stack` and `stack_item` are untouched, and the
catalog still holds both kinds behind `kind`.

## 4. The sharp edge

**A supplement carrying real macros still counts toward the day's intake, while
its entry is listed on the supplements page rather than under a meal.** The
totals come from `v_daily_summary`, which sums `food_log` without regard to
kind, and that was left alone on purpose: filtering it would mean a calorie the
database holds and no page reports, which is worse than a calorie whose entry
is one tab away.

This is only reachable by logging a calorie-bearing product as
`kind='supplement'`, which is the thing §1 says will not be done. Two guards
against discovering it the hard way:

- The supplements log prints `· N kcal` on any dose that has calories, so the
  calories are visible where the dose is.
- `test_editing_a_supplement_rewrites_past_totals` pins the behaviour and its
  docstring says which way to resolve it: log the product as food.

## 5. The stale-cache guard

The service worker serves `/api` network-first, so a cached `/day` from before
this change can still carry supplements. Without a client-side guard they would
fall into `unsorted` and read as unfiled food — a worse failure than the one
being fixed, because "unsorted" is an invitation to file it under a meal.
`Food.tsx` therefore drops `kind === 'supplement'` from the grouping as well.
Belt and braces on purpose; the server-side filter is the real one.

## 6. What this does not do

- No table split (§2), and none is planned.
- No change to how supplements are created or edited — the catalog editor,
  the stack editor and `PUT /api/food/{id}`'s retroactive warning are as 0011
  left them.
- No way to move an existing supplement row to `kind='food'` from the UI. The
  editor does not offer `kind`, so reclassifying whey today means creating the
  food and re-logging it. Worth doing if it comes up twice; not done on
  spec.
