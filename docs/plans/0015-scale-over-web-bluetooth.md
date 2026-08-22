# 0015 — The scale talks to the browser

**Status**: In progress — running on real hardware; §11's premise revised

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

The client must be free to send everything it read, every time, and let the
server decide what is new.

> **Revised 2026-08-20; withdrawn 2026-08-21; reinstated 2026-08-22.** The
> conclusion below is correct — see §13 for the measurements that settle it.
> The withdrawal in §12 was written before the release write had ever been
> tried twice in a row, and was itself the error.
>
> This section assumed the scale
> replays its *whole* buffer on every connect. It does not: the BF720 sends
> only measurements it has not yet delivered. Three drains showed it — a fresh
> weighing yielded one reading, the next drain after a second weighing reported
> "1 new, 0 already held" rather than "1 new, 1 already held", and a drain with
> no weighing in between returned nothing at all.
>
> The design is unaffected and the endpoint is unchanged, but the *reason* is.
> Server-side deduplication is no longer what makes a re-drain safe — the scale
> already does that — it is what makes the client able to stay stateless
> without depending on the scale's bookkeeping being right. Keep it: a scale
> that forgets what it delivered would otherwise duplicate history, and that
> failure is silent.

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

1. ✓ **Spike against the real scale.** Done, on desktop Chrome and on
   Android. The scale connects, bonds, accepts the consent code, and yields
   readings; the unit bit is read correctly (197.89 lb against a last-known
   191.3 — a double conversion would have written ~436). Two things only
   hardware could have taught: the app's Current Time write *fixes the scale's
   clock*, so a reset scale stamps correctly from the first drain onward; and
   `gatt.connect()` is what wakes a sleeping scale, where
   `watchAdvertisements()` cannot, because a sleeping peripheral advertises
   nothing.
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

- ~~Whether history replays over the standard characteristic.~~ ~~**Answered:**
  measurements arrive on the standard characteristics, but only the undelivered
  ones.~~ **Settled properly in §12:** they arrive on the standard
  characteristics, all of them, once asked for over the vendor service.
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

## 12. The history has to be asked for, and §2's premise was half right

**2026-08-21.** §2 says the BF720 speaks standard services and therefore needs
no protocol work. That is true of *decoding* and false of *access*, and the gap
between those two cost the best part of a day.

The SIG profile can consent to a slot and can carry a measurement. It cannot
enumerate the slots a scale already has, and it has no verb for "send me what
you stored". Both of those live on Beurer's vendor service `0000ffff-…`, which
openScale's `StandardBeurerSanitasHandler` drives for the BF105/720:

| Characteristic | What it does |
|---|---|
| `0x0001` | Write `0x00` → the scale streams its on-device users. Write `0x10 + n` → the scale **shows slot n's consent code on its own display** |
| `0x0002` | Three-character initials |
| `0x0004` | Activity level 1-5, which feeds its bioimpedance model |
| `0x0006` | Write `0x00` → **release the consented user's stored readings** |

`0x0006` is the byte the whole feature turned on. openScale calls it
`TAKE_MEASUREMENT`, which is why reading its source did not immediately suggest
it: nothing can make a scale weigh an absent person. What it does is release
the history.

### What this corrects

- **§3 stands, for a different reason.** The buffer does make on-demand
  draining sufficient — but the buffer belongs to the scale's *on-device user*,
  not to the client's slot, and it is not handed over unasked.
- **§4's amendment of 2026-08-20 stands after all.** It was withdrawn here on
  first writing and that was wrong — see §13. The scale really does send only
  what it has not yet delivered; the 08-20 drains reached that conclusion for
  partly the wrong reason, but the conclusion held.
- **§10's open question is still open.** It asked whether several weighings
  between drains all arrive or only the most recent. Nothing observed so far
  has had more than one reading pending, so it remains untested.
- **§11 is not triggered.** Reading four characteristics out of a GPL driver
  that names them is not "reverse-engineering a proprietary protocol", which is
  what that section forbids. Nothing here was derived from a packet capture.

### One user, one slot, and no provisioning

Helf attaches to **P01 and only P01**, and `REGISTER_NEW_USER` is deleted
rather than guarded. There is one person in this database; there is one user on
the scale.

Registering is what produced the confusion above. A refused consent used to
fall through to allocating a fresh slot, which always succeeded, always came
back empty, and always looked like a scale with no history — while quietly
consuming slots 2 and 3 and splitting the record across users nobody steps on
as. A scale that grows a user per failed pairing is worse than one that refuses
to pair.

The same list is where P01's **profile** comes from. It carries height, date
of birth and sex, so those are written into the User Data Service slot from the
scale's own record rather than typed into Helf beside it. The pairing form asks
for one thing, the consent code.

That is not only less to type. The slot's profile is what the scale's
bioimpedance model runs on, and a second copy maintained by hand is a copy free
to disagree with the P01 being stepped on — silently, since the only symptom is
body fat computed against the wrong height.

So the failure modes are now all terminal and all named:

- No P01 in the registry → error naming the slots that *are* there.
- No users at all → error saying to set P01 up on the scale.
- Wrong consent code → **the scale is told to print the right one on its
  display** before the error is raised, because the code is never readable over
  the air and this is the only way to recover one.

That last one is why the pairing form now tells you to enter anything if you do
not know the code. Being refused once is the documented way to learn it.

## 13. What a working drain actually does, measured

**2026-08-22.** First day the whole path worked. Three drains against a
freshly reset scale with P01 configured on the control unit:

| Drain at | Reading it returned | Gap |
|---|---|---|
| 10:36:51 | observed 09:56:24 | 40 minutes |
| 10:38:35 | observed 10:37:42 | 1 minute |
| 10:48:51 | observed 10:48:29 | 22 seconds |
| 10:51 | *nothing* | — |

Two things fall out of that table, and they pull in opposite directions.

**Stored readings are real.** The first drain returned a weighing taken forty
minutes earlier, with nobody standing on the scale. That is the feature: weigh
whenever, collect later. It is the thing §12 was written to establish and it
holds.

**Delivered readings are not re-sent.** The fourth drain, with no weighing in
between, returned nothing at all. So the scale marks what it hands over and
does not hand it over again — which is exactly what §4's 2026-08-20 amendment
said, and which §12 withdrew on the reasoning that those drains had been
reading an empty slot. Both things were true at once: the slot *was* empty, and
the scale *does* track delivery. Withdrawing the amendment threw out a correct
finding along with the wrong reason for it.

The lesson is narrow and worth keeping: an explanation that accounts for an
observation does not thereby displace every other explanation of it.

### `skipped` is a safety net, not the usual path

Server-side deduplication was justified in §4 as what makes a re-drain safe.
Re-drains turn out to be empty, so `skipped` is 0 on essentially every drain.

Keep the `UNIQUE (observed_at, source)` constraint — a scale that lost track of
what it had delivered would otherwise duplicate history silently, and that is a
worse failure than a redundant check. But the drain's result line no longer
leads with the count, because "0 already held" on every single drain read as
though something had been dropped.

### Still untested

Whether the scale holds **more than one** undelivered reading. Every drain
above had exactly one pending, so nothing here distinguishes "releases all
pending readings" from "releases the most recent". §10's question survives, and
two weighings before one drain settles it.

### Bioimpedance, and the proof the profile write matters

Before (Aug 20, against a slot nothing had written) and after (Aug 22, with
P01's own height in the slot):

```
162  2026-08-20  198.13 lb   fat —      muscle —     water —      bmi 31.0
165  2026-08-22  196.85 lb   fat 25.5   muscle 38.5  water 49.89  bmi 28.5
```

The BMI shift on an almost unchanged weight is the whole story: the earlier
rows were computed against a default height, and everything that needs a real
one was simply absent. Copying P01's profile into the slot is what turned four
empty columns into four populated ones.

## 14. Waking a sleeping scale: the chooser is the mechanism

**2026-08-22.** Reported symptom: with the scale asleep, the first tap errors,
the second raises the device chooser, and picking it from the chooser wakes and
drains.

Three explanations were tried on this, in order, and the first two were wrong.
They are written down because each one *fit the evidence available at the time*
and each cost a round trip through real hardware to kill.

**Wrong #1: the grant holds a stale address.** The scale sleeps and comes back
on a different address, so `getDevices()` hands back something undialable and
the chooser fixes it by rescanning. `connect()` acted on this by calling
`forget()` after a failed wake. Killed by measurement: with the scale asleep,
`watchAdvertisements()` received four advertisements in 25s (first at 15.5s,
RSSI −53), so Chrome had the *current* address, and `gatt.connect()` timed out
regardless. Forgetting a good grant only forced the chooser onto the next tap
and made the ceremony worse.

**Wrong #2: the failed attempts do the waking.** After that probe, a second
`gatt.connect()` succeeded instantly with no chooser — so `gatt.connect()`
rouses the radio and merely times out doing it. `connect()` acted on this by
retrying, waiting for an advertisement, and retrying again. Killed by the user
on real hardware: still "The scale did not wake up." The instant success in the
probe came from the scale being recently connected, not from the failed attempt
that preceded it. A confound, read as a mechanism.

**What holds.** The chooser wakes it and nothing else tried does. The most
plausible reason is that Chrome runs an **active** scan to populate the chooser
— scan requests the peripheral must answer — where `watchAdvertisements()`
listens passively and pokes nothing. That remains a *hypothesis*: the third
option, `navigator.bluetooth.requestLEScan()`, would test it directly, and on
this Mac it hangs without resolving and demands a permission prompt per call.

So `connect()` is now nothing but `requestDevice()`. No `getDevices()`, no
remembered-device path, no advertisement wait, no automatic `forget()`. One tap
raises the chooser, the scale is picked, it wakes and drains.

### The fallback is a second tap, and it is the UI's job

Going chooser-only fixed waking and broke the common case: an awake scale asked
to be picked from a list every single drain, for no reason.

There is no way to try the quiet path and fall back automatically. Transient
user activation expires about five seconds after the click, so by the time a
remembered device has failed, `requestDevice()` throws "must be handling a user
gesture" instead of opening anything. **The fallback has to be a fresh
gesture** — which means it has to be a button, which means the UI has to know
the difference.

So `connect(pick)` has two paths and never chooses between them:

- `pick: false` — dial the remembered device, one attempt, 5s. An awake BF720
  connects near-instantly, so this is a verdict rather than a wait. Fails with
  `ScaleAsleepError`.
- `pick: true` — open the chooser, which wakes it.

`ScaleAsleepError` earns its own class because the page acts on it rather than
printing it: the button becomes **Wake scale** and the message explains that
picking the BF720 from the list is what rouses it. Tapping that supplies the
activation the chooser needs.

An asleep scale is styled as ordinary text, not as an error. It is the expected
state of a bathroom scale, and colouring it red taught the eye to ignore the
place real failures appear.

### Still open, and where to test it

Whether `requestLEScan()` can wake the scale without the picker — and if so,
whether the drain can be one tap and no list. **Test it on the Android phone,
not on a laptop.** Chrome's scanning differs by platform, and the phone is the
only machine whose behaviour matters here; every measurement above was taken on
macOS, which is a proxy for it and not a good one.

> The wider lesson from the three attempts: an explanation that accounts for an
> observation does not thereby displace the other explanations of it. Both
> wrong theories fit every datum available when they were adopted. What settled
> the question was not more reasoning, it was the user tapping a button.
