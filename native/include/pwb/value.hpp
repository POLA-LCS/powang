// Scalar values for the N0 native runtime.
//
// Value is a 16 byte tagged union. It is trivially copyable so stack pushes,
// slot stores and swaps are plain copies. Strings and heap objects arrive at
// N1 and N2, so the Str tag is reserved and rejects at use.

#pragma once

#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>
#include <system_error>
#include <type_traits>

#include "pwb/bigint.hpp"
#include "pwb/error.hpp"

namespace pwb {

struct FunctionObject;
struct ArrayObject;
struct IteratorObject;
struct StringObject;
struct TupleObject;
struct MapObject;
struct SetObject;
struct ObjectObject;
struct TypeRuntime;
struct ModuleRuntime;
struct ErrorObject;
struct RefObject;
struct ProjectObject;
struct TaskObject;
struct FileObject;

enum class Tag : std::uint8_t {
    Nova = 0,
    Undef = 1,
    Bool = 2,
    Int = 3,
    Num = 4,
    Char = 5,
    Str = 6,
    BigInt = 7,
    Fun = 8,
    Arr = 9,
    Spread = 10,
    Iter = 11,
    Tup = 12,
    Map = 13,
    Set = 14,
    Obj = 15,
    Type = 16,
    Module = 17,
    Error = 18,
    Ref = 19,
    Project = 20,
    Task = 21,
    File = 22,
};

enum ValueFlag : std::uint8_t {
    ValueDefined = 1u << 0,
    ValueConst = 1u << 1,
    ValueWeak = 1u << 2,
};

struct Value {
    Tag tag;
    std::uint8_t flags;
    std::uint8_t aux;
    std::uint8_t reserved[5];
    union {
        std::int64_t i;
        double d;
        bool b;
        char32_t c;
        void* ref;
    };
};

static_assert(sizeof(Value) == 16, "Value must stay 16 bytes");
static_assert(std::is_trivially_copyable<Value>::value,
              "Value must stay trivially copyable");

inline const char* tag_name(Tag tag) noexcept {
    switch (tag) {
        case Tag::Nova: return "nova";
        case Tag::Undef: return "undef";
        case Tag::Bool: return "bool";
        case Tag::Int: return "int";
        case Tag::Num: return "num";
        case Tag::Char: return "char";
        case Tag::Str: return "str";
        case Tag::BigInt: return "bigint";
        case Tag::Fun: return "fun";
        case Tag::Arr: return "arr";
        case Tag::Spread: return "spread";
        case Tag::Iter: return "iter";
        case Tag::Tup: return "tup";
        case Tag::Map: return "map";
        case Tag::Set: return "set";
        case Tag::Obj: return "obj";
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

inline Value make_nova() {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Nova;
    return value;
}

inline Value make_undef() {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Undef;
    value.flags = 0;
    return value;
}

inline Value make_bool(bool flag) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Bool;
    value.b = flag;
    return value;
}

inline Value make_int(std::int64_t number) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Int;
    value.i = number;
    return value;
}

inline Value make_num(double number) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Num;
    value.d = number;
    return value;
}

inline Value make_char(char32_t code_point) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Char;
    value.c = code_point;
    return value;
}

inline Value make_bigint(BigIntObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::BigInt;
    value.ref = object;
    return value;
}

inline Value make_function(FunctionObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Fun;
    value.ref = object;
    return value;
}

inline Value make_array(ArrayObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Arr;
    value.ref = object;
    return value;
}

inline Value make_spread(ArrayObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Spread;
    value.ref = object;
    return value;
}

inline Value make_iterator(IteratorObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Iter;
    value.ref = object;
    return value;
}

inline Value make_string(StringObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Str;
    value.ref = object;
    return value;
}

inline Value make_tuple(TupleObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Tup;
    value.ref = object;
    return value;
}

inline Value make_map(MapObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Map;
    value.ref = object;
    return value;
}

inline Value make_set(SetObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Set;
    value.ref = object;
    return value;
}

inline Value make_object(ObjectObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Obj;
    value.ref = object;
    return value;
}

inline Value make_type(TypeRuntime* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Type;
    value.ref = object;
    return value;
}

inline Value make_module(ModuleRuntime* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Module;
    value.ref = object;
    return value;
}

inline Value make_error_value(ErrorObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Error;
    value.ref = object;
    return value;
}

inline Value make_reference(RefObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Ref;
    value.ref = object;
    return value;
}

inline Value make_project(ProjectObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Project;
    value.ref = object;
    return value;
}

inline Value make_task(TaskObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::Task;
    value.ref = object;
    return value;
}

inline Value make_file(FileObject* object) {
    Value value{};
    value.flags = ValueDefined;
    value.tag = Tag::File;
    value.ref = object;
    return value;
}

inline bool is_defined(const Value& value) noexcept {
    return (value.flags & ValueDefined) != 0;
}

inline bool is_const(const Value& value) noexcept {
    return (value.flags & ValueConst) != 0;
}

inline bool is_weak(const Value& value) noexcept {
    return (value.flags & ValueWeak) != 0;
}

inline bool is_nova(const Value& value) noexcept {
    return value.tag == Tag::Nova;
}

inline bool is_bigint(const Value& value) noexcept {
    return value.tag == Tag::BigInt;
}

inline bool is_function(const Value& value) noexcept {
    return value.tag == Tag::Fun;
}

inline bool is_array(const Value& value) noexcept {
    return value.tag == Tag::Arr;
}

inline bool is_spread(const Value& value) noexcept {
    return value.tag == Tag::Spread;
}

inline bool is_iterator(const Value& value) noexcept {
    return value.tag == Tag::Iter;
}

inline bool is_string(const Value& value) noexcept {
    return value.tag == Tag::Str;
}

inline bool is_tuple(const Value& value) noexcept {
    return value.tag == Tag::Tup;
}

inline bool is_map(const Value& value) noexcept {
    return value.tag == Tag::Map;
}

inline bool is_set(const Value& value) noexcept {
    return value.tag == Tag::Set;
}

inline bool is_object(const Value& value) noexcept {
    return value.tag == Tag::Obj;
}

inline bool is_type(const Value& value) noexcept {
    return value.tag == Tag::Type;
}

inline bool is_module(const Value& value) noexcept {
    return value.tag == Tag::Module;
}

inline bool is_error(const Value& value) noexcept {
    return value.tag == Tag::Error;
}

inline bool is_reference(const Value& value) noexcept {
    return value.tag == Tag::Ref;
}

inline bool is_project(const Value& value) noexcept {
    return value.tag == Tag::Project;
}

inline bool is_task(const Value& value) noexcept {
    return value.tag == Tag::Task;
}

inline bool is_file(const Value& value) noexcept {
    return value.tag == Tag::File;
}

inline BigIntObject* as_bigint(const Value& value) {
    return static_cast<BigIntObject*>(value.ref);
}

inline const BigIntObject* as_bigint_const(const Value& value) {
    return static_cast<const BigIntObject*>(value.ref);
}

inline FunctionObject* as_function(const Value& value) {
    return static_cast<FunctionObject*>(value.ref);
}

inline ArrayObject* as_array(const Value& value) {
    return static_cast<ArrayObject*>(value.ref);
}

inline IteratorObject* as_iterator(const Value& value) {
    return static_cast<IteratorObject*>(value.ref);
}

inline StringObject* as_string(const Value& value) {
    return static_cast<StringObject*>(value.ref);
}

inline const StringObject* as_string_const(const Value& value) {
    return static_cast<const StringObject*>(value.ref);
}

inline TupleObject* as_tuple(const Value& value) {
    return static_cast<TupleObject*>(value.ref);
}

inline MapObject* as_map(const Value& value) {
    return static_cast<MapObject*>(value.ref);
}

inline SetObject* as_set(const Value& value) {
    return static_cast<SetObject*>(value.ref);
}

inline ObjectObject* as_object(const Value& value) {
    return static_cast<ObjectObject*>(value.ref);
}

inline TypeRuntime* as_type(const Value& value) {
    return static_cast<TypeRuntime*>(value.ref);
}

inline ModuleRuntime* as_module(const Value& value) {
    return static_cast<ModuleRuntime*>(value.ref);
}

inline ErrorObject* as_error(const Value& value) {
    return static_cast<ErrorObject*>(value.ref);
}

inline RefObject* as_reference(const Value& value) {
    return static_cast<RefObject*>(value.ref);
}

inline ProjectObject* as_project(const Value& value) {
    return static_cast<ProjectObject*>(value.ref);
}

inline TaskObject* as_task(const Value& value) {
    return static_cast<TaskObject*>(value.ref);
}

inline FileObject* as_file(const Value& value) {
    return static_cast<FileObject*>(value.ref);
}

inline bool is_scalar_value(char32_t code_point) noexcept {
    return code_point <= 0x10FFFFu
        && !(code_point >= 0xD800u && code_point <= 0xDFFFu);
}

inline void append_utf8(std::string& out, char32_t code_point) {
    if (code_point < 0x80u) {
        out.push_back(static_cast<char>(code_point));
        return;
    }
    if (code_point < 0x800u) {
        out.push_back(static_cast<char>(0xC0u | (code_point >> 6)));
        out.push_back(static_cast<char>(0x80u | (code_point & 0x3Fu)));
        return;
    }
    if (code_point < 0x10000u) {
        out.push_back(static_cast<char>(0xE0u | (code_point >> 12)));
        out.push_back(static_cast<char>(0x80u | ((code_point >> 6) & 0x3Fu)));
        out.push_back(static_cast<char>(0x80u | (code_point & 0x3Fu)));
        return;
    }
    out.push_back(static_cast<char>(0xF0u | (code_point >> 18)));
    out.push_back(static_cast<char>(0x80u | ((code_point >> 12) & 0x3Fu)));
    out.push_back(static_cast<char>(0x80u | ((code_point >> 6) & 0x3Fu)));
    out.push_back(static_cast<char>(0x80u | (code_point & 0x3Fu)));
}

// Python compatible shortest representation of a double. Python switches to
// scientific notation when the decimal exponent is below -4 or above 15.
inline std::string format_number(double value) {
    if (std::isnan(value)) {
        return "nan";
    }
    if (std::isinf(value)) {
        return value < 0.0 ? "-inf" : "inf";
    }
    char buffer[64];
    const auto converted = std::to_chars(
        buffer, buffer + sizeof(buffer), value, std::chars_format::scientific);
    if (converted.ec != std::errc()) {
        char fallback[64];
        std::snprintf(fallback, sizeof(fallback), "%.17g", value);
        return std::string(fallback);
    }
    std::string text(buffer, converted.ptr);
    bool negative = false;
    std::size_t position = 0;
    if (!text.empty() && text[0] == '-') {
        negative = true;
        position = 1;
    }
    const std::size_t exponent_at = text.find('e');
    std::string digits;
    for (std::size_t index = position;
         index < exponent_at && index < text.size(); ++index) {
        if (text[index] != '.') {
            digits.push_back(text[index]);
        }
    }
    if (digits.empty()) {
        digits = "0";
    }
    int exponent = 0;
    if (exponent_at != std::string::npos) {
        exponent = std::stoi(text.substr(exponent_at + 1));
    }
    std::string out;
    if (negative) {
        out.push_back('-');
    }
    if (exponent >= -4 && exponent <= 15) {
        const int point = exponent + 1;
        if (point <= 0) {
            out += "0.";
            out.append(static_cast<std::size_t>(-point), '0');
            out += digits;
        } else if (static_cast<std::size_t>(point) >= digits.size()) {
            out += digits;
            out.append(static_cast<std::size_t>(point) - digits.size(), '0');
            out += ".0";
        } else {
            out += digits.substr(0, static_cast<std::size_t>(point));
            out.push_back('.');
            out += digits.substr(static_cast<std::size_t>(point));
        }
    } else {
        out.push_back(digits[0]);
        if (digits.size() > 1) {
            out.push_back('.');
            out += digits.substr(1);
        }
        const int magnitude = exponent < 0 ? -exponent : exponent;
        char exponent_text[16];
        std::snprintf(exponent_text, sizeof(exponent_text), "%02d", magnitude);
        out.push_back('e');
        out.push_back(exponent < 0 ? '-' : '+');
        out += exponent_text;
    }
    return out;
}

std::string format_heap_value(const Value& value);
bool heap_truthy(const Value& value);
std::string format_undef_value(const Value& value);

// Format one value using the print rules for the native scalars and heap
// values.
inline std::string format_value(const Value& value) {
    switch (value.tag) {
        case Tag::Nova:
            return "nova";
        case Tag::Undef:
            return format_undef_value(value);
        case Tag::Bool:
            return value.b ? "true" : "false";
        case Tag::Int:
            return std::to_string(value.i);
        case Tag::Num:
            return format_number(value.d);
        case Tag::Char: {
            std::string out;
            append_utf8(out, value.c);
            return out;
        }
        case Tag::Str:
        case Tag::Arr:
        case Tag::Tup:
        case Tag::Map:
        case Tag::Set:
        case Tag::Obj:
        case Tag::Type:
        case Tag::Module:
        case Tag::Error:
        case Tag::Ref:
        case Tag::Project:
        case Tag::Task:
        case Tag::File:
            return format_heap_value(value);
        case Tag::BigInt: {
            const BigIntObject* object = as_bigint_const(value);
            if (object == nullptr) {
                throw RuntimeError("native N1 encountered a null bigint");
            }
            return object->value.format_decimal();
        }
        case Tag::Fun:
        case Tag::Spread:
        case Tag::Iter:
            throw RuntimeError(
                "native N1 does not implement function or iterator printing");
    }
    throw RuntimeError("native N1 encountered an unknown value tag");
}

// Language truth value for the N0 scalars. This mirrors PowangBoolean.cast,
// which treats char values as false and nova as false.
inline bool truthy(const Value& value) {
    switch (value.tag) {
        case Tag::Nova:
        case Tag::Undef:
        case Tag::Char:
            return false;
        case Tag::Bool:
            return value.b;
        case Tag::Int:
            return value.i != 0;
        case Tag::Num:
            return value.d != 0.0;
        case Tag::Str:
        case Tag::Arr:
        case Tag::Tup:
        case Tag::Map:
        case Tag::Set:
        case Tag::Obj:
        case Tag::Type:
        case Tag::Module:
        case Tag::Error:
        case Tag::Ref:
        case Tag::Project:
        case Tag::Task:
        case Tag::File:
            return heap_truthy(value);
        case Tag::BigInt: {
            const BigIntObject* object = as_bigint_const(value);
            return object != nullptr && !object->value.is_zero();
        }
        case Tag::Fun:
        case Tag::Spread:
        case Tag::Iter:
            return true;
    }
    return false;
}

} // namespace pwb
