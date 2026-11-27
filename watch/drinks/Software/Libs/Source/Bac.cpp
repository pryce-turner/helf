#include "Bac.hpp"

#include <algorithm>

namespace Drinks {

float alcoholGrams(const Drink& d)
{
    return (d.ozTenths / 10.0f) * kMlPerUsFlOz * (d.abvTenths / 1000.0f) * kEthanolGramsPerMl;
}

float standardDrinks(const Drink& d)
{
    return alcoholGrams(d) / kStandardDrinkGrams;
}

namespace {

constexpr int64_t kStep = 60;

/** Grams of `d` absorbed during [t, t + kStep). */
float absorbedDuring(const Drink& d, int64_t t, const Model& m)
{
    const int64_t start = d.utc;
    const int64_t end = d.utc + static_cast<int64_t>(m.absorbSeconds);
    if (m.absorbSeconds == 0) {
        return (start >= t && start < t + kStep) ? alcoholGrams(d) : 0.0f;
    }
    const int64_t a = std::max(t, start);
    const int64_t b = std::min(t + kStep, end);
    if (b <= a) return 0.0f;
    return alcoholGrams(d) * static_cast<float>(b - a) / static_cast<float>(m.absorbSeconds);
}

/**
 * Walk the time line to `until` (or, when `stopAtZero`, to the first minute at
 * or after `notBefore` where BAC is zero and nothing is left to absorb).
 * Returns the BAC reached, and the time reached through `reached`.
 */
float walk(const Drink* drinks, size_t n, const Body& body, const Model& m, int64_t until,
           bool stopAtZero, int64_t notBefore, int64_t* reached)
{
    const float bodyGrams = body.weightLb * kGramsPerLb * body.r;
    const float elimPerStep = m.eliminationPerHour * static_cast<float>(kStep) / 3600.0f;
    const int64_t horizon = (stopAtZero ? notBefore : until);
    const int64_t windowStart = horizon - static_cast<int64_t>(m.windowSeconds);

    int64_t first = horizon;
    int64_t lastEnd = 0;
    for (size_t i = 0; i < n; ++i) {
        if (drinks[i].utc < windowStart || drinks[i].utc > horizon) continue;
        first = std::min(first, drinks[i].utc);
        lastEnd = std::max(lastEnd, drinks[i].utc + static_cast<int64_t>(m.absorbSeconds));
    }
    // Align to the minute so every caller sees the same steps.
    int64_t t = first - (((first % kStep) + kStep) % kStep);
    float bac = 0.0f;
    const int64_t hardStop = horizon + 3 * 24 * 3600;

    while (true) {
        if (!stopAtZero && t + kStep > until) break;
        if (stopAtZero && t >= notBefore && bac <= 0.0f && t >= lastEnd) break;
        if (stopAtZero && t >= hardStop) break;
        float grams = 0.0f;
        for (size_t i = 0; i < n; ++i) {
            if (drinks[i].utc < windowStart || drinks[i].utc > horizon) continue;
            grams += absorbedDuring(drinks[i], t, m);
        }
        bac += grams / bodyGrams * 100.0f;
        bac = std::max(0.0f, bac - elimPerStep);
        t += kStep;
    }
    if (reached) *reached = t;
    return bac;
}

} // namespace

float bacAt(const Drink* drinks, size_t n, const Body& body, int64_t utc, const Model& m)
{
    if (body.weightLb <= 0.0f || body.r <= 0.0f) return 0.0f;
    return walk(drinks, n, body, m, utc, false, 0, nullptr);
}

int64_t soberAt(const Drink* drinks, size_t n, const Body& body, int64_t nowUtc, const Model& m)
{
    if (body.weightLb <= 0.0f || body.r <= 0.0f) return nowUtc;
    if (bacAt(drinks, n, body, nowUtc, m) <= 0.0f) {
        bool absorbing = false;
        for (size_t i = 0; i < n; ++i) {
            if (drinks[i].utc <= nowUtc && drinks[i].utc + static_cast<int64_t>(m.absorbSeconds) > nowUtc) {
                absorbing = true;
            }
        }
        if (!absorbing) return nowUtc;
    }
    int64_t reached = nowUtc;
    walk(drinks, n, body, m, 0, true, nowUtc, &reached);
    return std::max(reached, nowUtc);
}

Band band(float bac)
{
    if (bac <= 0.0f) return Band::NONE;
    if (bac < 0.02f) return Band::LOW;
    if (bac < 0.05f) return Band::MILD;
    if (bac < 0.08f) return Band::HIGH;
    return Band::OVER;
}

} // namespace Drinks
