#include "pwb/disasm.hpp"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>
#include <string_view>
#include <vector>

#include "pwb/error.hpp"
#include "pwb/opcodes.hpp"
#include "pwb/value.hpp"

namespace pwb {
namespace {

std::size_t code_point_count(std::string_view text) {
    std::size_t count = 0;
    for (const char byte : text) {
        if ((static_cast<unsigned char>(byte) & 0xC0u) != 0x80u) {
            ++count;
        }
    }
    return count;
}

std::size_t byte_offset_for_code_points(
    std::string_view text, std::size_t wanted) {
    std::size_t seen = 0;
    for (std::size_t index = 0; index < text.size(); ++index) {
        if ((static_cast<unsigned char>(text[index]) & 0xC0u) != 0x80u) {
            if (seen == wanted) {
                return index;
            }
            ++seen;
        }
    }
    return text.size();
}

std::string short_text(std::string_view text, std::size_t limit = 60) {
    if (code_point_count(text) <= limit) {
        return std::string(text);
    }
    const std::size_t cut = byte_offset_for_code_points(text, limit - 3);
    std::string result(text.substr(0, cut));
    result += "...";
    return result;
}

char32_t next_code_point(std::string_view text, std::size_t& index) {
    if (index >= text.size()) {
        return 0;
    }
    const unsigned char first = static_cast<unsigned char>(text[index++]);
    if (first < 0x80u) {
        return first;
    }
    std::size_t extra = 0;
    char32_t code_point = 0;
    if ((first & 0xE0u) == 0xC0u) {
        extra = 1;
        code_point = first & 0x1Fu;
    } else if ((first & 0xF0u) == 0xE0u) {
        extra = 2;
        code_point = first & 0x0Fu;
    } else if ((first & 0xF8u) == 0xF0u) {
        extra = 3;
        code_point = first & 0x07u;
    } else {
        return 0xFFFD;
    }
    for (std::size_t continuation = 0; continuation < extra; ++continuation) {
        if (index >= text.size()) {
            return 0xFFFD;
        }
        const unsigned char next = static_cast<unsigned char>(text[index++]);
        if ((next & 0xC0u) != 0x80u) {
            return 0xFFFD;
        }
        code_point = (code_point << 6) | (next & 0x3Fu);
    }
    return code_point;
}

void append_hex4(std::string& out, std::uint32_t value) {
    char buffer[8];
    std::snprintf(buffer, sizeof(buffer), "\\u%04x", value);
    out += buffer;
}

void append_json_quoted(std::string& out, std::string_view text) {
    out.push_back('"');
    std::size_t index = 0;
    while (index < text.size()) {
        const char32_t code_point = next_code_point(text, index);
        switch (code_point) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case 0x08: out += "\\b"; break;
            case 0x0C: out += "\\f"; break;
            case 0x0A: out += "\\n"; break;
            case 0x0D: out += "\\r"; break;
            case 0x09: out += "\\t"; break;
            default:
                if (code_point < 0x20u || code_point > 0x7Eu) {
                    if (code_point > 0xFFFFu) {
                        const std::uint32_t adjusted = code_point - 0x10000u;
                        append_hex4(out, 0xD800u + (adjusted >> 10));
                        append_hex4(out, 0xDC00u + (adjusted & 0x3FFu));
                    } else {
                        append_hex4(out, static_cast<std::uint32_t>(code_point));
                    }
                } else {
                    out.push_back(static_cast<char>(code_point));
                }
                break;
        }
    }
    out.push_back('"');
}

std::string python_repr(std::string_view text) {
    const bool contains_single = text.find('\'') != std::string_view::npos;
    const bool contains_double = text.find('"') != std::string_view::npos;
    const char quote = (contains_single && !contains_double) ? '"' : '\'';
    std::string out;
    out.push_back(quote);
    std::size_t index = 0;
    while (index < text.size()) {
        const char32_t code_point = next_code_point(text, index);
        if (code_point == static_cast<char32_t>(quote)
            || code_point == static_cast<char32_t>('\\')) {
            out.push_back('\\');
            out.push_back(static_cast<char>(code_point));
        } else if (code_point == 0x0A) {
            out += "\\n";
        } else if (code_point == 0x0D) {
            out += "\\r";
        } else if (code_point == 0x09) {
            out += "\\t";
        } else if (code_point < 0x20u || code_point == 0x7Fu) {
            char buffer[8];
            std::snprintf(
                buffer, sizeof(buffer), "\\x%02x",
                static_cast<unsigned int>(code_point));
            out += buffer;
        } else if (code_point < 0x80u) {
            out.push_back(static_cast<char>(code_point));
        } else {
            append_utf8(out, code_point);
        }
    }
    out.push_back(quote);
    return out;
}

std::string json_number(double value) {
    if (std::isnan(value)) {
        return "NaN";
    }
    if (std::isinf(value)) {
        return value < 0.0 ? "-Infinity" : "Infinity";
    }
    return format_number(value);
}

std::string constant_json(const Constant& constant) {
    switch (constant.kind) {
        case ConstantKind::Nova:
            return "null";
        case ConstantKind::Bool:
            return constant.bool_value ? "true" : "false";
        case ConstantKind::Int:
            return std::to_string(constant.int_value);
        case ConstantKind::BigInt: {
            std::string out;
            append_json_quoted(out, constant.text);
            return out;
        }
        case ConstantKind::Num:
            return json_number(constant.num_value);
        case ConstantKind::Str: {
            std::string out;
            append_json_quoted(out, constant.text);
            return out;
        }
        case ConstantKind::Char: {
            char32_t code_point = static_cast<char32_t>(constant.uint_value);
            if (!is_scalar_value(code_point)) {
                code_point = 0xFFFDu;
            }
            std::string character;
            append_utf8(character, code_point);
            std::string out;
            append_json_quoted(out, character);
            return out;
        }
        case ConstantKind::Ast:
        case ConstantKind::Spec:
        case ConstantKind::Extern:
        case ConstantKind::Descriptor:
            return constant.text;
        case ConstantKind::Call:
        case ConstantKind::Pattern:
        case ConstantKind::Type:
        case ConstantKind::Trait:
        case ConstantKind::Function:
            return std::to_string(constant.uint_value);
        case ConstantKind::Tuple: {
            std::string out = "[";
            for (std::size_t index = 0; index < constant.tuple.size(); ++index) {
                if (index > 0) {
                    out.push_back(',');
                }
                out += constant_json(constant.tuple[index]);
            }
            out.push_back(']');
            return out;
        }
    }
    return "null";
}

std::string constant_text(const CodeObject& code, std::int64_t index) {
    if (index < 0
        || static_cast<std::uint64_t>(index) >= code.constants.size()) {
        return "<constant out of range>";
    }
    return short_text(constant_json(
        code.constants[static_cast<std::size_t>(index)]));
}

const std::string* image_string(
    const Image* image, std::int64_t index, bool global_name) {
    if (image == nullptr || index < 0) {
        return nullptr;
    }
    const auto position = static_cast<std::size_t>(index);
    const std::vector<std::string>& values =
        global_name ? image->global_names : image->strings;
    if (position < values.size()) {
        return &values[position];
    }
    if (global_name && position < image->strings.size()) {
        return &image->strings[position];
    }
    return nullptr;
}

std::string operand_text(
    const CodeObject& code, const Image* image, const OperandSpec& operand,
    const DecodedOperand& decoded) {
    const std::int64_t integer = decoded.integer;
    switch (operand.kind) {
        case OperandKind::Const:
            return "const=" + std::to_string(integer) + " "
                + constant_text(code, integer);
        case OperandKind::Spec: {
            std::string text = "spec=" + std::to_string(integer);
            if (integer >= 0
                && static_cast<std::uint64_t>(integer) < code.constants.size()) {
                const Constant& constant =
                    code.constants[static_cast<std::size_t>(integer)];
                if (constant.kind == ConstantKind::Spec) {
                    text += " " + short_text(constant_json(constant));
                }
            }
            return text;
        }
        case OperandKind::Slot:
            return "slot=" + std::to_string(integer);
        case OperandKind::Target:
            return "target=" + std::to_string(integer);
        case OperandKind::Flags:
            return "flags=" + std::to_string(integer);
        case OperandKind::Call: {
            std::string text = "call=" + std::to_string(integer);
            if (image != nullptr && integer >= 0
                && static_cast<std::uint64_t>(integer)
                    < image->call_sites.size()) {
                const CallSite& site =
                    image->call_sites[static_cast<std::size_t>(integer)];
                text += " " + site.dispatch + ":" + site.name;
            }
            return text;
        }
        case OperandKind::Pattern: {
            std::string text = "pattern=" + std::to_string(integer);
            if (image != nullptr && integer >= 0
                && static_cast<std::uint64_t>(integer)
                    < image->patterns.size()) {
                text += " "
                    + image->patterns[static_cast<std::size_t>(integer)].kind;
            }
            return text;
        }
        case OperandKind::Module: {
            std::string text = "module=" + std::to_string(integer);
            if (image != nullptr && integer >= 0
                && static_cast<std::uint64_t>(integer)
                    < image->modules.size()) {
                text += " "
                    + image->modules[static_cast<std::size_t>(integer)].name;
            }
            return text;
        }
        case OperandKind::Type: {
            std::string text = "type=" + std::to_string(integer);
            if (image != nullptr && integer >= 0
                && static_cast<std::uint64_t>(integer) < image->types.size()) {
                text += " " + image->types[static_cast<std::size_t>(integer)].name;
            }
            return text;
        }
        case OperandKind::Trait: {
            std::string text = "trait=" + std::to_string(integer);
            if (image != nullptr && integer >= 0
                && static_cast<std::uint64_t>(integer) < image->traits.size()) {
                text += " "
                    + image->traits[static_cast<std::size_t>(integer)].name;
            }
            return text;
        }
        case OperandKind::Field: {
            std::string text = "field=" + std::to_string(integer);
            if (const std::string* resolved =
                    image_string(image, integer, true)) {
                text += " " + *resolved;
            }
            return text;
        }
        case OperandKind::Name: {
            std::string text = "name=" + std::to_string(integer);
            if (const std::string* resolved =
                    image_string(image, integer, true)) {
                text += " " + *resolved;
            }
            return text;
        }
        case OperandKind::Export: {
            std::string text = "export=" + std::to_string(integer);
            if (const std::string* resolved =
                    image_string(image, integer, false)) {
                text += " " + *resolved;
            }
            return text;
        }
        case OperandKind::Host: {
            std::string text = "host=" + std::to_string(integer);
            if (const std::string* resolved =
                    image_string(image, integer, false)) {
                text += " " + *resolved;
            }
            return text;
        }
        case OperandKind::Event:
            return "event=" + std::to_string(integer);
        case OperandKind::Value:
            break;
    }
    if (decoded.is_float) {
        const std::string number = format_number(decoded.number);
        if (std::string_view(operand.name) == "value") {
            return number;
        }
        return std::string(operand.name) + "=" + number;
    }
    if (std::string_view(operand.name) == "value") {
        return std::to_string(integer);
    }
    return std::string(operand.name) + "=" + std::to_string(integer);
}

std::string span_text(const CodeObject& code, std::size_t instruction_index) {
    if (code.span_table.empty()
        || instruction_index >= code.span_table.size()) {
        return {};
    }
    const std::uint32_t span_index = code.span_table[instruction_index];
    if (code.spans.empty() || span_index >= code.spans.size()) {
        return {};
    }
    const SourceSpan& span = code.spans[span_index];
    return "; src=" + std::to_string(span.file_id) + ":"
        + std::to_string(span.start_line) + ":"
        + std::to_string(span.start_column) + "-"
        + std::to_string(span.end_line) + ":"
        + std::to_string(span.end_column);
}

std::string flags_text(std::uint32_t flags) {
    char buffer[16];
    std::snprintf(buffer, sizeof(buffer), "0x%04x", flags);
    std::string text(buffer);
    std::vector<const char*> names;
    if ((flags & kFlagAsync) != 0) {
        names.push_back("async");
    }
    if ((flags & kFlagVariadic) != 0) {
        names.push_back("variadic");
    }
    if ((flags & kFlagMethod) != 0) {
        names.push_back("method");
    }
    if ((flags & kFlagStatic) != 0) {
        names.push_back("static");
    }
    if (!names.empty()) {
        text.push_back('(');
        for (std::size_t index = 0; index < names.size(); ++index) {
            if (index > 0) {
                text.push_back(',');
            }
            text += names[index];
        }
        text.push_back(')');
    }
    return text;
}

std::string offset_text(std::uint32_t offset) {
    std::string text = std::to_string(offset);
    if (text.size() < 4) {
        text.insert(0, 4 - text.size(), '0');
    }
    return text;
}

} // namespace

std::string disassemble_code(const CodeObject& code, const Image* image) {
    std::string out;
    out += "code ";
    out += (code.qualname.empty() ? code.name : code.qualname);
    out += " args=" + std::to_string(code.parameter_count);
    out += " locals=" + std::to_string(code.local_count);
    out += " stack=" + std::to_string(code.max_stack);
    out += " captures=" + std::to_string(code.capture_count);
    out += " flags=" + flags_text(code.flags);
    out.push_back('\n');

    std::uint32_t offset = 0;
    std::size_t instruction_index = 0;
    while (offset < code.bytecode.size()) {
        DecodedInstruction instruction;
        try {
            instruction = decode_instruction(code.bytecode, offset);
        } catch (const DecodeError& error) {
            out += offset_text(offset);
            out += "  <decode error: ";
            out += error.what();
            out += ">\n";
            break;
        }
        std::string operands;
        for (std::uint8_t index = 0;
             index < instruction.spec->operand_count; ++index) {
            if (!operands.empty()) {
                operands.push_back(' ');
            }
            operands += operand_text(
                code, image, instruction.spec->operands[index],
                instruction.operands[index]);
        }
        out += offset_text(offset);
        out += "  ";
        out += instruction.spec->name;
        if (!operands.empty()) {
            out.push_back(' ');
            out += operands;
        }
        out += span_text(code, instruction_index);
        out.push_back('\n');
        offset = instruction.next_offset;
        ++instruction_index;
    }

    if (!code.local_names.empty()) {
        out += "locals: ";
        for (std::size_t index = 0; index < code.local_names.size(); ++index) {
            if (index > 0) {
                out += ", ";
            }
            out += std::to_string(index);
            out.push_back('=');
            out += python_repr(code.local_names[index]);
        }
        out.push_back('\n');
    }
    if (!code.parameter_names.empty()) {
        out += "parameters: ";
        for (std::size_t index = 0; index < code.parameter_names.size(); ++index) {
            if (index > 0) {
                out += ", ";
            }
            out += python_repr(code.parameter_names[index]);
        }
        out.push_back('\n');
    }
    if (!code.exception_table.empty()) {
        out += "exceptions:\n";
        for (const ExceptionEntry& entry : code.exception_table) {
            out += "  start=" + std::to_string(entry.start_ip);
            out += " end=" + std::to_string(entry.end_ip);
            out += " catch=" + std::to_string(entry.catch_ip);
            out += " finally=" + std::to_string(entry.finally_ip);
            out += " resume=" + std::to_string(entry.resume_ip);
            out += " depth=" + std::to_string(entry.stack_depth);
            out += " watermark=" + std::to_string(entry.local_watermark);
            out += " kind=";
            out += entry.kind == 1 ? "finally" : "catch";
            out.push_back('\n');
        }
    }
    return out;
}

} // namespace pwb
