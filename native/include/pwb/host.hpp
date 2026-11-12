// Host output boundary for the native runtime.

#pragma once

#include <string>

namespace pwb {

class Host {
public:
    virtual ~Host() = default;
    virtual void write(const std::string& text) = 0;
    // Diagnostics from the embedded runtime boundary, normally standard
    // error. The host layer owns the actual stream.
    virtual void write_error(const std::string& text) = 0;
};

// Host that writes output to standard output and diagnostics to standard
// error, without adding separators.
class StdoutHost : public Host {
public:
    void write(const std::string& text) override;
    void write_error(const std::string& text) override;
};

} // namespace pwb
