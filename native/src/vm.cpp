#include "pwb/vm.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <new>
#include <string>
#include <utility>
#include <vector>

#include "pwb/error.hpp"
#include "pwb/image.hpp"
#include "pwb/opcodes.hpp"
#include "pwb/opcodes_generated.hpp"
#include "pwb/value.hpp"
#include "pwb/verifier.hpp"

namespace pwb {
namespace {

struct Frame {
    const CodeObject* code = nullptr;
    std::vector<Value> locals;
    std::vector<Value> stack;
    std::uint32_t ip = 0;
};

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

void require_numeric(const Value& value, const char* opcode) {
    if (value.tag != Tag::Int && value.tag != Tag::Num) {
        runtime_fail(
            std::string("native N0 ") + opcode
            + " requires int or num operands, got " + tag_name(value.tag));
    }
}

double as_double(const Value& value) {
    return value.tag == Tag::Int ? static_cast<double>(value.i) : value.d;
}

// Numeric coercion used by num left comparisons and by int like comparison
// operands. Bool is 0 or 1 and every other numeric tag has a direct value.
double numeric_as_double(const Value& value) {
    switch (value.tag) {
        case Tag::Bool:
            return value.b ? 1.0 : 0.0;
        case Tag::Int:
            return static_cast<double>(value.i);
        case Tag::Num:
            return value.d;
        default:
            return 0.0;
    }
}

bool is_int_like(const Value& value) {
    return value.tag == Tag::Bool || value.tag == Tag::Int;
}

std::int64_t int_like_value(const Value& value) {
    if (value.tag == Tag::Bool) {
        return value.b ? 1 : 0;
    }
    return value.i;
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

[[noreturn]] void overflow(const char* opcode) {
    runtime_fail(std::string("integer overflow in ") + opcode);
}

Value arithmetic_add(const Value& left, const Value& right) {
    require_numeric(left, "ADD");
    require_numeric(right, "ADD");
    if (left.tag == Tag::Int && right.tag == Tag::Int) {
        std::int64_t result = 0;
        if (__builtin_add_overflow(left.i, right.i, &result)) {
            overflow("ADD");
        }
        return make_int(result);
    }
    if (left.tag == Tag::Int && right.tag == Tag::Num) {
        // The Python VM casts the right operand to the left type.
        const std::int64_t converted = num_to_int(right.d, "ADD");
        std::int64_t result = 0;
        if (__builtin_add_overflow(left.i, converted, &result)) {
            overflow("ADD");
        }
        return make_int(result);
    }
    return make_num(as_double(left) + as_double(right));
}

Value arithmetic_sub(const Value& left, const Value& right) {
    require_numeric(left, "SUB");
    require_numeric(right, "SUB");
    if (left.tag == Tag::Int && right.tag == Tag::Int) {
        std::int64_t result = 0;
        if (__builtin_sub_overflow(left.i, right.i, &result)) {
            overflow("SUB");
        }
        return make_int(result);
    }
    if (left.tag == Tag::Int && right.tag == Tag::Num) {
        const std::int64_t converted = num_to_int(right.d, "SUB");
        std::int64_t result = 0;
        if (__builtin_sub_overflow(left.i, converted, &result)) {
            overflow("SUB");
        }
        return make_int(result);
    }
    return make_num(as_double(left) - as_double(right));
}

Value arithmetic_mul(const Value& left, const Value& right) {
    require_numeric(left, "MUL");
    require_numeric(right, "MUL");
    if (left.tag == Tag::Int && right.tag == Tag::Int) {
        std::int64_t result = 0;
        if (__builtin_mul_overflow(left.i, right.i, &result)) {
            overflow("MUL");
        }
        return make_int(result);
    }
    if (left.tag == Tag::Int && right.tag == Tag::Num) {
        const std::int64_t converted = num_to_int(right.d, "MUL");
        std::int64_t result = 0;
        if (__builtin_mul_overflow(left.i, converted, &result)) {
            overflow("MUL");
        }
        return make_int(result);
    }
    return make_num(as_double(left) * as_double(right));
}

Value arithmetic_div(const Value& left, const Value& right) {
    require_numeric(left, "DIV");
    require_numeric(right, "DIV");
    if (left.tag == Tag::Int && right.tag == Tag::Int) {
        if (right.i == 0) {
            return make_nova();
        }
        if (left.i == std::numeric_limits<std::int64_t>::min()
            && right.i == -1) {
            overflow("DIV");
        }
        std::int64_t quotient = left.i / right.i;
        const std::int64_t remainder = left.i % right.i;
        if (remainder != 0 && ((remainder < 0) != (right.i < 0))) {
            quotient -= 1;
        }
        return make_int(quotient);
    }
    if (left.tag == Tag::Int && right.tag == Tag::Num) {
        // Python computes int(left / right), so the double quotient is
        // truncated toward zero instead of using integer floor division.
        if (right.d == 0.0) {
            return make_nova();
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

Value arithmetic_mod(const Value& left, const Value& right) {
    require_numeric(left, "MOD");
    require_numeric(right, "MOD");
    if (left.tag == Tag::Int && right.tag == Tag::Int) {
        if (right.i == 0) {
            return make_nova();
        }
        if (left.i == std::numeric_limits<std::int64_t>::min()
            && right.i == -1) {
            return make_int(0);
        }
        std::int64_t remainder = left.i % right.i;
        if (remainder != 0 && ((remainder < 0) != (right.i < 0))) {
            remainder += right.i;
        }
        return make_int(remainder);
    }
    if (left.tag == Tag::Int && right.tag == Tag::Num) {
        // The Python VM casts the num to int, then takes the int remainder.
        const std::int64_t divisor = num_to_int(right.d, "MOD");
        if (divisor == 0) {
            return make_nova();
        }
        if (left.i == std::numeric_limits<std::int64_t>::min()
            && divisor == -1) {
            return make_int(0);
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
    // Python float modulo takes the divisor sign. std::fmod takes the
    // dividend sign, so a zero result copies the divisor sign and a
    // non-zero result whose sign differs gets one divisor added.
    if (remainder == 0.0) {
        return make_num(std::copysign(0.0, divisor));
    }
    if ((remainder < 0.0) != (divisor < 0.0)) {
        remainder += divisor;
    }
    return make_num(remainder);
}

Value arithmetic_negate(const Value& value) {
    if (value.tag == Tag::Int) {
        if (value.i == std::numeric_limits<std::int64_t>::min()) {
            overflow("NEG");
        }
        return make_int(-value.i);
    }
    if (value.tag == Tag::Num) {
        return make_num(-value.d);
    }
    runtime_fail(
        std::string("native N0 NEG requires an int or num operand, got ")
        + tag_name(value.tag));
}

struct Comparison {
    bool unordered = false;
    int order = 0;
};

bool is_numeric_value(const Value& value) {
    return value.tag == Tag::Bool || value.tag == Tag::Int
        || value.tag == Tag::Num;
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
            if (is_int_like(right)) {
                other = int_like_value(right) != 0;
            } else {
                other = right.d != 0.0;
            }
            if (left.b == other) {
                return {false, 0};
            }
            return {false, left.b ? 1 : -1};
        }
        if (left.tag == Tag::Int) {
            if (right.tag == Tag::Num) {
                if (std::isnan(right.d)) {
                    return {true, 0};
                }
                const std::int64_t other =
                    num_to_int(right.d, opcode);
                return {
                    false,
                    left.i < other ? -1 : (left.i > other ? 1 : 0)};
            }
            const std::int64_t other = int_like_value(right);
            return {
                false,
                left.i < other ? -1 : (left.i > other ? 1 : 0)};
        }
        if (right.tag == Tag::Num) {
            if (std::isnan(left.d) || std::isnan(right.d)) {
                return {true, 0};
            }
            return {
                false,
                left.d < right.d ? -1 : (left.d > right.d ? 1 : 0)};
        }
        if (std::isnan(left.d)) {
            return {true, 0};
        }
        const double other = numeric_as_double(right);
        return {
            false,
            left.d < other ? -1 : (left.d > other ? 1 : 0)};
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
                break;
            case Tag::Bool:
            case Tag::Int:
            case Tag::Num:
                break;
        }
    }
    runtime_fail(
        std::string("native N0 ") + opcode + " does not support "
        + tag_name(left.tag) + " and " + tag_name(right.tag) + " operands");
}

Value load_constant(const CodeObject& code, std::int64_t index) {
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
                std::string("native N0 does not implement constant kind ")
                + constant_kind_name(constant.kind));
    }
}

void execute(const Image& image, Frame& frame, Host& host) {
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
            case Opcode::LOAD_CONST:
                push_value(
                    frame,
                    load_constant(
                        code, operand_integer(instruction, "const")));
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
                push_value(frame, arithmetic_add(left, right));
                break;
            }
            case Opcode::SUB: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_sub(left, right));
                break;
            }
            case Opcode::MUL: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_mul(left, right));
                break;
            }
            case Opcode::DIV: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_div(left, right));
                break;
            }
            case Opcode::MOD: {
                const Value right = pop_value(frame);
                const Value left = pop_value(frame);
                push_value(frame, arithmetic_mod(left, right));
                break;
            }
            case Opcode::NEG:
                push_value(frame, arithmetic_negate(pop_value(frame)));
                break;
            case Opcode::NOT:
                push_value(frame, make_bool(!truthy(pop_value(frame))));
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
            case Opcode::CALL: {
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
                if (site.name != "print" && site.name != "println") {
                    runtime_fail(
                        "native N0 does not implement call '" + site.name
                        + "'");
                }
                if (site.name == "print" && site.positional_count < 1) {
                    runtime_fail(
                        "print received too few arguments: expected at "
                        "least 1, got 0");
                }
                const std::size_t count = site.positional_count;
                if (frame.stack.size() < count) {
                    runtime_fail("stack underflow in CALL");
                }
                std::vector<Value> arguments(count);
                for (std::size_t index = 0; index < count; ++index) {
                    arguments[count - 1 - index] = pop_value(frame);
                }
                std::string text;
                for (const Value& value : arguments) {
                    text += format_value(value);
                }
                if (site.name == "println") {
                    text.push_back('\n');
                }
                host.write(text);
                push_value(frame, make_int(static_cast<std::int64_t>(count)));
                break;
            }
            case Opcode::RETURN:
                (void)pop_value(frame);
                return;
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

} // namespace

int run_embedded_image(
    const std::uint8_t* data, std::size_t size, Host& host) {
    try {
        const Image image = parse_image(data, size);
        verify_image(image);
        const CodeObject& code = image.codes[image.entry_code];
        Frame frame;
        frame.code = &code;
        frame.locals.assign(code.local_count, make_undef());
        frame.stack.reserve(code.max_stack);
        frame.ip = 0;
        execute(image, frame, host);
        return 0;
    } catch (const ImageError& error) {
        host.write_error(
            std::string("native image error: ") + error.what() + "\n");
        return 1;
    } catch (const VerificationError& error) {
        host.write_error(
            std::string("native verifier error: ") + error.what() + "\n");
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

} // namespace pwb
