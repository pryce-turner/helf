# Plan 0003: Units and metrics

**Status:** Implemented (2026-08-08) — through revision `e96bd4b90873`; see §9, §10
**Prerequisites:** Plan 0002 (Alembic + pragmas) — satisfied
**Related:** ADR-0003

| Rev | Revision id | State |
|-----|-------------|-------|
| `a1` | `a70937427207` | Done — body comp converted to lbs |
| `a2` | `4de188592eb5` | Done — `metric` + `metric_def`, seeded |
| `a3` | `de63ed0bc62d` | Done — 600 rows backfilled |
| `a4` | `f5abbd14fa00` | Done — four views |
| — | `7bba3fe3ee35` | Done — `observation` table; **unplanned**, see §9 |
| `a5` | `e96bd4b90873` | Done — `weight_unit` dropped, see §10 |

Reads are served from the views as of §9. `body_composition` is write-only, and
retiring it is a separate plan.

> ## `a2`–`a4` implementation notes
>
> **600 rows backfilled**, 150 each for `body_weight_lb`, `body_fat_pct`,
> `muscle_pct` and `water_pct`. The migration verifies itself: per-metric row
> counts *and* sums are compared against the source columns, because all four
> columns have identical counts and a count check alone would not catch a column
> being copied into the wrong metric name.
>
> **`document_id` is omitted from `metric`.** The design includes it, but
> `document` does not exist until Plan 0005, and with `foreign_keys=ON` a
> reference to a missing table fails at INSERT rather than at CREATE. Add it when
> its target exists.
>
> **The daily view averages; it does not `MAX`.** This is a deliberate deviation
> from §4. The history weighs in more than once on **30 days**, and **13 of those
> have genuinely different readings, spanning up to 4.06 lb**. `MAX` reports the
> heaviest reading of each such day, biasing every daily summary upward.
> Repeated readings from one instrument within one day are repeated measures of
> the same quantity, so averaging is sound — averaging *across sources* is not,
> which is exactly what the `source` grouping prevents. The view also exposes
> `n_measurements` so a collapsed day is visible rather than implied.
>
> **A per-measurement view was added** (`v_body_comp_measurements`), which §4
> suggested and which turns out to be necessary: it reproduces
> `body_composition` **exactly** — 150 rows, zero mismatches across all four
> populated columns. The daily view yields 107 rows for the same data. List and
> detail endpoints must read the per-measurement view; only summaries may read
> the daily one.
>
> **`muscle_mass` in the view is fed from `muscle_pct`.** §4's draft mapped it
> from `muscle_mass_lb`, a metric nothing seeds — the column would have been
> silently NULL on every row. The view preserves the legacy column *name* while
> the metric carries the honest one.
>
> **A test regression worth recording.** `test_database.py` built its
> "pre-Alembic" fixture with `create_all()`, which silently became *head* rather
> than *baseline* the moment `metric` was added, so the stamp-then-upgrade test
> broke. It now migrates to the baseline revision and drops `alembic_version`,
> which is what a pre-Alembic database actually is — and it additionally asserts
> the database is carried *forward* to head, which the original never checked.
>
> Verified: 155 tests pass; `alembic check` reports no drift (views do not
> confuse autogenerate); FK, UNIQUE and CHECK constraints all reject as intended;
> downgrade removes every table and view and leaves `body_composition` untouched
> at 150 rows / `sum(weight)` 29,232.74; all API endpoints still 200.
>
> ## Dual-write (2026-08-08)
>
> **The mirror lives in `BodyCompositionRepository.create`, not in
> `mqtt_service`.** §4a listed it as an MQTT change, but the manual POST endpoint
> is a second writer — putting it in the service would have left every manually
> entered measurement missing from `metric`. MQTT passes `source='openscale'` to
> continue the backfilled series; the API defaults to `'manual'`.
>
> **The mirror commits in its own transaction, after the primary write, and
> swallows its own failures.** This looks wrong and is deliberate. The two
> failure modes are not symmetric: a lost scale reading is unrecoverable because
> openScale does not retransmit, while a divergence between the tables is fixed
> by re-running the backfill. So the mirror is never permitted to roll back the
> measurement. Failures are logged at exception level.
>
> **`observed_at` formatting is load-bearing.** It is TEXT, and `a3` copied
> `body_composition.timestamp` verbatim, so new rows must render byte-identically
> or they silently fork the series and `UNIQUE(observed_at, name, source)` stops
> deduplicating. Verified end-to-end against a copy of production.
>
> **Two stale `kg` defaults fixed**: `BodyCompositionBase.weight_unit` and the
> repository's `or "kg"` fallback. A manual POST omitting the unit would have
> stored `kg` into a table that is now entirely pounds.
>
> **`metric_def` had to be seeded in the test fixtures.** They build schema with
> `create_all()`, which creates the table empty — so every mirrored write failed
> its foreign key. Because the mirror is deliberately non-fatal, the suite would
> have stayed green while the dual write did nothing.
>
> ## Blocker found: the read path cannot move as designed
>
> §4 asserts "**The API contract does not change** — `v_body_comp_daily` pivots
> the tall rows back into the wide shape the repository already returns." That is
> not true, and it blocks the switch.
>
> The response model (`models/body_composition.py`) requires three things the
> views cannot supply:
>
> | Field | Why the view has none |
> |---|---|
> | `id` (serialised as `doc_id`) | A measurement is **four `metric` rows**. There is no single row to take an id from |
> | `created_at` | Ingestion time is a property of the measurement, not of a metric |
> | `weight_unit` | Implied by the metric *name* (`body_weight_lb`), not stored |
>
> `doc_id` is load-bearing, not decorative: `DELETE /api/body-composition/{id}`
> takes it, and the frontend's delete mutation filters the cache on it
> (`useBodyComposition.ts:113`). Serving reads from a view would break deletion.
>
> **The tall model has no concept of a measurement** — only of individual
> observations that happen to share an `observed_at`. The likely fix is an
> `observation` table (`id`, `observed_at`, `source`, `created_at`) that `metric`
> rows reference, making `doc_id` a real identity again and giving `created_at` a
> home. That is a schema design decision, not a mechanical port, so it is not
> taken here.
>
> **Partial migration was considered and rejected.** `trends` needs no identity
> and could move today, but then one page would read two sources: a failed mirror
> would show gaps in the chart while the list below it showed the row. One
> consistent source beats a half-migrated one.
>
> **Resolved by the `observation` refactor (`7bba3fe3ee35`).** See below.
>
> ## Mirror reconciliation (2026-08-08)
>
> Since the mirror is deliberately non-fatal, the two tables *can* drift, and
> nothing would say so. `BodyCompositionRepository.reconcile_mirror()` compares
> them and reports missing, mismatched and orphaned rows with a bounded sample.
> `body_composition` is authoritative, so every difference is expressed as
> something the mirror lacks.
>
> Against production: **600 expected, 600 mirrored, zero drift.** Each failure
> mode is provoked in tests rather than assumed — a check that can only report
> success is worthless.

> ## `a1` implementation notes
>
> Body composition is in pounds. 150 rows converted; `sum(weight)` went
> 13,259.75 → 29,232.74, matching `× 2.20462262184878` exactly, and the
> downgrade restores 13,259.75 precisely (verified on a copy, both directions).
> Range is now 187.2–203.4 lbs, mean 194.9.
>
> **Percentages were left alone, as required:** `sum(body_fat_pct)` 3,689.1 and
> `sum(muscle_mass)` 5,809.0 are byte-identical before and after. `workouts`
> remains `lbs | 9292`, untouched.
>
> **The migration self-checks.** A double-applied conversion leaves values that
> are still numeric, still positive, and still ordered the same way — nothing
> downstream would complain. `upgrade()` therefore asserts the result lands in a
> plausible human range (50–700 lbs) and refuses to commit otherwise.
>
> **`a1` had to ship with the frontend change, not before it.** Converting stored
> values while `BodyComposition.tsx` still called `kgToLbs` would have doubled
> every displayed weight. Both are in the same commit.
>
> **The muscle-mass bug is fixed, and it was in three places, not two.** Besides
> the stat card (`:156`) and the chart tooltip (`:362`), the muscle chart's
> y-axis had its own inline `(v * 2.20462)` tick formatter — a percentage scaled
> as a mass on the axis as well as in the readout. The card and chart are now
> labelled "Muscle" / "Muscle %" with a `%` unit, since displaying it correctly
> means saying what it is.
>
> **Correction found while verifying: `water_pct` is populated** in all 150 rows.
> See §1. This changes `a3`'s expected row count from 450 to 600.
>
> Not done here: `a2`–`a5` (the tall `metric` table, the pivot view, dropping
> `weight_unit`), and §4a's two-source chart, which needs Plan 0008's BodySpec
> rows to exist first.
**Risk:** Low. Training data is untouched; body composition is one column across
150 rows.

Two changes: settle mass on pounds, and convert body composition from a wide
table to tall `metric` rows.

> **Revised twice.** An earlier draft converted all training weight to kilograms
> and was the highest-risk item in the roadmap; ADR-0003 reversed that.
> **`workouts` and `upcoming_workouts` are not touched at all** — all 9,292 rows
> are already lbs. Risk R1 is retired from `plans/0001-integration-roadmap.md`.
>
> **openScale is live** and both former blockers are resolved empirically
> against the production copy at `data/helf.db`, now corroborated by the first
> BodySpec DEXA scan. §1 and §2 record the evidence.

---

## 1. What openScale sends — **RESOLVED: kilograms**

Measured against the production database (`data/helf.db`, 150 rows,
2025-09-26 → 2026-05-19):

| | value |
|---|---|
| `weight` range | 84.9 – 92.2 |
| `weight` mean | 88.4 |

**These are kilograms.** 88.4 kg ≈ 195 lb, consistent with a lifter whose
working squat is 335 lb. Read as pounds it would be 40 kg, which is not an
adult. The hard-coded `weight_unit="kg"` at `mqtt_service.py:102` is therefore
*correct*, and the frontend's `kgToLbs` is also correct — the two are not
cancelling errors.

**Path A applies:** body composition converts kg → lbs (ADR-0003).

### What the scale actually populates

Only four of the nine columns are ever written:

| Column | Non-null of 150 |
|---|---|
| `weight` | 150 |
| `muscle_mass` | 150 |
| `body_fat_pct` | 150 |
| `water_pct` | 150 |
| `bmi`, `bone_mass`, `visceral_fat`, `metabolic_age`, `protein_pct` | **0** |

> **Corrected 2026-08-08.** An earlier draft listed `water_pct` among the empty
> columns. It is populated in all 150 rows, ranging 48.59–51.90% (mean 50.28) —
> a plausible total-body-water percentage. The seed list and backfill below are
> four metrics, not three, and the expected backfill row count is **600**, not
> 450. Found when the `/latest` endpoint returned `water_pct: 50.99` after the
> `a1` conversion.

Five columns have never held a value. This is an argument for the tall table in
its own right — the wide schema reserves storage and cognitive space for
measurements that do not exist. It also means the openScale backfill produces
four metric names, not nine, and BodySpec is the only source for bone and
visceral measures.

*(An earlier draft cited a BMI of 24.6 as corroboration. `bmi` is NULL in every
row; 24.6 is the mean `body_fat_pct`. The kg conclusion is unaffected — it rests
on plausibility of the weight range itself.)*

### Corroborated by the DEXA scan

`mqtt_service.py:80,102` still stores `payload.get("weight")` verbatim under a
hard-coded `weight_unit="kg"`, never reading a unit from the payload. The label
was an assumption — it is now a verified one, from a second direction:

| Source | Weight | Date |
|---|---|---|
| BodySpec DEXA (`total_mass_kg`) | **87.67 kg** | 2026-03-10 |
| openScale range | 84.9 – 92.2 kg | 2025-09 → 2026-05 |

The DEXA measurement, whose unit is unambiguous in the API, sits squarely inside
the scale's range. Two independent instruments agreeing on magnitude settles the
unit question beyond the plausibility argument above.

### The conversion

**`weight` is the only column that converts.** Per §1 and §2:

```sql
UPDATE body_composition
SET weight      = weight * 2.2046226218,
    weight_unit = 'lbs'
WHERE weight_unit = 'kg';
```

- `muscle_mass` — a **percentage** (§2). Not converted.
- `body_fat_pct` — a percentage. Not converted.
- `water_pct` — a percentage, populated in all 150 rows. Not converted.
- `bone_mass`, `bmi`, `protein_pct`, `visceral_fat`, `metabolic_age` — all NULL
  in every row (§1). Nothing to convert.

Converting `muscle_mass` would be the bug the earlier draft nearly introduced by
treating it as one of "the three mass columns".

The `WHERE weight_unit = 'kg'` guard plus Alembic revision tracking makes a
double-run non-destructive. Scope is one column across 150 rows — small next to
9,292 untouched workout rows.

Going forward, `mqtt_service.py` converts on ingest and
`frontend/src/pages/BodyComposition.tsx:102` loses `kgToLbs` entirely.

---

## 2. `muscle_mass` — **RESOLVED: it is a percentage, and there is a live bug**

`db/models.py:117` names it `muscle_mass` and `body_comp_repo.py:25` serialises
it as a mass, but `mqtt_service.py:120` logs it as `%`. Magnitude alone can't
settle it — 38.7 is plausible both as kg of muscle and as percent of body mass.

**Correlation settles it.** Against `weight`, across all 150 rows:

```
pearson_r = -0.985
```

| | weight | muscle_mass |
|---|---|---|
| Heaviest day | 92.2 | 37.8 |
| Lightest day | 84.9 | 39.6 |

A muscle *mass* in kg correlates **positively** with body weight — gaining
weight does not reduce your kilograms of muscle. A near-perfect **inverse**
correlation is the signature of a fraction: as fat mass rises, muscle as a
proportion of total falls. Combined with a mean `body_fat_pct` of 24.6% and mean
`muscle_mass` of 38.7, these are internally consistent bioimpedance
*percentages*.

### The live bug

`frontend/src/pages/BodyComposition.tsx:156` passes this value through
`kgToLbs`:

```
39.1 (percent) × 2.20462 = 86.2  → displayed as "86.2 lbs muscle mass"
```

The result is dimensionally meaningless but lands in exactly the range a real
muscle mass would occupy for an ~195 lb man, which is why it has never looked
wrong. **This is a present-day defect, independent of any migration**, and it is
worth fixing on its own.

### Consequences

- `metric_def` seeds **`muscle_pct`**, not `muscle_mass_lb`.
- The column is **not** converted during the units migration — percentages are
  not masses (ADR-0003 scope limit).
- The `muscle_mass` column name is wrong and should be treated as legacy. The
  tall table is the opportunity to retire the misnomer rather than carry it.
- DEXA's `lean_mass_kg` is a genuine mass and a different quantity. Do not plot
  them on one axis or treat one as a refinement of the other.

### Cross-checked against DEXA

The 2026-03-10 scan reports `lean_mass_kg` **69.61** on a total mass of 87.67 kg
— 79% of body mass. openScale's `muscle_mass` reads ~38.7 over the same period.
Those cannot both be masses of the same tissue; the scale value is a percentage
of a different quantity entirely (bioimpedance "muscle %" excludes bone and is
computed on a different model).

Further confirmation that they are separate quantities, not two estimates of one.

---

## 3. `metric` and `metric_def`

### Schema

`reference/qs_mcp.py:167` upserts with
`ON CONFLICT(observed_at, name, source)`, so that triple **must** carry a unique
constraint or the write tool raises at runtime.

```sql
CREATE TABLE metric_def (
    name            TEXT PRIMARY KEY,
    canonical_unit  TEXT,
    description     TEXT,
    ref_low         REAL,
    ref_high        REAL
);

CREATE TABLE metric (
    id           INTEGER PRIMARY KEY,
    observed_at  TEXT NOT NULL,
    date         TEXT GENERATED ALWAYS AS (substr(observed_at, 1, 10)) STORED,
    name         TEXT NOT NULL REFERENCES metric_def(name),
    value        REAL,
    text_value   TEXT,
    unit         TEXT,
    source       TEXT NOT NULL DEFAULT 'manual',
    document_id  INTEGER REFERENCES document(id),
    UNIQUE (observed_at, name, source),
    CHECK (value IS NOT NULL OR text_value IS NOT NULL)
);
CREATE INDEX ix_metric_date_name ON metric(date, name);
```

- `date` is `STORED`, not `VIRTUAL`, so it can be indexed. It is the design
  doc's universal join key.
- `name REFERENCES metric_def(name)` puts validation in the schema, where both
  writers hit it (ADR-0002). `add_metric` currently only *warns* on an unknown
  name (`qs_mcp.py:162`) and inserts anyway; with this FK the insert fails, so
  **`qs_mcp.py` must be updated to return a useful error** (Plan 0006, gap G3).

### Seed `metric_def`

Unit-suffixed per ADR-0003, in lbs:

| name | canonical_unit | from |
|------|---------------|------|
| `body_weight_lb` | lb | `body_composition.weight`, converted |
| `body_fat_pct` | % | unchanged |
| `muscle_pct` | % | **percentage, per §2** — not a mass |
| `water_pct` | % | unchanged |

Only these four. The other five wide columns are NULL in all 150 rows (§1), so
they seed no metrics from openScale — `bone_mass_lb`, `bmi`, `visceral_fat`,
`metabolic_age`, `protein_pct` are defined only if and when a source actually
produces them. BodySpec supplies genuine bone and visceral measures (Plan 0008).

### Reserved metrics — declared now, populated later

The coaching *loop* is dropped, but these three are seeded anyway so the model
has a home for them when development resumes:

| name | canonical_unit | notes |
|------|---------------|-------|
| `alcohol_units` | units | Log `0` on dry days so streaks compute from data rather than absence |
| `mood` | 1–10 | Set `ref_low`/`ref_high` to 1/10 |
| `sleep_hours` | hours | |

Declaring them costs nothing — `metric_def` is a vocabulary, not storage — and it
fixes the naming and units *before* anything writes them, which is the cheapest
moment to get that right.

**The false-affordance problem is real, and solved by a view rather than by
withholding definitions.** A `metric_def` row with no rows behind it will lead an
agent to write queries against an empty series and report "no change" instead of
"no data". So publish coverage as a first-class object:

```sql
CREATE VIEW v_metric_coverage AS
SELECT d.name,
       d.canonical_unit,
       d.description,
       count(m.id)  AS n_rows,
       min(m.date)  AS first_seen,
       max(m.date)  AS last_seen
FROM metric_def d
LEFT JOIN metric m ON m.name = d.name
GROUP BY d.name, d.canonical_unit, d.description;
```

`n_rows = 0` says "defined, never recorded" unambiguously. The MCP instructions
(Plan 0006 §5) point at this view rather than at `metric_def`, so the agent sees
what exists before querying it. This is self-maintaining — no flag to keep in
sync as metrics start and stop being collected.

**BodySpec adds more** — `fat_mass_kg`, `lean_mass_kg`, `vat_mass_kg`,
`bone_mineral_density`, `rmr_kcal_per_day`, `height_cm`, `android_gynoid_ratio`.
Those stay in their source units per ADR-0003's scope limit and are seeded by
`plans/0008-bodyspec-integration.md` §5, not here. Note that `body_fat_pct` will
then have two sources of differing accuracy — the `UNIQUE (observed_at, name,
source)` constraint keeps them as separate rows, and consumers must not silently
mix a bioimpedance estimate with a DEXA measurement.

### Backfill

Four inserts, one per populated column:

```sql
INSERT INTO metric (observed_at, name, value, unit, source)
SELECT timestamp, 'body_weight_lb', weight, 'lb', 'openscale'
FROM body_composition WHERE weight IS NOT NULL;

INSERT INTO metric (observed_at, name, value, unit, source)
SELECT timestamp, 'body_fat_pct', body_fat_pct, '%', 'openscale'
FROM body_composition WHERE body_fat_pct IS NOT NULL;

INSERT INTO metric (observed_at, name, value, unit, source)
SELECT timestamp, 'muscle_pct', muscle_mass, '%', 'openscale'
FROM body_composition WHERE muscle_mass IS NOT NULL;

INSERT INTO metric (observed_at, name, value, unit, source)
SELECT timestamp, 'water_pct', water_pct, '%', 'openscale'
FROM body_composition WHERE water_pct IS NOT NULL;
```

Note the third: source column `muscle_mass` → metric name `muscle_pct`. The
rename happens here, and this is the only place the misnomer needs handling.

`source = 'openscale'` makes the step reversible with
`DELETE FROM metric WHERE source = 'openscale'`.

**Expected row count: exactly 600** (150 × 4). Verify:

```sql
SELECT count(*) FROM metric WHERE source = 'openscale';   -- 600
SELECT name, count(*) FROM metric WHERE source = 'openscale' GROUP BY name;
-- body_fat_pct 150 | body_weight_lb 150 | muscle_pct 150 | water_pct 150
```

---

## 4. Keeping the existing API working

`body_composition` backs a real page (`frontend/src/pages/BodyComposition.tsx`,
461 lines) through a fixed response shape — `BodyCompositionBase` in
`backend/app/models/body_composition.py`, built by `_serialize` at
`backend/app/repositories/body_comp_repo.py:17-33`.

**The API contract does not change.** `v_body_comp_daily` pivots the tall rows
back into the wide shape the repository already returns.

> **Source-collapse defect — fixed below.** An earlier draft grouped by `date`
> alone. With openScale and BodySpec both writing `body_weight_lb` and
> `body_fat_pct`, that silently merges a bioimpedance estimate and a DEXA
> measurement into one value via `MAX()` — picking the larger, arbitrarily, on
> any day carrying both. **`source` is now part of the grouping key.** See §4a
> for the two-series design.

```sql
CREATE VIEW v_body_comp_daily AS
SELECT
    date,
    source,
    MAX(CASE WHEN name = 'body_weight_lb' THEN value END) AS weight,
    MAX(CASE WHEN name = 'body_fat_pct'   THEN value END) AS body_fat_pct,
    MAX(CASE WHEN name = 'muscle_mass_lb' THEN value END) AS muscle_mass,
    MAX(CASE WHEN name = 'bmi'            THEN value END) AS bmi,
    MAX(CASE WHEN name = 'water_pct'      THEN value END) AS water_pct,
    MAX(CASE WHEN name = 'bone_mass_lb'   THEN value END) AS bone_mass,
    MAX(CASE WHEN name = 'visceral_fat'   THEN value END) AS visceral_fat,
    MAX(CASE WHEN name = 'metabolic_age'  THEN value END) AS metabolic_age,
    MAX(CASE WHEN name = 'protein_pct'    THEN value END) AS protein_pct
FROM metric
GROUP BY date, source;
```

Column aliases are deliberate — `body_weight_lb` → `weight`, `muscle_mass_lb` →
`muscle_mass` — matching `_serialize` exactly so no Python changes.

Adding `source` to the grouping means the existing endpoints must either filter
(`WHERE source = 'openscale'`, preserving today's behaviour exactly) or pass the
column through. **Filter by default** — the current page expects one row per day,
and returning two would silently double every list.

**Grain change:** `body_composition` is per-*measurement* (`timestamp` is unique,
`db/models.py:112`); this view is per-*day*. Multiple weigh-ins in one day
collapse to one row, with `MAX` picking arbitrarily among same-named values. If
multiple daily weigh-ins matter, keep a per-timestamp view for detail endpoints
and use the daily view only for `v_daily_summary`.

**Retire the old table last.** Keep `body_composition` in place and dual-written
until the view-backed path is verified against real numbers. Dropping it belongs
in a later plan.

---

## 4a. Two sources, one chart

**Requirement:** openScale and BodySpec are complementary — openScale less
accurate but far more frequent, BodySpec the reference standard but quarterly.
They must remain categorically separate while appearing on the same graph.

Both are live. openScale contributes 150 measurements across roughly eight
months; BodySpec will contribute a handful of high-accuracy points.

**Only `body_fat_pct` and `body_weight_lb` are genuinely dual-source.**
`muscle_pct` (openScale, a percentage) and `lean_mass_kg` (BodySpec, a mass) are
*different quantities* despite describing the same tissue — they share no axis
and neither refines the other.

The tall `metric` table already supports this — `UNIQUE (observed_at, name,
source)` keeps them as distinct rows rather than overwriting. What needs care is
everything downstream.

### The three ways this goes wrong

1. **Collapsing them in a view.** Fixed above by grouping on `source`.
2. **Averaging across sources.** A moving average over mixed rows produces a
   number that describes neither instrument.
   `backend/app/utils/calculations.py:26` `calculate_moving_average` is
   source-blind; it must only ever be handed a single-source series.
3. **Interpolating the sparse one.** Drawing a line between two DEXA scans
   asserts a body-fat trajectory across three months that was never measured.

Point 3 is the one that determines the chart's form.

### Serving both series

```sql
CREATE VIEW v_body_comp_series AS
SELECT date, source, name, value
FROM metric
WHERE name IN ('body_weight_lb','body_fat_pct','lean_mass_kg','ffm_kg')
ORDER BY date;
```

Endpoint returns them already split, so the client never has to group:

```
GET /api/body-composition/series?metric=body_fat_pct&start=&end=
-> { "openscale": [{date, value}, ...], "bodyspec": [{date, value}, ...] }
```

### Encoding

Both series measure the same quantity in the same unit, so they share **one
y-axis**. This is explicitly *not* a dual-axis chart — two y-scales would make
the offset between instruments impossible to read, which is the single most
useful thing the combined chart shows.

| Series | Mark | Why |
|--------|------|-----|
| openScale | 2px line, no point markers,  `#3b82f6` blue | Dense and continuous; the line carries *shape*, which is what a precise-but-inaccurate instrument is good for |
| openScale (smoothed) | 2px line, 7-day moving average, same hue | The raw daily series is mostly water-weight noise |
| BodySpec | **Scatter only — ≥8px dots, no connecting line**, `#16a34a` green | Four points a year. A connecting line would fabricate the months between them |

Recharts: a `ComposedChart` with `<Line>` for openScale (`dot={false}`) and
`<Scatter>` for BodySpec. Give the DEXA dots a 2px surface-coloured ring so they
stay legible where they land on the line.

The visual weight is deliberately inverted against the data volume — the sparse
series is the more prominent mark, because it's the accurate one.

### Colors — validated, not chosen by eye

**openScale `#3b82f6`** (`--chart-2`, blue) · **BodySpec `#16a34a`** (green,
one step darker than `--chart-4`):

```
[PASS] Lightness band      all 2 inside L 0.48–0.67
[PASS] Chroma floor        all 2 >= 0.1
[PASS] CVD separation      ΔE 27.5 (deutan)                   [target ≥ 8]
[PASS] Normal-vision floor ΔE 29.4
[PASS] Contrast vs surface all 2 >= 3:1
```

**Orange is unavailable, despite being the obvious "important series" colour.**
Merge `1a27a0b` made the brand accent orange:

| Token | Value |
|---|---|
| `--accent` | `#f97316` — identical to `--chart-1` |
| `--accent-hover` | `#ea580c` |

An earlier draft picked `#ea580c` for the DEXA series. That is *exactly*
`--accent-hover` — a data series would have been wearing an interaction-state
token, so a static mark would read as a hovered control. And `--chart-1` is now
byte-identical to `--accent`, which makes any series using it read as
"selected" rather than as an identity.

Green sidesteps both. `--chart-4` (`#22c55e`) fails the lightness band on the
`#141416` surface (L 0.723); `#16a34a` is the same hue one step darker and
passes.

Tritan separation is 5.4, below the ΔE 8 target. That is acceptable here
*only* because mark shape already carries identity — a continuous line versus
discrete dots — which is the secondary encoding the floor band requires. It
would not be acceptable for two line series.

A legend is required — two series means identity must never rest on colour
alone. Mark shape (line vs dots) is already doing that work, which is what makes
this pairing robust.

### Pre-existing palette defect

Validating the full five-colour palette against the dark surface surfaced a
problem unrelated to this plan:

```
[FAIL] CVD separation  worst adjacent #a855f7 ↔ #3b82f6  ΔE 0.9 (deutan)
[FAIL] Lightness band  #f97316 (0.705), #22c55e (0.723), #eab308 (0.795)
```

`--chart-2` (blue) and `--chart-3` (purple) are **ΔE 0.9 under deuteranopia** —
indistinguishable to red-green colourblind viewers, who are ~8% of men. Any
existing chart using three or more series is affected, including Progression.
Out of scope here, but it should be fixed in the design system. Tracked in
`TODO.md`.

### Do not average them — calibrate instead

Tempting and wrong: averaging the two, or "correcting" openScale to match DEXA.

The useful relationship is that bioimpedance is typically **precise but not
accurate** — repeatable, with a consistent offset. So the openScale curve's
*shape* is informative even when its *level* is off by several points of body
fat. Each DEXA scan is an opportunity to measure that offset:

```sql
-- openScale bias against the DEXA reference, per scan date
SELECT b.date,
       b.value AS dexa_pct,
       o.value AS scale_pct,
       o.value - b.value AS scale_bias
FROM metric b
JOIN metric o ON o.date = b.date AND o.name = b.name AND o.source = 'openscale'
WHERE b.name = 'body_fat_pct' AND b.source = 'bodyspec';
```

If that bias is stable across scans, it's a real calibration constant and worth
surfacing. If it drifts, the scale isn't trustworthy for anything but direction.
Either way this is a **derived, displayed** quantity — never write a corrected
value back into `metric` as if it were measured.

### MQTT writer

`mqtt_service.py` needs three changes, all in `_on_message`:

1. Convert kg→lb on ingest if Path A (openScale keeps sending its native unit
   forever — this is permanent, not a one-off).
2. Stop hard-coding the unit label at line 102; derive it or assert it explicitly
   with a comment naming openScale's contract.
3. Write `metric` rows in addition to the `BodyComposition` row during the
   dual-write window.

This is the one place worth accepting temporary duplication: losing scale data
to a migration bug is unrecoverable, because the scale does not retransmit.

---

## 5. Frontend

Simpler than the kg draft: **conversion code is deleted rather than
generalised.**

1. Remove `kgToLbs` from `frontend/src/pages/BodyComposition.tsx:102` and its
   call sites (lines 129, 135, 153, 159). Storage is lbs; display is the
   identity function.
2. Axis labels already read `"Weight (lbs)"` (line 243) and become correct
   rather than coincidentally correct.
3. **No changes to `WorkoutSession.tsx` or `Progression.tsx`.** Under the kg
   draft both would have silently read ~45% low until updated. They display
   stored lbs today and continue to.
4. No display-unit preference, no `lib/units.ts`. Stored unit and display unit
   are the same. Add one only if kg display is ever wanted.

`wendler_service.py` needs no change: percentages are ratios, and nearest-5-lb
rounding continues to work directly against stored values.

---

## 6. Revision sequence

| Rev | Does | Reversible |
|-----|------|-----------|
| `a1` | Body comp mass columns → lbs (Path A only); set `weight_unit='lbs'` | Yes — divide by 2.2046226218 |
| `a2` | Add `metric_def` + `metric`; seed `metric_def` | Yes — drop |
| `a3` | Backfill `metric` from `body_composition` | Yes — delete by `source='openscale'` |
| `a4` | Add `v_body_comp_daily` | Yes — drop |
| `a5` | Drop `weight_unit` columns (batch mode, Plan 0002 §1.4) | Rebuild; do last |

Stop after `a1` and verify against real numbers before continuing.

---

## 7. Verification

```sql
-- body comp is lbs and plausible for a human
SELECT weight, weight_unit FROM body_composition ORDER BY timestamp DESC LIMIT 3;

-- training data untouched
SELECT weight_unit, count(*) FROM workouts GROUP BY weight_unit;   -- lbs | 9292

-- backfill complete
SELECT count(*) FROM metric WHERE source = 'openscale';

-- view matches source for a known day
SELECT * FROM v_body_comp_daily WHERE date = '2026-08-01';
SELECT * FROM body_composition  WHERE date = '2026-08-01';
```

`SELECT weight_unit, count(*) FROM workouts` returning `lbs | 9292` unchanged is
the clearest signal this plan did what it should: the largest table is not
involved. *(An earlier draft said 249 here — a stale figure from before the
full history was imported.)*

Tests needing updates are limited to body composition:
`backend/tests/test_repositories_body_comp.py`,
`backend/tests/test_services_mqtt.py`. Add a case asserting the MQTT path
converts (Path A) and that percentage fields are *not* converted — that
asymmetry is the likeliest regression.

`test_repositories_workout.py` and `test_services_progression.py` need no
changes, where the kg draft would have touched every weight fixture in both.

---

## 8. Rollback

Per-revision `downgrade()` for `a1`–`a5`.

Take the file copy before `a1` regardless — the migration is smaller than the kg
draft, not free:

```bash
sqlite3 "$HELF_DATA_PATH/helf.db" ".backup '$HELF_DATA_PATH/helf.db.pre-units'"
```

Use `.backup`, not `cp` — WAL is on after Plan 0002 and `cp` may miss
uncommitted pages.

---

## 9. Read path moved onto the views (2026-08-08)

**Status: done.** Every read in `BodyCompositionRepository` — `get_all`,
`get_by_id`, `get_latest`, `get_by_date_range`, `get_recent` and `get_stats` —
now queries `v_body_comp_measurements`. `body_composition` is written but no
longer read, except by `reconcile_mirror` and the duplicate-timestamp check.

### The blocker in §4 was resolved by `observation`, not worked around

Revision `7bba3fe3ee35` extracts an `observation` table (`id`, `observed_at`,
`date`, `source`, `created_at`) that `metric` rows reference with
`ON DELETE CASCADE`. That gives a measurement a real identity, which is what the
views were missing. `v_body_comp_measurements` now carries `doc_id`,
`created_at` and a literal `weight_unit`, so the response shape is unchanged.

### `doc_id` changed meaning — and the ids do not line up

**This is the sharp edge.** Reads now return `observation.id`.
`body_composition.id` is a different sequence: **77 of the 150 production rows
disagree.** `delete()` previously looked up `body_composition.id`, so leaving it
alone would have deleted a *different measurement* than the user asked for, in
roughly half of all cases, silently.

`delete()` now resolves an `Observation` by id and removes the legacy row by
matching the instant. Regression test
(`test_doc_id_round_trips_through_delete`) deliberately forces the two
sequences apart so a coincidental match cannot make it pass.

### Tests now run the migrations

`conftest.py` built its schema with `Base.metadata.create_all()`. That is no
longer viable: the read path queries views and `metric_def` carries a seeded
vocabulary, and neither exists in `Base.metadata` — `create_all()` produces a
database the application cannot run against. Fixtures now run `upgrade head`,
which costs about 2s across the suite and means tests exercise the same startup
path the container does.

### Verification

- 177 tests pass; `ruff` clean; `alembic check` reports no drift.
- Against a copy of production, served entirely from the views: the list returns
  **150 measurements, not 107 days** — the grain is preserved; `/stats` returns
  figures identical to the `body_composition`-backed implementation; and a
  `DELETE` round-trip returns 204 and removes the right row.
- `test_reads_are_served_from_the_view` empties `body_composition` and asserts
  reads still work, which is the strongest available proof of where they come
  from.

### What remains

- `a5`: drop the `weight_unit` columns.
- Retire `body_composition` entirely. It is now write-only; once the mirror has
  been trusted for a while, the dual write, `_serialize`, `reconcile_mirror` and
  the table all go. That is a separate plan.

---

## 10. `a5` — `weight_unit` dropped (2026-08-08)

**Status: done**, revision `e96bd4b90873`. Plan 0003 is complete.

All three columns held `'lbs'` in every row — 9,292 workouts, 30 upcoming, 150
body composition — because `a1` converted the only kilogram data there was.
Storing the same string 9,472 times records nothing and invites the belief that
another value is possible.

**The API still reports `weight_unit`.** The frontend renders it in six places
(`WorkoutSession.tsx`, `Progression.tsx`, `Upcoming.tsx`), so removing the field
would have printed "undefined" next to every weight. Dropping *storage* and
dropping the *field* are separate decisions, and only the first is justified
here: the unit is a property of the schema, not of a row. It now comes from
`app.utils.units.CANONICAL_WEIGHT_UNIT`.

That module also absorbs `KG_TO_LB`, which was duplicated between
`mqtt_service` and the `a1` migration. The migration keeps its own copy
deliberately — a migration must not change behaviour because an application
constant was edited later.

**The migration refuses to drop a column that disagrees with its premise.**
Dropping is irreversible in the way that matters: the values are gone. If any
row is not `'lbs'`, either `a1` missed it or a new writer has appeared, and
dropping would discard the only evidence. Verified by poisoning a copy — one
`'kg'` row aborts the migration and names the offending value.

**The generated downgrade was wrong and would have failed.** Alembic emitted
`add_column(..., nullable=False)` with no default; a batch rebuild of a
populated table cannot fill a NOT NULL column from nothing. It now carries
`server_default='lbs'`, and the round trip is verified.

Verified: 9,292 workouts and `sum(reps)` 63,719 unchanged; all four `workouts`
indexes survived the rebuild; `foreign_key_check` clean; `metric` untouched at
600 rows and reconciling in sync; every endpoint 200 with `weight_unit` still
reported as `lbs`; writes still work.
