// PWB1 image model and reader.
//
// This mirrors src/vm/image.py byte for byte. All integers are little endian,
// every table read is bounds checked, and every table must be consumed
// exactly.

#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace pwb {

inline constexpr std::uint16_t kFormatVersion = 1;
inline constexpr std::size_t kTableCount = 14;

inline constexpr std::uint32_t kFlagAsync = 0x01;
inline constexpr std::uint32_t kFlagVariadic = 0x02;
inline constexpr std::uint32_t kFlagMethod = 0x04;
inline constexpr std::uint32_t kFlagStatic = 0x08;

// Constant tags in the exact order used by the Python codec.
enum class ConstantKind : std::uint8_t {
    Nova = 0,
    Bool = 1,
    Int = 2,
    BigInt = 3,
    Num = 4,
    Str = 5,
    Char = 6,
    Ast = 7,
    Call = 8,
    Pattern = 9,
    Spec = 10,
    Type = 11,
    Trait = 12,
    Function = 13,
    Extern = 14,
    Descriptor = 15,
    Tuple = 16,
};

const char* constant_kind_name(ConstantKind kind) noexcept;

struct Constant {
    ConstantKind kind = ConstantKind::Nova;
    bool bool_value = false;
    std::int64_t int_value = 0;
    double num_value = 0.0;
    std::uint32_t uint_value = 0;
    std::string text;
    std::vector<Constant> tuple;
};

struct SourceSpan {
    std::uint32_t file_id = 0;
    std::uint32_t start_line = 0;
    std::uint32_t start_column = 0;
    std::uint32_t end_line = 0;
    std::uint32_t end_column = 0;
};

struct ExceptionEntry {
    std::int32_t start_ip = 0;
    std::int32_t end_ip = 0;
    std::int32_t catch_ip = 0;
    std::int32_t finally_ip = 0;
    std::int32_t resume_ip = 0;
    std::uint32_t stack_depth = 0;
    std::uint32_t local_watermark = 0;
    std::uint8_t kind = 0;  // 0 catch, 1 finally
};

struct CodeObject {
    std::string name;
    std::string qualname;
    std::uint32_t source_file = 0;
    std::uint32_t parameter_count = 0;
    std::uint32_t local_count = 0;
    std::uint32_t capture_count = 0;
    std::uint32_t max_stack = 0;
    std::uint32_t max_frame_depth = 1;
    std::vector<std::uint8_t> bytecode;
    std::vector<std::uint32_t> constant_indices;
    std::vector<Constant> constants;
    std::vector<SourceSpan> spans;
    std::vector<std::uint32_t> span_table;
    std::vector<ExceptionEntry> exception_table;
    std::vector<std::string> local_names;
    std::vector<std::string> parameter_names;
    std::int32_t return_spec = -1;
    std::uint32_t flags = 0;
    std::optional<std::string> trait_name;
    std::optional<std::string> operator_trait;
    std::string fallback_ast;
};

struct ModuleInfo {
    std::string name;
    std::string path;
    std::uint32_t code_index = 0;
    std::vector<std::string> imports;
    std::vector<std::pair<std::string, std::string>> exports;
};

struct TypeProperty {
    bool is_private = false;
    std::string name;
    std::uint32_t index = 0;
    std::optional<std::string> type_name;
};

struct TypeMethod {
    bool is_private = false;
    std::string name;
    std::uint32_t index = 0;
    std::optional<std::string> type_name;
    bool is_static = false;
};

struct TypeInfo {
    std::string name;
    std::string kind;
    std::vector<std::string> type_parameters;
    std::vector<TypeProperty> properties;
    std::vector<TypeMethod> methods;
    std::vector<std::string> variants;
};

struct TraitMethod {
    std::string name;
    std::uint32_t index = 0;
    bool is_static = false;
};

struct TraitInfo {
    std::string name;
    std::vector<std::string> properties;
    std::vector<TraitMethod> methods;
};

struct FunctionInfo {
    std::string name;
    std::uint32_t code_index = 0;
    std::string args;
    std::uint32_t min_argc = 0;
    std::string return_node;
    std::string flags_json;
    std::string body;
};

struct CallSite {
    std::string dispatch;
    std::string name;
    std::optional<std::string> module;
    std::optional<std::string> type_name;
    std::optional<std::string> trait_name;
    std::optional<std::string> operator_trait;
    std::optional<std::string> native_type;
    std::uint32_t positional_count = 0;
    std::vector<std::string> argument_kinds;
    std::vector<std::string> argument_names;
    std::uint32_t type_argument_count = 0;
    std::int32_t return_spec = -1;
    bool is_async = false;
    std::string callee_ast;
    std::string method_ast;
};

struct PatternDescriptor {
    std::string kind;
    std::string literal;
    std::vector<std::pair<std::string, std::uint32_t>> bindings;
    std::vector<PatternDescriptor> nested;
    std::optional<std::string> type_name;
    std::vector<std::pair<std::string, PatternDescriptor>> fields;
    std::int32_t rest_slot = -1;
    std::string start_ast;
    std::string end_ast;
};

struct Image {
    std::uint16_t format_version = kFormatVersion;
    std::string language_version;
    std::uint16_t flags = 0;
    std::uint32_t entry_module = 0;
    std::uint32_t entry_code = 0;
    std::vector<ModuleInfo> modules;
    std::vector<TypeInfo> types;
    std::vector<TraitInfo> traits;
    std::vector<FunctionInfo> functions;
    std::vector<Constant> constants;
    std::vector<CallSite> call_sites;
    std::vector<PatternDescriptor> patterns;
    std::vector<std::string> type_specs;
    std::vector<std::string> sources;
    std::vector<std::string> global_names;
    std::vector<std::string> strings;
    std::vector<std::string> debug_lines;
    std::vector<CodeObject> codes;
};

// Bounds checked little endian reader. `label` names the table or object in
// error messages and `what` names the field being read.
class Reader {
public:
    Reader(const std::uint8_t* data, std::size_t size, std::string label = {});

    const std::uint8_t* take(std::size_t count, std::string_view what = {});
    std::uint8_t u8(std::string_view what = {});
    std::uint16_t u16(std::string_view what = {});
    std::uint32_t u32(std::string_view what = {});
    std::int32_t i32(std::string_view what = {});
    std::int64_t i64(std::string_view what = {});
    double f64(std::string_view what = {});
    std::string string(std::string_view what = {});
    std::optional<std::string> optional_string(std::string_view what = {});

    std::size_t remaining() const noexcept;
    bool at_end() const noexcept;

private:
    [[noreturn]] void truncated(std::string_view what) const;
    std::string describe(std::string_view what) const;

    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t offset_;
    std::string label_;
};

// Standard reflected CRC-32, the same checksum as zlib.crc32.
std::uint32_t crc32(const std::uint8_t* data, std::size_t size);

// Parse and validate a PWB1 container. Throws ImageError.
Image parse_image(const std::uint8_t* data, std::size_t size);

} // namespace pwb
