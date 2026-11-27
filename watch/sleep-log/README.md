# SleepLog — UNA Watch app

A headless background app (packed as an autostarted Glance, the only GUI-less
type the SDK allows; its tile shows the mode) that records heart rate and
wrist motion at full rate while you are probably asleep, and leaves the data in 10-minute files for
Helf to fetch over Bluetooth. The reasoning and the rules are in
[`docs/plans/0024-sleep-from-the-watch.md`](../../docs/plans/0024-sleep-from-the-watch.md).

## What it does

| Mode | Sensors | Written |
|---|---|---|
| Idle (always) | accelerometer at 1 Hz, batched once a minute; worn, steps, charger, motion state | one `MINUTE` summary a minute, plus state changes |
| Recording | accelerometer ~50 Hz, heart rate at 1 Hz (the sensor's maximum) | everything, in 10-minute chunks |

- **Starts recording** after 20 consecutive still minutes while worn and off the charger.
- **Stops** on sustained walking (100 steps within 10 minutes), 5 minutes off the
  wrist, the charger, or after 14 hours. Rolling over in bed does not stop it.

Files go to the app's own folder: `Sleep/YYYYMMDD/HHMMSS.bin`, which the file
transfer service shows as `/Apps/<app folder>/Sleep/…`. A chunk is written as
`.part` and renamed to `.bin` when complete, and Helf only fetches `.bin`. The
newest 14 days are kept on the watch. The format is in
[`Software/Libs/Header/Format.hpp`](Software/Libs/Header/Format.hpp).

## Layout

Follows the SDK's example apps (GlanceSteps: a service, no GUI).

```
watch/sleep-log/
  Software/App/SleepLog-CMake/CMakeLists.txt   the app build
  Software/Libs/Header, Source                  the code
    Service.*        SDK plumbing: sensors, files, the loop (watch-only)
    SleepPolicy.*    when to record — pure, host-tested
    RecordWriter.*   the file format encoder — pure, host-tested
    Format.hpp       the format, shared contract with Helf's decoder
  Tests/                                        host tests (g++, no SDK)
  Output/                                       built .uapp lands here
```

## Build and install

Normally nothing to do by hand: the `helf-watch-app` compose service builds it
on every `up` (Dockerfile `watch-build`, newest SDK and Arm toolchain) and
publishes it to `data/watch-apps/`, and the Watch page installs it over
Bluetooth: **Install on watch**, then **Restart watch** (plan 0026).

By hand, it needs the UNA SDK set up as in its `Docs/sdk-setup.md` (Arm GNU Toolchain
14.3+, CMake 3.21+, Python 3) and `UNA_SDK` pointing at it.

```bash
cd watch/sleep-log/Software/App/SleepLog-CMake
cmake -B build -G Ninja      # or your usual generator
cmake --build build
# → watch/sleep-log/Output/SleepLog.uapp (or as una-app.cmake names it)
```

Or install over USB: copy it to `/Apps/SleepLog/SleepLog.uapp` (that folder,
so the Bluetooth installer finds and replaces it later), eject, and restart the
watch. Being autostart, it starts at the next boot or on leaving USB mode.

## Host tests

```bash
make -C watch/sleep-log/Tests          # 52 checks: policy and encoder
make -C watch/sleep-log/Tests fixture  # regenerate backend/tests/fixtures/sleep_log_v1.bin
```

Run `fixture` after any format change and commit the result: Helf's decoder
test reads that file, which is what keeps the two sides in step.

## First night: what to check

Things the source suggests but nothing has measured (plan 0024 §7):

1. The app starts at boot with no GUI, and its tile on the glances screen
   (Down) reads "Idle".
2. A recording starts about 20 minutes after lying still, and `.bin` chunks
   appear under `/Apps/…/Sleep/` (Helf's Watch tab lists them as fetched).
3. Heart rate arrives about once a second while recording, not in 5-minute
   bursts.
4. Battery: note the level at bedtime and on waking.
5. The sensor timestamps and `getTimeMs()` share a clock (the decoder assumes
   so when placing samples on the wall clock).
