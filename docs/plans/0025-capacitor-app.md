# 0025 — Helf as a Capacitor app (Android and iOS)

**Status**: In progress — phase 1 landed 2026-11-24 (§8); first native build on the Mac is next

One app for Android and iOS, wrapping the existing web frontend with
[Capacitor](https://capacitorjs.com), so the UNA Watch can be synced in the
background. Supersedes 0023 §4's "Web Bluetooth now, Capacitor if the phone
says so": the decision is taken, for the reasons in §1.

## 1. Why

0023 synced the watch from the PWA over Web Bluetooth, and it works — the first
sync from Android verified end to end. What Web Bluetooth cannot do is run
unattended: no Bluetooth in service workers, the page must stay open, in front,
with the screen on, and anything that unloads the tab (a browser update, the OS
reclaiming memory, a reboot) silently ends the polling. 0024 makes that worse,
because overnight polling would need a lit screen in the bedroom.

A native shell fixes exactly that and nothing else: the same web code, with the
Bluetooth stack reached through a plugin and the process kept alive by an
Android foreground service.

## 2. Decisions already taken

- **One app, both platforms, sync on both** (user, 2026-11-24). The always-on
  Android phone is the device that syncs. The iPhone will not be paired with the
  watch, but the option stays: sync is built into the iOS build too.
- **Sync is a per-device opt-in**, off by default. The watch has one connection
  slot and stops advertising while connected, so two syncing devices lock each
  other out (0023 §1).
- **The PWA stays.** In a browser the existing Web Bluetooth path keeps
  working; the native path is chosen at runtime by
  `Capacitor.isNativePlatform()`.
- **No version pinning**, per the repo-wide rule: Capacitor packages at latest
  (8.x as of writing).

## 3. Decisions for the user, with recommendations

| # | Question | Recommendation |
|---|---|---|
| a | Load the UI **from the Helf server** (`server.url`) or **bundle it into the app** | **From the server** — chosen. The UI and the sync code update with every redeploy, as the PWA does, instead of a rebuilt, re-sideloaded APK per change. Capacitor still injects its plugin bridge into a remote page. The cost: the app needs the server to open, which Helf needs anyway, and Capacitor's docs call `server.url` a development setting. Bundling is more robust offline and is the fallback if the remote mode misbehaves |
| b | The URL the phone uses for Helf | `https://helf.pryce.fyi` — chosen. HTTPS, so no cleartext exception |
| c | App id | `app.helf` (reverse-DNS, no personal name, since the repo is on GitHub) |
| d | Where native builds happen | **Android: the server** (amended 2026-11-26, §9): the Dockerfile builds the APK and a compose service signs it onto the data volume; the web UI offers it for download. Nothing is built on the Mac. **iOS: your Mac**, with Xcode, which cannot run anywhere else. Originally both were on the Mac (Android Studio and Xcode), because the admin container has no Android SDK, no Xcode and no Docker socket and the repo deliberately has no remote CI; the Mac turned out to have no JDK either, and a Dockerfile stage needed none of them |

## 4. Architecture

    Watch.tsx ──► WatchConnector (interface)
                    ├─ webBluetooth.ts   browser: today's unaWatch.ts, unchanged in behaviour
                    └─ nativeBle.ts      Capacitor: @capacitor-community/bluetooth-le
                  both produce an FtsTransport ──► FtsClient (fts.ts) ──► unaSync.ts

`fts.ts` and `unaSync.ts` are untouched: they already take a transport and an
injected `connect`. Only the connection layer has two implementations.

**`nativeBle.ts`** (plugin API checked against v8.4.0's `bleClient.d.ts`):

- `BleClient.initialize()`, then Android permissions (`BLUETOOTH_SCAN`,
  `BLUETOOTH_CONNECT`; location only below Android 12).
- Pair: on Android, `getBondedDevices()` and pick the `UNA Watch …` entry — no
  scan, no chooser. If the watch is not bonded yet, `requestDevice()` then
  `createBond()`, and Android shows the passkey prompt (0023 §9). On iOS,
  `requestDevice()`; iOS bonds itself on the first encrypted read.
- The chosen `deviceId` (a MAC address on Android, a UUID on iOS) is kept in
  local storage. Local, per device, and only a pointer — the manifest on the
  server stays the record of what was synced (0015 §4's rule).
- Connect: `connect(deviceId, onDisconnect)`, then `read` the FTS version,
  `startNotifications` on Raw Transfer, `writeWithoutResponse` for requests —
  the same calls the web layer makes, under the plugin's names.
  `onDisconnect` feeds `FtsTransport.onClose`.
- MTU: Android negotiates on connect; `getMtu()` is logged, since FTS chunk
  size follows it (0023 §3).

**Background, Android:**
`@capawesome-team/capacitor-android-foreground-service` keeps the process and
its WebView alive with a persistent notification ("Helf — syncing the watch"),
started when this device opts in and stopped when it opts out. The poll loop
itself stays in JavaScript (`pollLoop`), so there is one implementation of it.

- **Service type.** Android 14+ requires a foreground service type, and BLE
  work is `connectedDevice`. The plugin's `ServiceType` enum lists only
  Location and Microphone. Its option is the Android integer, so passing
  `FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE` (16) with the matching manifest
  entry may just work. If the plugin rejects it, the fallback is a small
  in-repo Capacitor plugin (one Kotlin service, ~100 lines).
- **Doze** does not apply while charging, and the always-on phone is always on
  its charger. Battery-optimisation exemption is still worth setting by hand
  (Settings → Apps → Helf → Battery → Unrestricted), and the Watch tab will say so.
- **WebView timers** may be throttled in the background. A 15-minute
  `setTimeout` survives throttling to ~1-minute granularity; if it is paused
  outright, that is the finding that moves the loop's timer into the native
  service (phase 3).

**Background, iOS:** `bluetooth-central` in `UIBackgroundModes` and the usage
strings in `Info.plist`. iOS does not run timers in the background, so sync on
iOS is foreground, plus reconnect-when-in-range if it is ever wanted (not
built). Fine for an opt-in nobody intends to use yet.

## 5. Files

- `frontend/capacitor.config.ts` — app id, name, `webDir: dist`, and per §3a
  `server.url` / `server.cleartext`.
- `frontend/android/`, `frontend/ios/` — generated by `npx cap add`, committed
  (Capacitor's own recommendation: the native projects are source). Manifest
  permissions and the foreground-service entries are edits to these.
- `frontend/src/lib/watchConnector.ts` — the interface and the runtime choice.
- `frontend/src/lib/webBluetooth.ts` — today's `unaWatch.ts`, renamed.
- `frontend/src/lib/nativeBle.ts` — the plugin adapter.
- `frontend/src/lib/nativeBackground.ts` — foreground service start/stop.
- `Watch.tsx` — the per-device "This phone syncs the watch" switch; pairing
  from bonded devices on native; wake lock only in the browser.

## 6. Phases

1. **Scaffold and connection layer** — buildable without any native toolchain,
   so it can be done here:
   - Capacitor packages, `capacitor.config.ts`, `npx cap add android ios`.
   - Split `unaWatch.ts` into `webBluetooth.ts` + `nativeBle.ts` behind
     `WatchConnector`. `nativeBle.ts` is tested against a mocked `BleClient`
     driving the existing `FakeWatch`, so the adapter is checked end to end
     without a radio.
   - Android manifest permissions; iOS `Info.plist` keys.
   - The opt-in switch.
2. **First native build, on the Mac.** Build the APK, sideload, pair from
   bonded devices, **Sync now** in the foreground. Settles the plugin, the
   bond, and §3a in practice.
3. **Background.** Foreground service, start polling on opt-in, check it keeps
   going with the screen off for a few hours. If WebView timers stall, move the
   interval into the service and have it wake the JS.
4. **Start on boot.** A `BOOT_COMPLETED` receiver, so a restarted phone resumes
   polling without anyone opening the app.
5. **iOS build check**, on the Mac with Xcode: builds, opens, sync available
   behind the switch. No background work beyond the plist.

## 7. What could go wrong

- **`server.url` in a shipped app** is outside Capacitor's documented use. If
  the bridge or plugins misbehave from a remote origin, switch to bundled
  assets (§3a) and set `VITE_API_BASE_URL` to the server.
- **Plugin background reconnects** are unverified. The design avoids needing
  them: every poll is a fresh `connect` to a known `deviceId`.
- **The foreground-service type** (§4). Fallback is in-repo native code.
- **Two code paths** for Bluetooth. Kept thin: both adapters only produce an
  `FtsTransport`, and the protocol, sync and poll loop exist once.

## 8. Phase 1, as landed (2026-11-24)

- Capacitor 8 core/CLI/Android/iOS, `@capacitor-community/bluetooth-le` and
  the Capawesome foreground-service plugin, unpinned.
- `capacitor.config.ts`: `app.helf`, UI from `https://helf.pryce.fyi`.
- `frontend/android/`, `frontend/ios/` generated and committed. The Android
  manifest adds the foreground service (type `connectedDevice`), its
  permissions, and `BLUETOOTH_SCAN` with `neverForLocation` (location only
  below Android 12). `Info.plist` adds the Bluetooth usage string and
  `bluetooth-central`. iOS uses Swift Package Manager, Capacitor 8's default.
- `nativeBle.ts` (`NativeWatch`) and `watchConnector.ts`. `unaWatch.ts` kept
  its name rather than becoming `webBluetooth.ts` (§5): a rename for nothing.
  `nativeBle.test.ts` runs a whole sync through a fake plugin wired to
  `FakeWatch`, and covers pairing from bonded devices, bonding when not
  bonded, iOS self-bonding, unpaired, unreachable and the passkey wait.
- The Watch tab: a per-device "This phone syncs the watch" switch that gates
  Sync now and polling, **including in the browser** — the PWA on the Android
  phone needs it ticked once. In the native app, polling starts on launch
  when the switch is on. The wake lock is browser-only.
- Not done: the foreground service is declared but not started (phase 3).

Generating the native projects needs a passwd entry, which uid 568 lacks
(`os.userInfo()` fails), so they were generated in a scratch copy with the
same `package-lock.json` and copied in. Running `npx cap sync` on the Mac is
unaffected.

## 9. The APK built and signed on the server (2026-11-26)

- The root `Dockerfile` has `frontend-deps` (Node 24, shared `npm ci`; the
  Capacitor CLI needs Node >= 22), `android-prep` (`cap sync` over only
  `capacitor.config.ts` and `android/`, with a placeholder `dist`, since
  `server.url` means the bundled assets are never shown), `android-build`
  (JDK 21 + SDK, `assembleDebug`, output `helf-unsigned.apk` plus version
  metadata) and `android-signer`. `production` does not contain the APK, so the
  web services never build any of this. Gradle reruns only for native changes.
  Removing `server.url` would mean bundling the real `dist` into `android-prep`
  and paying that rebuild every time.
- Signing is a one-shot `helf-apk` compose service, not a build step, because a
  build cannot write to the host and the key must be created on first run and
  kept. `scripts/sign-apk.sh` generates `data/android/signing.keystore` if
  absent (never overwritten), skips when the recorded source and certificate
  hashes match, else `apksigner sign` + `verify` and writes `helf.apk` and
  `helf-apk.json` atomically. A stable key is the only thing that lets an
  installed app update. No `depends_on`: signing can never block Helf.
- `GET /api/app/android` and `GET /download/helf.apk` (outside `/api/` so the
  service worker does not cache it) read `data/android/`; `AndroidAppPrompt`
  offers it to Android browsers outside the app and the PWA install prompt
  steps aside there.
- `scripts/build-android.sh` and `frontend/android/docker/` are gone: a
  Mac-built APK with a different key would be a trap.
- Still open: install on a phone, and iOS, which needs Xcode on the Mac.
