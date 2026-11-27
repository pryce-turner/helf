/**
 * Messages between the Drinks GUI and its service (plan 0027 §5).
 *
 * The kernel's largest message block is 256 bytes, so the GUI is never sent
 * the drink list: the service owns the files and the arithmetic and sends a
 * summary, `State`, in answer to every request.
 */

#pragma once

#include <cstdint>

#include "SDK/Messages/CommandMessages.hpp"
#include "SDK/Messages/MessageBase.hpp"
#include "SDK/Messages/MessageTypes.hpp"

#pragma pack(push, 4)

namespace CustomMessage {

// GUI -> Service
constexpr SDK::MessageType::Type GET_STATE  = 0x00000101;
constexpr SDK::MessageType::Type LOG_DRINK  = 0x00000102;
constexpr SDK::MessageType::Type UNDO_LAST  = 0x00000103;
constexpr SDK::MessageType::Type SET_WEIGHT = 0x00000104;
// Service -> GUI
constexpr SDK::MessageType::Type STATE      = 0x00000201;

struct GetState : public SDK::MessageBase {
    GetState() : SDK::MessageBase(GET_STATE) {}
};

struct LogDrink : public SDK::MessageBase {
    int32_t ozTenths;
    int32_t abvTenths;
    LogDrink() : SDK::MessageBase(LOG_DRINK), ozTenths(0), abvTenths(0) {}
    LogDrink(int32_t oz, int32_t abv) : LogDrink() { ozTenths = oz; abvTenths = abv; }
};

struct UndoLast : public SDK::MessageBase {
    UndoLast() : SDK::MessageBase(UNDO_LAST) {}
};

struct SetWeight : public SDK::MessageBase {
    int32_t weightLb;
    SetWeight() : SDK::MessageBase(SET_WEIGHT), weightLb(0) {}
    explicit SetWeight(int32_t lb) : SetWeight() { weightLb = lb; }
};

/** Everything the screens show, computed by the service. */
struct State : public SDK::MessageBase {
    int32_t bac1e4;          ///< BAC in % x 10000: 420 is 0.042 %
    int32_t band;            ///< Drinks::Band
    int32_t drinks24h;       ///< drinks in the last 24 h (undone ones excluded)
    int32_t stdTenths24h;    ///< their standard drinks x 10
    int32_t soberMinutes;    ///< minutes until the estimate is 0; 0 when it is
    int32_t weightLb;
    int32_t lastOzTenths;    ///< the picker's starting point
    int32_t lastAbvTenths;
    int32_t undoable;        ///< 1 when there is a drink Undo would cancel
    int32_t undoOzTenths;    ///< ... and what it is, for the confirmation
    int32_t undoAbvTenths;
    int32_t undoAgoMinutes;
    int32_t error;           ///< 1 when the last write failed

    State()
        : SDK::MessageBase(STATE), bac1e4(0), band(0), drinks24h(0), stdTenths24h(0), soberMinutes(0),
          weightLb(0), lastOzTenths(0), lastAbvTenths(0), undoable(0), undoOzTenths(0), undoAbvTenths(0),
          undoAgoMinutes(0), error(0)
    {}
};

} // namespace CustomMessage

#pragma pack(pop)
