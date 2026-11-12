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

#include "pwb/error.hpp"

namespace pwb {

enum class Tag : std::uint8_t {
    Nova = 0,
    Undef = 1,
    Bool = 2,
    Int = 3,
    Num = 4,
    Char = 5,
    Str = 6,
};

struct Value {
    Tag tag;
    std::uint8_t reserved[7];
    union {
        std::int64_t i;
        double d;
        bool b;
        char32_t c;
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
    }
    return "unknown";
}

inline Value make_nova() {
    Value value{};
    value.tag = Tag::Nova;
    return value;
}

inline Value make_undef() {
    Value value{};
    value.tag = Tag::Undef;
    return value;
}

inline Value make_bool(bool flag) {
    Value value{};
    value.tag = Tag::Bool;
    value.b = flag;
    return value;
}

inline Value make_int(std::int64_t number) {
    Value value{};
    value.tag = Tag::Int;
    value.i = number;
    return value;
}

inline Value make_num(double number) {
    Value value{};
    value.tag = Tag::Num;
    value.d = number;
    return value;
}

inline Value make_char(char32_t code_point) {
    Value value{};
    value.tag = Tag::Char;
    value.c = code_point;
    return value;
}

inline bool is_nova(const Value& value) noexcept {
    return value.tag == Tag::Nova;
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

// Format one value using the print rules for N0 scalars.
inline std::string format_value(const Value& value) {
    switch (value.tag) {
        case Tag::Nova:
            return "nova";
        case Tag::Undef:
            throw RuntimeError(
                "native N0 cannot print an undefined value");
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
            throw RuntimeError("native N0 does not implement string values");
    }
    throw RuntimeError("native N0 encountered an unknown value tag");
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
            throw RuntimeError("native N0 does not implement string values");
    }
    return false;
}

} // namespace pwb
