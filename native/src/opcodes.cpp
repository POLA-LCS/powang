#include "pwb/opcodes.hpp"

#include <cstdio>
#include <cstring>
#include <string>

#include "pwb/error.hpp"
#include "pwb/opcodes_generated.hpp"

namespace pwb {

std::size_t width_size(Width width) {
    switch (width) {
        case Width::U8: return 1;
        case Width::U16: return 2;
        case Width::U32: return 4;
        case Width::I32: return 4;
        case Width::I64: return 8;
        case Width::F64: return 8;
    }
    return 0;
}

std::uint32_t OpcodeSpec::size() const {
    std::uint32_t total = 1;
    for (std::uint8_t index = 0; index < operand_count; ++index) {
        total += static_cast<std::uint32_t>(width_size(operands[index].width));
    }
    return total;
}

const DecodedOperand* DecodedInstruction::find(const char* name) const {
    if (spec == nullptr) {
        return nullptr;
    }
    for (std::uint8_t index = 0; index < operand_count; ++index) {
        if (std::strcmp(spec->operands[index].name, name) == 0) {
            return &operands[index];
        }
    }
    return nullptr;
}

const OpcodeSpec& opcode_spec(std::uint8_t opcode) {
    if (opcode >= generated::kOpcodeCount) {
        char message[64];
        std::snprintf(message, sizeof(message), "unknown opcode 0x%02x", opcode);
        throw DecodeError(message);
    }
    return generated::kOpcodes[opcode];
}

std::size_t opcode_count() noexcept {
    return generated::kOpcodeCount;
}

DecodedInstruction decode_instruction(
    const std::vector<std::uint8_t>& bytecode, std::uint32_t offset) {
    if (offset >= bytecode.size()) {
        throw DecodeError(
            "truncated instruction: no opcode at offset " + std::to_string(offset));
    }
    const std::uint8_t opcode = bytecode[offset];
    const OpcodeSpec& spec = opcode_spec(opcode);
    DecodedInstruction instruction;
    instruction.opcode = opcode;
    instruction.spec = &spec;
    instruction.offset = offset;
    instruction.operand_count = spec.operand_count;
    std::size_t position = static_cast<std::size_t>(offset) + 1;
    for (std::uint8_t index = 0; index < spec.operand_count; ++index) {
        const OperandSpec& operand = spec.operands[index];
        const std::size_t width = width_size(operand.width);
        if (width > bytecode.size() - position) {
            throw DecodeError(
                "truncated instruction " + std::string(spec.name) + " at offset "
                + std::to_string(offset) + ": missing " + operand.name);
        }
        std::uint64_t raw = 0;
        for (std::size_t byte = 0; byte < width; ++byte) {
            raw |= static_cast<std::uint64_t>(bytecode[position + byte])
                << (8u * byte);
        }
        position += width;
        DecodedOperand& decoded = instruction.operands[index];
        decoded.width = operand.width;
        decoded.kind = operand.kind;
        switch (operand.width) {
            case Width::U8:
            case Width::U16:
            case Width::U32:
                decoded.integer = static_cast<std::int64_t>(raw);
                break;
            case Width::I32: {
                const std::uint32_t bits = static_cast<std::uint32_t>(raw);
                std::int32_t value = 0;
                std::memcpy(&value, &bits, sizeof(value));
                decoded.integer = value;
                break;
            }
            case Width::I64: {
                std::int64_t value = 0;
                std::memcpy(&value, &raw, sizeof(value));
                decoded.integer = value;
                break;
            }
            case Width::F64: {
                double value = 0.0;
                std::memcpy(&value, &raw, sizeof(value));
                decoded.number = value;
                decoded.is_float = true;
                break;
            }
        }
    }
    instruction.next_offset = static_cast<std::uint32_t>(position);
    return instruction;
}

} // namespace pwb
