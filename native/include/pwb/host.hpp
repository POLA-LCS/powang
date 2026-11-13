// Host output boundary for the native runtime.

#pragma once

#include <cstddef>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "pwb/value.hpp"

namespace pwb {

class Arena;

// A host extern rejected its arguments or raised a Python-style exception.
// The runtime turns this into an EXTERN language error instead of a
// DEVELOPMENT error for an unavailable host ABI.
class HostCallError : public std::runtime_error {
public:
    HostCallError(std::string python_type, std::string message)
        : std::runtime_error(std::move(message)),
          python_type(std::move(python_type)) {}

    std::string python_type;
};

class Host {
public:
    virtual ~Host() = default;
    virtual void write(const std::string& text) = 0;
    // Diagnostics from the embedded runtime boundary, normally standard
    // error. The host layer owns the actual stream.
    virtual void write_error(const std::string& text) = 0;

    // Optional scalar extern boundary. A host that supports an extern
    // overrides this method. The default reports that the ABI is unavailable.
    virtual Value call_extern(
        std::string_view name,
        const Value* arguments,
        std::size_t argument_count,
        Arena& arena);
};

// Host that writes output to standard output and diagnostics to standard
// error, without adding separators.
class StdoutHost : public Host {
public:
    StdoutHost();
    StdoutHost(int argc, char** argv);
    void write(const std::string& text) override;
    void write_error(const std::string& text) override;
    Value call_extern(
        std::string_view name,
        const Value* arguments,
        std::size_t argument_count,
        Arena& arena) override;

private:
    void emit_log(
        const std::string& level,
        const std::string& message,
        const std::string& fields);

    std::string log_level_ = "info";
    std::vector<std::string> script_arguments_;
};

} // namespace pwb
