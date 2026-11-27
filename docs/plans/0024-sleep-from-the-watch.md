# 0024 — Sleep from the watch

**Status**: In progress — first night recorded 2026-11-26/27 (§9): HR and the start/stop rules work; acceleration was 1 Hz, fixed for the next night

Sleep scored in Helf from heart rate and wrist motion recorded on the UNA
Watch by our own app, using the Walch method. Builds on 0023, which already
fetches files off the watch every 15 minutes.

## 1. Why an app, and why Walch

The watch has no sleep tracking of its own: `local_settings.json` carries a
sleep *schedule* (alert muting), nothing more. Its built-in data is too coarse
for sleep: daily-health HR comes from 20–45 s bursts every 5 min while still
(`Activity/Fsm.hpp`), which is why 0023 §9's first file showed 3–6 minute
plateaus, and there is no motion data at all.

Apps get what the kernel does not keep (`una-sdk/Docs/SensorsLayer.md`):
calibrated accelerometer at up to 1.6 kHz, `HEART_RATE` (bpm + trust) at up to
1 Hz, worn, steps, charger and motion state. An app subscribing to HR forces
the optical sensor on continuously (`SensorBody.cpp`: a subscriber puts the
part in AUTO), so it gets 1 Hz HR instead of the bursts. Beat-to-beat timing
(`HEART_BEAT`, `PPG`) is defined in the SDK but no driver is registered for it
(`InstanceSensorLayer.cpp`), so heart-rate *variability* is out of reach here.

That fixes the method. **Walch et al. 2019** (*Sleep*; data on PhysioNet as
"Motion and heart rate from a wrist-worn wearable and labeled sleep from
polysomnography", 31 subjects) scored wake / NREM / REM against lab
polysomnography from exactly these inputs — raw wrist acceleration and
heart rate every few seconds from a consumer watch, plus a time-of-night
feature. It does not separate light from deep sleep, and neither will this:
that split lives mostly in beat-to-beat variability. Wake / NREM / REM is the
ceiling.

## 2. Shape

    watch app (records)  →  files on the watch  →  phone polls every 15 min (0023)
         →  data/una/files/…/Sleep/*.bin  →  decoder → features → model → metrics

The watch records and keeps raw data; **every calculation is in Helf**, so the
scoring can change and be re-run over stored nights without touching the watch.

## 3. When the watch records

Recording at full rate all day would be the battery's whole budget, and the
app cannot read the watch's sleep schedule (apps are confined to their own
folder). So it switches itself (`watch/sleep-log/Software/Libs/Source/SleepPolicy.cpp`):

| | Rule |
|---|---|
| Idle (always) | Accelerometer at 1 Hz, batched once a minute; worn, steps, charger and motion state, all already running for the kernel. One `MINUTE` summary a minute: sample count, largest sample-to-sample change, mean orientation |
| → Recording | Worn, off the charger, and **20 consecutive minutes** whose largest change stayed under 50 mg |
| Recording | Accelerometer ~50 Hz, HR 1 Hz, everything else as it changes |
| → Idle | **Walking** (100 steps within 10 min), **off the wrist** for 5 min, **the charger**, or **14 hours** |

The user's first idea was a 5-minute accelerometer check and an hour of
stillness. Changed, with agreement, because a snapshot every 5 minutes misses
movement between snapshots and wakes the watch to take it, and because an
hour's lead-in loses sleep onset and most of the first cycle, which carries the
night's deep sleep. Twenty minutes catches nearly all of it, and the idle
`MINUTE` summaries cover the lead-in at low resolution, so onset is still
estimable within that window. Sitting still watching TV will trigger it
sometimes; that costs battery, and Helf scores it as wake.

Rolling over in bed never stops a recording; only walking does. A bathroom trip
of a few dozen steps stays under the threshold. A longer one ends the
recording, and 20 still minutes back in bed start the next. Helf stitches a
night from however many recordings it contains.

Every threshold is a named constant (`PolicyConfig`), and the `MINUTE` and
`STEPS` records hold the values the decision was made on, so they can be
re-tuned from real nights.

## 4. On the watch: files

`Sleep/YYYYMMDD/HHMMSS.bin` in the app's folder, which FTS shows as
`/Apps/<folder>/Sleep/…`. Day directories because FTS LISTDIR refuses a
directory of more than 255 entries (0023 §3), and 10-minute chunks fill a month
past that in a week.

- A chunk is written as `.part` and renamed to `.bin` when complete. Discovery
  (`unaSync.ts`) fetches only `.bin`, so a file is fetched once, whole, and
  never changes afterwards. One growing file would be re-fetched in full every
  poll, and 0023's mirror keeps every version.
- 10-minute chunks while recording, so a 15-minute poll always has something
  finished; 6 hours while idle, where a chunk is a few KB. A mode change
  always closes the chunk, so the lead-in before a recording is available at
  once.
- Flushed to storage every minute: a reboot gives no warning
  (`service-lifecycle.md` §7). On start the app publishes any `.part` a
  reboot left behind; the decoder drops a torn last record.
- The newest 14 days are kept. The phone polls every 15 minutes, so that is a
  wide margin, and without a limit the watch fills.

The format (`watch/sleep-log/Software/Libs/Header/Format.hpp`) is an 8-byte
header and self-delimiting little-endian records: CLOCK (boot ms ↔ Unix time
and UTC offset, first in every file), ACCEL_BLOCK (≤ 255 samples, u8 ms deltas,
milli-g), HR (bpm and trust as f32), TOUCH, CHARGING, STEPS, MODE, MINUTE,
MOTION. Acceleration is the calibrated m/s² stream packed to milli-g, not raw
counts: the BMI270 defaults to ±2 g, but another consumer can change the range,
and raw counts would silently change scale with it.

**Contract kept by a shared fixture.** The C++ encoder's host test writes
`backend/tests/fixtures/sleep_log_v1.bin`, and `test_sleep_log.py` decodes it.
A format change means changing both sides and `make -C watch/sleep-log/Tests
fixture`.

## 5. Volume

Recording: ~350 B/s of acceleration plus ~13 B/s of HR, about 1.3 MB/hour,
so ~330 KB per 15-minute poll (estimated 20–40 s of Bluetooth at 0023's read
rates, unmeasured) and ~10 MB a night.

Kept forever under 0023's no-pruning rule, that is ~4 GB a year in
`data/una/`. Not a problem for months; a decision before it is one: keep raw,
compress closed nights, or keep only derived per-epoch features after scoring.
Not decided here.

## 6. In Helf

Order of work. 1–2 are in this commit.

1. ✓ **Discovery.** `unaSync.ts` fetches `/Apps/*/Sleep/YYYYMMDD/*.bin`.
2. ✓ **Decoder.** `backend/app/services/sleep_log.py`, pure, tested against
   the fixture the C++ encoder wrote.
3. **A night view, before any scoring.** HR, motion and mode over the night
   from decoded chunks, to check the first real nights by eye: did recording
   start when lying down, is HR continuous, are the timestamps sane.
4. **Features, as Walch defines them**, per 30-second epoch: activity counts
   from the acceleration, HR features (interpolated, normalised per night,
   local variability), and the time-of-night proxy. Re-derived from the
   paper and its published code, not from memory.
5. **The model.** Trained on the Walch PhysioNet data, shipped as
   coefficients. The domain shift (an Apple Watch's sensors versus this watch's)
   is real; per-night normalisation is the main defence, and the night view
   from step 3 is how to see whether it works.
6. **Metrics.** Total sleep, onset latency, wake after sleep onset,
   efficiency, REM and NREM minutes: new names in `metric_def`, so **a
   migration, and asked for before it is written** (migrations land live —
   AGENTS.md). Until then results are computed on demand from the files.

## 7. Not yet known — the first night answers these

From reading the source, untested on the watch:

- The app starts at boot as a headless autostart service. **Changed
  2026-11-27 (0026 §5):** it is an autostart `Glance`, not a `Utility`, because
  the SDK will not pack a Utility without a GUI. Its glance tile shows the mode;
  hiding the tile does not stop it.
- An app's HR subscription gives continuous 1 Hz HR, not the kernel's bursts.
- `TOUCH_DETECT` and `STEP_COUNTER` report periodically when asked for a period
  (10 s here), so a watch already worn at boot reads as worn. If touch only
  reports changes, the app never sees "worn" until the next change, and never
  starts recording.
- Sensor timestamps and `sys.getTimeMs()` share a clock (the decoder places
  every sample through CLOCK records on that assumption).
- Battery cost of a recorded night.
- The 50 mg stillness threshold. Logged per minute, so it can be re-tuned.

## 8. Not doing

- **Light vs deep sleep.** Needs beat-to-beat intervals, which this firmware
  does not expose to apps. Three roads exist and none is taken: the PixArt
  manufacturer log (`ppgCfg.manufLog` in `/debug_settings.json` writes raw PPG
  and acceleration to `/Log/PPG/` during HR sessions, readable over FTS), a
  firmware fork that registers a `HEART_BEAT` driver, or a chest strap paired
  to the phone (the watch passes only bpm through from a strap).
- **On-watch scoring.** Raw data stays the source of truth so the scoring can
  change.
- **A watch GUI.** Headless. The status glance arrived with 0026 §5, because the
  app had to be a Glance anyway.

## 9. The first night, 2026-11-26/27

Installed over Bluetooth at 9:50 PM (0026), restarted again at 10:39 PM for
the Drinks install. Nothing synced overnight (the phone's app is not kept
alive in the background yet: 0025 phase 3), so the night arrived the next day
in one catch-up sync: 46 chunks, decoded with `app/services/sleep_log.py`.
Times are local (PST).

| Check (§7) | Result |
|---|---|
| Starts at boot, headless | **Yes.** Each restart opened an idle chunk with `idle/startup`; the glance tile read "Idle" |
| Recording starts after ~20 still minutes | **Yes.** `recording/still` at **2:53 AM**, with 245 idle MINUTE summaries before it |
| Rolling over does not stop it; walking does | **Yes.** One recording from 2:53 to **10:04 AM** (`idle/walking`), as steps went 270 → 370 |
| HR about once a second, not 5-minute bursts | **Yes.** 600 HR records per 10-minute chunk, all night; 44–103 bpm, mostly 50–60 |
| Chunks every 10 min, `.part` → `.bin` | **Yes.** 41 recording chunks, no torn records |
| Sensor time and wall clock agree | **Yes.** Chunk names, CLOCK records and mode times line up to the second |
| Acceleration at ~50 Hz while recording | **No: 1 Hz.** 600 samples per chunk, the idle rate |
| Battery cost of a night | Not noted |

**The 1 Hz bug.** The SDK's `Connection::connect(period, latency)` returns
without doing anything when the sensor is already connected
(`SensorConnection.cpp`), and the accelerometer stays connected in both
modes, so the switch to the recording rate never happened. Fixed: a rate
change is now `disconnect()` then `connect()`, for the accelerometer and HR.
That is also why chunks were 15.6 KB (~26 B/s) instead of §5's ~220 KB per
10 minutes: expect that size, ~10 MB a night, from the next one, and a
catch-up sync of a whole night to take correspondingly longer (§5 estimated
the Bluetooth time).

The night is still usable for the night view (§6 step 3): continuous HR, and
1 Hz motion, which is enough to see stillness and movement, though not for
Walch's activity counts, which want the full rate.
