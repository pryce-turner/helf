# Plan 0008: BodySpec DEXA integration

**Status:** Implemented (2026-08-09) — through revision `70709fd96184`; see §12
**Auth:** interactive paste-a-token, never persisted (§3)
**Prerequisites:** Plan 0002 (Alembic) ✓, Plan 0003 (`metric`) ✓, `document` — **created by this plan**, see §12
**Related:** ADR-0003
**Spec:** `https://app.bodyspec.com/openapi.json` — BodySpec API 0.15.0, **early access**

> **§12 reconciles this plan against the schema as built (2026-08-08).** Plan
> 0003 landed a different shape than this document assumed — `source` and
> `observed_at` moved off `metric` onto a new `observation` table, and the
> `UNIQUE (observed_at, name, source)` constraint this plan's idempotency design
> is built on no longer exists. Sections below have been corrected in place;
> §12 records what was wrong and why, because the corrections are not obvious
> from the corrected text.

Replaces "no data source yet for DEXA" (previously Plan 0001 §5, parked) with a
real integration. This is the design doc §2 `document` → `metric` promotion
pattern applied to its intended use case.

---

## 1. What the API provides

Base: `https://app.bodyspec.com`. Personal endpoints are under
`/api/v1/users/me/`.

| Endpoint | Returns |
|----------|---------|
| `GET /results/` | Paginated scan list — `result_id`, `start_time`, location, service |
| `GET /results/{id}/dexa/scan-info` | Scanner model, acquire/analyze time, `age_years`, `height_cm`, `weight_kg` |
| `GET /results/{id}/dexa/composition` | `total` + 7 regions × 6 measures |
| `GET /results/{id}/dexa/bone-density` | BMD, area, mineral content, Z/T percentiles + regions |
| `GET /results/{id}/dexa/visceral-fat` | `vat_mass_kg`, `vat_volume_cm3` |
| `GET /results/{id}/dexa/rmr` | Array of RMR estimates by formula, `kcal_per_day` |
| `GET /results/{id}/dexa/percentiles` | Population percentiles |

The composition payload carries `total` plus seven regions — `android`,
`gynoid`, `left_arm`, `right_arm`, `left_leg`, `right_leg`, `trunk` — each with
`fat_mass_kg`, `lean_mass_kg`, `bone_mass_kg`, `total_mass_kg`,
`tissue_fat_pct`, `region_fat_pct`. Flattened across all six endpoints, a single
scan is **well over a hundred scalars**. All confirmed against a live response.

**Region sets differ between endpoints** — composition has 7, bone-density has 5
(no `android` or `gynoid`). A generic flattener must not assume a shared region
list across sections.

That number settles a design question. The wide `body_composition` table
(`db/models.py:105-124`, nine columns) could not hold this without a column
explosion, and adding a column per region per measure per scan type is exactly
the migration treadmill the tall `metric` table exists to avoid. **BodySpec is
the strongest argument yet for Plan 0003's wide→tall conversion.**

## 2. Units: everything is kilograms

Every mass field is explicitly kg-suffixed — `fat_mass_kg`, `lean_mass_kg`,
`bone_mass_kg`, `total_mass_kg`, `vat_mass_kg`, `weight_kg`. Also `height_cm`,
BMD in g/cm², bone area cm², mineral content grams, VAT volume cm³, RMR
kcal/day.

This is **not** a reason to revisit ADR-0003. That ADR's scope limit already
anticipated it: *"Future DEXA and blood work land in `metric` in their source
units, with unit-suffixed names."* Two reinforcing points:

- BodySpec independently arrived at the same convention ADR-0003 adopted —
  the unit lives in the field name, so a reader never has to consult a schema.
  Storing `fat_mass_kg` as `fat_mass_kg` is the convention working, not a
  violation of it.
- Fat mass, lean mass, and BMD are **different quantities** from body weight.
  They are never summed with training weight, so they need no shared unit.

### The one field that does collide — and there are two of them

`total_mass_kg` (composition) and `patient_intake.weight_kg` (scan-info) are both
body weight, the quantity ADR-0003 pins to pounds. **They are not the same
number.** From the 2026-03-10 scan:

| Field | Value | What it is |
|---|---|---|
| `composition.total.total_mass_kg` | **87.67** | Mass the scanner measured |
| `scan_info.patient_intake.weight_kg` | **86.2** | Weight recorded at intake |

A 1.47 kg (3.2 lb) gap. Intake weight is what went on the clipboard; total mass
is the sum of the scan's own fat + lean + bone. An earlier draft treated them as
interchangeable — they are not, and picking the wrong one puts a systematic
offset into the weight series.

**Promote `composition.total.total_mass_kg`**, converted to `body_weight_lb`
with `source = 'bodyspec'`. It is the measurement; `patient_intake` is metadata
about the appointment. Do not promote `patient_intake.weight_kg` at all — it
would create a second, conflicting body-weight series from the same scan.

Everything else keeps its source unit and kg-suffixed name. Raw kg stays in
`document`, so the conversion is auditable against the original payload.

### Decomposition confirmed

`fat + lean + bone = total` holds exactly:

```
14.51 + 69.61 + 3.55 = 87.67 ✓
```

which makes fat-free mass unambiguous — `total − fat = 73.16 kg`, equal to
`lean + bone`. This is the input Katch-McArdle needs (§8).

This makes scale weight and DEXA weight directly comparable on one axis while
leaving the DEXA-specific measures untouched — which is the whole point of
`source` on `metric`.

## 3. Authentication — paste-a-token, never stored

`info.description` documents two methods, and **neither is a simple API key**:

**OAuth2 + PKCE via Keycloak** (`auth.bodyspec.com/realms/bodyspec`),
authorization-code flow, scopes `openid profile email`. Designed for interactive
use — the docs literally say "Click the Authorize button".

**Partner Auth** — `Authorization: Basic base64(partner_id:partner_secret)`,
explicitly "for partner integrations only", requiring credentials from BodySpec.
This is what the entire `/api/v1/partners/**` surface uses, including webhooks.

### The approach

Rather than automating OAuth, the access token is obtained **interactively from
BodySpec's own docs** (the Authorize button at `app.bodyspec.com/docs`) and
pasted into Helf to trigger a sync.

**The token is a parameter of the sync request and is never persisted.** It
arrives in the request, is used for the handful of upstream calls, and is
discarded when the request ends.

That single choice dissolves most of the difficulty:

- **No stored credential.** Nothing in the database, nothing in env, nothing in
  a mounted secret file, nothing to rotate or leak.
- **Expiry stops mattering.** Measured from a real token's JWT claims, the
  lifetime is **exactly 3600 seconds — 60 minutes** (`iat` → `exp`, issuer
  `auth.bodyspec.com/realms/bodyspec`, client `bodyspec-api-ext-v1`, scopes
  `openid profile email`). A sync is a few dozen HTTP calls taking seconds, so
  an hour is an enormous margin. The token can only expire *between* syncs,
  when Helf isn't holding one anyway.
- **No OAuth client implementation at all** — no PKCE, no redirect URI, no
  token endpoint, no refresh handling. Helf forwards a bearer string.
- **It stays out of the LLM's reach.** A token stored in `helf.db` — in a
  settings table or otherwise — would be readable by the MCP server's `query`
  tool, which has unrestricted read across the schema (ADR-0004: read-only is
  not a confidentiality control). Not persisting it makes that structurally
  impossible rather than a matter of restricting views.

The cost is that sync is manual. At a few DEXA scans a year, that is not a
meaningful degradation — arguably it's correct, since a sync is only useful
right after a scan.

### Handling expiry

The token *can* still expire mid-sync — a long first import, or a token pasted
some minutes after it was issued. Two requirements:

1. **A 401 from BodySpec surfaces as "token expired, paste a fresh one"**, not a
   generic 500. This is the one error the user will actually hit — confirmed in
   practice. The upstream body is:

   ```json
   {"detail": "Invalid token: Signature has expired"}
   ```

   Match on the 401 status, not that string.
2. **A partial sync must be resumable.** It already is: idempotency is keyed on
   `result_id` per §5, so a sync that dies halfway leaves completed scans
   imported and re-running picks up the rest. Nothing is corrupted by an
   interrupted run, which is what makes a short-lived token safe here.

### Not logging it

The token must never reach logs. `mqtt_service.py` logs full payloads at INFO
(`logger.info(f"Received message on {msg.topic}: {payload}")`), so the codebase
does not currently have a reflex for this — worth being explicit in review.

### Why the token can't live in `.env`

A 60-minute lifetime settles this empirically: a token written to `.env` is dead
within the hour and useless by the next container restart. Storing it in config
doesn't merely violate the principle in this section — **it does not work**.
`.env` is fine as a scratchpad for a manual validation run; it is not a path to
an implementation.

One thing worth chasing: the JWT carries an `ext_api_token` claim. That naming
hints BodySpec may offer a longer-lived external API token distinct from these
hour-long session tokens. If it exists, it would change this section
substantially — worth an email to `dev-support@bodyspec.com`, which the API
description gives as the contact for early-access questions.

### Where the token lives in production: nowhere

Stated plainly because it is the question this design keeps provoking.

The 60-minute JWT is a **session artifact**, not a service credential — it is
what an interactive login hands a browser tab. Nothing is supposed to store it.
Its production home is the request:

```
browser field  →  Authorization header  →  handler variable  →  out of scope
```

On disk: never. In `helf.db`: never. In `.env`: never (and it wouldn't survive
an hour anyway). Total lifetime inside Helf: the duration of one HTTP request.

This is viable because the cadence is ~4 scans a year, and a sync is only useful
immediately after one. Four paste operations a year is not friction worth
engineering away.

### If background sync is ever wanted

The credential to store is then **not this token** — it is a *refresh* token,
obtained once via PKCE and exchanged for access tokens on demand. Only at that
point does storage become a real question, and the answer is:

| | |
|---|---|
| **Docker secret or mounted file, mode 0600** | Injected at runtime, outside the image and outside the repo |
| **Never `helf.db`** | The MCP `query` tool reads the whole schema (ADR-0004); a credential there is readable by any connected LLM |
| **Never a committed `.env` or an image layer** | Both outlive the credential and travel further than intended |

Cost: implementing PKCE, a redirect URI, and rotation handling — Keycloak
typically rotates refresh tokens on use and expires them on inactivity, so a
quarterly job can find its credential dead with nobody present to re-authorise.
That is real work to save four paste operations a year. **Don't**, unless the
`ext_api_token` lead above turns out to be a genuine long-lived API key — in
which case it goes in a Docker secret and background sync becomes trivial.

## 4. No webhooks for personal accounts

Webhook endpoints exist only under `/api/v1/partners/{partner_id}/webhooks`. As
an individual user, **polling is the only option**.

This is fine. DEXA scans happen every few months, so a daily poll of
`GET /results/?page=1&page_size=25` is more than sufficient and trivially cheap.

The spec documents **no rate limits** — zero mentions of rate limiting or 429
anywhere. Given it is early access, treat that as unspecified rather than
unlimited: back off on errors, and don't poll more than once an hour.

## 5. Import design

### Idempotency

`result_id` is the natural key. `document` carries an external identity so a
re-poll can't double-import. This plan creates the table (Plan 0005's schema,
with `external_id` present from the start rather than bolted on):

```sql
CREATE TABLE document (
    id           INTEGER PRIMARY KEY,
    imported_at  TEXT NOT NULL DEFAULT (datetime('now')),
    kind         TEXT NOT NULL,
    source       TEXT,
    external_id  TEXT,
    raw          TEXT NOT NULL CHECK (json_valid(raw))
);
CREATE UNIQUE INDEX ux_document_kind_external ON document(kind, external_id);

ALTER TABLE metric ADD COLUMN document_id INTEGER REFERENCES document(id);
```

Sync algorithm:

1. `GET /results/` (paginate on `has_more`).
2. For each `result_id` not already in `document`, fetch all six sub-resources.
3. Store the combined payload as one `document` row, `kind = 'dexa_bodyspec'`,
   `external_id = result_id`, `raw` = the merged JSON.
4. Upsert an `observation` for the scan, then promote the curated scalars into
   its `metric` rows with `document_id` set.

Steps 3 and 4 in one transaction — a document without its metrics is a silent
gap, and the FK is what keeps provenance intact.

> **The uniqueness this rests on is on `observation`, not `metric`.** An earlier
> draft specified `ON CONFLICT (observed_at, name, source)` against `metric`.
> That constraint was never built: Plan 0003 §9 moved `observed_at` and `source`
> onto `observation` (`UNIQUE (observed_at, source)`) and left `metric` unique on
> `(observation_id, name)`. The import therefore upserts
> `observation(observed_at = acquire_time, source = 'bodyspec')` **first**, and
> keys its metrics on `(observation_id, name)`. The property is unchanged — a
> DEXA and a scale reading of the same quantity on the same day remain two rows —
> but it now comes from the observation's identity rather than the metric's.

### `observed_at` must match the existing convention exactly

Two things depend on the format, and neither is obvious:

- **`observation.date` is `substr(observed_at, 1, 10)`**, a stored generated
  column, and it is the app's universal join key. Every existing row is
  Pacific-local and naive, so a format that shifts the day files a scan under
  the wrong date.
- **Idempotency keys on byte-identical `observed_at`.** A format that varies
  between runs re-imports the same scan under a second observation.

The spec settles what `acquire_time` actually is: *"When the scan was acquired
**in location timezone**"* — not UTC, as an earlier version of this section
assumed. `parse_iso_timestamp` already does exactly the right thing with that:
an offset is converted to Pacific, and a naive timestamp is taken as already
local. It is then formatted `%Y-%m-%d %H:%M:%S.%f`, matching
`body_comp_repo._observed_at`. Pinned, not incidental.

(A scan taken outside Pacific and reported naive is filed at its own wall-clock
time, which keeps the calendar date right — the part that matters — while the
hour is nominal.)

### What to promote

The design doc says *"the handful of scalars you care about"* — deliberately not
all of them. Promoting 100+ scalars per scan makes `metric` unreadable and
`metric_def` a maintenance burden, for regional data that is browsed rather than
trended.

Promote what you'd chart over time:

| `metric` name | Source field | Unit |
|---------------|--------------|------|
| `body_weight_lb` | `composition.total.total_mass_kg` | lb — **converted** |
| `fat_mass_kg` | `composition.total.fat_mass_kg` | kg |
| `lean_mass_kg` | `composition.total.lean_mass_kg` | kg |
| `bone_mass_kg` | `composition.total.bone_mass_kg` | kg |
| `body_fat_pct` | `composition.total.tissue_fat_pct` — canonical, see below | % |
| `android_gynoid_ratio` | `composition.android_gynoid_ratio` | — |
| `vat_mass_kg` | `visceral_fat.vat_mass_kg` | kg |
| `bone_mineral_density_g_cm2` | `bone_density.total.bone_mineral_density` | g/cm² |
| `rmr_kcal_per_day` | **Derived** — Katch-McArdle from FFM, see §8 | kcal/day |
| `ffm_kg` | `total_mass_kg − fat_mass_kg` (fat-free mass) | kg |
| `total_lmi_kg_m2` | `percentiles.metrics.total_lmi_kg_m2.value` | kg/m² |
| `limb_lmi_kg_m2` | `percentiles.metrics.limb_lmi_kg_m2.value` | kg/m² |
| `height_cm` | `scan_info.patient_intake.height_cm` | cm |

`bone_mineral_density` was renamed `bone_mineral_density_g_cm2` — ADR-0003 point
4 and §2 above both require the unit in the name, and an earlier draft of this
table was the one place that didn't follow it.

**Every one of these names must be seeded into `metric_def` by the migration.**
`metric.name` is a foreign key to `metric_def.name`, so an unseeded name is not
a warning, it is a failed insert. Eleven of the thirteen are new;
`body_weight_lb` and `body_fat_pct` already exist from Plan 0003 and must be
`UPDATE`d rather than `INSERT`ed — see the `body_fat_pct` note below, whose
earlier `INSERT` would have been a primary-key conflict.

The two lean mass indices come from the `percentiles` endpoint, which turns out
to be richer than the spec example suggested — it returns both a `value` and a
`percentile` for five metrics, against a stated reference population
(`gender`, `reference_age_range`, `reference_dataset_size: 444000`).

**Promote the values, not the percentiles.** A percentile is a function of the
value *and* the reference cohort, and the cohort shifts as you age out of a
band — so a stored percentile silently means something different over time.
Percentiles stay in `document.raw`, queryable and correctly frozen alongside the
`params` that produced them.

`observation.observed_at` = `scan_info.acquire_time` (when the scan happened),
**not** `create_time` or `update_time`, normalized as described above.
`observation.source = 'bodyspec'`.

Everything unpromoted stays queryable — the raw JSON is intact in `document`,
reachable via `json_extract`, and the agent's `query` tool can reach it. Nothing
is lost by promoting conservatively; a scalar can be promoted later by
re-running the promotion step over stored documents.

**`body_fat_pct` now has two sources** — the scale and DEXA — with DEXA being
the accurate one. `UNIQUE (observed_at, source)` on `observation` keeps them as
distinct measurements rather than overwriting. Any view or chart showing body
fat must either pick a source or plot both; silently mixing a bioimpedance
estimate with a DEXA measurement would be misleading.

> **This is not hypothetical, and the read path does not currently do it.**
> Plan 0003 §9 moved every body-composition read onto
> `v_body_comp_measurements`, which has no filter on `source`. The first
> imported scan therefore joins the measurement list, can become
> `get_latest()`, and enters both `get_stats()`'s earliest-to-latest deltas and
> `/trends` → `calculate_moving_average` — which Plan 0003 §4a names explicitly
> as source-blind and requiring a single-source series. Making the read path
> source-aware is a prerequisite of the first import, not a follow-up. See §12.

### `tissue_fat_pct` is canonical — decided, with one caveat worth reading

BodySpec returns two fat percentages per region: `tissue_fat_pct` excludes bone,
`region_fat_pct` includes it. **`tissue_fat_pct` is the canonical source for
`body_fat_pct`.**

From the 2026-03-10 scan: `tissue_fat_pct` **17.25**, `region_fat_pct` **16.55**
— a 0.70 pp spread, as anticipated.

> **Caveat, found while validating.** An earlier draft justified this partly as
> "what BodySpec's own reports headline." The `percentiles` endpoint contradicts
> that: it reports `total_body_fat_pct = 16.6`, which matches `region_fat_pct`
> (16.55), **not** `tissue_fat_pct` (17.25). So BodySpec benchmarks against the
> population using the region figure.
>
> The consequence is narrow but real: the app will show 17.25% while BodySpec's
> percentile context is computed on 16.6%. The choice stands — `tissue_fat_pct`
> is the more standard "body fat percentage" and excluding bone is defensible —
> but it is a deliberate divergence from their reporting, not alignment with it.
> If matching their percentile framing matters more, switch now, before any
> history accumulates.

Record the choice where it's visible to anyone — including the agent — writing a
query:

`body_fat_pct` is already seeded by Plan 0003, so this is an `UPDATE` — an
`INSERT` is a primary-key conflict and would abort the migration:

```sql
UPDATE metric_def SET description =
  'Body fat percentage. DEXA source = BodySpec tissue_fat_pct (soft tissue, '
  'excludes bone) — NOT region_fat_pct. Scale source = openScale bioimpedance. '
  'Distinguish by observation.source; do not mix in one series.'
WHERE name = 'body_fat_pct';
```

Note `observation.source`, not `metric.source`. `metric` has no source column.

**Never switch to `region_fat_pct` later.** The two differ by roughly a
percentage point, so a switch mid-history manufactures a step change that reads
as a real body composition shift. If it ever must change, re-promote the whole
series from stored `document` rows in one migration rather than changing the
field going forward — the raw payloads make that possible, which is a large part
of why they're retained.

## 6. Implementation

| Layer | File | Content |
|-------|------|---------|
| Client | `backend/app/services/bodyspec_client.py` | The six GETs + pagination; takes a token per call, holds none |
| Sync | `backend/app/services/bodyspec_sync.py` | Walk results, dedupe, store document, promote metrics |
| API | `backend/app/api/body_comp.py` | `POST /api/body-composition/sync/bodyspec` |
| Repo | `backend/app/repositories/document_repo.py` | Document + promotion writes |
| UI | `frontend/src/pages/BodyComposition.tsx` | Token field + "Sync" button + result summary |

**No config entries.** Nothing to add to `backend/app/config.py` and nothing to
`docker-compose.yml` — a consequence of §3 not persisting the token.

`httpx` needs no work: it is already a runtime dependency
(`backend/pyproject.toml:17`, under `[project] dependencies`). An earlier draft
called it test-only.

### Endpoint shape

```
POST /api/body-composition/sync/bodyspec
Authorization: Bearer <bodyspec access token>

200 { "scans_found": 5, "imported": 2, "skipped": 3, "metrics_written": 20 }
401 { "detail": "BodySpec token expired or invalid — paste a fresh one" }
```

Taking the token in the `Authorization` header rather than a JSON body keeps it
out of request-body logging and out of any URL. The handler forwards it upstream
and never writes it anywhere.

**No scheduler.** The app has no scheduling mechanism today, and §3 explains why
adding one for this would be a step backwards. Sync is user-triggered.

### Frontend

A small section on the existing Body Composition page: a password-type input for
the token, a Sync button, and the counts from the response. Link out to
`app.bodyspec.com/docs` so the token is two clicks away when needed.

Use `type="password"` so the token isn't shoulder-surfable or captured in
screenshots, and don't put it in component state that persists across navigation
— it should die with the request, mirroring the backend.

## 7. BodySpec supplements openScale — decided

**Both sources stay.** They measure the same quantities with opposite
strengths:

| | openScale | BodySpec DEXA |
|---|---|---|
| Frequency | Daily | ~Quarterly |
| Accuracy | Low (bioimpedance) | Reference standard |
| Good for | Trend, direction, velocity | Absolute values, composition detail |

`observation.source` keeps them categorically separate at the storage layer; the
`UNIQUE (observed_at, source)` constraint on `observation` means they coexist
rather than overwrite.

**The design work this requires lives in `plans/0003-units-and-metrics.md` §4a** —
source-aware views, the two-series chart encoding, and the rule against
averaging or interpolating across sources.

> **openScale is parked** — the Bluetooth integration may be defunct and would
> need a custom reimplementation. The supplement design above is the intended
> end state, not the current one. **BodySpec is the sole live body-composition
> source**, which makes this plan the critical path rather than an addition to
> an existing feed.

Consequences for this plan:

- Plan 0003 §1 (openScale payload units) and §2 (`muscle_mass` mass-vs-percent)
  are **parked, not blocking**. Nothing here waits on them.
- `body_fat_pct` and `body_weight_lb` carry only `source = 'bodyspec'` for now.
  Consumers must still be written source-aware — see `plans/0003-units-and-metrics.md`
  §4a — because retrofitting that later is how sources get silently merged.
- DEXA is authoritative for lean mass regardless. Its `lean_mass_kg` is a real
  measurement, where the scale's ambiguous `muscle_mass` column is at best an
  estimate of something adjacent.
- **Quarterly data is thin for trend work.** With the scale parked there is no
  daily weight series, so the moving averages and velocity-style views assume
  data that will not exist. Charts should degrade to discrete points rather than
  implying continuity — the §4a scatter encoding already does this correctly.

## 8. RMR: Katch-McArdle, computed locally

`dexa/rmr` returns RMR estimates as an **array of formulas**. Confirmed against
the 2026-03-10 scan:

| Formula | kcal/day |
|---|---|
| ten Haaf (2014) | 2150 |
| Cunningham (1980) | 2110 |
| De Lorenzo (1999) | 1882 |
| Mifflin-St. Jeor (1990) | 1854 |

**Katch-McArdle is not among them** — matching the spec exactly, where the
string appears nowhere.

### Decision: compute it

Katch-McArdle is driven by lean body mass, which is exactly what a DEXA scan
measures directly — it's the formula that earns its keep from having a scan,
where Mifflin-St. Jeor only needs a bathroom scale and a birthday. Since the
inputs are already being promoted, compute it rather than substituting a
different formula:

```
RMR = 370 + (21.6 × LBM_kg)
```

Stored as `rmr_kcal_per_day` **on the scan's own observation**, alongside the
measurements it derives from. Their full estimate array stays in `document.raw`,
so every offered formula remains queryable for comparison without being promoted.

> **Not `source = 'derived'` — that would 500 the body-composition page.** An
> earlier draft asked for a distinct source, which was expressible when `source`
> lived on `metric`. It no longer does: `source` is a property of the
> *observation*, so a derived source means a **second observation at the same
> instant**, carrying only `rmr_kcal_per_day`. Provoked against a copy of
> production, that observation becomes a 151st row in
> `v_body_comp_measurements` with `weight` NULL, and `BodyComposition.weight` is
> a required `float`:
>
> ```
> doc_id 151 | source derived | weight (null)
> ValidationError: weight — Input should be a valid number, input_value=None
> ```
>
> An RMR is not a separate act of measuring; it is a number computed from one.
> It belongs to the scan's observation. The provenance that `source = 'derived'`
> was meant to carry goes in `metric_def.description`, which §8 already writes —
> and that is where a reader or an agent will actually look for it.
>
> This also removes an inconsistency the old shape hid: `ffm_kg` is equally
> derived (`total − fat`) and §5 already files it under `bodyspec`. Both are now
> treated the same way.

### LBM means fat-free mass — not `lean_mass_kg`

**This is the easy way to get it wrong.** BodySpec decomposes body mass three
ways: `fat_mass_kg + lean_mass_kg + bone_mass_kg = total_mass_kg`. Its
`lean_mass_kg` is lean *soft tissue*, which excludes bone.

Katch-McArdle's LBM is **fat-free mass**, which includes bone:

```
LBM_kg = total_mass_kg − fat_mass_kg        (equivalently lean_mass_kg + bone_mass_kg)
```

Using `lean_mass_kg` alone understates LBM by bone mass — roughly 2.5–4 kg —
and therefore understates RMR by about **55–85 kcal/day**. That error is small
enough to look plausible and large enough to matter as a daily target, and it
would be silently baked into every scan. Hence promoting `ffm_kg` explicitly:
the intermediate is stored, so the derivation is checkable rather than buried in
a service.

### Verified against BodySpec's own arithmetic

Cunningham is `500 + 22 × LBM`. Solving their published 2110 kcal/day gives
LBM = 73.2 kg — which equals `total − fat` = **73.16 kg** exactly, and *not*
`lean_mass_kg` (69.61).

**BodySpec uses fat-free mass as LBM.** That independently confirms the
definition above, from their side of the API.

Working the real scan through both formulas:

| Formula | Expression | LBM 73.16 |
|---------|-----------|-----------|
| Katch-McArdle | `370 + 21.6 × LBM` | **1950** kcal/day |
| Cunningham (1980) | `500 + 22 × LBM` | 2110 kcal/day *(BodySpec's own)* |

A **160 kcal/day gap (~7.6%)**, so the app's figure sits below the report — as
expected, not a bug.

And the error the wrong LBM would cause, now concrete: using `lean_mass_kg`
(69.61) yields `370 + 21.6 × 69.61 = 1874` — **76 kcal/day low**, squarely in the
55–85 range predicted above.

Maintenance target at the §8 multiplier: `1950 × 1.4 = 2730 kcal/day`.

State the divergence in `metric_def.description` so it doesn't get "fixed"
later:

```sql
INSERT INTO metric_def (name, canonical_unit, description) VALUES
  ('rmr_kcal_per_day', 'kcal/day',
   'Resting metabolic rate, Katch-McArdle: 370 + 21.6 * FFM_kg. FFM = '
   'total_mass_kg - fat_mass_kg (includes bone). Computed locally — BodySpec '
   'does not offer this formula; its own estimates (Cunningham et al.) remain '
   'in document.raw and run ~150 kcal/day higher. Do not mix formulas.'),
  ('ffm_kg', 'kg',
   'Fat-free mass from DEXA: total_mass_kg - fat_mass_kg. Includes bone; '
   'NOT the same as BodySpec lean_mass_kg, which is lean soft tissue only.');
```

### Closing the calorie loop

Plan 0005 adds calorie tracking with no target to track *against* — a kcal total
with nothing to compare it to. This supplies one from measured body composition
rather than a formula fed by total weight.

It also appears to answer a standing item from Obsidian
(`Lifting/Helf Notes.md`): **"Update maintenance preset *somehow*"**. The
*somehow* is a Katch-McArdle RMR recomputed from each new scan. That's the
cross-domain link `v_daily_summary` exists for — measured expenditure against
logged intake against body composition trend.

Extend `v_daily_summary` with a `kcal_target` column from the most recent
`rmr_kcal_per_day`, scaled by a fixed **activity multiplier of 1.4**:

```
kcal_target = rmr_kcal_per_day × 1.4
```

1.4 reflects a 3-day lifting split. The conventional table says 1.55 for that
frequency, but those factors were calibrated on endurance activity and overshoot
for strength training, where most of a session is spent resting between sets.

Keep the multiplier in the **view**, not in the promoted metric —
`rmr_kcal_per_day` stays resting expenditure. Changing the multiplier is then a
`DROP VIEW` / `CREATE VIEW`, with no stored data to migrate.

If the number ever looks wrong, it's measurable rather than arguable: with food
logging (Plan 0005) and daily scale weight, `TDEE ≈ avg_intake − (weekly_lb_change
× 500)`. Not worth doing until there's a few weeks of intake data.

## 9. Verification

```bash
# TOKEN comes from the Authorize button at app.bodyspec.com/docs
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://app.bodyspec.com/api/v1/users/me/results/?page=1&page_size=5" | jq '.pagination'

# an expired token must produce a clean 401, not a 500
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H "Authorization: Bearer expired-nonsense" \
  http://localhost:30171/api/body-composition/sync/bodyspec      # -> 401

# the token must appear nowhere in the logs
docker logs helf-app 2>&1 | grep -c "$TOKEN"                     # -> 0
```

These queries go through `observation` — `metric` has no `source`, no
`observed_at` and (before this plan) no `document_id`. An earlier draft's
versions referenced all three and could not have run.

```sql
-- one document per scan, no duplicates on re-sync
SELECT kind, external_id, count(*) FROM document GROUP BY 1,2 HAVING count(*) > 1;  -- empty

-- one observation per scan, and it is the only thing 'bodyspec' writes
SELECT o.id, o.observed_at, o.date, count(m.id) AS n_metrics
FROM observation o JOIN metric m ON m.observation_id = o.id
WHERE o.source = 'bodyspec' GROUP BY o.id ORDER BY o.observed_at DESC;

-- promoted metrics carry provenance
SELECT m.name, m.value, m.unit, d.external_id
FROM metric m
JOIN observation o ON o.id = m.observation_id
JOIN document d ON d.id = m.document_id
WHERE o.source = 'bodyspec' ORDER BY o.observed_at DESC, m.name;

-- DEXA weight is lb and agrees with the raw kg in the document
-- 2.20462262184878 is app.utils.units.KG_TO_LB; an earlier draft used a
-- truncated 2.2046226218 here, which disagrees with what the importer used.
SELECT m.value AS lb,
       json_extract(d.raw, '$.composition.total.total_mass_kg') AS raw_kg,
       m.value / 2.20462262184878 AS implied_kg
FROM metric m
JOIN observation o ON o.id = m.observation_id
JOIN document d ON d.id = m.document_id
WHERE m.name = 'body_weight_lb' AND o.source = 'bodyspec';

-- the derived RMR lives on the scan's observation, not one of its own
SELECT count(*) FROM observation WHERE source = 'derived';   -- 0
```

Run the sync twice and confirm the second is a no-op — idempotency is the
property most likely to break, and the failure is silent duplicate history.

## 10. Rollback

```sql
DELETE FROM observation WHERE source = 'bodyspec';   -- metrics cascade
DELETE FROM document   WHERE kind   = 'dexa_bodyspec';
```

Order still matters, but for a different reason than the earlier draft gave:
`metric` rows go with their observation via `ON DELETE CASCADE`, so they are
never deleted directly, and `metric.document_id` is what requires the document
to go second. There is no config to remove — §6 adds none.

No other data is touched. Because raw payloads are retained, a botched
promotion is re-runnable from stored documents without re-fetching anything from
the API.

## 11. Open questions

1. ~~**The API returns only one scan** but there are four `DXAReport*.pdf`
   files in `~/Documents`.~~ **Resolved — and the premise was wrong.**

   The older reports are not BodySpec at all. They are **DexaFit** (DexaFit
   Seattle), a different provider with a different scanner. Nothing was missing
   from the API and there is nothing to ask `dev-support@bodyspec.com` about:
   `has_more: false` was the complete BodySpec history all along.

   There are also only **three** distinct scans, not four — `DXAReport2.pdf`
   and `DXAReport4.pdf` are byte-identical (same MD5).

   | Date | Total | Body fat | Lean | VAT | Source file |
   |---|---|---|---|---|---|
   | 2024-05-21 | 200 lb | 18.4% | 156 lb | 0.24 lb | `DXAReport3.pdf` |
   | 2024-09-10 | 191 lb | 15.1% | 154 lb | 0 lb | `DXAReport2.pdf` |
   | 2025-03-31 | 218 lb | 22.6% | 161 lb | 0.82 lb | `DXAReport.pdf` |

   Backfilled 2026-08-09 by a **one-off script kept outside the repo**, under
   `source = 'dexafit'` and `document.kind = 'dexa_dexafit'`. Deliberately no
   application code: there is no DexaFit API, no further scans are coming, and
   every metric name it writes was already in `metric_def`, so it needed no
   migration either. Three points of history are not worth a permanent
   integration.

   Three things about that data are worth knowing before querying it:

   - **It is a third source, not more BodySpec.** Different provider and
     scanner, so `observation.source` distinguishes it for the same reason
     openScale and BodySpec are distinguished. Do not merge them.
   - **The conversion runs the other way.** DexaFit reports in *pounds*, so
     `body_weight_lb` needs no conversion at all, while `fat_mass_kg`,
     `lean_mass_kg`, `ffm_kg` and `vat_mass_kg` are converted *into* kg — the
     opposite direction from §2. They are converted rather than given new
     lb-suffixed names so one quantity stays one series across providers.
   - **The values were read by eye.** The PDFs have no text layer; every number
     is a rasterised image, so they were transcribed from pages rendered at
     150dpi rather than parsed. `document.raw` records
     `transcribed_by_eye: true`, the source filename and its MD5. The importer
     refused any scan where `fat / total` disagreed with the printed body-fat
     percentage by more than 0.6pp, or where `total − fat − lean` fell outside
     4–12 lb of bone; both guards were provoked with deliberately corrupted
     values before the run. Masses are printed rounded to whole pounds, and no
     time of day is recorded — `observed_at` uses `00:00:00`, which is not a
     midnight measurement.

   One consequence: these scans predate the `/trends` 365-day cap, so they
   appear in the measurement list and in `/stats` (which now reports a range
   starting 2024-05-21) but not on the trend charts.

*Resolved: authentication (§3) — interactive paste-a-token, never stored.*
*Resolved: `tissue_fat_pct` is the canonical body fat source (§5).*
*Resolved: BodySpec supplements openScale; both retained (§7).*
*Resolved: RMR is Katch-McArdle, computed locally from FFM; activity multiplier
fixed at 1.4 in the view (§8).*

---

## 12. Reconciliation against the schema as built (2026-08-08)

This plan was written before Plan 0003 was implemented, and 0003 landed a
different shape than it assumed. Recorded here rather than silently corrected
above, because the corrections only make sense against what they replaced —
ADR-0001's premise.

### The shape that actually exists

| | Plan 0008 assumed | As built |
|---|---|---|
| Measurement identity | none — `metric` rows stood alone | `observation` (`observed_at`, `date`, `source`, `created_at`) |
| Uniqueness | `UNIQUE (observed_at, name, source)` on `metric` | `UNIQUE (observed_at, source)` on `observation`; `UNIQUE (observation_id, name)` on `metric` |
| `metric.source` | a column | **does not exist** — lives on `observation` |
| `metric.observed_at` | a column | **does not exist** — lives on `observation` |
| `metric.document_id` | a column | did not exist; **added by this plan** |
| `document` | Plan 0005's, pre-existing | did not exist; **created by this plan** |

### What that changed, in order of how badly it would have bitten

1. **`source = 'derived'` for RMR (§8) would have 500'd the body-composition
   page.** The worst of them, and the least obvious: with `source` on
   `observation`, a derived source means a second observation at the same
   instant carrying no body weight, which `v_body_comp_measurements` surfaces as
   a measurement row with `weight` NULL against a required `float`. Provoked on
   a copy of production before deciding, not reasoned about. RMR now lives on
   the scan's own observation.
2. **The read path is not source-filtered.** Nothing in the original plan could
   have anticipated this — Plan 0003 §9 moved reads onto the views after this
   document was written. The first import would have put a DEXA point into
   `get_latest()`, `get_stats()` and the `/trends` moving average alongside
   bioimpedance, which 0003 §4a forbids in as many words. Fixed before the first
   import by carrying `source` through the read path.
3. **Idempotency had no constraint to hang on** (§5). Upsert the observation
   first, then its metrics.
4. **`metric_def` seeding was never stated.** The FK makes an unseeded name a
   failed insert, not a warning. Eleven new definitions; `body_fat_pct`'s
   `INSERT` was a primary-key conflict and is now an `UPDATE`.
5. **Verification queries in §9 could not have run** — they selected
   `m.source`, `m.observed_at` and `m.document_id`, none of which existed.
6. **`observed_at` format was unspecified**, and both the app's notion of a date
   and the idempotency key depend on it.

### Smaller corrections

- `bone_mineral_density` → `bone_mineral_density_g_cm2`, per ADR-0003 point 4.
- `httpx` is already a runtime dependency; §6 claimed it was test-only.
- §9 used a truncated conversion factor disagreeing with `KG_TO_LB`.
- §10's rollback deleted from `metric` directly; metrics cascade.
- `height_cm` appeared twice in the §5 promotion table.
- §8's `v_daily_summary` extension targets a view Plan 0005 has not created. It
  stays specified here and is **out of scope for this plan**.

### Verified against the live API (2026-08-09)

One scan imported into the production database. Everything §2 and §8 assert
about the payload holds, checked rather than assumed:

| Claim | Result |
|---|---|
| Token lifetime is exactly 3600s | ✓ from the JWT claims |
| `has_more: false`, one scan only | ✓ — §11's open question confirmed |
| `fat + lean + bone = total` | ✓ 14.51 + 69.61 + 3.55 = 87.67 exactly |
| Cunningham back-solves to FFM, not lean mass | ✓ 2110 → 73.18 ≈ `total − fat` 73.16 |
| `tissue_fat_pct` ≠ `region_fat_pct` | ✓ 17.25 vs 16.55 |
| Percentiles benchmark on the *region* figure | ✓ `total_body_fat_pct` 16.6 |
| `body_weight_lb` round-trips to the raw kg | ✓ 193.2793 lb → 87.67 kg |
| `ffm_kg` is not `lean_mass_kg` | ✓ 73.16, not 69.61 |
| RMR is Katch-McArdle over FFM | ✓ 1950.256, not 1874 |
| Second sync is a no-op | ✓ `imported: 0, skipped: 1` |
| A bad token is a clean 401 | ✓ not a 500 |
| Token absent from logs and `helf.db` | ✓ zero occurrences of both |

**`acquire_time` carries an offset** (`2026-03-10T11:48:21-07:00`), so the
"location timezone" wording resolves to a real Pacific instant and
`observation.date` lands on `2026-03-10` correctly.

#### The instrument gap, now measured

The scan shares a day with an openScale reading, which makes §4a's calibration
query answerable for the first time:

| | DEXA | openScale | bias |
|---|---|---|---|
| Body fat | 17.25% | 23.40% | **+6.15 pp** |
| Weight | 193.28 lb | 190.37 lb | −2.91 lb |

Six percentage points, on the same body, hours apart. That is the number the
old `get_stats` would have differenced and reported as fat lost. `body_fat_change`
still reads the openScale series' own −2.8 after the import, and
`primary_source` reads `openscale` — the read-path fix working on real data
rather than on a fixture.

### What did *not* change

The units decision. ADR-0003's scope limit and §2 both survive contact with the
new schema unaltered: `composition.total.total_mass_kg` converts to
`body_weight_lb` because it is the same *quantity* the scale measures and must
share an axis with it; `patient_intake.weight_kg` is not promoted at all;
everything else is a different quantity that never enters body-mass arithmetic
and keeps its kg-suffixed source unit. Conversion uses
`app.utils.units.KG_TO_LB`, with the raw kg retained in `document` so the
arithmetic stays auditable against the original payload.
