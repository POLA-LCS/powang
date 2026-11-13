#include "pwb/host.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <iomanip>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "pwb/object.hpp"
#include "pwb/sha256.hpp"

namespace pwb {
namespace {

double numeric_argument(const Value& value) {
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
            throw std::runtime_error(
                "native extern scalar argument is not numeric");
    }
}

std::string json_escape(const std::string& text) {
    std::string out;
    for (const char character : text) {
        switch (character) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default:
                out.push_back(character);
                break;
        }
    }
    return out;
}

std::string json_stringify(
    const Value& value, int depth = 0, int indent = 0) {
    if (depth > 100) {
        throw std::runtime_error("JSON nesting is too deep");
    }
    const auto newline = [&](int level) {
        if (indent <= 0) {
            return std::string();
        }
        return "\n" + std::string(
            static_cast<std::size_t>(level * indent), ' ');
    };
    switch (value.tag) {
        case Tag::Nova:
            return "null";
        case Tag::Bool:
            return value.b ? "true" : "false";
        case Tag::Int:
            return std::to_string(value.i);
        case Tag::BigInt:
            return as_bigint_const(value)->value.format_decimal();
        case Tag::Num:
            return format_number(value.d);
        case Tag::Str:
            return "\"" + json_escape(as_string_const(value)->utf8) + "\"";
        case Tag::Arr:
        case Tag::Tup: {
            const std::vector<Value>& items = value.tag == Tag::Arr
                ? as_array(value)->items : as_tuple(value)->items;
            if (items.empty()) {
                return "[]";
            }
            std::string out = "[";
            for (std::size_t index = 0; index < items.size(); ++index) {
                if (index != 0) {
                    out += indent > 0 ? "," : ", ";
                }
                if (indent > 0) {
                    out += newline(depth + 1);
                }
                out += json_stringify(
                    items[index], depth + 1, indent);
            }
            if (indent > 0) {
                out += newline(depth);
            }
            out += "]";
            return out;
        }
        case Tag::Map: {
            if (as_map(value)->entries.empty()) {
                return "{}";
            }
            std::string out = "{";
            bool first = true;
            for (const auto& entry : as_map(value)->entries) {
                if (entry.first.tag != Tag::Str) {
                    throw std::runtime_error(
                        "JSON object keys must be strings");
                }
                if (!first) {
                    out += indent > 0 ? "," : ", ";
                }
                first = false;
                if (indent > 0) {
                    out += newline(depth + 1);
                }
                out += "\""
                    + json_escape(as_string_const(entry.first)->utf8)
                    + "\": ";
                out += json_stringify(
                    entry.second, depth + 1, indent);
            }
            if (indent > 0) {
                out += newline(depth);
            }
            out += "}";
            return out;
        }
        default:
            throw std::runtime_error(
                "JSON cannot stringify this value");
    }
}

class JsonParser {
public:
    JsonParser(const std::string& text, Arena& arena)
        : text_(text), arena_(arena) {}

    Value parse() {
        skip();
        Value value = parse_value();
        skip();
        if (position_ != text_.size()) {
            throw std::runtime_error("trailing JSON data");
        }
        return value;
    }

private:
    void skip() {
        while (position_ < text_.size()
               && std::isspace(
                   static_cast<unsigned char>(text_[position_]))) {
            ++position_;
        }
    }

    Value parse_value() {
        skip();
        if (position_ >= text_.size()) {
            throw std::runtime_error("unexpected end of JSON");
        }
        const char character = text_[position_];
        if (character == '{') {
            return parse_object();
        }
        if (character == '[') {
            return parse_array();
        }
        if (character == '"') {
            return make_string(arena_.allocate_string_utf8(parse_string()));
        }
        if (character == 't' && text_.compare(position_, 4, "true") == 0) {
            position_ += 4;
            return make_bool(true);
        }
        if (character == 'f' && text_.compare(position_, 5, "false") == 0) {
            position_ += 5;
            return make_bool(false);
        }
        if (character == 'n' && text_.compare(position_, 4, "null") == 0) {
            position_ += 4;
            return make_nova();
        }
        return parse_number();
    }

    Value parse_object() {
        ++position_;
        MapObject* map = arena_.allocate_map();
        skip();
        if (position_ < text_.size() && text_[position_] == '}') {
            ++position_;
            return make_map(map);
        }
        while (true) {
            skip();
            if (position_ >= text_.size() || text_[position_] != '"') {
                throw std::runtime_error("JSON object key is missing");
            }
            const std::string key = parse_string();
            skip();
            if (position_ >= text_.size() || text_[position_] != ':') {
                throw std::runtime_error("JSON object colon is missing");
            }
            ++position_;
            Value value = parse_value();
            map_set(
                *map,
                make_string(arena_.allocate_string_utf8(key)),
                value);
            skip();
            if (position_ < text_.size() && text_[position_] == ',') {
                ++position_;
                continue;
            }
            if (position_ < text_.size() && text_[position_] == '}') {
                ++position_;
                break;
            }
            throw std::runtime_error("JSON object is malformed");
        }
        return make_map(map);
    }

    Value parse_array() {
        ++position_;
        std::vector<Value> items;
        skip();
        if (position_ < text_.size() && text_[position_] == ']') {
            ++position_;
            return make_array(arena_.allocate_array(std::move(items)));
        }
        while (true) {
            items.push_back(parse_value());
            skip();
            if (position_ < text_.size() && text_[position_] == ',') {
                ++position_;
                continue;
            }
            if (position_ < text_.size() && text_[position_] == ']') {
                ++position_;
                break;
            }
            throw std::runtime_error("JSON array is malformed");
        }
        return make_array(arena_.allocate_array(std::move(items)));
    }

    std::string parse_string() {
        ++position_;
        std::string out;
        while (position_ < text_.size()) {
            const char character = text_[position_++];
            if (character == '"') {
                return out;
            }
            if (character == '\\' && position_ < text_.size()) {
                const char escaped = text_[position_++];
                switch (escaped) {
                    case 'n': out.push_back('\n'); break;
                    case 'r': out.push_back('\r'); break;
                    case 't': out.push_back('\t'); break;
                    case 'b': out.push_back('\b'); break;
                    case 'f': out.push_back('\f'); break;
                    case '\\': out.push_back('\\'); break;
                    case '/': out.push_back('/'); break;
                    case '"': out.push_back('"'); break;
                    default: out.push_back(escaped); break;
                }
                continue;
            }
            out.push_back(character);
        }
        throw std::runtime_error("unterminated JSON string");
    }

    Value parse_number() {
        const std::size_t start = position_;
        while (position_ < text_.size()
               && (std::isdigit(
                       static_cast<unsigned char>(text_[position_]))
                   || text_[position_] == '-'
                   || text_[position_] == '+'
                   || text_[position_] == '.'
                   || text_[position_] == 'e'
                   || text_[position_] == 'E')) {
            ++position_;
        }
        if (start == position_) {
            throw std::runtime_error("invalid JSON value");
        }
        const std::string number =
            text_.substr(start, position_ - start);
        try {
            if (number.find_first_of(".eE") != std::string::npos) {
                return make_num(std::stod(number));
            }
            return make_int(std::stoll(number));
        } catch (const std::exception&) {
            throw std::runtime_error("invalid JSON number");
        }
    }

    const std::string& text_;
    Arena& arena_;
    std::size_t position_ = 0;
};

std::string url_encode(const std::string& text) {
    static const char* hex = "0123456789ABCDEF";
    std::string out;
    for (const unsigned char character : text) {
        if (std::isalnum(character) || character == '-'
            || character == '_' || character == '.' || character == '~') {
            out.push_back(static_cast<char>(character));
        } else if (character == ' ') {
            out.push_back('+');
        } else {
            out.push_back('%');
            out.push_back(hex[character >> 4]);
            out.push_back(hex[character & 0x0F]);
        }
    }
    return out;
}

int hex_value(char character) {
    if (character >= '0' && character <= '9') {
        return character - '0';
    }
    if (character >= 'a' && character <= 'f') {
        return character - 'a' + 10;
    }
    if (character >= 'A' && character <= 'F') {
        return character - 'A' + 10;
    }
    return -1;
}

std::string url_decode(const std::string& text) {
    std::string out;
    out.reserve(text.size());
    for (std::size_t index = 0; index < text.size(); ++index) {
        const char character = text[index];
        if (character == '+') {
            out.push_back(' ');
            continue;
        }
        if (character == '%' && index + 2 < text.size()) {
            const int high = hex_value(text[index + 1]);
            const int low = hex_value(text[index + 2]);
            if (high >= 0 && low >= 0) {
                out.push_back(static_cast<char>((high << 4) | low));
                index += 2;
                continue;
            }
        }
        out.push_back(character);
    }
    return out;
}

std::array<std::uint8_t, 32> hmac_sha256_bytes(
    const std::string& key, const std::string& message) {
    std::array<std::uint8_t, 64> key_block{};
    if (key.size() > key_block.size()) {
        const auto digest = sha256(
            reinterpret_cast<const std::uint8_t*>(key.data()),
            key.size());
        std::copy(digest.begin(), digest.end(), key_block.begin());
    } else {
        std::copy(key.begin(), key.end(), key_block.begin());
    }
    std::vector<std::uint8_t> inner;
    inner.reserve(64 + message.size());
    for (const std::uint8_t byte : key_block) {
        inner.push_back(static_cast<std::uint8_t>(byte ^ 0x36));
    }
    inner.insert(inner.end(), message.begin(), message.end());
    const auto inner_digest = sha256(inner.data(), inner.size());
    std::vector<std::uint8_t> outer;
    outer.reserve(96);
    for (const std::uint8_t byte : key_block) {
        outer.push_back(static_cast<std::uint8_t>(byte ^ 0x5C));
    }
    outer.insert(outer.end(), inner_digest.begin(), inner_digest.end());
    return sha256(outer.data(), outer.size());
}

std::string hex_bytes(const std::uint8_t* data, std::size_t size) {
    static const char* digits = "0123456789abcdef";
    std::string out;
    out.reserve(size * 2);
    for (std::size_t index = 0; index < size; ++index) {
        out.push_back(digits[data[index] >> 4]);
        out.push_back(digits[data[index] & 0x0F]);
    }
    return out;
}

std::string random_hex(std::size_t size) {
    std::random_device device;
    std::vector<std::uint8_t> bytes(size);
    for (std::uint8_t& byte : bytes) {
        byte = static_cast<std::uint8_t>(device() & 0xFF);
    }
    return hex_bytes(bytes.data(), bytes.size());
}

std::tm utc_time(std::time_t value) {
    std::tm result{};
#ifdef _WIN32
    gmtime_s(&result, &value);
#else
    gmtime_r(&value, &result);
#endif
    return result;
}

std::string iso_now() {
    const auto now = std::chrono::system_clock::now();
    const auto seconds =
        std::chrono::time_point_cast<std::chrono::seconds>(now);
    const auto micros = std::chrono::duration_cast<std::chrono::microseconds>(
        now - seconds).count();
    const std::time_t stamp =
        std::chrono::system_clock::to_time_t(now);
    const std::tm moment = utc_time(stamp);
    char buffer[32];
    std::strftime(
        buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S", &moment);
    char result[64];
    std::snprintf(
        result, sizeof(result), "%s.%06lldZ", buffer,
        static_cast<long long>(micros));
    return result;
}

std::string format_fixed_number(double value, int decimals) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(decimals) << value;
    return out.str();
}

std::string format_epoch_text(double epoch, const std::string& format) {
    const std::time_t stamp =
        static_cast<std::time_t>(std::floor(epoch));
    const std::tm moment = utc_time(stamp);
    std::string pattern = format;
    const std::size_t fraction_at = pattern.find("%f");
    if (fraction_at != std::string::npos) {
        const double fraction =
            epoch - std::floor(epoch);
        char fraction_text[16];
        std::snprintf(
            fraction_text, sizeof(fraction_text), "%06d",
            static_cast<int>(fraction * 1000000.0 + 0.5));
        pattern.replace(fraction_at, 2, fraction_text);
    }
    std::vector<char> buffer(4096);
    const std::size_t written = std::strftime(
        buffer.data(), buffer.size(), pattern.c_str(), &moment);
    if (written == 0) {
        return "";
    }
    return std::string(buffer.data(), written);
}

int log_rank(const std::string& level) {
    if (level == "debug") {
        return 10;
    }
    if (level == "warn") {
        return 30;
    }
    if (level == "error") {
        return 40;
    }
    return 20;
}

std::string log_timestamp() {
    const std::tm moment = utc_time(std::time(nullptr));
    char buffer[32];
    std::strftime(
        buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &moment);
    return buffer;
}

std::string python_type_name(const Value& value) {
    switch (value.tag) {
        case Tag::Nova: return "NoneType";
        case Tag::Undef: return "NoneType";
        case Tag::Bool: return "bool";
        case Tag::Int:
        case Tag::BigInt: return "int";
        case Tag::Num: return "float";
        case Tag::Char:
        case Tag::Str: return "str";
        case Tag::Arr: return "list";
        case Tag::Tup: return "tuple";
        case Tag::Map: return "dict";
        case Tag::Set: return "set";
        case Tag::Fun: return "PowangFunction";
        case Tag::Error: return "PowangError";
        case Tag::Obj: return "PowangObjectType";
        default: return "object";
    }
}

Value query_parse(Arena& arena, const std::string& query) {
    MapObject* map = arena.allocate_map();
    std::size_t start = 0;
    while (start <= query.size()) {
        const std::size_t end = query.find('&', start);
        const std::string part = query.substr(
            start,
            end == std::string::npos ? std::string::npos : end - start);
        if (!part.empty()) {
            const std::size_t equals = part.find('=');
            const std::string raw_key = equals == std::string::npos
                ? part : part.substr(0, equals);
            const std::string raw_value = equals == std::string::npos
                ? "" : part.substr(equals + 1);
            const Value key = make_string(
                arena.allocate_string_utf8(url_decode(raw_key)));
            const Value value = make_string(
                arena.allocate_string_utf8(url_decode(raw_value)));
            const Value* existing = map_get(*map, key);
            if (existing == nullptr) {
                map_set(*map, key, value);
            } else if (existing->tag == Tag::Arr) {
                auto& items = as_array(*existing)->items;
                items.push_back(value);
            } else {
                std::vector<Value> items{*existing, value};
                map_set(
                    *map, key,
                    make_array(arena.allocate_array(std::move(items))));
            }
        }
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }
    return make_map(map);
}

} // namespace

Value Host::call_extern(
    std::string_view name,
    const Value* arguments,
    std::size_t argument_count,
    Arena& arena) {
    (void)name;
    (void)arguments;
    (void)argument_count;
    (void)arena;
    throw std::runtime_error("native extern ABI is not implemented");
}

StdoutHost::StdoutHost() {
    const char* level = std::getenv("POWANG_LOG_LEVEL");
    if (level != nullptr && level[0] != '\0') {
        log_level_ = level;
        for (char& character : log_level_) {
            character = static_cast<char>(
                std::tolower(static_cast<unsigned char>(character)));
        }
    }
}

StdoutHost::StdoutHost(int argc, char** argv) : StdoutHost() {
    for (int index = 1; index < argc; ++index) {
        script_arguments_.emplace_back(
            argv[index] != nullptr ? argv[index] : "");
    }
}

void StdoutHost::emit_log(
    const std::string& level,
    const std::string& message,
    const std::string& fields) {
    if (log_rank(level) < log_rank(log_level_)) {
        return;
    }
    std::string upper = level;
    for (char& character : upper) {
        character = static_cast<char>(
            std::toupper(static_cast<unsigned char>(character)));
    }
    std::string line = log_timestamp() + " " + upper + " " + message;
    if (!fields.empty() && fields != "{}") {
        line += " " + fields;
    }
    write_error(line + "\n");
}

void StdoutHost::write(const std::string& text) {
    if (!text.empty()) {
        std::fwrite(text.data(), 1, text.size(), stdout);
    }
    std::fflush(stdout);
}

void StdoutHost::write_error(const std::string& text) {
    if (!text.empty()) {
        std::fwrite(text.data(), 1, text.size(), stderr);
    }
    std::fflush(stderr);
}

Value StdoutHost::call_extern(
    std::string_view name,
    const Value* arguments,
    std::size_t argument_count,
    Arena& arena) {
    auto text_argument = [&](std::size_t index,
                             const char* name = "text") -> std::string {
        if (index >= argument_count || arguments[index].tag != Tag::Str) {
            const std::string actual = index < argument_count
                ? python_type_name(arguments[index]) : "NoneType";
            throw HostCallError(
                "ValueError",
                std::string(name) + " must be a string, got " + actual);
        }
        return as_string_const(arguments[index])->utf8;
    };
    auto string_value = [&](const std::string& text) {
        return make_string(arena.allocate_string_utf8(text));
    };
    auto codepoints = [&](const std::string& text) {
        return arena.allocate_string_utf8(text)->code_points;
    };
    if (name == "stdlib_strings.trim" && argument_count == 1) {
        const std::string text = text_argument(0);
        std::size_t start = 0;
        std::size_t end = text.size();
        while (start < end
               && std::isspace(static_cast<unsigned char>(text[start]))) {
            ++start;
        }
        while (end > start
               && std::isspace(
                   static_cast<unsigned char>(text[end - 1]))) {
            --end;
        }
        return string_value(text.substr(start, end - start));
    }
    if ((name == "stdlib_strings.upper"
         || name == "stdlib_strings.lower")
        && argument_count == 1) {
        std::string text = text_argument(0);
        for (char& character : text) {
            const unsigned char value =
                static_cast<unsigned char>(character);
            if (value < 0x80u) {
                character = name == "stdlib_strings.upper"
                    ? static_cast<char>(std::toupper(value))
                    : static_cast<char>(std::tolower(value));
            }
        }
        return string_value(text);
    }
    if (name == "stdlib_strings.replace" && argument_count == 3) {
        std::string text = text_argument(0);
        const std::string old_text = text_argument(1);
        const std::string new_text = text_argument(2);
        if (old_text.empty()) {
            return string_value(text);
        }
        std::size_t position = 0;
        while ((position = text.find(old_text, position))
               != std::string::npos) {
            text.replace(position, old_text.size(), new_text);
            position += new_text.size();
        }
        return string_value(text);
    }
    if (name == "stdlib_strings.contains" && argument_count == 2) {
        return make_bool(
            text_argument(0).find(text_argument(1)) != std::string::npos);
    }
    if (name == "stdlib_strings.starts_with" && argument_count == 2) {
        const std::string text = text_argument(0);
        const std::string prefix = text_argument(1);
        return make_bool(
            text.size() >= prefix.size()
            && text.compare(0, prefix.size(), prefix) == 0);
    }
    if (name == "stdlib_strings.ends_with" && argument_count == 2) {
        const std::string text = text_argument(0);
        const std::string suffix = text_argument(1);
        return make_bool(
            text.size() >= suffix.size()
            && text.compare(
                   text.size() - suffix.size(), suffix.size(), suffix)
                == 0);
    }
    if (name == "stdlib_strings.repeat" && argument_count == 2) {
        const std::string text = text_argument(0);
        const std::int64_t count =
            arguments[1].tag == Tag::Int ? arguments[1].i : 0;
        std::string result;
        for (std::int64_t index = 0; index < count; ++index) {
            result += text;
        }
        return string_value(result);
    }
    if (name == "stdlib_strings.slice" && argument_count == 3) {
        std::u32string text = codepoints(text_argument(0));
        std::int64_t start =
            arguments[1].tag == Tag::Int ? arguments[1].i : 0;
        std::int64_t end =
            arguments[2].tag == Tag::Int ? arguments[2].i
                                         : static_cast<std::int64_t>(
                                             text.size());
        const std::int64_t length =
            static_cast<std::int64_t>(text.size());
        if (start < 0) {
            start += length;
        }
        if (end < 0) {
            end += length;
        }
        start = std::max<std::int64_t>(0, std::min(start, length));
        end = std::max<std::int64_t>(start, std::min(end, length));
        return make_string(arena.allocate_string(
            text.substr(
                static_cast<std::size_t>(start),
                static_cast<std::size_t>(end - start))));
    }
    if (name == "stdlib_strings.split"
        && (argument_count == 1 || argument_count == 2)) {
        const std::string text = text_argument(0);
        const std::string separator =
            argument_count == 2 ? text_argument(1) : " ";
        std::vector<Value> parts;
        if (separator.empty()) {
            for (const char32_t code_point : codepoints(text)) {
                parts.push_back(make_string(
                    arena.allocate_string(
                        std::u32string(1, code_point))));
            }
        } else {
            std::size_t start = 0;
            while (true) {
                const std::size_t found =
                    text.find(separator, start);
                if (found == std::string::npos) {
                    parts.push_back(string_value(text.substr(start)));
                    break;
                }
                parts.push_back(string_value(
                    text.substr(start, found - start)));
                start = found + separator.size();
            }
        }
        return make_array(arena.allocate_array(std::move(parts)));
    }
    if (name == "stdlib_strings.join" && argument_count == 2) {
        if (arguments[0].tag != Tag::Arr) {
            throw std::runtime_error(
                "stdlib_strings.join expects an array");
        }
        const std::string separator = text_argument(1);
        std::string result;
        const auto& items = as_array(arguments[0])->items;
        for (std::size_t index = 0; index < items.size(); ++index) {
            if (index != 0) {
                result += separator;
            }
            if (items[index].tag != Tag::Str) {
                throw std::runtime_error(
                    "stdlib_strings.join expects string items");
            }
            result += as_string_const(items[index])->utf8;
        }
        return string_value(result);
    }
    if (name == "stdlib_strings.char_code" && argument_count == 1) {
        const std::u32string text = codepoints(text_argument(0));
        if (text.size() != 1) {
            throw std::runtime_error(
                "stdlib_strings.char_code expects one character");
        }
        return make_int(static_cast<std::int64_t>(text.front()));
    }
    if (name == "stdlib_strings.from_char_code" && argument_count == 1) {
        if (arguments[0].tag != Tag::Int) {
            throw std::runtime_error(
                "stdlib_strings.from_char_code expects an int");
        }
        return make_string(arena.allocate_string(
            std::u32string(
                1, static_cast<char32_t>(arguments[0].i))));
    }
    if (name == "stdlib_strings.parse_int" && argument_count == 1) {
        const std::string text = text_argument(0);
        const std::size_t start = text.find_first_not_of(" \t\r\n");
        const std::size_t end = text.find_last_not_of(" \t\r\n");
        const std::string trimmed = start == std::string::npos
            ? "" : text.substr(start, end - start + 1);
        try {
            std::size_t consumed = 0;
            const long long value = std::stoll(trimmed, &consumed);
            if (consumed != trimmed.size()) {
                throw std::invalid_argument("trailing");
            }
            return make_int(value);
        } catch (const std::exception&) {
            throw HostCallError(
                "ValueError", "not a valid integer: '" + text + "'");
        }
    }
    if (name == "stdlib_strings.parse_number" && argument_count == 1) {
        const std::string text = text_argument(0);
        const std::size_t start = text.find_first_not_of(" \t\r\n");
        const std::size_t end = text.find_last_not_of(" \t\r\n");
        const std::string trimmed = start == std::string::npos
            ? "" : text.substr(start, end - start + 1);
        try {
            std::size_t consumed = 0;
            const double value = std::stod(trimmed, &consumed);
            if (consumed != trimmed.size()) {
                throw std::invalid_argument("trailing");
            }
            return make_num(value);
        } catch (const std::exception&) {
            throw HostCallError(
                "ValueError", "not a valid number: '" + text + "'");
        }
    }
    if (name == "stdlib_strings.format_number" && argument_count == 2) {
        if (arguments[0].tag == Tag::Bool
            || (arguments[0].tag != Tag::Int
                && arguments[0].tag != Tag::Num)) {
            throw HostCallError(
                "ValueError",
                "value must be a number, got "
                    + python_type_name(arguments[0]));
        }
        if (arguments[1].tag == Tag::Bool
            || arguments[1].tag != Tag::Int) {
            throw HostCallError(
                "ValueError",
                "decimals must be an integer, got "
                    + python_type_name(arguments[1]));
        }
        const std::int64_t decimals = arguments[1].i;
        if (decimals < 0) {
            throw HostCallError(
                "ValueError",
                "decimals must not be negative, got "
                    + std::to_string(decimals));
        }
        const double value = arguments[0].tag == Tag::Int
            ? static_cast<double>(arguments[0].i)
            : arguments[0].d;
        return string_value(format_fixed_number(
            value, static_cast<int>(decimals)));
    }
    if ((name == "stdlib_strings.pad_left"
         || name == "stdlib_strings.pad_right")
        && (argument_count == 2 || argument_count == 3)) {
        const std::string text = text_argument(0);
        const std::u32string text_codepoints = codepoints(text);
        if (arguments[1].tag == Tag::Bool
            || arguments[1].tag != Tag::Int) {
            throw HostCallError(
                "ValueError",
                "width must be an integer, got "
                    + python_type_name(arguments[1]));
        }
        const std::int64_t width = arguments[1].i;
        char32_t fill = U' ';
        if (argument_count == 3) {
            const std::u32string fill_codepoints =
                codepoints(text_argument(2, "fill"));
            if (fill_codepoints.size() != 1) {
                throw HostCallError(
                    "ValueError",
                    "fill must be exactly one character, got "
                        + std::to_string(fill_codepoints.size()));
            }
            fill = fill_codepoints.front();
        }
        if (width <= static_cast<std::int64_t>(
                         text_codepoints.size())) {
            return string_value(text);
        }
        const std::size_t padding = static_cast<std::size_t>(
            width - static_cast<std::int64_t>(text_codepoints.size()));
        std::u32string result;
        if (name == "stdlib_strings.pad_left") {
            result.append(padding, fill);
            result += text_codepoints;
        } else {
            result = text_codepoints;
            result.append(padding, fill);
        }
        return make_string(arena.allocate_string(std::move(result)));
    }
    if (name == "stdlib_json.stringify"
        && (argument_count == 1 || argument_count == 2)) {
        int indent = 0;
        if (argument_count == 2) {
            if (arguments[1].tag == Tag::Bool
                || arguments[1].tag != Tag::Int) {
                throw HostCallError(
                    "ValueError",
                    "indent must be an integer, got "
                        + python_type_name(arguments[1]));
            }
            indent = static_cast<int>(arguments[1].i);
            if (indent < 0) {
                throw HostCallError(
                    "ValueError",
                    "indent must not be negative, got "
                        + std::to_string(indent));
            }
        }
        return string_value(
            json_stringify(arguments[0], 0, indent));
    }
    if (name == "stdlib_json.parse" && argument_count == 1) {
        return JsonParser(text_argument(0), arena).parse();
    }
    if (name == "stdlib_url.encode" && argument_count == 1) {
        return string_value(url_encode(text_argument(0)));
    }
    if (name == "stdlib_url.decode" && argument_count == 1) {
        return string_value(url_decode(text_argument(0)));
    }
    if (name == "stdlib_url.parse_query" && argument_count == 1) {
        return query_parse(arena, text_argument(0, "query"));
    }
    if (name == "stdlib_url.query_build" && argument_count == 1) {
        if (arguments[0].tag != Tag::Map) {
            throw HostCallError(
                "ValueError",
                "mapping must be a map, got "
                    + python_type_name(arguments[0]));
        }
        const auto query_text = [&](const Value& value,
                                    const std::string& name)
            -> std::string {
            if (value.tag == Tag::Str) {
                return as_string_const(value)->utf8;
            }
            if (value.tag == Tag::Bool) {
                return value.b ? "true" : "false";
            }
            if (value.tag == Tag::Nova) {
                return "";
            }
            if (value.tag == Tag::Int || value.tag == Tag::BigInt
                || value.tag == Tag::Num) {
                return format_value(value);
            }
            throw HostCallError(
                "ValueError",
                "query value for '" + name
                    + "' must be a string, number, bool or nova, got "
                    + python_type_name(value));
        };
        std::string out;
        for (const auto& entry : as_map(arguments[0])->entries) {
            if (entry.first.tag != Tag::Str) {
                throw HostCallError(
                    "ValueError",
                    "query keys must be strings, got "
                        + python_type_name(entry.first));
            }
            const std::string raw_key =
                as_string_const(entry.first)->utf8;
            const std::string key = url_encode(raw_key);
            const auto append = [&](const Value& value) {
                if (!out.empty()) {
                    out.push_back('&');
                }
                out += key;
                out.push_back('=');
                out += url_encode(query_text(value, raw_key));
            };
            if (entry.second.tag == Tag::Arr
                || entry.second.tag == Tag::Tup) {
                const std::vector<Value>& items =
                    entry.second.tag == Tag::Arr
                    ? as_array(entry.second)->items
                    : as_tuple(entry.second)->items;
                for (const Value& item : items) {
                    append(item);
                }
            } else {
                append(entry.second);
            }
        }
        return string_value(out);
    }
    if (name == "stdlib_crypto.sha256" && argument_count == 1) {
        const std::string text = text_argument(0);
        const auto digest = sha256(
            reinterpret_cast<const std::uint8_t*>(text.data()),
            text.size());
        return string_value(hex_bytes(digest.data(), digest.size()));
    }
    if (name == "stdlib_crypto.hmac_sha256" && argument_count == 2) {
        const auto digest = hmac_sha256_bytes(
            text_argument(0, "key"), text_argument(1, "message"));
        return string_value(hex_bytes(digest.data(), digest.size()));
    }
    if (name == "stdlib_crypto.random_token" && argument_count == 1) {
        if (arguments[0].tag == Tag::Bool
            || arguments[0].tag != Tag::Int) {
            throw HostCallError(
                "ValueError",
                "byte_length must be an integer, got "
                    + python_type_name(arguments[0]));
        }
        const std::int64_t length = arguments[0].i;
        if (length <= 0) {
            throw HostCallError(
                "ValueError",
                "byte_length must be positive, got "
                    + std::to_string(length));
        }
        if (length > 4096) {
            throw HostCallError(
                "ValueError",
                "byte_length must be at most 4096, got "
                    + std::to_string(length));
        }
        return string_value(
            random_hex(static_cast<std::size_t>(length)));
    }
    if (name == "stdlib_crypto.constant_time_compare"
        && argument_count == 2) {
        const std::string left = text_argument(0, "a");
        const std::string right = text_argument(1, "b");
        std::size_t difference = left.size() ^ right.size();
        const std::size_t length =
            std::min(left.size(), right.size());
        for (std::size_t index = 0; index < length; ++index) {
            difference |= static_cast<unsigned char>(left[index])
                ^ static_cast<unsigned char>(right[index]);
        }
        return make_bool(difference == 0);
    }
    if (name == "math.sqrt" && argument_count == 1) {
        return make_num(std::sqrt(numeric_argument(arguments[0])));
    }
    if (name == "math.pow" && argument_count == 2) {
        return make_num(std::pow(
            numeric_argument(arguments[0]),
            numeric_argument(arguments[1])));
    }
    if (name == "math.log"
        && (argument_count == 1 || argument_count == 2)) {
        const double value = numeric_argument(arguments[0]);
        const double base = argument_count == 2
            ? numeric_argument(arguments[1]) : 10.0;
        return make_num(std::log(value) / std::log(base));
    }
    if (name == "math.cos" && argument_count == 1) {
        return make_num(std::cos(numeric_argument(arguments[0])));
    }
    if (name == "math.sin" && argument_count == 1) {
        return make_num(std::sin(numeric_argument(arguments[0])));
    }
    if (name == "math.tan" && argument_count == 1) {
        return make_num(std::tan(numeric_argument(arguments[0])));
    }
    if (name == "stdlib_time.sleep_ms" && argument_count == 1) {
        const std::int64_t milliseconds =
            arguments[0].tag == Tag::Int ? arguments[0].i : 0;
        if (milliseconds > 0) {
            std::this_thread::sleep_for(
                std::chrono::milliseconds(milliseconds));
        }
        return make_nova();
    }
    if (name == "stdlib_time.epoch" && argument_count == 0) {
        const auto now = std::chrono::system_clock::now();
        const auto duration =
            now.time_since_epoch();
        return make_num(
            std::chrono::duration<double>(duration).count());
    }
    if (name == "stdlib_time.now_iso" && argument_count == 0) {
        return string_value(iso_now());
    }
    if (name == "stdlib_time.format_epoch" && argument_count == 2) {
        if (arguments[0].tag == Tag::Bool
            || (arguments[0].tag != Tag::Int
                && arguments[0].tag != Tag::Num)) {
            throw HostCallError(
                "ValueError",
                "epoch must be a number, got "
                    + python_type_name(arguments[0]));
        }
        const double epoch = arguments[0].tag == Tag::Int
            ? static_cast<double>(arguments[0].i)
            : arguments[0].d;
        return string_value(
            format_epoch_text(epoch, text_argument(1, "fmt")));
    }
    if (name == "stdlib_env.argv" && argument_count == 0) {
        std::vector<Value> values;
        values.reserve(script_arguments_.size());
        for (const std::string& argument : script_arguments_) {
            values.push_back(string_value(argument));
        }
        return make_array(arena.allocate_array(std::move(values)));
    }
    if (name == "stdlib_env.argv_count" && argument_count == 0) {
        return make_int(
            static_cast<std::int64_t>(script_arguments_.size()));
    }
    if (name == "stdlib_env.argv_get" && argument_count == 1) {
        if (arguments[0].tag == Tag::Bool
            || arguments[0].tag != Tag::Int) {
            throw HostCallError(
                "ValueError",
                "index must be an integer, got "
                    + python_type_name(arguments[0]));
        }
        std::int64_t index = arguments[0].i;
        if (index < 0) {
            index += static_cast<std::int64_t>(
                script_arguments_.size());
        }
        if (index < 0
            || index >= static_cast<std::int64_t>(
                script_arguments_.size())) {
            return make_nova();
        }
        return string_value(
            script_arguments_[static_cast<std::size_t>(index)]);
    }
    if (name == "stdlib_env.get" && argument_count == 1) {
        const std::string variable = text_argument(0, "name");
        const char* value = std::getenv(variable.c_str());
        return value == nullptr ? make_nova() : string_value(value);
    }
    if (name == "stdlib_env.get_or" && argument_count == 2) {
        const std::string variable = text_argument(0, "name");
        const std::string fallback = text_argument(1, "default");
        const char* value = std::getenv(variable.c_str());
        return string_value(value == nullptr ? fallback : value);
    }
    if (name == "stdlib_env.has" && argument_count == 1) {
        const std::string variable = text_argument(0, "name");
        return make_bool(std::getenv(variable.c_str()) != nullptr);
    }
    if (name == "stdlib_log.debug" || name == "stdlib_log.info"
        || name == "stdlib_log.warn" || name == "stdlib_log.error") {
        const std::string level =
            std::string(name.substr(std::string("stdlib_log.").size()));
        emit_log(level, text_argument(0, "message"), "");
        return make_nova();
    }
    if (name == "stdlib_log.with_fields" && argument_count == 3) {
        std::string level = text_argument(0, "level");
        for (char& character : level) {
            character = static_cast<char>(
                std::tolower(static_cast<unsigned char>(character)));
        }
        const std::string message = text_argument(1, "message");
        std::string fields;
        if (arguments[2].tag == Tag::Map
            && !as_map(arguments[2])->entries.empty()) {
            fields = json_stringify(arguments[2], 0, 0);
        }
        emit_log(level, message, fields);
        return make_nova();
    }
    if (name == "stdlib_log.set_level" && argument_count == 1) {
        const std::string original = text_argument(0, "level");
        std::string level = original;
        for (char& character : level) {
            character = static_cast<char>(
                std::tolower(static_cast<unsigned char>(character)));
        }
        if (level != "debug" && level != "info" && level != "warn"
            && level != "error") {
            throw HostCallError(
                "ValueError",
                "unknown log level: '" + original
                    + "'; expected debug, info, warn or error");
        }
        log_level_ = level;
        return make_nova();
    }
    if (name == "stdlib_log.is_enabled" && argument_count == 1) {
        std::string level = text_argument(0, "level");
        for (char& character : level) {
            character = static_cast<char>(
                std::tolower(static_cast<unsigned char>(character)));
        }
        return make_bool(
            log_rank(level) >= log_rank(log_level_));
    }
    if (name == "stdlib_log.access" && argument_count == 5) {
        if (arguments[0].tag != Tag::Int) {
            throw HostCallError(
                "ValueError",
                "request_id must be an integer, got "
                    + python_type_name(arguments[0]));
        }
        if (arguments[3].tag != Tag::Int) {
            throw HostCallError(
                "ValueError",
                "status must be an integer, got "
                    + python_type_name(arguments[3]));
        }
        const std::string method = text_argument(1, "method");
        const std::string path = text_argument(2, "path");
        double elapsed = 0.0;
        if (arguments[4].tag == Tag::Num) {
            elapsed = arguments[4].d;
        } else if (arguments[4].tag == Tag::Int) {
            elapsed = static_cast<double>(arguments[4].i);
        } else {
            throw HostCallError(
                "ValueError",
                "elapsed_ms must be a number, got "
                    + python_type_name(arguments[4]));
        }
        MapObject* fields = arena.allocate_map();
        map_set(
            *fields, string_value("request_id"),
            make_int(arguments[0].i));
        map_set(*fields, string_value("method"), string_value(method));
        map_set(*fields, string_value("path"), string_value(path));
        map_set(
            *fields, string_value("status"),
            make_int(arguments[3].i));
        map_set(
            *fields, string_value("elapsed_ms"),
            make_num(std::round(elapsed * 1000.0) / 1000.0));
        emit_log(
            "info", "request",
            json_stringify(make_map(fields), 0, 0));
        return make_nova();
    }
    throw std::runtime_error("native extern ABI is not implemented");
}

} // namespace pwb
