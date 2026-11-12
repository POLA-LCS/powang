// Embedded image execution entry point for the native runtime.

#pragma once

#include <cstddef>
#include <cstdint>

#include "pwb/host.hpp"

namespace pwb {

// Parse, verify and run the entry code of an embedded PWB1 image. Errors are
// written through Host::write_error as `native image error`,
// `native verifier error` or `native runtime error` lines. Returns 0 on
// success and 1 on failure.
int run_embedded_image(
    const std::uint8_t* data, std::size_t size, Host& host);

} // namespace pwb
