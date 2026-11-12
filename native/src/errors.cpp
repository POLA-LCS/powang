#include "pwb/errors.hpp"

#include <utility>

#include "pwb/object.hpp"

namespace pwb {
namespace {

std::string kind_prefix(const std::string& kind) {
    if (kind.empty() || kind == "ERROR") {
        return "[ERROR]";
    }
    return "[" + kind + " ERROR]";
}

} // namespace

std::string FrameRecord::render() const {
    std::string location = file.empty() ? "<unknown>" : file;
    if (line > 0) {
        location += ":" + std::to_string(line);
        if (column > 0) {
            location += ":" + std::to_string(column);
        }
    }
    return "at " + name + " (" + location + ")";
}

std::string format_error_text(
    const std::string& kind,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    std::string text = kind_prefix(kind);
    if (!where.empty()) {
        text += " (in " + where + ")";
    }
    if (!message.empty()) {
        text += " " + message;
    }
    if (!details.empty()) {
        text += ":";
        for (const std::string& detail : details) {
            text += "\n      | " + detail;
        }
    }
    return text;
}

std::string ErrorObject::base_text() const {
    if (has_text_override) {
        return text_override;
    }
    return format_error_text(kind, where, message, details);
}

std::string ErrorObject::text() const {
    if (line > 0) {
        return "ln: " + std::to_string(line) + " | " + base_text();
    }
    return base_text();
}

std::string ErrorObject::readable() const {
    std::string text = kind_prefix(kind);
    if (!message.empty()) {
        text += " " + message;
    }
    return text;
}

[[noreturn]] void throw_error(ErrorObject* error) {
    throw UnwindSignal{error};
}

ErrorObject* make_error(
    Arena& arena,
    std::string kind,
    std::string where,
    std::string message,
    std::vector<std::string> details) {
    ErrorObject* error = arena.allocate_error();
    error->kind = kind.empty() ? "ERROR" : std::move(kind);
    error->where = std::move(where);
    error->message = std::move(message);
    error->details = std::move(details);
    return error;
}

ErrorObject* error_identifier_not_found(
    Arena& arena,
    const std::string& where,
    const std::string& name,
    const std::vector<std::string>& messages) {
    std::vector<std::string> details;
    details.reserve(messages.size() + 1);
    details.push_back(name);
    details.insert(details.end(), messages.begin(), messages.end());
    return make_error(
        arena, "IDENTIFIER", where, "doens't exists", std::move(details));
}

ErrorObject* error_type_match(
    Arena& arena,
    const std::string& where,
    const std::string& expected,
    const std::string& encountered) {
    return make_error(
        arena, "TYPE", where, "Types doesn't match",
        {"expected " + expected, "but " + encountered + " was encounter"});
}

ErrorObject* error_unsupported_operation(
    Arena& arena,
    const std::string& where,
    const std::string& left,
    const std::string& op,
    const std::string& right) {
    std::string detail = "Unsupported \"" + op + "\" operation ";
    if (right.empty()) {
        detail += "for " + left;
    } else {
        detail += "between " + left + " and " + right;
    }
    return make_error(
        arena, "OPERATION", where, "Invalid operation", {std::move(detail)});
}

ErrorObject* error_index_out_of_range(
    Arena& arena, std::int64_t index, std::int64_t size) {
    return make_error(
        arena, "INDEX", "", "Out of range",
        {"index " + std::to_string(index) + " out of range [0; "
             + std::to_string(size) + ")"});
}

ErrorObject* error_key(Arena& arena, const std::string& key) {
    return make_error(
        arena, "KEY", "", "Does not refers to a value: " + key);
}

ErrorObject* error_argument(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    return make_error(arena, "ARGUMENT", where, message, details);
}

ErrorObject* error_module(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    return make_error(arena, "MODULE", where, message, details);
}

ErrorObject* error_reference(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    return make_error(arena, "REFERENCE", where, message, details);
}

ErrorObject* error_const(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    return make_error(arena, "CONST", where, message, details);
}

ErrorObject* error_overload(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    return make_error(arena, "OVERLOAD", where, message, details);
}

ErrorObject* error_recursion(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    return make_error(arena, "RECURSION", where, message, details);
}

ErrorObject* error_development(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    return make_error(arena, "DEVELOPMENT", where, message, details);
}

ErrorObject* error_user(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details) {
    return make_error(arena, "USER", where, message, details);
}

} // namespace pwb
