// Task values for async and worker execution.
//
// The worker executor in N5 is deterministic: spawned work runs on the
// spawning thread against a cloned module snapshot. The task object still
// models the Python lifecycle and status strings so await, wait, cancel and
// status have the same observable behavior.

#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "pwb/value.hpp"

namespace pwb {

struct FunctionObject;
struct ModuleRuntime;
struct ErrorObject;

struct TaskObject {
    enum class Kind : std::uint8_t { Lazy, Worker };
    enum class Status : std::uint8_t {
        Pending,
        Running,
        Done,
        Failed,
        Canceled,
    };

    std::uint64_t id = 0;
    Kind kind = Kind::Lazy;
    Status status = Status::Pending;
    bool cancel_requested = false;
    bool handled = false;
    bool counted = false;
    Value result = make_nova();
    ErrorObject* error = nullptr;
    FunctionObject* function = nullptr;
    std::vector<Value> positional;
    std::vector<std::pair<std::string, Value>> named;
    Value receiver = make_nova();
    bool has_receiver = false;
    std::shared_ptr<ModuleRuntime> module_clone;
    std::string where;
    std::string frame_name;
};

const char* task_status_name(TaskObject::Status status) noexcept;

} // namespace pwb
