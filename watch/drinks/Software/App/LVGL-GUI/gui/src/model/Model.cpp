#include "gui/model/Model.hpp"
#include "gui/model/ModelListener.hpp"

#include "SDK/Kernel/KernelProviderGUI.hpp"
#include "SDK/Messages/MessageGuard.hpp"
#include "SDK/Port/LVGL/LvglPort.hpp"

#define LOG_MODULE_PRX      "Model"
#define LOG_MODULE_LEVEL    LOG_LEVEL_INFO
#include "SDK/UnaLogger/Logger.h"

Model::Model()
    : mKernel(SDK::KernelProviderGUI::GetInstance().getKernel())
{
    SDK::LVGL::Port::GetInstance().setAppLifeCycleCallback(this);
    SDK::LVGL::Port::GetInstance().setCustomMessageHandler(this);
}

void Model::requestState()
{
    SDK::send_msg<CustomMessage::GetState>(mKernel);
}

void Model::logDrink(int32_t ozTenths, int32_t abvTenths)
{
    SDK::send_msg<CustomMessage::LogDrink>(mKernel, ozTenths, abvTenths);
}

void Model::undoLast()
{
    SDK::send_msg<CustomMessage::UndoLast>(mKernel);
}

void Model::setWeight(int32_t lb)
{
    SDK::send_msg<CustomMessage::SetWeight>(mKernel, lb);
}

void Model::exitApp()
{
    SDK::LVGL::Port::GetInstance().setAppLifeCycleCallback(nullptr);
    SDK::LVGL::Port::GetInstance().setCustomMessageHandler(nullptr);
    mKernel.sys.exit();
}

void Model::onResume()
{
    // Back on screen after time away: the estimate has moved.
    requestState();
}

bool Model::customMessageHandler(SDK::MessageBase* msg)
{
    if (msg->getType() == CustomMessage::STATE && mListener) {
        mListener->onState(*static_cast<CustomMessage::State*>(msg));
    }
    return true;
}
