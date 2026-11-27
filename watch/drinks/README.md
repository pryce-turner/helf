# Drinks — UNA Watch app

Log drinks by volume and strength; the main screen shows an estimated BAC,
with a background colour that changes with it. Each drink is a small file
Helf fetches over Bluetooth. The reasoning, the model and the screens are in
[`docs/plans/0027-drinks-on-the-watch.md`](../../docs/plans/0027-drinks-on-the-watch.md).

An estimate from a body weight, the clock and what you logged: not a measure,
and not a basis for deciding whether to drive.

## Using it

Open **Drinks** from the watch's app list.

| On | Up | Down | Select | Back |
|---|---|---|---|---|
| Main | | menu | add a drink | exit |
| Volume, Strength, Weight | more (hold) | less (hold) | next / save | back |
| Confirm | | | log it | back |
| Menu | move | move | open | back |

Set your weight once: Down → Weight. Volume and strength start from the last
drink you logged.

## Layout

Follows the SDK's Files tutorial (LVGL): a service and an LVGL GUI.

```
watch/drinks/
  Software/App/Drinks-CMake/CMakeLists.txt   the app build
  Software/App/LVGL-GUI/                     the GUI process
    gui/src/screens/DrinksScreen.cpp         every page
    gui/src/model/Model.cpp                  messages to and from the service
    assets/fonts/                            generated Poppins (see its README)
    simulator/                               the SDK's LVGL PC simulator
  Software/Libs/
    Source/Service.cpp    the service: files and arithmetic (watch-only)
    Bac.*                 the estimate — pure, host-tested
    DrinkLog.*            the file format — pure, host-tested
    Steps.hpp             the pickers' steps — pure, host-tested
    Commands.hpp          GUI <-> service messages
  Tests/                                     host tests (g++, no SDK)
  Resources/                                 launcher icons
```

## Build

Normally nothing to do: the `helf-watch-app` compose service builds it with
the other watch apps and the Watch page installs it (plan 0026). By hand,
with the UNA SDK (and its LVGL submodule) at `UNA_SDK` and the Arm GNU
Toolchain on `PATH`:

```bash
cd watch/drinks/Software/App/Drinks-CMake
cmake -B build -G Ninja && cmake --build build
# → watch/drinks/Output/Drinks_<version>.uapp
```

## Host tests

```bash
make -C watch/drinks/Tests      # 170 checks: BAC model, log format, steps
```

## Simulator

The SDK's LVGL simulator runs the real service and GUI on a PC (Linux needs
`libsdl2-dev`), headless from a script that presses buttons and takes
screenshots:

```bash
cd watch/drinks/Software/App/LVGL-GUI/simulator
cmake -S . -B build-linux -G Ninja && cmake --build build-linux
cd build/bin
./DrinksSimulator --headless --script ../../smoke.txt --out /tmp/shots --fs-root /tmp/fs
```

`--fs-root` is the app's folder. To see the colours, put drinks from the last
hour or two in it first, e.g. `/tmp/fs/Log/20261127/213000.json` holding
`{"v":1,"kind":"drink","t":<unix seconds>,"tz":0,"oz":12.0,"abv":5.0}`.
