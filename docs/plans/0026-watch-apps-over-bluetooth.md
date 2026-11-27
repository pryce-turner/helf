# 0026 — Installing watch apps over Bluetooth

**Status**: In progress — first real install 2026-11-27 (§8); the first recorded night is next

Helf builds Sleep Log (0024) on the NAS, serves it, and the phone installs it on
the UNA Watch over the File Transfer Service, then restarts the watch so it
runs. No USB cable, no SDK on a laptop. Asked for by the user on 2026-11-27,
after the USB route (copy into `/Apps/`, power-cycle) was laid out as the
alternative.

## 1. How the watch installs an app

Read from `una-kernel-public`, not the docs, which say nothing about it:

- **An app is a `.uapp` file in `/Apps/<folder>/`.** `Backend::isBleAppFile`
  matches `2:/Apps/*/*.uapp`; a phone writing one over FTS is the official
  app's own install path (the watch shows its firmware-update progress for it).
- **Apps are registered once, at boot.** `App::Manager::scan()` walks `/Apps`
  and takes the first `.uapp` in each folder (a non-alias wins). Nothing rescans
  after an FTS write, so a new app runs from the next restart.
- **The loader reads a `.uapp` into RAM and closes it** (`Loader.cpp`), so the
  file can be replaced under a running app, which carries on as it was.
- **FTS has no read-only paths in practice.** `ERROR_READ_ONLY` is defined but
  never returned; every write goes through. The guard has to be on our side.
- **RESET restarts the watch**: Custom Command Service `0x01`, request
  `01 00`, answered `01 01`, then `Power::reboot()`. The watch ignores commands
  until notifications are on for the command characteristic.
- **Writes are flow-controlled (FTS v5).** Each WRITE_DATA is ACKed with
  `freeSpace = totalSize − contiguousEnd`: a hole-free high-water mark, so a
  lost chunk stalls the ACK at the gap; 0 comes only once the file is closed
  and committed. A resent tail after completion is re-ACKed with 0.

## 2. What was built

| Piece | Where |
|---|---|
| Build | Dockerfile `watch-versions` → `watch-build` → `watch-publisher`. Resolves the UNA SDK's `main` commit and the newest Arm GNU Toolchain (probing Arm's download URLs, since the index page refuses scripts; SHA-256 checked against Arm's `.sha256asc`), runs the host tests, builds, checks the `.uapp` carries its APP_ID and autostart flag |
| Publish | `helf-watch-app` compose service → `scripts/publish-watch-app.sh` → `data/watch-apps/SleepLog.uapp` + `watch-app.json` (size, SHA-256, CRC-32, SDK commit, toolchain). Skips an unchanged build |
| Serve | `GET /api/app/watch`, `GET /download/watch/SleepLog.uapp` (`backend/app/api/watch_app.py`) |
| Write | `FtsAppInstaller` (`frontend/src/lib/ftsInstall.ts`), a subclass of the read-only `FtsClient` |
| Install | `installApp` (same file) and `installWatchApp` (`watchAppInstall.ts`) |
| Restart | `frontend/src/lib/unaCommand.ts`, RESET only |
| UI | Watch page → *Sleep Log on the watch* → **Install on watch**, then **Restart watch** |

## 3. The write scope is the safety

`FtsClient` stays read-only by construction: the sync never gets anything
else. Writing exists only in `FtsAppInstaller`, created only for an install
session (`connect({ installFolder })`), and its `permits()` admits, for its one
folder:

- WRITE, DELETE, MOVE: only `/Apps/<folder>/<name>.uapp` or `.uapp.part`,
  directly in the folder. Never a directory, never below it, so the app's own
  recordings (`/Apps/SleepLog/Sleep/…`) cannot be touched.
- MKDIR: only `/Apps/<folder>` itself.
- WRITE_DATA: only while one of those WRITEs is open.

Checked on the encoded bytes in `send()`, the last step before the radio, and
tested by trying every way out of the folder.

RESET is likewise its own module whose only encoder produces `01 00`: the next
opcode, `0x02`, flashes firmware. 0023 §6's "never" stands for the sync.

## 4. The install sequence

1. Download from Helf; check size and CRC-32 against `watch-app.json` before
   connecting. A truncated download never reaches the watch.
2. If `/Apps/<folder>` is missing, MKDIR it. If `<file>.uapp` is already there,
   the same size, and its DIGEST matches, stop: already installed.
3. WRITE `<file>.uapp.part`, windowed (2048 bytes in flight), go-back-N on
   silence.
4. DIGEST the `.part` and compare with our CRC. On a mismatch, delete it and
   stop; the old app is untouched.
5. DELETE the old `<file>.uapp` (FatFs will not rename over a file), MOVE the
   `.part` into place, DIGEST again.
6. DELETE any other `.uapp` in the folder (the kernel takes the first it
   meets). Report, but do not touch, a folder named for the app ID, which is
   where a USB install following the SDK blog's advice would have put it.
7. Offer **Restart watch** (RESET).

Chunk size: on Android the Capacitor plugin negotiates the MTU and reports it,
so a WRITE_DATA is `MTU − 3 − 12` bytes. Web Bluetooth does not report it, so
128 bytes, halved whenever the watch answers a chunk with a protocol error
(the sign of a packet cut short); the errors already due for the oversized
burst are counted off rather than each halving again.

One connection at a time: the watch takes one and stops advertising while it
is held, so every session (poll, install, restart) goes through
`watchConnector`'s `exclusive()` and waits for the previous `disconnect()`.

## 5. Sleep Log is a Glance

0024 planned an autostarted headless **Utility**. The SDK's packer refuses one:
`app_merging.py` requires a `.gui` for every type but Glance ("Missing .gui
file … required for type Utility"). Autostart, though, is a header flag the
kernel honours for any type (`App::Manager::autoRun`), so Sleep Log is now an
autostarted **Glance** (user's choice, 2026-11-27, over adding a GUI): it runs
from boot exactly as planned, and the glances screen shows a status tile
("Idle", "Idle, still 7/20 min", "Recording since 23:14"). Unlike the SDK's
example glances, it does not exit on `EVENT_GLANCE_STOP`.

## 6. Versions

The SDK stamps `BUILD_VERSION` from `apps-*` git tags; the image builds from a
context without `.git`, so every build is `0.0.0-dev`. Helf does not rely on
it: "already installed" is the watch's CRC of the file, and Helf shows the
build date. The file on the watch is always `SleepLog.uapp`, whatever the
build called it.

## 7. Not yet known — the first install answers these

- That the watch accepts the write into `/Apps/SleepLog/` at all, and DIGEST
  agrees.
- MTU on the real Android link (expected 220, the watch's maximum), and
  write speed. 28 KB should take a few seconds.
- That RESET restarts it and the app is registered at boot, as a Glance with
  autostart: the tile appears, and the service runs without the glances screen
  ever being opened (0024 §7's checks follow from there).
- Whether opening the glances screen sends `EVENT_GLANCE_START` to the running
  autostarted service or tries to start a second one.
- On Web Bluetooth, a grant made before this change lacks the Custom Command
  Service; **Pair again** adds it. Native is unaffected.

## 8. First real install, 2026-11-27

From the Android app, after redeploying (`c046cb8`): **Install on watch**,
then **Restart watch**. After the reboot the glances screen showed the Sleep
Log tile reading "Idle". So, settled from §7:

- The watch accepts writes into `/Apps/SleepLog/`, and the `.part` + DIGEST +
  MOVE sequence completes against the real FTS.
- RESET restarts it, and the boot scan registers a `.uapp` written over
  Bluetooth.
- A Glance with the autostart flag starts at boot, and its service answers the
  glances screen (the tile was configured, so `EVENT_GLANCE_START` reached the
  service, which had no other way to draw it).

Still open: MTU and write speed on the real link (not captured), and everything
in 0024 §7, which the first recorded night answers.
