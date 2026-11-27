/**
 * The pickers' steps (plan 0027 §3), header-only so the GUI process can use
 * them without linking the service's sources. Values are in tenths.
 *
 * Fine where drinks cluster, coarse where they do not, so no value is more
 * than a few clicks (or one hold) away:
 *
 * - volume (oz): 0.5 to 16, 1 to 32, 2 to 64
 * - strength (%): 0.5 to 15, 1 to 30, 5 to 75
 * - weight (lb): 1, from 60 to 500
 */

#pragma once

#include <cstdint>

namespace Drinks::Steps {

constexpr int32_t kOzMin = 5, kOzMax = 640, kOzDefault = 120;
constexpr int32_t kAbvMin = 5, kAbvMax = 750, kAbvDefault = 50;
constexpr int32_t kLbMin = 60, kLbMax = 500, kLbDefault = 180;

constexpr int32_t clamp(int32_t v, int32_t lo, int32_t hi) { return v < lo ? lo : (v > hi ? hi : v); }

/** Next volume in tenths of an oz, `dir` +1 or -1. */
constexpr int32_t oz(int32_t v, int dir)
{
    // Step by the band the move starts in, going up; by the band below, going down.
    const int32_t at = dir > 0 ? v : v - 1;
    const int32_t step = at < 160 ? 5 : (at < 320 ? 10 : 20);
    return clamp(v + dir * step, kOzMin, kOzMax);
}

/** Next strength in tenths of a percent. */
constexpr int32_t abv(int32_t v, int dir)
{
    const int32_t at = dir > 0 ? v : v - 1;
    const int32_t step = at < 150 ? 5 : (at < 300 ? 10 : 50);
    return clamp(v + dir * step, kAbvMin, kAbvMax);
}

constexpr int32_t lb(int32_t v, int dir) { return clamp(v + dir, kLbMin, kLbMax); }

} // namespace Drinks::Steps
