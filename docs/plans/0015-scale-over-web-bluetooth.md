# 0015 — The scale talks to the browser

**Status**: In progress — everything but the hardware contact

Retires the MQTT ingest path built for plan 0003 and the phone-side chain in
front of it.

## 1. The chain, and which link is actually load-bearing

Today a weight reading crosses four hops before it lands:

    BF720 → BLE → Android phone → openScale → openScale-sync → MQTT broker → helf

The obvious complaint is the manual sync — openScale-sync has to be opened and
told to publish. That complaint is mostly wrong, and it is worth being precise
about why, because it changes what this plan is for.

Readings are **not lost** to a late sync. The scale stores its own history, so
a drain three weeks later still recovers everything in between. Grouping
`observation` by write date against measurement date shows exactly that:

| Written | Rows | Spanning |
|---|---|---|
| 2026-01-04 | 47 | back to 2025-09-26 |
| 2026-01-26 | 9 | 01-11 → 01-26 |
| 2026-02-22 | 12 | 01-27 → 02-18 |
| 2026-03-24 | 28 | 02-16 → 03-24 |

So the cost of a late sync is staleness, which is cosmetic. **The real risk is
the ring.** The BF720's manual puts onboard storage at the last 30
measurements. The March drain recovered 27 readings across 29 days — 90% of
capacity, with a margin measured in days rather than weeks. Past that ceiling
the scale overwrites its oldest reading and the measurement is gone for good,
silently, with nothing anywhere recording that it happened.

That is the failure this plan exists to prevent. Not the tapping.

## 2. The BF720 is on a standard service, which is the whole reason this is cheap

Beurer's older scales — BF700, BF710, BF800, and the Sanitas/Silvercrest
rebadges — speak a proprietary protocol that has to be reverse-engineered from
a decompiled app. Scoped against those, this plan was a research project.

The BF720 is not one of them. It uses the **Bluetooth SIG Body Composition
Service** (`0x181B`, measurement characteristic `0x2A9C`) alongside the Weight
Scale Service (`0x181D`). openScale's handler for it is named
`StandardBeurerSanitasHandler` for that reason, and `ble-scale-sync` files it
under "SIG-standard, native body composition". Published UUIDs, a documented
payload, no reverse engineering.

This is the fact the plan rests on. If it turns out to be wrong, stop and
reconsider rather than starting to reverse-engineer — §11.

## 3. The drain is on demand, and the buffer is what makes that sufficient

Web Bluetooth cannot poll. `requestDevice()` requires a user gesture for every
connection, `navigator.bluetooth` is not exposed in `ServiceWorkerGlobalScope`,
and the GATT connection drops when the tab closes. Periodic Background Sync
does not help, because it runs in the service worker and inherits the same
missing API.

So the PWA cannot wake up and fetch. It does not need to. Because the scale
buffers 30 readings, "drain more often than 30 accumulate" is the entire
requirement, and one tap every week or two satisfies it with a wide margin. The
weighing itself needs no phone at all — the scale records to its own memory and
the drain catches up later.

The interaction is: open helf on the bathroom Android, tap **Read scale**,
watch a count of readings appear. Seconds, and it replaces opening openScale.

## 4. One batch endpoint, and the browser holds no state

The scale replays its whole buffer on every connect, so a drain re-sends
readings helf already has — most of them, most of the time. The client must
therefore be free to send everything it read, every time, and let the server
sort it out.

`POST /api/body-composition` **cannot be that endpoint**, and this is easy to
miss: it calls `repo.create(measurement)` with no `source`, so it writes
`source='manual'`. `BodyCompositionCreate` has no `source` field at all. Posted
through as-is, every drained reading would land as a manual entry, splitting the
series exactly the way §6 forbids — and silently, because a manual entry is a
legitimate thing for that route to produce.

So the drain gets its own endpoint, **`POST /api/body-composition/sync/scale`**,
taking a batch and returning counts. There is already a precedent to copy in
`sync/bodyspec`, which imports many measurements at once, reports
`imported`/`skipped`, and exists for the same reason: an instrument-specific
ingest that must not be confused with hand entry.

Batch beats one request per reading on three counts. The `source` is fixed by
the route rather than trusted from the client. The response is the outcome line
the UI wants — "3 new, 11 already held" — rather than something assembled by
counting 409s. And a fourteen-reading drain is one request over a bathroom wifi
connection instead of fourteen.

Duplicate rejection is still the database's, not the endpoint's.
`body_comp_repo.create()` already returns `None` when `(observed_at, source)`
collides — the unique constraint has been the real guard since plan 0010 — so
the endpoint counts `None` as `skipped` and writes nothing extra.

The client therefore persists nothing, remembers no cursor, tracks no
high-water mark. Clear the PWA's storage and the next drain re-converges. The
tempting alternative — remember the last timestamp, send only newer readings —
is worse in every way: it puts correctness in the client where it cannot be
audited, and it breaks the moment the phone is replaced or the scale's clock
drifts.

## 5. The unit arrives in the payload now, and this is the trap

`mqtt_service.py` multiplies by `KG_TO_LB` unconditionally, and it is right to,
because openScale always sends kilograms. **That assumption does not survive
this change.**

The SIG Body Composition Measurement begins with a flags bitfield whose bit 0
selects the measurement units: clear means SI (kg), set means Imperial (lb).
The scale reports in whatever it is configured to display — and this unit is
almost certainly set to pounds. A copy of the MQTT conversion would therefore
double-convert, producing weights around 190 kg, plausible-looking against
nothing and wrong by 2.2x.

Read the flag. Convert only when it says SI. This must have a test with both
payload variants before any real reading is written.

The second mapping trap is inherited rather than new: the API field
`muscle_mass` holds a **percentage**, and the SIG service has separate Muscle
Percentage and Muscle Mass fields. Map percentage to it, matching the existing
`muscle_pct` metric. See the data-model notes in `AGENTS.md`.

## 6. `source` stays `openscale`

The name reads like the Android app, and the app is what is being removed. It
still stays, because `observation.source` names the **instrument** and the
instrument is unchanged — the same BF720, the same bioimpedance estimate, the
same disagreement with DEXA that `BodyCompositionStats.primary_source` exists
to keep honest.

Introducing `source = 'beurer'` would split one continuous series into two at
an arbitrary date, break the openScale-vs-DEXA bias comparison in
`0003-units-and-metrics.md` §4a, and assert an instrument change that did not
occur. The name is slightly wrong; a split would be substantively wrong.

## 7. What the phone has to be

Web Bluetooth is a Chromium engine feature. Firefox does not implement it and
Mozilla has classed it "Harmful", so the browser choice is not cosmetic.

The target is **Brave on the bathroom Android**, which needs Web Bluetooth
switched on at `brave://flags` — Brave ships it disabled by default for
privacy reasons. Two further flags make it pleasant rather than merely
possible:

- `#enable-experimental-web-platform-features` for `getDevices()`, without
  which every drain raises the device chooser instead of reconnecting silently
- `#enable-web-bluetooth-new-permissions-backend` for persistent grants

Android also requires **Location Services enabled** for BLE scanning, at the OS
level, because a scan can infer position. The PWA cannot request its way past
this and should say so plainly when a scan finds nothing.

Brave installs a PWA as a shortcut rather than minting a WebAPK — only Chrome
and Samsung Internet do that. It costs a launcher icon and a standalone task,
and nothing functional: a shortcut still runs in the browser's context, so the
Bluetooth permission grant behaves identically.

**Bonding is the OS's job and is already done.** Web Bluetooth exposes no
pairing API; when a characteristic requires encryption, Android raises the
system pairing dialog and bonds. That phone is already bonded to the scale
through openScale, so the bond predates any code written here. It is the single
strongest reason to do this on that handset rather than anywhere else.

## 8. Deliberately not built: a staleness prompt

An earlier draft had helf notice that the last reading was three weeks old and
say so — a banner, or a Web Push from the backend. It is **not being built**,
by decision, and is recorded here so a later session does not add it as an
obvious missing safeguard.

The argument for it was that §1's ring is guarded only by remembering. The
argument against is that the user does not want to be nagged by a weight
tracker, which is a legitimate thing to not want and outranks a hypothetical.
If a reading is ever demonstrably lost to an overflowed ring, this is the first
thing to reconsider — and §9's Phase 4 is where the evidence would show up.

## 9. Order of work

1. **Spike against the real scale.** ← *the only step left.* Tap **Read
   scale** on the bathroom Android with the console open. This answers the
   three questions no amount of code can: whether history replays on
   subscribe, which unit bit the scale sets, and whether the consent code is
   accepted. Everything below is written and tested; none of it has met the
   hardware.
2. ✓ Payload parser as a pure function with fixture bytes from the spike, tested
   in both unit modes. No BLE involved, so it runs in CI.
3. ✓ `POST /api/body-composition/sync/scale` — §4. Testable without a browser,
   and the place the `source='openscale'` guarantee actually lives.
4. ✓ The drain UI on `/body-composition` — a button, a progress count, an outcome
   line distinguishing written from already-held. Feature-detect
   `navigator.bluetooth` and hide the control where it is absent rather than
   offering a button that cannot work.
5. **Run both paths for a fortnight.** openScale keeps publishing over MQTT;
   the PWA drains in parallel. Both write `source='openscale'`, so the unique
   constraint makes the second writer a no-op and the two cannot diverge —
   which is precisely what makes the overlap safe to run.
6. Retire the MQTT path **without deleting it**. `mqtt_enabled` defaults to
   False, so the lifespan does not start it and nothing connects; the service,
   its tests, the two `/api/mqtt/*` routes and the `paho-mqtt` dependency all
   stay. Only the broker on the NAS actually goes away.

   Deleting it was the original plan and it was wrong. `bcs.ts` decodes the
   Bluetooth SIG profile and nothing else, so it reads this scale and scales
   like it. openScale has drivers for around a hundred, most of them
   proprietary. The day this scale is replaced by one of those, the MQTT path
   is the way back in — and reconstructing it from git history is far more
   expensive than carrying a service that costs nothing while switched off.

   `/api/mqtt/status` therefore reports `enabled` separately from `connected`.
   Collapsed into one field, a deliberately retired ingest and a broker that
   had fallen over gave the same answer.

Phases 1–4 are reversible and touch nothing existing. Phase 6 is the only
destructive one and is gated on phase 5 producing a fortnight of agreement.

### What landed, and what it is worth

Built and green: the decoder (`frontend/src/lib/bcs.ts`, 15 tests over fixture
bytes), the drain endpoint (`backend/tests/test_api_scale_sync.py`, 5 tests),
and the UI with its two gates (`frontend/src/pages/BodyComposition.test.tsx`,
7 tests). `frontend/src/lib/scale.ts` is the BLE plumbing and is **deliberately
logic-free**, because it is the one file no test can reach.

So the tests prove the decoder handles the payloads *the spec describes*. They
prove nothing about whether the BF720 sends those payloads. Treat a green suite
here as evidence that phase 1 will be quick to debug, not as evidence that it
will pass.

Two guesses are load-bearing and will be settled in the first minute of phase
1. **The replay has no terminator**, so the drain ends after 2.5s of silence -
if the scale pauses mid-replay, a drain will truncate and the next one will
pick up the rest, which is safe but slow to notice. And **consent is written
once on connect**; if the BF720 wants `REGISTER_NEW_USER` before it will accept
`CONSENT` on an unknown slot, the pairing form is the wrong shape and needs a
registration path beside it.

## 10. What is not decided

- **Whether history replays over the standard characteristic** or needs a
  vendor-specific one. openScale marks History supported for this model, which
  is evidence but not proof about the mechanism. Phase 1 settles it.
- **Whether the characteristics require encryption at all.** If they do not,
  bonding is irrelevant and §7's last paragraph is merely reassuring.
- **What happens to openScale afterwards.** Keeping it installed costs nothing
  and is a second opinion when a reading looks wrong. Recommend keeping it and
  simply not opening it.

## 11. The condition for abandoning this

If phase 1 shows the BF720 does not in fact serve readings over the standard
Body Composition Service, **this plan is void** rather than harder. The whole
economic case is that no protocol work is needed. At that point the honest
options are the openScale-sync webhook exporter — v0.5+ has a generic webhook
and v0.6.1 added background reconciliation, which together remove the manual
step without any BLE work at all — or a headless bridge on a machine with a
real Bluetooth stack.

Not, under any circumstances, reverse-engineering a proprietary protocol in
TypeScript to save one tap.
