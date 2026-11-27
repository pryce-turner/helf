#ifndef DRINKS_ASSETS_HPP
#define DRINKS_ASSETS_HPP

#include "lvgl.h"

// The generated definitions are C, so the names must not be mangled.
#ifdef __cplusplus
extern "C" {
#endif

LV_FONT_DECLARE(poppins_semibold_60);   // numbers only: the big value
LV_FONT_DECLARE(poppins_medium_25);     // units, menu items
LV_FONT_DECLARE(poppins_regular_18);    // titles, notes

#ifdef __cplusplus
} // extern "C"
#endif

#endif // DRINKS_ASSETS_HPP
