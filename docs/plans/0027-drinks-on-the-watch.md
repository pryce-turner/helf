# 0027 — Drinks: log drinks and see a BAC estimate on the watch

**Status**: In progress — app written, host-tested and run in the SDK's simulator 2026-11-27; not yet installed on the watch (§8)

A launcher app with a full GUI (`watch/drinks/`): log a drink by volume and
strength in a few button presses, and the main screen shows an estimated blood
alcohol concentration whose background colour changes with it. Each drink is a
small file Helf fetches like Sleep Log's chunks (0024), and the app installs
over Bluetooth like Sleep Log (0026). Asked for by the user on 2026-11-27.

## 1. What it is not

An estimate from the clock, a body weight and what was logged. It knows
nothing about food, metabolism, or what was actually in the glass, and it is
not a basis for deciding whether to drive. The screen says "Estimated BAC".

## 2. Decisions taken with the user (2026-11-27)

| Question | Answer |
|---|---|
| Where the weight comes from | **Set on the watch** (Menu → Weight), not pushed by Helf: nothing extra is written over Bluetooth, so 0026's write scope is unchanged |
| Widmark r | **0.68** |
| Drinks back to Helf | **Yes, like sleep**: one file per drink, fetched by the regular poll |
| Units | **US fl oz** and % ABV; the screens also show US standard drinks (14 g) |
| GUI framework | LVGL (not TouchGFX): its UI is plain code with committed fonts, so it builds in Docker like Sleep Log; TouchGFX's assets come from a Windows designer |

## 3. Screens and buttons

240×240 round, 64 colours, four buttons: L1 Up, L2 Down, R1 Select, R2 Back.

| Page | Shows | Buttons |
|---|---|---|
| Main | "Estimated BAC", `0.063 %`, "4 drinks, 4.0 std / zero at 11:29 AM"; background by band | Select: add a drink. Down: menu. Back: exit |
| Volume | `12` fl oz, starting from the last drink logged | Up/Down (hold to repeat), Select: next, Back: cancel |
| Strength | `5` % ABV, and what that makes in standard drinks | same |
| Confirm | `1.0` std drinks, "12 oz at 5%" | Select: log it. Back: strength |
| Menu | Undo last drink / Weight 180 lb | Up/Down, Select, Back |
| Undo | the drink that would be cancelled, how long ago | Select: undo. Back |
| Weight | `180` lb | Up/Down (hold), Select: save, Back |

Steps are fine where drinks cluster and coarse elsewhere (`Steps.hpp`):
volume 0.5 oz to 16, 1 to 32, 2 to 64; strength 0.5 % to 15, 1 to 30, 5 to
75. Holding repeats every 110 ms after 450 ms. Undo reaches back 12 hours.

Bands (`Bac.hpp`), in full-strength panel colours:

| BAC | Background | Text |
|---|---|---|
| 0 | black | white |
| under 0.02 | green | white |
| under 0.05 | yellow | black |
| under 0.08 | orange | white |
| 0.08 and up (US driving limit) | red | white |

## 4. The model and the log

**Widmark**, stepped a minute at a time: each drink's alcohol
(`oz × 29.5735 mL × ABV × 0.789 g/mL`) enters evenly over 30 minutes from when
it was logged; the body clears 0.015 %/h whenever there is any; BAC% =
grams / (lb × 453.592 × r) × 100. Drinks older than 24 h are ignored. "Zero
at" is the first minute the estimate is back to 0 with nothing still
absorbing. One 12 oz 5 % beer at 180 lb: 0.025 %.

**The log**: `/Apps/Drinks/Log/YYYYMMDD/HHMMSS.json` (local date and time;
`-2`, `-3`… for a second event in the same second), one per event, written as
`.tmp` and renamed, never changed:

    {"v":1,"kind":"drink","t":1795813200,"tz":-28800,"oz":12.0,"abv":5.0}
    {"v":1,"kind":"undo","t":1795813500,"tz":-28800,"ref":"20261127/130000"}

`t` is UTC and `tz` the offset then. An undo names the drink's stem; nothing
is deleted, so the log is the history. Settings (`weight_lb`, the last volume
and strength) are `/Apps/Drinks/settings.json`, which the sync does not fetch.

Helf's poll fetches `Log/YYYYMMDD/*.json` from any app folder
(`discoverDrinks` in `unaSync.ts`) into the `data/una/` mirror. Nothing reads
them yet: a Helf view, and whether drinks become `metric` rows (a migration,
asked for first), is the next step.

## 5. Inside the app

- **Service** (`Libs/Source/Service.cpp`): owns the files and the arithmetic.
  Starts with the GUI, leaves when it closes; nothing needs to run unseen,
  since the estimate is a function of the log and the clock. Reads the
  newest three day folders at start.
- **GUI** (`App/LVGL-GUI/`): one LVGL screen with a page per step; asks for
  `State` on every page change and every 20 s on the main page.
- **Messages** (`Commands.hpp`): the kernel's largest message is 256 bytes,
  so the GUI never gets the drink list, only `State`: BAC, band, counts,
  minutes to zero, weight, the last drink's values, and what Undo would undo.
- **Pure parts**, host-tested (`Tests/`, 170 checks, run by the Docker build
  before it builds): `Bac`, `DrinkLog`, `Steps`.

## 6. Build, install, preview

Built by `watch-build` with Sleep Log (the stage now builds every app under
`watch/`, and fetches the SDK's LVGL submodule). Published to
`data/watch-apps/Drinks/`, offered on the Watch page with its own **Install on
watch** card; after the restart it is in the watch's app list.

The SDK's LVGL simulator builds from `App/LVGL-GUI/simulator/` (needs SDL2)
and runs headless from a script: `simulator/smoke.txt` visits every page and
takes a screenshot of each. Seed `--fs-root` with a `Log/` folder of drinks
from the last hours to see the colours (the README has the recipe).

## 7. Known nits

- On the yellow band the button-hint arcs (white, amber) are faint. The SDK
  offers only white, amber, red and green for them.
- `0.0.0-dev` for every build (0026 §6).

## 8. Not yet known — the first install answers these

- That the GUI app starts from the launcher and the service answers it.
- File writes from the service under `/Apps/Drinks/Log/`, and the poll
  fetching them.
- Whether the watch's local time (`localtime_r`) is set, so "zero at" and the
  day folders are local.
- Battery and responsiveness of the 20 s refresh while the app is open.
