# ADR-0003: Pounds as the canonical unit for body mass

**Status:** Accepted
**Date:** 2026-08-07

> **Revision note.** An earlier draft of this ADR selected kilograms, carried
> over from `design/quantified-self-plan.md` §2. That draft was never committed
> and no work was done against it; it is rewritten here rather than superseded.
> §5 records why the reversal happened, because the reasoning matters more than
> the outcome.

## Context

Mass is currently labelled per row, with defaults that disagree by table:

| Location | Label | Reality |
|----------|-------|---------|
| `backend/app/models/workout.py:14` | `"lbs"` | **249 of 249 rows are `lbs`** — verified, no mixing |
| `backend/app/models/upcoming.py:14` | `"lbs"` | same default |
| `backend/app/services/mqtt_service.py:102` | `"kg"` | **hard-coded, not derived from the payload** |

Three facts drive this decision:

1. **Training data is already uniformly lbs.** Not "defaults to" — a count over
   `workouts` returns 249 rows, all `lbs`, none null. There is no mixing to
   repair.
2. **Pryce reads, thinks, and trains in lbs.** US plates are lbs; the standing
   goal (`PryceVault/Lifting/1000lb Program.md`) is denominated in pounds, with
   working maxes of 335 / 295 / 385.
3. **The `"kg"` on body composition is an assertion by the code, not a property
   of the data.** `mqtt_service.py:101-102` stores `payload.get("weight")`
   verbatim and stamps `weight_unit="kg"` without reading a unit from the
   payload or converting anything.

The design doc §2 says *"All weights/masses in kg"*, but it asserts the unit
rather than arguing for it. The argument it actually makes is about **not
mixing** — *"never mix units in `metric.value`. This is the one real footgun of a
tall table."* That requirement is unit-agnostic.

Units also only need to be consistent **within a quantity**, not across them.
Nothing sums training weight with body weight; they are different measurements.

## Decision

**Pounds are the canonical stored unit for all body mass** — training weight and
body composition alike. Storage is uniform; no per-row unit column survives.

1. `workouts.weight` and `upcoming_workouts.weight` stay exactly as they are.
   **No conversion, no migration, no risk.**
2. Body composition converts to lbs, conditional on the verification in
   `plans/0003-units-and-metrics.md` §1 establishing what the payload contains.
3. `weight_unit` columns are dropped. A per-row unit column is an invitation to
   reintroduce mixing; its absence is the enforcement.
4. **Units are encoded in column and metric names** — `body_weight_lb`,
   `muscle_mass_lb`, `training_volume_lb` — so both a human and an LLM can see
   the unit without consulting a schema.
5. `metric` names are validated against `metric_def`, which carries the
   canonical unit.

Conversion factor, where conversion is needed: **1 kg = 2.2046226218 lb**.

### Scope limit

This governs **mass**. It does not make the system imperial:

- **BMI stays kg/m².** It is a defined index, not a mass, and openScale sends it
  precomputed. Converting it would be meaningless.
- **Body fat %, water %, protein %, visceral fat, metabolic age** are unitless
  or non-mass. Unaffected.
- **DEXA and blood work land in `metric` in their source units**, with
  unit-suffixed names. Lab markers are metric by convention and stay that way —
  they are separate quantities and never interact with body mass arithmetic.

  Confirmed against the BodySpec API, which reports every mass in kg with
  explicitly kg-suffixed field names (`fat_mass_kg`, `lean_mass_kg`,
  `vat_mass_kg`). Those are stored as-is. The one exception is DEXA **body
  weight** (`total_mass_kg` / `weight_kg`), which is the same quantity the scale
  measures and is therefore converted to `body_weight_lb` on import, with the
  raw kg retained in `document` for provenance. See
  `plans/0008-bodyspec-integration.md` §2.

  That BodySpec independently uses unit-suffixed field names is corroboration
  for point 4 above rather than a conflict with it.

## Consequences

- **The riskiest step in the roadmap disappears.** The earlier draft required
  `UPDATE workouts SET weight = weight * 0.45359237` across the largest table —
  non-idempotent, and silently plausible when wrong. Keeping training data in
  lbs removes that migration entirely.
- **Stored values stay round and human-readable.** 335 lb remains 335, not
  151.9528... A number typed in is the number stored.
- **Plate rounding stays natural.** `wendler_service.py` percentages are ratios
  and unit-agnostic, but rounding is not. Nearest-5-lb rounding works directly
  against stored values with no display-layer parameterisation.
- **The 1RM formula is unaffected** either way — `(0.033 × reps × weight) +
  weight` (`utils/calculations.py:25`) is linear in weight. Historical values
  keep their current magnitude, so any thresholds or cached estimates remain
  valid. Under the kg draft they would all have changed.
- **MQTT ingest gains a conversion**, if verification shows kg on the wire.
  openScale will keep sending its native unit forever, so this is a permanent
  ingest-time conversion rather than a one-off. Float precision is not a
  practical concern at this scale.
- **`kgToLbs` in `frontend/src/pages/BodyComposition.tsx:39` is deleted, not
  generalised.** Once storage is lbs, the display path is the identity function.
  This is the clearest signal the decision is right: the conversion code
  disappears instead of spreading.
- **A latent double-conversion is closed off.** Today the hard-coded `kg` label
  and the frontend's `kgToLbs` cancel out to a correct on-screen number *only if*
  the payload is genuinely kg. That coupling is invisible and fragile; making
  storage lbs removes both halves.

## 5. Why the reversal

Recorded deliberately, per ADR-0001's premise that reasoning is what's worth
keeping.

The first draft adopted kg because the design doc said kg. The design doc's
actual argument was about not mixing units, and kg was an unexamined default
carried along with it. Challenged directly — *"why are we trying to go lbs to
kg?"* — the justification did not survive contact with the data: there was no
mixing to fix, the conversion was purely preventive, and it would have imposed
the single most dangerous migration in the roadmap to solve a problem that a
naming convention solves for free.

The generalisable lesson: **a design doc's conclusions and its arguments are
separable, and only the arguments transfer.** When importing a decision from a
document written without knowledge of the existing system, re-derive it against
that system's actual data before accepting it.
