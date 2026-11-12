#include "pwb/vm.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cctype>
#include <cstdlib>
#include <cwctype>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <new>
#include <optional>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "pwb/bundle.hpp"
#include "pwb/error.hpp"
#include "pwb/errors.hpp"
#include "pwb/image.hpp"
#include "pwb/meta.hpp"
#include "pwb/module.hpp"
#include "pwb/object.hpp"
#include "pwb/opcodes.hpp"
#include "pwb/opcodes_generated.hpp"
#include "pwb/project.hpp"
#include "pwb/value.hpp"
#include "pwb/verifier.hpp"

namespace pwb {
namespace {

enum class TransferKind : std::uint8_t { None, Jump, Return };

struct Transfer {
    TransferKind kind = TransferKind::None;
    std::int32_t target = -1;
};

struct HandlerEntry {
    std::int32_t start_ip = 0;
    std::int32_t end_ip = 0;
    std::int32_t catch_ip = -1;
    std::int32_t finally_ip = -1;
    std::int32_t resume_ip = -1;
    std::uint32_t stack_depth = 0;
    std::uint32_t local_watermark = 0;
    std::uint32_t scope_depth = 0;
    std::uint8_t kind = 0;
    std::uint8_t state = 0;  // 0 active, 1 catch, 2 finally
    Value pending_return = make_nova();
    ErrorObject* pending_error = nullptr;
};

struct Frame {
    const CodeObject* code = nullptr;
    std::vector<Value> locals;
    std::vector<Value> stack;
    std::uint32_t ip = 0;
    std::size_t span_index = 0;
    FunctionObject* function = nullptr;
    ModuleRuntime* module = nullptr;
    std::vector<Value> captures;
    std::unordered_map<std::string, std::size_t> local_slots;
    std::vector<bool> declared;
    Value receiver = make_nova();
    bool has_receiver = false;
    bool is_module = false;
    bool is_function = false;

    std::vector<HandlerEntry> handlers;
    Transfer transfer;
    Value pending_return = make_nova();
    bool has_pending_return = false;
    ErrorObject* pending_error = nullptr;
    std::shared_ptr<FrameLifetime> lifetime;

    bool is_alive() const {
        return lifetime != nullptr && lifetime->alive;
    }
};

struct Machine {
    Host& host;
    Arena arena;
    Bundle* bundle = nullptr;
    ModuleTable modules;
    std::vector<ModuleRuntime*> module_stack;
    std::vector<Frame*> module_frames;
    std::vector<FrameRecord> call_frames;
    Frame* current_frame = nullptr;
    std::string entry_path;
    ProjectObject project;
    bool has_project = false;
    std::uint64_t next_task_id = 0;
    std::size_t lazy_pending = 0;
    TaskObject* current_task = nullptr;
    std::unordered_map<std::string, FileStream> files;
    std::size_t frame_depth = 0;
    // Python reports a 900 frame language limit, but its own recursion limit
    // trips first in practice. The native guard is lower so the C++ stack
    // cannot overflow before the language error is raised.
    std::size_t max_frames = 500;
};

Value execute(Frame& frame, Machine& machine);

Frame make_frame(
    const CodeObject& code,
    ModuleRuntime& module,
    FunctionObject* function,
    bool is_module,
    bool is_function) {
    Frame frame;
    frame.code = &code;
    frame.locals.assign(code.local_count, make_undef());
    frame.declared.assign(code.local_count, false);
    frame.stack.reserve(code.max_stack);
    frame.module = &module;
    frame.function = function;
    frame.is_module = is_module;
    frame.is_function = is_function;
    static std::uint64_t generation = 0;
    frame.lifetime = std::make_shared<FrameLifetime>();
    frame.lifetime->generation = ++generation;
    for (std::size_t slot = 0; slot < code.local_names.size(); ++slot) {
        const std::string& name = code.local_names[slot];
        if (!name.empty()) {
            frame.local_slots.emplace(name, slot);
        }
    }
    return frame;
}

Value module_member_value(
    Machine& machine,
    ModuleRuntime& module,
    const std::string& name,
    const std::string& where);
Value error_property_value(
    Machine& machine, ErrorObject* error, const std::string& name);
Value project_member_value(
    Machine& machine, ProjectObject* project, const std::string& name);
Value call_extern_function(
    Machine& machine,
    Frame& frame,
    const std::string& name,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named);
Value call_extern_descriptor(
    Machine& machine,
    const MetaDescriptor& descriptor,
    const std::string& name,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named);
Value cast_value(
    Machine& machine,
    Frame& frame,
    const Value& value,
    const std::string& target);
bool match_pattern(
    Machine& machine,
    Frame& frame,
    const PatternDescriptor& pattern,
    const Value& subject);
Value destructure_value(
    Machine& machine,
    Frame& frame,
    const std::string& descriptor,
    const Value& source);
Value property_default_value(
    Machine& machine, const TypeRuntime& type, const TypeProperty& property);
void initialize_object_fields(
    Machine& machine, ObjectObject* object, const TypeRuntime& type);
Value coerce_declared_value(
    Machine& machine,
    Frame& frame,
    const std::string& type_name,
    const Value& value);
bool function_is_async(const FunctionObject* function);
void run_task(Machine& machine, TaskObject* task);
TaskObject* create_task(
    Machine& machine,
    FunctionObject* function,
    std::vector<Value> positional,
    std::vector<std::pair<std::string, Value>> named,
    const Value* receiver,
    const std::string& where,
    const std::string& frame_name,
    TaskObject::Kind kind);
Value await_task(
    Machine& machine, TaskObject* task, const std::string& where);
void cancel_task(Machine& machine, TaskObject* task);
Value invoke_function(
    Machine& machine,
    FunctionObject* function,
    std::vector<Value> positional,
    std::vector<std::pair<std::string, Value>> named,
    const std::string& where,
    const Value* receiver = nullptr,
    const std::string& frame_name = "");
bool resolve_pending_call(
    Machine& machine,
    Frame& frame,
    const CallSite& site,
    const std::vector<Value>& positional,
    const Value* target,
    FunctionObject*& function,
    Value& receiver,
    bool& has_receiver,
    std::string& where,
    std::string& frame_name);
TypeRuntime* resolve_qualified_type(
    Machine& machine,
    Frame& frame,
    const std::string& qualified,
    const std::string& where);
void initialize_module(ModuleRuntime& module, Machine& machine);
bool try_resolve_name(
    Machine& machine, Frame& frame, const std::string& name, Value& out);
Value call_module_member(
    Machine& machine,
    const CallSite& site,
    ModuleRuntime& module,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named,
    const std::string& where);
void import_wildcard(
    ModuleRuntime& target, Frame& frame, Machine& machine);

void sync_module_global(
    Machine& machine,
    ModuleRuntime& module,
    const std::string& name,
    const Value& value) {
    for (Frame* frame : machine.module_frames) {
        if (frame == nullptr || !frame->is_module
            || frame->module != &module) {
            continue;
        }
        const auto slot = frame->local_slots.find(name);
        if (slot != frame->local_slots.end()) {
            frame->locals[slot->second] = value;
        }
    }
}

void publish_module_local(
    Frame& frame, std::uint32_t slot, const Value& value) {
    if (!frame.is_module || frame.module == nullptr || frame.code == nullptr) {
        return;
    }
    if (slot >= frame.code->local_names.size()) {
        return;
    }
    const std::string& name = frame.code->local_names[slot];
    if (name.empty() || name.front() == '#') {
        return;
    }
    frame.module->globals[name] = value;
}

[[noreturn]] void runtime_fail(const std::string& message) {
    throw RuntimeError(message);
}

std::int64_t value_as_int(const Value& value, const char* what);
std::string runtime_type_name(const Value& value);

std::string frame_label(const Frame& frame) {
    if (frame.code == nullptr) {
        return "frame";
    }
    return frame.code->qualname.empty() ? frame.code->name : frame.code->qualname;
}

void push_value(Frame& frame, const Value& value) {
    if (frame.stack.size() >= frame.code->max_stack) {
        runtime_fail(
            "stack overflow in " + frame_label(frame) + " at offset "
            + std::to_string(frame.ip));
    }
    frame.stack.push_back(value);
}

Value pop_value(Frame& frame) {
    if (frame.stack.empty()) {
        runtime_fail(
            "stack underflow in " + frame_label(frame) + " at offset "
            + std::to_string(frame.ip));
    }
    const Value value = frame.stack.back();
    frame.stack.pop_back();
    return value;
}

const Value& peek_value(const Frame& frame, std::size_t depth) {
    if (depth >= frame.stack.size()) {
        runtime_fail(
            "stack underflow in " + frame_label(frame) + " at offset "
            + std::to_string(frame.ip));
    }
    return frame.stack[frame.stack.size() - 1 - depth];
}

std::int64_t operand_integer(
    const DecodedInstruction& instruction, const char* name) {
    const DecodedOperand* operand = instruction.find(name);
    if (operand == nullptr) {
        runtime_fail(
            std::string("missing operand ") + name + " on "
            + instruction.spec->name);
    }
    return operand->integer;
}

std::uint32_t operand_slot(
    const DecodedInstruction& instruction, const CodeObject& code,
    const char* name) {
    const std::int64_t value = operand_integer(instruction, name);
    if (value < 0 || static_cast<std::uint64_t>(value) >= code.local_count) {
        runtime_fail(
            "slot " + std::to_string(value) + " is outside local_count "
            + std::to_string(code.local_count) + " on "
            + instruction.spec->name);
    }
    return static_cast<std::uint32_t>(value);
}

std::uint32_t operand_target(
    const DecodedInstruction& instruction, const CodeObject& code) {
    const std::int64_t value = operand_integer(instruction, "target");
    if (value < 0 || static_cast<std::uint64_t>(value) > code.bytecode.size()) {
        runtime_fail(
            "jump target out of range: " + std::to_string(value) + " on "
            + instruction.spec->name);
    }
    return static_cast<std::uint32_t>(value);
}

const std::string& global_name_at(
    const Image& image,
    const DecodedInstruction& instruction,
    const char* operand = "name") {
    const std::int64_t index = operand_integer(instruction, operand);
    if (index < 0
        || static_cast<std::uint64_t>(index) >= image.global_names.size()) {
        runtime_fail(
            "global name index out of range: " + std::to_string(index));
    }
    return image.global_names[static_cast<std::size_t>(index)];
}

bool is_numeric_operand(const Value& value) {
    return value.tag == Tag::Int || value.tag == Tag::BigInt
        || value.tag == Tag::Num || value.tag == Tag::Bool;
}

void require_numeric_pair(
    Machine& machine,
    const Value& left,
    const Value& right,
    const char* symbol) {
    if (!is_numeric_operand(left) || !is_numeric_operand(right)) {
        throw_error(error_unsupported_operation(
            machine.arena, "implicit operation",
            runtime_type_name(left), symbol, runtime_type_name(right)));
    }
}

double as_double(const Value& value) {
    if (value.tag == Tag::Int) {
        return static_cast<double>(value.i);
    }
    if (value.tag == Tag::BigInt) {
        return as_bigint_const(value)->value.to_double();
    }
    return value.d;
}

// Numeric coercion used by num left comparisons and by int like comparison
// operands. Bool is 0 or 1 and every other numeric tag has a direct value.
double numeric_as_double(const Value& value) {
    switch (value.tag) {
        case Tag::Bool:
            return value.b ? 1.0 : 0.0;
        case Tag::Int:
            return static_cast<double>(value.i);
        case Tag::BigInt:
            return as_bigint_const(value)->value.to_double();
        case Tag::Num:
            return value.d;
        default:
            return 0.0;
    }
}

// Python casts a num to int with int(). Truncation toward zero is the C++
// static cast. NaN, infinities and values outside int64 have no int64 result,
// so they fail with a runtime error instead of undefined behavior.
std::int64_t num_to_int(double value, const char* opcode) {
    if (std::isnan(value)) {
        runtime_fail(std::string("cannot convert NaN to int in ") + opcode);
    }
    if (std::isinf(value)) {
        runtime_fail(
            std::string("cannot convert infinity to int in ") + opcode);
    }
    if (value < -9223372036854775808.0
        || value >= 9223372036854775808.0) {
        runtime_fail(
            std::string("num is outside the int64 range in ") + opcode);
    }
    return static_cast<std::int64_t>(value);
}

bool is_integer_value(const Value& value) {
    return value.tag == Tag::Int || value.tag == Tag::BigInt
        || value.tag == Tag::Bool;
}

BigInt as_bigint_value(const Value& value) {
    switch (value.tag) {
        case Tag::BigInt:
            return as_bigint_const(value)->value;
        case Tag::Int:
            return BigInt(value.i);
        case Tag::Bool:
            return BigInt(value.b ? 1 : 0);
        default:
            runtime_fail(
                std::string("expected an integer, got ") + tag_name(value.tag));
    }
}

bool bigint_fits_int64(const BigInt& value) {
    return value.compare(BigInt(std::numeric_limits<std::int64_t>::min())) >= 0
        && value.compare(BigInt(std::numeric_limits<std::int64_t>::max())) <= 0;
}

std::int64_t bigint_to_int64(const BigInt& value) {
    return std::stoll(value.format_decimal());
}

Value make_integer_result(Machine& machine, const BigInt& value) {
    if (bigint_fits_int64(value)) {
        return make_int(bigint_to_int64(value));
    }
    return make_bigint(machine.arena.allocate_bigint(value));
}

Value arithmetic_add(Machine& machine, const Value& left, const Value& right) {
    if (left.tag == Tag::Bool) {
        return make_bool(left.b || truthy(right));
    }
    if (right.tag == Tag::Bool) {
        return make_bool(truthy(left) || right.b);
    }
    if (left.tag == Tag::Char && right.tag == Tag::Str) {
        std::u32string text(1, left.c);
        text += as_string_const(right)->code_points;
        return make_string(
            machine.arena.allocate_string(std::move(text)));
    }
    if (left.tag == Tag::Char && right.tag == Tag::Char) {
        std::u32string text(1, left.c);
        text.push_back(right.c);
        return make_string(
            machine.arena.allocate_string(std::move(text)));
    }
    if (left.tag == Tag::Str) {
        std::u32string text = as_string_const(left)->code_points;
        if (right.tag == Tag::Str) {
            text += as_string_const(right)->code_points;
        } else if (right.tag == Tag::Char) {
            text.push_back(right.c);
        } else {
            runtime_fail("string addition expects a str or a char");
        }
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    if (left.tag == Tag::Arr && right.tag == Tag::Arr) {
        std::vector<Value> items = as_array(left)->items;
        items.insert(
            items.end(),
            as_array(right)->items.begin(),
            as_array(right)->items.end());
        return make_array(machine.arena.allocate_array(std::move(items)));
    }
    if (left.tag == Tag::Map && right.tag == Tag::Map) {
        MapObject* result = machine.arena.allocate_map();
        for (const auto& entry : as_map(left)->entries) {
            map_set(
                *result,
                copy_value(machine.arena, entry.first),
                copy_value(machine.arena, entry.second));
        }
        for (const auto& entry : as_map(right)->entries) {
            map_set(
                *result,
                copy_value(machine.arena, entry.first),
                copy_value(machine.arena, entry.second));
        }
        return make_map(result);
    }
    require_numeric_pair(machine, left, right, "+");
    if (is_integer_value(left) && is_integer_value(right)) {
        if (left.tag == Tag::BigInt || right.tag == Tag::BigInt
            || left.tag == Tag::Bool || right.tag == Tag::Bool) {
            return make_integer_result(
                machine, as_bigint_value(left).add(as_bigint_value(right)));
        }
        std::int64_t result = 0;
        if (__builtin_add_overflow(left.i, right.i, &result)) {
            return make_integer_result(
                machine, as_bigint_value(left).add(as_bigint_value(right)));
        }
        return make_int(result);
    }
    if (is_integer_value(left) && right.tag == Tag::Num) {
        const std::int64_t converted = num_to_int(right.d, "ADD");
        if (left.tag == Tag::BigInt || left.tag == Tag::Bool) {
            return make_integer_result(
                machine, as_bigint_value(left).add(BigInt(converted)));
        }
        std::int64_t result = 0;
        if (__builtin_add_overflow(left.i, converted, &result)) {
            return make_integer_result(
                machine, BigInt(left.i).add(BigInt(converted)));
        }
        return make_int(result);
    }
    return make_num(as_double(left) + as_double(right));
}

Value arithmetic_sub(Machine& machine, const Value& left, const Value& right) {
    if (left.tag == Tag::Bool) {
        return make_bool(left.b || !truthy(right));
    }
    if (right.tag == Tag::Bool) {
        return make_bool(truthy(left) || !right.b);
    }
    if (left.tag == Tag::Str && right.tag == Tag::Str) {
        std::u32string text = as_string_const(left)->code_points;
        const std::u32string needle =
            as_string_const(right)->code_points;
        const std::size_t found = text.find(needle);
        if (found != std::u32string::npos) {
            text.erase(found, needle.size());
        }
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    if (left.tag == Tag::Arr && is_integer_value(right)) {
        const std::int64_t count = value_as_int(right, "array subtraction");
        if (count < 0) {
            runtime_fail("cannot remove a negative amount of elements");
        }
        const std::size_t remove =
            std::min(static_cast<std::size_t>(count),
                     as_array(left)->items.size());
        const std::size_t keep = as_array(left)->items.size() - remove;
        std::vector<Value> items(
            as_array(left)->items.begin(),
            as_array(left)->items.begin()
                + static_cast<std::ptrdiff_t>(keep));
        return make_array(machine.arena.allocate_array(std::move(items)));
    }
    if (left.tag == Tag::Arr && right.tag == Tag::Arr) {
        std::vector<Value> items = as_array(left)->items;
        for (const Value& needle : as_array(right)->items) {
            for (std::size_t index = 0; index < items.size(); ++index) {
                if (value_equal(items[index], needle)) {
                    items.erase(
                        items.begin() + static_cast<std::ptrdiff_t>(index));
                    break;
                }
            }
        }
        return make_array(machine.arena.allocate_array(std::move(items)));
    }
    require_numeric_pair(machine, left, right, "-");
    if (is_integer_value(left) && is_integer_value(right)) {
        if (left.tag == Tag::BigInt || right.tag == Tag::BigInt
            || left.tag == Tag::Bool || right.tag == Tag::Bool) {
            return make_integer_result(
                machine, as_bigint_value(left).subtract(as_bigint_value(right)));
        }
        std::int64_t result = 0;
        if (__builtin_sub_overflow(left.i, right.i, &result)) {
            return make_integer_result(
                machine, as_bigint_value(left).subtract(as_bigint_value(right)));
        }
        return make_int(result);
    }
    if (is_integer_value(left) && right.tag == Tag::Num) {
        const std::int64_t converted = num_to_int(right.d, "SUB");
        if (left.tag == Tag::BigInt || left.tag == Tag::Bool) {
            return make_integer_result(
                machine, as_bigint_value(left).subtract(BigInt(converted)));
        }
        std::int64_t result = 0;
        if (__builtin_sub_overflow(left.i, converted, &result)) {
            return make_integer_result(
                machine, BigInt(left.i).subtract(BigInt(converted)));
        }
        return make_int(result);
    }
    return make_num(as_double(left) - as_double(right));
}

Value arithmetic_mul(Machine& machine, const Value& left, const Value& right) {
    if (left.tag == Tag::Bool) {
        return make_bool(left.b && truthy(right));
    }
    if (right.tag == Tag::Bool) {
        return make_bool(truthy(left) && right.b);
    }
    if (left.tag == Tag::Str && right.tag == Tag::Str) {
        const std::u32string& text = as_string_const(left)->code_points;
        const std::u32string& needle =
            as_string_const(right)->code_points;
        if (needle.empty()) {
            return make_int(static_cast<std::int64_t>(text.size() + 1));
        }
        std::int64_t count = 0;
        std::size_t start = 0;
        while (true) {
            const std::size_t found = text.find(needle, start);
            if (found == std::u32string::npos) {
                break;
            }
            ++count;
            start = found + needle.size();
        }
        return make_int(count);
    }
    if (left.tag == Tag::Str && is_integer_value(right)) {
        const std::int64_t count =
            value_as_int(right, "string multiplication");
        std::u32string text;
        for (std::int64_t index = 0; index < count; ++index) {
            text += as_string_const(left)->code_points;
        }
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    if (is_integer_value(left) && right.tag == Tag::Str) {
        const std::int64_t count =
            value_as_int(left, "string multiplication");
        std::u32string text;
        for (std::int64_t index = 0; index < count; ++index) {
            text += as_string_const(right)->code_points;
        }
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    require_numeric_pair(machine, left, right, "*");
    if (is_integer_value(left) && is_integer_value(right)) {
        if (left.tag == Tag::BigInt || right.tag == Tag::BigInt
            || left.tag == Tag::Bool || right.tag == Tag::Bool) {
            return make_integer_result(
                machine, as_bigint_value(left).multiply(as_bigint_value(right)));
        }
        std::int64_t result = 0;
        if (__builtin_mul_overflow(left.i, right.i, &result)) {
            return make_integer_result(
                machine, as_bigint_value(left).multiply(as_bigint_value(right)));
        }
        return make_int(result);
    }
    if (is_integer_value(left) && right.tag == Tag::Num) {
        const std::int64_t converted = num_to_int(right.d, "MUL");
        if (left.tag == Tag::BigInt || left.tag == Tag::Bool) {
            return make_integer_result(
                machine, as_bigint_value(left).multiply(BigInt(converted)));
        }
        std::int64_t result = 0;
        if (__builtin_mul_overflow(left.i, converted, &result)) {
            return make_integer_result(
                machine, BigInt(left.i).multiply(BigInt(converted)));
        }
        return make_int(result);
    }
    return make_num(as_double(left) * as_double(right));
}

Value integer_divmod(
    Machine& machine,
    const Value& left,
    const Value& right,
    bool want_remainder,
    const char* opcode) {
    BigInt dividend = as_bigint_value(left);
    BigInt divisor = as_bigint_value(right);
    if (divisor.is_zero()) {
        return make_nova();
    }
    const std::pair<BigInt, BigInt> result = dividend.divmod(divisor);
    BigInt quotient = result.first;
    BigInt remainder = result.second;
    if (!remainder.is_zero()
        && (remainder.is_negative() != divisor.is_negative())) {
        quotient = quotient.subtract(BigInt(1));
        remainder = remainder.add(divisor);
    }
    (void)opcode;
    return make_integer_result(
        machine, want_remainder ? remainder : quotient);
}

Value chunk_size_error(
    Machine& machine, const char* type_name, std::int64_t size) {
    throw_error(make_error(
        machine.arena, "VALUE", std::string(type_name) + " chunking",
        "Chunk size must be positive",
        {std::string(type_name)
             + " cannot be divided into chunks of non-positive size "
             + std::to_string(size)}));
}

Value arithmetic_div(Machine& machine, const Value& left, const Value& right) {
    if (left.tag == Tag::Bool) {
        return make_bool(left.b && !truthy(right));
    }
    if (right.tag == Tag::Bool) {
        return make_bool(truthy(left) && !right.b);
    }
    if (left.tag == Tag::Str && is_integer_value(right)) {
        const std::int64_t size = value_as_int(right, "string chunking");
        if (size <= 0) {
            return chunk_size_error(machine, "str", size);
        }
        const std::u32string& text = as_string_const(left)->code_points;
        std::vector<Value> chunks;
        std::size_t end = text.size();
        while (end > 0) {
            const std::size_t start =
                end > static_cast<std::size_t>(size)
                ? end - static_cast<std::size_t>(size) : 0;
            chunks.push_back(make_string(
                machine.arena.allocate_string(
                    text.substr(start, end - start))));
            end = start;
        }
        std::reverse(chunks.begin(), chunks.end());
        return make_array(
            machine.arena.allocate_array(std::move(chunks)));
    }
    if (is_integer_value(left) && right.tag == Tag::Str) {
        const std::int64_t size = value_as_int(left, "str chunking");
        if (size <= 0) {
            return chunk_size_error(machine, "str", size);
        }
        const std::u32string& text = as_string_const(right)->code_points;
        std::vector<Value> chunks;
        for (std::size_t start = 0; start < text.size();
             start += static_cast<std::size_t>(size)) {
            chunks.push_back(make_string(
                machine.arena.allocate_string(text.substr(
                    start, static_cast<std::size_t>(size)))));
        }
        return make_array(
            machine.arena.allocate_array(std::move(chunks)));
    }
    if (is_integer_value(left) && right.tag == Tag::Arr) {
        const std::int64_t size = value_as_int(left, "arr chunking");
        if (size <= 0) {
            return chunk_size_error(machine, "arr", size);
        }
        const std::vector<Value>& items = as_array(right)->items;
        std::vector<Value> chunks;
        for (std::size_t start = 0; start < items.size();
             start += static_cast<std::size_t>(size)) {
            const std::size_t end = std::min(
                items.size(), start + static_cast<std::size_t>(size));
            chunks.push_back(make_array(machine.arena.allocate_array(
                std::vector<Value>(
                    items.begin() + static_cast<std::ptrdiff_t>(start),
                    items.begin() + static_cast<std::ptrdiff_t>(end)))));
        }
        return make_array(
            machine.arena.allocate_array(std::move(chunks)));
    }
    if (left.tag == Tag::Str && right.tag == Tag::Str) {
        const std::u32string& text = as_string_const(left)->code_points;
        const std::u32string& separator =
            as_string_const(right)->code_points;
        if (separator.empty()) {
            runtime_fail("string division separator must not be empty");
        }
        std::vector<Value> parts;
        std::size_t start = 0;
        while (true) {
            const std::size_t found = text.find(separator, start);
            if (found == std::u32string::npos) {
                parts.push_back(make_string(
                    machine.arena.allocate_string(text.substr(start))));
                break;
            }
            parts.push_back(make_string(machine.arena.allocate_string(
                text.substr(start, found - start))));
            start = found + separator.size();
        }
        return make_array(
            machine.arena.allocate_array(std::move(parts)));
    }
    require_numeric_pair(machine, left, right, "/");
    if (is_integer_value(left) && is_integer_value(right)) {
        if (left.tag == Tag::BigInt || right.tag == Tag::BigInt
            || left.tag == Tag::Bool || right.tag == Tag::Bool
            || (left.tag == Tag::Int && right.tag == Tag::Int
                && left.i == std::numeric_limits<std::int64_t>::min()
                && right.i == -1)) {
            return integer_divmod(machine, left, right, false, "DIV");
        }
        if (right.i == 0) {
            return make_nova();
        }
        std::int64_t quotient = left.i / right.i;
        const std::int64_t remainder = left.i % right.i;
        if (remainder != 0 && ((remainder < 0) != (right.i < 0))) {
            quotient -= 1;
        }
        return make_int(quotient);
    }
    if (is_integer_value(left) && right.tag == Tag::Num) {
        if (right.d == 0.0) {
            return make_nova();
        }
        if (left.tag == Tag::BigInt || left.tag == Tag::Bool) {
            const std::int64_t converted = num_to_int(right.d, "DIV");
            if (converted == 0) {
                return make_nova();
            }
            return integer_divmod(
                machine, left, make_int(converted), false, "DIV");
        }
        const double quotient =
            static_cast<double>(left.i) / right.d;
        return make_int(num_to_int(quotient, "DIV"));
    }
    const double divisor = as_double(right);
    if (divisor == 0.0) {
        return make_nova();
    }
    return make_num(as_double(left) / divisor);
}

Value arithmetic_mod(Machine& machine, const Value& left, const Value& right) {
    require_numeric_pair(machine, left, right, "%");
    if (is_integer_value(left) && is_integer_value(right)) {
        if (left.tag == Tag::BigInt || right.tag == Tag::BigInt
            || left.tag == Tag::Bool || right.tag == Tag::Bool
            || (left.tag == Tag::Int && right.tag == Tag::Int
                && left.i == std::numeric_limits<std::int64_t>::min()
                && right.i == -1)) {
            return integer_divmod(machine, left, right, true, "MOD");
        }
        if (right.i == 0) {
            return make_nova();
        }
        std::int64_t remainder = left.i % right.i;
        if (remainder != 0 && ((remainder < 0) != (right.i < 0))) {
            remainder += right.i;
        }
        return make_int(remainder);
    }
    if (is_integer_value(left) && right.tag == Tag::Num) {
        const std::int64_t divisor = num_to_int(right.d, "MOD");
        if (divisor == 0) {
            return make_nova();
        }
        if (left.tag == Tag::BigInt || left.tag == Tag::Bool) {
            return integer_divmod(
                machine, left, make_int(divisor), true, "MOD");
        }
        std::int64_t remainder = left.i % divisor;
        if (remainder != 0 && ((remainder < 0) != (divisor < 0))) {
            remainder += divisor;
        }
        return make_int(remainder);
    }
    const double divisor = as_double(right);
    if (divisor == 0.0) {
        return make_nova();
    }
    double remainder = std::fmod(as_double(left), divisor);
    if (remainder == 0.0) {
        return make_num(std::copysign(0.0, divisor));
    }
    if ((remainder < 0.0) != (divisor < 0.0)) {
        remainder += divisor;
    }
    return make_num(remainder);
}

Value arithmetic_negate(Machine& machine, const Value& value) {
    if (value.tag == Tag::Int) {
        if (value.i == std::numeric_limits<std::int64_t>::min()) {
            return make_integer_result(machine, BigInt(value.i).negate());
        }
        return make_int(-value.i);
    }
    if (value.tag == Tag::BigInt) {
        return make_integer_result(
            machine, as_bigint_const(value)->value.negate());
    }
    if (value.tag == Tag::Num) {
        return make_num(-value.d);
    }
    runtime_fail(
        std::string("native N1 NEG requires an int or num operand, got ")
        + tag_name(value.tag));
}

struct Comparison {
    bool unordered = false;
    int order = 0;
};

bool is_numeric_value(const Value& value) {
    return value.tag == Tag::Bool || value.tag == Tag::Int
        || value.tag == Tag::BigInt || value.tag == Tag::Num;
}

// One comparison helper for EQ, NEQ, LT, LE, GT and GE. The Python VM casts
// the right operand to the left operand type, so int left comparisons convert
// a num right operand to int and num left comparisons convert an int or bool
// right operand to double. Bool left comparisons cast the right operand to
// bool. A NaN operand returns unordered, which makes EQ, LT, LE, GT and GE
// false and NEQ true. Bool left comparisons keep Python truthiness, where NaN
// is true.
Comparison compare_values(
    Machine& machine,
    const Value& left,
    const Value& right,
    const char* opcode) {
    const std::string equality(opcode);
    const std::string symbol =
        equality == "EQ" || equality == "EQ_TYPED" ? "=="
        : equality == "NEQ" || equality == "NEQ_TYPED" ? "!="
        : equality == "LT" || equality == "LT_TYPED" ? "<"
        : equality == "LE" || equality == "LE_TYPED" ? "<="
        : equality == "GT" || equality == "GT_TYPED" ? ">"
        : equality == "GE" || equality == "GE_TYPED" ? ">="
        : equality;
    if (equality == "EQ" || equality == "NEQ"
        || equality == "EQ_TYPED" || equality == "NEQ_TYPED") {
        const bool both_numeric =
            is_numeric_value(left) && is_numeric_value(right);
        if (!both_numeric) {
            const bool comparable =
                left.tag == right.tag
                || left.tag == Tag::Nova || right.tag == Tag::Nova
                || (left.tag == Tag::Str && right.tag == Tag::Char)
                || (left.tag == Tag::Char && right.tag == Tag::Str);
            if (!comparable) {
                throw_error(error_unsupported_operation(
                    machine.arena, "comparisson",
                    runtime_type_name(left), symbol,
                    runtime_type_name(right)));
            }
            return {false, value_equal(left, right) ? 0 : 1};
        }
    }
    if (is_numeric_value(left) && is_numeric_value(right)) {
        if (left.tag == Tag::Bool) {
            bool other = false;
            if (is_integer_value(right)) {
                other = !as_bigint_value(right).is_zero();
            } else {
                other = right.d != 0.0;
            }
            if (left.b == other) {
                return {false, 0};
            }
            return {false, left.b ? 1 : -1};
        }
        if (is_integer_value(left)) {
            if (right.tag == Tag::Num) {
                if (std::isnan(right.d)) {
                    return {true, 0};
                }
                const std::int64_t other = num_to_int(right.d, opcode);
                if (left.tag == Tag::BigInt || left.tag == Tag::Bool) {
                    const int order =
                        as_bigint_value(left).compare(BigInt(other));
                    return {
                        false, order < 0 ? -1 : (order > 0 ? 1 : 0)};
                }
                return {
                    false,
                    left.i < other ? -1 : (left.i > other ? 1 : 0)};
            }
            const int order =
                as_bigint_value(left).compare(as_bigint_value(right));
            return {false, order < 0 ? -1 : (order > 0 ? 1 : 0)};
        }
        if (left.tag == Tag::Num) {
            if (std::isnan(left.d)) {
                return {true, 0};
            }
            const double other = numeric_as_double(right);
            if (std::isnan(other)) {
                return {true, 0};
            }
            return {
                false,
                left.d < other ? -1 : (left.d > other ? 1 : 0)};
        }
    }
    if (left.tag == Tag::Str && right.tag == Tag::Str) {
        const std::u32string& a = as_string_const(left)->code_points;
        const std::u32string& b = as_string_const(right)->code_points;
        const int order = a.compare(b);
        return {false, order < 0 ? -1 : (order > 0 ? 1 : 0)};
    }
    if ((left.tag == Tag::Str && right.tag == Tag::Char)
        || (left.tag == Tag::Char && right.tag == Tag::Str)) {
        const std::string operation(opcode);
        if (operation == "EQ" || operation == "NEQ") {
            return {false, value_equal(left, right) ? 0 : 1};
        }
        runtime_fail("ordering is not supported between str and char");
    }
    if ((left.tag == Tag::Arr || left.tag == Tag::Tup
         || left.tag == Tag::Map || left.tag == Tag::Set
         || left.tag == Tag::Obj || left.tag == Tag::Type)
        && left.tag == right.tag) {
        const std::string operation(opcode);
        if (operation == "EQ" || operation == "NEQ") {
            return {false, value_equal(left, right) ? 0 : 1};
        }
        runtime_fail("ordering is not supported for containers");
    }
    if (left.tag == right.tag) {
        switch (left.tag) {
            case Tag::Nova:
            case Tag::Undef:
                return {false, 0};
            case Tag::Char:
                return {
                    false,
                    left.c == right.c ? 0 : (left.c < right.c ? -1 : 1)};
            case Tag::Str:
            case Tag::BigInt:
            case Tag::Fun:
            case Tag::Arr:
            case Tag::Spread:
            case Tag::Iter:
            case Tag::Tup:
            case Tag::Map:
            case Tag::Set:
            case Tag::Obj:
            case Tag::Type:
                break;
            case Tag::Bool:
            case Tag::Int:
            case Tag::Num:
                break;
        }
    }
    throw_error(error_unsupported_operation(
        machine.arena, "comparisson",
        runtime_type_name(left), symbol.c_str(),
        runtime_type_name(right)));
}

Value load_constant(
    Machine& machine, const CodeObject& code, std::int64_t index) {
    if (index < 0
        || static_cast<std::uint64_t>(index) >= code.constants.size()) {
        runtime_fail("constant index out of range: " + std::to_string(index));
    }
    const Constant& constant = code.constants[static_cast<std::size_t>(index)];
    switch (constant.kind) {
        case ConstantKind::Nova:
            return make_nova();
        case ConstantKind::Bool:
            return make_bool(constant.bool_value);
        case ConstantKind::Int:
            return make_int(constant.int_value);
        case ConstantKind::BigInt: {
            BigInt value = BigInt::parse_decimal(constant.text);
            return make_bigint(machine.arena.allocate_bigint(std::move(value)));
        }
        case ConstantKind::Str:
            return make_string(
                machine.arena.allocate_string_utf8(constant.text));
        case ConstantKind::Num:
            return make_num(constant.num_value);
        case ConstantKind::Char: {
            const char32_t code_point =
                static_cast<char32_t>(constant.uint_value);
            if (!is_scalar_value(code_point)) {
                runtime_fail(
                    "char constant is not a Unicode scalar value: "
                    + std::to_string(constant.uint_value));
            }
            return make_char(code_point);
        }
        default:
            runtime_fail(
                std::string("native N1 does not implement constant kind ")
                + constant_kind_name(constant.kind));
    }
}

std::string constant_type_name(const Constant& constant) {
    const std::size_t name_at =
        constant.text.find("\"value\":\"");
    if (name_at == std::string::npos) {
        return "";
    }
    const std::size_t start = name_at + 9;
    const std::size_t end = constant.text.find('"', start);
    if (end == std::string::npos) {
        return "";
    }
    return constant.text.substr(start, end - start);
}

Value make_typed_undef(
    Machine& machine, const std::string& type_name) {
    Value value = make_undef();
    if (!type_name.empty()) {
        value.ref = machine.arena.allocate_string_utf8(type_name);
    }
    return value;
}

void apply_declared_spec_flags(
    const CodeObject& code, std::int64_t spec_index, Value& value) {
    if (spec_index < 0
        || static_cast<std::uint64_t>(spec_index)
            >= code.constants.size()) {
        return;
    }
    const Constant& spec = code.constants[
        static_cast<std::size_t>(spec_index)];
    if (spec.kind != ConstantKind::Spec) {
        return;
    }
    if (spec.text.find("\"const\":true") != std::string::npos) {
        value.flags |= ValueConst;
        if (value.tag == Tag::Obj) {
            as_object(value)->structure_locked = true;
        }
    }
    const std::size_t element_at =
        spec.text.find("\"element_type\":");
    if (value.tag == Tag::Arr && element_at != std::string::npos
        && spec.text.find("\"const\":true", element_at)
            != std::string::npos) {
        as_array(value)->elements_locked = true;
    }
    if (spec.text.find("\"weak\":true") != std::string::npos) {
        value.flags |= ValueWeak;
    }
}

std::uint32_t code_index_of(
    const Image& image, const CodeObject& code) {
    const CodeObject* base = image.codes.data();
    const CodeObject* pointer = &code;
    if (pointer >= base && pointer < base + image.codes.size()) {
        return static_cast<std::uint32_t>(pointer - base);
    }
    throw RuntimeError("code object does not belong to its image");
}

std::vector<Value> collect_arguments(Frame& frame, std::size_t count);
std::vector<Value> flatten_arguments(
    const CallSite& site,
    std::vector<Value> raw,
    std::vector<std::pair<std::string, Value>>& named);
Value call_function(
    Machine& machine,
    FunctionObject* function,
    std::vector<Value> positional,
    std::vector<std::pair<std::string, Value>> named,
    const std::string& where,
    const Value* receiver = nullptr,
    const std::string& frame_name = "");
Value call_builtin(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named);
bool try_resolve_name(
    Machine& machine, Frame& frame, const std::string& name, Value& out);
bool try_resolve_free(
    Machine& machine, Frame& frame, const std::string& name, Value& out);
Value resolve_name(
    Machine& machine, Frame& frame, const std::string& name);
void assign_name(
    Machine& machine,
    Frame& frame,
    const std::string& name,
    const Value& value);
void capture_scope(
    Machine& machine,
    FunctionObject& function,
    Frame& caller,
    bool by_reference);
std::string runtime_type_name(const Value& value);
int score_type(const MetaTypeSpec& spec, const Value& value, const Meta& meta);
bool assignable_type(
    const MetaTypeSpec& spec, const Value& value, const Meta& meta);
FunctionObject* select_overload(
    const std::vector<FunctionObject*>& functions,
    const std::vector<Value>& arguments,
    const Meta& meta);
Value string_from_utf8(Machine& machine, const std::string& text);
std::string string_to_utf8(const Value& value);
std::int64_t value_as_int(const Value& value, const char* what);
std::int64_t resolved_index(
    Machine& machine,
    const Value& index,
    std::size_t size,
    const char* what);
std::size_t slice_start(const Value& value, std::size_t size);
std::size_t slice_end(const Value& value, std::size_t size);
Value index_get(
    Machine& machine, const Value& container, const Value& index);
Value index_set(
    Machine& machine,
    const Value& container,
    const Value& index,
    const Value& value);
Value slice_value(
    Machine& machine,
    const Value& target,
    const Value& start,
    const Value& end);
Value reverse_value(Machine& machine, const Value& value);
Value builtin_size(Machine& machine, const Value& value);
Value call_native_method(
    Machine& machine,
    const CallSite& site,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named);
Value call_type_method(
    Machine& machine,
    const Value& receiver,
    const std::string& name,
    const std::vector<Value>& arguments,
    const std::string& where);
Comparison compare_object_values(
    Machine& machine,
    const Value& left,
    const Value& right,
    const char* opcode);

bool is_builtin_name(const std::string& name) {
    static const std::unordered_set<std::string> names = {
        "print", "println", "format", "printf", "error", "fail",
        "system", "input", "inputf", "typeof", "typedeep",
        "is_digit", "is_alpha", "is_alnum", "is_space", "is_upper",
        "is_lower", "is_ascii", "ord", "chr", "digit_value", "size",
        "open", "close", "write", "read", "wait", "cancel",
        "task_status",
    };
    return names.count(name) != 0;
}

bool private_access_allowed(
    Machine& machine, Frame& frame, const ObjectObject& object) {
    (void)machine;
    if (frame.function == nullptr || frame.function->owner == nullptr) {
        return false;
    }
    if (frame.function->owner->info == nullptr) {
        return false;
    }
    return frame.function->owner->info->name == object.type_name
        && !frame.function->is_static;
}

Value load_object_member(
    Machine& machine,
    Frame& frame,
    const Value& owner,
    const std::string& name,
    bool safe,
    bool allow_methods);
Value store_object_member(
    Machine& machine,
    Frame& frame,
    const Value& owner,
    const std::string& name,
    const Value& value);
bool object_satisfies_trait(
    Machine& machine,
    const ObjectObject& object,
    const TraitRuntime& trait);

[[noreturn]] void stale_reference(Machine& machine) {
    throw_error(error_reference(
        machine.arena, "reference expression", "Stale reference",
        {"the target frame is no longer active"}));
}

Value reference_get(Machine& machine, RefObject* reference) {
    if (reference == nullptr) {
        throw RuntimeError("null reference value");
    }
    switch (reference->kind) {
        case RefObject::Kind::Local: {
            Frame* local_frame =
                static_cast<Frame*>(reference->frame);
            if (local_frame == nullptr
                || reference->lifetime == nullptr
                || !reference->lifetime->alive
                || reference->lifetime->generation
                    != reference->generation
                || reference->slot >= local_frame->locals.size()) {
                stale_reference(machine);
            }
            return local_frame->locals[reference->slot];
        }
        case RefObject::Kind::Global: {
            if (reference->module == nullptr) {
                throw RuntimeError("null module in reference");
            }
            const auto found =
                reference->module->globals.find(reference->name);
            if (found == reference->module->globals.end()) {
                throw_error(error_identifier_not_found(
                    machine.arena, "reference expression",
                    reference->name));
            }
            return found->second;
        }
        case RefObject::Kind::Field: {
            if (reference->object == nullptr) {
                throw RuntimeError("null object in reference");
            }
            const auto found =
                reference->object->fields.find(reference->name);
            if (found == reference->object->fields.end()) {
                throw_error(error_identifier_not_found(
                    machine.arena, "reference expression",
                    reference->name));
            }
            return found->second;
        }
        case RefObject::Kind::Index:
            if (reference->array == nullptr) {
                throw RuntimeError("null array in reference");
            }
            if (reference->index >= reference->array->items.size()) {
                throw_error(error_index_out_of_range(
                    machine.arena,
                    static_cast<std::int64_t>(reference->index),
                    static_cast<std::int64_t>(
                        reference->array->items.size())));
            }
            return reference->array->items[reference->index];
    }
    throw RuntimeError("unknown reference kind");
}

void reference_set(
    Machine& machine, RefObject* reference, const Value& value) {
    if (reference == nullptr) {
        throw RuntimeError("null reference value");
    }
    const Value stored = copy_value(machine.arena, value);
    switch (reference->kind) {
        case RefObject::Kind::Local: {
            Frame* local_frame =
                static_cast<Frame*>(reference->frame);
            if (local_frame == nullptr
                || reference->lifetime == nullptr
                || !reference->lifetime->alive
                || reference->lifetime->generation
                    != reference->generation
                || reference->slot >= local_frame->locals.size()) {
                stale_reference(machine);
            }
            local_frame->locals[reference->slot] = stored;
            return;
        }
        case RefObject::Kind::Global:
            if (reference->module == nullptr) {
                throw RuntimeError("null module in reference");
            }
            if (reference->module->globals.count(reference->name) == 0) {
                throw_error(error_identifier_not_found(
                    machine.arena, "reference expression",
                    reference->name));
            }
            reference->module->globals[reference->name] = stored;
            sync_module_global(
                machine, *reference->module, reference->name, stored);
            return;
        case RefObject::Kind::Field:
            if (reference->object == nullptr) {
                throw RuntimeError("null object in reference");
            }
            if (reference->object->fields.count(reference->name) == 0) {
                throw_error(error_identifier_not_found(
                    machine.arena, "reference expression",
                    reference->name));
            }
            reference->object->fields[reference->name] = stored;
            return;
        case RefObject::Kind::Index:
            if (reference->array == nullptr) {
                throw RuntimeError("null array in reference");
            }
            if (reference->index >= reference->array->items.size()) {
                throw_error(error_index_out_of_range(
                    machine.arena,
                    static_cast<std::int64_t>(reference->index),
                    static_cast<std::int64_t>(
                        reference->array->items.size())));
            }
            reference->array->items[reference->index] = stored;
            return;
    }
    throw RuntimeError("unknown reference kind");
}

Value unwrap_reference(Machine& machine, const Value& value) {
    if (!is_reference(value)) {
        return value;
    }
    return reference_get(machine, as_reference(value));
}

void close_frame(Frame& frame) {
    if (frame.lifetime != nullptr) {
        frame.lifetime->alive = false;
    }
}

bool handle_error(Frame& frame, ErrorObject* error, std::int32_t fault_ip) {
    for (std::int32_t index =
             static_cast<std::int32_t>(frame.handlers.size()) - 1;
         index >= 0; --index) {
        HandlerEntry& handler =
            frame.handlers[static_cast<std::size_t>(index)];
        if (handler.state == 2) {
            continue;
        }
        if (!(handler.start_ip <= fault_ip && fault_ip < handler.end_ip)) {
            continue;
        }
        if (handler.catch_ip >= 0 && handler.state == 0) {
            frame.handlers.resize(static_cast<std::size_t>(index) + 1);
            if (frame.stack.size() > handler.stack_depth) {
                frame.stack.resize(handler.stack_depth);
            }
            handler.state = 1;
            frame.pending_error = nullptr;
            frame.pending_return = make_nova();
            frame.has_pending_return = false;
            frame.transfer = Transfer{};
            frame.ip = static_cast<std::uint32_t>(handler.catch_ip);
            frame.stack.push_back(make_error_value(error));
            return true;
        }
        if (handler.finally_ip >= 0) {
            frame.handlers.resize(static_cast<std::size_t>(index) + 1);
            if (frame.stack.size() > handler.stack_depth) {
                frame.stack.resize(handler.stack_depth);
            }
            handler.state = 2;
            frame.pending_error = error;
            frame.pending_return = make_nova();
            frame.has_pending_return = false;
            frame.transfer = Transfer{};
            frame.ip = static_cast<std::uint32_t>(handler.finally_ip);
            return true;
        }
        frame.handlers.erase(
            frame.handlers.begin() + index);
    }
    return false;
}

void attach_frames(Machine& machine, ErrorObject* error) {
    if (error == nullptr || !error->frames.empty()
        || machine.call_frames.empty()) {
        return;
    }
    for (auto it = machine.call_frames.rbegin();
         it != machine.call_frames.rend(); ++it) {
        FrameRecord record;
        record.name = it->name;
        record.file = it->file;
        record.line = it->line;
        record.column = it->column;
        error->frames.push_back(std::move(record));
    }
}

Value execute(Frame& frame, Machine& machine) {
    const Image& image = *frame.module->image;
    const Meta* meta = frame.module->meta;
    const CodeObject& code = *frame.code;
    while (frame.ip < code.bytecode.size()) {
        const DecodedInstruction instruction =
            decode_instruction(code.bytecode, frame.ip);
        frame.ip = instruction.next_offset;
        if (instruction.offset < code.offset_to_span.size()) {
            frame.span_index =
                code.offset_to_span[instruction.offset];
        }
        machine.current_frame = &frame;
        try {
        switch (static_cast<Opcode>(instruction.opcode)) {
            case Opcode::NOP:
                break;
            case Opcode::POP:
                (void)pop_value(frame);
                break;
            case Opcode::DUP:
                push_value(frame, peek_value(frame, 0));
                break;
            case Opcode::DUP2: {
                const Value first = peek_value(frame, 1);
                const Value second = peek_value(frame, 0);
                push_value(frame, first);
                push_value(frame, second);
                break;
            }
            case Opcode::SWAP: {
                if (frame.stack.size() < 2) {
                    runtime_fail("stack underflow in SWAP");
                }
                std::swap(
                    frame.stack[frame.stack.size() - 1],
                    frame.stack[frame.stack.size() - 2]);
                break;
            }
            case Opcode::ROT3: {
                if (frame.stack.size() < 3) {
                    runtime_fail("stack underflow in ROT3");
                }
                const std::size_t size = frame.stack.size();
                const Value a = frame.stack[size - 3];
                const Value b = frame.stack[size - 2];
                const Value c = frame.stack[size - 1];
                frame.stack[size - 3] = b;
                frame.stack[size - 2] = c;
                frame.stack[size - 1] = a;
                break;
            }
            case Opcode::ROT: {
                const std::int64_t count =
                    operand_integer(instruction, "count");
                if (count <= 0) {
                    break;
                }
                if (static_cast<std::uint64_t>(count) > frame.stack.size()) {
                    runtime_fail("stack underflow in ROT");
                }
                const std::size_t size = frame.stack.size();
                const std::size_t width = static_cast<std::size_t>(count);
                const Value last = frame.stack[size - 1];
                for (std::size_t index = size - 1; index > size - width;
                     --index) {
                    frame.stack[index] = frame.stack[index - 1];
                }
                frame.stack[size - width] = last;
                break;
            }
            case Opcode::LOAD_NOVA:
                push_value(frame, make_nova());
                break;
            case Opcode::LOAD_UNDEF:
                push_value(frame, make_undef());
                break;
            case Opcode::LOAD_TRUE:
                push_value(frame, make_bool(true));
                break;
            case Opcode::LOAD_FALSE:
                push_value(frame, make_bool(false));
                break;
            case Opcode::LOAD_INT:
                push_value(
                    frame,
                    make_int(operand_integer(instruction, "value")));
                break;
            case Opcode::LOAD_NUM: {
                const DecodedOperand* operand = instruction.find("value");
                if (operand == nullptr) {
                    runtime_fail("missing operand value on LOAD_NUM");
                }
                push_value(frame, make_num(operand->number));
                break;
            }
            case Opcode::LOAD_CHAR: {
                const std::int64_t raw = operand_integer(instruction, "value");
                if (raw < 0 || raw > 0x10FFFF) {
                    runtime_fail(
                        "LOAD_CHAR value is not a Unicode scalar value: "
                        + std::to_string(raw));
                }
                const char32_t code_point = static_cast<char32_t>(raw);
                if (!is_scalar_value(code_point)) {
                    runtime_fail(
                        "LOAD_CHAR value is not a Unicode scalar value: "
                        + std::to_string(raw));
                }
                push_value(frame, make_char(code_point));
                break;
            }
            case Opcode::LOAD_STR:
                push_value(
                    frame,
                    load_constant(
                        machine, code,
                        operand_integer(instruction, "const")));
                break;
            case Opcode::LOAD_BIGINT: {
                const std::int64_t index =
                    operand_integer(instruction, "const");
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= code.constants.size()) {
                    runtime_fail(
                        "constant index out of range: "
                        + std::to_string(index));
                }
                const Constant& constant =
                    code.constants[static_cast<std::size_t>(index)];
                if (constant.kind != ConstantKind::BigInt) {
                    runtime_fail("LOAD_BIGINT constant is not a bigint");
                }
                push_value(
                    frame,
                    make_bigint(machine.arena.allocate_bigint(
                        BigInt::parse_decimal(constant.text))));
                break;
            }
            case Opcode::LOAD_CONST:
                push_value(
                    frame,
                    load_constant(
                        machine, code,
                        operand_integer(instruction, "const")));
                break;
            case Opcode::DECLARE_TYPE: {
                const std::int64_t index =
                    operand_integer(instruction, "type");
                if (meta == nullptr) {
                    runtime_fail("type metadata is required");
                }
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= image.types.size()) {
                    runtime_fail(
                        "type index out of range: "
                        + std::to_string(index));
                }
                const TypeInfo& info =
                    image.types[static_cast<std::size_t>(index)];
                TypeRuntime& runtime = frame.module->types[info.name];
                runtime = TypeRuntime{};
                runtime.info = &info;
                runtime.module = frame.module;
                runtime.qualified_name =
                    frame.module->name + "." + info.name;
                for (const TypeMethod& method : info.methods) {
                    if (static_cast<std::uint64_t>(method.index)
                        >= meta->functions.size()) {
                        continue;
                    }
                    FunctionObject* function =
                        machine.arena.allocate_function(
                            &meta->functions[
                                static_cast<std::size_t>(method.index)]);
                    const bool is_instance =
                        method.name == "constructor" || method.is_static;
                    function->module = frame.module;
                    function->owner = &runtime;
                    function->is_static = !is_instance;
                    function->is_private = !method.is_private;
                    if (method.type_name.has_value()) {
                        function->trait_qualifier = *method.type_name;
                    }
                    if (!function->trait_qualifier.empty()) {
                        runtime.trait_methods[
                            function->trait_qualifier][method.name]
                            .push_back(function);
                    } else if (!is_instance) {
                        runtime.statics[method.name].push_back(function);
                    } else if (method.name == "constructor") {
                        runtime.constructors[method.name].push_back(function);
                    } else {
                        runtime.methods[method.name].push_back(function);
                    }
                }
                if (info.kind == "enum") {
                    MapObject* variants = machine.arena.allocate_map();
                    for (const std::string& variant : info.variants) {
                        ObjectObject* object =
                            machine.arena.allocate_object(
                                info.name, true, variant);
                        object->type = &runtime;
                        object->module = frame.module;
                        object->fields["name"] =
                            string_from_utf8(machine, variant);
                        map_set(
                            *variants,
                            string_from_utf8(machine, variant),
                            make_object(object));
                    }
                    const Value enum_value = make_map(variants);
                    frame.module->globals[info.name] = enum_value;
                    push_value(frame, enum_value);
                } else {
                    const Value type_value = make_type(&runtime);
                    frame.module->globals[info.name] = type_value;
                    push_value(frame, type_value);
                }
                break;
            }
            case Opcode::DECLARE_TRAIT: {
                const std::int64_t index =
                    operand_integer(instruction, "trait");
                if (meta == nullptr) {
                    runtime_fail("trait metadata is required");
                }
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= image.traits.size()) {
                    runtime_fail(
                        "trait index out of range: "
                        + std::to_string(index));
                }
                const TraitInfo& info =
                    image.traits[static_cast<std::size_t>(index)];
                TraitRuntime& runtime = frame.module->traits[info.name];
                runtime = TraitRuntime{};
                runtime.info = &info;
                runtime.module = frame.module;
                for (const TraitMethod& method : info.methods) {
                    if (static_cast<std::uint64_t>(method.index)
                        >= meta->functions.size()) {
                        continue;
                    }
                    FunctionObject* function =
                        machine.arena.allocate_function(
                            &meta->functions[
                                static_cast<std::size_t>(method.index)]);
                    function->module = frame.module;
                    function->trait_qualifier = info.name;
                    runtime.defaults[method.name].push_back(function);
                }
                break;
            }
            case Opcode::MAKE_ARRAY:
            case Opcode::MAKE_ARRAY_TYPED: {
                const std::int64_t count =
                    operand_integer(instruction, "count");
                std::vector<Value> values = collect_arguments(
                    frame, static_cast<std::size_t>(count));
                push_value(
                    frame,
                    make_array(machine.arena.allocate_array(
                        std::move(values))));
                break;
            }
            case Opcode::MAKE_TUPLE:
            case Opcode::MAKE_TUPLE_TYPED: {
                const std::int64_t count =
                    operand_integer(instruction, "count");
                std::vector<Value> values = collect_arguments(
                    frame, static_cast<std::size_t>(count));
                push_value(
                    frame,
                    make_tuple(machine.arena.allocate_tuple(
                        std::move(values))));
                break;
            }
            case Opcode::MAKE_MAP:
            case Opcode::MAKE_MAP_TYPED: {
                const std::int64_t count =
                    operand_integer(instruction, "count");
                std::vector<Value> values = collect_arguments(
                    frame, static_cast<std::size_t>(count) * 2);
                MapObject* map = machine.arena.allocate_map();
                for (std::size_t index = 0; index + 1 < values.size();
                     index += 2) {
                    map_set(*map, values[index], values[index + 1]);
                }
                push_value(frame, make_map(map));
                break;
            }
            case Opcode::MAKE_SET:
            case Opcode::MAKE_SET_TYPED: {
                const std::int64_t count =
                    operand_integer(instruction, "count");
                std::vector<Value> values = collect_arguments(
                    frame, static_cast<std::size_t>(count));
                SetObject* set = machine.arena.allocate_set();
                for (const Value& value : values) {
                    set_add(*set, value);
                }
                push_value(frame, make_set(set));
                break;
            }
            case Opcode::MAKE_EMPTY_MAP:
                push_value(frame, make_map(machine.arena.allocate_map()));
                break;
            case Opcode::MAKE_EMPTY_SET:
                push_value(frame, make_set(machine.arena.allocate_set()));
                break;
            case Opcode::INDEX_GET: {
                const Value index = pop_value(frame);
                const Value container = pop_value(frame);
                push_value(frame, index_get(machine, container, index));
                break;
            }
            case Opcode::INDEX_SET: {
                const Value value = pop_value(frame);
                const Value index = pop_value(frame);
                const Value container = pop_value(frame);
                push_value(
                    frame, index_set(machine, container, index, value));
                break;
            }
            case Opcode::SLICE: {
                const Value end = pop_value(frame);
                const Value start = pop_value(frame);
                const Value target = pop_value(frame);
                push_value(
                    frame, slice_value(machine, target, start, end));
                break;
            }
            case Opcode::SIZE:
                push_value(frame, builtin_size(machine, pop_value(frame)));
                break;
            case Opcode::CONCAT_STR: {
                const std::int64_t count =
                    operand_integer(instruction, "count");
                const std::vector<Value> values =
                    collect_arguments(frame, static_cast<std::size_t>(count));
                std::u32string text;
                for (const Value& value : values) {
                    if (value.tag == Tag::Str) {
                        text += as_string_const(value)->code_points;
                    }
                }
                push_value(
                    frame,
                    make_string(machine.arena.allocate_string(
                        std::move(text))));
                break;
            }
            case Opcode::TO_STRING: {
                const Value value = pop_value(frame);
                push_value(
                    frame, string_from_utf8(machine, format_value(value)));
                break;
            }
            case Opcode::REVERSE:
                push_value(
                    frame, reverse_value(machine, pop_value(frame)));
                break;
            case Opcode::DECLARE_LOCAL: {
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                const std::int64_t flags =
                    operand_integer(instruction, "flags");
                if (!(flags & 1) && frame.declared[slot]) {
                    runtime_fail("Cannot redefine variables");
                }
                frame.declared[slot] = true;
                Value undefined = make_undef();
                if (instruction.find("spec") != nullptr) {
                    const std::int64_t spec_index =
                        operand_integer(instruction, "spec");
                    if (spec_index >= 0
                        && static_cast<std::uint64_t>(spec_index)
                            < code.constants.size()) {
                        undefined = make_typed_undef(
                            machine,
                            constant_type_name(
                                code.constants[static_cast<std::size_t>(
                                    spec_index)]));
                    }
                }
                frame.locals[slot] = undefined;
                publish_module_local(frame, slot, frame.locals[slot]);
                push_value(frame, frame.locals[slot]);
                break;
            }
            case Opcode::DECLARE_TYPED:
            case Opcode::DECLARE_INFER: {
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                frame.declared[slot] = true;
                Value value = copy_value(machine.arena, pop_value(frame));
                if (instruction.find("spec") != nullptr) {
                    const std::int64_t spec_index =
                        operand_integer(instruction, "spec");
                    apply_declared_spec_flags(
                        code, spec_index, value);
                    if (spec_index >= 0
                        && static_cast<std::uint64_t>(spec_index)
                            < code.constants.size()) {
                        const std::string& spec_text =
                            code.constants[static_cast<std::size_t>(
                                spec_index)].text;
                        const std::size_t name_at =
                            spec_text.find("\"value\":\"");
                        if (name_at != std::string::npos) {
                            const std::size_t start = name_at + 9;
                            const std::size_t end =
                                spec_text.find('"', start);
                            if (end != std::string::npos) {
                                const std::string type_name =
                                    spec_text.substr(
                                        start, end - start);
                                const std::size_t alternatives_at =
                                    spec_text.find("\"alternatives\":");
                                const bool is_union =
                                    alternatives_at != std::string::npos
                                    && spec_text.compare(
                                           alternatives_at + 15, 2, "[]")
                                        != 0;
                                const bool is_weak =
                                    spec_text.find("\"weak\":true")
                                    != std::string::npos;
                                if (!type_name.empty()
                                    && type_name != "any"
                                    && type_name != "mixed"
                                    && !is_union
                                    && !(is_weak
                                         && value.tag == Tag::Nova)) {
                                    value = cast_value(
                                        machine, frame, value,
                                        type_name);
                                    value = coerce_declared_value(
                                        machine, frame, type_name,
                                        value);
                                }
                            }
                        }
                    }
                }
                frame.locals[slot] = value;
                publish_module_local(frame, slot, value);
                push_value(frame, value);
                break;
            }
            case Opcode::DECLARE_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                const std::int64_t flags =
                    operand_integer(instruction, "flags");
                if (!(flags & 1)
                    && frame.module->declared_globals.count(name) != 0) {
                    runtime_fail("Cannot redefine variables");
                }
                frame.module->declared_globals.insert(name);
                Value undefined = make_undef();
                if (instruction.find("spec") != nullptr) {
                    const std::int64_t spec_index =
                        operand_integer(instruction, "spec");
                    if (spec_index >= 0
                        && static_cast<std::uint64_t>(spec_index)
                            < code.constants.size()) {
                        undefined = make_typed_undef(
                            machine,
                            constant_type_name(
                                code.constants[static_cast<std::size_t>(
                                    spec_index)]));
                    }
                }
                frame.module->globals[name] = undefined;
                push_value(frame, undefined);
                break;
            }
            case Opcode::DECLARE_TYPED_GLOBAL:
            case Opcode::DECLARE_INFER_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                if (frame.module->declared_globals.count(name) != 0) {
                    runtime_fail("Cannot redefine variables");
                }
                frame.module->declared_globals.insert(name);
                Value value = copy_value(machine.arena, pop_value(frame));
                if (instruction.find("spec") != nullptr) {
                    apply_declared_spec_flags(
                        code, operand_integer(instruction, "spec"),
                        value);
                }
                frame.module->globals[name] = value;
                push_value(frame, value);
                break;
            }
            case Opcode::DECLARE_UNDEFINED_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                frame.module->declared_globals.insert(name);
                Value undefined = make_undef();
                if (instruction.find("spec") != nullptr) {
                    const std::int64_t spec_index =
                        operand_integer(instruction, "spec");
                    if (spec_index >= 0
                        && static_cast<std::uint64_t>(spec_index)
                            < code.constants.size()) {
                        undefined = make_typed_undef(
                            machine,
                            constant_type_name(
                                code.constants[static_cast<std::size_t>(
                                    spec_index)]));
                    }
                }
                frame.module->globals[name] = undefined;
                push_value(frame, undefined);
                break;
            }
            case Opcode::DECLARE_EXTERN: {
                const std::int64_t spec_index =
                    operand_integer(instruction, "extern");
                if (meta == nullptr) {
                    throw RuntimeError("extern metadata is required");
                }
                const MetaDescriptor* descriptor = find_descriptor(
                    *meta, code_index_of(image, code),
                    static_cast<std::uint32_t>(spec_index));
                if (descriptor == nullptr
                    || descriptor->kind != MetaDescriptor::Kind::Extern) {
                    throw RuntimeError("missing native extern descriptor");
                }
                const std::size_t dot =
                    descriptor->python_target.find('.');
                const std::string module_name =
                    dot == std::string::npos
                    ? descriptor->python_target
                    : descriptor->python_target.substr(0, dot);
                static const std::unordered_set<std::string>
                    kDefaultExternModules = {
                        "math", "stdlib_strings", "stdlib_json",
                        "stdlib_url", "stdlib_env", "stdlib_time",
                        "stdlib_crypto", "stdlib_http",
                        "stdlib_http_server", "stdlib_http_router",
                        "stdlib_log", "stdlib_host",
                    };
                bool allowed =
                    kDefaultExternModules.count(module_name) != 0;
                if (!allowed && machine.has_project) {
                    for (const std::string& candidate :
                         machine.project.module_names) {
                        if (candidate == module_name) {
                            allowed = true;
                            break;
                        }
                    }
                }
                if (!allowed) {
                    throw_error(error_module(
                        machine.arena, "extern",
                        "Module is not allowed in the extern enviroment",
                        {"module: " + module_name}));
                }
                if (descriptor->name.empty()) {
                    throw_error(make_error(
                        machine.arena, "EXTERN", "extern type",
                        "extern type declarations are not supported yet",
                        {"python type: " + descriptor->python_target}));
                }
                frame.module->externs[descriptor->name] = *descriptor;
                FunctionMetadata metadata;
                metadata.name = descriptor->name;
                metadata.min_argc = descriptor->min_argc;
                frame.module->extern_metadata.push_back(
                    std::move(metadata));
                FunctionObject* function =
                    machine.arena.allocate_function(
                        &frame.module->extern_metadata.back());
                function->module = frame.module;
                function->extern_descriptor = descriptor;
                frame.module->functions[descriptor->name].push_back(
                    function);
                break;
            }
            case Opcode::DECLARE_FUNCTION: {
                const std::int64_t index =
                    operand_integer(instruction, "function");
                if (meta == nullptr) {
                    runtime_fail("function metadata is required");
                }
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= meta->functions.size()) {
                    runtime_fail(
                        "function index out of range: "
                        + std::to_string(index));
                }
                const FunctionMetadata& metadata =
                    meta->functions[static_cast<std::size_t>(index)];
                FunctionObject* function =
                    machine.arena.allocate_function(&metadata);
                function->module = frame.module;
                frame.module->functions[metadata.name].push_back(function);
                push_value(frame, make_function(function));
                break;
            }
            case Opcode::MAKE_FUNCTION: {
                const std::int64_t index =
                    operand_integer(instruction, "function");
                if (meta == nullptr) {
                    runtime_fail("function metadata is required");
                }
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= meta->functions.size()) {
                    runtime_fail(
                        "function index out of range: "
                        + std::to_string(index));
                }
                const FunctionMetadata& metadata =
                    meta->functions[static_cast<std::size_t>(index)];
                FunctionObject* function =
                    machine.arena.allocate_function(&metadata);
                function->module = frame.module;
                if (meta_flag(metadata, MetaFunctionFlag::Lambda)) {
                    capture_scope(
                        machine, *function, frame,
                        meta_flag(
                            metadata, MetaFunctionFlag::MutableCapture));
                    if (metadata.lambda_name.has_value()) {
                        function->captured.functions[
                            *metadata.lambda_name].push_back(function);
                    }
                }
                push_value(frame, make_function(function));
                break;
            }
            case Opcode::REF_LOCAL: {
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                const Value value = frame.locals[slot];
                const std::string name =
                    slot < code.local_names.size()
                    ? code.local_names[slot] : std::string();
                if (is_reference(value)) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Cannot take a reference to a reference",
                        {"'" + name + "' already holds a reference"}));
                }
                if (is_const(value)) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Cannot take a reference to a constant",
                        {
                            "'" + name + "' is constant",
                            "references mutate the target, so the target "
                            "must be assignable",
                        }));
                }
                RefObject* reference = machine.arena.allocate_reference();
                reference->kind = RefObject::Kind::Local;
                reference->frame = &frame;
                reference->lifetime = frame.lifetime;
                reference->generation = frame.lifetime->generation;
                reference->slot = slot;
                reference->target_type = runtime_type_name(value);
                reference->is_const = is_const(value);
                push_value(frame, make_reference(reference));
                break;
            }
            case Opcode::REF_GLOBAL: {
                const std::string& name =
                    global_name_at(image, instruction, "name");
                const auto found = frame.module->globals.find(name);
                if (found == frame.module->globals.end()) {
                    throw_error(error_identifier_not_found(
                        machine.arena, "reference expression", name));
                }
                const Value value = found->second;
                if (is_reference(value)) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Cannot take a reference to a reference",
                        {"'" + name + "' already holds a reference"}));
                }
                if (is_const(value)) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Cannot take a reference to a constant",
                        {
                            "'" + name + "' is constant",
                            "references mutate the target, so the target "
                            "must be assignable",
                        }));
                }
                RefObject* reference = machine.arena.allocate_reference();
                reference->kind = RefObject::Kind::Global;
                reference->module = frame.module;
                reference->name = name;
                reference->target_type = runtime_type_name(value);
                reference->is_const = is_const(value);
                push_value(frame, make_reference(reference));
                break;
            }
            case Opcode::REF_FIELD: {
                const Value owner = pop_value(frame);
                const std::string& name =
                    global_name_at(image, instruction, "field");
                if (owner.tag == Tag::Module) {
                    throw_error(error_module(
                        machine.arena, "reference expression",
                        "Modules are immutable",
                        {"module properties cannot be referenced"}));
                }
                if (owner.tag != Tag::Obj) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Only object properties can be referenced",
                        {"but " + std::string(tag_name(owner.tag))
                             + " was encountered"}));
                }
                ObjectObject* object = as_object(owner);
                const auto field = object->fields.find(name);
                if (field == object->fields.end()) {
                    throw_error(error_identifier_not_found(
                        machine.arena, "reference expression", name,
                        {"perhaps it is a private property?"}));
                }
                if (object->private_fields.count(name) != 0
                    && !private_access_allowed(machine, frame, *object)) {
                    throw_error(error_identifier_not_found(
                        machine.arena, "reference expression", name,
                        {"perhaps it is a private property?"}));
                }
                if (object->structure_locked) {
                    throw_error(error_const(
                        machine.arena, "reference expression",
                        "object fields are locked",
                        {"the object type ends with '!'"}));
                }
                if (is_reference(field->second)) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Cannot take a reference to a reference",
                        {"'" + name + "' already holds a reference"}));
                }
                if (is_const(field->second)) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Cannot take a reference to a constant",
                        {
                            "'" + name + "' is constant",
                            "references mutate the target, so the target "
                            "must be assignable",
                        }));
                }
                RefObject* reference = machine.arena.allocate_reference();
                reference->kind = RefObject::Kind::Field;
                reference->object = object;
                reference->name = name;
                reference->target_type =
                    runtime_type_name(field->second);
                reference->is_const = is_const(field->second);
                push_value(frame, make_reference(reference));
                break;
            }
            case Opcode::REF_INDEX: {
                const Value index = pop_value(frame);
                const Value container = pop_value(frame);
                if (container.tag != Tag::Arr) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Only array elements can be referenced by index",
                        {"but " + std::string(tag_name(container.tag))
                             + " was encountered"}));
                }
                if (index.tag != Tag::Int) {
                    throw_error(error_reference(
                        machine.arena, "reference expression",
                        "Array references need an int index",
                        {"but " + std::string(tag_name(index.tag))
                             + " was encountered"}));
                }
                ArrayObject* array = as_array(container);
                const std::int64_t original = index.i;
                std::int64_t position = original;
                const std::int64_t length = static_cast<std::int64_t>(
                    array->items.size());
                if (position < 0) {
                    position += length;
                }
                if (position < 0 || position >= length) {
                    throw_error(error_index_out_of_range(
                        machine.arena, original, length));
                }
                if (array->elements_locked) {
                    throw_error(error_const(
                        machine.arena, "reference expression",
                        "array elements are locked",
                        {"the element type ends with '!'"}));
                }
                RefObject* reference = machine.arena.allocate_reference();
                reference->kind = RefObject::Kind::Index;
                reference->array = array;
                reference->index = static_cast<std::size_t>(position);
                reference->target_type = runtime_type_name(
                    array->items[static_cast<std::size_t>(position)]);
                reference->is_const = is_const(
                    array->items[static_cast<std::size_t>(position)]);
                push_value(frame, make_reference(reference));
                break;
            }
            case Opcode::LOAD_REF: {
                const Value reference = pop_value(frame);
                if (!is_reference(reference)) {
                    throw RuntimeError("LOAD_REF expects a reference");
                }
                push_value(
                    frame,
                    reference_get(machine, as_reference(reference)));
                break;
            }
            case Opcode::STORE_REF: {
                const Value value = pop_value(frame);
                const Value reference = pop_value(frame);
                if (!is_reference(reference)) {
                    throw RuntimeError("STORE_REF expects a reference");
                }
                RefObject* target = as_reference(reference);
                const Value current = reference_get(machine, target);
                (void)current;
                if (target->is_const) {
                    throw_error(error_const(
                        machine.arena, "assignment", "constant assign",
                        {"trying to assign into a const "
                             + target->target_type}));
                }
                if (target->kind == RefObject::Kind::Field
                    && target->object != nullptr
                    && target->object->structure_locked) {
                    throw_error(error_const(
                        machine.arena, "assignment",
                        "object fields are locked",
                        {"the object type ends with '!'"}));
                }
                if (target->kind == RefObject::Kind::Index
                    && target->array != nullptr
                    && target->array->elements_locked) {
                    throw_error(error_const(
                        machine.arena, "assignment",
                        "array elements are locked",
                        {"the element type ends with '!'"}));
                }
                reference_set(machine, target, value);
                break;
            }
            case Opcode::IMPORT: {
                const std::int64_t module_index =
                    operand_integer(instruction, "module");
                if (module_index < 0) {
                    runtime_fail("IMPORT module index is negative");
                }
                const BundleImport* binding = frame.module->import_for(
                    static_cast<std::uint32_t>(module_index));
                if (binding == nullptr) {
                    throw RuntimeError("IMPORT has no bundle binding");
                }
                ModuleRuntime& target =
                    machine.modules.get(binding->target_module_id);
                initialize_module(target, machine);
                const Value module_value = make_module(&target);
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                bool has_existing = false;
                Value existing;
                if (is_defined(frame.locals[slot])) {
                    existing = frame.locals[slot];
                    has_existing = true;
                } else if (frame.function != nullptr) {
                    const auto reference =
                        frame.function->captured.references.find(
                            binding->alias);
                    if (reference
                        != frame.function->captured.references.end()) {
                        existing = *reference->second;
                        has_existing = true;
                    } else {
                        const auto captured =
                            frame.function->captured.values.find(
                                binding->alias);
                        if (captured
                            != frame.function->captured.values.end()) {
                            existing = captured->second;
                            has_existing = true;
                        }
                    }
                } else {
                    const auto global =
                        frame.module->globals.find(binding->alias);
                    if (global != frame.module->globals.end()) {
                        existing = global->second;
                        has_existing = true;
                    }
                }
                if (has_existing
                    && (existing.tag != Tag::Module
                        || existing.ref != module_value.ref)) {
                    throw_error(error_module(
                        machine.arena, "use expression",
                        "Import collision for '" + binding->alias + "'",
                        {
                            "module '" + target.name
                                + "' cannot be bound",
                            "'" + binding->alias
                                + "' is already declared in this scope",
                        }));
                }
                frame.locals[slot] = module_value;
                frame.declared[slot] = true;
                if (frame.is_module) {
                    frame.module->globals[binding->alias] = module_value;
                    frame.module->aliases[binding->alias] = &target;
                }
                if (target.legacy && !binding->explicit_alias) {
                    import_wildcard(target, frame, machine);
                }
                break;
            }
            case Opcode::IMPORT_WILDCARD: {
                const std::int64_t module_index =
                    operand_integer(instruction, "module");
                if (module_index < 0) {
                    runtime_fail("IMPORT_WILDCARD module index is negative");
                }
                const BundleImport* binding = frame.module->import_for(
                    static_cast<std::uint32_t>(module_index));
                if (binding == nullptr) {
                    throw RuntimeError(
                        "IMPORT_WILDCARD has no bundle binding");
                }
                ModuleRuntime& target =
                    machine.modules.get(binding->target_module_id);
                initialize_module(target, machine);
                import_wildcard(target, frame, machine);
                break;
            }
            case Opcode::LOAD_MODULE_MEMBER: {
                const std::int64_t module_index =
                    operand_integer(instruction, "module");
                const std::int64_t export_index =
                    operand_integer(instruction, "export");
                if (module_index < 0) {
                    runtime_fail(
                        "LOAD_MODULE_MEMBER module index is negative");
                }
                const BundleImport* binding = frame.module->import_for(
                    static_cast<std::uint32_t>(module_index));
                if (binding == nullptr) {
                    throw RuntimeError(
                        "LOAD_MODULE_MEMBER has no bundle binding");
                }
                ModuleRuntime& target =
                    machine.modules.get(binding->target_module_id);
                initialize_module(target, machine);
                if (static_cast<std::uint64_t>(module_index)
                    >= image.modules.size()) {
                    runtime_fail("module index is out of range");
                }
                const ModuleInfo& pseudo =
                    image.modules[static_cast<std::size_t>(module_index)];
                std::string member;
                if (export_index >= 0
                    && static_cast<std::uint64_t>(export_index)
                        < pseudo.exports.size()) {
                    member = pseudo.exports[
                        static_cast<std::size_t>(export_index)].first;
                } else if (export_index >= 0
                           && static_cast<std::uint64_t>(export_index)
                               < image.global_names.size()) {
                    member = image.global_names[
                        static_cast<std::size_t>(export_index)];
                } else {
                    runtime_fail("module export index is out of range");
                }
                push_value(
                    frame,
                    module_member_value(
                        machine, target, member, "access expression"));
                break;
            }
            case Opcode::LOAD_PROJECT:
                push_value(
                    frame,
                    machine.has_project
                        ? make_project(&machine.project)
                        : make_nova());
                break;
            case Opcode::EXPORT:
                (void)pop_value(frame);
                break;
            case Opcode::LOAD_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                const auto found = frame.module->globals.find(name);
                if (found == frame.module->globals.end()) {
                    throw_error(error_identifier_not_found(
                        machine.arena, "", name));
                }
                push_value(
                    frame, unwrap_reference(machine, found->second));
                break;
            }
            case Opcode::STORE_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                const Value value =
                    copy_value(machine.arena, pop_value(frame));
                frame.module->globals[name] = value;
                sync_module_global(machine, *frame.module, name, value);
                break;
            }
            case Opcode::LOAD_NAME: {
                const std::string& name = global_name_at(image, instruction);
                push_value(frame, resolve_name(machine, frame, name));
                break;
            }
            case Opcode::LOAD_FREE: {
                const std::string& name = global_name_at(image, instruction);
                Value value;
                if (!try_resolve_free(machine, frame, name, value)) {
                    throw_error(error_identifier_not_found(
                        machine.arena, "", name));
                }
                push_value(frame, unwrap_reference(machine, value));
                break;
            }
            case Opcode::STORE_NAME:
            case Opcode::ASSIGN_NAME: {
                const std::string& name = global_name_at(image, instruction);
                const Value value =
                    copy_value(machine.arena, pop_value(frame));
                assign_name(machine, frame, name, value);
                break;
            }
            case Opcode::SCOPE_PUSH:
            case Opcode::SCOPE_POP:
                break;
            case Opcode::LOAD_CAPTURE: {
                const std::int64_t index =
                    operand_integer(instruction, "index");
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= frame.captures.size()) {
                    runtime_fail("capture index out of range");
                }
                push_value(
                    frame, frame.captures[static_cast<std::size_t>(index)]);
                break;
            }
            case Opcode::MAKE_CAPTURE: {
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                frame.captures.push_back(frame.locals[slot]);
                break;
            }
            case Opcode::MAKE_SPREAD: {
                const Value value = pop_value(frame);
                std::vector<Value> items;
                if (value.tag == Tag::Arr) {
                    items = as_array(value)->items;
                } else if (value.tag == Tag::Tup) {
                    items = as_tuple(value)->items;
                } else if (value.tag == Tag::Set) {
                    items = as_set(value)->items;
                } else if (value.tag == Tag::Map) {
                    for (const auto& entry :
                         as_map(value)->entries) {
                        items.push_back(make_tuple(
                            machine.arena.allocate_tuple(
                                {entry.first, entry.second})));
                    }
                } else if (value.tag == Tag::Str) {
                    for (const char32_t code_point :
                         as_string_const(value)->code_points) {
                        items.push_back(make_char(code_point));
                    }
                } else {
                    runtime_fail(
                        "spread requires a container or string");
                }
                push_value(
                    frame,
                    make_spread(machine.arena.allocate_array(
                        std::move(items))));
                break;
            }
            case Opcode::COPY:
                push_value(
                    frame,
                    copy_value(machine.arena, pop_value(frame)));
                break;
            case Opcode::ITER_NEW: {
                const Value iterable = pop_value(frame);
                std::vector<Value> values;
                switch (iterable.tag) {
                    case Tag::Arr:
                        values = as_array(iterable)->items;
                        break;
                    case Tag::Tup:
                        values = as_tuple(iterable)->items;
                        break;
                    case Tag::Str:
                        for (const char32_t code_point :
                             as_string_const(iterable)->code_points) {
                            values.push_back(make_char(code_point));
                        }
                        break;
                    case Tag::Set:
                        values = as_set(iterable)->items;
                        break;
                    case Tag::Map:
                        for (const auto& entry :
                             as_map(iterable)->entries) {
                            std::vector<Value> pair = {
                                entry.first, entry.second};
                            values.push_back(make_array(
                                machine.arena.allocate_array(
                                    std::move(pair))));
                        }
                        break;
                    default:
                        runtime_fail(
                            "for each expression is not an iterable value");
                }
                IteratorObject* iterator =
                    machine.arena.allocate_iterator(std::move(values));
                push_value(frame, make_iterator(iterator));
                break;
            }
            case Opcode::ITER_NEXT: {
                const Value iterator_value = peek_value(frame, 0);
                if (!is_iterator(iterator_value)) {
                    runtime_fail("ITER_NEXT without an iterator");
                }
                IteratorObject* iterator = as_iterator(iterator_value);
                if (iterator->index >= iterator->values.size()) {
                    (void)pop_value(frame);
                    frame.ip = operand_target(instruction, code);
                } else {
                    const Value item = iterator->values[iterator->index];
                    ++iterator->index;
                    push_value(frame, item);
                }
                break;
            }
            case Opcode::CAST: {
                const std::int64_t spec_index =
                    operand_integer(instruction, "spec");
                if (spec_index < 0
                    || static_cast<std::uint64_t>(spec_index)
                        >= code.constants.size()) {
                    runtime_fail("cast spec index out of range");
                }
                const Constant& spec =
                    code.constants[static_cast<std::size_t>(spec_index)];
                std::string target;
                const std::size_t name_at =
                    spec.text.find("\"value\":\"");
                if (name_at != std::string::npos) {
                    const std::size_t start = name_at + 9;
                    const std::size_t end = spec.text.find('"', start);
                    if (end != std::string::npos) {
                        target = spec.text.substr(start, end - start);
                    }
                }
                push_value(
                    frame,
                    cast_value(
                        machine, frame, pop_value(frame), target));
                break;
            }
            case Opcode::CAST_ASSIGN:
            case Opcode::CAST_RETURN:
            case Opcode::BOX_ANY:
            case Opcode::UNBOX_ANY:
                push_value(frame, pop_value(frame));
                break;
            case Opcode::TYPE_CHECK:
                (void)pop_value(frame);
                push_value(frame, make_bool(true));
                break;
            case Opcode::TYPE_CHECK_NOT:
                (void)pop_value(frame);
                push_value(frame, make_bool(false));
                break;
            case Opcode::IS_NOVA: {
                const Value value = pop_value(frame);
                push_value(frame, make_bool(value.tag == Tag::Nova));
                break;
            }
            case Opcode::IS_DEFINED: {
                const Value value = pop_value(frame);
                push_value(frame, make_bool(value.tag != Tag::Undef));
                break;
            }
            case Opcode::IS_WEAK:
                (void)pop_value(frame);
                push_value(frame, make_bool(false));
                break;
            case Opcode::LOAD_LOCAL:
                push_value(
                    frame,
                    unwrap_reference(
                        machine,
                        frame.locals[operand_slot(
                            instruction, code, "slot")]));
                break;
            case Opcode::STORE_LOCAL: {
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                frame.locals[slot] =
                    copy_value(machine.arena, pop_value(frame));
                publish_module_local(frame, slot, frame.locals[slot]);
                break;
            }
            case Opcode::ASSIGN_LOCAL: {
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                const Value value = pop_value(frame);
                if (is_reference(frame.locals[slot])) {
                    reference_set(
                        machine, as_reference(frame.locals[slot]), value);
                    break;
                }
                frame.locals[slot] =
                    copy_value(machine.arena, value);
                publish_module_local(frame, slot, frame.locals[slot]);
                break;
            }
            case Opcode::LOAD_RAW:
                push_value(
                    frame,
                    frame.locals[operand_slot(instruction, code, "slot")]);
                break;
            case Opcode::STORE_RAW: {
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                frame.locals[slot] = pop_value(frame);
                publish_module_local(frame, slot, frame.locals[slot]);
                break;
            }
            case Opcode::LOAD_THIS:
                if (!frame.has_receiver) {
                    runtime_fail("this is not available in this frame");
                }
                push_value(frame, frame.receiver);
                break;
            case Opcode::NEW_ENUM:
            case Opcode::LOAD_ENUM_MEMBER: {
                const std::int64_t enum_index =
                    operand_integer(instruction, "enum");
                const std::int64_t variant =
                    operand_integer(instruction, "variant");
                if (enum_index < 0
                    || static_cast<std::uint64_t>(enum_index)
                        >= image.types.size()) {
                    runtime_fail("enum type index out of range");
                }
                const TypeInfo& info =
                    image.types[static_cast<std::size_t>(enum_index)];
                if (variant < 0
                    || static_cast<std::uint64_t>(variant)
                        >= info.variants.size()) {
                    runtime_fail("enum variant index out of range");
                }
                const std::string& variant_name =
                    info.variants[static_cast<std::size_t>(variant)];
                ObjectObject* object = machine.arena.allocate_object(
                    info.name, true, variant_name);
                const auto runtime =
                    frame.module->types.find(info.name);
                if (runtime != frame.module->types.end()) {
                    object->type = &runtime->second;
                }
                object->module = frame.module;
                object->fields["name"] =
                    string_from_utf8(machine, variant_name);
                push_value(frame, make_object(object));
                break;
            }
            case Opcode::LOAD_FIELD: {
                const std::string& name =
                    global_name_at(image, instruction, "field");
                const Value owner = pop_value(frame);
                push_value(
                    frame,
                    load_object_member(
                        machine, frame, owner, name, false, false));
                break;
            }
            case Opcode::STORE_FIELD: {
                const std::string& name =
                    global_name_at(image, instruction, "field");
                const Value value = pop_value(frame);
                const Value owner = pop_value(frame);
                push_value(
                    frame,
                    store_object_member(
                        machine, frame, owner, name, value));
                break;
            }
            case Opcode::LOAD_MEMBER:
            case Opcode::LOAD_MEMBER_SAFE: {
                const std::string& name =
                    global_name_at(image, instruction, "name");
                const Value owner = pop_value(frame);
                push_value(
                    frame,
                    load_object_member(
                        machine, frame, owner, name,
                        static_cast<Opcode>(instruction.opcode)
                            == Opcode::LOAD_MEMBER_SAFE,
                        true));
                break;
            }
            case Opcode::STORE_MEMBER: {
                const std::string& name =
                    global_name_at(image, instruction, "name");
                const Value value = pop_value(frame);
                const Value owner = pop_value(frame);
                push_value(
                    frame,
                    store_object_member(
                        machine, frame, owner, name, value));
                break;
            }
            case Opcode::SET_LOCKS: {
                const std::int64_t flags =
                    operand_integer(instruction, "flags");
                const Value owner = pop_value(frame);
                if (owner.tag == Tag::Arr) {
                    if ((flags & 2) != 0) {
                        as_array(owner)->elements_locked = true;
                    }
                    break;
                }
                if (owner.tag != Tag::Obj) {
                    runtime_fail("locks require an object value or array");
                }
                ObjectObject* object = as_object(owner);
                if ((flags & 1) != 0) {
                    object->structure_locked = true;
                }
                if ((flags & 2) != 0) {
                    object->elements_locked = true;
                }
                break;
            }
            case Opcode::CHECK_TRAIT:
            case Opcode::TRAIT_CAST: {
                const std::int64_t index =
                    operand_integer(instruction, "trait");
                const Value value = pop_value(frame);
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= image.traits.size()
                    || value.tag != Tag::Obj) {
                    runtime_fail("value does not satisfy the trait");
                }
                const TraitInfo& info = image.traits[
                    static_cast<std::size_t>(index)];
                ObjectObject* object = as_object(value);
                const TraitRuntime* trait = nullptr;
                if (object->type != nullptr
                    && object->type->module != nullptr) {
                    const auto found =
                        object->type->module->traits.find(info.name);
                    if (found != object->type->module->traits.end()) {
                        trait = &found->second;
                    }
                }
                if (trait == nullptr) {
                    const auto found =
                        frame.module->traits.find(info.name);
                    if (found != frame.module->traits.end()) {
                        trait = &found->second;
                    }
                }
                if (trait == nullptr
                    || !object_satisfies_trait(machine, *object, *trait)) {
                    runtime_fail(
                        "value does not satisfy trait '" + info.name + "'");
                }
                push_value(frame, value);
                break;
            }
            case Opcode::ADD:
            case Opcode::ADD_TYPED: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (instruction.opcode
                        == static_cast<std::uint8_t>(Opcode::ADD_TYPED)
                    && is_numeric_operand(left)
                    && is_numeric_operand(right)) {
                    push_value(
                        frame,
                        make_num(as_double(left) + as_double(right)));
                    break;
                }
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "add", {right}, "operator +"));
                    break;
                }
                push_value(frame, arithmetic_add(machine, left, right));
                break;
            }
            case Opcode::SUB:
            case Opcode::SUB_TYPED: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (instruction.opcode
                        == static_cast<std::uint8_t>(Opcode::SUB_TYPED)
                    && is_numeric_operand(left)
                    && is_numeric_operand(right)) {
                    push_value(
                        frame,
                        make_num(as_double(left) - as_double(right)));
                    break;
                }
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "subtract", {right}, "operator -"));
                    break;
                }
                push_value(frame, arithmetic_sub(machine, left, right));
                break;
            }
            case Opcode::MUL:
            case Opcode::MUL_TYPED: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (instruction.opcode
                        == static_cast<std::uint8_t>(Opcode::MUL_TYPED)
                    && is_numeric_operand(left)
                    && is_numeric_operand(right)) {
                    push_value(
                        frame,
                        make_num(as_double(left) * as_double(right)));
                    break;
                }
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "multiply", {right}, "operator *"));
                    break;
                }
                push_value(frame, arithmetic_mul(machine, left, right));
                break;
            }
            case Opcode::DIV:
            case Opcode::DIV_TYPED: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (instruction.opcode
                        == static_cast<std::uint8_t>(Opcode::DIV_TYPED)
                    && is_numeric_operand(left)
                    && is_numeric_operand(right)) {
                    const double divisor = as_double(right);
                    if (divisor == 0.0) {
                        push_value(frame, make_nova());
                    } else {
                        push_value(
                            frame,
                            make_num(as_double(left) / divisor));
                    }
                    break;
                }
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "divide", {right}, "operator /"));
                    break;
                }
                push_value(frame, arithmetic_div(machine, left, right));
                break;
            }
            case Opcode::MOD:
            case Opcode::MOD_TYPED: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "remainder", {right}, "operator %"));
                    break;
                }
                push_value(frame, arithmetic_mod(machine, left, right));
                break;
            }
            case Opcode::NEG: {
                const Value value = pop_value(frame);
                if (value.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, value, "negate", {}, "operator -"));
                    break;
                }
                if (value.tag != Tag::Int && value.tag != Tag::BigInt
                    && value.tag != Tag::Num) {
                    throw_error(make_error(
                        machine.arena, "PREFIX", "",
                        "Unsupported prefix",
                        {
                            "for prefix \"-\"",
                            "and type \""
                                + runtime_type_name(value) + "\"",
                        }));
                }
                push_value(frame, arithmetic_negate(machine, value));
                break;
            }
            case Opcode::NOT:
                push_value(frame, make_bool(!truthy(pop_value(frame))));
                break;
            case Opcode::TO_BOOL:
                push_value(frame, make_bool(truthy(pop_value(frame))));
                break;
            case Opcode::EQ:
            case Opcode::EQ_TYPED:
            case Opcode::NEQ:
            case Opcode::NEQ_TYPED:
            case Opcode::LT:
            case Opcode::LT_TYPED:
            case Opcode::LE:
            case Opcode::LE_TYPED:
            case Opcode::GT:
            case Opcode::GT_TYPED:
            case Opcode::GE:
            case Opcode::GE_TYPED: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                const Comparison comparison =
                    (left.tag == Tag::Obj || right.tag == Tag::Obj)
                    ? compare_object_values(
                        machine, left, right, instruction.spec->name)
                    : compare_values(
                        machine, left, right,
                        instruction.spec->name);
                bool result = false;
                switch (static_cast<Opcode>(instruction.opcode)) {
                    case Opcode::EQ:
                    case Opcode::EQ_TYPED:
                        result = !comparison.unordered
                            && comparison.order == 0;
                        break;
                    case Opcode::NEQ:
                    case Opcode::NEQ_TYPED:
                        result = comparison.unordered
                            || comparison.order != 0;
                        break;
                    case Opcode::LT:
                    case Opcode::LT_TYPED:
                        result = !comparison.unordered
                            && comparison.order < 0;
                        break;
                    case Opcode::LE:
                    case Opcode::LE_TYPED:
                        result = !comparison.unordered
                            && comparison.order <= 0;
                        break;
                    case Opcode::GT:
                    case Opcode::GT_TYPED:
                        result = !comparison.unordered
                            && comparison.order > 0;
                        break;
                    case Opcode::GE:
                    case Opcode::GE_TYPED:
                        result = !comparison.unordered
                            && comparison.order >= 0;
                        break;
                    default:
                        break;
                }
                push_value(frame, make_bool(result));
                break;
            }
            case Opcode::JUMP:
                frame.ip = operand_target(instruction, code);
                break;
            case Opcode::JUMP_IF_FALSE: {
                const Value condition = pop_value(frame);
                if (!truthy(condition)) {
                    frame.ip = operand_target(instruction, code);
                }
                break;
            }
            case Opcode::JUMP_IF_TRUE: {
                const Value condition = pop_value(frame);
                if (truthy(condition)) {
                    frame.ip = operand_target(instruction, code);
                }
                break;
            }
            case Opcode::JUMP_IF_FALSE_KEEP:
                if (!truthy(peek_value(frame, 0))) {
                    frame.ip = operand_target(instruction, code);
                }
                break;
            case Opcode::JUMP_IF_TRUE_KEEP:
                if (truthy(peek_value(frame, 0))) {
                    frame.ip = operand_target(instruction, code);
                }
                break;
            case Opcode::JUMP_IF_NOVA: {
                const Value condition = pop_value(frame);
                if (condition.tag == Tag::Nova) {
                    frame.ip = operand_target(instruction, code);
                }
                break;
            }
            case Opcode::JUMP_IF_NOT_NOVA: {
                const Value condition = pop_value(frame);
                if (condition.tag != Tag::Nova) {
                    frame.ip = operand_target(instruction, code);
                }
                break;
            }
            case Opcode::CALL:
            case Opcode::CALL_VALUE:
            case Opcode::CALL_BUILTIN:
            case Opcode::CALL_NATIVE: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                std::vector<std::pair<std::string, Value>> named;
                std::vector<Value> positional =
                    flatten_arguments(site, std::move(raw), named);
                const Opcode call_opcode =
                    static_cast<Opcode>(instruction.opcode);
                if (call_opcode == Opcode::CALL_VALUE) {
                    const Value callee = pop_value(frame);
                    if (!is_function(callee)) {
                        runtime_fail(
                            "call expression target is not a function");
                    }
                    push_value(
                        frame,
                        invoke_function(
                            machine, as_function(callee),
                            std::move(positional), std::move(named),
                            "call expression"));
                    break;
                }
                if (call_opcode == Opcode::CALL_BUILTIN) {
                    push_value(
                        frame,
                        call_builtin(
                            machine, site.name, positional, named));
                    break;
                }
                if (call_opcode == Opcode::CALL_NATIVE) {
                    push_value(
                        frame,
                        call_native_method(
                            machine, site, positional, named));
                    break;
                }
                const std::vector<FunctionObject*>* candidates = nullptr;
                if (frame.function != nullptr) {
                    const auto found =
                        frame.function->captured.functions.find(site.name);
                    if (found != frame.function->captured.functions.end()) {
                        candidates = &found->second;
                    }
                }
                if (candidates == nullptr) {
                    const auto found =
                        frame.module->functions.find(site.name);
                    if (found != frame.module->functions.end()) {
                        candidates = &found->second;
                    }
                }
                std::vector<FunctionObject*> generic_candidates;
                if (candidates != nullptr
                    && site.type_argument_count > 0) {
                    for (FunctionObject* candidate : *candidates) {
                        if (candidate != nullptr
                            && candidate->metadata != nullptr
                            && candidate->metadata->type_parameters.size()
                                == site.type_argument_count) {
                            generic_candidates.push_back(candidate);
                        }
                    }
                    if (generic_candidates.empty()) {
                        throw_error(error_argument(
                            machine.arena,
                            "call: " + site.name,
                            "No generic overload of '" + site.name
                                + "' accepts "
                                + std::to_string(
                                    site.type_argument_count)
                                + " type arguments"));
                    }
                    candidates = &generic_candidates;
                }
                if (candidates != nullptr) {
                    if (candidates->empty()) {
                        runtime_fail(
                            "no function named '" + site.name + "'");
                    }
                    FunctionObject* function = nullptr;
                    if (!named.empty()) {
                        if (candidates->size() != 1) {
                            runtime_fail(
                                "Named arguments for '" + site.name
                                + "' require a single overload");
                        }
                        function = candidates->front();
                    } else {
                        if (meta == nullptr) {
                            runtime_fail(
                                "function metadata is required for '"
                                + site.name + "'");
                        }
                        function = select_overload(
                            *candidates, positional, *meta);
                    }
                    push_value(
                        frame,
                        invoke_function(
                            machine, function, std::move(positional),
                            std::move(named), "call: " + site.name,
                            nullptr, site.name));
                    break;
                }
                if (is_builtin_name(site.name)) {
                    push_value(
                        frame,
                        call_builtin(
                            machine, site.name, positional, named));
                    break;
                }
                Value variable;
                if (try_resolve_name(machine, frame, site.name, variable)
                    && is_function(variable)) {
                    push_value(
                        frame,
                        invoke_function(
                            machine, as_function(variable),
                            std::move(positional), std::move(named),
                            "call: " + site.name, nullptr, site.name));
                    break;
                }
                if (frame.module->externs.count(site.name) != 0) {
                    push_value(
                        frame,
                        call_extern_function(
                            machine, frame, site.name, positional, named));
                    break;
                }
                throw_error(error_identifier_not_found(
                    machine.arena, "call: " + site.name, site.name));
            }
            case Opcode::CALL_EXTERN: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                std::vector<std::pair<std::string, Value>> named;
                const std::vector<Value> positional =
                    flatten_arguments(site, raw, named);
                push_value(
                    frame,
                    call_extern_function(
                        machine, frame, site.name, positional, named));
                break;
            }
            case Opcode::CALL_MODULE: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                const Value target = pop_value(frame);
                std::vector<std::pair<std::string, Value>> named;
                const std::vector<Value> positional =
                    flatten_arguments(site, raw, named);
                if (target.tag == Tag::Module) {
                    ModuleRuntime* module = as_module(target);
                    push_value(
                        frame,
                        call_module_member(
                            machine, site, *module, positional, named,
                            "module: " + module->name));
                    break;
                }
                if (!named.empty()) {
                    throw_error(error_argument(
                        machine.arena, "call expression",
                        "Named arguments are not supported for this callee"));
                }
                if (target.tag == Tag::Fun) {
                    push_value(
                        frame,
                        invoke_function(
                            machine, as_function(target), positional, {},
                            "call expression"));
                    break;
                }
                if (target.tag == Tag::Arr) {
                    std::vector<FunctionObject*> candidates;
                    for (const Value& item : as_array(target)->items) {
                        if (is_function(item)) {
                            candidates.push_back(as_function(item));
                        }
                    }
                    if (!candidates.empty()) {
                        FunctionObject* function = select_overload(
                            candidates, positional, *frame.module->meta);
                        push_value(
                            frame,
                            invoke_function(
                                machine, function, positional, {},
                                "call expression"));
                        break;
                    }
                }
                throw_error(error_module(
                    machine.arena, "call expression",
                    "'<expression>' is not callable",
                    {"it is a " + std::string(tag_name(target.tag))
                         + " value"}));
            }
            case Opcode::CALL_METHOD: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                const Value receiver = pop_value(frame);
                std::vector<std::pair<std::string, Value>> named;
                const std::vector<Value> positional =
                    flatten_arguments(site, raw, named);
                if (receiver.tag == Tag::Module) {
                    ModuleRuntime* module = as_module(receiver);
                    push_value(
                        frame,
                        call_module_member(
                            machine, site, *module, positional, named,
                            "method call: " + site.name));
                    break;
                }
                if (receiver.tag == Tag::Type) {
                    TypeRuntime* runtime = as_type(receiver);
                    if (runtime == nullptr || runtime->info == nullptr) {
                        runtime_fail("null type receiver");
                    }
                    const auto statics = runtime->statics.find(site.name);
                    if (statics == runtime->statics.end()
                        || statics->second.empty()) {
                        throw_error(error_identifier_not_found(
                            machine.arena,
                            "method call: " + runtime->info->name + "."
                                + site.name,
                            "method: " + site.name,
                            {"perhaps is a private static method?"}));
                    }
                    ModuleRuntime* module = runtime->module;
                    if (module == nullptr || module->meta == nullptr) {
                        runtime_fail("static method metadata is required");
                    }
                    FunctionObject* function = select_overload(
                        statics->second, positional, *module->meta);
                    push_value(
                        frame,
                        invoke_function(
                            machine, function, positional, named,
                            "method call: " + runtime->info->name + "."
                                + site.name,
                            nullptr,
                            runtime->info->name + "." + site.name));
                    break;
                }
                if (receiver.tag == Tag::Str
                    || receiver.tag == Tag::Arr
                    || receiver.tag == Tag::Map
                    || receiver.tag == Tag::Set
                    || receiver.tag == Tag::Tup
                    || receiver.tag == Tag::Char
                    || receiver.tag == Tag::Task
                    || receiver.tag == Tag::File) {
                    std::vector<Value> native_arguments;
                    native_arguments.reserve(positional.size() + 1);
                    native_arguments.push_back(receiver);
                    native_arguments.insert(
                        native_arguments.end(),
                        positional.begin(), positional.end());
                    push_value(
                        frame,
                        call_native_method(
                            machine, site, native_arguments, named));
                    break;
                }
                if (receiver.tag != Tag::Obj) {
                    runtime_fail("method call requires an object receiver");
                }
                ObjectObject* object = as_object(receiver);
                TypeRuntime* type_ptr = object->type;
                if (type_ptr == nullptr) {
                    const auto type_it =
                        frame.module->types.find(object->type_name);
                    if (type_it == frame.module->types.end()) {
                        runtime_fail(
                            "unknown type '" + object->type_name + "'");
                    }
                    type_ptr = &type_it->second;
                }
                const TypeRuntime& type = *type_ptr;
                const std::vector<FunctionObject*>* candidates = nullptr;
                if (site.trait_name.has_value()) {
                    const auto trait =
                        type.trait_methods.find(*site.trait_name);
                    if (trait != type.trait_methods.end()) {
                        const auto found =
                            trait->second.find(site.name);
                        if (found != trait->second.end()) {
                            candidates = &found->second;
                        }
                    }
                }
                if (candidates == nullptr) {
                    const auto found = type.methods.find(site.name);
                    if (found != type.methods.end()) {
                        candidates = &found->second;
                    }
                }
                if (candidates == nullptr && frame.function != nullptr
                    && !frame.function->trait_qualifier.empty()) {
                    const auto trait = type.trait_methods.find(
                        frame.function->trait_qualifier);
                    if (trait != type.trait_methods.end()) {
                        const auto found =
                            trait->second.find(site.name);
                        if (found != trait->second.end()) {
                            candidates = &found->second;
                        }
                    }
                }
                if (candidates == nullptr) {
                    for (const auto& entry : type.trait_methods) {
                        const auto found =
                            entry.second.find(site.name);
                        if (found != entry.second.end()) {
                            candidates = &found->second;
                            break;
                        }
                    }
                }
                if (candidates == nullptr && type.module != nullptr) {
                    for (const auto& entry : type.module->traits) {
                        const auto found =
                            entry.second.defaults.find(site.name);
                        if (found != entry.second.defaults.end()) {
                            candidates = &found->second;
                            break;
                        }
                    }
                }
                if (candidates == nullptr) {
                    for (const auto& entry : frame.module->traits) {
                        const auto found =
                            entry.second.defaults.find(site.name);
                        if (found != entry.second.defaults.end()) {
                            candidates = &found->second;
                            break;
                        }
                    }
                }
                if (candidates == nullptr || candidates->empty()) {
                    runtime_fail("method not found: " + site.name);
                }
                const Meta& overload_meta =
                    type.module != nullptr && type.module->meta != nullptr
                    ? *type.module->meta : *meta;
                FunctionObject* function = select_overload(
                    *candidates, positional, overload_meta);
                if (function->is_private
                    && !private_access_allowed(machine, frame, *object)) {
                    runtime_fail("private method: " + site.name);
                }
                push_value(
                    frame,
                    invoke_function(
                        machine, function, positional, {},
                        "method call: " + site.name, &receiver,
                        runtime_type_name(receiver) + "." + site.name));
                break;
            }
            case Opcode::CALL_STATIC: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                std::vector<std::pair<std::string, Value>> named;
                const std::vector<Value> positional =
                    flatten_arguments(site, raw, named);
                if (!site.type_name.has_value()) {
                    runtime_fail("static call requires a type name");
                }
                TypeRuntime* runtime = resolve_qualified_type(
                    machine, frame, *site.type_name,
                    "method call: " + *site.type_name);
                if (runtime == nullptr) {
                    throw_error(error_identifier_not_found(
                        machine.arena,
                        "method call: " + *site.type_name,
                        "method: " + site.name,
                        {"type '" + *site.type_name + "' not found"}));
                }
                const auto methods = runtime->statics.find(site.name);
                if (methods == runtime->statics.end()
                    || methods->second.empty()) {
                    runtime_fail("static method not found: " + site.name);
                }
                ModuleRuntime* owner = runtime->module;
                if (owner == nullptr || owner->meta == nullptr) {
                    runtime_fail("static method metadata is required");
                }
                FunctionObject* function = select_overload(
                    methods->second, positional, *owner->meta);
                push_value(
                    frame,
                    invoke_function(
                        machine, function, positional, named,
                        "method call: " + *site.type_name + "."
                        + site.name,
                        nullptr,
                        *site.type_name + "." + site.name));
                break;
            }
            case Opcode::CALL_TRAIT: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                std::vector<std::pair<std::string, Value>> named;
                const std::vector<Value> positional =
                    flatten_arguments(site, raw, named);
                (void)named;
                if (positional.empty()) {
                    runtime_fail("trait call requires a receiver");
                }
                const Value receiver = positional[0];
                const std::vector<Value> arguments(
                    positional.begin() + 1, positional.end());
                if (receiver.tag != Tag::Obj) {
                    runtime_fail("trait call requires an object receiver");
                }
                ObjectObject* object = as_object(receiver);
                TypeRuntime* type = object->type;
                if (type == nullptr) {
                    const auto type_it =
                        frame.module->types.find(object->type_name);
                    if (type_it != frame.module->types.end()) {
                        type = &type_it->second;
                    }
                }
                if (type == nullptr) {
                    runtime_fail(
                        "unknown type '" + object->type_name + "'");
                }
                const std::string trait_name =
                    site.trait_name.value_or("");
                const std::vector<FunctionObject*>* candidates = nullptr;
                const auto trait =
                    type->trait_methods.find(trait_name);
                if (trait != type->trait_methods.end()) {
                    const auto found = trait->second.find(site.name);
                    if (found != trait->second.end()) {
                        candidates = &found->second;
                    }
                }
                if (candidates == nullptr && type->module != nullptr) {
                    const auto defaults =
                        type->module->traits.find(trait_name);
                    if (defaults != type->module->traits.end()) {
                        const auto found =
                            defaults->second.defaults.find(site.name);
                        if (found != defaults->second.defaults.end()) {
                            candidates = &found->second;
                        }
                    }
                }
                if (candidates == nullptr) {
                    const auto defaults =
                        frame.module->traits.find(trait_name);
                    if (defaults != frame.module->traits.end()) {
                        const auto found =
                            defaults->second.defaults.find(site.name);
                        if (found != defaults->second.defaults.end()) {
                            candidates = &found->second;
                        }
                    }
                }
                if (candidates == nullptr || candidates->empty()) {
                    runtime_fail("trait method not found: " + site.name);
                }
                const Meta& overload_meta =
                    type->module != nullptr && type->module->meta != nullptr
                    ? *type->module->meta : *meta;
                FunctionObject* function = select_overload(
                    *candidates, arguments, overload_meta);
                push_value(
                    frame,
                    invoke_function(
                        machine, function, arguments, {},
                        "trait call: " + trait_name + "." + site.name,
                        &receiver,
                        runtime_type_name(receiver) + "." + site.name));
                break;
            }
            case Opcode::CALL_OPERATOR: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                std::vector<std::pair<std::string, Value>> named;
                const std::vector<Value> positional =
                    flatten_arguments(site, raw, named);
                (void)named;
                if (positional.empty()) {
                    runtime_fail("operator call requires a receiver");
                }
                const Value receiver = positional[0];
                const std::vector<Value> arguments(
                    positional.begin() + 1, positional.end());
                if (receiver.tag != Tag::Obj) {
                    runtime_fail(
                        "operator methods require an object receiver");
                }
                ObjectObject* object = as_object(receiver);
                TypeRuntime* type = object->type;
                if (type == nullptr) {
                    const auto type_it =
                        frame.module->types.find(object->type_name);
                    if (type_it != frame.module->types.end()) {
                        type = &type_it->second;
                    }
                }
                if (type == nullptr) {
                    runtime_fail(
                        "unknown type '" + object->type_name + "'");
                }
                const std::string trait_name =
                    site.operator_trait.value_or("");
                const std::vector<FunctionObject*>* candidates = nullptr;
                const auto trait =
                    type->trait_methods.find(trait_name);
                if (trait != type->trait_methods.end()) {
                    const auto found = trait->second.find(site.name);
                    if (found != trait->second.end()) {
                        candidates = &found->second;
                    }
                }
                if (candidates == nullptr && type->module != nullptr) {
                    const auto defaults =
                        type->module->traits.find(trait_name);
                    if (defaults != type->module->traits.end()) {
                        const auto found =
                            defaults->second.defaults.find(site.name);
                        if (found != defaults->second.defaults.end()) {
                            candidates = &found->second;
                        }
                    }
                }
                if (candidates == nullptr) {
                    const auto defaults =
                        frame.module->traits.find(trait_name);
                    if (defaults != frame.module->traits.end()) {
                        const auto found =
                            defaults->second.defaults.find(site.name);
                        if (found != defaults->second.defaults.end()) {
                            candidates = &found->second;
                        }
                    }
                }
                if (candidates == nullptr) {
                    const auto methods =
                        type->methods.find(site.name);
                    if (methods != type->methods.end()) {
                        candidates = &methods->second;
                    }
                }
                if (candidates == nullptr || candidates->empty()) {
                    runtime_fail(
                        "operator method not found: " + site.name);
                }
                const Meta& overload_meta =
                    type->module != nullptr && type->module->meta != nullptr
                    ? *type->module->meta : *meta;
                FunctionObject* function = select_overload(
                    *candidates, arguments, overload_meta);
                push_value(
                    frame,
                    invoke_function(
                        machine, function, arguments, {},
                        "operator call: " + site.name, &receiver,
                        runtime_type_name(receiver) + "." + site.name));
                break;
            }
            case Opcode::CONSTRUCT: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                std::vector<Value> positional;
                std::vector<std::pair<Value, Value>> pairs;
                std::vector<std::pair<std::string, Value>> named;
                std::size_t stack_index = 0;
                std::size_t argument_index = 0;
                while (argument_index < site.argument_kinds.size()
                       && stack_index < raw.size()) {
                    const std::string kind =
                        site.argument_kinds[argument_index];
                    if (raw[stack_index].tag == Tag::Spread) {
                        for (const Value& item :
                             as_array(raw[stack_index])->items) {
                            positional.push_back(item);
                        }
                        ++stack_index;
                        ++argument_index;
                        continue;
                    }
                    if (kind == "pair") {
                        if (stack_index + 1 >= raw.size()) {
                            runtime_fail(
                                "instantiation pair is missing its value");
                        }
                        pairs.emplace_back(
                            raw[stack_index], raw[stack_index + 1]);
                        stack_index += 2;
                        ++argument_index;
                        continue;
                    }
                    if (kind == "named") {
                        const std::string name =
                            argument_index
                                < site.argument_names.size()
                            ? site.argument_names[argument_index]
                            : std::string();
                        named.emplace_back(name, raw[stack_index]);
                        ++stack_index;
                        ++argument_index;
                        continue;
                    }
                    positional.push_back(raw[stack_index]);
                    ++stack_index;
                    ++argument_index;
                }
                while (stack_index < raw.size()) {
                    positional.push_back(raw[stack_index]);
                    ++stack_index;
                }
                const bool builtin_construction =
                    site.name == "arr" || site.name == "tup"
                    || site.name == "set" || site.name == "map"
                    || site.name == "str" || site.name == "int"
                    || site.name == "num" || site.name == "bool"
                    || site.name == "char";
                if (!named.empty() && builtin_construction) {
                    throw_error(error_argument(
                        machine.arena, "instantiation",
                        "Named arguments are only supported for user "
                        "type constructors"));
                }
                if (site.name == "arr") {
                    push_value(
                        frame,
                        make_array(machine.arena.allocate_array(
                            std::move(positional))));
                    break;
                }
                if (site.name == "tup") {
                    push_value(
                        frame,
                        make_tuple(machine.arena.allocate_tuple(
                            std::move(positional))));
                    break;
                }
                if (site.name == "set") {
                    SetObject* set = machine.arena.allocate_set();
                    for (const Value& item : positional) {
                        set_add(*set, item);
                    }
                    push_value(frame, make_set(set));
                    break;
                }
                if (site.name == "map") {
                    if (!positional.empty()) {
                        runtime_fail(
                            "map construction requires key >> value entries");
                    }
                    MapObject* map = machine.arena.allocate_map();
                    for (const auto& pair : pairs) {
                        map_set(*map, pair.first, pair.second);
                    }
                    push_value(frame, make_map(map));
                    break;
                }
                if (site.name == "str" || site.name == "int"
                    || site.name == "num" || site.name == "bool"
                    || site.name == "char") {
                    if (positional.size() != 1) {
                        runtime_fail(
                            "primitive construction requires one value");
                    }
                    push_value(
                        frame,
                        cast_value(
                            machine, frame, positional[0], site.name));
                    break;
                }
                TypeRuntime* type_runtime = resolve_qualified_type(
                    machine, frame, site.name, "instantiation");
                if (type_runtime != nullptr && type_runtime->info != nullptr
                    && type_runtime->info->kind == "object") {
                    TypeRuntime& type = *type_runtime;
                    const std::string type_name =
                        type.info->name.empty()
                        ? site.name : type.info->name;
                    ObjectObject* object =
                        machine.arena.allocate_object(
                            type_name, false, "");
                    object->type = &type;
                    object->module = type.module;
                    initialize_object_fields(machine, object, type);
                    const Value object_value = make_object(object);
                    const auto constructors =
                        type.constructors.find("constructor");
                    if (constructors == type.constructors.end()
                        || constructors->second.empty()) {
                        if (positional.size()
                            > type.info->properties.size()) {
                            runtime_fail(
                                "too many arguments for the default "
                                "constructor");
                        }
                        for (std::size_t index = 0;
                             index < positional.size(); ++index) {
                            object->fields[
                                type.info->properties[index].name] =
                                copy_value(
                                    machine.arena, positional[index]);
                        }
                        for (const auto& [name, value] : named) {
                            bool found = false;
                            for (const TypeProperty& property :
                                 type.info->properties) {
                                if (property.name == name) {
                                    object->fields[name] =
                                        copy_value(
                                            machine.arena, value);
                                    found = true;
                                    break;
                                }
                            }
                            if (!found) {
                                throw_error(error_identifier_not_found(
                                    machine.arena, "instantiation",
                                    name));
                            }
                        }
                        push_value(frame, object_value);
                        break;
                    }
                    ModuleRuntime* owner = type.module;
                    if (owner == nullptr || owner->meta == nullptr) {
                        runtime_fail("constructor metadata is required");
                    }
                    FunctionObject* function = select_overload(
                        constructors->second, positional, *owner->meta);
                    const Value result = call_function(
                        machine, function, positional, named,
                        "instantiation", &object_value,
                        type_name + ".constructor");
                    push_value(
                        frame,
                        result.tag == Tag::Nova ? object_value : result);
                    break;
                }
                throw_error(error_identifier_not_found(
                    machine.arena, "instantiation", site.name,
                    {"user type doesn't exists"}));
            }
            case Opcode::MAKE_ERROR: {
                const std::int64_t spec_index =
                    operand_integer(instruction, "spec");
                if (meta == nullptr) {
                    throw RuntimeError("error metadata is required");
                }
                const std::uint32_t code_index = code_index_of(image, code);
                const MetaDescriptor* descriptor = find_descriptor(
                    *meta, code_index, static_cast<std::uint32_t>(spec_index));
                if (descriptor == nullptr
                    || descriptor->kind != MetaDescriptor::Kind::ErrorSpec) {
                    throw RuntimeError("missing native error descriptor");
                }
                const std::vector<Value> arguments = collect_arguments(
                    frame, descriptor->argument_count);
                const std::size_t required =
                    descriptor->has_kind ? 2u : 1u;
                if (arguments.size() < required) {
                    throw_error(error_argument(
                        machine.arena, descriptor->where,
                        "not enought arguments"));
                }
                auto text_argument = [&](const Value& value,
                                         const std::string& where) {
                    if (value.tag != Tag::Str) {
                        throw_error(error_type_match(
                            machine.arena, where, "str",
                            runtime_type_name(value)));
                    }
                    return as_string_const(value)->utf8;
                };
                std::string kind = "USER";
                std::string message;
                std::size_t detail_start = 1;
                if (descriptor->has_kind) {
                    kind = text_argument(
                        arguments[0], "builtin: fail, kind");
                    message = text_argument(
                        arguments[1], "builtin: fail, message");
                    detail_start = 2;
                } else {
                    message = text_argument(
                        arguments[0], "builtin: error, message");
                }
                std::vector<std::string> details;
                for (std::size_t index = detail_start;
                     index < arguments.size(); ++index) {
                    details.push_back(text_argument(
                        arguments[index],
                        descriptor->has_kind
                            ? "builtin: fail, argument"
                            : "builtin: error, argument"));
                }
                ErrorObject* created = make_error(
                    machine.arena, kind, descriptor->where,
                    message, std::move(details));
                if (descriptor->mode == "value") {
                    push_value(frame, make_error_value(created));
                    break;
                }
                throw_error(created);
            }
            case Opcode::ERROR_PROPERTY: {
                const std::int64_t property =
                    operand_integer(instruction, "property");
                const Value value = pop_value(frame);
                if (!is_error(value)) {
                    throw_error(error_type_match(
                        machine.arena, "error property", "error",
                        runtime_type_name(value)));
                }
                static const char* kErrorProperties[] = {
                    "kind", "message", "details", "where",
                    "line", "column", "cause", "frames",
                };
                const char* name = "kind";
                if (property >= 0
                    && static_cast<std::size_t>(property)
                        < sizeof(kErrorProperties)
                            / sizeof(kErrorProperties[0])) {
                    name = kErrorProperties[
                        static_cast<std::size_t>(property)];
                }
                push_value(
                    frame,
                    error_property_value(
                        machine, as_error(value), name));
                break;
            }
            case Opcode::THROW:
            case Opcode::RETHROW: {
                const Value value = pop_value(frame);
                if (!is_error(value)) {
                    throw_error(error_type_match(
                        machine.arena, "throw", "error",
                        runtime_type_name(value)));
                }
                throw_error(as_error(value));
            }
            case Opcode::PROPAGATE: {
                const Value value = pop_value(frame);
                if (!is_error(value)) {
                    push_value(frame, value);
                    break;
                }
                if (!frame.is_function) {
                    throw_error(make_error(
                        machine.arena, "LOGIC", "postfix unwrap",
                        "Trying to use the '?' operator outside a "
                        "function scope",
                        {"the scope you are trying to unwrap from it's "
                         "global"}));
                }
                bool handled = false;
                for (auto it = frame.handlers.rbegin();
                     it != frame.handlers.rend(); ++it) {
                    if (it->state == 2) {
                        continue;
                    }
                    if (!(it->start_ip
                              <= static_cast<std::int32_t>(
                                  instruction.offset)
                          && static_cast<std::int32_t>(instruction.offset)
                              < it->end_ip)) {
                        continue;
                    }
                    if (it->finally_ip >= 0) {
                        it->state = 2;
                        frame.pending_return =
                            copy_value(machine.arena, value);
                        frame.has_pending_return = true;
                        frame.pending_error = nullptr;
                        frame.transfer = Transfer{
                            TransferKind::Return, -1};
                        frame.ip = static_cast<std::uint32_t>(
                            it->finally_ip);
                        handled = true;
                        break;
                    }
                }
                if (!handled) {
                    return copy_value(machine.arena, value);
                }
                break;
            }
            case Opcode::TRY_BEGIN: {
                const std::int32_t next_ip =
                    static_cast<std::int32_t>(frame.ip);
                const ExceptionEntry* entry = nullptr;
                for (const ExceptionEntry& candidate :
                     code.exception_table) {
                    if (candidate.start_ip == next_ip) {
                        entry = &candidate;
                        break;
                    }
                }
                if (entry == nullptr) {
                    throw RuntimeError(
                        "TRY_BEGIN at "
                        + std::to_string(instruction.offset)
                        + " has no exception entry");
                }
                HandlerEntry handler;
                handler.start_ip = entry->start_ip;
                handler.end_ip = entry->end_ip;
                handler.catch_ip = entry->catch_ip;
                handler.finally_ip = entry->finally_ip;
                handler.resume_ip = entry->resume_ip;
                handler.stack_depth = static_cast<std::uint32_t>(
                    frame.stack.size());
                handler.local_watermark = entry->local_watermark;
                handler.kind = entry->kind;
                handler.state = 0;
                frame.handlers.push_back(std::move(handler));
                break;
            }
            case Opcode::TRY_END:
                if (!frame.handlers.empty()) {
                    frame.handlers.pop_back();
                }
                break;
            case Opcode::FINALLY_END: {
                HandlerEntry handler;
                bool has_handler = false;
                if (!frame.handlers.empty()) {
                    handler = frame.handlers.back();
                    frame.handlers.pop_back();
                    has_handler = true;
                }
                if (frame.pending_error != nullptr) {
                    ErrorObject* error = frame.pending_error;
                    frame.pending_error = nullptr;
                    throw_error(error);
                }
                if (has_handler && handler.resume_ip >= 0) {
                    frame.ip = static_cast<std::uint32_t>(
                        handler.resume_ip);
                }
                break;
            }
            case Opcode::SET_RETURN:
                frame.pending_return = copy_value(
                    machine.arena, pop_value(frame));
                frame.has_pending_return = true;
                frame.pending_error = nullptr;
                frame.transfer = Transfer{TransferKind::Return, -1};
                break;
            case Opcode::SET_TRANSFER: {
                const std::int64_t kind =
                    operand_integer(instruction, "kind");
                if (kind == 0) {
                    frame.transfer = Transfer{
                        TransferKind::Jump,
                        operand_target(instruction, code)};
                } else {
                    frame.transfer =
                        Transfer{TransferKind::Return, -1};
                }
                frame.pending_error = nullptr;
                frame.pending_return = make_nova();
                frame.has_pending_return = false;
                break;
            }
            case Opcode::JUMP_IF_TRANSFER:
                if (frame.transfer.kind != TransferKind::None
                    || frame.has_pending_return) {
                    frame.ip = operand_target(instruction, code);
                }
                break;
            case Opcode::APPLY_TRANSFER: {
                if (frame.transfer.kind == TransferKind::None
                    && !frame.has_pending_return) {
                    break;
                }
                const Transfer transfer = frame.transfer;
                frame.transfer = Transfer{};
                if (transfer.kind == TransferKind::Jump) {
                    frame.ip = static_cast<std::uint32_t>(
                        transfer.target);
                    break;
                }
                Value value = frame.has_pending_return
                    ? frame.pending_return : make_nova();
                frame.pending_return = make_nova();
                frame.has_pending_return = false;
                if (frame.is_function) {
                    return copy_value(machine.arena, value);
                }
                return value;
            }
            case Opcode::ABANDON_FINALLY:
                if (!frame.handlers.empty()
                    && frame.handlers.back().state == 2) {
                    frame.handlers.pop_back();
                }
                frame.pending_error = nullptr;
                frame.pending_return = make_nova();
                frame.has_pending_return = false;
                frame.transfer = Transfer{};
                break;
            case Opcode::DESTRUCTURE: {
                const std::int64_t descriptor_index =
                    operand_integer(instruction, "descriptor");
                if (descriptor_index < 0
                    || static_cast<std::uint64_t>(descriptor_index)
                        >= code.constants.size()) {
                    runtime_fail("destructure descriptor out of range");
                }
                const std::uint32_t source_slot =
                    operand_slot(instruction, code, "source_slot");
                const Value source = unwrap_reference(
                    machine, frame.locals[source_slot]);
                push_value(
                    frame,
                    destructure_value(
                        machine, frame,
                        code.constants[static_cast<std::size_t>(
                            descriptor_index)].text,
                        source));
                break;
            }
            case Opcode::MATCH: {
                const std::int64_t pattern_index =
                    operand_integer(instruction, "pattern");
                if (pattern_index < 0
                    || static_cast<std::uint64_t>(pattern_index)
                        >= image.patterns.size()) {
                    runtime_fail("match pattern index out of range");
                }
                const Value subject = pop_value(frame);
                if (!match_pattern(
                        machine, frame,
                        image.patterns[
                            static_cast<std::size_t>(pattern_index)],
                        subject)) {
                    frame.ip = operand_target(instruction, code);
                }
                break;
            }
            case Opcode::AWAIT: {
                const Value value = pop_value(frame);
                if (!is_task(value)) {
                    throw_error(error_type_match(
                        machine.arena, "await", "task",
                        runtime_type_name(value)));
                }
                TaskObject* task = as_task(value);
                push_value(
                    frame,
                    await_task(
                        machine, task,
                        task->kind == TaskObject::Kind::Lazy
                            ? "await" : "wait"));
                break;
            }
            case Opcode::SPAWN: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                std::optional<Value> target;
                if (!site.method_ast.empty()
                    && site.method_ast != "null"
                    && site.dispatch != "spawn_static") {
                    target = pop_value(frame);
                }
                std::vector<std::pair<std::string, Value>> named;
                const std::vector<Value> positional =
                    flatten_arguments(site, raw, named);
                FunctionObject* function = nullptr;
                Value receiver;
                bool has_receiver = false;
                std::string where;
                std::string frame_name;
                if (!resolve_pending_call(
                        machine, frame, site, positional,
                        target.has_value() ? &*target : nullptr,
                        function, receiver, has_receiver, where,
                        frame_name)) {
                    throw_error(error_identifier_not_found(
                        machine.arena, "spawn: " + site.name,
                        site.name));
                }
                TaskObject* task = create_task(
                    machine, function, positional, named,
                    has_receiver ? &receiver : nullptr, where,
                    frame_name, TaskObject::Kind::Worker);
                run_task(machine, task);
                push_value(frame, make_task(task));
                break;
            }
            case Opcode::CALL_ASYNC:
            case Opcode::CALL_ASYNC_METHOD: {
                const std::int64_t call_index =
                    operand_integer(instruction, "call");
                if (call_index < 0
                    || static_cast<std::uint64_t>(call_index)
                        >= image.call_sites.size()) {
                    runtime_fail(
                        "call index out of range: "
                        + std::to_string(call_index));
                }
                const CallSite& site =
                    image.call_sites[static_cast<std::size_t>(call_index)];
                const std::vector<Value> raw =
                    collect_arguments(frame, site.positional_count);
                std::optional<Value> target;
                if (site.dispatch == "method"
                    || site.dispatch == "module"
                    || site.dispatch == "value") {
                    target = pop_value(frame);
                }
                std::vector<std::pair<std::string, Value>> named;
                const std::vector<Value> positional =
                    flatten_arguments(site, raw, named);
                FunctionObject* function = nullptr;
                Value receiver;
                bool has_receiver = false;
                std::string where;
                std::string frame_name;
                if (!resolve_pending_call(
                        machine, frame, site, positional,
                        target.has_value() ? &*target : nullptr,
                        function, receiver, has_receiver, where,
                        frame_name)) {
                    throw_error(error_identifier_not_found(
                        machine.arena, "call: " + site.name,
                        site.name));
                }
                TaskObject* task = create_task(
                    machine, function, positional, named,
                    has_receiver ? &receiver : nullptr, where,
                    frame_name, TaskObject::Kind::Lazy);
                push_value(frame, make_task(task));
                break;
            }
            case Opcode::RETURN: {
                const Value value = pop_value(frame);
                if (frame.is_function) {
                    return copy_value(machine.arena, value);
                }
                return value;
            }
            case Opcode::CHECK_CANCEL:
                if (machine.current_task != nullptr
                    && machine.current_task->cancel_requested) {
                    throw_error(make_error(
                        machine.arena, "TASK", "", "canceled",
                        {"task "
                             + std::to_string(
                                 machine.current_task->id)
                             + " cancellation was requested"}));
                }
                break;
            default:
                runtime_fail(
                    std::string("native N0 does not implement opcode ")
                    + instruction.spec->name);
        }
        } catch (const UnwindSignal& signal) {
            if (handle_error(
                    frame, signal.error,
                    static_cast<std::int32_t>(instruction.offset))) {
                continue;
            }
            throw;
        }
    }
    runtime_fail(
        "execution fell off the end of " + frame_label(frame)
        + " without a return");
}

std::vector<Value> collect_arguments(Frame& frame, std::size_t count) {
    if (frame.stack.size() < count) {
        runtime_fail("stack underflow in CALL");
    }
    std::vector<Value> raw(count);
    for (std::size_t index = 0; index < count; ++index) {
        raw[count - 1 - index] = pop_value(frame);
    }
    return raw;
}

std::vector<Value> flatten_arguments(
    const CallSite& site,
    std::vector<Value> raw,
    std::vector<std::pair<std::string, Value>>& named) {
    std::vector<Value> positional;
    for (std::size_t index = 0; index < raw.size(); ++index) {
        const std::string kind = index < site.argument_kinds.size()
            ? site.argument_kinds[index]
            : "positional";
        const std::string name = index < site.argument_names.size()
            ? site.argument_names[index]
            : "";
        const Value& value = raw[index];
        if (value.tag == Tag::Spread) {
            for (const Value& item : as_array(value)->items) {
                positional.push_back(item);
            }
            continue;
        }
        if (kind == "named") {
            named.emplace_back(name, value);
            continue;
        }
        positional.push_back(value);
    }
    return positional;
}

std::string runtime_type_name(const Value& value) {
    switch (value.tag) {
        case Tag::Nova: return "nova";
        case Tag::Undef: return "undef";
        case Tag::Bool: return "bool";
        case Tag::Int: return "int";
        case Tag::BigInt: return "int";
        case Tag::Num: return "num";
        case Tag::Char: return "char";
        case Tag::Str: return "str";
        case Tag::Fun: return "function";
        case Tag::Arr: return "arr";
        case Tag::Spread: return "spread";
        case Tag::Iter: return "iter";
        case Tag::Tup: return "tup";
        case Tag::Map: return "map";
        case Tag::Set: return "set";
        case Tag::Obj: {
            const ObjectObject* object = as_object(value);
            if (object != nullptr) {
                if (object->type != nullptr && object->type->info != nullptr) {
                    return object->type->info->name;
                }
                if (!object->type_name.empty()) {
                    return object->type_name;
                }
            }
            return "obj";
        }
        case Tag::Type: return "type";
        case Tag::Module: return "module";
        case Tag::Error: return "error";
        case Tag::Ref: return "reference";
        case Tag::Project: return "Project";
        case Tag::Task: return "task";
        case Tag::File: return "file";
    }
    return "unknown";
}

bool assignable_type(
    const MetaTypeSpec& spec, const Value& value, const Meta& meta) {
    if (spec.kind == MetaTypeKind::Union) {
        for (const std::uint32_t index : spec.args) {
            if (index < meta.types.size()
                && assignable_type(meta.types[index], value, meta)) {
                return true;
            }
        }
        return false;
    }
    const std::string& name = spec.name;
    if (name == "any" || name == "mixed") {
        return true;
    }
    const std::string type = runtime_type_name(value);
    if (name == type) {
        return true;
    }
    if (name == "num" && type == "int") {
        return true;
    }
    if (name == "int" && type == "bool") {
        return true;
    }
    return false;
}

int score_type(
    const MetaTypeSpec& spec, const Value& value, const Meta& meta) {
    if (spec.kind == MetaTypeKind::Union) {
        int best = 1;
        for (const std::uint32_t index : spec.args) {
            if (index < meta.types.size()) {
                best = std::max(
                    best, score_type(meta.types[index], value, meta));
            }
        }
        return best;
    }
    const std::string& name = spec.name;
    if (name == "any" || name == "mixed") {
        return 1;
    }
    const std::string type = runtime_type_name(value);
    if (name == type) {
        return 3;
    }
    if (assignable_type(spec, value, meta)) {
        return 2;
    }
    if (name == "num" && type == "int") {
        return 1;
    }
    if (name == "int" && type == "num") {
        return 1;
    }
    return -1;
}

FunctionObject* select_overload(
    const std::vector<FunctionObject*>& functions,
    const std::vector<Value>& arguments,
    const Meta& meta) {
    int best = std::numeric_limits<int>::min();
    std::vector<FunctionObject*> best_functions;
    for (FunctionObject* function : functions) {
        if (function == nullptr || function->metadata == nullptr) {
            continue;
        }
        const FunctionMetadata& spec = *function->metadata;
        int score = 0;
        if (arguments.size() == spec.parameters.size()) {
            score += 3;
        } else if (arguments.size() == spec.min_argc) {
            score += 2;
        }
        for (std::size_t index = 0;
             index < arguments.size() && index < spec.parameters.size();
             ++index) {
            const MetaParameter& parameter = spec.parameters[index];
            if (parameter.type_index >= meta.types.size()) {
                runtime_fail("parameter type index out of range");
            }
            score += score_type(
                meta.types[parameter.type_index], arguments[index], meta);
            if (!meta_flag(parameter, MetaParameterFlag::Weak)) {
                score += 1;
            }
        }
        if (best == std::numeric_limits<int>::min() || score > best) {
            best = score;
            best_functions.assign(1, function);
        } else if (score == best) {
            best_functions.push_back(function);
        }
    }
    if (best_functions.size() != 1) {
        runtime_fail(
            "Ambiguous call, multiple overloads match equally well");
    }
    return best_functions.front();
}

bool try_resolve_name(
    Machine& machine, Frame& frame, const std::string& name, Value& out) {
    const auto local = frame.local_slots.find(name);
    if (local != frame.local_slots.end()) {
        out = frame.locals[local->second];
        return true;
    }
    if (frame.function != nullptr) {
        const auto reference =
            frame.function->captured.references.find(name);
        if (reference != frame.function->captured.references.end()) {
            out = *reference->second;
            return true;
        }
        const auto value = frame.function->captured.values.find(name);
        if (value != frame.function->captured.values.end()) {
            out = value->second;
            return true;
        }
        const auto functions = frame.function->captured.functions.find(name);
        if (functions != frame.function->captured.functions.end()
            && !functions->second.empty()) {
            out = make_function(functions->second.back());
            return true;
        }
    }
    const auto global = frame.module->globals.find(name);
    if (global != frame.module->globals.end()) {
        out = global->second;
        return true;
    }
    const auto functions = frame.module->functions.find(name);
    if (functions != frame.module->functions.end()
        && !functions->second.empty()) {
        out = make_function(functions->second.back());
        return true;
    }
    const auto wildcard_value = frame.module->wildcard_values.find(name);
    if (wildcard_value != frame.module->wildcard_values.end()) {
        out = wildcard_value->second;
        return true;
    }
    const auto wildcard_functions =
        frame.module->wildcard_functions.find(name);
    if (wildcard_functions != frame.module->wildcard_functions.end()
        && !wildcard_functions->second.empty()) {
        out = make_function(wildcard_functions->second.back());
        return true;
    }
    const auto wildcard_type = frame.module->wildcard_types.find(name);
    if (wildcard_type != frame.module->wildcard_types.end()) {
        out = make_type(wildcard_type->second);
        return true;
    }
    const auto alias = frame.module->aliases.find(name);
    if (alias != frame.module->aliases.end()) {
        out = make_module(alias->second);
        return true;
    }
    return false;
}

bool try_resolve_free(
    Machine& machine, Frame& frame, const std::string& name, Value& out) {
    if (frame.function != nullptr) {
        const auto reference =
            frame.function->captured.references.find(name);
        if (reference != frame.function->captured.references.end()) {
            out = *reference->second;
            return true;
        }
        const auto value = frame.function->captured.values.find(name);
        if (value != frame.function->captured.values.end()) {
            out = value->second;
            return true;
        }
        const auto functions = frame.function->captured.functions.find(name);
        if (functions != frame.function->captured.functions.end()
            && !functions->second.empty()) {
            out = make_function(functions->second.back());
            return true;
        }
    }
    const auto global = frame.module->globals.find(name);
    if (global != frame.module->globals.end()) {
        out = global->second;
        return true;
    }
    const auto functions = frame.module->functions.find(name);
    if (functions != frame.module->functions.end()
        && !functions->second.empty()) {
        out = make_function(functions->second.back());
        return true;
    }
    const auto wildcard_value = frame.module->wildcard_values.find(name);
    if (wildcard_value != frame.module->wildcard_values.end()) {
        out = wildcard_value->second;
        return true;
    }
    const auto wildcard_functions =
        frame.module->wildcard_functions.find(name);
    if (wildcard_functions != frame.module->wildcard_functions.end()
        && !wildcard_functions->second.empty()) {
        out = make_function(wildcard_functions->second.back());
        return true;
    }
    const auto wildcard_type = frame.module->wildcard_types.find(name);
    if (wildcard_type != frame.module->wildcard_types.end()) {
        out = make_type(wildcard_type->second);
        return true;
    }
    const auto alias = frame.module->aliases.find(name);
    if (alias != frame.module->aliases.end()) {
        out = make_module(alias->second);
        return true;
    }
    return false;
}

Value resolve_name(
    Machine& machine, Frame& frame, const std::string& name) {
    Value value;
    if (try_resolve_name(machine, frame, name, value)) {
        return unwrap_reference(machine, value);
    }
    throw_error(error_identifier_not_found(
        machine.arena, "", name));
}

void assign_name(
    Machine& machine,
    Frame& frame,
    const std::string& name,
    const Value& value) {
    const auto local = frame.local_slots.find(name);
    if (local != frame.local_slots.end()) {
        if (is_reference(frame.locals[local->second])) {
            reference_set(
                machine, as_reference(frame.locals[local->second]),
                value);
            return;
        }
        frame.locals[local->second] = value;
        publish_module_local(
            frame, static_cast<std::uint32_t>(local->second), value);
        return;
    }
    if (frame.function != nullptr) {
        const auto reference =
            frame.function->captured.references.find(name);
        if (reference != frame.function->captured.references.end()) {
            *reference->second = value;
            return;
        }
        const auto captured = frame.function->captured.values.find(name);
        if (captured != frame.function->captured.values.end()) {
            captured->second = value;
            return;
        }
    }
    const auto global = frame.module->globals.find(name);
    if (global != frame.module->globals.end()) {
        global->second = value;
        sync_module_global(machine, *frame.module, name, value);
        return;
    }
    runtime_fail("identifier '" + name + "' not found");
}

void capture_scope(
    Machine& machine,
    FunctionObject& function,
    Frame& caller,
    bool by_reference) {
    (void)machine;
    if (caller.code != nullptr) {
        for (std::size_t slot = 0; slot < caller.code->local_names.size();
             ++slot) {
            const std::string& name = caller.code->local_names[slot];
            if (name.empty() || name.front() == '#') {
                continue;
            }
            if (by_reference) {
                function.captured.references[name] = &caller.locals[slot];
            } else {
                function.captured.values[name] = caller.locals[slot];
            }
        }
    }
    if (caller.function != nullptr) {
        for (const auto& [name, value] :
             caller.function->captured.values) {
            function.captured.values.emplace(name, value);
        }
        for (const auto& [name, pointer] :
             caller.function->captured.references) {
            function.captured.references.emplace(name, pointer);
        }
        for (const auto& [name, functions] :
             caller.function->captured.functions) {
            function.captured.functions[name] = functions;
        }
    }
}

void set_parameter(
    Machine& machine,
    Frame& frame,
    const std::string& name,
    const Value& value,
    bool reference = false) {
    const auto slot = frame.local_slots.find(name);
    if (slot == frame.local_slots.end()) {
        runtime_fail("parameter slot not found: " + name);
    }
    frame.locals[slot->second] = reference
        ? value
        : copy_value(machine.arena, value);
}

void check_reference_parameter(
    Machine& machine,
    FunctionObject* function,
    const MetaParameter& parameter,
    const Value& value) {
    std::string expected = "any";
    if (function->module != nullptr
        && function->module->meta != nullptr) {
        const Meta& meta = *function->module->meta;
        if (parameter.type_index < meta.types.size()) {
            expected = meta.types[parameter.type_index].name;
            if (expected.empty()) {
                expected = "any";
            }
        }
    }
    if (!is_reference(value)) {
        throw_error(error_reference(
            machine.arena, "function call",
            "Expected a reference argument",
            {
                "parameter '" + parameter.name
                    + "' is declared as &" + expected,
                "pass it as &variable",
                "but " + runtime_type_name(value) + " was encountered",
            }));
    }
    RefObject* reference = as_reference(value);
    if (expected != "any"
        && reference->target_type != expected) {
        throw_error(error_reference(
            machine.arena, "function call",
            "Reference type does not match",
            {
                "expected &" + expected,
                "but &" + reference->target_type
                    + " was encountered",
            }));
    }
}

Value run_default(
    Machine& machine,
    ModuleRuntime& module,
    int code_index,
    const std::string& where) {
    (void)where;
    if (module.image == nullptr) {
        runtime_fail("function metadata is required");
    }
    if (code_index < 0
        || static_cast<std::size_t>(code_index)
            >= module.image->codes.size()) {
        runtime_fail("default code index out of range");
    }
    const CodeObject& code =
        module.image->codes[static_cast<std::size_t>(code_index)];
    if (machine.frame_depth >= machine.max_frames) {
        runtime_fail("maximum frame depth exceeded");
    }
    Frame frame = make_frame(code, module, nullptr, false, false);
    ++machine.frame_depth;
    try {
        const Value value = execute(frame, machine);
        --machine.frame_depth;
        close_frame(frame);
        return value;
    } catch (...) {
        --machine.frame_depth;
        close_frame(frame);
        throw;
    }
}

void bind_function(
    Machine& machine,
    Frame& frame,
    FunctionObject* function,
    std::vector<Value>& positional,
    std::vector<std::pair<std::string, Value>>& named,
    const std::string& where) {
    const FunctionMetadata& spec = *function->metadata;
    const bool variadic =
        meta_flag(spec, MetaFunctionFlag::Variadic);
    const std::size_t fixed = variadic && spec.variadic_index >= 0
        ? static_cast<std::size_t>(spec.variadic_index)
        : spec.parameters.size();
    std::vector<std::optional<Value>> resolved(fixed);
    std::vector<Value> extra;
    for (std::size_t index = 0; index < positional.size(); ++index) {
        if (index < fixed) {
            resolved[index] = positional[index];
        } else if (variadic) {
            extra.push_back(positional[index]);
        } else {
            runtime_fail("too many arguments");
        }
    }
    for (const auto& [name, value] : named) {
        bool found = false;
        for (std::size_t index = 0; index < fixed; ++index) {
            if (spec.parameters[index].name == name) {
                if (resolved[index].has_value()) {
                    runtime_fail(
                        "received '" + name + "' more than once");
                }
                resolved[index] = value;
                found = true;
                break;
            }
        }
        if (!found) {
            runtime_fail("has no parameter named '" + name + "'");
        }
    }
    for (std::size_t index = 0; index < fixed; ++index) {
        const bool reference =
            meta_flag(spec.parameters[index], MetaParameterFlag::Reference);
        if (resolved[index].has_value()) {
            if (reference) {
                check_reference_parameter(
                    machine, function, spec.parameters[index],
                    *resolved[index]);
            }
            set_parameter(
                machine, frame, spec.parameters[index].name,
                *resolved[index], reference);
            continue;
        }
        if (index < spec.min_argc) {
            runtime_fail(
                "Missing required argument '"
                + spec.parameters[index].name + "'");
        }
        if (spec.parameters[index].default_index >= 0) {
            const Value default_value = run_default(
                machine, *function->module,
                spec.parameters[index].default_index, where);
            if (reference) {
                check_reference_parameter(
                    machine, function, spec.parameters[index],
                    default_value);
            }
            set_parameter(
                machine, frame, spec.parameters[index].name,
                default_value, reference);
            continue;
        }
        runtime_fail(
            "Missing required argument '"
            + spec.parameters[index].name + "'");
    }
    if (variadic && spec.variadic_index >= 0) {
        ArrayObject* array =
            machine.arena.allocate_array(std::move(extra));
        set_parameter(
            machine,
            frame,
            spec.parameters[static_cast<std::size_t>(spec.variadic_index)]
                .name,
            make_array(array));
    }
}

Value call_function(
    Machine& machine,
    FunctionObject* function,
    std::vector<Value> positional,
    std::vector<std::pair<std::string, Value>> named,
    const std::string& where,
    const Value* receiver,
    const std::string& frame_name) {
    if (function == nullptr || function->metadata == nullptr
        || function->module == nullptr
        || function->module->image == nullptr
        || function->module->meta == nullptr) {
        runtime_fail("function metadata is required");
    }
    if (function->extern_descriptor != nullptr) {
        return call_extern_descriptor(
            machine, *function->extern_descriptor,
            function->metadata->name, positional, named);
    }
    ModuleRuntime& module = *function->module;
    const FunctionMetadata& spec = *function->metadata;
    if (spec.code_index >= module.image->codes.size()) {
        runtime_fail("function code index out of range");
    }
    const CodeObject& code =
        module.image->codes[spec.code_index];
    if (machine.frame_depth >= machine.max_frames) {
        throw_error(error_recursion(
            machine.arena, "", "Maximum evaluation depth exceeded",
            {
                "depth limit: 900",
                "check for unbounded or deeply nested recursion",
            }));
    }
    Frame frame = make_frame(code, module, function, false, true);
    if (receiver == nullptr && function->has_receiver) {
        receiver = &function->receiver;
    }
    if (receiver != nullptr) {
        frame.receiver = *receiver;
        frame.has_receiver = true;
    }
    bind_function(
        machine, frame, function, positional, named, where);
    FrameRecord record;
    record.name = !frame_name.empty()
        ? frame_name
        : (function->metadata != nullptr
               && !function->metadata->name.empty()
           ? function->metadata->name : where);
    record.file = machine.entry_path;
    if (machine.current_frame != nullptr
        && machine.current_frame->code != nullptr) {
        const Frame& caller = *machine.current_frame;
        if (caller.span_index < caller.code->spans.size()) {
            const SourceSpan& span = caller.code->spans[caller.span_index];
            record.line = static_cast<std::int32_t>(span.start_line);
            record.column = static_cast<std::int32_t>(
                span.start_column);
        }
    }
    machine.call_frames.push_back(std::move(record));
    ++machine.frame_depth;
    try {
        const Value value = execute(frame, machine);
        --machine.frame_depth;
        machine.call_frames.pop_back();
        close_frame(frame);
        return value;
    } catch (const UnwindSignal& signal) {
        --machine.frame_depth;
        attach_frames(machine, signal.error);
        machine.call_frames.pop_back();
        close_frame(frame);
        throw;
    } catch (...) {
        --machine.frame_depth;
        machine.call_frames.pop_back();
        close_frame(frame);
        throw;
    }
}

bool function_is_async(const FunctionObject* function) {
    return function != nullptr && function->metadata != nullptr
        && meta_flag(*function->metadata, MetaFunctionFlag::Async);
}

std::shared_ptr<ModuleRuntime> clone_module_for_task(
    Machine& machine,
    ModuleRuntime& source,
    FunctionObject* target,
    FunctionObject*& cloned_target) {
    auto clone = std::make_shared<ModuleRuntime>();
    *clone = source;
    clone->init = ModuleRuntime::Init::Ready;
    clone->globals.clear();
    for (const auto& [name, value] : source.globals) {
        clone->globals[name] = copy_value(machine.arena, value);
    }
    clone->functions.clear();
    for (const auto& [name, overloads] : source.functions) {
        auto& copied = clone->functions[name];
        copied.reserve(overloads.size());
        for (FunctionObject* original : overloads) {
            FunctionObject* function =
                machine.arena.allocate_function(original->metadata);
            *function = *original;
            function->module = clone.get();
            copied.push_back(function);
            if (original == target) {
                cloned_target = function;
            }
        }
    }
    for (auto& [name, type] : clone->types) {
        (void)name;
        type.module = clone.get();
    }
    for (auto& [name, trait] : clone->traits) {
        (void)name;
        trait.module = clone.get();
    }
    clone->wildcard_values.clear();
    for (const auto& [name, value] : source.wildcard_values) {
        clone->wildcard_values[name] =
            copy_value(machine.arena, value);
    }
    if (cloned_target == nullptr && target != nullptr) {
        FunctionObject* function =
            machine.arena.allocate_function(target->metadata);
        *function = *target;
        function->module = clone.get();
        cloned_target = function;
    }
    return clone;
}

TaskObject* create_task(
    Machine& machine,
    FunctionObject* function,
    std::vector<Value> positional,
    std::vector<std::pair<std::string, Value>> named,
    const Value* receiver,
    const std::string& where,
    const std::string& frame_name,
    TaskObject::Kind kind) {
    if (function == nullptr) {
        throw RuntimeError("task has no callable");
    }
    if (kind == TaskObject::Kind::Lazy) {
        if (machine.lazy_pending >= 64) {
            throw_error(make_error(
                machine.arena, "TASK", "await",
                "too many pending async tasks",
                {
                    "pending async tasks: "
                        + std::to_string(machine.lazy_pending),
                    "limit: 64",
                    "await or cancel pending async tasks before creating more",
                }));
        }
        ++machine.lazy_pending;
    }
    TaskObject* task = machine.arena.allocate_task();
    task->id = ++machine.next_task_id;
    task->kind = kind;
    task->status = TaskObject::Status::Pending;
    task->where = where;
    task->frame_name = frame_name;
    task->function = function;
    task->positional.clear();
    task->positional.reserve(positional.size());
    for (const Value& value : positional) {
        task->positional.push_back(
            copy_value(machine.arena, value));
    }
    task->named.clear();
    task->named.reserve(named.size());
    for (const auto& [name, value] : named) {
        task->named.emplace_back(
            name, copy_value(machine.arena, value));
    }
    if (receiver != nullptr) {
        task->receiver = *receiver;
        task->has_receiver = true;
    }
    task->counted = kind == TaskObject::Kind::Lazy;
    if (kind == TaskObject::Kind::Worker) {
        ModuleRuntime* owner = function->module;
        if (owner != nullptr) {
            FunctionObject* cloned = nullptr;
            task->module_clone = clone_module_for_task(
                machine, *owner, function, cloned);
            if (cloned != nullptr) {
                task->function = cloned;
            }
        }
    }
    return task;
}

void run_task(Machine& machine, TaskObject* task) {
    if (task == nullptr) {
        return;
    }
    if (task->status == TaskObject::Status::Done
        || task->status == TaskObject::Status::Failed
        || task->status == TaskObject::Status::Canceled) {
        return;
    }
    if (task->counted) {
        task->counted = false;
        if (machine.lazy_pending > 0) {
            --machine.lazy_pending;
        }
    }
    if (task->cancel_requested) {
        task->status = TaskObject::Status::Canceled;
        return;
    }
    task->status = TaskObject::Status::Running;
    auto saved_frames = std::move(machine.call_frames);
    machine.call_frames.clear();
    Frame* saved_current = machine.current_frame;
    machine.current_frame = nullptr;
    const std::size_t saved_depth = machine.frame_depth;
    machine.frame_depth = 0;
    TaskObject* saved_task = machine.current_task;
    machine.current_task = task;
    try {
        const Value value = call_function(
            machine, task->function, task->positional, task->named,
            task->where,
            task->has_receiver ? &task->receiver : nullptr,
            task->frame_name);
        task->result = value;
        task->status = TaskObject::Status::Done;
    } catch (const UnwindSignal& signal) {
        task->error = signal.error;
        task->status = task->cancel_requested
            ? TaskObject::Status::Canceled
            : TaskObject::Status::Failed;
    } catch (const std::exception& error) {
        task->error = make_error(
            machine.arena, "TASK", "task",
            "task raised an unexpected error",
            {std::string("std::exception: ") + error.what()});
        task->status = TaskObject::Status::Failed;
    }
    machine.current_task = saved_task;
    machine.frame_depth = saved_depth;
    machine.current_frame = saved_current;
    machine.call_frames = std::move(saved_frames);
}

std::string task_failure_text(TaskObject* task) {
    if (task != nullptr && task->error != nullptr) {
        return task->error->text();
    }
    return "task failed";
}

Value await_task(
    Machine& machine, TaskObject* task, const std::string& where) {
    if (task == nullptr) {
        throw RuntimeError("null task value");
    }
    if (task->status == TaskObject::Status::Pending) {
        run_task(machine, task);
    }
    if (task->status == TaskObject::Status::Done) {
        return copy_value(machine.arena, task->result);
    }
    if (task->status == TaskObject::Status::Failed) {
        throw_error(make_error(
            machine.arena, "TASK", where, "task failed",
            {task_failure_text(task)}));
    }
    if (task->status == TaskObject::Status::Canceled) {
        const std::string original =
            task->error != nullptr
            ? task->error->text() : "cancellation requested";
        throw_error(make_error(
            machine.arena, "TASK", where, "task canceled",
            {original}));
    }
    throw_error(make_error(
        machine.arena, "TASK", where, "task is already running",
        {"an async task cannot await itself"}));
}

void cancel_task(Machine& machine, TaskObject* task) {
    (void)machine;
    if (task == nullptr) {
        return;
    }
    if (task->status == TaskObject::Status::Pending
        || task->status == TaskObject::Status::Running) {
        task->cancel_requested = true;
        if (task->status == TaskObject::Status::Pending) {
            task->status = TaskObject::Status::Canceled;
        }
    }
    if (task->counted) {
        task->counted = false;
        if (machine.lazy_pending > 0) {
            --machine.lazy_pending;
        }
    }
}

Value invoke_function(
    Machine& machine,
    FunctionObject* function,
    std::vector<Value> positional,
    std::vector<std::pair<std::string, Value>> named,
    const std::string& where,
    const Value* receiver,
    const std::string& frame_name) {
    if (function_is_async(function)) {
        return make_task(create_task(
            machine, function, std::move(positional),
            std::move(named), receiver, where, frame_name,
            TaskObject::Kind::Lazy));
    }
    return call_function(
        machine, function, std::move(positional), std::move(named),
        where, receiver, frame_name);
}

Value string_from_utf8(Machine& machine, const std::string& text) {
    return make_string(machine.arena.allocate_string_utf8(text));
}

[[noreturn]] void invalid_cast(
    Machine& machine,
    const std::string& target,
    const std::string& source) {
    throw_error(make_error(
        machine.arena, "TYPE", "binary expression",
        "Invalid explicit cast types",
        {"unable to cast " + source + " to " + target}));
}

std::string cast_string(Machine& machine, const Value& value) {
    switch (value.tag) {
        case Tag::Nova:
            return "nova";
        case Tag::Undef:
            return "<" + runtime_type_name(value) + ": undefined>";
        case Tag::Str:
            return as_string_const(value)->utf8;
        case Tag::Char: {
            std::string text;
            append_utf8(text, value.c);
            return text;
        }
        case Tag::Int:
            return std::to_string(value.i);
        case Tag::BigInt:
            return as_bigint_const(value)->value.format_decimal();
        case Tag::Num:
            return format_number(value.d);
        case Tag::Bool:
            return value.b ? "true" : "false";
        case Tag::Arr:
        case Tag::Tup:
        case Tag::Map:
        case Tag::Set:
            return format_value(value);
        case Tag::Obj: {
            const ObjectObject* object = as_object(value);
            if (object != nullptr && object->is_enum) {
                return format_value(value);
            }
            invalid_cast(
                machine, "str", runtime_type_name(value));
        }
        case Tag::Project:
            return "<Project>";
        default:
            invalid_cast(
                machine, "str", runtime_type_name(value));
    }
}

Value cast_value(
    Machine& machine,
    Frame& frame,
    const Value& value,
    const std::string& target) {
    if (target.empty() || target == "any" || target == "mixed") {
        return value;
    }
    if (target == runtime_type_name(value)) {
        return value;
    }
    if (value.tag == Tag::Fun) {
        return value;
    }
    if (value.tag == Tag::Obj) {
        ObjectObject* object = as_object(value);
        const std::string type_name =
            object->type != nullptr && object->type->info != nullptr
            ? object->type->info->name
            : (object != nullptr ? object->type_name : std::string());
        if (target == "obj" || target == type_name) {
            return copy_value(machine.arena, value);
        }
    }
    if (target == "obj") {
        invalid_cast(machine, target, runtime_type_name(value));
    }
    if (target == "str") {
        return string_from_utf8(machine, cast_string(machine, value));
    }
    if (target == "int") {
        switch (value.tag) {
            case Tag::Int:
            case Tag::BigInt:
                return value;
            case Tag::Bool:
                return make_int(value.b ? 1 : 0);
            case Tag::Num: {
                const std::int64_t converted =
                    num_to_int(value.d, "explicit cast");
                return make_int(converted);
            }
            case Tag::Str: {
                const std::string text = as_string_const(value)->utf8;
                try {
                    std::size_t consumed = 0;
                    const long long converted =
                        std::stoll(text, &consumed);
                    if (consumed != text.size()) {
                        throw std::invalid_argument("trailing");
                    }
                    return make_int(converted);
                } catch (const std::exception&) {
                    throw_error(make_error(
                        machine.arena, "RUNTIME", "explicit cast",
                        "Invalid int string", {"\"" + text + "\""}));
                }
            }
            case Tag::Nova:
                return make_int(0);
            default:
                invalid_cast(
                    machine, target, runtime_type_name(value));
        }
    }
    if (target == "num") {
        switch (value.tag) {
            case Tag::Num:
                return value;
            case Tag::Int:
                return make_num(static_cast<double>(value.i));
            case Tag::BigInt:
                return make_num(
                    as_bigint_const(value)->value.to_double());
            case Tag::Bool:
                return make_num(value.b ? 1.0 : 0.0);
            case Tag::Str: {
                const std::string text = as_string_const(value)->utf8;
                try {
                    std::size_t consumed = 0;
                    const double converted = std::stod(text, &consumed);
                    if (consumed != text.size()) {
                        throw std::invalid_argument("trailing");
                    }
                    return make_num(converted);
                } catch (const std::exception&) {
                    throw_error(make_error(
                        machine.arena, "RUNTIME", "explicit cast",
                        "Invalid num string", {"\"" + text + "\""}));
                }
            }
            case Tag::Nova:
                return make_num(0.0);
            default:
                invalid_cast(
                    machine, target, runtime_type_name(value));
        }
    }
    if (target == "bool") {
        return make_bool(truthy(value));
    }
    if (target == "char") {
        if (value.tag == Tag::Char) {
            return value;
        }
        if (value.tag == Tag::Nova) {
            return make_char(U'\0');
        }
        if (value.tag == Tag::Str) {
            const std::u32string& text =
                as_string_const(value)->code_points;
            if (text.empty()) {
                return make_char(U'\0');
            }
            if (text.size() == 1) {
                return make_char(text.front());
            }
        }
        invalid_cast(machine, target, runtime_type_name(value));
    }
    if (target == "arr") {
        switch (value.tag) {
            case Tag::Arr:
                return copy_value(machine.arena, value);
            case Tag::Tup:
                return make_array(machine.arena.allocate_array(
                    as_tuple(value)->items));
            case Tag::Str: {
                std::vector<Value> items;
                for (const char32_t code_point :
                     as_string_const(value)->code_points) {
                    items.push_back(make_string(
                        machine.arena.allocate_string(
                            std::u32string(1, code_point))));
                }
                return make_array(
                    machine.arena.allocate_array(std::move(items)));
            }
            case Tag::Map: {
                std::vector<Value> items;
                for (const auto& entry : as_map(value)->entries) {
                    items.push_back(make_tuple(
                        machine.arena.allocate_tuple(
                            {entry.first, entry.second})));
                }
                return make_array(
                    machine.arena.allocate_array(std::move(items)));
            }
            case Tag::Nova:
                return make_array(machine.arena.allocate_array());
            default:
                invalid_cast(
                    machine, target, runtime_type_name(value));
        }
    }
    if (target == "tup") {
        switch (value.tag) {
            case Tag::Tup:
                return copy_value(machine.arena, value);
            case Tag::Arr:
                return make_tuple(machine.arena.allocate_tuple(
                    as_array(value)->items));
            case Tag::Map: {
                std::vector<Value> items;
                for (const auto& entry : as_map(value)->entries) {
                    items.push_back(make_tuple(
                        machine.arena.allocate_tuple(
                            {entry.first, entry.second})));
                }
                return make_tuple(
                    machine.arena.allocate_tuple(std::move(items)));
            }
            case Tag::Nova:
                return make_tuple(machine.arena.allocate_tuple());
            default:
                invalid_cast(
                    machine, target, runtime_type_name(value));
        }
    }
    if (target == "set") {
        if (value.tag == Tag::Set) {
            return copy_value(machine.arena, value);
        }
        if (value.tag == Tag::Nova) {
            return make_set(machine.arena.allocate_set());
        }
        invalid_cast(machine, target, runtime_type_name(value));
    }
    if (target == "map") {
        if (value.tag == Tag::Map) {
            return copy_value(machine.arena, value);
        }
        if (value.tag == Tag::Nova) {
            return make_map(machine.arena.allocate_map());
        }
        invalid_cast(machine, target, runtime_type_name(value));
    }
    if (value.tag == Tag::Tup || value.tag == Tag::Arr) {
        TypeRuntime* type = nullptr;
        const auto direct = frame.module->types.find(target);
        if (direct != frame.module->types.end()) {
            type = &direct->second;
        } else {
            const auto wildcard =
                frame.module->wildcard_types.find(target);
            if (wildcard != frame.module->wildcard_types.end()) {
                type = wildcard->second;
            }
        }
        if (type != nullptr && type->info != nullptr
            && type->info->kind == "object") {
            const std::vector<Value>& items = value.tag == Tag::Tup
                ? as_tuple(value)->items : as_array(value)->items;
            if (items.size() > type->info->properties.size()) {
                invalid_cast(
                    machine, target, runtime_type_name(value));
            }
            ObjectObject* object = machine.arena.allocate_object(
                type->info->name, false, "");
            object->type = type;
            object->module = type->module;
            initialize_object_fields(machine, object, *type);
            for (std::size_t index = 0; index < items.size();
                 ++index) {
                object->fields[type->info->properties[index].name] =
                    copy_value(machine.arena, items[index]);
            }
            return make_object(object);
        }
    }
    {
        const Value coerced = coerce_declared_value(
            machine, frame, target, value);
        if (coerced.tag == Tag::Obj) {
            return coerced;
        }
    }
    invalid_cast(machine, target, runtime_type_name(value));
}

struct DestructureEntry {
    std::string name;
    std::int32_t slot = -1;
    bool reference = false;
};

std::vector<DestructureEntry> parse_destructure_entries(
    const std::string& text) {
    std::vector<DestructureEntry> entries;
    const std::size_t key = text.find("\"entries\":[");
    if (key == std::string::npos) {
        return entries;
    }
    std::size_t position = key + 10;
    while (position < text.size()) {
        while (position < text.size()
               && (std::isspace(
                       static_cast<unsigned char>(text[position]))
                   || text[position] == ',')) {
            ++position;
        }
        if (position >= text.size() || text[position] == ']') {
            break;
        }
        if (text[position] != '{') {
            ++position;
            continue;
        }
        const std::size_t start = position;
        int depth = 0;
        while (position < text.size()) {
            if (text[position] == '{') {
                ++depth;
            } else if (text[position] == '}') {
                --depth;
                if (depth == 0) {
                    ++position;
                    break;
                }
            }
            ++position;
        }
        const std::string entry =
            text.substr(start, position - start);
        DestructureEntry parsed;
        const std::size_t name_at = entry.find("\"name\":\"");
        if (name_at != std::string::npos) {
            const std::size_t name_start = name_at + 8;
            const std::size_t name_end =
                entry.find('"', name_start);
            if (name_end != std::string::npos) {
                parsed.name = entry.substr(
                    name_start, name_end - name_start);
            }
        }
        const std::size_t slot_at = entry.find("\"slot\":");
        if (slot_at != std::string::npos) {
            try {
                parsed.slot = static_cast<std::int32_t>(
                    std::stoll(entry.substr(slot_at + 7)));
            } catch (const std::exception&) {
                parsed.slot = -1;
            }
        }
        parsed.reference =
            entry.find("\"reference\":true") != std::string::npos;
        entries.push_back(std::move(parsed));
    }
    return entries;
}

Value destructure_value(
    Machine& machine,
    Frame& frame,
    const std::string& descriptor,
    const Value& source) {
    const std::vector<DestructureEntry> entries =
        parse_destructure_entries(descriptor);
    if (source.tag == Tag::Arr || source.tag == Tag::Tup) {
        const std::vector<Value>& items = source.tag == Tag::Arr
            ? as_array(source)->items : as_tuple(source)->items;
        for (std::size_t index = 0; index < entries.size(); ++index) {
            if (index >= items.size()) {
                throw_error(error_index_out_of_range(
                    machine.arena,
                    static_cast<std::int64_t>(index),
                    static_cast<std::int64_t>(items.size())));
            }
            const DestructureEntry& entry = entries[index];
            if (entry.slot < 0
                || static_cast<std::size_t>(entry.slot)
                    >= frame.locals.size()) {
                continue;
            }
            Value bound;
            if (entry.reference && source.tag == Tag::Arr) {
                RefObject* reference =
                    machine.arena.allocate_reference();
                reference->kind = RefObject::Kind::Index;
                reference->array = as_array(source);
                reference->index = index;
                reference->target_type =
                    runtime_type_name(items[index]);
                bound = make_reference(reference);
            } else {
                bound = copy_value(machine.arena, items[index]);
            }
            frame.locals[static_cast<std::size_t>(entry.slot)] = bound;
            publish_module_local(
                frame, static_cast<std::uint32_t>(entry.slot), bound);
        }
        return source;
    }
    if (source.tag == Tag::Obj) {
        ObjectObject* object = as_object(source);
        for (const DestructureEntry& entry : entries) {
            const auto found = object->fields.find(entry.name);
            if (found == object->fields.end()) {
                throw_error(error_identifier_not_found(
                    machine.arena, "destructure declaration",
                    entry.name));
            }
            if (entry.slot < 0
                || static_cast<std::size_t>(entry.slot)
                    >= frame.locals.size()) {
                continue;
            }
            Value bound;
            if (entry.reference) {
                RefObject* reference =
                    machine.arena.allocate_reference();
                reference->kind = RefObject::Kind::Field;
                reference->object = object;
                reference->name = entry.name;
                reference->target_type =
                    runtime_type_name(found->second);
                bound = make_reference(reference);
            } else {
                bound = copy_value(machine.arena, found->second);
            }
            frame.locals[static_cast<std::size_t>(entry.slot)] = bound;
            publish_module_local(
                frame, static_cast<std::uint32_t>(entry.slot), bound);
        }
        return source;
    }
    throw_error(error_type_match(
        machine.arena, "destructure declaration",
        "array or object", runtime_type_name(source)));
}

std::string unescape_pattern_text(const std::string& raw) {
    std::string out;
    for (std::size_t index = 0; index < raw.size(); ++index) {
        if (raw[index] != '\\' || index + 1 >= raw.size()) {
            out.push_back(raw[index]);
            continue;
        }
        const char next = raw[++index];
        switch (next) {
            case 'n': out.push_back('\n'); break;
            case 'r': out.push_back('\r'); break;
            case 't': out.push_back('\t'); break;
            case '\\': out.push_back('\\'); break;
            case '"': out.push_back('"'); break;
            default: out.push_back(next); break;
        }
    }
    return out;
}

bool pattern_scalar(
    Machine& machine, const std::string& text, Value& out) {
    if (text.find("UNARY_EXPRESSION") != std::string::npos) {
        const std::size_t last = text.rfind("\"value\":");
        if (last == std::string::npos) {
            return false;
        }
        std::size_t position = last + 8;
        while (position < text.size()
               && std::isspace(
                   static_cast<unsigned char>(text[position]))) {
            ++position;
        }
        const std::size_t end = text.find_first_of(",}", position);
        if (end == std::string::npos || end == position) {
            return false;
        }
        const std::string number =
            text.substr(position, end - position);
        try {
            if (number.find_first_of(".eE") != std::string::npos) {
                out = make_num(-std::stod(number));
            } else {
                out = make_int(-std::stoll(number));
            }
            return true;
        } catch (const std::exception&) {
            return false;
        }
    }
    const std::size_t key = text.find("\"value\":");
    if (key == std::string::npos) {
        return false;
    }
    std::size_t position = key + 8;
    while (position < text.size()
           && std::isspace(
               static_cast<unsigned char>(text[position]))) {
        ++position;
    }
    if (position >= text.size()) {
        return false;
    }
    if (text[position] == '"') {
        ++position;
        std::string raw;
        while (position < text.size()) {
            if (text[position] == '\\' && position + 1 < text.size()) {
                raw.push_back(text[position]);
                raw.push_back(text[position + 1]);
                position += 2;
                continue;
            }
            if (text[position] == '"') {
                break;
            }
            raw.push_back(text[position]);
            ++position;
        }
        const std::string value = unescape_pattern_text(raw);
        if (text.find("CHAR_LITERAL") != std::string::npos) {
            StringObject* object =
                machine.arena.allocate_string_utf8(value);
            if (object->code_points.size() == 1) {
                out = make_char(object->code_points.front());
                return true;
            }
            return false;
        }
        out = make_string(
            machine.arena.allocate_string_utf8(value));
        return true;
    }
    if (text.compare(position, 4, "true") == 0) {
        out = make_bool(true);
        return true;
    }
    if (text.compare(position, 5, "false") == 0) {
        out = make_bool(false);
        return true;
    }
    if (text.compare(position, 4, "null") == 0) {
        out = make_nova();
        return true;
    }
    const std::size_t end = text.find_first_of(",}", position);
    if (end == std::string::npos || end == position) {
        return false;
    }
    const std::string number = text.substr(position, end - position);
    try {
        if (number.find_first_of(".eE") != std::string::npos) {
            out = make_num(std::stod(number));
        } else {
            out = make_int(std::stoll(number));
        }
        return true;
    } catch (const std::exception&) {
        return false;
    }
}

Value property_default_value(
    Machine& machine, const TypeRuntime& type, const TypeProperty& property) {
    if (type.module == nullptr || type.module->image == nullptr) {
        return make_undef();
    }
    const Image& image = *type.module->image;
    if (property.index >= image.type_specs.size()) {
        return make_undef();
    }
    const std::string& spec = image.type_specs[property.index];
    const std::size_t expression_at = spec.find("\"expression\":");
    if (expression_at == std::string::npos) {
        return make_undef();
    }
    const std::size_t start = spec.find('{', expression_at);
    if (start == std::string::npos) {
        return make_undef();
    }
    int depth = 0;
    std::size_t end = start;
    while (end < spec.size()) {
        if (spec[end] == '{') {
            ++depth;
        } else if (spec[end] == '}') {
            --depth;
            if (depth == 0) {
                ++end;
                break;
            }
        }
        ++end;
    }
    const std::string expression = spec.substr(start, end - start);
    Value value;
    if (pattern_scalar(machine, expression, value)) {
        return copy_value(machine.arena, value);
    }
    return make_undef();
}

void initialize_object_fields(
    Machine& machine, ObjectObject* object, const TypeRuntime& type) {
    if (type.info == nullptr) {
        return;
    }
    for (const TypeProperty& property : type.info->properties) {
        object->fields[property.name] =
            property_default_value(machine, type, property);
        if (!property.is_private) {
            object->private_fields.insert(property.name);
        }
    }
}

Value coerce_declared_value(
    Machine& machine,
    Frame& frame,
    const std::string& type_name,
    const Value& value) {
    TypeRuntime* type = nullptr;
    const auto direct = frame.module->types.find(type_name);
    if (direct != frame.module->types.end()) {
        type = &direct->second;
    } else {
        const auto wildcard =
            frame.module->wildcard_types.find(type_name);
        if (wildcard != frame.module->wildcard_types.end()) {
            type = wildcard->second;
        }
    }
    if (type == nullptr || type->info == nullptr
        || type->info->kind != "object") {
        return value;
    }
    if (value.tag == Tag::Obj) {
        ObjectObject* object = as_object(value);
        const std::string current =
            object->type != nullptr && object->type->info != nullptr
            ? object->type->info->name : object->type_name;
        if (current == type->info->name) {
            return copy_value(machine.arena, value);
        }
    }
    if (type->info->properties.empty()) {
        return value;
    }
    ObjectObject* object = machine.arena.allocate_object(
        type->info->name, false, "");
    object->type = type;
    object->module = type->module;
    initialize_object_fields(machine, object, *type);
    if (value.tag == Tag::Tup || value.tag == Tag::Arr) {
        const std::vector<Value>& items = value.tag == Tag::Tup
            ? as_tuple(value)->items : as_array(value)->items;
        if (items.size() > type->info->properties.size()) {
            return value;
        }
        for (std::size_t index = 0; index < items.size(); ++index) {
            object->fields[type->info->properties[index].name] =
                copy_value(machine.arena, items[index]);
        }
        return make_object(object);
    }
    object->fields[type->info->properties.front().name] =
        copy_value(machine.arena, value);
    return make_object(object);
}

bool match_pattern(
    Machine& machine,
    Frame& frame,
    const PatternDescriptor& pattern,
    const Value& subject) {
    if (pattern.kind == "wildcard") {
        return true;
    }
    if (pattern.kind == "binding") {
        for (const auto& [name, slot] : pattern.bindings) {
            (void)name;
            if (slot < frame.locals.size()) {
                const Value bound =
                    copy_value(machine.arena, subject);
                frame.locals[slot] = bound;
                publish_module_local(frame, slot, bound);
            }
        }
        return true;
    }
    if (pattern.kind == "literal") {
        if (pattern.literal.find("ACCESS_EXPRESSION")
            != std::string::npos) {
            const std::size_t key =
                pattern.literal.rfind("\"value\":\"");
            if (key == std::string::npos
                || subject.tag != Tag::Obj) {
                return false;
            }
            const std::size_t start = key + 9;
            const std::size_t end =
                pattern.literal.find('"', start);
            if (end == std::string::npos) {
                return false;
            }
            const std::string member =
                pattern.literal.substr(start, end - start);
            return as_object(subject)->variant == member;
        }
        Value literal;
        if (!pattern_scalar(machine, pattern.literal, literal)) {
            return false;
        }
        if (subject.tag == Tag::Char && literal.tag == Tag::Str) {
            const StringObject* text = as_string_const(literal);
            return text->code_points.size() == 1
                && text->code_points.front() == subject.c;
        }
        return value_equal(subject, literal);
    }
    if (pattern.kind == "range") {
        Value start;
        Value end;
        if (!pattern_scalar(machine, pattern.start_ast, start)
            || !pattern_scalar(machine, pattern.end_ast, end)) {
            return false;
        }
        if (!is_numeric_operand(subject)
            || !is_numeric_operand(start)
            || !is_numeric_operand(end)) {
            return false;
        }
        const double value = as_double(subject);
        return as_double(start) <= value && value < as_double(end);
    }
    if (pattern.kind == "array" || pattern.kind == "tuple") {
        if (pattern.kind == "tuple") {
            if (subject.tag != Tag::Tup) {
                return false;
            }
        } else if (subject.tag != Tag::Arr
                   && subject.tag != Tag::Tup) {
            return false;
        }
        const std::vector<Value>& items = subject.tag == Tag::Arr
            ? as_array(subject)->items
            : as_tuple(subject)->items;
        const bool has_rest = pattern.rest_slot != -1;
        if ((!has_rest && items.size() != pattern.nested.size())
            || (has_rest && items.size() < pattern.nested.size())) {
            return false;
        }
        for (std::size_t index = 0; index < pattern.nested.size();
             ++index) {
            if (!match_pattern(
                    machine, frame, pattern.nested[index],
                    items[index])) {
                return false;
            }
        }
        if (pattern.rest_slot >= 0
            && static_cast<std::size_t>(pattern.rest_slot)
                < frame.locals.size()) {
            std::vector<Value> tail;
            for (std::size_t index = pattern.nested.size();
                 index < items.size(); ++index) {
                tail.push_back(
                    copy_value(machine.arena, items[index]));
            }
            const Value rest = subject.tag == Tag::Tup
                ? make_tuple(
                    machine.arena.allocate_tuple(std::move(tail)))
                : make_array(
                    machine.arena.allocate_array(std::move(tail)));
            frame.locals[
                static_cast<std::size_t>(pattern.rest_slot)] = rest;
            publish_module_local(
                frame,
                static_cast<std::uint32_t>(pattern.rest_slot), rest);
        }
        return true;
    }
    if (pattern.kind == "object") {
        if (subject.tag != Tag::Obj) {
            return false;
        }
        ObjectObject* object = as_object(subject);
        const std::string type_name =
            object->type != nullptr && object->type->info != nullptr
            ? object->type->info->name : object->type_name;
        if (!pattern.type_name.has_value()
            || *pattern.type_name != type_name) {
            return false;
        }
        for (const auto& [name, nested] : pattern.fields) {
            const auto found = object->fields.find(name);
            if (found == object->fields.end()) {
                return false;
            }
            if (!match_pattern(
                    machine, frame, nested, found->second)) {
                return false;
            }
        }
        return true;
    }
    return false;
}

std::string string_to_utf8(const Value& value) {
    if (value.tag != Tag::Str) {
        runtime_fail(
            std::string("expected a string, got ") + tag_name(value.tag));
    }
    return as_string_const(value)->utf8;
}

std::int64_t value_as_int(const Value& value, const char* what) {
    if (value.tag == Tag::Int) {
        return value.i;
    }
    if (value.tag == Tag::BigInt) {
        const BigInt& big = as_bigint_const(value)->value;
        if (!bigint_fits_int64(big)) {
            runtime_fail(
                std::string(what) + " is outside the int64 range");
        }
        return bigint_to_int64(big);
    }
    runtime_fail(std::string(what) + " requires an int");
}

std::int64_t resolved_index(
    Machine& machine,
    const Value& index,
    std::size_t size,
    const char* what) {
    if (index.tag != Tag::Int && index.tag != Tag::BigInt) {
        throw_error(error_type_match(
            machine.arena, std::string(what) + " indexing",
            "int", runtime_type_name(index)));
    }
    const std::int64_t original = value_as_int(index, what);
    std::int64_t value = original;
    const std::int64_t length = static_cast<std::int64_t>(size);
    if (value < 0) {
        value += length;
    }
    if (value < 0 || value >= length) {
        throw_error(error_index_out_of_range(
            machine.arena, original, length));
    }
    return value;
}

std::size_t slice_start(const Value& value, std::size_t size) {
    if (value.tag == Tag::Nova) {
        return 0;
    }
    std::int64_t index = value_as_int(value, "slice start");
    const std::int64_t length = static_cast<std::int64_t>(size);
    if (index < 0) {
        index += length;
    }
    if (index < 0) {
        index = 0;
    }
    if (index > length) {
        index = length;
    }
    return static_cast<std::size_t>(index);
}

std::size_t slice_end(const Value& value, std::size_t size) {
    if (value.tag == Tag::Nova) {
        return size;
    }
    std::int64_t index = value_as_int(value, "slice end");
    const std::int64_t length = static_cast<std::int64_t>(size);
    if (index < 0) {
        index += length;
    }
    if (index < 0) {
        index = 0;
    }
    if (index > length) {
        index = length;
    }
    return static_cast<std::size_t>(index);
}

std::string python_value_repr(const Value& value) {
    std::string data;
    switch (value.tag) {
        case Tag::Int: data = std::to_string(value.i); break;
        case Tag::BigInt:
            data = as_bigint_const(value)->value.format_decimal();
            break;
        case Tag::Num: data = format_number(value.d); break;
        case Tag::Bool: data = value.b ? "True" : "False"; break;
        case Tag::Str: data = as_string_const(value)->utf8; break;
        case Tag::Char: {
            append_utf8(data, value.c);
            break;
        }
        case Tag::Nova: data = "None"; break;
        default: data = format_value(value); break;
    }
    return "PowangType(" + runtime_type_name(value)
        + " | defined: " + data + ")";
}

Value index_get(
    Machine& machine, const Value& container, const Value& index) {
    switch (container.tag) {
        case Tag::Map: {
            const Value* found = map_get(*as_map(container), index);
            if (found == nullptr) {
                throw_error(error_key(
                    machine.arena, python_value_repr(index)));
            }
            return *found;
        }
        case Tag::Arr: {
            const auto& items = as_array(container)->items;
            const std::int64_t position =
                resolved_index(machine, index, items.size(), "arr");
            return items[static_cast<std::size_t>(position)];
        }
        case Tag::Tup: {
            const auto& items = as_tuple(container)->items;
            const std::int64_t position =
                resolved_index(machine, index, items.size(), "tup");
            return items[static_cast<std::size_t>(position)];
        }
        case Tag::Str: {
            const auto& points = as_string_const(container)->code_points;
            const std::int64_t position =
                resolved_index(machine, index, points.size(), "str");
            return make_char(points[static_cast<std::size_t>(position)]);
        }
        default:
            runtime_fail(
                std::string("value of type ") + tag_name(container.tag)
                + " is not indexable");
    }
}

Value index_set(
    Machine& machine,
    const Value& container,
    const Value& index,
    const Value& value) {
    const Value stored = copy_value(machine.arena, value);
    switch (container.tag) {
        case Tag::Map: {
            const Value key = copy_value(machine.arena, index);
            map_set(*as_map(container), key, stored);
            return stored;
        }
        case Tag::Arr: {
            ArrayObject* array = as_array(container);
            if (array->elements_locked) {
                throw_error(error_const(
                    machine.arena, "assignment",
                    "array elements are locked",
                    {"the element type ends with '!'"}));
            }
            auto& items = array->items;
            const std::int64_t position =
                resolved_index(machine, index, items.size(), "arr");
            items[static_cast<std::size_t>(position)] = stored;
            return stored;
        }
        case Tag::Tup:
            runtime_fail("tuples are immutable");
        case Tag::Str:
            runtime_fail("strings are immutable");
        default:
            runtime_fail(
                std::string("value of type ") + tag_name(container.tag)
                + " is not assignable by index");
    }
}

Value slice_value(
    Machine& machine,
    const Value& target,
    const Value& start,
    const Value& end) {
    std::size_t size = 0;
    switch (target.tag) {
        case Tag::Str:
            size = as_string_const(target)->code_points.size();
            break;
        case Tag::Arr:
            size = as_array(target)->items.size();
            break;
        case Tag::Tup:
            size = as_tuple(target)->items.size();
            break;
        default:
            runtime_fail(
                std::string("value of type ") + tag_name(target.tag)
                + " cannot be sliced");
    }
    const std::size_t begin = slice_start(start, size);
    const std::size_t finish = slice_end(end, size);
    const std::size_t count = finish > begin ? finish - begin : 0;
    switch (target.tag) {
        case Tag::Str: {
            std::u32string points =
                as_string_const(target)->code_points.substr(begin, count);
            return make_string(machine.arena.allocate_string(
                std::move(points)));
        }
        case Tag::Arr: {
            const auto& source = as_array(target)->items;
            std::vector<Value> items(
                source.begin() + static_cast<std::ptrdiff_t>(begin),
                source.begin() + static_cast<std::ptrdiff_t>(begin + count));
            return make_array(machine.arena.allocate_array(std::move(items)));
        }
        case Tag::Tup: {
            const auto& source = as_tuple(target)->items;
            std::vector<Value> items(
                source.begin() + static_cast<std::ptrdiff_t>(begin),
                source.begin() + static_cast<std::ptrdiff_t>(begin + count));
            return make_tuple(machine.arena.allocate_tuple(std::move(items)));
        }
        default:
            runtime_fail("unsupported slice target");
    }
}

Value reverse_value(Machine& machine, const Value& value) {
    switch (value.tag) {
        case Tag::Int:
        case Tag::BigInt: {
            const std::string text =
                value.tag == Tag::Int
                ? std::to_string(value.i)
                : as_bigint_const(value)->value.format_decimal();
            const std::string reversed(text.rbegin(), text.rend());
            try {
                return make_int(std::stoll(reversed));
            } catch (const std::exception&) {
                return make_nova();
            }
        }
        case Tag::Num: {
            const std::string text = format_number(value.d);
            const std::string reversed(text.rbegin(), text.rend());
            try {
                return make_num(std::stod(reversed));
            } catch (const std::exception&) {
                return make_nova();
            }
        }
        case Tag::Str: {
            const std::u32string& source =
                as_string_const(value)->code_points;
            std::u32string reversed(source.rbegin(), source.rend());
            return make_string(machine.arena.allocate_string(
                std::move(reversed)));
        }
        case Tag::Arr: {
            const auto& source = as_array(value)->items;
            std::vector<Value> items(source.rbegin(), source.rend());
            return make_array(machine.arena.allocate_array(std::move(items)));
        }
        case Tag::Tup: {
            const auto& source = as_tuple(value)->items;
            std::vector<Value> items(source.rbegin(), source.rend());
            return make_tuple(machine.arena.allocate_tuple(std::move(items)));
        }
        default:
            return make_nova();
    }
}

std::int64_t value_size(Machine& machine, const Value& value) {
    switch (value.tag) {
        case Tag::Str:
            return static_cast<std::int64_t>(
                as_string_const(value)->code_points.size());
        case Tag::Arr:
            return static_cast<std::int64_t>(as_array(value)->items.size());
        case Tag::Tup:
            return static_cast<std::int64_t>(as_tuple(value)->items.size());
        case Tag::Map:
            return static_cast<std::int64_t>(as_map(value)->entries.size());
        case Tag::Set:
            return static_cast<std::int64_t>(as_set(value)->items.size());
        case Tag::Char:
            return 1;
        default:
            throw_error(error_unsupported_operation(
                machine.arena, "",
                runtime_type_name(value) + " ", "size"));
    }
}

Value builtin_size(Machine& machine, const Value& value) {
    return make_int(value_size(machine, value));
}

Value builtin_size_all(Machine& machine, const std::vector<Value>& values) {
    (void)machine;
    std::int64_t total = 0;
    for (const Value& value : values) {
        total += value_size(machine, value);
    }
    return make_int(total);
}

char32_t character_value(const Value& value, const char* what) {
    if (value.tag == Tag::Char) {
        return value.c;
    }
    if (value.tag == Tag::Str) {
        const auto& points = as_string_const(value)->code_points;
        if (points.size() == 1) {
            return points[0];
        }
    }
    runtime_fail(
        std::string(what) + " expects a char or a one-character str");
}

bool char_is_digit(char32_t value) {
    return value >= U'0' && value <= U'9';
}

bool char_is_alpha(char32_t value) {
    return (value >= U'a' && value <= U'z')
        || (value >= U'A' && value <= U'Z');
}

bool char_is_space(char32_t value) {
    return value == U' ' || value == U'\t' || value == U'\n'
        || value == U'\r' || value == U'\v' || value == U'\f';
}

bool char_is_upper(char32_t value) {
    return value >= U'A' && value <= U'Z';
}

bool char_is_lower(char32_t value) {
    return value >= U'a' && value <= U'z';
}

bool char_is_ascii(char32_t value) {
    return value < 0x80u;
}

std::u32string string_operand(const Value& value, const char* what) {
    if (value.tag == Tag::Str) {
        return as_string_const(value)->code_points;
    }
    if (value.tag == Tag::Char) {
        return std::u32string(1, value.c);
    }
    runtime_fail(std::string(what) + " expects a str or a char");
}

std::string format_text(
    Arena& arena,
    const std::string& format,
    const std::vector<Value>& arguments) {
    std::string out;
    std::size_t index = 0;
    while (index < format.size()) {
        if (format[index] != '{') {
            out.push_back(format[index]);
            ++index;
            continue;
        }
        const std::size_t close = format.find('}', index + 1);
        if (close == std::string::npos) {
            out += format.substr(index);
            break;
        }
        const std::string inside =
            format.substr(index + 1, close - index - 1);
        const std::size_t slash = inside.find('/');
        const std::string index_text = inside.substr(0, slash);
        bool digits = !index_text.empty();
        for (const char character : index_text) {
            if (!std::isdigit(static_cast<unsigned char>(character))) {
                digits = false;
                break;
            }
        }
        if (!digits) {
            out += format.substr(index, close - index + 1);
            index = close + 1;
            continue;
        }
        const std::size_t argument_index =
            static_cast<std::size_t>(std::stoul(index_text));
        if (argument_index >= arguments.size()) {
            runtime_fail("format argument index out of range");
        }
        if (slash == std::string::npos) {
            out += format_value(arguments[argument_index]);
            index = close + 1;
            continue;
        }
        const std::string separator = inside.substr(slash + 1);
        std::vector<std::string> items;
        const Value& argument = arguments[argument_index];
        if (argument.tag == Tag::Arr) {
            for (const Value& item : as_array(argument)->items) {
                items.push_back(format_value(item));
            }
        } else if (argument.tag == Tag::Str) {
            for (const char32_t code_point :
                 as_string_const(argument)->code_points) {
                items.push_back(format_value(make_char(code_point)));
            }
        } else if (argument.tag == Tag::Map) {
            for (const auto& entry : as_map(argument)->entries) {
                std::vector<Value> pair = {entry.first, entry.second};
                items.push_back(format_value(
                    make_array(arena.allocate_array(std::move(pair)))));
            }
        } else {
            items.push_back(format_value(argument));
        }
        for (std::size_t position = 0; position < items.size(); ++position) {
            if (position != 0) {
                out += separator;
            }
            out += items[position];
        }
        index = close + 1;
    }
    return out;
}

Value array_method(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& arguments) {
    if (arguments.empty() || arguments[0].tag != Tag::Arr) {
        runtime_fail("arr method requires an array receiver");
    }
    const ArrayObject* source = as_array(arguments[0]);
    const std::size_t size = source->items.size();
    if (name == "size") {
        return make_int(static_cast<std::int64_t>(size));
    }
    if (name == "get" || name == "pop" || name == "popget") {
        const Value index =
            arguments.size() > 1 ? arguments[1] : make_int(-1);
        const std::int64_t position =
            resolved_index(machine, index, size, "arr");
        return copy_value(
            machine.arena,
            source->items[static_cast<std::size_t>(position)]);
    }
    if (name == "push" || name == "add") {
        if (arguments.size() < 2) {
            runtime_fail("arr." + name + " requires an argument");
        }
        std::vector<Value> items;
        items.reserve(size + 1);
        for (const Value& item : source->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        if (name == "push") {
            items.push_back(copy_value(machine.arena, arguments[1]));
        } else {
            const Value& addition = arguments[1];
            if (addition.tag == Tag::Arr) {
                for (const Value& item : as_array(addition)->items) {
                    items.push_back(copy_value(machine.arena, item));
                }
            } else if (addition.tag == Tag::Tup) {
                for (const Value& item : as_tuple(addition)->items) {
                    items.push_back(copy_value(machine.arena, item));
                }
            } else if (addition.tag == Tag::Set) {
                for (const Value& item : as_set(addition)->items) {
                    items.push_back(copy_value(machine.arena, item));
                }
            } else {
                runtime_fail("arr.add expects an arr, tup or set");
            }
        }
        return make_array(
            machine.arena.allocate_array(std::move(items)));
    }
    if (name == "put") {
        if (arguments.size() < 3) {
            runtime_fail("arr.put requires an index and a value");
        }
        std::vector<Value> items;
        items.reserve(size + 1);
        for (const Value& item : source->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        std::int64_t position = value_as_int(arguments[1], "arr.put");
        if (position < 0) {
            position = std::max<std::int64_t>(
                0, static_cast<std::int64_t>(items.size()) + position);
        }
        if (position > static_cast<std::int64_t>(items.size())) {
            position = static_cast<std::int64_t>(items.size());
        }
        items.insert(
            items.begin() + position,
            copy_value(machine.arena, arguments[2]));
        return make_array(
            machine.arena.allocate_array(std::move(items)));
    }
    if (name == "popval") {
        if (arguments.size() < 2) {
            runtime_fail("arr.popval requires a value");
        }
        const std::int64_t maximum = arguments.size() > 2
            ? value_as_int(arguments[2], "arr.popval")
            : -1;
        std::vector<Value> items;
        std::int64_t removed = 0;
        for (const Value& item : source->items) {
            if ((maximum < 0 || removed < maximum)
                && value_equal(item, arguments[1])) {
                ++removed;
                continue;
            }
            items.push_back(copy_value(machine.arena, item));
        }
        return make_array(
            machine.arena.allocate_array(std::move(items)));
    }
    if (name == "set") {
        if (arguments.size() < 3) {
            runtime_fail("arr.set requires an index and a value");
        }
        std::vector<Value> items;
        items.reserve(size);
        for (const Value& item : source->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        const std::int64_t position =
            resolved_index(machine, arguments[1], size, "arr");
        items[static_cast<std::size_t>(position)] =
            copy_value(machine.arena, arguments[2]);
        return make_array(
            machine.arena.allocate_array(std::move(items)));
    }
    if (name == "reverse") {
        std::vector<Value> items;
        items.reserve(size);
        for (const Value& item : source->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        std::reverse(items.begin(), items.end());
        return make_array(
            machine.arena.allocate_array(std::move(items)));
    }
    if (name == "clear") {
        return make_array(machine.arena.allocate_array());
    }
    runtime_fail("unknown arr method: " + name);
}

Value string_method(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& arguments) {
    if (arguments.empty() || arguments[0].tag != Tag::Str) {
        runtime_fail("str method requires a string receiver");
    }
    const std::u32string& source =
        as_string_const(arguments[0])->code_points;
    if (name == "size") {
        return make_int(static_cast<std::int64_t>(source.size()));
    }
    if (name == "get") {
        const Value index =
            arguments.size() > 1 ? arguments[1] : make_int(-1);
        const std::int64_t position =
            resolved_index(machine, index, source.size(), "str");
        return make_char(source[static_cast<std::size_t>(position)]);
    }
    if (name == "add") {
        if (arguments.size() < 2) {
            runtime_fail("str.add requires an argument");
        }
        std::u32string text = source;
        text += string_operand(arguments[1], "str.add");
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    if (name == "sub") {
        if (arguments.size() < 2) {
            runtime_fail("str.sub requires an argument");
        }
        std::u32string text = source;
        const std::u32string needle =
            string_operand(arguments[1], "str.sub");
        const std::size_t found = text.find(needle);
        if (found != std::u32string::npos) {
            text.erase(found, needle.size());
        }
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    if (name == "mul") {
        const std::int64_t count = arguments.size() > 1
            ? value_as_int(arguments[1], "str.mul")
            : 0;
        std::u32string text;
        for (std::int64_t index = 0; index < count; ++index) {
            text += source;
        }
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    if (name == "div") {
        if (arguments.size() < 2) {
            runtime_fail("str.div requires a separator");
        }
        const std::u32string separator =
            string_operand(arguments[1], "str.div");
        if (separator.empty()) {
            runtime_fail("str.div separator must not be empty");
        }
        std::vector<Value> parts;
        std::size_t start = 0;
        while (true) {
            const std::size_t found = source.find(separator, start);
            if (found == std::u32string::npos) {
                parts.push_back(make_string(
                    machine.arena.allocate_string(source.substr(start))));
                break;
            }
            parts.push_back(make_string(machine.arena.allocate_string(
                source.substr(start, found - start))));
            start = found + separator.size();
        }
        return make_array(
            machine.arena.allocate_array(std::move(parts)));
    }
    if (name == "count") {
        if (arguments.size() < 2) {
            runtime_fail("str.count requires a substring");
        }
        const std::u32string needle =
            string_operand(arguments[1], "str.count");
        if (needle.empty()) {
            return make_int(static_cast<std::int64_t>(source.size() + 1));
        }
        std::int64_t count = 0;
        std::size_t start = 0;
        while (true) {
            const std::size_t found = source.find(needle, start);
            if (found == std::u32string::npos) {
                break;
            }
            ++count;
            start = found + needle.size();
        }
        return make_int(count);
    }
    if (name == "reverse") {
        std::u32string text(source.rbegin(), source.rend());
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    if (name == "chars") {
        std::vector<Value> chars;
        chars.reserve(source.size());
        for (const char32_t code_point : source) {
            chars.push_back(make_char(code_point));
        }
        return make_array(
            machine.arena.allocate_array(std::move(chars)));
    }
    runtime_fail("unknown str method: " + name);
}

Value map_method(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& arguments) {
    if (arguments.empty() || arguments[0].tag != Tag::Map) {
        runtime_fail("map method requires a map receiver");
    }
    const MapObject* source = as_map(arguments[0]);
    if (name == "size") {
        return make_int(static_cast<std::int64_t>(source->entries.size()));
    }
    if (name == "has") {
        if (arguments.size() < 2) {
            runtime_fail("map.has requires a key");
        }
        return make_bool(map_get(*source, arguments[1]) != nullptr);
    }
    if (name == "get") {
        if (arguments.size() < 2) {
            runtime_fail("map.get requires a key");
        }
        const Value* found = map_get(*source, arguments[1]);
        if (found != nullptr) {
            return copy_value(machine.arena, *found);
        }
        if (arguments.size() > 2) {
            return copy_value(machine.arena, arguments[2]);
        }
        runtime_fail("map key was not found");
    }
    if (name == "pop" || name == "popget") {
        if (arguments.size() < 2) {
            runtime_fail("map." + name + " requires a key");
        }
        const Value* found = map_get(*source, arguments[1]);
        if (found == nullptr) {
            runtime_fail("map key was not found");
        }
        const Value value = copy_value(machine.arena, *found);
        if (name == "popget") {
            return value;
        }
        MapObject* result = machine.arena.allocate_map();
        for (const auto& entry : source->entries) {
            if (!value_equal(entry.first, arguments[1])) {
                map_set(
                    *result,
                    copy_value(machine.arena, entry.first),
                    copy_value(machine.arena, entry.second));
            }
        }
        return make_map(result);
    }
    if (name == "merge") {
        if (arguments.size() < 2 || arguments[1].tag != Tag::Map) {
            runtime_fail("map.merge requires a map");
        }
        MapObject* result = machine.arena.allocate_map();
        for (const auto& entry : source->entries) {
            map_set(
                *result,
                copy_value(machine.arena, entry.first),
                copy_value(machine.arena, entry.second));
        }
        for (const auto& entry : as_map(arguments[1])->entries) {
            map_set(
                *result,
                copy_value(machine.arena, entry.first),
                copy_value(machine.arena, entry.second));
        }
        return make_map(result);
    }
    if (name == "keys") {
        std::vector<Value> keys;
        keys.reserve(source->entries.size());
        for (const auto& entry : source->entries) {
            keys.push_back(copy_value(machine.arena, entry.first));
        }
        return make_array(
            machine.arena.allocate_array(std::move(keys)));
    }
    if (name == "values") {
        std::vector<Value> values;
        values.reserve(source->entries.size());
        for (const auto& entry : source->entries) {
            values.push_back(copy_value(machine.arena, entry.second));
        }
        return make_array(
            machine.arena.allocate_array(std::move(values)));
    }
    if (name == "clear") {
        return make_map(machine.arena.allocate_map());
    }
    runtime_fail("unknown map method: " + name);
}

Value set_method(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& arguments) {
    if (arguments.empty() || arguments[0].tag != Tag::Set) {
        runtime_fail("set method requires a set receiver");
    }
    const SetObject* source = as_set(arguments[0]);
    if (name == "size") {
        return make_int(static_cast<std::int64_t>(source->items.size()));
    }
    if (name == "has") {
        if (arguments.size() < 2) {
            runtime_fail("set.has requires a value");
        }
        return make_bool(set_has(*source, arguments[1]));
    }
    if (name == "add") {
        if (arguments.size() < 2) {
            runtime_fail("set.add requires a value");
        }
        SetObject* result = machine.arena.allocate_set();
        for (const Value& item : source->items) {
            set_add(*result, copy_value(machine.arena, item));
        }
        set_add(*result, copy_value(machine.arena, arguments[1]));
        return make_set(result);
    }
    if (name == "pop" || name == "popget") {
        if (arguments.size() < 2) {
            runtime_fail("set." + name + " requires a value");
        }
        const bool existed = set_has(*source, arguments[1]);
        if (name == "popget") {
            return make_bool(existed);
        }
        SetObject* result = machine.arena.allocate_set();
        for (const Value& item : source->items) {
            if (!value_equal(item, arguments[1])) {
                set_add(*result, copy_value(machine.arena, item));
            }
        }
        return make_set(result);
    }
    if (name == "union" || name == "intersection" || name == "difference") {
        if (arguments.size() < 2 || arguments[1].tag != Tag::Set) {
            runtime_fail("set." + name + " requires a set");
        }
        const SetObject* other = as_set(arguments[1]);
        SetObject* result = machine.arena.allocate_set();
        if (name == "union") {
            for (const Value& item : source->items) {
                set_add(*result, copy_value(machine.arena, item));
            }
            for (const Value& item : other->items) {
                set_add(*result, copy_value(machine.arena, item));
            }
        } else if (name == "intersection") {
            for (const Value& item : source->items) {
                if (set_has(*other, item)) {
                    set_add(*result, copy_value(machine.arena, item));
                }
            }
        } else {
            for (const Value& item : source->items) {
                if (!set_has(*other, item)) {
                    set_add(*result, copy_value(machine.arena, item));
                }
            }
        }
        return make_set(result);
    }
    if (name == "to_arr") {
        std::vector<Value> items;
        items.reserve(source->items.size());
        for (const Value& item : source->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        return make_array(
            machine.arena.allocate_array(std::move(items)));
    }
    if (name == "clear") {
        return make_set(machine.arena.allocate_set());
    }
    runtime_fail("unknown set method: " + name);
}

Value tuple_method(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& arguments) {
    if (arguments.empty() || arguments[0].tag != Tag::Tup) {
        runtime_fail("tup method requires a tuple receiver");
    }
    const TupleObject* source = as_tuple(arguments[0]);
    if (name == "size") {
        return make_int(static_cast<std::int64_t>(source->items.size()));
    }
    if (name == "get") {
        const Value index =
            arguments.size() > 1 ? arguments[1] : make_int(-1);
        const std::int64_t position =
            resolved_index(machine, index, source->items.size(), "tup");
        return copy_value(
            machine.arena,
            source->items[static_cast<std::size_t>(position)]);
    }
    if (name == "to_arr") {
        std::vector<Value> items;
        items.reserve(source->items.size());
        for (const Value& item : source->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        return make_array(
            machine.arena.allocate_array(std::move(items)));
    }
    if (name == "reverse") {
        std::vector<Value> items;
        items.reserve(source->items.size());
        for (const Value& item : source->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        std::reverse(items.begin(), items.end());
        return make_tuple(
            machine.arena.allocate_tuple(std::move(items)));
    }
    if (name == "add") {
        if (arguments.size() < 2 || arguments[1].tag != Tag::Tup) {
            runtime_fail("tup.add requires a tuple");
        }
        std::vector<Value> items;
        items.reserve(
            source->items.size() + as_tuple(arguments[1])->items.size());
        for (const Value& item : source->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        for (const Value& item : as_tuple(arguments[1])->items) {
            items.push_back(copy_value(machine.arena, item));
        }
        return make_tuple(
            machine.arena.allocate_tuple(std::move(items)));
    }
    runtime_fail("unknown tup method: " + name);
}

Value char_method(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& arguments) {
    if (arguments.empty() || arguments[0].tag != Tag::Char) {
        runtime_fail("char method requires a char receiver");
    }
    const char32_t value = arguments[0].c;
    if (name == "code") {
        return make_int(static_cast<std::int64_t>(value));
    }
    if (name == "to_str") {
        std::u32string text(1, value);
        return make_string(machine.arena.allocate_string(std::move(text)));
    }
    if (name == "is_digit") {
        return make_bool(char_is_digit(value));
    }
    if (name == "is_alpha") {
        return make_bool(char_is_alpha(value));
    }
    if (name == "is_alnum") {
        return make_bool(char_is_digit(value) || char_is_alpha(value));
    }
    if (name == "is_space") {
        return make_bool(char_is_space(value));
    }
    if (name == "is_upper") {
        return make_bool(char_is_upper(value));
    }
    if (name == "is_lower") {
        return make_bool(char_is_lower(value));
    }
    if (name == "is_ascii") {
        return make_bool(char_is_ascii(value));
    }
    runtime_fail("unknown char method: " + name);
}

TaskObject* require_task_value(
    Machine& machine,
    const Value& value,
    const std::string& where) {
    if (!is_task(value)) {
        throw_error(make_error(
            machine.arena, "TYPE", "builtin: " + where,
            "expected a task value",
            {"but " + runtime_type_name(value) + " was encountered"}));
    }
    return as_task(value);
}

bool file_mode_valid(const std::string& mode) {
    return mode == "read" || mode == "write" || mode == "append"
        || mode == "write+" || mode == "append+";
}

bool file_mode_readable(const std::string& mode) {
    return mode == "read" || mode == "write+" || mode == "append+";
}

bool file_mode_writable(const std::string& mode) {
    return mode == "write" || mode == "append"
        || mode == "write+" || mode == "append+";
}

std::ios::openmode file_open_mode(const std::string& mode) {
    if (mode == "read") {
        return std::ios::in;
    }
    if (mode == "write") {
        return std::ios::out | std::ios::trunc;
    }
    if (mode == "append") {
        return std::ios::out | std::ios::app;
    }
    if (mode == "write+") {
        return std::ios::in | std::ios::out | std::ios::trunc;
    }
    return std::ios::in | std::ios::out | std::ios::app;
}

Value open_file_value(
    Machine& machine,
    const std::string& path,
    const std::string& mode) {
    if (!file_mode_valid(mode)) {
        throw_error(make_error(
            machine.arena, "VALUE", "builtin: open, mode",
            "Invalid mode: " + mode,
            {"valid modes are: read, write, append, write+, append+"}));
    }
    FileStream stream;
    stream.stream = std::make_unique<std::fstream>();
    stream.stream->open(path, file_open_mode(mode));
    if (!stream.stream->is_open()) {
        return make_bool(false);
    }
    stream.mode = mode;
    machine.files[path] = std::move(stream);
    return make_bool(true);
}

FileStream* find_file_stream(Machine& machine, const std::string& path) {
    const auto found = machine.files.find(path);
    return found == machine.files.end() ? nullptr : &found->second;
}

Value read_file_value(Machine& machine, const std::string& path) {
    FileStream* stream = find_file_stream(machine, path);
    if (stream == nullptr) {
        throw_error(make_error(
            machine.arena, "VALUE", "builtin: read",
            "File is not opened: " + path));
    }
    if (!file_mode_readable(stream->mode)) {
        throw_error(make_error(
            machine.arena, "LOGIC", "builtin: read",
            "File must be in a readable mode to read",
            {"file is in the " + stream->mode}));
    }
    std::ostringstream text;
    text << stream->stream->rdbuf();
    return string_from_utf8(machine, text.str());
}

Value write_file_value(
    Machine& machine,
    const std::string& path,
    const std::vector<Value>& lines) {
    FileStream* stream = find_file_stream(machine, path);
    if (stream == nullptr) {
        throw_error(make_error(
            machine.arena, "VALUE", "builtin: write",
            "File is not opened: " + path));
    }
    if (!file_mode_writable(stream->mode)) {
        throw_error(make_error(
            machine.arena, "LOGIC", "builtin: write",
            "File must be in a writable mode to write",
            {"file is in the " + stream->mode}));
    }
    for (const Value& line : lines) {
        if (line.tag == Tag::Str) {
            *stream->stream << as_string_const(line)->utf8;
        } else {
            *stream->stream << format_value(line);
        }
    }
    stream->stream->flush();
    return make_bool(true);
}

Value close_file_value(Machine& machine, const std::string& path) {
    const auto found = machine.files.find(path);
    if (found == machine.files.end()) {
        throw_error(make_error(
            machine.arena, "VALUE", "builtin: close",
            "File is not opened: " + path));
    }
    if (found->second.stream != nullptr) {
        found->second.stream->close();
    }
    machine.files.erase(found);
    return make_bool(true);
}

Value file_method(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& positional) {
    if (positional.empty()) {
        throw RuntimeError("file method requires a receiver");
    }
    const Value receiver = positional[0];
    std::string path;
    if (receiver.tag == Tag::Str) {
        path = as_string_const(receiver)->utf8;
    } else if (is_file(receiver)) {
        path = as_file(receiver)->path;
    } else {
        throw_error(error_type_match(
            machine.arena, "native method: file",
            "file or str", runtime_type_name(receiver)));
    }
    if (name == "open") {
        std::string mode = "read";
        if (positional.size() > 1) {
            if (positional[1].tag != Tag::Str) {
                throw_error(error_type_match(
                    machine.arena, "native method: file",
                    "str", runtime_type_name(positional[1])));
            }
            mode = as_string_const(positional[1])->utf8;
        }
        const Value opened = open_file_value(machine, path, mode);
        if (!opened.b) {
            return opened;
        }
        return make_file(machine.arena.allocate_file(path, mode));
    }
    if (name == "read") {
        return read_file_value(machine, path);
    }
    if (name == "write") {
        if (positional.size() < 2) {
            throw_error(error_argument(
                machine.arena, "native method: file.write",
                "not enought arguments"));
        }
        return write_file_value(
            machine, path, {positional[1]});
    }
    if (name == "close") {
        return close_file_value(machine, path);
    }
    throw_error(error_identifier_not_found(
        machine.arena, "native method", "file." + name));
}

Value task_method(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& positional) {
    if (positional.empty() || !is_task(positional[0])) {
        throw_error(error_type_match(
            machine.arena, "native method",
            "task",
            positional.empty() ? "nova" : runtime_type_name(positional[0])));
    }
    TaskObject* task = as_task(positional[0]);
    if (name == "wait") {
        return await_task(
            machine, task,
            task->kind == TaskObject::Kind::Lazy ? "await" : "wait");
    }
    if (name == "cancel") {
        cancel_task(machine, task);
        return make_nova();
    }
    if (name == "status") {
        return string_from_utf8(
            machine, task_status_name(task->status));
    }
    throw_error(error_identifier_not_found(
        machine.arena, "native method", "task." + name));
}

Value call_native_method(
    Machine& machine,
    const CallSite& site,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named) {
    if (!named.empty()) {
        runtime_fail(
            "named arguments are not supported for native methods");
    }
    if (positional.empty()) {
        runtime_fail("missing receiver argument");
    }
    std::vector<Value> resolved;
    const std::vector<Value>* values = &positional;
    const bool receiver_reference = is_reference(positional[0]);
    if (receiver_reference) {
        resolved = positional;
        resolved[0] = unwrap_reference(machine, positional[0]);
        values = &resolved;
    }
    const std::string type = site.native_type.has_value()
        ? *site.native_type
        : runtime_type_name((*values)[0]);
    if (type == "arr") {
        const Value result = array_method(machine, site.name, *values);
        if (receiver_reference && result.tag == Tag::Arr) {
            reference_set(
                machine, as_reference(positional[0]), result);
            return positional[0];
        }
        return result;
    }
    if (type == "str") {
        return string_method(machine, site.name, *values);
    }
    if (type == "map") {
        return map_method(machine, site.name, *values);
    }
    if (type == "set") {
        return set_method(machine, site.name, *values);
    }
    if (type == "tup") {
        return tuple_method(machine, site.name, *values);
    }
    if (type == "char") {
        return char_method(machine, site.name, *values);
    }
    if (type == "task") {
        return task_method(machine, site.name, *values);
    }
    if (type == "file") {
        return file_method(machine, site.name, *values);
    }
    runtime_fail("native method type not implemented: " + type);
}

const char* export_kind_name(ExportEntry::Kind kind) {
    switch (kind) {
        case ExportEntry::Kind::Variable: return "variable";
        case ExportEntry::Kind::Function: return "function";
        case ExportEntry::Kind::Type: return "type";
    }
    return "variable";
}

void reset_module_runtime(ModuleRuntime& module) {
    module.globals.clear();
    module.declared_globals.clear();
    module.functions.clear();
    module.types.clear();
    module.traits.clear();
    module.aliases.clear();
    module.wildcard_values.clear();
    module.wildcard_functions.clear();
    module.wildcard_types.clear();
    module.wildcard_sources.clear();
    module.exports.clear();
    module.init = ModuleRuntime::Init::New;
}

void build_export_table(
    ModuleRuntime& module, Machine& machine, bool is_entry) {
    if (module.image == nullptr) {
        return;
    }
    const std::uint32_t image_module = module.bundle != nullptr
        ? module.bundle->image_module_index
        : module.image->entry_module;
    if (image_module >= module.image->modules.size()) {
        throw RuntimeError("module image index is out of range");
    }
    const ModuleInfo& info = module.image->modules[image_module];
    module.exports.clear();
    if (info.exports.empty()) {
        module.legacy = !is_entry;
        if (is_entry) {
            return;
        }
        if (!module.warned) {
            module.warned = true;
            machine.host.write_error(
                "[MODULE WARNING] module '" + module.name
                + "' declares no exports; exporting all top-level names\n");
        }
        for (const auto& [name, value] : module.globals) {
            if (name.empty() || name.front() == '#') {
                continue;
            }
            if (module.functions.count(name) != 0
                || module.types.count(name) != 0) {
                continue;
            }
            ExportEntry entry;
            entry.kind = ExportEntry::Kind::Variable;
            entry.value = value;
            module.exports.emplace(name, std::move(entry));
        }
        for (const auto& [name, overloads] : module.functions) {
            ExportEntry entry;
            entry.kind = ExportEntry::Kind::Function;
            entry.functions = overloads;
            module.exports.emplace(name, std::move(entry));
        }
        for (auto& [name, type] : module.types) {
            ExportEntry entry;
            entry.kind = ExportEntry::Kind::Type;
            entry.type = &type;
            module.exports.emplace(name, std::move(entry));
        }
        return;
    }
    module.legacy = false;
    for (const auto& [name, kind] : info.exports) {
        auto existing = module.exports.find(name);
        if (existing != module.exports.end()) {
            const bool both_functions =
                existing->second.kind == ExportEntry::Kind::Function
                && kind == "function";
            if (!both_functions) {
                throw_error(error_module(
                    machine.arena, "module: " + module.path,
                    "Duplicate export: " + name,
                    {
                        std::string("already exported as ")
                            + export_kind_name(existing->second.kind),
                        "then exported again as " + kind,
                    }));
            }
            continue;
        }
        ExportEntry entry;
        const auto functions = module.functions.find(name);
        if (functions != module.functions.end()) {
            entry.kind = ExportEntry::Kind::Function;
            entry.functions = functions->second;
        } else {
            const auto type = module.types.find(name);
            if (type != module.types.end()) {
                entry.kind = ExportEntry::Kind::Type;
                entry.type = &type->second;
            } else {
                const auto global = module.globals.find(name);
                if (global == module.globals.end()) {
                    throw_error(error_module(
                        machine.arena, "module: " + module.path,
                        "Exported name was not declared: " + name));
                }
                entry.kind = ExportEntry::Kind::Variable;
                entry.value = global->second;
            }
        }
        module.exports.emplace(name, std::move(entry));
    }
}

Value project_member_value(
    Machine& machine,
    ProjectObject* project,
    const std::string& name) {
    if (project == nullptr) {
        throw RuntimeError("null project value");
    }
    auto strings = [&](const std::vector<std::string>& items) {
        std::vector<Value> values;
        values.reserve(items.size());
        for (const std::string& item : items) {
            values.push_back(string_from_utf8(machine, item));
        }
        return make_array(
            machine.arena.allocate_array(std::move(values)));
    };
    if (name == "modules") {
        return strings(project->module_names);
    }
    if (name == "paths") {
        return strings(project->paths);
    }
    if (name == "logLevel") {
        return string_from_utf8(machine, project->log_level);
    }
    if (name == "allowSystem") {
        return make_bool(project->allow_system);
    }
    if (name == "engine") {
        return string_from_utf8(machine, project->engine);
    }
    throw_error(error_identifier_not_found(
        machine.arena, "access expression", name,
        {"fields: modules, paths, logLevel, allowSystem, engine"}));
}

Value call_extern_function(
    Machine& machine,
    Frame& frame,
    const std::string& name,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named) {
    const auto found = frame.module->externs.find(name);
    if (found == frame.module->externs.end()) {
        throw_error(error_identifier_not_found(
            machine.arena, "extern", name));
    }
    return call_extern_descriptor(
        machine, found->second, name, positional, named);
}

Value call_extern_descriptor(
    Machine& machine,
    const MetaDescriptor& descriptor,
    const std::string& name,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named) {
    if (!named.empty()) {
        throw_error(error_argument(
            machine.arena, "extern call",
            "Named arguments are not supported for external functions"));
    }
    if (positional.size() < descriptor.min_argc) {
        throw_error(error_argument(
            machine.arena, "extern call", "not enought arguments"));
    }
    const bool variadic = !descriptor.parameters.empty()
        && (descriptor.parameters.back().flags & 4) != 0;
    if (!variadic
        && positional.size() > descriptor.parameters.size()) {
        throw_error(error_argument(
            machine.arena, "extern call", "too many arguments"));
    }
    Value result;
    try {
        result = machine.host.call_extern(
            descriptor.python_target,
            positional.data(), positional.size(), machine.arena);
    } catch (const std::runtime_error& error) {
        throw_error(error_development(
            machine.arena, "extern function: " + name,
            error.what(), {"extern '" + name + "'"}));
    }
    if (is_error(result)) {
        throw_error(as_error(result));
    }
    return result;
}

Value module_member_value(
    Machine& machine,
    ModuleRuntime& module,
    const std::string& name,
    const std::string& where) {
    if (module.init != ModuleRuntime::Init::Ready) {
        initialize_module(module, machine);
    }
    const auto found = module.exports.find(name);
    if (found == module.exports.end()) {
        throw_error(error_identifier_not_found(
            machine.arena, where, name,
            {"module '" + module.name + "' has no exported member '"
                 + name + "'"}));
    }
    const ExportEntry& entry = found->second;
    if (entry.kind == ExportEntry::Kind::Function) {
        if (entry.functions.size() == 1) {
            return make_function(entry.functions.front());
        }
        std::vector<Value> values;
        values.reserve(entry.functions.size());
        for (FunctionObject* function : entry.functions) {
            values.push_back(make_function(function));
        }
        return make_array(machine.arena.allocate_array(std::move(values)));
    }
    if (entry.kind == ExportEntry::Kind::Type) {
        return make_type(entry.type);
    }
    return entry.value;
}

Value call_module_member(
    Machine& machine,
    const CallSite& site,
    ModuleRuntime& module,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named,
    const std::string& where) {
    if (!named.empty()) {
        throw_error(error_argument(
            machine.arena, where,
            "Named arguments are not supported for module members"));
    }
    if (module.init != ModuleRuntime::Init::Ready) {
        initialize_module(module, machine);
    }
    const auto found = module.exports.find(site.name);
    if (found == module.exports.end()) {
        throw_error(error_identifier_not_found(
            machine.arena, where, site.name,
            {"module '" + module.name + "' has no exported member '"
                 + site.name + "'"}));
    }
    const ExportEntry& entry = found->second;
    if (entry.kind == ExportEntry::Kind::Function) {
        if (entry.functions.empty()) {
            throw_error(error_identifier_not_found(
                machine.arena, where, site.name));
        }
        if (module.meta == nullptr) {
            throw RuntimeError("module member metadata is required");
        }
        FunctionObject* function =
            select_overload(entry.functions, positional, *module.meta);
        return invoke_function(
            machine, function, positional, {},
            where.empty() ? site.name : where, nullptr, site.name);
    }
    const Value member = entry.value;
    if (is_function(member)) {
        return invoke_function(
            machine, as_function(member), positional, {}, where,
            nullptr, site.name);
    }
    throw_error(error_module(
        machine.arena, where, "Module member is not callable",
        {"member '" + site.name + "' of module '" + module.name
             + "' is a " + tag_name(member.tag)}));
}

bool resolve_pending_call(
    Machine& machine,
    Frame& frame,
    const CallSite& site,
    const std::vector<Value>& positional,
    const Value* target,
    FunctionObject*& function,
    Value& receiver,
    bool& has_receiver,
    std::string& where,
    std::string& frame_name) {
    const std::string& dispatch = site.dispatch;
    const bool spawn = dispatch == "spawn"
        || dispatch == "spawn_static";
    const bool identifier = dispatch == "call"
        || (dispatch == "spawn" && target == nullptr);
    if (identifier) {
        const std::vector<FunctionObject*>* candidates = nullptr;
        if (frame.function != nullptr) {
            const auto found =
                frame.function->captured.functions.find(site.name);
            if (found != frame.function->captured.functions.end()) {
                candidates = &found->second;
            }
        }
        if (candidates == nullptr) {
            const auto found =
                frame.module->functions.find(site.name);
            if (found != frame.module->functions.end()) {
                candidates = &found->second;
            }
        }
        if (candidates != nullptr && !candidates->empty()) {
            const Meta& meta =
                candidates->front()->module != nullptr
                && candidates->front()->module->meta != nullptr
                ? *candidates->front()->module->meta
                : *frame.module->meta;
            function = select_overload(*candidates, positional, meta);
            where = "call: " + site.name;
            frame_name = site.name;
            return true;
        }
        Value value;
        if (try_resolve_name(machine, frame, site.name, value)
            && is_function(value)) {
            function = as_function(value);
            where = "call: " + site.name;
            frame_name = site.name;
            return true;
        }
        return false;
    }
    if (dispatch == "value") {
        if (target == nullptr || !is_function(*target)) {
            return false;
        }
        function = as_function(*target);
        where = "call expression";
        return true;
    }
    if (dispatch == "module"
        || (spawn && target != nullptr && is_module(*target))) {
        if (target == nullptr || !is_module(*target)) {
            return false;
        }
        ModuleRuntime* module = as_module(*target);
        const auto found = module->exports.find(site.name);
        if (found == module->exports.end()
            || found->second.kind != ExportEntry::Kind::Function) {
            return false;
        }
        function = select_overload(
            found->second.functions, positional, *module->meta);
        where = "module: " + module->name;
        frame_name = site.name;
        return true;
    }
    if (dispatch == "method"
        && target != nullptr && is_module(*target)) {
        ModuleRuntime* module = as_module(*target);
        const auto found = module->exports.find(site.name);
        if (found == module->exports.end()
            || found->second.kind != ExportEntry::Kind::Function) {
            return false;
        }
        function = select_overload(
            found->second.functions, positional, *module->meta);
        where = "module: " + module->name;
        frame_name = site.name;
        return true;
    }
    if (dispatch == "method"
        || (spawn && target != nullptr && target->tag == Tag::Obj)) {
        if (target == nullptr || target->tag != Tag::Obj) {
            return false;
        }
        receiver = *target;
        has_receiver = true;
        ObjectObject* object = as_object(*target);
        TypeRuntime* type = object->type;
        if (type == nullptr) {
            const auto found =
                frame.module->types.find(object->type_name);
            if (found != frame.module->types.end()) {
                type = &found->second;
            }
        }
        if (type == nullptr) {
            return false;
        }
        const std::vector<FunctionObject*>* candidates = nullptr;
        const auto direct = type->methods.find(site.name);
        if (direct != type->methods.end() && !direct->second.empty()) {
            candidates = &direct->second;
        }
        if (candidates == nullptr && frame.function != nullptr
            && !frame.function->trait_qualifier.empty()) {
            const auto trait = type->trait_methods.find(
                frame.function->trait_qualifier);
            if (trait != type->trait_methods.end()) {
                const auto found = trait->second.find(site.name);
                if (found != trait->second.end()) {
                    candidates = &found->second;
                }
            }
        }
        if (candidates == nullptr) {
            for (const auto& entry : type->trait_methods) {
                const auto found = entry.second.find(site.name);
                if (found != entry.second.end()) {
                    candidates = &found->second;
                    break;
                }
            }
        }
        if (candidates == nullptr && site.trait_name.has_value()) {
            const auto trait =
                type->trait_methods.find(*site.trait_name);
            if (trait != type->trait_methods.end()) {
                const auto found = trait->second.find(site.name);
                if (found != trait->second.end()) {
                    candidates = &found->second;
                }
            }
        }
        if (candidates == nullptr && type->module != nullptr) {
            for (const auto& entry : type->module->traits) {
                const auto found = entry.second.defaults.find(site.name);
                if (found != entry.second.defaults.end()) {
                    candidates = &found->second;
                    break;
                }
            }
        }
        if (candidates == nullptr) {
            for (const auto& entry : frame.module->traits) {
                const auto found = entry.second.defaults.find(site.name);
                if (found != entry.second.defaults.end()) {
                    candidates = &found->second;
                    break;
                }
            }
        }
        if (candidates == nullptr || candidates->empty()) {
            return false;
        }
        const Meta& meta = type->module != nullptr
            && type->module->meta != nullptr
            ? *type->module->meta : *frame.module->meta;
        function = select_overload(*candidates, positional, meta);
        where = "method call: " + site.name;
        frame_name = runtime_type_name(*target) + "." + site.name;
        return true;
    }
    if (dispatch == "static" || dispatch == "spawn_static") {
        if (!site.type_name.has_value()) {
            return false;
        }
        TypeRuntime* type = resolve_qualified_type(
            machine, frame, *site.type_name,
            "method call: " + *site.type_name);
        if (type == nullptr) {
            return false;
        }
        const auto found = type->statics.find(site.name);
        if (found == type->statics.end() || found->second.empty()) {
            return false;
        }
        const Meta& meta = type->module != nullptr
            && type->module->meta != nullptr
            ? *type->module->meta : *frame.module->meta;
        function = select_overload(found->second, positional, meta);
        where = "method call: " + *site.type_name + "." + site.name;
        frame_name = *site.type_name + "." + site.name;
        return true;
    }
    return false;
}

void import_wildcard(
    ModuleRuntime& target, Frame& frame, Machine& machine) {
    for (const auto& [name, entry] : target.exports) {
        std::string collision_kind;
        std::string collision_source;
        const auto source = frame.module->wildcard_sources.find(name);
        if (frame.module->functions.count(name) != 0) {
            collision_kind = "function";
            if (source != frame.module->wildcard_sources.end()) {
                collision_source = source->second;
            }
        } else if (frame.module->globals.count(name) != 0
                   || frame.module->wildcard_values.count(name) != 0) {
            collision_kind = "variable";
            if (source != frame.module->wildcard_sources.end()) {
                collision_source = source->second;
            }
        } else if (frame.module->types.count(name) != 0
                   || frame.module->wildcard_types.count(name) != 0) {
            collision_kind = "type";
            if (source != frame.module->wildcard_sources.end()) {
                collision_source = source->second;
            }
        }
        if (!collision_kind.empty()) {
            const std::string other = collision_source.empty()
                ? "an existing " + collision_kind + " declaration"
                : "module '" + collision_source + "'";
            throw_error(error_module(
                machine.arena, "use expression",
                "Import collision for '" + name + "'",
                {
                    "imported from module '" + target.name + "'",
                    "already provided by " + other,
                }));
        }
        if (entry.kind == ExportEntry::Kind::Function) {
            frame.module->wildcard_functions[name] = entry.functions;
            frame.module->wildcard_sources[name] = target.name;
        } else if (entry.kind == ExportEntry::Kind::Type) {
            frame.module->wildcard_types[name] = entry.type;
            frame.module->wildcard_sources[name] = target.name;
        } else {
            frame.module->wildcard_values[name] = entry.value;
            if (frame.is_module) {
                frame.module->globals[name] = entry.value;
            }
            frame.module->wildcard_sources[name] = target.name;
        }
    }
}

TypeRuntime* resolve_qualified_type(
    Machine& machine,
    Frame& frame,
    const std::string& qualified,
    const std::string& where) {
    const std::size_t dot = qualified.find('.');
    if (dot == std::string::npos) {
        const auto direct = frame.module->types.find(qualified);
        if (direct != frame.module->types.end()) {
            return &direct->second;
        }
        const auto wildcard =
            frame.module->wildcard_types.find(qualified);
        if (wildcard != frame.module->wildcard_types.end()) {
            return wildcard->second;
        }
        return nullptr;
    }
    const std::string qualifier = qualified.substr(0, dot);
    const std::string member = qualified.substr(dot + 1);
    Value value;
    if (!try_resolve_name(machine, frame, qualifier, value)
        || !is_module(value)) {
        throw_error(error_identifier_not_found(
            machine.arena, where, qualifier,
            {"expected a module alias"}));
    }
    ModuleRuntime* target = as_module(value);
    if (target == nullptr) {
        throw_error(error_identifier_not_found(
            machine.arena, where, qualifier));
    }
    if (target->init != ModuleRuntime::Init::Ready) {
        initialize_module(*target, machine);
    }
    const auto direct = target->types.find(member);
    if (direct != target->types.end()) {
        return &direct->second;
    }
    const auto wildcard = target->wildcard_types.find(member);
    if (wildcard != target->wildcard_types.end()) {
        return wildcard->second;
    }
    return nullptr;
}

void initialize_module(ModuleRuntime& module, Machine& machine) {
    if (module.init == ModuleRuntime::Init::Ready) {
        return;
    }
    if (module.init == ModuleRuntime::Init::Initializing) {
        std::vector<std::string> chain;
        bool found = false;
        for (ModuleRuntime* active : machine.module_stack) {
            if (active == &module) {
                found = true;
            }
            if (found) {
                chain.push_back(active->path);
            }
        }
        chain.push_back(module.path);
        ErrorObject* error = error_module(
            machine.arena, "module: " + module.path,
            "Cyclic module import", chain);
        error->is_module_error = true;
        throw_error(error);
    }
    if (module.init == ModuleRuntime::Init::Failed) {
        reset_module_runtime(module);
    }
    if (module.image == nullptr) {
        ErrorObject* error = make_error(
            machine.arena,
            module.deferred_error_kind.empty()
                ? "MODULE" : module.deferred_error_kind,
            "module: " + module.path,
            module.deferred_error_message);
        if (!module.deferred_error_text.empty()) {
            error->text_override = module.deferred_error_text;
            error->has_text_override = true;
        }
        error->is_module_error = true;
        throw_error(error);
    }
    const bool is_entry = machine.bundle != nullptr
        && module.module_id == machine.bundle->entry_module;
    const std::uint32_t image_module = module.bundle != nullptr
        ? module.bundle->image_module_index
        : module.image->entry_module;
    if (image_module >= module.image->modules.size()) {
        throw RuntimeError("module image index is out of range");
    }
    const ModuleInfo& info = module.image->modules[image_module];
    if (info.code_index >= module.image->codes.size()) {
        throw RuntimeError("module code index is out of range");
    }
    module.init = ModuleRuntime::Init::Initializing;
    machine.module_stack.push_back(&module);
    bool frame_pushed = false;
    try {
        const CodeObject& code =
            module.image->codes[info.code_index];
        Frame frame = make_frame(code, module, nullptr, true, false);
        if (module.bind_project && machine.has_project) {
            module.globals["project"] =
                make_project(&machine.project);
            module.declared_globals.insert("project");
        }
        machine.module_frames.push_back(&frame);
        frame_pushed = true;
        (void)execute(frame, machine);
        machine.module_frames.pop_back();
        frame_pushed = false;
        build_export_table(module, machine, is_entry);
        module.init = ModuleRuntime::Init::Ready;
    } catch (const UnwindSignal& signal) {
        if (frame_pushed) {
            machine.module_frames.pop_back();
        }
        machine.module_stack.pop_back();
        reset_module_runtime(module);
        if (!is_entry && signal.error != nullptr
            && !signal.error->is_module_error) {
            ErrorObject* wrapped = make_error(
                machine.arena, "MODULE", "module: " + module.path,
                "Module failed to load", {signal.error->text()});
            wrapped->cause = signal.error;
            wrapped->is_module_error = true;
            throw_error(wrapped);
        }
        throw;
    } catch (...) {
        if (frame_pushed) {
            machine.module_frames.pop_back();
        }
        machine.module_stack.pop_back();
        reset_module_runtime(module);
        throw;
    }
    machine.module_stack.pop_back();
}

Value error_property_value(
    Machine& machine, ErrorObject* error, const std::string& name) {
    if (error == nullptr) {
        return make_nova();
    }
    if (name == "kind") {
        return string_from_utf8(machine, error->kind);
    }
    if (name == "message") {
        return string_from_utf8(machine, error->message);
    }
    if (name == "details") {
        std::vector<Value> values;
        values.reserve(error->details.size());
        for (const std::string& detail : error->details) {
            values.push_back(string_from_utf8(machine, detail));
        }
        return make_array(machine.arena.allocate_array(std::move(values)));
    }
    if (name == "where") {
        if (error->where.empty()) {
            return make_nova();
        }
        return string_from_utf8(machine, error->where);
    }
    if (name == "line") {
        return error->line > 0 ? make_int(error->line) : make_nova();
    }
    if (name == "column") {
        return error->column > 0 ? make_int(error->column) : make_nova();
    }
    if (name == "cause") {
        return error->cause != nullptr
            ? make_error_value(error->cause) : make_nova();
    }
    if (name == "frames") {
        std::vector<Value> values;
        values.reserve(error->frames.size());
        for (const FrameRecord& frame : error->frames) {
            values.push_back(string_from_utf8(machine, frame.render()));
        }
        return make_array(machine.arena.allocate_array(std::move(values)));
    }
    throw_error(error_identifier_not_found(
        machine.arena, "error property", name,
        {"error values expose: kind, message, details, where, line, "
         "column, cause"}));
}

Value load_object_member(
    Machine& machine,
    Frame& frame,
    const Value& owner,
    const std::string& name,
    bool safe,
    bool allow_methods) {
    if (owner.tag == Tag::Module) {
        ModuleRuntime* module = as_module(owner);
        if (module == nullptr) {
            runtime_fail("null module value");
        }
        return module_member_value(
            machine, *module, name, "access expression");
    }
    if (owner.tag == Tag::Type) {
        TypeRuntime* runtime = as_type(owner);
        if (runtime == nullptr || runtime->info == nullptr) {
            runtime_fail("null type value");
        }
        if (runtime->info->kind == "enum") {
            for (const std::string& variant : runtime->info->variants) {
                if (variant == name) {
                    ObjectObject* object = machine.arena.allocate_object(
                        runtime->info->name, true, variant);
                    object->type = runtime;
                    object->module = runtime->module;
                    object->fields["name"] =
                        string_from_utf8(machine, variant);
                    return make_object(object);
                }
            }
        }
        const auto methods = runtime->statics.find(name);
        if (methods != runtime->statics.end() && !methods->second.empty()) {
            FunctionObject* source = methods->second.back();
            FunctionObject* bound = machine.arena.allocate_function(
                source->metadata);
            bound->module = source->module;
            bound->owner = source->owner;
            bound->is_static = true;
            bound->is_private = source->is_private;
            bound->trait_qualifier = source->trait_qualifier;
            bound->receiver = owner;
            bound->has_receiver = true;
            return make_function(bound);
        }
        if (safe) {
            return make_nova();
        }
        runtime_fail("type has no static member '" + name + "'");
    }
    if (owner.tag == Tag::Error) {
        return error_property_value(machine, as_error(owner), name);
    }
    if (owner.tag == Tag::Project) {
        return project_member_value(machine, as_project(owner), name);
    }
    if (owner.tag == Tag::Map) {
        const Value key = string_from_utf8(machine, name);
        const Value* found = map_get(*as_map(owner), key);
        if (found != nullptr) {
            return *found;
        }
        if (safe) {
            return make_nova();
        }
        runtime_fail("map has no member '" + name + "'");
    }
    if (owner.tag != Tag::Obj) {
        if (safe) {
            return make_nova();
        }
        runtime_fail("member access requires an object value");
    }
    ObjectObject* object = as_object(owner);
    const auto field = object->fields.find(name);
    if (field != object->fields.end()) {
        if (object->private_fields.count(name) != 0
            && !private_access_allowed(machine, frame, *object)) {
            runtime_fail("private member: " + name);
        }
        return field->second;
    }
    if (!allow_methods) {
        if (safe) {
            return make_nova();
        }
        runtime_fail("object has no field '" + name + "'");
    }
    const TypeRuntime* type = object->type;
    if (type == nullptr) {
        const auto type_it =
            frame.module->types.find(object->type_name);
        if (type_it != frame.module->types.end()) {
            type = &type_it->second;
        }
    }
    if (type != nullptr) {
        const auto methods = type->methods.find(name);
        if (methods != type->methods.end() && !methods->second.empty()) {
            FunctionObject* source = methods->second.back();
            if (source->is_private
                && !private_access_allowed(machine, frame, *object)) {
                runtime_fail("private method: " + name);
            }
            FunctionObject* bound = machine.arena.allocate_function(
                source->metadata);
            bound->module = source->module;
            bound->owner = source->owner;
            bound->is_static = false;
            bound->is_private = source->is_private;
            bound->trait_qualifier = source->trait_qualifier;
            bound->receiver = owner;
            bound->has_receiver = true;
            return make_function(bound);
        }
        if (type->module != nullptr) {
            for (const auto& entry : type->module->traits) {
                const auto defaults = entry.second.defaults.find(name);
                if (defaults != entry.second.defaults.end()
                    && !defaults->second.empty()) {
                    FunctionObject* source = defaults->second.back();
                    FunctionObject* bound = machine.arena.allocate_function(
                        source->metadata);
                    bound->module = source->module;
                    bound->owner = source->owner;
                    bound->is_static = false;
                    bound->is_private = source->is_private;
                    bound->trait_qualifier = source->trait_qualifier;
                    bound->receiver = owner;
                    bound->has_receiver = true;
                    return make_function(bound);
                }
            }
        }
    }
    if (safe) {
        return make_nova();
    }
    runtime_fail("object has no member '" + name + "'");
}

Value store_object_member(
    Machine& machine,
    Frame& frame,
    const Value& owner,
    const std::string& name,
    const Value& value) {
    if (owner.tag == Tag::Module) {
        ModuleRuntime* runtime = as_module(owner);
        throw_error(error_module(
            machine.arena, "member assignment", "Modules are immutable",
            {"cannot assign to '"
                 + (runtime != nullptr ? runtime->name
                                       : std::string("module"))
                 + "." + name + "'"}));
    }
    if (owner.tag == Tag::Project) {
        throw_error(make_error(
            machine.arena, "ASSIGN", "member assignment",
            "Project values are read only",
            {"cannot assign to 'project." + name + "'"}));
    }
    if (owner.tag != Tag::Obj) {
        runtime_fail("member assignment requires an object value");
    }
    ObjectObject* object = as_object(owner);
    if (object->structure_locked) {
        throw_error(error_const(
            machine.arena, "assignment", "object fields are locked",
            {"the object type ends with '!'"}));
    }
    const auto field = object->fields.find(name);
    if (field == object->fields.end()) {
        runtime_fail("object has no field '" + name + "'");
    }
    if (object->private_fields.count(name) != 0
        && !private_access_allowed(machine, frame, *object)) {
        runtime_fail("private member: " + name);
    }
    const Value stored = copy_value(machine.arena, value);
    field->second = stored;
    return stored;
}

bool object_satisfies_trait(
    Machine& machine,
    const ObjectObject& object,
    const TraitRuntime& trait) {
    (void)machine;
    if (trait.info == nullptr) {
        return false;
    }
    const TypeRuntime* type = object.type;
    if (type == nullptr && trait.module != nullptr) {
        const auto found =
            trait.module->types.find(object.type_name);
        if (found != trait.module->types.end()) {
            type = &found->second;
        }
    }
    if (type == nullptr) {
        return false;
    }
    for (const std::string& property : trait.info->properties) {
        bool found = object.fields.count(property) != 0;
        if (!found && type->info != nullptr) {
            for (const TypeProperty& info_property :
                 type->info->properties) {
                if (info_property.name == property) {
                    found = true;
                    break;
                }
            }
        }
        if (!found) {
            return false;
        }
    }
    for (const TraitMethod& method : trait.info->methods) {
        bool found = type->methods.count(method.name) != 0;
        if (!found) {
            const auto trait_methods =
                type->trait_methods.find(trait.info->name);
            if (trait_methods != type->trait_methods.end()
                && trait_methods->second.count(method.name) != 0) {
                found = true;
            }
        }
        if (!found) {
            const auto defaults = trait.defaults.find(method.name);
            if (defaults != trait.defaults.end()) {
                found = true;
            }
        }
        if (!found) {
            return false;
        }
    }
    return true;
}

Value call_type_method(
    Machine& machine,
    const Value& receiver,
    const std::string& name,
    const std::vector<Value>& arguments,
    const std::string& where) {
    if (receiver.tag != Tag::Obj) {
        runtime_fail(where + " requires an object receiver");
    }
    ObjectObject* object = as_object(receiver);
    TypeRuntime* type = object->type;
    if (type == nullptr) {
        runtime_fail("unknown type '" + object->type_name + "'");
    }
    const auto methods = type->methods.find(name);
    if (methods == type->methods.end() || methods->second.empty()) {
        runtime_fail("operator method not found: " + name);
    }
    ModuleRuntime* module = type->module != nullptr
        ? type->module : object->module;
    if (module == nullptr || module->meta == nullptr) {
        runtime_fail("operator method metadata is required");
    }
    FunctionObject* function = select_overload(
        methods->second, arguments, *module->meta);
    return call_function(
        machine, function, arguments, {}, where, &receiver,
        runtime_type_name(receiver) + "." + name);
}

Comparison compare_object_values(
    Machine& machine,
    const Value& left,
    const Value& right,
    const char* opcode) {
    if (left.tag == Tag::Obj && right.tag == Tag::Obj) {
        const ObjectObject* a = as_object(left);
        const ObjectObject* b = as_object(right);
        if (a->is_enum || b->is_enum) {
            return {false, value_equal(left, right) ? 0 : 1};
        }
        TypeRuntime* runtime = a->type;
        if (runtime != nullptr) {
            const auto methods = runtime->methods.find("compare");
            if (methods != runtime->methods.end()
                && !methods->second.empty()) {
                ModuleRuntime* module = runtime->module != nullptr
                    ? runtime->module : a->module;
                if (module == nullptr || module->meta == nullptr) {
                    runtime_fail("compare metadata is required");
                }
                FunctionObject* function = select_overload(
                    methods->second, {right}, *module->meta);
                const Value result = call_function(
                    machine, function, {right}, {},
                    "operator compare", &left,
                    runtime_type_name(left) + ".compare");
                const std::int64_t order =
                    value_as_int(result, "compare");
                return {
                    false,
                    order < 0 ? -1 : (order > 0 ? 1 : 0)};
            }
        }
        return {false, left.ref == right.ref ? 0 : 1};
    }
    const std::string operation(opcode);
    if (operation == "EQ" || operation == "NEQ") {
        return {false, left.ref == right.ref ? 0 : 1};
    }
    runtime_fail("ordering is not supported for object values");
}

std::string deep_type_name(const Value& value) {
    if (value.tag == Tag::Arr) {
        std::vector<std::string> names;
        for (const Value& item : as_array(value)->items) {
            const std::string name = deep_type_name(item);
            bool seen = false;
            for (const std::string& existing : names) {
                if (existing == name) {
                    seen = true;
                    break;
                }
            }
            if (!seen) {
                names.push_back(name);
            }
        }
        if (names.empty()) {
            return "arr[any]";
        }
        std::string joined;
        for (std::size_t index = 0; index < names.size(); ++index) {
            if (index != 0) {
                joined += " | ";
            }
            joined += names[index];
        }
        return "arr[" + joined + "]";
    }
    if (value.tag == Tag::Tup) {
        const std::vector<Value>& items = as_tuple(value)->items;
        if (items.empty()) {
            return "tup";
        }
        std::string joined;
        for (std::size_t index = 0; index < items.size(); ++index) {
            if (index != 0) {
                joined += ", ";
            }
            joined += deep_type_name(items[index]);
        }
        return "tup[" + joined + "]";
    }
    if (value.tag == Tag::Set) {
        std::vector<std::string> names;
        for (const Value& item : as_set(value)->items) {
            const std::string name = deep_type_name(item);
            bool seen = false;
            for (const std::string& existing : names) {
                if (existing == name) {
                    seen = true;
                    break;
                }
            }
            if (!seen) {
                names.push_back(name);
            }
        }
        if (names.empty()) {
            return "set[any]";
        }
        std::string joined;
        for (std::size_t index = 0; index < names.size(); ++index) {
            if (index != 0) {
                joined += " | ";
            }
            joined += names[index];
        }
        return "set[" + joined + "]";
    }
    if (value.tag == Tag::Fun) {
        const FunctionObject* function = as_function(value);
        if (function != nullptr && function->metadata != nullptr
            && !function->metadata->function_type.empty()) {
            return function->metadata->function_type;
        }
        return "function";
    }
    return runtime_type_name(value);
}

Value call_builtin(
    Machine& machine,
    const std::string& name,
    const std::vector<Value>& positional,
    const std::vector<std::pair<std::string, Value>>& named) {
    if (!named.empty()) {
        runtime_fail(
            "named arguments are not supported for builtin '" + name + "'");
    }
    if (name == "print" || name == "println") {
        if (name == "print" && positional.empty()) {
            runtime_fail(
                "print received too few arguments: expected at least 1, "
                "got 0");
        }
        std::string text;
        for (const Value& value : positional) {
            text += format_value(value);
        }
        if (name == "println") {
            text.push_back('\n');
        }
        machine.host.write(text);
        return make_int(static_cast<std::int64_t>(positional.size()));
    }
    if (name == "size") {
        return builtin_size_all(machine, positional);
    }
    if (name == "chr") {
        if (positional.size() != 1) {
            runtime_fail("chr expects one argument");
        }
        const std::int64_t code =
            value_as_int(positional[0], "chr");
        if (code < 0 || code > 0x10FFFF
            || (code >= 0xD800 && code <= 0xDFFF)) {
            runtime_fail("chr received an invalid Unicode scalar value");
        }
        return make_char(static_cast<char32_t>(code));
    }
    if (name == "ord") {
        if (positional.size() != 1) {
            runtime_fail("ord expects one argument");
        }
        return make_int(static_cast<std::int64_t>(
            character_value(positional[0], "ord")));
    }
    if (name == "digit_value") {
        if (positional.size() != 1) {
            runtime_fail("digit_value expects one argument");
        }
        const char32_t value =
            character_value(positional[0], "digit_value");
        return make_int(
            char_is_digit(value)
                ? static_cast<std::int64_t>(value - U'0')
                : static_cast<std::int64_t>(-1));
    }
    if (name == "is_digit" || name == "is_alpha" || name == "is_alnum"
        || name == "is_space" || name == "is_upper" || name == "is_lower"
        || name == "is_ascii") {
        if (positional.size() != 1) {
            runtime_fail(name + " expects one argument");
        }
        const char32_t value =
            character_value(positional[0], name.c_str());
        bool result = false;
        if (name == "is_digit") {
            result = char_is_digit(value);
        } else if (name == "is_alpha") {
            result = char_is_alpha(value);
        } else if (name == "is_alnum") {
            result = char_is_digit(value) || char_is_alpha(value);
        } else if (name == "is_space") {
            result = char_is_space(value);
        } else if (name == "is_upper") {
            result = char_is_upper(value);
        } else if (name == "is_lower") {
            result = char_is_lower(value);
        } else {
            result = char_is_ascii(value);
        }
        return make_bool(result);
    }
    if (name == "format" || name == "printf") {
        if (positional.empty()) {
            runtime_fail(name + " expects a format string");
        }
        const std::string format = string_to_utf8(positional[0]);
        const std::vector<Value> arguments(
            positional.begin() + 1, positional.end());
        const std::string text =
            format_text(machine.arena, format, arguments);
        if (name == "printf") {
            machine.host.write(text);
            return make_int(1);
        }
        return string_from_utf8(machine, text);
    }
    if (name == "typeof" || name == "typedeep") {
        if (positional.size() != 1) {
            runtime_fail(name + " expects one argument");
        }
        return string_from_utf8(
            machine,
            name == "typeof"
                ? runtime_type_name(positional[0])
                : deep_type_name(positional[0]));
    }
    if (name == "wait") {
        if (positional.empty()) {
            throw_error(error_argument(
                machine.arena, "builtin: wait",
                "not enought arguments"));
        }
        TaskObject* task = require_task_value(
            machine, positional[0], "wait");
        return await_task(
            machine, task,
            task->kind == TaskObject::Kind::Lazy ? "await" : "wait");
    }
    if (name == "cancel") {
        if (positional.empty()) {
            throw_error(error_argument(
                machine.arena, "builtin: cancel",
                "not enought arguments"));
        }
        cancel_task(
            machine, require_task_value(
                machine, positional[0], "cancel"));
        return make_nova();
    }
    if (name == "task_status") {
        if (positional.empty()) {
            throw_error(error_argument(
                machine.arena, "builtin: task_status",
                "not enought arguments"));
        }
        TaskObject* task = require_task_value(
            machine, positional[0], "task_status");
        return string_from_utf8(
            machine, task_status_name(task->status));
    }
    if (name == "open") {
        if (positional.empty() || positional[0].tag != Tag::Str) {
            throw_error(error_type_match(
                machine.arena, "builtin: open, name",
                "str",
                positional.empty() ? "nova"
                                   : runtime_type_name(positional[0])));
        }
        std::string mode = "read";
        if (positional.size() > 1) {
            if (positional[1].tag != Tag::Str) {
                throw_error(error_type_match(
                    machine.arena, "builtin: open, name",
                    "str", runtime_type_name(positional[1])));
            }
            mode = as_string_const(positional[1])->utf8;
        }
        return open_file_value(
            machine, as_string_const(positional[0])->utf8, mode);
    }
    if (name == "read") {
        if (positional.empty() || positional[0].tag != Tag::Str) {
            throw_error(error_type_match(
                machine.arena, "builtin: read, name",
                "str",
                positional.empty() ? "nova"
                                   : runtime_type_name(positional[0])));
        }
        return read_file_value(
            machine, as_string_const(positional[0])->utf8);
    }
    if (name == "write") {
        if (positional.empty() || positional[0].tag != Tag::Str) {
            throw_error(error_type_match(
                machine.arena, "builtin: write, name",
                "str",
                positional.empty() ? "nova"
                                   : runtime_type_name(positional[0])));
        }
        std::vector<Value> lines;
        if (positional.size() > 1) {
            if (positional[1].tag == Tag::Arr) {
                lines = as_array(positional[1])->items;
            } else {
                lines.push_back(positional[1]);
            }
        }
        return write_file_value(
            machine, as_string_const(positional[0])->utf8, lines);
    }
    if (name == "close") {
        if (positional.empty() || positional[0].tag != Tag::Str) {
            throw_error(error_type_match(
                machine.arena, "builtin: close, name",
                "str",
                positional.empty() ? "nova"
                                   : runtime_type_name(positional[0])));
        }
        return close_file_value(
            machine, as_string_const(positional[0])->utf8);
    }
    if (name == "input" || name == "inputf") {
        Value receptor = positional.empty()
            ? make_string(machine.arena.allocate_string_utf8(""))
            : positional[0];
        if (name == "inputf") {
            if (positional.size() < 2) {
                throw_error(error_argument(
                    machine.arena, "builtin: inputf",
                    "not enought arguments"));
            }
            if (positional[1].tag != Tag::Str) {
                throw_error(error_type_match(
                    machine.arena, "builtin: inputf, prompt",
                    "str", runtime_type_name(positional[1])));
            }
            machine.host.write(format_value(positional[1]));
            receptor = positional[0];
        }
        std::string line;
        if (!std::getline(std::cin, line)) {
            throw_error(make_error(
                machine.arena, "INPUT", "builtin: input",
                "Input stream ended unexpectedly"));
        }
        if (receptor.tag == Tag::Str) {
            return string_from_utf8(machine, line);
        }
        if (receptor.tag == Tag::Bool) {
            return make_bool(!line.empty());
        }
        if (receptor.tag == Tag::Int || receptor.tag == Tag::BigInt) {
            try {
                std::size_t consumed = 0;
                const long long value = std::stoll(line, &consumed);
                if (consumed != line.size()) {
                    throw std::invalid_argument("trailing");
                }
                return make_int(value);
            } catch (const std::exception&) {
                throw_error(make_error(
                    machine.arena, "INPUT", "",
                    "Invalid input for specified type",
                    {"cannot convert " + line,
                     "into type int"}));
            }
        }
        if (receptor.tag == Tag::Num) {
            try {
                std::size_t consumed = 0;
                const double value = std::stod(line, &consumed);
                if (consumed != line.size()) {
                    throw std::invalid_argument("trailing");
                }
                return make_num(value);
            } catch (const std::exception&) {
                throw_error(make_error(
                    machine.arena, "INPUT", "",
                    "Invalid input for specified type",
                    {"cannot convert " + line,
                     "into type num"}));
            }
        }
        throw_error(error_type_match(
            machine.arena, "builtin: input",
            "primitive type", runtime_type_name(receptor)));
    }
    if (name == "system") {
        if (positional.size() != 1
            || positional[0].tag != Tag::Str) {
            throw_error(error_type_match(
                machine.arena, "builtin: system",
                "str",
                positional.empty() ? "nova"
                                   : runtime_type_name(positional[0])));
        }
        const std::string command =
            as_string_const(positional[0])->utf8;
        const int code = std::system(command.c_str());
        return make_int(static_cast<std::int64_t>(code));
    }
    runtime_fail("native N2 does not implement builtin '" + name + "'");
}

} // namespace

int run_embedded_image_with_meta(
    const std::uint8_t* data,
    std::size_t size,
    const std::uint8_t* meta_data,
    std::size_t meta_size,
    Host& host) {
    try {
        Image image = parse_image(data, size);
        verify_image(image);
        Meta meta_storage;
        const Meta* meta = nullptr;
        if (meta_data != nullptr && meta_size != 0) {
            meta_storage = parse_meta(meta_data, meta_size);
            validate_meta(meta_storage, image);
            meta = &meta_storage;
        }
        const ModuleInfo& info = image.modules[image.entry_module];
        Machine machine{host};
        machine.modules = ModuleTable(image, meta, info.name);
        const CodeObject& code = image.codes[image.entry_code];
        Frame frame = make_frame(
            code, machine.modules.entry(), nullptr, true, false);
        try {
            (void)execute(frame, machine);
        } catch (const UnwindSignal& signal) {
            if (signal.error != nullptr) {
                host.write(signal.error->text() + "\n");
            }
            return 1;
        }
        return 0;
    } catch (const ImageError& error) {
        host.write_error(
            std::string("native image error: ") + error.what() + "\n");
        return 1;
    } catch (const VerificationError& error) {
        host.write_error(
            std::string("native verifier error: ") + error.what() + "\n");
        return 1;
    } catch (const MetadataError& error) {
        host.write_error(
            std::string("native metadata error: ") + error.what() + "\n");
        return 1;
    } catch (const RuntimeError& error) {
        host.write_error(
            std::string("native runtime error: ") + error.what() + "\n");
        return 1;
    } catch (const std::bad_alloc&) {
        host.write_error("native internal error: out of memory\n");
        return 1;
    } catch (const std::exception& error) {
        host.write_error(
            std::string("native internal error: ") + error.what() + "\n");
        return 1;
    }
}

int run_embedded_image(
    const std::uint8_t* data, std::size_t size, Host& host) {
    return run_embedded_image_with_meta(data, size, nullptr, 0, host);
}

int run_embedded_bundle_with_meta(
    const std::uint8_t* bundle_data,
    std::size_t bundle_size,
    Host& host) {
    std::uint32_t entry_line_count = 0;
    try {
        Bundle bundle = parse_bundle(bundle_data, bundle_size);
        entry_line_count = bundle.entry_source_line_count;
        Machine machine{host};
        machine.bundle = &bundle;
        machine.entry_path = bundle.entry_path;
        machine.has_project = bundle.has_project;
        if (bundle.has_project) {
            machine.project.module_names = bundle.project.modules;
            machine.project.paths = bundle.project.paths;
            machine.project.log_level = bundle.project.log_level;
            machine.project.allow_system = bundle.project.allow_system;
            machine.project.engine = bundle.project.engine;
        }
        machine.modules = ModuleTable(bundle, machine.arena);
        try {
            initialize_module(machine.modules.entry(), machine);
        } catch (const UnwindSignal& signal) {
            ErrorObject* error = signal.error;
            if (error != nullptr) {
                if (error->line == 0) {
                    error->line = static_cast<std::int32_t>(
                        entry_line_count == 0 ? 1 : entry_line_count);
                }
                host.write(error->text() + "\n");
            }
            return 1;
        }
        return 0;
    } catch (const BundleError& error) {
        host.write_error(
            std::string("native bundle error: ") + error.what() + "\n");
        return 1;
    } catch (const ImageError& error) {
        host.write_error(
            std::string("native image error: ") + error.what() + "\n");
        return 1;
    } catch (const MetadataError& error) {
        host.write_error(
            std::string("native metadata error: ") + error.what() + "\n");
        return 1;
    } catch (const std::exception& error) {
        host.write_error(
            std::string("native internal error: ") + error.what() + "\n");
        return 1;
    }
}

} // namespace pwb
