#include "DrinkLog.hpp"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace Drinks {

namespace {

/** Civil date from days since 1970-01-01 (Howard Hinnant's algorithm). */
void civil(int64_t days, int& y, unsigned& m, unsigned& d)
{
    days += 719468;
    const int64_t era = (days >= 0 ? days : days - 146096) / 146097;
    const unsigned doe = static_cast<unsigned>(days - era * 146097);
    const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const unsigned mp = (5 * doy + 2) / 153;
    d = doy - (153 * mp + 2) / 5 + 1;
    m = mp < 10 ? mp + 3 : mp - 9;
    y = static_cast<int>(static_cast<int64_t>(yoe) + era * 400 + (m <= 2));
}

/** The value after `"key":` in a flat JSON object, or nullptr. */
const char* valueOf(const char* text, size_t len, const char* key)
{
    char needle[16];
    const int n = std::snprintf(needle, sizeof(needle), "\"%s\":", key);
    if (n <= 0 || static_cast<size_t>(n) >= sizeof(needle)) return nullptr;
    for (size_t i = 0; i + static_cast<size_t>(n) <= len; ++i) {
        if (std::memcmp(text + i, needle, static_cast<size_t>(n)) == 0) return text + i + n;
    }
    return nullptr;
}

bool number(const char* text, size_t len, const char* key, double& out)
{
    const char* v = valueOf(text, len, key);
    if (!v) return false;
    char* end = nullptr;
    out = std::strtod(v, &end);
    return end != v && std::isfinite(out);
}

bool string(const char* text, size_t len, const char* key, char* out, size_t size)
{
    const char* v = valueOf(text, len, key);
    if (!v || *v != '"') return false;
    ++v;
    size_t i = 0;
    while (v < text + len && *v != '"') {
        if (i + 1 >= size) return false;
        out[i++] = *v++;
    }
    if (v >= text + len) return false;
    out[i] = '\0';
    return true;
}

} // namespace

size_t stemFor(int64_t utc, int32_t tz, int bump, char* out, size_t size)
{
    const int64_t local = utc + tz;
    const int64_t days = (local >= 0 ? local : local - 86399) / 86400;
    const int64_t secs = local - days * 86400;
    int y;
    unsigned m, d;
    civil(days, y, m, d);
    const int hh = static_cast<int>(secs / 3600), mm = static_cast<int>(secs / 60 % 60), ss = static_cast<int>(secs % 60);
    const int n = bump <= 0
        ? std::snprintf(out, size, "%04d%02u%02u/%02d%02d%02d", y, m, d, hh, mm, ss)
        : std::snprintf(out, size, "%04d%02u%02u/%02d%02d%02d-%d", y, m, d, hh, mm, ss, bump + 1);
    return (n > 0 && static_cast<size_t>(n) < size) ? static_cast<size_t>(n) : 0;
}

size_t encode(const Event& e, char* out, size_t size)
{
    int n = 0;
    if (e.kind == Event::Kind::DRINK) {
        n = std::snprintf(out, size, "{\"v\":1,\"kind\":\"drink\",\"t\":%lld,\"tz\":%ld,\"oz\":%u.%u,\"abv\":%u.%u}",
                          static_cast<long long>(e.utc), static_cast<long>(e.tz),
                          e.ozTenths / 10u, e.ozTenths % 10u, e.abvTenths / 10u, e.abvTenths % 10u);
    } else if (e.kind == Event::Kind::UNDO) {
        n = std::snprintf(out, size, "{\"v\":1,\"kind\":\"undo\",\"t\":%lld,\"tz\":%ld,\"ref\":\"%s\"}",
                          static_cast<long long>(e.utc), static_cast<long>(e.tz), e.ref);
    }
    return (n > 0 && static_cast<size_t>(n) < size) ? static_cast<size_t>(n) : 0;
}

bool decode(const char* text, size_t len, Event& out)
{
    out = Event{};
    double v = 0, t = 0, tz = 0;
    char kind[8] = {};
    if (!number(text, len, "v", v) || v != 1.0) return false;
    if (!string(text, len, "kind", kind, sizeof(kind))) return false;
    if (!number(text, len, "t", t) || !number(text, len, "tz", tz)) return false;
    out.utc = static_cast<int64_t>(t);
    out.tz = static_cast<int32_t>(tz);
    if (std::strcmp(kind, "drink") == 0) {
        double oz = 0, abv = 0;
        if (!number(text, len, "oz", oz) || !number(text, len, "abv", abv)) return false;
        if (oz < 0 || oz > 6553 || abv < 0 || abv > 100) return false;
        out.kind = Event::Kind::DRINK;
        out.ozTenths = static_cast<uint16_t>(std::lround(oz * 10.0));
        out.abvTenths = static_cast<uint16_t>(std::lround(abv * 10.0));
        return true;
    }
    if (std::strcmp(kind, "undo") == 0) {
        if (!string(text, len, "ref", out.ref, sizeof(out.ref))) return false;
        out.kind = Event::Kind::UNDO;
        return true;
    }
    return false;
}

bool plausible(const Event& e)
{
    if (e.kind != Event::Kind::DRINK) return e.kind == Event::Kind::UNDO;
    return e.ozTenths >= 1 && e.ozTenths <= 1280 && e.abvTenths >= 1 && e.abvTenths <= 1000;
}

} // namespace Drinks
