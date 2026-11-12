#include "pwb/verifier.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <set>
#include <string>
#include <string_view>
#include <vector>

#include "pwb/error.hpp"
#include "pwb/opcodes.hpp"
#include "pwb/opcodes_generated.hpp"

namespace pwb {
namespace {

// Python verifier rules are the source of truth. This file ports
// _check_metadata, _check_spans, _check_exception_ranges, _check_operands,
// _check_target, _check_image_operand, _check_reference_lifetime,
// _analyze_stack, _successors, _successor_heights,
// _instruction_stack_effect and _call_argument_count.
//
// Rules intentionally not ported yet: none of the Python metadata rules are
// skipped except the negative count checks, because the native fields are
// unsigned. Constant JSON text is compared literally instead of decoding it
// to a Python object, which is stricter for crafted images but identical for
// compiler output.
constexpr std::int64_t kFrameResourceLimit = 1000000;

struct CodeAnalysis {
    std::vector<DecodedInstruction> instructions;
    // starts[offset] is 1 for instruction starts. starts[bytecode.size()] is
    // also 1 so the end position is easy to test, but jump target checks must
    // reject the end explicitly, matching Python.
    std::vector<std::uint8_t> starts;
};

std::string code_label(const CodeObject& code) {
    return code.qualname.empty() ? code.name : code.qualname;
}

[[noreturn]] void fail(
    const CodeObject& code, const std::string& message, long offset = -1,
    const char* opcode = nullptr) {
    std::string text = code_label(code);
    if (offset >= 0) {
        text += "@" + std::to_string(offset);
    }
    if (opcode != nullptr && opcode[0] != '\0') {
        text += " ";
        text += opcode;
    }
    text += ": " + message;
    throw VerificationError(text);
}

CodeAnalysis decode_code(const CodeObject& code) {
    CodeAnalysis analysis;
    analysis.starts.assign(code.bytecode.size() + 1, 0);
    std::uint32_t offset = 0;
    while (offset < code.bytecode.size()) {
        analysis.starts[offset] = 1;
        DecodedInstruction instruction;
        try {
            instruction = decode_instruction(code.bytecode, offset);
        } catch (const DecodeError& error) {
            fail(code, error.what(), static_cast<long>(offset));
        }
        if (instruction.next_offset <= offset) {
            fail(code, "instruction did not advance", static_cast<long>(offset),
                 instruction.spec->name);
        }
        analysis.instructions.push_back(instruction);
        offset = instruction.next_offset;
    }
    if (offset != code.bytecode.size()) {
        fail(code, "instruction stream ended in the middle of an instruction",
             static_cast<long>(offset));
    }
    analysis.starts[code.bytecode.size()] = 1;
    return analysis;
}

const DecodedInstruction* instruction_at(
    const CodeAnalysis& analysis, std::uint32_t offset) {
    const auto found = std::lower_bound(
        analysis.instructions.begin(), analysis.instructions.end(), offset,
        [](const DecodedInstruction& instruction, std::uint32_t value) {
            return instruction.offset < value;
        });
    if (found == analysis.instructions.end() || found->offset != offset) {
        return nullptr;
    }
    return &*found;
}

bool is_instruction_start(
    const CodeAnalysis& analysis, std::int64_t offset) {
    if (offset < 0 || analysis.starts.empty()) {
        return false;
    }
    // starts also holds the code end sentinel. Python's starts set does not,
    // so a jump, catch or finally target may never be the code end.
    const auto value = static_cast<std::uint64_t>(offset);
    return value + 1 < analysis.starts.size() && analysis.starts[value] != 0;
}

const DecodedOperand* operand_named(
    const DecodedInstruction& instruction, const char* name) {
    return instruction.find(name);
}

// ---------------------------------------------------------------------------
// Metadata and table checks.

void check_metadata(const CodeObject& code, const Image& image) {
    if (code.local_count > kFrameResourceLimit) {
        fail(
            code,
            "local_count " + std::to_string(code.local_count)
                + " exceeds the verifier frame limit of "
                + std::to_string(kFrameResourceLimit));
    }
    if (code.capture_count > kFrameResourceLimit) {
        fail(
            code,
            "capture_count " + std::to_string(code.capture_count)
                + " exceeds the verifier frame limit of "
                + std::to_string(kFrameResourceLimit));
    }
    if (code.max_stack > kFrameResourceLimit) {
        fail(
            code,
            "max_stack " + std::to_string(code.max_stack)
                + " exceeds the verifier frame limit of "
                + std::to_string(kFrameResourceLimit));
    }
    if (!code.parameter_names.empty()
        && code.parameter_names.size() != code.parameter_count) {
        fail(
            code,
            "parameter name count " + std::to_string(code.parameter_names.size())
                + " does not match parameter_count "
                + std::to_string(code.parameter_count));
    }
    if (code.return_spec >= 0
        && static_cast<std::uint64_t>(code.return_spec)
            >= image.type_specs.size()) {
        fail(
            code,
            "return spec index out of range: "
                + std::to_string(code.return_spec));
    }
}

void check_spans(
    const CodeObject& code, const CodeAnalysis& analysis) {
    if (code.span_table.empty()) {
        return;
    }
    if (code.span_table.size() != analysis.instructions.size()) {
        fail(
            code,
            "span table length " + std::to_string(code.span_table.size())
                + " does not match instruction count "
                + std::to_string(analysis.instructions.size()));
    }
    if (!code.spans.empty()) {
        for (const std::uint32_t index : code.span_table) {
            if (static_cast<std::uint64_t>(index) >= code.spans.size()) {
                fail(
                    code,
                    "span index out of range: " + std::to_string(index));
            }
        }
    }
}

void check_exception_ranges(
    const CodeObject& code, const CodeAnalysis& analysis) {
    const std::int64_t end =
        static_cast<std::int64_t>(code.bytecode.size());
    for (const ExceptionEntry& entry : code.exception_table) {
        if (entry.start_ip < 0 || entry.end_ip < 0) {
            fail(code, "exception range offsets must not be negative");
        }
        if (!is_instruction_start(analysis, entry.start_ip)) {
            fail(
                code,
                "exception start is not an instruction boundary: "
                    + std::to_string(entry.start_ip));
        }
        if (entry.end_ip > end) {
            fail(
                code,
                "exception end is outside the code object: "
                    + std::to_string(entry.end_ip));
        }
        if (entry.end_ip != end
            && !is_instruction_start(analysis, entry.end_ip)) {
            fail(
                code,
                "exception end is not an instruction boundary: "
                    + std::to_string(entry.end_ip));
        }
        if (entry.start_ip >= entry.end_ip) {
            fail(code, "exception start must be smaller than exception end");
        }
        if (entry.catch_ip >= 0
            && !is_instruction_start(analysis, entry.catch_ip)) {
            fail(
                code,
                "exception catch target is not an instruction boundary: "
                    + std::to_string(entry.catch_ip));
        }
        if (entry.finally_ip >= 0
            && !is_instruction_start(analysis, entry.finally_ip)) {
            fail(
                code,
                "exception finally target is not an instruction boundary: "
                    + std::to_string(entry.finally_ip));
        }
        if (entry.resume_ip >= 0 && entry.resume_ip != end
            && !is_instruction_start(analysis, entry.resume_ip)) {
            fail(
                code,
                "exception resume target is not an instruction boundary: "
                    + std::to_string(entry.resume_ip));
        }
    }
}

// ---------------------------------------------------------------------------
// Operand checks.

void check_constant_index(
    const CodeObject& code, const DecodedInstruction& instruction,
    std::int64_t index) {
    if (index < 0
        || static_cast<std::uint64_t>(index) >= code.constants.size()) {
        fail(
            code,
            "constant index " + std::to_string(index)
                + " is out of range for " + std::to_string(code.constants.size())
                + " constants",
            instruction.offset, instruction.spec->name);
    }
}

void check_target(
    const CodeObject& code, const DecodedInstruction& instruction,
    const char* operand_name, std::int64_t target,
    const CodeAnalysis& analysis) {
    const std::int64_t end =
        static_cast<std::int64_t>(code.bytecode.size());
    if (std::string_view(instruction.spec->name) == "TRY_BEGIN") {
        if (target < 0) {
            return;
        }
        if (!is_instruction_start(analysis, target)) {
            fail(
                code,
                std::string(operand_name)
                    + " target is not an instruction boundary: "
                    + std::to_string(target),
                instruction.offset, instruction.spec->name);
        }
        return;
    }
    if (target < 0 || target >= end) {
        fail(
            code, "jump target out of range: " + std::to_string(target),
            instruction.offset, instruction.spec->name);
    }
    if (!is_instruction_start(analysis, target)) {
        fail(
            code,
            "jump target is not an instruction boundary: "
                + std::to_string(target),
            instruction.offset, instruction.spec->name);
    }
}

std::int64_t image_operand_value(const DecodedOperand& operand) {
    if (!operand.is_float) {
        return operand.integer;
    }
    // Python passes int(value) to _check_image_operand. Only the sign matters
    // here, because float literals use the unlimited value kind.
    if (!std::isfinite(operand.number)) {
        return 0;
    }
    if (operand.number <= -1.0) {
        return -1;
    }
    if (operand.number >= 1.0) {
        return 1;
    }
    return 0;
}

void check_image_operand(
    const CodeObject& code, const DecodedInstruction& instruction,
    const char* operand_name, OperandKind kind, std::int64_t value,
    const Image& image) {
    if (value < 0) {
        fail(
            code,
            std::string(operand_name) + " index must not be negative: "
                + std::to_string(value),
            instruction.offset, instruction.spec->name);
    }
    std::size_t limit = 0;
    bool has_limit = true;
    switch (kind) {
        case OperandKind::Call:
            limit = image.call_sites.size();
            break;
        case OperandKind::Pattern:
            limit = image.patterns.size();
            break;
        case OperandKind::Module:
            limit = image.modules.size();
            break;
        case OperandKind::Type:
            limit = image.types.size();
            break;
        case OperandKind::Trait:
            limit = image.traits.size();
            break;
        case OperandKind::Field:
        case OperandKind::Name:
        case OperandKind::Export:
            limit = image.global_names.size();
            break;
        default:
            // Python leaves value, event, flags and host without a table
            // limit. Host only gets the negative check above.
            has_limit = false;
            break;
    }
    if (!has_limit || limit == 0) {
        return;
    }
    if (static_cast<std::uint64_t>(value) >= limit) {
        fail(
            code,
            std::string(operand_name) + " index out of range: "
                + std::to_string(value),
            instruction.offset, instruction.spec->name);
    }
}

void check_pattern_slots(
    const CodeObject& code, const DecodedInstruction& instruction,
    const PatternDescriptor& pattern) {
    for (const auto& binding : pattern.bindings) {
        if (binding.second >= code.local_count) {
            fail(
                code,
                "pattern binding slot " + std::to_string(binding.second)
                    + " is outside local_count "
                    + std::to_string(code.local_count),
                instruction.offset, instruction.spec->name);
        }
    }
    if (pattern.rest_slot >= 0
        && static_cast<std::uint64_t>(pattern.rest_slot)
            >= code.local_count) {
        fail(
            code,
            "pattern rest slot " + std::to_string(pattern.rest_slot)
                + " is outside local_count " + std::to_string(code.local_count),
            instruction.offset, instruction.spec->name);
    }
    for (const PatternDescriptor& nested : pattern.nested) {
        check_pattern_slots(code, instruction, nested);
    }
    for (const auto& field : pattern.fields) {
        check_pattern_slots(code, instruction, field.second);
    }
}

void check_operands(
    const CodeObject& code, const Image& image,
    const CodeAnalysis& analysis) {
    for (const DecodedInstruction& instruction : analysis.instructions) {
        const OpcodeSpec& spec = *instruction.spec;
        for (std::uint8_t index = 0; index < spec.operand_count; ++index) {
            const OperandSpec& operand = spec.operands[index];
            const std::int64_t value = instruction.operands[index].integer;
            switch (operand.kind) {
                case OperandKind::Const:
                case OperandKind::Spec:
                    check_constant_index(code, instruction, value);
                    break;
                case OperandKind::Slot:
                    if (value < 0
                        || static_cast<std::uint64_t>(value)
                            >= code.local_count) {
                        fail(
                            code,
                            "slot " + std::to_string(value)
                                + " is outside local_count "
                                + std::to_string(code.local_count),
                            instruction.offset, spec.name);
                    }
                    break;
                case OperandKind::Target:
                    check_target(
                        code, instruction, operand.name, value, analysis);
                    break;
                default:
                    check_image_operand(
                        code, instruction, operand.name, operand.kind,
                        image_operand_value(instruction.operands[index]),
                        image);
                    break;
            }
        }
        const std::string_view name(spec.name);
        if (name == "LOAD_CAPTURE") {
            const DecodedOperand* operand =
                operand_named(instruction, "index");
            if (operand != nullptr
                && (operand->integer < 0
                    || static_cast<std::uint64_t>(operand->integer)
                        >= code.capture_count)) {
                fail(
                    code,
                    "capture index " + std::to_string(operand->integer)
                        + " is outside capture_count "
                        + std::to_string(code.capture_count),
                    instruction.offset, spec.name);
            }
        }
        if (name == "DECLARE_FUNCTION" || name == "MAKE_FUNCTION") {
            const DecodedOperand* operand =
                operand_named(instruction, "function");
            if (operand != nullptr
                && (operand->integer < 0
                    || static_cast<std::uint64_t>(operand->integer)
                        >= image.functions.size())) {
                fail(
                    code,
                    "function index out of range: "
                        + std::to_string(operand->integer),
                    instruction.offset, spec.name);
            }
        }
        if (name == "DECLARE_EXTERN") {
            const DecodedOperand* operand =
                operand_named(instruction, "extern");
            if (operand != nullptr
                && (operand->integer < 0
                    || static_cast<std::uint64_t>(operand->integer)
                        >= code.constants.size())) {
                fail(
                    code,
                    "extern index out of range: "
                        + std::to_string(operand->integer),
                    instruction.offset, spec.name);
            }
        }
        if (name == "NEW_ENUM" || name == "LOAD_ENUM_MEMBER") {
            const DecodedOperand* type_operand =
                operand_named(instruction, "enum");
            const DecodedOperand* variant_operand =
                operand_named(instruction, "variant");
            if (type_operand != nullptr && variant_operand != nullptr
                && type_operand->integer >= 0
                && static_cast<std::uint64_t>(type_operand->integer)
                    < image.types.size()) {
                const std::vector<std::string>& variants =
                    image.types[static_cast<std::size_t>(
                        type_operand->integer)].variants;
                if (!variants.empty()
                    && (variant_operand->integer < 0
                        || static_cast<std::uint64_t>(
                               variant_operand->integer)
                            >= variants.size())) {
                    fail(
                        code,
                        "enum variant index out of range: "
                            + std::to_string(variant_operand->integer),
                        instruction.offset, spec.name);
                }
            }
        }
        if (name == "MATCH") {
            const DecodedOperand* operand =
                operand_named(instruction, "pattern");
            if (operand != nullptr && operand->integer >= 0
                && static_cast<std::uint64_t>(operand->integer)
                    < image.patterns.size()) {
                check_pattern_slots(
                    code, instruction,
                    image.patterns[static_cast<std::size_t>(
                        operand->integer)]);
            }
        }
        if (name == "LOAD_MODULE_MEMBER") {
            const DecodedOperand* module_operand =
                operand_named(instruction, "module");
            const DecodedOperand* export_operand =
                operand_named(instruction, "export");
            if (module_operand != nullptr && export_operand != nullptr
                && module_operand->integer >= 0
                && static_cast<std::uint64_t>(module_operand->integer)
                    < image.modules.size()) {
                const std::vector<std::pair<std::string, std::string>>& exports =
                    image.modules[static_cast<std::size_t>(
                        module_operand->integer)].exports;
                if (export_operand->integer < 0
                    || static_cast<std::uint64_t>(export_operand->integer)
                        >= exports.size()) {
                    fail(
                        code,
                        "module export index out of range: "
                            + std::to_string(export_operand->integer),
                        instruction.offset, spec.name);
                }
            }
        }
    }
}

// _REFERENCE_STORES and _REFERENCE_PRODUCERS from the Python verifier.
bool is_reference_store(std::string_view name) {
    return name == "STORE_LOCAL" || name == "STORE_GLOBAL"
        || name == "STORE_NAME" || name == "STORE_FIELD"
        || name == "STORE_REF" || name == "INDEX_SET"
        || name == "MAKE_ARRAY" || name == "MAKE_ARRAY_TYPED"
        || name == "MAKE_TUPLE" || name == "MAKE_TUPLE_TYPED"
        || name == "MAKE_MAP" || name == "MAKE_MAP_TYPED"
        || name == "MAKE_SET" || name == "MAKE_SET_TYPED";
}

bool is_reference_producer(std::string_view name) {
    return name == "REF_LOCAL" || name == "REF_GLOBAL" || name == "REF_FIELD"
        || name == "REF_INDEX";
}

void check_reference_lifetime(
    const CodeObject& code, const CodeAnalysis& analysis) {
    for (std::size_t index = 1; index < analysis.instructions.size();
         ++index) {
        const DecodedInstruction& current = analysis.instructions[index];
        const DecodedInstruction& previous = analysis.instructions[index - 1];
        if (is_reference_store(current.spec->name)
            && is_reference_producer(previous.spec->name)) {
            fail(
                code,
                std::string(current.spec->name)
                    + " cannot store a reference produced by "
                    + previous.spec->name,
                current.offset, current.spec->name);
        }
    }
}

// ---------------------------------------------------------------------------
// Stack effect helpers.

std::int64_t count_operand(const DecodedInstruction& instruction) {
    const DecodedOperand* operand = operand_named(instruction, "count");
    if (operand == nullptr || operand->integer <= 0) {
        return 0;
    }
    return operand->integer;
}

bool is_call_opcode(std::string_view name) {
    return name == "CALL" || name == "CALL_VALUE" || name == "CALL_METHOD"
        || name == "CALL_STATIC" || name == "CALL_MODULE"
        || name == "CALL_NATIVE" || name == "CALL_BUILTIN"
        || name == "CALL_TRAIT" || name == "CALL_OPERATOR"
        || name == "CALL_EXTERN" || name == "CALL_ASYNC"
        || name == "CALL_ASYNC_METHOD" || name == "SPAWN"
        || name == "HOST_CALL";
}

bool is_receiver_call(std::string_view name) {
    return name == "CALL_METHOD" || name == "CALL_TRAIT"
        || name == "CALL_OPERATOR" || name == "CALL_MODULE"
        || name == "CALL_VALUE";
}

std::int64_t call_argument_count(
    const Image& image, const DecodedInstruction& instruction) {
    const DecodedOperand* operand = operand_named(instruction, "call");
    if (operand == nullptr) {
        return 0;
    }
    const std::int64_t index = operand->integer;
    if (index < 0
        || static_cast<std::uint64_t>(index) >= image.call_sites.size()) {
        return 0;
    }
    const CallSite& site = image.call_sites[static_cast<std::size_t>(index)];
    std::int64_t count = site.argument_kinds.empty()
        ? static_cast<std::int64_t>(site.positional_count)
        : static_cast<std::int64_t>(site.argument_kinds.size());
    const std::string_view name(instruction.spec->name);
    if (name == "CALL_VALUE") {
        count += 1;
    } else if (is_receiver_call(name)) {
        count += 1;
    } else if (name == "SPAWN" && site.method_ast != "null"
               && site.dispatch != "spawn_static") {
        count += 1;
    } else if (name == "CALL_ASYNC"
               && (site.dispatch == "method" || site.dispatch == "module"
                   || site.dispatch == "value")) {
        count += 1;
    } else if (name == "CALL_ASYNC_METHOD"
               && site.dispatch == "method") {
        count += 1;
    }
    return std::max<std::int64_t>(0, count);
}

// Minimal JSON scanning for the MAKE_ERROR descriptor. Python decodes the
// descriptor to a dict and reads argument_count. We only need that one field,
// so the scanner locates it at the top level of a JSON object and skips every
// other value. A descriptor that is not a JSON object has no inputs, while an
// object without argument_count defaults to one input, matching Python.
void skip_json_space(std::string_view text, std::size_t& position) {
    while (position < text.size()
           && (text[position] == ' ' || text[position] == '\t'
               || text[position] == '\n' || text[position] == '\r')) {
        ++position;
    }
}

bool skip_json_string(std::string_view text, std::size_t& position) {
    if (position >= text.size() || text[position] != '"') {
        return false;
    }
    ++position;
    while (position < text.size()) {
        const char value = text[position++];
        if (value == '"') {
            return true;
        }
        if (value == '\\') {
            if (position >= text.size()) {
                return false;
            }
            const char escape = text[position++];
            if (escape == 'u') {
                if (position + 4 > text.size()) {
                    return false;
                }
                for (int digit = 0; digit < 4; ++digit) {
                    const char hex = text[position + static_cast<std::size_t>(digit)];
                    const bool valid = (hex >= '0' && hex <= '9')
                        || (hex >= 'a' && hex <= 'f')
                        || (hex >= 'A' && hex <= 'F');
                    if (!valid) {
                        return false;
                    }
                }
                position += 4;
            } else if (escape != '"' && escape != '\\' && escape != '/'
                       && escape != 'b' && escape != 'f'
                       && escape != 'n' && escape != 'r'
                       && escape != 't') {
                return false;
            }
            continue;
        }
        if (static_cast<unsigned char>(value) < 0x20u) {
            return false;
        }
    }
    return false;
}

bool skip_json_value(
    std::string_view text, std::size_t& position, int depth) {
    if (depth > 64) {
        return false;
    }
    skip_json_space(text, position);
    if (position >= text.size()) {
        return false;
    }
    const char first = text[position];
    if (first == '"') {
        return skip_json_string(text, position);
    }
    if (first == '{') {
        ++position;
        skip_json_space(text, position);
        if (position < text.size() && text[position] == '}') {
            ++position;
            return true;
        }
        while (position < text.size()) {
            skip_json_space(text, position);
            if (!skip_json_string(text, position)) {
                return false;
            }
            skip_json_space(text, position);
            if (position >= text.size() || text[position] != ':') {
                return false;
            }
            ++position;
            if (!skip_json_value(text, position, depth + 1)) {
                return false;
            }
            skip_json_space(text, position);
            if (position >= text.size()) {
                return false;
            }
            if (text[position] == ',') {
                ++position;
                continue;
            }
            if (text[position] == '}') {
                ++position;
                return true;
            }
            return false;
        }
        return false;
    }
    if (first == '[') {
        ++position;
        skip_json_space(text, position);
        if (position < text.size() && text[position] == ']') {
            ++position;
            return true;
        }
        while (position < text.size()) {
            if (!skip_json_value(text, position, depth + 1)) {
                return false;
            }
            skip_json_space(text, position);
            if (position >= text.size()) {
                return false;
            }
            if (text[position] == ',') {
                ++position;
                continue;
            }
            if (text[position] == ']') {
                ++position;
                return true;
            }
            return false;
        }
        return false;
    }
    if (text.compare(position, 4, "true") == 0) {
        position += 4;
        return true;
    }
    if (text.compare(position, 5, "false") == 0) {
        position += 5;
        return true;
    }
    if (text.compare(position, 4, "null") == 0) {
        position += 4;
        return true;
    }
    const std::size_t start = position;
    if (text[position] == '-' || text[position] == '+') {
        ++position;
    }
    while (position < text.size()
           && ((text[position] >= '0' && text[position] <= '9')
               || text[position] == '.' || text[position] == 'e'
               || text[position] == 'E' || text[position] == '+'
               || text[position] == '-')) {
        ++position;
    }
    return position > start;
}

bool read_argument_count(std::string_view text, std::int64_t& count) {
    std::size_t position = 0;
    skip_json_space(text, position);
    if (position >= text.size() || text[position] != '{') {
        return false;
    }
    ++position;
    skip_json_space(text, position);
    if (position < text.size() && text[position] == '}') {
        return false;
    }
    while (position < text.size()) {
        skip_json_space(text, position);
        const std::size_t key_start = position;
        if (!skip_json_string(text, position)) {
            return false;
        }
        const std::string_view raw_key =
            text.substr(key_start + 1, position - key_start - 2);
        skip_json_space(text, position);
        if (position >= text.size() || text[position] != ':') {
            return false;
        }
        ++position;
        skip_json_space(text, position);
        if (raw_key == "argument_count") {
            std::int64_t value = 0;
            const char* begin = text.data() + position;
            const char* end = text.data() + text.size();
            const auto parsed = std::from_chars(begin, end, value);
            if (parsed.ec != std::errc()) {
                return false;
            }
            count = value;
            return true;
        }
        if (!skip_json_value(text, position, 0)) {
            return false;
        }
        skip_json_space(text, position);
        if (position >= text.size()) {
            return false;
        }
        if (text[position] == ',') {
            ++position;
            continue;
        }
        return false;
    }
    return false;
}

bool json_is_object(std::string_view text) {
    std::size_t position = 0;
    skip_json_space(text, position);
    return position < text.size() && text[position] == '{';
}

std::int64_t make_error_argument_count(
    const CodeObject& code, const DecodedInstruction& instruction) {
    const DecodedOperand* operand = operand_named(instruction, "spec");
    if (operand == nullptr || operand->integer < 0
        || static_cast<std::uint64_t>(operand->integer)
            >= code.constants.size()) {
        return 0;
    }
    const Constant& descriptor =
        code.constants[static_cast<std::size_t>(operand->integer)];
    const bool json_kind = descriptor.kind == ConstantKind::Ast
        || descriptor.kind == ConstantKind::Descriptor
        || descriptor.kind == ConstantKind::Spec
        || descriptor.kind == ConstantKind::Extern;
    if (!json_kind || !json_is_object(descriptor.text)) {
        return 0;
    }
    std::int64_t count = 1;
    if (!read_argument_count(descriptor.text, count)) {
        return 1;
    }
    return count;
}

struct StackEffect {
    std::int64_t input = 0;
    std::int64_t output = 0;
};

StackEffect instruction_stack_effect(
    const CodeObject& code, const Image& image,
    const DecodedInstruction& instruction) {
    const OpcodeSpec& spec = *instruction.spec;
    if (spec.stack_in >= 0) {
        return {spec.stack_in, spec.stack_out};
    }
    const std::string_view name(spec.name);
    if (name == "ROT") {
        const std::int64_t count = count_operand(instruction);
        return {count, count};
    }
    if (name == "MAKE_ARRAY" || name == "MAKE_ARRAY_TYPED"
        || name == "MAKE_TUPLE" || name == "MAKE_TUPLE_TYPED"
        || name == "MAKE_MAP" || name == "MAKE_MAP_TYPED"
        || name == "MAKE_SET" || name == "MAKE_SET_TYPED"
        || name == "CONCAT_STR") {
        return {count_operand(instruction), 1};
    }
    if (is_call_opcode(name) || name == "CONSTRUCT") {
        return {call_argument_count(image, instruction), 1};
    }
    if (name == "MAKE_ERROR") {
        return {make_error_argument_count(code, instruction), 1};
    }
    return {0, spec.stack_out};
}

// ---------------------------------------------------------------------------
// Stack height dataflow.

bool is_conditional_jump(std::string_view name) {
    return name == "JUMP_IF_FALSE" || name == "JUMP_IF_TRUE"
        || name == "JUMP_IF_FALSE_KEEP" || name == "JUMP_IF_TRUE_KEEP"
        || name == "JUMP_IF_NOVA" || name == "JUMP_IF_NOT_NOVA";
}

std::vector<std::uint32_t> successors(
    const DecodedInstruction& instruction, std::uint32_t end) {
    const std::string_view name(instruction.spec->name);
    if (name == "JUMP") {
        const DecodedOperand* target = operand_named(instruction, "target");
        if (target == nullptr) {
            return {};
        }
        return {static_cast<std::uint32_t>(target->integer)};
    }
    if (is_conditional_jump(name) || name == "MATCH"
        || name == "ITER_NEXT" || name == "JUMP_IF_TRANSFER") {
        const DecodedOperand* target = operand_named(instruction, "target");
        if (target == nullptr) {
            return {};
        }
        const std::uint32_t target_offset =
            static_cast<std::uint32_t>(target->integer);
        if (instruction.next_offset <= end
            && instruction.next_offset != target_offset) {
            return {target_offset, instruction.next_offset};
        }
        return {target_offset};
    }
    if (name == "RETURN" || name == "THROW" || name == "RETHROW") {
        return {};
    }
    if (instruction.next_offset <= end) {
        return {instruction.next_offset};
    }
    return {};
}

struct SuccessorHeight {
    std::uint32_t offset = 0;
    std::int64_t height = 0;
};

std::vector<SuccessorHeight> successor_heights(
    const DecodedInstruction& instruction, std::uint32_t end,
    std::int64_t height, std::int64_t result_height) {
    if (std::string_view(instruction.spec->name) == "ITER_NEXT") {
        const DecodedOperand* target = operand_named(instruction, "target");
        if (target == nullptr) {
            return {};
        }
        const std::uint32_t target_offset =
            static_cast<std::uint32_t>(target->integer);
        std::vector<SuccessorHeight> pairs;
        pairs.push_back(
            {target_offset, std::max<std::int64_t>(0, height - 1)});
        if (instruction.next_offset <= end
            && instruction.next_offset != target_offset) {
            pairs.push_back({instruction.next_offset, height + 1});
        }
        return pairs;
    }
    std::vector<SuccessorHeight> pairs;
    for (const std::uint32_t offset : successors(instruction, end)) {
        pairs.push_back({offset, result_height});
    }
    return pairs;
}

std::int64_t analyze_stack(
    const CodeObject& code, const Image& image,
    const CodeAnalysis& analysis) {
    const std::uint32_t end =
        static_cast<std::uint32_t>(code.bytecode.size());
    std::vector<std::int64_t> heights(code.bytecode.size(), -1);
    std::set<std::uint32_t> worklist;
    heights[0] = 0;
    worklist.insert(0);
    std::int64_t peak = 0;
    bool falls_off_end = false;
    while (!worklist.empty()) {
        const std::uint32_t offset = *worklist.begin();
        worklist.erase(worklist.begin());
        const std::int64_t height = heights[offset];
        const DecodedInstruction* instruction = instruction_at(analysis, offset);
        if (instruction == nullptr) {
            fail(
                code, "missing instruction at stack height offset",
                static_cast<long>(offset));
        }
        const std::string_view name(instruction->spec->name);
        if (is_conditional_jump(name) && height < 1) {
            fail(
                code, "conditional jump requires at least one stack value",
                offset, instruction->spec->name);
        }
        const StackEffect effect =
            instruction_stack_effect(code, image, *instruction);
        if (height < effect.input) {
            fail(
                code,
                "stack underflow: needs " + std::to_string(effect.input)
                    + " values but height is " + std::to_string(height),
                offset, instruction->spec->name);
        }
        const std::int64_t result = height - effect.input + effect.output;
        peak = std::max({peak, height, result});
        for (const SuccessorHeight& successor :
             successor_heights(*instruction, end, height, result)) {
            if (successor.offset == end) {
                falls_off_end = true;
                continue;
            }
            if (!is_instruction_start(analysis, successor.offset)) {
                fail(
                    code,
                    "jump target is not an instruction boundary: "
                        + std::to_string(successor.offset),
                    offset, instruction->spec->name);
            }
            if (successor.offset >= heights.size()) {
                continue;
            }
            const std::int64_t existing =
                heights[successor.offset];
            if (existing < 0) {
                heights[successor.offset] = successor.height;
                worklist.insert(successor.offset);
            } else if (existing != successor.height) {
                const DecodedInstruction* at =
                    instruction_at(analysis, successor.offset);
                fail(
                    code,
                    "merge mismatch at offset "
                        + std::to_string(successor.offset)
                        + ": incoming heights "
                        + std::to_string(existing) + " and "
                        + std::to_string(successor.height),
                    successor.offset,
                    at == nullptr ? nullptr : at->spec->name);
            }
        }
    }
    if (falls_off_end) {
        fail(code, "missing return: a reachable path falls off the end");
    }
    return peak;
}

void verify_code(const CodeObject& code, const Image& image) {
    check_metadata(code, image);
    if (code.bytecode.empty()) {
        fail(code, "missing return: code object is empty");
    }
    const CodeAnalysis analysis = decode_code(code);
    check_spans(code, analysis);
    check_exception_ranges(code, analysis);
    check_operands(code, image, analysis);
    check_reference_lifetime(code, analysis);
    const std::int64_t peak = analyze_stack(code, image, analysis);
    if (static_cast<std::uint64_t>(code.max_stack)
        < static_cast<std::uint64_t>(peak)) {
        fail(
            code,
            "max_stack " + std::to_string(code.max_stack)
                + " is smaller than the computed peak "
                + std::to_string(peak));
    }
}

// Compare constants for the code constant_indices cross check. Python compares
// decoded Constant values. Text constant kinds keep their deterministic JSON
// text, so identical compiler output compares equal. A crafted image with
// differently formatted but JSON equivalent text is rejected, which is
// stricter than Python.
bool constant_equal(const Constant& left, const Constant& right) {
    if (left.kind != right.kind) {
        return false;
    }
    switch (left.kind) {
        case ConstantKind::Nova:
            return true;
        case ConstantKind::Bool:
            return left.bool_value == right.bool_value;
        case ConstantKind::Int:
            return left.int_value == right.int_value;
        case ConstantKind::BigInt:
            return left.text == right.text;
        case ConstantKind::Num:
            return left.num_value == right.num_value;
        case ConstantKind::Char:
            return left.uint_value == right.uint_value;
        case ConstantKind::Str:
        case ConstantKind::Ast:
        case ConstantKind::Spec:
        case ConstantKind::Extern:
        case ConstantKind::Descriptor:
            return left.text == right.text;
        case ConstantKind::Call:
        case ConstantKind::Pattern:
        case ConstantKind::Type:
        case ConstantKind::Trait:
        case ConstantKind::Function:
            return left.uint_value == right.uint_value;
        case ConstantKind::Tuple:
            if (left.tuple.size() != right.tuple.size()) {
                return false;
            }
            for (std::size_t index = 0; index < left.tuple.size(); ++index) {
                if (!constant_equal(left.tuple[index], right.tuple[index])) {
                    return false;
                }
            }
            return true;
    }
    return false;
}

void check_constant_index_value(
    std::uint32_t value, std::size_t limit, const std::string& kind,
    const std::string& where) {
    if (static_cast<std::uint64_t>(value) >= limit) {
        throw VerificationError(
            where + ": " + kind + " index out of range: "
            + std::to_string(value));
    }
}

void check_constant_references(
    const Image& image, const Constant& constant,
    const std::string& where) {
    switch (constant.kind) {
        case ConstantKind::Call:
            check_constant_index_value(
                constant.uint_value, image.call_sites.size(), "call site",
                where);
            break;
        case ConstantKind::Pattern:
            check_constant_index_value(
                constant.uint_value, image.patterns.size(), "pattern", where);
            break;
        case ConstantKind::Type:
            check_constant_index_value(
                constant.uint_value, image.types.size(), "type", where);
            break;
        case ConstantKind::Trait:
            check_constant_index_value(
                constant.uint_value, image.traits.size(), "trait", where);
            break;
        case ConstantKind::Function:
            check_constant_index_value(
                constant.uint_value, image.functions.size(), "function",
                where);
            break;
        case ConstantKind::Tuple:
            for (std::size_t index = 0; index < constant.tuple.size();
                 ++index) {
                check_constant_references(
                    image, constant.tuple[index],
                    where + " tuple item " + std::to_string(index));
            }
            break;
        default:
            break;
    }
}

} // namespace

void verify_image(const Image& image) {
    if (image.format_version != kFormatVersion) {
        throw VerificationError(
            "image: unsupported format version: "
            + std::to_string(image.format_version));
    }
    if (image.language_version != generated::kLanguageVersion) {
        throw VerificationError(
            "image: language version \"" + image.language_version
            + "\" does not match \"" + generated::kLanguageVersion + "\"");
    }
    if (image.entry_module >= image.modules.size()) {
        throw VerificationError(
            "image: entry module index out of range: "
            + std::to_string(image.entry_module));
    }
    if (image.entry_code >= image.codes.size()) {
        throw VerificationError(
            "image: entry code index out of range: "
            + std::to_string(image.entry_code));
    }
    for (const ModuleInfo& module : image.modules) {
        if (static_cast<std::uint64_t>(module.code_index)
            >= image.codes.size()) {
            throw VerificationError(
                "image: module '" + module.name
                + "' code index out of range: "
                + std::to_string(module.code_index));
        }
    }
    for (const FunctionInfo& function : image.functions) {
        if (static_cast<std::uint64_t>(function.code_index)
            >= image.codes.size()) {
            throw VerificationError(
                "image: function '" + function.name
                + "' code index out of range: "
                + std::to_string(function.code_index));
        }
    }
    for (std::size_t index = 0; index < image.call_sites.size(); ++index) {
        const CallSite& site = image.call_sites[index];
        if (site.return_spec >= 0
            && static_cast<std::uint64_t>(site.return_spec)
                >= image.type_specs.size()) {
            throw VerificationError(
                "image: call site " + std::to_string(index)
                + " return spec index out of range: "
                + std::to_string(site.return_spec));
        }
    }
    for (std::size_t index = 0; index < image.constants.size(); ++index) {
        check_constant_references(
            image, image.constants[index],
            "image constant " + std::to_string(index));
    }
    for (const CodeObject& code : image.codes) {
        verify_code(code, image);
        if (!code.constant_indices.empty()) {
            if (image.constants.empty()) {
                fail(
                    code,
                    "constant indices reference an empty image constant pool");
            }
            if (!code.constants.empty()
                && code.constant_indices.size() != code.constants.size()) {
                fail(
                    code,
                    "constant index count "
                        + std::to_string(code.constant_indices.size())
                        + " does not match the inline constant count "
                        + std::to_string(code.constants.size()));
            }
            for (std::size_t position = 0;
                 position < code.constant_indices.size(); ++position) {
                const std::uint32_t index = code.constant_indices[position];
                if (static_cast<std::uint64_t>(index)
                    >= image.constants.size()) {
                    fail(
                        code,
                        "constant index " + std::to_string(index)
                            + " is out of range");
                }
                if (position < code.constants.size()
                    && !constant_equal(
                        image.constants[index], code.constants[position])) {
                    fail(
                        code,
                        "constant index " + std::to_string(index)
                            + " does not match inline constant "
                            + std::to_string(position));
                }
            }
        }
        for (std::size_t position = 0; position < code.constants.size();
             ++position) {
            check_constant_references(
                image, code.constants[position],
                code.name + " constant " + std::to_string(position));
        }
    }
}

} // namespace pwb
