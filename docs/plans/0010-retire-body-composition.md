# Plan 0010: Retire `body_composition`

**Status:** Implemented (2026-08-09) — revision `9a4c05d7f31e`
**Prerequisites:** Plan 0003 ✓ (read path on the views), Plan 0007 ✓ (the
audit log, so a deletion is not the last word on what a row held)
**Related:** ADR-0003, Plan 0003 §4 and §9

Plan 0003 §9 ends with *"Retire `body_composition` entirely. It is now
write-only... That is a separate plan."* This is it.

---

## 1. Why now

`body_composition` has been written and not read since revision
`7bba3fe3ee35`. Every read — `get_all`, `get_by_id`, `get_latest`,
`get_by_date_range`, `get_recent`, `get_stats` — comes from
`v_body_comp_measurements`. The only remaining consumers of the table are the
dual write, the duplicate-timestamp check, and `reconcile_mirror`, which exists
solely to watch the dual write.

The condition Plan 0003 set was "once the mirror has been trusted for a while".
Against production:

```
expected_rows 600  mirrored_rows 600  missing 0  mismatched 0  orphaned 0
in_sync: true
```

600 of 600, exact. There is nothing left to trust.

## 2. The five columns that never held a value

| Column | Non-null in 150 rows |
|---|---|
| `weight`, `body_fat_pct`, `muscle_mass`, `water_pct` | 150 each — all mirrored |
| `bmi`, `bone_mass`, `visceral_fat`, `metabolic_age`, `protein_pct` | **0** |

Plan 0003 §2 noted this. What it did not note is that the five are **not
inert** — `mqtt_service` maps every one of them off the openScale payload
(`bmi`, `bone`, `visceralFat`, `metabolicAge`, `protein`) and `POST
/api/body-composition/` accepts all five. They are zero because the scale has
never published them, not because nothing would write them.

So dropping the table cannot be a plain drop. Today those fields land in a
table nobody reads; after the drop they would land nowhere at all, and the API
would be accepting data it silently discards. Either the fields go, or they get
somewhere real.

**They get somewhere real.** Five `metric_def` entries, five more names in the
repository's mirror map. That is one migration and one list, against the
alternative of pruning five fields from a Pydantic model, three view pivots and
the frontend types — and it turns five always-NULL response fields into ones
that would actually carry a value if the scale ever sent one.

### `bone_mass` is the one with a real decision in it

`metric_def` already has **`bone_mass_kg`**, seeded by Plan 0008 for DEXA.
openScale reports bone in kg too, and `mqtt_service` was converting it to
pounds to fill a column named `bone_mass`.

Inventing `bone_mass_lb` alongside `bone_mass_kg` would put one quantity under
two names, which is exactly the confusion ADR-0003 exists to prevent — units
live in names precisely so that a name means one thing. ADR-0003's canonical
pound applies to **body mass**; Plan 0008 already filed every DEXA sub-mass
(`fat_mass_kg`, `lean_mass_kg`, `ffm_kg`) in kg, and bone belongs with them.

So: openScale's bone mass is stored unconverted as `bone_mass_kg`, the
conversion in `mqtt_service` goes, and the views pivot `bone_mass_kg`. The API
field is renamed `bone_mass_kg` to match — a field whose unit disagrees with
its neighbours has to say so. Nothing displays it, so the rename costs a type
definition.

## 3. What the write path becomes

`create()` currently writes `body_composition`, commits, then mirrors into
`observation`/`metric` in a **separate transaction** that is deliberately
allowed to fail — because a lost scale reading is unrecoverable (openScale does
not retransmit) while a divergent mirror is not.

That asymmetry disappears with the table. There is one write, so it is one
transaction, and a failure is a failure.

Duplicate detection changes shape and improves:

- **Was:** `body_composition.timestamp` is UNIQUE, so a manual entry and a
  scale reading at the same instant collided and the second was dropped.
- **Now:** `observation` is unique on `(observed_at, source)`, so they are two
  observations. Which is the whole point of `source` — a bioimpedance estimate
  and a DEXA scan at one instant are two measurements, not a conflict.

`_observed_at`'s `"%Y-%m-%d %H:%M:%S.%f"` formatting stays exactly as it is.
The backfill copied `body_composition.timestamp` verbatim into
`observation.observed_at`, which is TEXT, and the uniqueness that deduplicates
a re-published MQTT reading is textual.

## 4. What goes

| Thing | Why |
|---|---|
| `body_composition` table | The point of the plan |
| `BodyComposition` ORM model, `db/__init__` export | Nothing left to map |
| `_serialize` | Served the table; `_from_view` serves the view |
| `_mirror_to_metric` | There is no longer a primary to mirror *from* |
| `reconcile_mirror` + its tests | Watched a dual write that no longer exists |
| `MIRROR_SOURCES` | Distinguished mirrored observations from imported ones |
| the legacy `DELETE ... WHERE timestamp = ?` in `delete()` | Nothing to delete |
| `KG_TO_LB` on bone in `mqtt_service` | §2 |

## 5. Rollback

Not symmetric, and this is the plan where that matters. `downgrade()` recreates
the table and **backfills it from `observation`/`metric`**, because a plain
`CREATE TABLE` would restore an empty one and call it a rollback. The five
never-populated columns come back NULL, which is what they were.

The backfill can only restore what was mirrored — which, per §1, is everything.
Back up first regardless: `sqlite3 data/helf.db ".backup data/helf.db.pre-0010.bak"`.

## 6. Verification

- `reconcile_mirror` reports `in_sync` immediately before the drop. The
  migration **re-runs that comparison itself** and refuses to drop the table if
  a single value differs — the check has to happen at the moment of the drop,
  not in a session that ran beforehand.
- Measurement count, first and last date, and `/stats` figures identical
  before and after.
- A round-trip through `POST` and `DELETE` on a copy of production.
- `alembic downgrade -1` restores 150 rows with matching checksums.
