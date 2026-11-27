/**
 * GUI-side link to the Drinks service. Sends requests; hands every `State`
 * the service answers with to the screen. See Commands.hpp.
 */

#ifndef DRINKS_MODEL_HPP
#define DRINKS_MODEL_HPP

#include <cstdint>

#include "SDK/Interfaces/ICustomMessageHandler.hpp"
#include "SDK/Interfaces/IGuiLifeCycleCallback.hpp"
#include "SDK/Kernel/Kernel.hpp"

#include "Commands.hpp"

class ModelListener;

class Model : public SDK::Interface::IGuiLifeCycleCallback,
              public SDK::Interface::ICustomMessageHandler
{
public:
    Model();

    void bind(ModelListener* listener) { mListener = listener; }

    void requestState();
    void logDrink(int32_t ozTenths, int32_t abvTenths);
    void undoLast();
    void setWeight(int32_t lb);
    void exitApp();

protected:
    void onStart() override {}
    void onResume() override;
    void onSuspend() override {}
    void onStop() override {}
    bool customMessageHandler(SDK::MessageBase* msg) override;

private:
    ModelListener*     mListener = nullptr;
    const SDK::Kernel& mKernel;
};

#endif // DRINKS_MODEL_HPP
