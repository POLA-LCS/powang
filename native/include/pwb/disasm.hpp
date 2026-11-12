// Stable text disassembler for one code object.

#pragma once

#include <string>

#include "pwb/image.hpp"

namespace pwb {

// Render `code` exactly like src/vm/disasm.py. When `image` is not null,
// call, pattern, module, type, trait, field, name, export and host operands
// are resolved against the image tables.
std::string disassemble_code(const CodeObject& code, const Image* image = nullptr);

} // namespace pwb
