/**
 * Blood alcohol estimate from logged drinks (plan 0027).
 *
 * Pure: no SDK, tested on the host. Widmark's formula with two common
 * refinements, so the number moves the way people expect rather than jumping:
 *
 * - **Absorption.** Each drink's alcohol enters the blood evenly over
 *   `absorbSeconds` (30 min) from when it was logged, not all at once.
 * - **Elimination.** The body clears `eliminationPerHour` (0.015 %BAC/h, the
 *   usual average) whenever there is alcohol to clear, never below zero.
 *
 *   BAC% = grams / (body weight in grams x r) x 100
 *
 * The time line is stepped a minute at a time from the oldest drink still in
 * the window; drinks older than `windowSeconds` are ignored (a day is far
 * longer than anything the model could still be clearing).
 *
 * An estimate, nothing more: it knows nothing about food, metabolism or what
 * was actually in the glass.
 */

#pragma once

#include <cstddef>
#include <cstdint>

namespace Drinks {

/** One logged drink. Volume and strength in tenths, as they are picked. */
struct Drink {
    int64_t  utc = 0;        ///< when it was logged, Unix seconds
    uint16_t ozTenths = 0;   ///< US fluid ounces x 10
    uint16_t abvTenths = 0;  ///< percent alcohol by volume x 10
};

struct Body {
    float weightLb = 180.0f;
    /// Widmark body-water factor: 0.68 (user's choice, plan 0027 §2).
    float r = 0.68f;
};

struct Model {
    float    eliminationPerHour = 0.015f;   ///< %BAC per hour
    uint32_t absorbSeconds = 30u * 60u;
    uint32_t windowSeconds = 24u * 60u * 60u;
};

constexpr float kMlPerUsFlOz = 29.5735f;
constexpr float kEthanolGramsPerMl = 0.789f;
/// A US standard drink: 14 g of alcohol.
constexpr float kStandardDrinkGrams = 14.0f;
constexpr float kGramsPerLb = 453.592f;

float alcoholGrams(const Drink& d);
float standardDrinks(const Drink& d);

/** BAC in percent (g/100 mL) at `utc`. */
float bacAt(const Drink* drinks, size_t n, const Body& body, int64_t utc, const Model& m = {});

/**
 * When the estimate next reaches zero, at or after `nowUtc`, to the minute.
 * `nowUtc` itself when it is already zero and nothing is still absorbing.
 */
int64_t soberAt(const Drink* drinks, size_t n, const Body& body, int64_t nowUtc, const Model& m = {});

/** Colour bands for the main screen, by BAC. */
enum class Band : uint8_t {
    NONE = 0,   ///< 0
    LOW,        ///< under 0.02
    MILD,       ///< under 0.05
    HIGH,       ///< under 0.08
    OVER,       ///< 0.08 and up: the US legal limit for driving
};

Band band(float bacPercent);

} // namespace Drinks
