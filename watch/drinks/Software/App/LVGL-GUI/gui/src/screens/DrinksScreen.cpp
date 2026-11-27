#include "gui/screens/DrinksScreen.hpp"

#include <cstdio>
#include <ctime>
#include <initializer_list>

#include "SDK/GUI/Button.hpp"
#include "SDK/GUI/Color.hpp"
#include "SDK/GUI/LVGL/Draw.hpp"

#include "Bac.hpp"
#include "Steps.hpp"
#include "gui/Assets.hpp"

namespace Draw  = SDK::LVGL::Draw;
namespace Color = SDK::GUI::Color;
namespace Btn   = SDK::GUI::Button;
namespace Steps = Drinks::Steps;
using Hint = SDK::LVGL::Buttons;

namespace
{
constexpr uint32_t kRepeatDelayMs  = 450;
constexpr uint32_t kRepeatPeriodMs = 110;
constexpr uint32_t kRefreshMs      = 20000;

/// "12" or "12.5": tenths, without a trailing ".0".
void tenths(char* out, size_t size, int32_t v)
{
    if (v % 10 == 0) std::snprintf(out, size, "%ld", static_cast<long>(v / 10));
    else std::snprintf(out, size, "%ld.%ld", static_cast<long>(v / 10), static_cast<long>(v % 10));
}

float stdDrinks(int32_t ozTenths, int32_t abvTenths)
{
    return Drinks::standardDrinks(Drinks::Drink{0, static_cast<uint16_t>(ozTenths), static_cast<uint16_t>(abvTenths)});
}

/// Background, and the text colour that reads on it, by band. Full-strength
/// ABGR2222 colours only: the panel has four levels per channel.
struct Look {
    uint32_t bg;
    uint32_t fg;
};

Look lookFor(int32_t band)
{
    switch (static_cast<Drinks::Band>(band)) {
        case Drinks::Band::LOW:  return {Color::GREEN_MID, Color::WHITE};
        case Drinks::Band::MILD: return {Color::YELLOW, Color::BLACK};
        case Drinks::Band::HIGH: return {Color::ORANGE_DARK, Color::WHITE};
        case Drinks::Band::OVER: return {Color::RED, Color::WHITE};
        default:                 return {Color::BLACK, Color::WHITE};
    }
}
} // namespace

DrinksScreen::DrinksScreen(Model& model)
    : mModel(model)
    , mOz(Steps::kOzDefault)
    , mAbv(Steps::kAbvDefault)
    , mLb(Steps::kLbDefault)
{
    mRoot = lv_obj_create(nullptr);
    Draw::applyScreen(mRoot);
    lv_obj_set_style_bg_opa(mRoot, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_add_event_cb(mRoot, &DrinksScreen::keyEventCb, LV_EVENT_KEY, this);

    // Centred column, inside the round panel's safe area.
    mTitle = Draw::label(mRoot, &poppins_regular_18, "", 20, 36, 200, LV_TEXT_ALIGN_CENTER);
    mBig   = Draw::label(mRoot, &poppins_semibold_60, "", 0, 62, 240, LV_TEXT_ALIGN_CENTER);
    mUnit  = Draw::label(mRoot, &poppins_medium_25, "", 20, 136, 200, LV_TEXT_ALIGN_CENTER);
    mInfo  = Draw::label(mRoot, &poppins_regular_18, "", 30, 172, 180, LV_TEXT_ALIGN_CENTER);
    mItem[0] = Draw::label(mRoot, &poppins_medium_25, "", 20, 86, 200, LV_TEXT_ALIGN_CENTER);
    mItem[1] = Draw::label(mRoot, &poppins_medium_25, "", 20, 132, 200, LV_TEXT_ALIGN_CENTER);

    mButtons = std::make_unique<Hint>(mRoot);

    mRepeat = lv_timer_create(&DrinksScreen::repeatCb, kRepeatDelayMs, this);
    lv_timer_pause(mRepeat);
    mRefresh = lv_timer_create(&DrinksScreen::refreshCb, kRefreshMs, this);

    mModel.bind(this);
    show(Page::MAIN);
    mModel.requestState();
}

DrinksScreen::~DrinksScreen()
{
    mModel.bind(nullptr);
    lv_timer_delete(mRepeat);
    lv_timer_delete(mRefresh);
    lv_obj_delete(mRoot);
}

void DrinksScreen::keyEventCb(lv_event_t* e)
{
    auto* self = static_cast<DrinksScreen*>(lv_event_get_user_data(e));
    self->onKey(static_cast<uint8_t>(lv_event_get_key(e)));
}

void DrinksScreen::repeatCb(lv_timer_t* t)
{
    auto* self = static_cast<DrinksScreen*>(lv_timer_get_user_data(t));
    lv_timer_set_period(t, kRepeatPeriodMs);
    self->step(self->mRepeatDir);
}

void DrinksScreen::refreshCb(lv_timer_t* t)
{
    auto* self = static_cast<DrinksScreen*>(lv_timer_get_user_data(t));
    if (self->mPage == Page::MAIN) self->mModel.requestState();
}

void DrinksScreen::onState(const CustomMessage::State& state)
{
    // The kernel's message is released after this returns: copy the fields.
    mState.bac1e4 = state.bac1e4;
    mState.band = state.band;
    mState.drinks24h = state.drinks24h;
    mState.stdTenths24h = state.stdTenths24h;
    mState.soberMinutes = state.soberMinutes;
    mState.weightLb = state.weightLb;
    mState.lastOzTenths = state.lastOzTenths;
    mState.lastAbvTenths = state.lastAbvTenths;
    mState.undoable = state.undoable;
    mState.undoOzTenths = state.undoOzTenths;
    mState.undoAbvTenths = state.undoAbvTenths;
    mState.undoAgoMinutes = state.undoAgoMinutes;
    mState.error = state.error;
    mHaveState = true;
    mShowError = state.error != 0;
    if (mPage == Page::MAIN || mPage == Page::UNDO) render();
}

// --------------------------------------------------------------- buttons

void DrinksScreen::step(int dir)
{
    switch (mPage) {
        case Page::VOLUME:   mOz = Steps::oz(mOz, dir); break;
        case Page::STRENGTH: mAbv = Steps::abv(mAbv, dir); break;
        case Page::WEIGHT:   mLb = Steps::lb(mLb, dir); break;
        default: return;
    }
    render();
}

void DrinksScreen::onKey(uint8_t code)
{
    const bool stepper = mPage == Page::VOLUME || mPage == Page::STRENGTH || mPage == Page::WEIGHT;

    // Up/Down on a picker: step on the press, repeat while held, stop on
    // release. The click that follows a short press is ignored, or every
    // tap would count twice.
    if (stepper) {
        if (code == Btn::L1_PRESS || code == Btn::L2_PRESS) {
            mRepeatDir = code == Btn::L1_PRESS ? +1 : -1;
            step(mRepeatDir);
            lv_timer_set_period(mRepeat, kRepeatDelayMs);
            lv_timer_reset(mRepeat);
            lv_timer_resume(mRepeat);
            return;
        }
        if (code == Btn::L1_RELEASE || code == Btn::L2_RELEASE) {
            lv_timer_pause(mRepeat);
            return;
        }
        if (code == Btn::L1 || code == Btn::L2) return;
    }

    if (code != Btn::L1 && code != Btn::L2 && code != Btn::R1 && code != Btn::R2) return;
    lv_timer_pause(mRepeat);

    switch (mPage) {
        case Page::MAIN:
            if (code == Btn::R1) {
                mOz = mHaveState ? mState.lastOzTenths : Steps::kOzDefault;
                mAbv = mHaveState ? mState.lastAbvTenths : Steps::kAbvDefault;
                show(Page::VOLUME);
            } else if (code == Btn::L2) {
                mMenuIndex = 0;
                show(Page::MENU);
            } else if (code == Btn::R2) {
                mModel.exitApp();
            }
            break;
        case Page::VOLUME:
            if (code == Btn::R1) show(Page::STRENGTH);
            else if (code == Btn::R2) show(Page::MAIN);
            break;
        case Page::STRENGTH:
            if (code == Btn::R1) show(Page::CONFIRM);
            else if (code == Btn::R2) show(Page::VOLUME);
            break;
        case Page::CONFIRM:
            if (code == Btn::R1) {
                mModel.logDrink(mOz, mAbv);
                show(Page::MAIN);
            } else if (code == Btn::R2) {
                show(Page::STRENGTH);
            }
            break;
        case Page::MENU:
            if (code == Btn::L1 || code == Btn::L2) {
                mMenuIndex = 1 - mMenuIndex;
                render();
            } else if (code == Btn::R1) {
                if (mMenuIndex == 0) {
                    mModel.requestState();   // the undo target may have aged out
                    show(Page::UNDO);
                } else {
                    mLb = mHaveState ? mState.weightLb : Steps::kLbDefault;
                    show(Page::WEIGHT);
                }
            } else if (code == Btn::R2) {
                show(Page::MAIN);
            }
            break;
        case Page::UNDO:
            if (code == Btn::R1 && mHaveState && mState.undoable) {
                mModel.undoLast();
                show(Page::MAIN);
            } else if (code == Btn::R2) {
                show(Page::MENU);
            }
            break;
        case Page::WEIGHT:
            if (code == Btn::R1) {
                mModel.setWeight(mLb);
                show(Page::MAIN);
            } else if (code == Btn::R2) {
                show(Page::MENU);
            }
            break;
    }
}

// ---------------------------------------------------------------- drawing

void DrinksScreen::show(Page page)
{
    mPage = page;
    if (page == Page::MAIN) mModel.requestState();
    render();
}

void DrinksScreen::render()
{
    const bool menu = mPage == Page::MENU;
    Draw::setHidden(mBig, menu || mPage == Page::UNDO);
    Draw::setHidden(mItem[0], !menu);
    Draw::setHidden(mItem[1], !menu);
    Draw::setHidden(mUnit, menu);

    if (mPage == Page::MAIN) {
        renderMain();
        return;
    }

    // Every other page is black: the colour means the estimate, nothing else.
    lv_obj_set_style_bg_color(mRoot, Draw::rgb(Color::BLACK), LV_PART_MAIN);
    for (lv_obj_t* o : {mTitle, mBig, mUnit, mInfo}) {
        lv_obj_set_style_text_color(o, Draw::rgb(Color::WHITE), LV_PART_MAIN);
    }
    lv_obj_set_style_text_color(mTitle, Draw::rgb(Color::GRAY), LV_PART_MAIN);
    lv_obj_set_style_text_color(mInfo, Draw::rgb(Color::GRAY), LV_PART_MAIN);

    char big[16], a[16], b[16], line[64];
    switch (mPage) {
        case Page::VOLUME:
            tenths(big, sizeof(big), mOz);
            lv_label_set_text(mTitle, "Volume");
            lv_label_set_text(mBig, big);
            lv_label_set_text(mUnit, "fl oz");
            lv_label_set_text(mInfo, "Hold Up/Down to\nmove faster");
            mButtons->set(Hint::WHITE, Hint::WHITE, Hint::AMBER, Hint::WHITE);
            break;
        case Page::STRENGTH:
            tenths(big, sizeof(big), mAbv);
            tenths(a, sizeof(a), mOz);
            std::snprintf(line, sizeof(line), "%s oz is %.1f std\ndrinks", a, static_cast<double>(stdDrinks(mOz, mAbv)));
            lv_label_set_text(mTitle, "Strength");
            lv_label_set_text(mBig, big);
            lv_label_set_text(mUnit, "% ABV");
            lv_label_set_text(mInfo, line);
            mButtons->set(Hint::WHITE, Hint::WHITE, Hint::AMBER, Hint::WHITE);
            break;
        case Page::CONFIRM:
            std::snprintf(big, sizeof(big), "%.1f", static_cast<double>(stdDrinks(mOz, mAbv)));
            tenths(a, sizeof(a), mOz);
            tenths(b, sizeof(b), mAbv);
            std::snprintf(line, sizeof(line), "%s oz at %s%%\nSelect to log it", a, b);
            lv_label_set_text(mTitle, "Log this drink?");
            lv_label_set_text(mBig, big);
            lv_label_set_text(mUnit, "std drinks");
            lv_label_set_text(mInfo, line);
            mButtons->set(Hint::NONE, Hint::NONE, Hint::GREEN, Hint::WHITE);
            break;
        case Page::MENU:
            std::snprintf(line, sizeof(line), "Weight %ld lb",
                          static_cast<long>(mHaveState ? mState.weightLb : Steps::kLbDefault));
            lv_label_set_text(mTitle, "Menu");
            lv_label_set_text(mItem[0], "Undo last drink");
            lv_label_set_text(mItem[1], line);
            for (int i = 0; i < 2; ++i) {
                lv_obj_set_style_text_color(mItem[i], Draw::rgb(i == mMenuIndex ? Color::YELLOW : Color::GRAY),
                                            LV_PART_MAIN);
            }
            lv_label_set_text(mInfo, "");
            mButtons->set(Hint::WHITE, Hint::WHITE, Hint::AMBER, Hint::WHITE);
            break;
        case Page::UNDO:
            lv_label_set_text(mTitle, "Undo last drink?");
            if (mHaveState && mState.undoable) {
                tenths(a, sizeof(a), mState.undoOzTenths);
                tenths(b, sizeof(b), mState.undoAbvTenths);
                std::snprintf(line, sizeof(line), "%s oz at %s%%", a, b);
                lv_label_set_text(mUnit, line);
                std::snprintf(line, sizeof(line), "logged %ld min ago\nSelect to undo",
                              static_cast<long>(mState.undoAgoMinutes));
                lv_label_set_text(mInfo, line);
                mButtons->set(Hint::NONE, Hint::NONE, Hint::RED, Hint::WHITE);
            } else {
                lv_label_set_text(mUnit, "Nothing to undo");
                lv_label_set_text(mInfo, "in the last 12 hours");
                mButtons->set(Hint::NONE, Hint::NONE, Hint::NONE, Hint::WHITE);
            }
            break;
        case Page::WEIGHT:
            std::snprintf(big, sizeof(big), "%ld", static_cast<long>(mLb));
            lv_label_set_text(mTitle, "Body weight");
            lv_label_set_text(mBig, big);
            lv_label_set_text(mUnit, "lb");
            lv_label_set_text(mInfo, "for the BAC\nestimate");
            mButtons->set(Hint::WHITE, Hint::WHITE, Hint::AMBER, Hint::WHITE);
            break;
        default:
            break;
    }
}

void DrinksScreen::renderMain()
{
    const Look look = lookFor(mHaveState ? mState.band : 0);
    lv_obj_set_style_bg_color(mRoot, Draw::rgb(look.bg), LV_PART_MAIN);
    for (lv_obj_t* o : {mTitle, mBig, mUnit, mInfo}) {
        lv_obj_set_style_text_color(o, Draw::rgb(look.fg), LV_PART_MAIN);
    }

    char big[16], line[80];
    // Thousandths of a percent, rounded: 0.042.
    const int32_t th = ((mHaveState ? mState.bac1e4 : 0) + 5) / 10;
    std::snprintf(big, sizeof(big), "%ld.%03ld", static_cast<long>(th / 1000), static_cast<long>(th % 1000));
    lv_label_set_text(mTitle, mShowError ? "Could not save!" : "Estimated BAC");
    lv_label_set_text(mBig, big);
    lv_label_set_text(mUnit, "%");

    if (!mHaveState || mState.drinks24h == 0) {
        lv_label_set_text(mInfo, "No drinks today\nSelect to add one");
    } else {
        char when[24] = "now";
        if (mState.soberMinutes > 0) {
            const std::time_t at = std::time(nullptr) + static_cast<std::time_t>(mState.soberMinutes) * 60;
            std::tm local {};
            localtime_r(&at, &local);
            const int h12 = local.tm_hour % 12 == 0 ? 12 : local.tm_hour % 12;
            std::snprintf(when, sizeof(when), "%d:%02d %s", h12, local.tm_min, local.tm_hour < 12 ? "AM" : "PM");
        }
        std::snprintf(line, sizeof(line), "%ld drink%s, %ld.%ld std\nzero at %s", static_cast<long>(mState.drinks24h),
                      mState.drinks24h == 1 ? "" : "s", static_cast<long>(mState.stdTenths24h / 10),
                      static_cast<long>(mState.stdTenths24h % 10), when);
        lv_label_set_text(mInfo, line);
    }
    mButtons->set(Hint::NONE, Hint::WHITE, Hint::AMBER, Hint::WHITE);
}
