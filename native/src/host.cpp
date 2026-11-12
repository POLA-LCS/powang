#include "pwb/host.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdio>
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

std::string json_stringify(const Value& value, int depth = 0) {
    if (depth > 100) {
        throw std::runtime_error("JSON nesting is too deep");
    }
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
            std::string out = "[";
            for (std::size_t index = 0; index < items.size(); ++index) {
                if (index != 0) {
                    out += ", ";
                }
                out += json_stringify(items[index], depth + 1);
            }
            out += "]";
            return out;
        }
        case Tag::Map: {
            std::string out = "{";
            bool first = true;
            for (const auto& entry : as_map(value)->entries) {
                if (entry.first.tag != Tag::Str) {
                    throw std::runtime_error(
                        "JSON object keys must be strings");
                }
                if (!first) {
                    out += ", ";
                }
                first = false;
                out += "\""
                    + json_escape(as_string_const(entry.first)->utf8)
                    + "\": ";
                out += json_stringify(entry.second, depth + 1);
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
    auto text_argument = [&](std::size_t index) -> std::string {
        if (index >= argument_count || arguments[index].tag != Tag::Str) {
            throw std::runtime_error(
                "native extern string argument is not a string");
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
        try {
            return make_int(std::stoll(text));
        } catch (const std::exception&) {
            throw std::runtime_error(
                "stdlib_strings.parse_int could not parse the value");
        }
    }
    if (name == "stdlib_json.stringify"
        && (argument_count == 1 || argument_count == 2)) {
        return string_value(json_stringify(arguments[0]));
    }
    if (name == "stdlib_json.parse" && argument_count == 1) {
        return JsonParser(text_argument(0), arena).parse();
    }
    if (name == "stdlib_url.encode" && argument_count == 1) {
        return string_value(url_encode(text_argument(0)));
    }
    if (name == "stdlib_url.query_build" && argument_count == 1) {
        if (arguments[0].tag != Tag::Map) {
            throw std::runtime_error(
                "stdlib_url.query_build expects a map");
        }
        std::string out;
        for (const auto& entry : as_map(arguments[0])->entries) {
            if (entry.first.tag != Tag::Str) {
                throw std::runtime_error(
                    "query keys must be strings");
            }
            if (!out.empty()) {
                out.push_back('&');
            }
            out += url_encode(as_string_const(entry.first)->utf8);
            out.push_back('=');
            if (entry.second.tag == Tag::Str) {
                out += url_encode(
                    as_string_const(entry.second)->utf8);
            } else {
                out += url_encode(format_value(entry.second));
            }
        }
        return string_value(out);
    }
    if (name == "stdlib_crypto.sha256" && argument_count == 1) {
        const std::string text = text_argument(0);
        const std::array<std::uint8_t, 32> digest = sha256(
            reinterpret_cast<const std::uint8_t*>(text.data()),
            text.size());
        static const char* digits = "0123456789abcdef";
        std::string hex;
        hex.reserve(64);
        for (const std::uint8_t byte : digest) {
            hex.push_back(digits[byte >> 4]);
            hex.push_back(digits[byte & 0x0F]);
        }
        return string_value(hex);
    }
    if (name == "stdlib_crypto.constant_time_compare"
        && argument_count == 2) {
        const std::string left = text_argument(0);
        const std::string right = text_argument(1);
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
    if (name == "stdlib_env.argv_count") {
        return make_int(0);
    }
    if (name == "stdlib_env.argv_get") {
        return make_nova();
    }
    throw std::runtime_error("native extern ABI is not implemented");
}

} // namespace pwb
