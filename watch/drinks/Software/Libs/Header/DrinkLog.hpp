/**
 * The drink log's on-watch format (plan 0027 §4). Pure, tested on the host.
 *
 * One small JSON file per event, never changed once written, so Helf's poll
 * fetches each exactly once (as for Sleep Log's chunks):
 *
 *     Log/YYYYMMDD/HHMMSS.json        local date and time of the event
 *     Log/YYYYMMDD/HHMMSS-2.json      a second event in the same second
 *
 * A drink:  {"v":1,"kind":"drink","t":1795741200,"tz":-28800,"oz":12.0,"abv":5.0}
 * An undo:  {"v":1,"kind":"undo","t":1795741500,"tz":-28800,"ref":"20261127/231500"}
 *
 * `t` is UTC seconds and `tz` the watch's UTC offset then, so Helf never has
 * to guess the zone. An undo cancels the drink whose file stem is `ref`
 * (`YYYYMMDD/HHMMSS[-n]`); nothing is ever deleted, so the log is the history.
 */

#pragma once

#include <cstddef>
#include <cstdint>

#include "Bac.hpp"

namespace Drinks {

constexpr const char* kLogDir = "Log";
/// Longest stem: "YYYYMMDD/HHMMSS-NN".
constexpr size_t kRefLen = 20;

struct Event {
    enum class Kind : uint8_t { NONE = 0, DRINK, UNDO };
    Kind    kind = Kind::NONE;
    int64_t utc = 0;
    int32_t tz = 0;
    uint16_t ozTenths = 0;
    uint16_t abvTenths = 0;
    char    ref[kRefLen + 1] = {};   ///< UNDO: the cancelled drink's stem
};

/**
 * `YYYYMMDD/HHMMSS` (bump 0) or `YYYYMMDD/HHMMSS-<bump+1>` for the local time
 * `utc + tz`. Returns the length written, 0 if it did not fit.
 */
size_t stemFor(int64_t utc, int32_t tz, int bump, char* out, size_t size);

/** One event as its file's JSON (no newline). Returns the length, 0 if it did not fit. */
size_t encode(const Event& e, char* out, size_t size);

/** Parse a file's JSON. False for anything that is not a v1 drink or undo. */
bool decode(const char* text, size_t len, Event& out);

/** Clamp to what the pickers allow, so a bad file cannot poison the estimate. */
bool plausible(const Event& e);

} // namespace Drinks
