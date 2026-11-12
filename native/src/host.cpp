#include "pwb/host.hpp"

#include <cstdio>

namespace pwb {

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
