#include "pwb/host.hpp"

#include <cstdio>
#include <stdexcept>

namespace pwb {

Value Host::call_extern(
    std::string_view name,
    const Value* arguments,
    std::size_t argument_count) {
    (void)name;
    (void)arguments;
    (void)argument_count;
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

} // namespace pwb
