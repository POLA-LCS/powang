// SHA-256 helper for the PWBB bundle digest.

#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace pwb {

std::array<std::uint8_t, 32> sha256(
    const std::uint8_t* data, std::size_t size);

} // namespace pwb
