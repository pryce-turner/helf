// Host tests for the SDK-free parts of Drinks: the BAC model, the drink log's
// file format and the pickers' steps. No framework:
// `make -C watch/drinks/Tests` builds and runs them with the host compiler.

#include <cmath>
#include <cstdio>
#include <cstring>

#include "Bac.hpp"
#include "DrinkLog.hpp"
#include "Steps.hpp"

using namespace Drinks;

static int gFailures = 0;
static int gChecks = 0;

#define CHECK(cond)                                                                   \
    do {                                                                              \
        ++gChecks;                                                                    \
        if (!(cond)) {                                                                \
            ++gFailures;                                                              \
            std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);               \
        }                                                                             \
    } while (0)

#define NEAR(a, b, tol) CHECK(std::fabs((a) - (b)) <= (tol))

static constexpr int64_t T0 = 1795813200;   // 2026-11-27 21:00 UTC (13:00 PST)
static constexpr int64_t H = 3600, M = 60;

static Drink beer(int64_t t) { return Drink{t, 120, 50}; }   // 12 oz, 5%

// ---------------------------------------------------------------- grams

static void testGrams()
{
    // 12 oz of 5%: 354.9 mL x 0.05 x 0.789 = 14.0 g, one US standard drink.
    NEAR(alcoholGrams(beer(T0)), 14.0f, 0.05f);
    NEAR(standardDrinks(beer(T0)), 1.0f, 0.01f);
    // 1.5 oz of 40% and 5 oz of 12% are standard drinks too.
    NEAR(standardDrinks(Drink{T0, 15, 400}), 1.0f, 0.01f);
    NEAR(standardDrinks(Drink{T0, 50, 120}), 1.0f, 0.02f);
}

// ------------------------------------------------------------------ BAC

static void testWidmark()
{
    const Body body{180.0f, 0.68f};
    const Drink d[] = {beer(T0)};
    // Before the drink: zero.
    CHECK(bacAt(d, 1, body, T0 - M, {}) == 0.0f);
    // No elimination, instant absorption: pure Widmark.
    Model pure;
    pure.eliminationPerHour = 0.0f;
    pure.absorbSeconds = 0;
    // 14 g / (180 lb x 453.592 g x 0.68) x 100 = 0.0252 %
    NEAR(bacAt(d, 1, body, T0 + M, pure), 0.0252f, 0.0003f);
    // Absorbed over 30 min: half-way, about half.
    Model slow;
    slow.eliminationPerHour = 0.0f;
    NEAR(bacAt(d, 1, body, T0 + 15 * M, slow), 0.0126f, 0.0006f);
    NEAR(bacAt(d, 1, body, T0 + 45 * M, slow), 0.0252f, 0.0003f);
}

static void testElimination()
{
    const Body body{180.0f, 0.68f};
    const Drink d[] = {beer(T0), beer(T0), beer(T0)};   // three at once
    Model instant;
    instant.absorbSeconds = 0;
    // 0.0756 - 0.015 x 2 h = 0.0456
    NEAR(bacAt(d, 3, body, T0 + 2 * H, instant), 0.0456f, 0.0005f);
    // Gone after ~5 h, and never negative.
    CHECK(bacAt(d, 3, body, T0 + 6 * H, instant) == 0.0f);
    // Sober time: 0.0756 / 0.015 = 5.04 h after the drink.
    const int64_t sober = soberAt(d, 3, body, T0 + H, instant);
    CHECK(sober >= T0 + 5 * H && sober <= T0 + 5 * H + 5 * M);
    // Already sober, nothing absorbing: now.
    CHECK(soberAt(d, 3, body, T0 + 9 * H, instant) == T0 + 9 * H);
    // Still absorbing a drink logged a minute ago: not "now", even at 0.
    const Drink fresh[] = {beer(T0)};
    CHECK(soberAt(fresh, 1, body, T0, {}) > T0 + H);
}

static void testWindowAndBody()
{
    const Body body{180.0f, 0.68f};
    // A drink from two days ago is outside the window entirely.
    const Drink old[] = {beer(T0 - 48 * H)};
    CHECK(bacAt(old, 1, body, T0, {}) == 0.0f);
    // Lighter body, higher BAC; women's r would be higher still.
    const Drink d[] = {beer(T0)};
    Model pure;
    pure.eliminationPerHour = 0.0f;
    pure.absorbSeconds = 0;
    CHECK(bacAt(d, 1, Body{120.0f, 0.68f}, T0 + M, pure) > bacAt(d, 1, body, T0 + M, pure));
    CHECK(bacAt(d, 1, Body{0.0f, 0.68f}, T0 + M, pure) == 0.0f);
    // A drink logged in the future (clock change) is ignored.
    const Drink future[] = {beer(T0 + H)};
    CHECK(bacAt(future, 1, body, T0, {}) == 0.0f);
}

static void testBands()
{
    CHECK(band(0.0f) == Band::NONE);
    CHECK(band(0.001f) == Band::LOW);
    CHECK(band(0.02f) == Band::MILD);
    CHECK(band(0.049f) == Band::MILD);
    CHECK(band(0.05f) == Band::HIGH);
    CHECK(band(0.08f) == Band::OVER);
}

// ------------------------------------------------------------------ log

static void testStems()
{
    char s[32];
    // 2026-11-27 21:00:00 UTC is 13:00:00 in PST (-8 h).
    CHECK(stemFor(T0, -8 * 3600, 0, s, sizeof(s)) > 0 && std::strcmp(s, "20261127/130000") == 0);
    // Across midnight local: 2026-11-28 07:30 UTC is 23:30 on the 27th in PST.
    CHECK(stemFor(T0 + 10 * H + 30 * M, -8 * 3600, 0, s, sizeof(s)) > 0 && std::strcmp(s, "20261127/233000") == 0);
    CHECK(stemFor(T0, 0, 1, s, sizeof(s)) > 0 && std::strcmp(s, "20261127/210000-2") == 0);
    CHECK(stemFor(T0, 0, 0, s, 8) == 0);   // too small: refused, not truncated
}

static void testRoundTrip()
{
    Event e;
    e.kind = Event::Kind::DRINK;
    e.utc = T0;
    e.tz = -28800;
    e.ozTenths = 125;
    e.abvTenths = 55;
    char buf[160];
    const size_t n = encode(e, buf, sizeof(buf));
    CHECK(n > 0);
    CHECK(std::strcmp(buf, "{\"v\":1,\"kind\":\"drink\",\"t\":1795813200,\"tz\":-28800,\"oz\":12.5,\"abv\":5.5}") == 0);
    Event back;
    CHECK(decode(buf, n, back));
    CHECK(back.kind == Event::Kind::DRINK && back.utc == T0 && back.tz == -28800);
    CHECK(back.ozTenths == 125 && back.abvTenths == 55);

    Event u;
    u.kind = Event::Kind::UNDO;
    u.utc = T0 + 60;
    u.tz = -28800;
    std::snprintf(u.ref, sizeof(u.ref), "%s", "20261127/130000-2");
    const size_t m = encode(u, buf, sizeof(buf));
    CHECK(m > 0);
    Event ub;
    CHECK(decode(buf, m, ub));
    CHECK(ub.kind == Event::Kind::UNDO && std::strcmp(ub.ref, "20261127/130000-2") == 0);
}

static void testDecodeRejects()
{
    Event e;
    const char* bad[] = {
        "",
        "{}",
        "{\"v\":2,\"kind\":\"drink\",\"t\":1,\"tz\":0,\"oz\":12,\"abv\":5}",
        "{\"v\":1,\"kind\":\"beer\",\"t\":1,\"tz\":0,\"oz\":12,\"abv\":5}",
        "{\"v\":1,\"kind\":\"drink\",\"t\":1,\"tz\":0,\"oz\":12}",
        "{\"v\":1,\"kind\":\"drink\",\"t\":1,\"tz\":0,\"oz\":12,\"abv\":150}",
        "{\"v\":1,\"kind\":\"undo\",\"t\":1,\"tz\":0,\"ref\":\"unterminated",
        "{\"v\":1,\"kind\":\"undo\",\"t\":1,\"tz\":0,\"ref\":\"20261127/130000-2-way-too-long\"}",
    };
    for (const char* b : bad) CHECK(!decode(b, std::strlen(b), e));
    // Torn file (power loss mid-write): rejected, not misread.
    const char* torn = "{\"v\":1,\"kind\":\"drink\",\"t\":1795741200,\"tz\":0,\"oz\":12.";
    CHECK(!decode(torn, std::strlen(torn), e));
    Event zero;
    zero.kind = Event::Kind::DRINK;
    CHECK(!plausible(zero));
}

// ---------------------------------------------------------------- steps

static void testSteps()
{
    namespace S = Steps;
    CHECK(S::oz(120, +1) == 125);
    CHECK(S::oz(155, +1) == 160 && S::oz(160, +1) == 170);
    CHECK(S::oz(170, -1) == 160 && S::oz(160, -1) == 155);
    CHECK(S::oz(320, +1) == 340 && S::oz(340, -1) == 320);
    CHECK(S::oz(S::kOzMin, -1) == S::kOzMin && S::oz(S::kOzMax, +1) == S::kOzMax);
    CHECK(S::abv(50, +1) == 55 && S::abv(150, +1) == 160 && S::abv(300, +1) == 350);
    CHECK(S::abv(350, -1) == 300 && S::abv(160, -1) == 150);
    // Every value reached going up is reached again going down.
    for (int32_t v = S::kOzMin; v < S::kOzMax; v = S::oz(v, +1)) CHECK(S::oz(S::oz(v, +1), -1) == v);
    for (int32_t v = S::kAbvMin; v < S::kAbvMax; v = S::abv(v, +1)) CHECK(S::abv(S::abv(v, +1), -1) == v);
    // Beer to spirits in under 40 clicks (a few seconds held), not seventy.
    int clicks = 0;
    for (int32_t v = 50; v < 400; v = S::abv(v, +1)) ++clicks;
    CHECK(clicks <= 40);
    CHECK(S::lb(S::kLbMin, -1) == S::kLbMin && S::lb(180, +1) == 181);
}

int main()
{
    testGrams();
    testWidmark();
    testElimination();
    testWindowAndBody();
    testBands();
    testStems();
    testRoundTrip();
    testDecodeRejects();
    testSteps();
    std::printf("%d checks, %d failed\n", gChecks, gFailures);
    return gFailures == 0 ? 0 : 1;
}
