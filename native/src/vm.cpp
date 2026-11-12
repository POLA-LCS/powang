#include "pwb/vm.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
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

struct Module {
    std::unordered_map<std::string, Value> globals;
    std::unordered_map<std::string, std::vector<FunctionObject*>> functions;
    std::unordered_set<std::string> declared_globals;
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
    const Image& image, const DecodedInstruction& instruction) {
    const std::int64_t index = operand_integer(instruction, "name");
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
    const std::string& where);
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
                runtime_fail(
                    "native N0 does not implement string literals (LOAD_STR)");
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
                const Value value = pop_value(frame);
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
                const Value value = pop_value(frame);
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
                machine.module.globals[name] = pop_value(frame);
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
                const Value value = pop_value(frame);
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
                push_value(frame, pop_value(frame));
                break;
            case Opcode::ITER_NEW: {
                const Value iterable = pop_value(frame);
                if (iterable.tag != Tag::Arr) {
                    runtime_fail(
                        "for each expression is not an iterable value");
                }
                IteratorObject* iterator =
                    machine.arena.allocate_iterator(as_array(iterable)->items);
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
                    pop_value(frame);
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
            case Opcode::ADD: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_add(machine, left, right));
                break;
            }
            case Opcode::SUB: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_sub(machine, left, right));
                break;
            }
            case Opcode::MUL: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_mul(machine, left, right));
                break;
            }
            case Opcode::DIV: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_div(machine, left, right));
                break;
            }
            case Opcode::MOD: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_mod(machine, left, right));
                break;
            }
            case Opcode::NEG:
                push_value(frame, arithmetic_negate(machine, pop_value(frame)));
                break;
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
                    compare_values(left, right, instruction.spec->name);
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
            case Opcode::CALL_BUILTIN: {
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
                if (site.name == "print" || site.name == "println") {
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
    Frame& frame, const std::string& name, const Value& value) {
    const auto slot = frame.local_slots.find(name);
    if (slot == frame.local_slots.end()) {
        runtime_fail("parameter slot not found: " + name);
    }
    frame.locals[slot->second] = value;
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
                frame, spec.parameters[index].name, *resolved[index]);
            continue;
        }
        if (index < spec.min_argc) {
            runtime_fail(
                "Missing required argument '"
                + spec.parameters[index].name + "'");
        }
        if (spec.parameters[index].default_index >= 0) {
            set_parameter(
                frame, spec.parameters[index].name,
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
    const std::string& where) {
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
    runtime_fail("native N1 does not implement builtin '" + name + "'");
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
