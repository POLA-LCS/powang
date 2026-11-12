// Native image verifier, N0 subset.

#pragma once

#include "pwb/image.hpp"

namespace pwb {

// Verify the container level facts, every instruction stream, operand bounds
// and the conservative stack height dataflow. Throws VerificationError on the
// first violation.
void verify_image(const Image& image);

} // namespace pwb
