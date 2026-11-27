/**
 * Drinks service: owns the drink log and the settings file, and does the
 * arithmetic (plan 0027 §5). The GUI asks; the service answers with `State`.
 *
 * Not resident: it starts with the GUI and leaves when the GUI closes
 * (service-lifecycle.md §5.2). Nothing needs to run while nobody is looking,
 * because the estimate is a function of the log and the clock.
 *
 * The decisions live in `Bac` and the format in `DrinkLog`, both tested on
 * the host; this class is the SDK plumbing around them.
 */

#pragma once

#include <cstdint>

#include "SDK/Kernel/Kernel.hpp"

#include "Bac.hpp"
#include "Commands.hpp"
#include "DrinkLog.hpp"

class Service
{
public:
    explicit Service(SDK::Kernel& kernel);
    void run();

private:
    struct Logged {
        Drinks::Drink drink;
        char stem[Drinks::kRefLen + 1];
        bool undone;
    };

    void loadSettings();
    bool saveSettings();
    void loadLog(int64_t nowUtc);
    void loadFile(const char* dayName, const char* fileName, int64_t nowUtc);
    bool writeEvent(const Drinks::Event& e, char* stemOut);
    void applyUndo(const char* ref);
    void sendState(bool error = false);
    const Logged* lastUndoable(int64_t nowUtc) const;

    SDK::Kernel& mKernel;
    bool mGuiStarted = false;
    int32_t mWeightLb;
    int32_t mLastOz;
    int32_t mLastAbv;

    static constexpr size_t kMaxDrinks = 96;   ///< two days of heavy logging
    Logged mDrinks[kMaxDrinks] {};
    size_t mCount = 0;

    /// Undo reaches back this far: past it, a drink is history, not a mistake.
    static constexpr int64_t kUndoWindowSeconds = 12 * 3600;
    static constexpr uint32_t kGuiGraceMs = 5000;
};
