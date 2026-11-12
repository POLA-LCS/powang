#include "pwb/task.hpp"

namespace pwb {

const char* task_status_name(TaskObject::Status status) noexcept {
    switch (status) {
        case TaskObject::Status::Pending: return "pending";
        case TaskObject::Status::Running: return "running";
        case TaskObject::Status::Done: return "done";
        case TaskObject::Status::Failed: return "failed";
        case TaskObject::Status::Canceled: return "canceled";
    }
    return "pending";
}

} // namespace pwb
