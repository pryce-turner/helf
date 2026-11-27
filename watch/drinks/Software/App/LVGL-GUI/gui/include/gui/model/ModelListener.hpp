#ifndef DRINKS_MODEL_LISTENER_HPP
#define DRINKS_MODEL_LISTENER_HPP

#include "Commands.hpp"

/** Events the Model raises towards the screen. */
class ModelListener
{
public:
    virtual ~ModelListener() = default;
    /// The service's summary, after every request.
    virtual void onState(const CustomMessage::State& state) = 0;
};

#endif // DRINKS_MODEL_LISTENER_HPP
