// Opcode registry views and instruction decoding for the native runtime.
//
// The tables themselves come from opcodes_generated.hpp, which is generated
// from src/vm/opcodes.py. This header only declares the stable native shapes.

#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace pwb {

// Encoded operand widths. The order matches the Python registry names.
enum class Width : std::uint8_t {
    U8 = 0,
    U16 = 1,
    U32 = 2,
    I32 = 3,
    I64 = 4,
    F64 = 5,
};

// Operand meaning, used by the verifier and the disassembler.
enum class OperandKind : std::uint8_t {
    Value = 0,
    Slot = 1,
    Target = 2,
    Const = 3,
    Spec = 4,
    Call = 5,
    Pattern = 6,
    Module = 7,
    Type = 8,
    Trait = 9,
    Field = 10,
    Name = 11,
    Export = 12,
    Host = 13,
    Event = 14,
    Flags = 15,
};

// Width of one encoded operand in bytes.
std::size_t width_size(Width width);

struct OperandSpec {
    const char* name;
    Width width;
    OperandKind kind;
};

struct OpcodeSpec {
    const char* name;
    std::uint8_t opcode;
    const OperandSpec* operands;
    std::uint8_t operand_count;
    std::int16_t stack_in;
    std::int16_t stack_out;
    const char* verifier;

    // Encoded size in bytes, including the opcode byte.
    std::uint32_t size() const;
};

// Maximum operand count in the registry. The current maximum is three.
inline constexpr std::size_t kMaxOperands = 4;

struct DecodedOperand {
    Width width = Width::U8;
    OperandKind kind = OperandKind::Value;
    std::int64_t integer = 0;
    double number = 0.0;
    bool is_float = false;
};

struct DecodedInstruction {
    std::uint8_t opcode = 0;
    const OpcodeSpec* spec = nullptr;
    std::uint32_t offset = 0;
    std::uint32_t next_offset = 0;
    std::uint8_t operand_count = 0;
    std::array<DecodedOperand, kMaxOperands> operands{};

    // Return the operand with `name`, or nullptr when it is absent.
    const DecodedOperand* find(const char* name) const;
};

// Return the spec for `opcode`. Throws DecodeError for an unknown opcode.
const OpcodeSpec& opcode_spec(std::uint8_t opcode);

// Number of registered opcodes.
std::size_t opcode_count() noexcept;

// Decode the instruction at `offset`. Throws DecodeError on an unknown opcode
// or a truncated operand.
DecodedInstruction decode_instruction(
    const std::vector<std::uint8_t>& bytecode, std::uint32_t offset);

} // namespace pwb
