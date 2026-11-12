#include <string>

#include "pwb/object.hpp"
#include "pwb/task.hpp"
#include "pwb/value.hpp"
#include "test_support.hpp"

namespace {

using pwb::TaskObject;
using pwb::test::check;
using pwb::test::check_equal;

} // namespace

void run_task_tests() {
    TaskObject task;
    check_equal(
        pwb::task_status_name(task.status), "pending",
        "task starts pending");
    task.status = TaskObject::Status::Running;
    check_equal(
        pwb::task_status_name(task.status), "running",
        "task running status");
    task.status = TaskObject::Status::Done;
    check_equal(
        pwb::task_status_name(task.status), "done",
        "task done status");
    task.status = TaskObject::Status::Failed;
    check_equal(
        pwb::task_status_name(task.status), "failed",
        "task failed status");
    task.status = TaskObject::Status::Canceled;
    check_equal(
        pwb::task_status_name(task.status), "canceled",
        "task canceled status");
    check(
        pwb::is_nova(task.result),
        "task result starts nova");

    pwb::Arena arena;
    pwb::TaskObject* allocated = arena.allocate_task();
    check(allocated != nullptr, "arena allocates a task");
    check(
        pwb::is_task(pwb::make_task(allocated)),
        "task value tag");
    pwb::FileObject* file =
        arena.allocate_file("program.po", "read");
    check(
        pwb::is_file(pwb::make_file(file)),
        "file value tag");
    check_equal(file->path, "program.po", "file path");
    check_equal(file->mode, "read", "file mode");
}
