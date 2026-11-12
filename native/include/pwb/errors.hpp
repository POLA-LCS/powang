// Language error values and the private unwind signal.
//
// A language error is an arena allocated ErrorObject carried by Tag::Error.
// The C++ exception is only a control transfer between recursive execute
// calls. It is never observable by Powang code.

#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace pwb {

struct Arena;
struct ErrorObject;

struct FrameRecord {
    std::string name;
    std::string file;
    std::int32_t line = 0;
    std::int32_t column = 0;

    std::string render() const;
};

struct ErrorObject {
    std::string kind = "ERROR";
    std::string message;
    std::vector<std::string> details;
    std::string where;
    std::int32_t line = 0;
    std::int32_t column = 0;
    std::vector<FrameRecord> frames;
    ErrorObject* cause = nullptr;
    std::string text_override;
    bool has_text_override = false;
    bool is_module_error = false;

    std::string base_text() const;
    std::string text() const;
    std::string readable() const;
};

struct UnwindSignal {
    ErrorObject* error = nullptr;
};

[[noreturn]] void throw_error(ErrorObject* error);

std::string format_error_text(
    const std::string& kind,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details);

ErrorObject* make_error(
    Arena& arena,
    std::string kind,
    std::string where,
    std::string message,
    std::vector<std::string> details = {});

ErrorObject* error_identifier_not_found(
    Arena& arena,
    const std::string& where,
    const std::string& name,
    const std::vector<std::string>& messages = {});
ErrorObject* error_type_match(
    Arena& arena,
    const std::string& where,
    const std::string& expected,
    const std::string& encountered);
ErrorObject* error_unsupported_operation(
    Arena& arena,
    const std::string& where,
    const std::string& left,
    const std::string& op,
    const std::string& right = "");
ErrorObject* error_index_out_of_range(
    Arena& arena, std::int64_t index, std::int64_t size);
ErrorObject* error_key(Arena& arena, const std::string& key);
ErrorObject* error_argument(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details = {});
ErrorObject* error_module(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details = {});
ErrorObject* error_reference(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details = {});
ErrorObject* error_const(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details = {});
ErrorObject* error_overload(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details = {});
ErrorObject* error_recursion(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details = {});
ErrorObject* error_development(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details = {});
ErrorObject* error_user(
    Arena& arena,
    const std::string& where,
    const std::string& message,
    const std::vector<std::string>& details = {});

} // namespace pwb
