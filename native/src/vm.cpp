#include "pwb/vm.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cctype>
#include <cwctype>
#include <limits>
#include <new>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "pwb/error.hpp"
#include "pwb/image.hpp"
#include "pwb/meta.hpp"
#include "pwb/object.hpp"
#include "pwb/opcodes.hpp"
#include "pwb/opcodes_generated.hpp"
#include "pwb/value.hpp"
#include "pwb/verifier.hpp"

namespace pwb {
namespace {

struct TraitRuntime {
    const TraitInfo* info = nullptr;
    std::unordered_map<std::string, std::vector<FunctionObject*>> defaults;
};

struct Module {
    std::unordered_map<std::string, Value> globals;
    std::unordered_map<std::string, std::vector<FunctionObject*>> functions;
    std::unordered_set<std::string> declared_globals;
    std::unordered_map<std::string, TypeRuntime> types;
    std::unordered_map<std::string, TraitRuntime> traits;
};

struct Frame {
    const CodeObject* code = nullptr;
    std::vector<Value> locals;
    std::vector<Value> stack;
    std::uint32_t ip = 0;
    std::size_t span_index = 0;
    FunctionObject* function = nullptr;
    Module* module = nullptr;
    std::vector<Value> captures;
    std::unordered_map<std::string, std::size_t> local_slots;
    std::vector<bool> declared;
    Value receiver = make_nova();
    bool has_receiver = false;
};

struct Machine {
    Host& host;
    Arena arena;
    const Meta* meta = nullptr;
    const Image* image = nullptr;
    Module module;
    std::size_t frame_depth = 0;
    std::size_t max_frames = 256;
};

Value execute(const Image& image, Frame& frame, Machine& machine);

Frame make_frame(
    const CodeObject& code, Module& module, FunctionObject* function) {
    Frame frame;
    frame.code = &code;
    frame.locals.assign(code.local_count, make_undef());
    frame.declared.assign(code.local_count, false);
    frame.stack.reserve(code.max_stack);
    frame.module = &module;
    frame.function = function;
    for (std::size_t slot = 0; slot < code.local_names.size(); ++slot) {
        const std::string& name = code.local_names[slot];
        if (!name.empty()) {
            frame.local_slots.emplace(name, slot);
        }
    }
    return frame;
}

[[noreturn]] void runtime_fail(const std::string& message) {
    throw RuntimeError(message);
}

std::int64_t value_as_int(const Value& value, const char* what);

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

void require_numeric(const Value& value, const char* opcode) {
    if (value.tag != Tag::Int && value.tag != Tag::BigInt
        && value.tag != Tag::Num) {
        runtime_fail(
            std::string("native N1 ") + opcode
            + " requires int or num operands, got " + tag_name(value.tag));
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
    require_numeric(left, "ADD");
    require_numeric(right, "ADD");
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
    require_numeric(left, "SUB");
    require_numeric(right, "SUB");
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
    require_numeric(left, "MUL");
    require_numeric(right, "MUL");
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

Value arithmetic_div(Machine& machine, const Value& left, const Value& right) {
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
    require_numeric(left, "DIV");
    require_numeric(right, "DIV");
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
    require_numeric(left, "MOD");
    require_numeric(right, "MOD");
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
    const Value& left, const Value& right, const char* opcode) {
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
    runtime_fail(
        std::string("native N1 ") + opcode + " does not support "
        + tag_name(left.tag) + " and " + tag_name(right.tag) + " operands");
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
    const Value* receiver = nullptr);
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
    const Value& index, std::size_t size, const char* what);
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

Value execute(const Image& image, Frame& frame, Machine& machine) {
    const CodeObject& code = *frame.code;
    while (frame.ip < code.bytecode.size()) {
        const DecodedInstruction instruction =
            decode_instruction(code.bytecode, frame.ip);
        frame.ip = instruction.next_offset;
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
                if (machine.meta == nullptr || machine.image == nullptr) {
                    runtime_fail("type metadata is required");
                }
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= machine.image->types.size()) {
                    runtime_fail(
                        "type index out of range: "
                        + std::to_string(index));
                }
                const TypeInfo& info =
                    machine.image->types[static_cast<std::size_t>(index)];
                TypeRuntime& runtime = machine.module.types[info.name];
                runtime = TypeRuntime{};
                runtime.info = &info;
                for (const TypeMethod& method : info.methods) {
                    if (static_cast<std::uint64_t>(method.index)
                        >= machine.meta->functions.size()) {
                        continue;
                    }
                    FunctionObject* function =
                        machine.arena.allocate_function(
                            &machine.meta->functions[
                                static_cast<std::size_t>(method.index)]);
                    const bool is_instance =
                        method.name == "constructor" || method.is_static;
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
                        object->fields["name"] =
                            string_from_utf8(machine, variant);
                        map_set(
                            *variants,
                            string_from_utf8(machine, variant),
                            make_object(object));
                    }
                    const Value enum_value = make_map(variants);
                    machine.module.globals[info.name] = enum_value;
                    push_value(frame, enum_value);
                } else {
                    const Value type_value = make_type(&runtime);
                    machine.module.globals[info.name] = type_value;
                    push_value(frame, type_value);
                }
                break;
            }
            case Opcode::DECLARE_TRAIT: {
                const std::int64_t index =
                    operand_integer(instruction, "trait");
                if (machine.meta == nullptr || machine.image == nullptr) {
                    runtime_fail("trait metadata is required");
                }
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= machine.image->traits.size()) {
                    runtime_fail(
                        "trait index out of range: "
                        + std::to_string(index));
                }
                const TraitInfo& info =
                    machine.image->traits[static_cast<std::size_t>(index)];
                TraitRuntime& runtime = machine.module.traits[info.name];
                runtime = TraitRuntime{};
                runtime.info = &info;
                for (const TraitMethod& method : info.methods) {
                    if (static_cast<std::uint64_t>(method.index)
                        >= machine.meta->functions.size()) {
                        continue;
                    }
                    FunctionObject* function =
                        machine.arena.allocate_function(
                            &machine.meta->functions[
                                static_cast<std::size_t>(method.index)]);
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
                frame.locals[slot] = make_undef();
                push_value(frame, frame.locals[slot]);
                break;
            }
            case Opcode::DECLARE_TYPED:
            case Opcode::DECLARE_INFER: {
                const std::uint32_t slot =
                    operand_slot(instruction, code, "slot");
                frame.declared[slot] = true;
                const Value value = copy_value(machine.arena, pop_value(frame));
                frame.locals[slot] = value;
                push_value(frame, value);
                break;
            }
            case Opcode::DECLARE_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                const std::int64_t flags =
                    operand_integer(instruction, "flags");
                if (!(flags & 1)
                    && machine.module.declared_globals.count(name) != 0) {
                    runtime_fail("Cannot redefine variables");
                }
                machine.module.declared_globals.insert(name);
                machine.module.globals[name] = make_undef();
                push_value(frame, make_undef());
                break;
            }
            case Opcode::DECLARE_TYPED_GLOBAL:
            case Opcode::DECLARE_INFER_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                if (machine.module.declared_globals.count(name) != 0) {
                    runtime_fail("Cannot redefine variables");
                }
                machine.module.declared_globals.insert(name);
                const Value value = copy_value(machine.arena, pop_value(frame));
                machine.module.globals[name] = value;
                push_value(frame, value);
                break;
            }
            case Opcode::DECLARE_UNDEFINED_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                machine.module.declared_globals.insert(name);
                machine.module.globals[name] = make_undef();
                push_value(frame, make_undef());
                break;
            }
            case Opcode::DECLARE_FUNCTION: {
                const std::int64_t index =
                    operand_integer(instruction, "function");
                if (machine.meta == nullptr) {
                    runtime_fail("function metadata is required");
                }
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= machine.meta->functions.size()) {
                    runtime_fail(
                        "function index out of range: "
                        + std::to_string(index));
                }
                const FunctionMetadata& metadata =
                    machine.meta->functions[static_cast<std::size_t>(index)];
                FunctionObject* function =
                    machine.arena.allocate_function(&metadata);
                machine.module.functions[metadata.name].push_back(function);
                push_value(frame, make_function(function));
                break;
            }
            case Opcode::MAKE_FUNCTION: {
                const std::int64_t index =
                    operand_integer(instruction, "function");
                if (machine.meta == nullptr) {
                    runtime_fail("function metadata is required");
                }
                if (index < 0
                    || static_cast<std::uint64_t>(index)
                        >= machine.meta->functions.size()) {
                    runtime_fail(
                        "function index out of range: "
                        + std::to_string(index));
                }
                const FunctionMetadata& metadata =
                    machine.meta->functions[static_cast<std::size_t>(index)];
                FunctionObject* function =
                    machine.arena.allocate_function(&metadata);
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
            case Opcode::LOAD_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                const auto found = machine.module.globals.find(name);
                if (found == machine.module.globals.end()) {
                    runtime_fail("identifier '" + name + "' not found");
                }
                push_value(frame, found->second);
                break;
            }
            case Opcode::STORE_GLOBAL: {
                const std::string& name = global_name_at(image, instruction);
                machine.module.globals[name] =
                    copy_value(machine.arena, pop_value(frame));
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
                    runtime_fail("identifier '" + name + "' not found");
                }
                push_value(frame, value);
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
                if (value.tag != Tag::Arr) {
                    runtime_fail("spread requires an array in N1");
                }
                push_value(frame, make_spread(as_array(value)));
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
                    frame.locals[operand_slot(instruction, code, "slot")]);
                break;
            case Opcode::STORE_LOCAL:
            case Opcode::ASSIGN_LOCAL:
                frame.locals[operand_slot(instruction, code, "slot")] =
                    copy_value(machine.arena, pop_value(frame));
                break;
            case Opcode::LOAD_RAW:
                push_value(
                    frame,
                    frame.locals[operand_slot(instruction, code, "slot")]);
                break;
            case Opcode::STORE_RAW:
                frame.locals[operand_slot(instruction, code, "slot")] =
                    pop_value(frame);
                break;
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
                if (machine.image == nullptr || enum_index < 0
                    || static_cast<std::uint64_t>(enum_index)
                        >= machine.image->types.size()) {
                    runtime_fail("enum type index out of range");
                }
                const TypeInfo& info =
                    machine.image->types[static_cast<std::size_t>(enum_index)];
                if (variant < 0
                    || static_cast<std::uint64_t>(variant)
                        >= info.variants.size()) {
                    runtime_fail("enum variant index out of range");
                }
                const std::string& variant_name =
                    info.variants[static_cast<std::size_t>(variant)];
                ObjectObject* object = machine.arena.allocate_object(
                    info.name, true, variant_name);
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
                if (owner.tag != Tag::Obj) {
                    runtime_fail("locks require an object value");
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
                if (machine.image == nullptr || index < 0
                    || static_cast<std::uint64_t>(index)
                        >= machine.image->traits.size()
                    || value.tag != Tag::Obj) {
                    runtime_fail("value does not satisfy the trait");
                }
                const TraitInfo& info = machine.image->traits[
                    static_cast<std::size_t>(index)];
                const auto trait = machine.module.traits.find(info.name);
                if (trait == machine.module.traits.end()
                    || !object_satisfies_trait(
                        machine, *as_object(value), trait->second)) {
                    runtime_fail(
                        "value does not satisfy trait '" + info.name + "'");
                }
                push_value(frame, value);
                break;
            }
            case Opcode::ADD: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "add", {right}, "operator +"));
                    break;
                }
                push_value(frame, arithmetic_add(machine, left, right));
                break;
            }
            case Opcode::SUB: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "subtract", {right}, "operator -"));
                    break;
                }
                push_value(frame, arithmetic_sub(machine, left, right));
                break;
            }
            case Opcode::MUL: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "multiply", {right}, "operator *"));
                    break;
                }
                push_value(frame, arithmetic_mul(machine, left, right));
                break;
            }
            case Opcode::DIV: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                if (left.tag == Tag::Obj) {
                    push_value(frame, call_type_method(
                        machine, left, "divide", {right}, "operator /"));
                    break;
                }
                push_value(frame, arithmetic_div(machine, left, right));
                break;
            }
            case Opcode::MOD: {
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
            case Opcode::NEQ:
            case Opcode::LT:
            case Opcode::LE:
            case Opcode::GT:
            case Opcode::GE: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                const Comparison comparison =
                    (left.tag == Tag::Obj || right.tag == Tag::Obj)
                    ? compare_object_values(
                        machine, left, right, instruction.spec->name)
                    : compare_values(left, right, instruction.spec->name);
                bool result = false;
                switch (static_cast<Opcode>(instruction.opcode)) {
                    case Opcode::EQ:
                        result = !comparison.unordered
                            && comparison.order == 0;
                        break;
                    case Opcode::NEQ:
                        result = comparison.unordered
                            || comparison.order != 0;
                        break;
                    case Opcode::LT:
                        result = !comparison.unordered
                            && comparison.order < 0;
                        break;
                    case Opcode::LE:
                        result = !comparison.unordered
                            && comparison.order <= 0;
                        break;
                    case Opcode::GT:
                        result = !comparison.unordered
                            && comparison.order > 0;
                        break;
                    case Opcode::GE:
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
                        call_function(
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
                        machine.module.functions.find(site.name);
                    if (found != machine.module.functions.end()) {
                        candidates = &found->second;
                    }
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
                        if (machine.meta == nullptr) {
                            runtime_fail(
                                "function metadata is required for '"
                                + site.name + "'");
                        }
                        function = select_overload(
                            *candidates, positional, *machine.meta);
                    }
                    push_value(
                        frame,
                        call_function(
                            machine, function, std::move(positional),
                            std::move(named), "call: " + site.name));
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
                        call_function(
                            machine, as_function(variable),
                            std::move(positional), std::move(named),
                            "call: " + site.name));
                    break;
                }
                runtime_fail("identifier '" + site.name + "' not found");
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
                (void)named;
                if (receiver.tag != Tag::Obj) {
                    runtime_fail("method call requires an object receiver");
                }
                ObjectObject* object = as_object(receiver);
                const auto type_it =
                    machine.module.types.find(object->type_name);
                if (type_it == machine.module.types.end()) {
                    runtime_fail(
                        "unknown type '" + object->type_name + "'");
                }
                const TypeRuntime& type = type_it->second;
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
                if (candidates == nullptr) {
                    for (const auto& entry : machine.module.traits) {
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
                FunctionObject* function = select_overload(
                    *candidates, positional, *machine.meta);
                if (function->is_private
                    && !private_access_allowed(machine, frame, *object)) {
                    runtime_fail("private method: " + site.name);
                }
                push_value(
                    frame,
                    call_function(
                        machine, function, positional, {},
                        "method call: " + site.name, &receiver));
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
                const auto type_it =
                    machine.module.types.find(*site.type_name);
                if (type_it == machine.module.types.end()) {
                    runtime_fail(
                        "unknown type '" + *site.type_name + "'");
                }
                const auto methods =
                    type_it->second.statics.find(site.name);
                if (methods == type_it->second.statics.end()
                    || methods->second.empty()) {
                    runtime_fail("static method not found: " + site.name);
                }
                FunctionObject* function = select_overload(
                    methods->second, positional, *machine.meta);
                push_value(
                    frame,
                    call_function(
                        machine, function, positional, named,
                        "method call: " + *site.type_name + "."
                        + site.name));
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
                const auto type_it =
                    machine.module.types.find(object->type_name);
                if (type_it == machine.module.types.end()) {
                    runtime_fail(
                        "unknown type '" + object->type_name + "'");
                }
                const std::string trait_name =
                    site.trait_name.value_or("");
                const std::vector<FunctionObject*>* candidates = nullptr;
                const auto trait =
                    type_it->second.trait_methods.find(trait_name);
                if (trait != type_it->second.trait_methods.end()) {
                    const auto found = trait->second.find(site.name);
                    if (found != trait->second.end()) {
                        candidates = &found->second;
                    }
                }
                if (candidates == nullptr) {
                    const auto defaults =
                        machine.module.traits.find(trait_name);
                    if (defaults != machine.module.traits.end()) {
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
                FunctionObject* function = select_overload(
                    *candidates, arguments, *machine.meta);
                push_value(
                    frame,
                    call_function(
                        machine, function, arguments, {},
                        "trait call: " + trait_name + "." + site.name,
                        &receiver));
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
                const auto type_it =
                    machine.module.types.find(object->type_name);
                if (type_it == machine.module.types.end()) {
                    runtime_fail(
                        "unknown type '" + object->type_name + "'");
                }
                const std::string trait_name =
                    site.operator_trait.value_or("");
                const std::vector<FunctionObject*>* candidates = nullptr;
                const auto trait =
                    type_it->second.trait_methods.find(trait_name);
                if (trait != type_it->second.trait_methods.end()) {
                    const auto found = trait->second.find(site.name);
                    if (found != trait->second.end()) {
                        candidates = &found->second;
                    }
                }
                if (candidates == nullptr) {
                    const auto defaults =
                        machine.module.traits.find(trait_name);
                    if (defaults != machine.module.traits.end()) {
                        const auto found =
                            defaults->second.defaults.find(site.name);
                        if (found != defaults->second.defaults.end()) {
                            candidates = &found->second;
                        }
                    }
                }
                if (candidates == nullptr) {
                    const auto methods =
                        type_it->second.methods.find(site.name);
                    if (methods != type_it->second.methods.end()) {
                        candidates = &methods->second;
                    }
                }
                if (candidates == nullptr || candidates->empty()) {
                    runtime_fail(
                        "operator method not found: " + site.name);
                }
                FunctionObject* function = select_overload(
                    *candidates, arguments, *machine.meta);
                push_value(
                    frame,
                    call_function(
                        machine, function, arguments, {},
                        "operator call: " + site.name, &receiver));
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
                        runtime_fail(
                            "named arguments are only supported for user "
                            "type constructors");
                    }
                    positional.push_back(raw[stack_index]);
                    ++stack_index;
                    ++argument_index;
                }
                while (stack_index < raw.size()) {
                    positional.push_back(raw[stack_index]);
                    ++stack_index;
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
                const auto type_it =
                    machine.module.types.find(site.name);
                if (type_it != machine.module.types.end()
                    && type_it->second.info != nullptr
                    && type_it->second.info->kind == "object") {
                    TypeRuntime& type = type_it->second;
                    ObjectObject* object =
                        machine.arena.allocate_object(site.name, false, "");
                    for (const TypeProperty& property :
                         type.info->properties) {
                        object->fields[property.name] = make_undef();
                        if (!property.is_private) {
                            object->private_fields.insert(property.name);
                        }
                    }
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
                        push_value(frame, object_value);
                        break;
                    }
                    FunctionObject* function = select_overload(
                        constructors->second, positional, *machine.meta);
                    const Value result = call_function(
                        machine, function, positional, {},
                        "instantiation", &object_value);
                    push_value(
                        frame,
                        result.tag == Tag::Nova ? object_value : result);
                    break;
                }
                runtime_fail(
                    "native N3 does not implement construction of '"
                    + site.name + "'");
            }
            case Opcode::RETURN:
                return pop_value(frame);
            case Opcode::CHECK_CANCEL:
                break;
            default:
                runtime_fail(
                    std::string("native N0 does not implement opcode ")
                    + instruction.spec->name);
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
        case Tag::Obj: return "obj";
        case Tag::Type: return "type";
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
    const auto global = machine.module.globals.find(name);
    if (global != machine.module.globals.end()) {
        out = global->second;
        return true;
    }
    const auto functions = machine.module.functions.find(name);
    if (functions != machine.module.functions.end()
        && !functions->second.empty()) {
        out = make_function(functions->second.back());
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
    const auto global = machine.module.globals.find(name);
    if (global != machine.module.globals.end()) {
        out = global->second;
        return true;
    }
    const auto functions = machine.module.functions.find(name);
    if (functions != machine.module.functions.end()
        && !functions->second.empty()) {
        out = make_function(functions->second.back());
        return true;
    }
    return false;
}

Value resolve_name(
    Machine& machine, Frame& frame, const std::string& name) {
    Value value;
    if (try_resolve_name(machine, frame, name, value)) {
        return value;
    }
    runtime_fail("identifier '" + name + "' not found");
}

void assign_name(
    Machine& machine,
    Frame& frame,
    const std::string& name,
    const Value& value) {
    const auto local = frame.local_slots.find(name);
    if (local != frame.local_slots.end()) {
        frame.locals[local->second] = value;
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
    const auto global = machine.module.globals.find(name);
    if (global != machine.module.globals.end()) {
        global->second = value;
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
    const Value& value) {
    const auto slot = frame.local_slots.find(name);
    if (slot == frame.local_slots.end()) {
        runtime_fail("parameter slot not found: " + name);
    }
    frame.locals[slot->second] = copy_value(machine.arena, value);
}

Value run_default(
    Machine& machine, int code_index, const std::string& where) {
    (void)where;
    if (machine.image == nullptr) {
        runtime_fail("function metadata is required");
    }
    if (code_index < 0
        || static_cast<std::size_t>(code_index)
            >= machine.image->codes.size()) {
        runtime_fail("default code index out of range");
    }
    const CodeObject& code =
        machine.image->codes[static_cast<std::size_t>(code_index)];
    if (machine.frame_depth >= machine.max_frames) {
        runtime_fail("maximum frame depth exceeded");
    }
    Frame frame = make_frame(code, machine.module, nullptr);
    ++machine.frame_depth;
    try {
        const Value value = execute(*machine.image, frame, machine);
        --machine.frame_depth;
        return value;
    } catch (...) {
        --machine.frame_depth;
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
        if (resolved[index].has_value()) {
            set_parameter(
                machine, frame, spec.parameters[index].name, *resolved[index]);
            continue;
        }
        if (index < spec.min_argc) {
            runtime_fail(
                "Missing required argument '"
                + spec.parameters[index].name + "'");
        }
        if (spec.parameters[index].default_index >= 0) {
            set_parameter(
                machine, frame, spec.parameters[index].name,
                run_default(
                    machine, spec.parameters[index].default_index, where));
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
    const Value* receiver) {
    if (machine.meta == nullptr || machine.image == nullptr) {
        runtime_fail("function metadata is required");
    }
    if (function == nullptr || function->metadata == nullptr) {
        runtime_fail("invalid function value");
    }
    const FunctionMetadata& spec = *function->metadata;
    if (spec.code_index >= machine.image->codes.size()) {
        runtime_fail("function code index out of range");
    }
    const CodeObject& code =
        machine.image->codes[spec.code_index];
    if (machine.frame_depth >= machine.max_frames) {
        runtime_fail("maximum frame depth exceeded");
    }
    Frame frame = make_frame(code, machine.module, function);
    if (receiver == nullptr && function->has_receiver) {
        receiver = &function->receiver;
    }
    if (receiver != nullptr) {
        frame.receiver = *receiver;
        frame.has_receiver = true;
    }
    bind_function(
        machine, frame, function, positional, named, where);
    ++machine.frame_depth;
    try {
        const Value value = execute(*machine.image, frame, machine);
        --machine.frame_depth;
        return value;
    } catch (...) {
        --machine.frame_depth;
        throw;
    }
}

Value string_from_utf8(Machine& machine, const std::string& text) {
    return make_string(machine.arena.allocate_string_utf8(text));
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
    const Value& index, std::size_t size, const char* what) {
    std::int64_t value = value_as_int(index, what);
    const std::int64_t length = static_cast<std::int64_t>(size);
    if (value < 0) {
        value += length;
    }
    if (value < 0 || value >= length) {
        runtime_fail(
            std::string(what) + " index out of range: "
            + std::to_string(value));
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

Value index_get(
    Machine& machine, const Value& container, const Value& index) {
    (void)machine;
    switch (container.tag) {
        case Tag::Map: {
            const Value* found = map_get(*as_map(container), index);
            if (found == nullptr) {
                runtime_fail("map key was not found");
            }
            return *found;
        }
        case Tag::Arr: {
            const auto& items = as_array(container)->items;
            const std::int64_t position =
                resolved_index(index, items.size(), "arr");
            return items[static_cast<std::size_t>(position)];
        }
        case Tag::Tup: {
            const auto& items = as_tuple(container)->items;
            const std::int64_t position =
                resolved_index(index, items.size(), "tup");
            return items[static_cast<std::size_t>(position)];
        }
        case Tag::Str: {
            const auto& points = as_string_const(container)->code_points;
            const std::int64_t position =
                resolved_index(index, points.size(), "str");
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
            auto& items = as_array(container)->items;
            const std::int64_t position =
                resolved_index(index, items.size(), "arr");
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
            runtime_fail(
                std::string("value of type ") + tag_name(value.tag)
                + " cannot be reversed");
    }
}

std::int64_t value_size(const Value& value) {
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
        default:
            runtime_fail(
                std::string("value of type ") + tag_name(value.tag)
                + " has no size");
    }
}

Value builtin_size(Machine& machine, const Value& value) {
    (void)machine;
    return make_int(value_size(value));
}

Value builtin_size_all(Machine& machine, const std::vector<Value>& values) {
    (void)machine;
    std::int64_t total = 0;
    for (const Value& value : values) {
        total += value_size(value);
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
            resolved_index(index, size, "arr");
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
            resolved_index(arguments[1], size, "arr");
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
            resolved_index(index, source.size(), "str");
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
            resolved_index(index, source->items.size(), "tup");
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
    const std::string type = site.native_type.has_value()
        ? *site.native_type
        : runtime_type_name(positional[0]);
    if (type == "arr") {
        return array_method(machine, site.name, positional);
    }
    if (type == "str") {
        return string_method(machine, site.name, positional);
    }
    if (type == "map") {
        return map_method(machine, site.name, positional);
    }
    if (type == "set") {
        return set_method(machine, site.name, positional);
    }
    if (type == "tup") {
        return tuple_method(machine, site.name, positional);
    }
    if (type == "char") {
        return char_method(machine, site.name, positional);
    }
    runtime_fail("native method type not implemented: " + type);
}

Value load_object_member(
    Machine& machine,
    Frame& frame,
    const Value& owner,
    const std::string& name,
    bool safe,
    bool allow_methods) {
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
    const auto type_it = machine.module.types.find(object->type_name);
    if (type_it != machine.module.types.end()) {
        const auto methods = type_it->second.methods.find(name);
        if (methods != type_it->second.methods.end()
            && !methods->second.empty()) {
            FunctionObject* source = methods->second.back();
            if (source->is_private
                && !private_access_allowed(machine, frame, *object)) {
                runtime_fail("private method: " + name);
            }
            FunctionObject* bound = machine.arena.allocate_function(
                source->metadata);
            bound->owner = source->owner;
            bound->is_static = false;
            bound->is_private = source->is_private;
            bound->trait_qualifier = source->trait_qualifier;
            bound->receiver = owner;
            bound->has_receiver = true;
            return make_function(bound);
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
    if (owner.tag != Tag::Obj) {
        runtime_fail("member assignment requires an object value");
    }
    ObjectObject* object = as_object(owner);
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
    if (trait.info == nullptr) {
        return false;
    }
    const auto type_it = machine.module.types.find(object.type_name);
    if (type_it == machine.module.types.end()) {
        return false;
    }
    const TypeRuntime& type = type_it->second;
    for (const std::string& property : trait.info->properties) {
        bool found = object.fields.count(property) != 0;
        if (!found && type.info != nullptr) {
            for (const TypeProperty& info_property :
                 type.info->properties) {
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
        bool found = type.methods.count(method.name) != 0;
        if (!found) {
            const auto trait_methods =
                type.trait_methods.find(trait.info->name);
            if (trait_methods != type.trait_methods.end()
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
    const auto type_it = machine.module.types.find(object->type_name);
    if (type_it == machine.module.types.end()) {
        runtime_fail("unknown type '" + object->type_name + "'");
    }
    const auto methods = type_it->second.methods.find(name);
    if (methods == type_it->second.methods.end()
        || methods->second.empty()) {
        runtime_fail("operator method not found: " + name);
    }
    FunctionObject* function = select_overload(
        methods->second, arguments, *machine.meta);
    return call_function(
        machine, function, arguments, {}, where, &receiver);
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
        const auto type_it = machine.module.types.find(a->type_name);
        if (type_it != machine.module.types.end()) {
            const auto methods = type_it->second.methods.find("compare");
            if (methods != type_it->second.methods.end()
                && !methods->second.empty()) {
                FunctionObject* function = select_overload(
                    methods->second, {right}, *machine.meta);
                const Value result = call_function(
                    machine, function, {right}, {},
                    "operator compare", &left);
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
            char_is_digit(value) ? value - U'0' : -1);
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
        const Image image = parse_image(data, size);
        verify_image(image);
        Meta meta_storage;
        const Meta* meta = nullptr;
        if (meta_data != nullptr && meta_size != 0) {
            meta_storage = parse_meta(meta_data, meta_size);
            validate_meta(meta_storage, image);
            meta = &meta_storage;
        }
        const CodeObject& code = image.codes[image.entry_code];
        Machine machine{host, {}, meta, &image, {}, 0, 256};
        Frame frame = make_frame(code, machine.module, nullptr);
        (void)execute(image, frame, machine);
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

} // namespace pwb
