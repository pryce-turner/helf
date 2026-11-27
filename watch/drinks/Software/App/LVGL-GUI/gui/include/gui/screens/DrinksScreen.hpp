/**
 * The one LVGL screen of Drinks, with a page per step (plan 0027 §3).
 *
 *   MAIN      BAC, coloured by band.  Select: add a drink.  Down: menu.  Back: exit.
 *   VOLUME    Up/Down (hold to repeat) fl oz.  Select: next.  Back: cancel.
 *   STRENGTH  Up/Down % ABV.                  Select: next.  Back: volume.
 *   CONFIRM   The drink in standard drinks.   Select: log it. Back: strength.
 *   MENU      Undo last drink / Weight.       Select: open.  Back: main.
 *   UNDO      What would be undone.           Select: undo.  Back: menu.
 *   WEIGHT    Up/Down lb.                     Select: save.  Back: menu.
 *
 * Buttons: L1 = Up, L2 = Down, R1 = Select, R2 = Back.
 */

#ifndef DRINKS_SCREEN_HPP
#define DRINKS_SCREEN_HPP

#include <cstdint>
#include <memory>

#include "lvgl.h"

#include "SDK/GUI/LVGL/Buttons.hpp"

#include "Commands.hpp"
#include "gui/model/Model.hpp"
#include "gui/model/ModelListener.hpp"

class DrinksScreen : public ModelListener
{
public:
    explicit DrinksScreen(Model& model);
    ~DrinksScreen() override;

    DrinksScreen(const DrinksScreen&)            = delete;
    DrinksScreen& operator=(const DrinksScreen&) = delete;

    lv_obj_t* root() const { return mRoot; }

    void onState(const CustomMessage::State& state) override;

private:
    enum class Page : uint8_t { MAIN, VOLUME, STRENGTH, CONFIRM, MENU, UNDO, WEIGHT };

    static void keyEventCb(lv_event_t* e);
    static void repeatCb(lv_timer_t* t);
    static void refreshCb(lv_timer_t* t);

    void onKey(uint8_t code);
    void step(int dir);
    void show(Page page);
    void render();
    void renderMain();

    Model&    mModel;
    lv_obj_t* mRoot = nullptr;
    lv_obj_t* mTitle = nullptr;
    lv_obj_t* mBig = nullptr;
    lv_obj_t* mUnit = nullptr;
    lv_obj_t* mInfo = nullptr;
    lv_obj_t* mItem[2] = {};
    std::unique_ptr<SDK::LVGL::Buttons> mButtons;

    lv_timer_t* mRepeat = nullptr;    ///< hold-to-repeat on Up/Down
    lv_timer_t* mRefresh = nullptr;   ///< the estimate moves with the clock
    int         mRepeatDir = 0;

    Page    mPage = Page::MAIN;
    bool    mHaveState = false;
    CustomMessage::State mState;
    int32_t mOz = 0;
    int32_t mAbv = 0;
    int32_t mLb = 0;
    int     mMenuIndex = 0;
    bool    mShowError = false;
};

#endif // DRINKS_SCREEN_HPP
