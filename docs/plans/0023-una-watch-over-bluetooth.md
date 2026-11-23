# 0023 — The UNA Watch, polled over Bluetooth

**Status**: In progress — first real sync from Android on 2026-11-23; polling over time and workouts not yet seen

The UNA Watch (open STM32 watch, upstream `github.com/UNAWatch`) records daily
health and workouts to its own storage. This plan reads those files from an
always-on Android phone at intervals and keeps them, verified, in `data/`.

## 1. What the watch offers over BLE, and what it does not

From the upstream source (`una-kernel-public`, `una-sdk/Docs`), checked
2026-11-23:

- **No live sensor stream.** No Heart Rate service; raw sensors are for
  on-watch apps only. Over the air, the data is **stored files**.
- **File Transfer Service** `0xFEBB`, Adafruit's protocol plus UNA's v5
  extensions (windowed reads, `DIGEST` = CRC-32 of a whole file). Verified on
  the real watch from a Mac on 2026-11-22: FTS version 5, LISTDIR works, MTU
  220.
- **Custom Command Service** `554e4100-a2cf-4df8-0000-7e1e48595106` — §6.
- **Custom Android Notification Service** `554e4100-28e7-4811-0000-141f8b92ee40`
  — phone→watch notifications (CANS, the Android ANCS). Nothing to read.
- **One connection at a time.** While connected the watch stops advertising,
  so any other bonded device in range — an old phone, the Mac — can hold the
  slot and lock the poller out. From the phone that is indistinguishable from
  out of range.

## 2. What is fetched

| Path | What |
|---|---|
| `/DailyHealth/YYYYMM/dh_YYYYMMDD.json` | Finished days: steps, floors up/down, activity minutes, resting and average HR, `hrPerMinute[1440]` |
| `/Apps/<App>/Activity/YYYYMM/*.fit` | Workouts, one directory per watch app (Running, Cycling, Hiking, Treadmill, Workout…) |
| `/Apps/<App>/Activity/summary.json` | Each app's running summary |
| `/Workouts/**` except `Schedule/` | `Schedule/` holds plans a phone pushed *to* the watch |

Deliberately skipped:

- `/DailyHealth/dh.tmp` — today's binary crash-recovery state, rewritten
  constantly. Today arrives as JSON after midnight; for a live "today", §6.
- The `.fit` named in an app's `Activity/.recording` — a workout still being
  recorded. It is picked up on the first poll after it finishes.
- A file whose size changes between LISTDIR and READ (being written).
- `200005/` and similar exist on the real watch: days recorded before its clock
  was set. They are fetched like any other; the filename date is wrong, the
  bytes are what the watch wrote.

The doc's example path `/Apps/Workout/Activity/…` is right in shape: each app's
files live under `/Apps/<App>/`, and FIT-writing apps use `Activity/`. On the
real watch only `/Workouts/Schedule/` has been seen so far — the first
recorded workout settles where it lands.

## 3. The FTS client, and where the firmware differs from its doc

`frontend/src/lib/fts.ts`, pure, over an abstract transport. Read-only by
construction: only READ, READ_PACING, LISTDIR and DIGEST have encoders, and
the sender refuses every other opcode, under test.

Read from `FileTransferService.cpp` rather than the doc:

- **Errors are two bytes carrying the request opcode** (`sendErr(cmd,
  code)`): a missing file answers READ with `10 03`, not a READ_DATA.
- **mtime is microseconds**, `utc * 1_000_000`, not the nanoseconds the doc
  says. Compared as an opaque string, never interpreted, so a firmware fix
  costs one re-fetch of everything rather than silent mis-dating.
- **Any non-READ command cancels a read window.** One command in flight, always.
- **LISTDIR fails on a directory with more than 255 entries** ("cycling
  detected"). Month directories hold ≤ 31; `/Apps` and `Activity/YYYYMM`
  would need hundreds of apps or workouts in a month.

Reads request a 4096-byte window, reassemble by `chunkOffset`, and always pace
from the contiguous end, so a lost notification is re-requested. A burst ends
when the chunk at the window's end arrives or after 2 s of silence (the lost
chunk was the last one). Tested against `fakeWatch.ts`, which mirrors the
firmware, at up to ~15% random loss.

## 4. Where it runs: Web Bluetooth now, Capacitor if the phone says so

Same constraints as the scale (0015 §3): no Bluetooth in service workers, no
background, `requestDevice()` needs a tap. Two differences make polling
plausible here where it was not for the scale:

- **The watch does not sleep.** It advertises every ~1 s to bonded devices,
  so dialling the granted device should connect without the chooser's active
  scan — the thing that defeated the scale (0015 §14).
- **The grant persists.** Chrome for Android's `getDevices()` returns the
  watch after one Pair tap, so later polls need no gesture.

So the PWA polls while `/watch` is open, in front, with a screen wake lock,
the phone on a charger. If the first test (§8) shows `getDevices()` absent or
`gatt.connect()` to the granted watch failing while it advertises, the
fallback is wrapping the same code in Capacitor with
`@capacitor-community/bluetooth-le` and a foreground service. `fts.ts` and
`unaSync.ts` take a transport and a `connect`, so only `unaWatch.ts` would be
replaced.

## 5. Storage: a verified mirror, not rows

`PUT /api/watch/files?path=…` with the raw bytes and `X-Watch-Size`,
`X-Watch-Mtime`, `X-Watch-Crc32`; `GET /api/watch/files` is the manifest the
phone diffs against. **No migration.**

- The phone checks the watch's `DIGEST` against what it read over BLE; the
  server checks the CRC again against what crossed HTTP. What lands is what
  the watch hashed.
- Files go to `data/una/files/<watch path>`; changed content goes beside it as
  `<path>.v<crc32>`. Nothing is overwritten, as for the rest of `data/`.
- `data/una/manifest.jsonl` is append-only; a path's current state is its last
  line. The phone holds no state (0015 §4): clear it and it re-converges.
- Unlike the scale drain, reading is not destructive — the watch keeps its
  files — so an unreachable Helf just means the next poll fetches again.

Raw files rather than `document`/`metric` because `.fit` is binary
(`document.raw` is `json_valid`), the daily-health format is still moving
upstream (a time-stamped HR series is planned), and promotion into `metric`
needs new names in `metric_def` — a migration, and a decision about each name
and unit. That is §7, done against real files.

## 6. The Custom Command Service — better for "today", not a replacement

`CustomCommandService.cpp`. Command characteristic `…-0001-…` (write without
response + notify), event characteristic `…-0002-…` (notify). The watch ignores
commands until notifications are on.

| Cmd | Name | Read-only? | Use |
|---|---|---|---|
| `0x10` | GET_DAILY_HEALTH `{year u16, month, day}` | yes | steps, floors (**up + down summed**), activity min, RHR, AHR — **today from RAM**, past days from storage |
| `0x14` | GET_DAILY_HEALTH_HR `{year, month, day, hour}` | yes | 60 one-byte HR values for that hour; today from RAM |
| `0x12` | GET_EPO_STATUS | yes | GPS assistance data validity |
| `0x01` | RESET | **reboots the watch** | never |
| `0x02` | START_FW_UPDATE | **flashes firmware** | never |
| `0x11`, `0x13`, `0x20` | find-phone ack, reference location, media now-playing | writes state | no |
| event `0x01` | ACTIVITY_SESSION_ENDED `{appId u64}` | — | pushed only while connected |

So: **today's numbers live**, which `dh.tmp` cannot give, at the cost of a
two-byte opcode space where a typo reboots the watch. It does not replace files:
it loses the floors up/down split, has no workouts, and a whole day of HR is 24
round trips against one READ of the JSON. And the activity-ended event only
fires on a held connection, which is the battery cost connect–sync–disconnect
avoids. Not built. If a live "today" is wanted, add a separate client
whose encoder can only produce `0x10` and `0x14`, guarded like `fts.ts`.

## 7. What is not decided

- **Promotion into `metric`.** Candidate names: `steps`, `floors_up`,
  `floors_down`, `active_minutes`, `resting_hr_bpm`, `average_hr_bpm`, on one
  observation per day with `source='una'`. Needs a migration, so it waits for
  real files and an explicit go-ahead (migrations land live, AGENTS.md).
  `hrPerMinute` probably stays in the file.
- **Workouts.** Whether a `.fit` becomes anything in `workouts`, or stays
  as a file the agent can read.
- **Polling interval.** 15 minutes by default. Finished days change once a day
  and workouts a few times a week, so 30–60 is enough unless §6 is built.

## 8. First test on the phone

1. Unpair the watch from the Mac (it is the only bonded device, and it would
   take the slot). Watch: Settings → Phone → Pair.
2. Chrome on the Android phone, `chrome://flags`:
   `#enable-web-bluetooth-new-permissions-backend` on. Location on.
3. Open Helf → Body → Watch → **Pair watch**, pick `UNA Watch 418271`.
   Android should offer to pair on the first read; accept.
4. **Sync now.** Expect "N files uploaded" and the manifest count to rise.
5. **Reload the page** and tap **Sync now** again without pairing. This is the
   real test: it shows whether `getDevices()` hands back the watch and whether
   `gatt.connect()` reaches it with no chooser. Expect "nothing new".
6. Start polling at 5 min, screen on, phone on a charger, and leave it an
   hour. Then walk out of range for one poll and come back.

If step 5 fails, Web Bluetooth cannot poll this watch and §4's Capacitor
fallback is the next plan.

## 9. First real sync, 2026-11-23

From the Android phone, after bonding in Android settings (§8 was wrong to
expect Chrome to drive the bond — see below):

- **Two files, both verified** (watch DIGEST = phone CRC = server CRC):
  `/DailyHealth/202611/dh_20261121.json` (3342 bytes: 2096 steps, 13/18
  floors, 5 active min, RHR 54, AHR 77, 259 of 1440 minutes with HR, 46-127
  bpm) and `/DailyHealth/200005/dh_20000522.json` (all zeros — a day from
  before the clock was set).
- **mtime is microseconds on the real watch too**: `1795363200000000` reads
  as 2026-11-22 16:00 UTC only at 1e6 per second. §3 holds.
- **No workouts yet.** None recorded; where the first `.fit` lands is still
  open (§2).
- **Pairing is passkey entry.** The watch is DISPLAY_ONLY with MITM and
  Secure Connections mandatory (`PeripheralBlueNRG.cpp`): it shows a random
  six-digit code, typed into the phone. The first attempt failed because
  `connectWatch` disconnected on the first failed protected read, aborting the
  bond and leaving the watch on its code screen (fixed in `eed9a0c`: the read
  retries for 90s while the link is up). Bonding from Android's own Bluetooth
  settings first, then pairing in Helf, worked and is the recommended path.

