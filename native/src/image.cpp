#include "pwb/image.hpp"

#include <array>
#include <cstdio>
#include <cstring>
#include <string>
#include <utility>

#include "pwb/error.hpp"
#include "pwb/opcodes.hpp"

namespace pwb {
namespace {

const char* const kTableNames[kTableCount] = {
    "meta",
    "modules",
    "types",
    "traits",
    "functions",
    "constants",
    "call_sites",
    "patterns",
    "type_specs",
    "sources",
    "global_names",
    "strings",
    "debug_lines",
    "codes",
};

void require_utf8(std::string_view text, const std::string& what) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(text.data());
    std::size_t index = 0;
    while (index < text.size()) {
        const unsigned char first = bytes[index++];
        if (first < 0x80u) {
            continue;
        }
        std::size_t extra = 0;
        std::uint32_t code_point = 0;
        if ((first & 0xE0u) == 0xC0u) {
            if (first < 0xC2u) {
                throw ImageError("invalid UTF-8 in " + what);
            }
            extra = 1;
            code_point = first & 0x1Fu;
        } else if ((first & 0xF0u) == 0xE0u) {
            extra = 2;
            code_point = first & 0x0Fu;
        } else if ((first & 0xF8u) == 0xF0u) {
            if (first > 0xF4u) {
                throw ImageError("invalid UTF-8 in " + what);
            }
            extra = 3;
            code_point = first & 0x07u;
        } else {
            throw ImageError("invalid UTF-8 in " + what);
        }
        if (extra > text.size() - index) {
            throw ImageError("invalid UTF-8 in " + what);
        }
        for (std::size_t continuation = 0; continuation < extra; ++continuation) {
            const unsigned char next = bytes[index++];
            if ((next & 0xC0u) != 0x80u) {
                throw ImageError("invalid UTF-8 in " + what);
            }
            code_point = (code_point << 6) | (next & 0x3Fu);
        }
        if (extra == 2 && code_point < 0x800u) {
            throw ImageError("invalid UTF-8 in " + what);
        }
        if (extra == 3 && code_point < 0x10000u) {
            throw ImageError("invalid UTF-8 in " + what);
        }
        if (code_point >= 0xD800u && code_point <= 0xDFFFu) {
            throw ImageError("invalid UTF-8 in " + what);
        }
        if (code_point > 0x10FFFFu) {
            throw ImageError("invalid UTF-8 in " + what);
        }
    }
}

Constant read_constant(Reader& reader) {
    const std::uint8_t tag = reader.u8("constant tag");
    Constant constant;
    switch (tag) {
        case 0:
            constant.kind = ConstantKind::Nova;
            return constant;
        case 1:
            constant.kind = ConstantKind::Bool;
            constant.bool_value = reader.u8("bool constant") != 0;
            return constant;
        case 2:
            constant.kind = ConstantKind::Int;
            constant.int_value = reader.i64("int constant");
            return constant;
        case 3:
            constant.kind = ConstantKind::BigInt;
            constant.text = reader.string("bigint constant");
            return constant;
        case 4:
            constant.kind = ConstantKind::Num;
            constant.num_value = reader.f64("num constant");
            return constant;
        case 5:
            constant.kind = ConstantKind::Str;
            constant.text = reader.string("str constant");
            return constant;
        case 6:
            constant.kind = ConstantKind::Char;
            constant.uint_value = reader.u32("char constant");
            return constant;
        case 7:
            constant.kind = ConstantKind::Ast;
            constant.text = reader.string("ast constant");
            return constant;
        case 8:
            constant.kind = ConstantKind::Call;
            constant.uint_value = reader.u32("call constant");
            return constant;
        case 9:
            constant.kind = ConstantKind::Pattern;
            constant.uint_value = reader.u32("pattern constant");
            return constant;
        case 10:
            constant.kind = ConstantKind::Spec;
            constant.text = reader.string("spec constant");
            return constant;
        case 11:
            constant.kind = ConstantKind::Type;
            constant.uint_value = reader.u32("type constant");
            return constant;
        case 12:
            constant.kind = ConstantKind::Trait;
            constant.uint_value = reader.u32("trait constant");
            return constant;
        case 13:
            constant.kind = ConstantKind::Function;
            constant.uint_value = reader.u32("function constant");
            return constant;
        case 14:
            constant.kind = ConstantKind::Extern;
            constant.text = reader.string("extern constant");
            return constant;
        case 15:
            constant.kind = ConstantKind::Descriptor;
            constant.text = reader.string("descriptor constant");
            return constant;
        case 16: {
            constant.kind = ConstantKind::Tuple;
            const std::uint32_t count = reader.u32("tuple constant count");
            for (std::uint32_t index = 0; index < count; ++index) {
                constant.tuple.push_back(read_constant(reader));
            }
            return constant;
        }
        default:
            throw ImageError(
                "unknown constant tag: " + std::to_string(static_cast<int>(tag)));
    }
}

SourceSpan read_source_span(Reader& reader) {
    SourceSpan span;
    span.file_id = reader.u32("span file");
    span.start_line = reader.u32("span start line");
    span.start_column = reader.u32("span start column");
    span.end_line = reader.u32("span end line");
    span.end_column = reader.u32("span end column");
    return span;
}

ExceptionEntry read_exception_entry(Reader& reader) {
    ExceptionEntry entry;
    entry.start_ip = reader.i32("exception start");
    entry.end_ip = reader.i32("exception end");
    entry.catch_ip = reader.i32("exception catch");
    entry.finally_ip = reader.i32("exception finally");
    entry.resume_ip = reader.i32("exception resume");
    entry.stack_depth = reader.u32("exception stack depth");
    entry.local_watermark = reader.u32("exception local watermark");
    const std::uint8_t kind = reader.u8("exception kind");
    if (kind > 1) {
        throw ImageError(
            "unknown exception kind tag: " + std::to_string(static_cast<int>(kind)));
    }
    entry.kind = kind;
    return entry;
}

CodeObject read_code(Reader& reader) {
    CodeObject code;
    code.name = reader.string("code name");
    code.qualname = reader.string("code qualname");
    code.source_file = reader.u32("code source file");
    code.parameter_count = reader.u32("code parameter count");
    code.local_count = reader.u32("code local count");
    code.capture_count = reader.u32("code capture count");
    code.max_stack = reader.u32("code max stack");
    code.max_frame_depth = reader.u32("code max frame depth");
    const std::uint32_t bytecode_length = reader.u32("code bytecode length");
    const std::uint8_t* bytecode = reader.take(bytecode_length, "code bytecode");
    if (bytecode_length > 0) {
        code.bytecode.assign(bytecode, bytecode + bytecode_length);
    }
    const std::uint32_t constant_index_count =
        reader.u32("code constant index count");
    for (std::uint32_t index = 0; index < constant_index_count; ++index) {
        code.constant_indices.push_back(reader.u32("code constant index"));
    }
    const std::uint32_t constant_count = reader.u32("code constant count");
    for (std::uint32_t index = 0; index < constant_count; ++index) {
        code.constants.push_back(read_constant(reader));
    }
    const std::uint32_t span_count = reader.u32("code span count");
    for (std::uint32_t index = 0; index < span_count; ++index) {
        code.spans.push_back(read_source_span(reader));
    }
    const std::uint32_t span_table_count =
        reader.u32("code span table count");
    for (std::uint32_t index = 0; index < span_table_count; ++index) {
        code.span_table.push_back(reader.u32("code span index"));
    }
    code.offset_to_span.assign(bytecode_length, 0);
    std::uint32_t span_offset = 0;
    std::uint32_t span_instruction = 0;
    while (span_offset < bytecode_length) {
        try {
            const DecodedInstruction instruction =
                decode_instruction(code.bytecode, span_offset);
            code.offset_to_span[span_offset] =
                span_instruction < code.span_table.size()
                ? code.span_table[span_instruction] : 0;
            span_offset = instruction.next_offset;
            ++span_instruction;
        } catch (...) {
            break;
        }
    }
    const std::uint32_t exception_count = reader.u32("code exception count");
    for (std::uint32_t index = 0; index < exception_count; ++index) {
        code.exception_table.push_back(read_exception_entry(reader));
    }
    const std::uint32_t local_name_count = reader.u32("code local name count");
    for (std::uint32_t index = 0; index < local_name_count; ++index) {
        code.local_names.push_back(reader.string("code local name"));
    }
    const std::uint32_t parameter_name_count =
        reader.u32("code parameter name count");
    for (std::uint32_t index = 0; index < parameter_name_count; ++index) {
        code.parameter_names.push_back(reader.string("code parameter name"));
    }
    code.return_spec = reader.i32("code return spec");
    code.flags = reader.u32("code flags");
    code.trait_name = reader.optional_string("code trait name");
    code.operator_trait = reader.optional_string("code operator trait");
    code.fallback_ast = reader.string("code fallback ast");
    return code;
}

ModuleInfo read_module(Reader& reader) {
    ModuleInfo module;
    module.name = reader.string("module name");
    module.path = reader.string("module path");
    module.code_index = reader.u32("module code index");
    const std::uint32_t import_count = reader.u32("module import count");
    for (std::uint32_t index = 0; index < import_count; ++index) {
        module.imports.push_back(reader.string("module import"));
    }
    const std::uint32_t export_count = reader.u32("module export count");
    for (std::uint32_t index = 0; index < export_count; ++index) {
        const std::string name = reader.string("module export name");
        const std::string target = reader.string("module export target");
        module.exports.emplace_back(name, target);
    }
    return module;
}

TypeInfo read_type(Reader& reader) {
    TypeInfo info;
    info.name = reader.string("type name");
    info.kind = reader.string("type kind");
    const std::uint32_t parameter_count = reader.u32("type parameter count");
    for (std::uint32_t index = 0; index < parameter_count; ++index) {
        info.type_parameters.push_back(reader.string("type parameter"));
    }
    const std::uint32_t property_count = reader.u32("property count");
    for (std::uint32_t index = 0; index < property_count; ++index) {
        TypeProperty property;
        property.is_private = reader.u8("property private") != 0;
        property.name = reader.string("property name");
        property.index = reader.u32("property index");
        property.type_name = reader.optional_string("property type name");
        info.properties.push_back(std::move(property));
    }
    const std::uint32_t method_count = reader.u32("method count");
    for (std::uint32_t index = 0; index < method_count; ++index) {
        TypeMethod method;
        method.is_private = reader.u8("method private") != 0;
        method.name = reader.string("method name");
        method.index = reader.u32("method index");
        method.type_name = reader.optional_string("method type name");
        method.is_static = reader.u8("method static") != 0;
        info.methods.push_back(std::move(method));
    }
    const std::uint32_t variant_count = reader.u32("type variant count");
    for (std::uint32_t index = 0; index < variant_count; ++index) {
        info.variants.push_back(reader.string("type variant"));
    }
    return info;
}

TraitInfo read_trait(Reader& reader) {
    TraitInfo info;
    info.name = reader.string("trait name");
    const std::uint32_t property_count = reader.u32("trait property count");
    for (std::uint32_t index = 0; index < property_count; ++index) {
        info.properties.push_back(reader.string("trait property"));
    }
    const std::uint32_t method_count = reader.u32("trait method count");
    for (std::uint32_t index = 0; index < method_count; ++index) {
        TraitMethod method;
        method.name = reader.string("trait method name");
        method.index = reader.u32("trait method index");
        method.is_static = reader.u8("trait method static") != 0;
        info.methods.push_back(std::move(method));
    }
    return info;
}

FunctionInfo read_function(Reader& reader) {
    FunctionInfo info;
    info.name = reader.string("function name");
    info.code_index = reader.u32("function code index");
    info.args = reader.string("function args");
    info.min_argc = reader.u32("function min argc");
    info.return_node = reader.string("function return node");
    info.flags_json = reader.string("function flags");
    info.body = reader.string("function body");
    return info;
}

CallSite read_call_site(Reader& reader) {
    CallSite site;
    site.dispatch = reader.string("call dispatch");
    site.name = reader.string("call name");
    site.module = reader.optional_string("call module");
    site.type_name = reader.optional_string("call type name");
    site.trait_name = reader.optional_string("call trait name");
    site.operator_trait = reader.optional_string("call operator trait");
    site.native_type = reader.optional_string("call native type");
    site.positional_count = reader.u32("call positional count");
    const std::uint32_t kind_count = reader.u32("call argument kind count");
    for (std::uint32_t index = 0; index < kind_count; ++index) {
        site.argument_kinds.push_back(reader.string("call argument kind"));
    }
    const std::uint32_t name_count = reader.u32("call argument name count");
    for (std::uint32_t index = 0; index < name_count; ++index) {
        site.argument_names.push_back(reader.string("call argument name"));
    }
    site.type_argument_count = reader.u32("call type argument count");
    site.return_spec = reader.i32("call return spec");
    site.is_async = reader.u8("call async") != 0;
    site.callee_ast = reader.string("call callee ast");
    site.method_ast = reader.string("call method ast");
    return site;
}

PatternDescriptor read_pattern(Reader& reader) {
    PatternDescriptor pattern;
    pattern.kind = reader.string("pattern kind");
    pattern.literal = reader.string("pattern literal");
    const std::uint32_t binding_count = reader.u32("pattern binding count");
    for (std::uint32_t index = 0; index < binding_count; ++index) {
        const std::string name = reader.string("pattern binding name");
        const std::uint32_t slot = reader.u32("pattern binding slot");
        pattern.bindings.emplace_back(name, slot);
    }
    const std::uint32_t nested_count = reader.u32("pattern nested count");
    for (std::uint32_t index = 0; index < nested_count; ++index) {
        pattern.nested.push_back(read_pattern(reader));
    }
    pattern.type_name = reader.optional_string("pattern type name");
    const std::uint32_t field_count = reader.u32("pattern field count");
    for (std::uint32_t index = 0; index < field_count; ++index) {
        const std::string name = reader.string("pattern field name");
        pattern.fields.emplace_back(name, read_pattern(reader));
    }
    pattern.rest_slot = reader.i32("pattern rest slot");
    pattern.start_ast = reader.string("pattern start ast");
    pattern.end_ast = reader.string("pattern end ast");
    return pattern;
}

void finish_table(const Reader& reader, const char* name) {
    if (!reader.at_end()) {
        throw ImageError(
            "trailing bytes in image table " + std::string(name) + ": "
            + std::to_string(reader.remaining()));
    }
}

std::string magic_text(const std::uint8_t* magic) {
    std::string text;
    for (std::size_t index = 0; index < 4; ++index) {
        const unsigned char byte = magic[index];
        if (byte >= 0x20u && byte < 0x7Fu) {
            text.push_back(static_cast<char>(byte));
        } else {
            char escaped[8];
            std::snprintf(escaped, sizeof(escaped), "\\x%02x", byte);
            text += escaped;
        }
    }
    return text;
}

} // namespace

const char* constant_kind_name(ConstantKind kind) noexcept {
    switch (kind) {
        case ConstantKind::Nova: return "nova";
        case ConstantKind::Bool: return "bool";
        case ConstantKind::Int: return "int";
        case ConstantKind::BigInt: return "bigint";
        case ConstantKind::Num: return "num";
        case ConstantKind::Str: return "str";
        case ConstantKind::Char: return "char";
        case ConstantKind::Ast: return "ast";
        case ConstantKind::Call: return "call";
        case ConstantKind::Pattern: return "pattern";
        case ConstantKind::Spec: return "spec";
        case ConstantKind::Type: return "type";
        case ConstantKind::Trait: return "trait";
        case ConstantKind::Function: return "function";
        case ConstantKind::Extern: return "extern";
        case ConstantKind::Descriptor: return "descriptor";
        case ConstantKind::Tuple: return "tuple";
    }
    return "unknown";
}

Reader::Reader(const std::uint8_t* data, std::size_t size, std::string label)
    : data_(data), size_(size), offset_(0), label_(std::move(label)) {}

std::string Reader::describe(std::string_view what) const {
    std::string text = label_;
    if (!what.empty()) {
        if (!text.empty()) {
            text += " ";
        }
        text += what;
    }
    if (text.empty()) {
        text = "data";
    }
    return text;
}

void Reader::truncated(std::string_view what) const {
    throw ImageError(
        "truncated image while reading " + describe(what) + " at offset "
        + std::to_string(offset_));
}

const std::uint8_t* Reader::take(std::size_t count, std::string_view what) {
    if (count > size_ - offset_) {
        truncated(what);
    }
    const std::uint8_t* result = nullptr;
    if (count > 0) {
        result = data_ + offset_;
    }
    offset_ += count;
    return result;
}

std::uint8_t Reader::u8(std::string_view what) {
    const std::uint8_t* bytes = take(1, what);
    return bytes[0];
}

std::uint16_t Reader::u16(std::string_view what) {
    const std::uint8_t* bytes = take(2, what);
    return static_cast<std::uint16_t>(
        static_cast<std::uint16_t>(bytes[0])
        | (static_cast<std::uint16_t>(bytes[1]) << 8));
}

std::uint32_t Reader::u32(std::string_view what) {
    const std::uint8_t* bytes = take(4, what);
    std::uint32_t value = 0;
    for (std::size_t index = 0; index < 4; ++index) {
        value |= static_cast<std::uint32_t>(bytes[index]) << (8u * index);
    }
    return value;
}

std::int32_t Reader::i32(std::string_view what) {
    const std::uint32_t bits = u32(what);
    std::int32_t value = 0;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

std::int64_t Reader::i64(std::string_view what) {
    const std::uint8_t* bytes = take(8, what);
    std::uint64_t bits = 0;
    for (std::size_t index = 0; index < 8; ++index) {
        bits |= static_cast<std::uint64_t>(bytes[index]) << (8u * index);
    }
    std::int64_t value = 0;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

double Reader::f64(std::string_view what) {
    const std::uint8_t* bytes = take(8, what);
    std::uint64_t bits = 0;
    for (std::size_t index = 0; index < 8; ++index) {
        bits |= static_cast<std::uint64_t>(bytes[index]) << (8u * index);
    }
    double value = 0.0;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

std::string Reader::string(std::string_view what) {
    const std::uint32_t length = u32(what);
    const std::uint8_t* bytes = take(length, what);
    if (length == 0) {
        return {};
    }
    std::string text(reinterpret_cast<const char*>(bytes), length);
    require_utf8(text, describe(what));
    return text;
}

std::optional<std::string> Reader::optional_string(std::string_view what) {
    const std::uint8_t present = u8(what);
    if (present == 0) {
        return std::nullopt;
    }
    if (present != 1) {
        throw ImageError(
            "invalid optional string presence value: "
            + std::to_string(static_cast<int>(present)) + " while reading "
            + describe(what));
    }
    return string(what);
}

std::size_t Reader::remaining() const noexcept {
    return size_ - offset_;
}

bool Reader::at_end() const noexcept {
    return offset_ == size_;
}

std::uint32_t crc32(const std::uint8_t* data, std::size_t size) {
    static const std::array<std::uint32_t, 256> table = [] {
        std::array<std::uint32_t, 256> entries{};
        for (std::uint32_t index = 0; index < entries.size(); ++index) {
            std::uint32_t value = index;
            for (int bit = 0; bit < 8; ++bit) {
                value = (value & 1u)
                    ? (0xEDB88320u ^ (value >> 1))
                    : (value >> 1);
            }
            entries[index] = value;
        }
        return entries;
    }();
    std::uint32_t value = 0xFFFFFFFFu;
    for (std::size_t index = 0; index < size; ++index) {
        value = table[(value ^ data[index]) & 0xFFu] ^ (value >> 8);
    }
    return value ^ 0xFFFFFFFFu;
}

constexpr std::size_t kMaxImageBytes = 256u * 1024u * 1024u;

Image parse_image(const std::uint8_t* data, std::size_t size) {
    if (size > kMaxImageBytes) {
        throw ImageError(
            "image size " + std::to_string(size)
            + " exceeds the 256 MiB limit");
    }
    if (data == nullptr && size != 0) {
        throw ImageError("image data is null but the size is not zero");
    }
    Reader reader(data, size, "image");

    const std::uint8_t* magic = reader.take(4, "magic");
    if (magic[0] != 'P' || magic[1] != 'W' || magic[2] != 'B' || magic[3] != '1') {
        throw ImageError("invalid image magic: \"" + magic_text(magic) + "\"");
    }

    const std::uint16_t version = reader.u16("format version");
    if (version != kFormatVersion) {
        throw ImageError(
            "unsupported image format version: " + std::to_string(version));
    }
    const std::uint16_t flags = reader.u16("image flags");
    const std::uint16_t language_length = reader.u16("language version length");
    const std::uint8_t* language_bytes =
        reader.take(language_length, "language version");
    std::string language;
    if (language_length > 0) {
        language.assign(
            reinterpret_cast<const char*>(language_bytes), language_length);
        require_utf8(language, "language version");
    }

    const std::uint32_t table_count = reader.u32("table count");
    if (table_count != kTableCount) {
        throw ImageError(
            "image has " + std::to_string(table_count) + " tables but "
            + std::to_string(kTableCount) + " are expected");
    }

    std::array<std::pair<const std::uint8_t*, std::size_t>, kTableCount> tables{};
    for (std::size_t index = 0; index < kTableCount; ++index) {
        const std::uint32_t length = reader.u32(
            std::string(kTableNames[index]) + " table length");
        tables[index] = std::make_pair(
            reader.take(length, std::string(kTableNames[index]) + " table"),
            static_cast<std::size_t>(length));
    }

    if (reader.remaining() != 4) {
        throw ImageError(
            "image has " + std::to_string(reader.remaining())
            + " trailing bytes before the checksum");
    }
    const std::uint32_t expected_crc = reader.u32("checksum");
    const std::uint32_t actual_crc = crc32(data, size - 4);
    if (expected_crc != actual_crc) {
        char message[128];
        std::snprintf(
            message, sizeof(message),
            "image checksum mismatch: expected 0x%08x but computed 0x%08x",
            expected_crc, actual_crc);
        throw ImageError(message);
    }

    Image image;
    image.format_version = version;
    image.language_version = std::move(language);
    image.flags = flags;

    {
        Reader table(tables[0].first, tables[0].second, "table meta");
        image.entry_module = table.u32("entry module");
        image.entry_code = table.u32("entry code");
        finish_table(table, kTableNames[0]);
    }
    {
        Reader table(tables[1].first, tables[1].second, "table modules");
        const std::uint32_t count = table.u32("module count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.modules.push_back(read_module(table));
        }
        finish_table(table, kTableNames[1]);
    }
    {
        Reader table(tables[2].first, tables[2].second, "table types");
        const std::uint32_t count = table.u32("type count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.types.push_back(read_type(table));
        }
        finish_table(table, kTableNames[2]);
    }
    {
        Reader table(tables[3].first, tables[3].second, "table traits");
        const std::uint32_t count = table.u32("trait count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.traits.push_back(read_trait(table));
        }
        finish_table(table, kTableNames[3]);
    }
    {
        Reader table(tables[4].first, tables[4].second, "table functions");
        const std::uint32_t count = table.u32("function count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.functions.push_back(read_function(table));
        }
        finish_table(table, kTableNames[4]);
    }
    {
        Reader table(tables[5].first, tables[5].second, "table constants");
        const std::uint32_t count = table.u32("constant count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.constants.push_back(read_constant(table));
        }
        finish_table(table, kTableNames[5]);
    }
    {
        Reader table(tables[6].first, tables[6].second, "table call_sites");
        const std::uint32_t count = table.u32("call site count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.call_sites.push_back(read_call_site(table));
        }
        finish_table(table, kTableNames[6]);
    }
    {
        Reader table(tables[7].first, tables[7].second, "table patterns");
        const std::uint32_t count = table.u32("pattern count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.patterns.push_back(read_pattern(table));
        }
        finish_table(table, kTableNames[7]);
    }
    {
        Reader table(tables[8].first, tables[8].second, "table type_specs");
        const std::uint32_t count = table.u32("type spec count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.type_specs.push_back(table.string("type spec"));
        }
        finish_table(table, kTableNames[8]);
    }
    {
        Reader table(tables[9].first, tables[9].second, "table sources");
        const std::uint32_t count = table.u32("source count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.sources.push_back(table.string("source"));
        }
        finish_table(table, kTableNames[9]);
    }
    {
        Reader table(tables[10].first, tables[10].second, "table global_names");
        const std::uint32_t count = table.u32("global name count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.global_names.push_back(table.string("global name"));
        }
        finish_table(table, kTableNames[10]);
    }
    {
        Reader table(tables[11].first, tables[11].second, "table strings");
        const std::uint32_t count = table.u32("string count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.strings.push_back(table.string("string"));
        }
        finish_table(table, kTableNames[11]);
    }
    {
        Reader table(tables[12].first, tables[12].second, "table debug_lines");
        const std::uint32_t count = table.u32("debug line count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.debug_lines.push_back(table.string("debug line"));
        }
        finish_table(table, kTableNames[12]);
    }
    {
        Reader table(tables[13].first, tables[13].second, "table codes");
        const std::uint32_t count = table.u32("code count");
        for (std::uint32_t index = 0; index < count; ++index) {
            image.codes.push_back(read_code(table));
        }
        finish_table(table, kTableNames[13]);
    }

    return image;
}

} // namespace pwb
