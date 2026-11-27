#include "Service.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>

#define LOG_MODULE_PRX      "Drinks"
#define LOG_MODULE_LEVEL    LOG_LEVEL_INFO
#include "SDK/UnaLogger/Logger.h"

#include "SDK/Kernel/KernelProviderService.hpp"
#include "SDK/Messages/MessageGuard.hpp"

#include "Steps.hpp"

using Drinks::Event;

namespace {

constexpr const char* kSettingsFile = "settings.json";
/// The newest day directories read at start: 24 h of BAC and 12 h of undo
/// never reach back further than the day before yesterday in local time.
constexpr size_t kDaysToRead = 3;

int32_t utcOffsetSeconds(std::time_t utc)
{
    std::tm local {};
    std::tm gm {};
    localtime_r(&utc, &local);
    gmtime_r(&utc, &gm);
    int32_t diff = (local.tm_hour - gm.tm_hour) * 3600 + (local.tm_min - gm.tm_min) * 60;
    const int dayDiff = local.tm_yday - gm.tm_yday;
    if (dayDiff == 1 || dayDiff < -1) diff += 86400;
    if (dayDiff == -1 || dayDiff > 1) diff -= 86400;
    return diff;
}

bool isDayName(const char* s)
{
    if (std::strlen(s) != 8) return false;
    for (int i = 0; i < 8; ++i) {
        if (s[i] < '0' || s[i] > '9') return false;
    }
    return true;
}

/** `HHMMSS.json` or `HHMMSS-N.json`: the files the service itself publishes. */
bool isEventName(const char* s)
{
    const size_t n = std::strlen(s);
    if (n < 11 || std::strcmp(s + n - 5, ".json") != 0) return false;
    for (int i = 0; i < 6; ++i) {
        if (s[i] < '0' || s[i] > '9') return false;
    }
    return n == 11 || s[6] == '-';
}

} // namespace

Service::Service(SDK::Kernel& kernel)
    : mKernel(kernel)
    , mWeightLb(Drinks::Steps::kLbDefault)
    , mLastOz(Drinks::Steps::kOzDefault)
    , mLastAbv(Drinks::Steps::kAbvDefault)
{
}

// ----------------------------------------------------------------- settings

void Service::loadSettings()
{
    auto file = mKernel.fs.file(kSettingsFile);
    if (!file || !file->open()) return;
    char buf[128] = {};
    size_t n = 0;
    file->read(buf, sizeof(buf) - 1, n);
    file->close();
    int lb = 0, oz = 0, abv = 0;
    // {"weight_lb":180,"last_oz":12.0,"last_abv":5.0}, written by saveSettings.
    const char* w = std::strstr(buf, "\"weight_lb\":");
    if (w && std::sscanf(w, "\"weight_lb\":%d", &lb) == 1) {
        mWeightLb = Drinks::Steps::clamp(lb, Drinks::Steps::kLbMin, Drinks::Steps::kLbMax);
    }
    float f = 0;
    const char* o = std::strstr(buf, "\"last_oz\":");
    if (o && std::sscanf(o, "\"last_oz\":%f", &f) == 1) oz = static_cast<int>(std::lround(f * 10));
    const char* a = std::strstr(buf, "\"last_abv\":");
    if (a && std::sscanf(a, "\"last_abv\":%f", &f) == 1) abv = static_cast<int>(std::lround(f * 10));
    if (oz) mLastOz = Drinks::Steps::clamp(oz, Drinks::Steps::kOzMin, Drinks::Steps::kOzMax);
    if (abv) mLastAbv = Drinks::Steps::clamp(abv, Drinks::Steps::kAbvMin, Drinks::Steps::kAbvMax);
}

bool Service::saveSettings()
{
    char buf[128];
    const int n = std::snprintf(buf, sizeof(buf), "{\"weight_lb\":%ld,\"last_oz\":%ld.%ld,\"last_abv\":%ld.%ld}",
                                static_cast<long>(mWeightLb), static_cast<long>(mLastOz / 10),
                                static_cast<long>(mLastOz % 10), static_cast<long>(mLastAbv / 10),
                                static_cast<long>(mLastAbv % 10));
    auto file = mKernel.fs.file(kSettingsFile);
    if (n <= 0 || !file || !file->open(true, true)) return false;
    size_t written = 0;
    const bool ok = file->write(buf, static_cast<size_t>(n), written) && written == static_cast<size_t>(n);
    file->close();
    return ok;
}

// ---------------------------------------------------------------------- log

void Service::loadFile(const char* dayName, const char* fileName, int64_t nowUtc)
{
    char path[64];
    std::snprintf(path, sizeof(path), "%s/%s/%s", Drinks::kLogDir, dayName, fileName);
    auto file = mKernel.fs.file(path);
    if (!file || !file->open()) return;
    char buf[192] = {};
    size_t n = 0;
    file->read(buf, sizeof(buf) - 1, n);
    file->close();

    Event e;
    if (!Drinks::decode(buf, n, e) || !Drinks::plausible(e)) {
        LOG_WARNING("skipping %s\n", path);
        return;
    }
    if (e.kind == Event::Kind::UNDO) {
        applyUndo(e.ref);
        return;
    }
    // Older than the BAC window and the undo window: nothing left to show.
    if (e.utc < nowUtc - 24 * 3600 || mCount >= kMaxDrinks) return;
    Logged& l = mDrinks[mCount++];
    l.drink = Drinks::Drink{e.utc, e.ozTenths, e.abvTenths};
    std::snprintf(l.stem, sizeof(l.stem), "%s/%.*s", dayName, static_cast<int>(std::strlen(fileName) - 5), fileName);
    l.undone = false;
}

void Service::loadLog(int64_t nowUtc)
{
    mCount = 0;
    struct Day { char name[9]; };
    Day days[16] = {};
    size_t dayCount = 0;
    auto root = mKernel.fs.dir(Drinks::kLogDir);
    if (!root || !root->open()) return;
    SDK::Interface::IFileSystem::ObjectInfo item {};
    while (root->readNext(item)) {
        if (!item.isDir || !isDayName(item.name)) continue;
        // Keep the newest kDaysToRead; YYYYMMDD sorts as text in date order.
        if (dayCount < sizeof(days) / sizeof(days[0])) {
            std::snprintf(days[dayCount++].name, 9, "%s", item.name);
        } else {
            char* oldest = days[0].name;
            for (size_t i = 1; i < dayCount; ++i) {
                if (std::strcmp(days[i].name, oldest) < 0) oldest = days[i].name;
            }
            if (std::strcmp(item.name, oldest) > 0) std::snprintf(oldest, 9, "%s", item.name);
        }
    }
    root->close();
    std::sort(days, days + dayCount, [](const Day& a, const Day& b) { return std::strcmp(a.name, b.name) < 0; });
    const size_t from = dayCount > kDaysToRead ? dayCount - kDaysToRead : 0;

    // Two passes, so an undo is applied whichever order the directory lists
    // files in: drinks first, then undos.
    for (int pass = 0; pass < 2; ++pass) {
        for (size_t i = from; i < dayCount; ++i) {
            char dayPath[24];
            std::snprintf(dayPath, sizeof(dayPath), "%s/%s", Drinks::kLogDir, days[i].name);
            auto d = mKernel.fs.dir(dayPath);
            if (!d || !d->open()) continue;
            SDK::Interface::IFileSystem::ObjectInfo f {};
            while (d->readNext(f)) {
                if (f.isDir || !isEventName(f.name)) continue;
                char path[64];
                std::snprintf(path, sizeof(path), "%s/%s", dayPath, f.name);
                auto file = mKernel.fs.file(path);
                if (!file || !file->open()) continue;
                char head[48] = {};
                size_t n = 0;
                file->read(head, sizeof(head) - 1, n);
                file->close();
                const bool isUndo = std::strstr(head, "\"kind\":\"undo\"") != nullptr;
                if ((pass == 0) != isUndo) loadFile(days[i].name, f.name, nowUtc);
            }
            d->close();
        }
    }
    LOG_INFO("loaded %u drinks\n", static_cast<unsigned>(mCount));
}

void Service::applyUndo(const char* ref)
{
    for (size_t i = 0; i < mCount; ++i) {
        if (std::strcmp(mDrinks[i].stem, ref) == 0) mDrinks[i].undone = true;
    }
}

/**
 * Write one event as `Log/YYYYMMDD/HHMMSS[-n].json`, via a `.tmp` and a
 * rename so Helf can never fetch half a file (it fetches only `.json`).
 */
bool Service::writeEvent(const Event& e, char* stemOut)
{
    char json[192];
    const size_t len = Drinks::encode(e, json, sizeof(json));
    if (!len) return false;

    char stem[Drinks::kRefLen + 1];
    char path[64], tmp[64];
    bool found = false;
    for (int bump = 0; bump < 10 && !found; ++bump) {
        if (!Drinks::stemFor(e.utc, e.tz, bump, stem, sizeof(stem))) return false;
        std::snprintf(path, sizeof(path), "%s/%s.json", Drinks::kLogDir, stem);
        found = !mKernel.fs.exist(path);
    }
    if (!found) return false;

    char dayDir[24];
    std::snprintf(dayDir, sizeof(dayDir), "%s/%.8s", Drinks::kLogDir, stem);
    mKernel.fs.mkdir(Drinks::kLogDir);
    mKernel.fs.mkdir(dayDir);
    std::snprintf(tmp, sizeof(tmp), "%s/%s.tmp", Drinks::kLogDir, stem);

    auto file = mKernel.fs.file(tmp);
    if (!file || !file->open(true, true)) return false;
    size_t written = 0;
    bool ok = file->write(json, len, written) && written == len;
    ok = file->flush() && ok;
    file->close();
    if (!ok || !mKernel.fs.rename(tmp, path)) {
        LOG_ERROR("write %s failed\n", path);
        mKernel.fs.remove(tmp);
        return false;
    }
    if (stemOut) std::snprintf(stemOut, Drinks::kRefLen + 1, "%s", stem);
    return true;
}

const Service::Logged* Service::lastUndoable(int64_t nowUtc) const
{
    const Logged* best = nullptr;
    for (size_t i = 0; i < mCount; ++i) {
        const Logged& l = mDrinks[i];
        if (l.undone || l.drink.utc < nowUtc - kUndoWindowSeconds) continue;
        if (!best || l.drink.utc > best->drink.utc ||
            (l.drink.utc == best->drink.utc && std::strcmp(l.stem, best->stem) > 0)) {
            best = &l;
        }
    }
    return best;
}

// -------------------------------------------------------------------- state

void Service::sendState(bool error)
{
    const int64_t now = static_cast<int64_t>(std::time(nullptr));
    Drinks::Drink active[kMaxDrinks];
    size_t n = 0;
    float std24 = 0.0f;
    for (size_t i = 0; i < mCount; ++i) {
        if (mDrinks[i].undone) continue;
        active[n++] = mDrinks[i].drink;
        if (mDrinks[i].drink.utc >= now - 24 * 3600 && mDrinks[i].drink.utc <= now) {
            std24 += Drinks::standardDrinks(mDrinks[i].drink);
        }
    }
    const Drinks::Body body{static_cast<float>(mWeightLb), 0.68f};
    const float bac = Drinks::bacAt(active, n, body, now);
    const int64_t sober = Drinks::soberAt(active, n, body, now);

    auto msg = SDK::make_msg<CustomMessage::State>(mKernel);
    if (!msg) return;
    // Fields only: the MessageBase header belongs to the kernel's allocator.
    CustomMessage::State& s = *msg;
    s.bac1e4 = static_cast<int32_t>(std::lround(bac * 10000.0f));
    s.band = static_cast<int32_t>(Drinks::band(bac));
    s.drinks24h = 0;
    for (size_t i = 0; i < n; ++i) {
        if (active[i].utc >= now - 24 * 3600 && active[i].utc <= now) ++s.drinks24h;
    }
    s.stdTenths24h = static_cast<int32_t>(std::lround(std24 * 10.0f));
    s.soberMinutes = sober > now ? static_cast<int32_t>((sober - now + 59) / 60) : 0;
    s.weightLb = mWeightLb;
    s.lastOzTenths = mLastOz;
    s.lastAbvTenths = mLastAbv;
    if (const Logged* u = lastUndoable(now)) {
        s.undoable = 1;
        s.undoOzTenths = u->drink.ozTenths;
        s.undoAbvTenths = u->drink.abvTenths;
        s.undoAgoMinutes = static_cast<int32_t>(std::max<int64_t>(0, now - u->drink.utc) / 60);
    }
    s.error = error ? 1 : 0;
    msg.send();
}

// --------------------------------------------------------------------- loop

void Service::run()
{
    LOG_INFO("Started\n");
    loadSettings();
    loadLog(static_cast<int64_t>(std::time(nullptr)));
    const uint32_t start = mKernel.sys.getTimeMs();

    while (true) {
        SDK::MessageBase* msg = nullptr;
        if (!mKernel.comm.getMessage(msg, 1000)) {
            // No GUI ever came: nobody wants this service (lifecycle §5.2).
            if (!mGuiStarted && mKernel.sys.getTimeMs() - start > kGuiGraceMs) {
                LOG_INFO("no GUI, exiting\n");
                return;
            }
            continue;
        }

        bool stop = false;
        switch (msg->getType()) {
            case SDK::MessageType::COMMAND_APP_STOP:
            case SDK::MessageType::COMMAND_APP_NOTIF_GUI_STOP:
                stop = true;
                break;
            case SDK::MessageType::COMMAND_APP_NOTIF_GUI_RUN:
                mGuiStarted = true;
                break;
            case CustomMessage::GET_STATE:
                sendState();
                break;
            case CustomMessage::LOG_DRINK: {
                auto* m = static_cast<CustomMessage::LogDrink*>(msg);
                Event e;
                e.kind = Event::Kind::DRINK;
                e.utc = static_cast<int64_t>(std::time(nullptr));
                e.tz = utcOffsetSeconds(static_cast<std::time_t>(e.utc));
                e.ozTenths = static_cast<uint16_t>(Drinks::Steps::clamp(m->ozTenths, Drinks::Steps::kOzMin, Drinks::Steps::kOzMax));
                e.abvTenths = static_cast<uint16_t>(Drinks::Steps::clamp(m->abvTenths, Drinks::Steps::kAbvMin, Drinks::Steps::kAbvMax));
                char stem[Drinks::kRefLen + 1] = {};
                const bool ok = writeEvent(e, stem);
                if (ok && mCount < kMaxDrinks) {
                    Logged& l = mDrinks[mCount++];
                    l.drink = Drinks::Drink{e.utc, e.ozTenths, e.abvTenths};
                    std::snprintf(l.stem, sizeof(l.stem), "%s", stem);
                    l.undone = false;
                }
                if (ok) {
                    mLastOz = e.ozTenths;
                    mLastAbv = e.abvTenths;
                    saveSettings();
                }
                sendState(!ok);
                break;
            }
            case CustomMessage::UNDO_LAST: {
                const int64_t now = static_cast<int64_t>(std::time(nullptr));
                bool ok = true;
                if (const Logged* u = lastUndoable(now)) {
                    Event e;
                    e.kind = Event::Kind::UNDO;
                    e.utc = now;
                    e.tz = utcOffsetSeconds(static_cast<std::time_t>(now));
                    std::snprintf(e.ref, sizeof(e.ref), "%s", u->stem);
                    ok = writeEvent(e, nullptr);
                    if (ok) applyUndo(e.ref);
                }
                sendState(!ok);
                break;
            }
            case CustomMessage::SET_WEIGHT: {
                auto* m = static_cast<CustomMessage::SetWeight*>(msg);
                mWeightLb = Drinks::Steps::clamp(m->weightLb, Drinks::Steps::kLbMin, Drinks::Steps::kLbMax);
                sendState(!saveSettings());
                break;
            }
            default:
                break;
        }
        mKernel.comm.releaseMessage(msg);
        if (stop) break;
    }
    LOG_INFO("Stopped\n");
}
