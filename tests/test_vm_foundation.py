"""Foundation tests for the bytecode VM.

Covers the opcode registry, instruction encoding, label patching, the program
image codec and the verifier reject cases.
"""

from __future__ import annotations

import struct
import unittest

from src.vm.builder import Builder
from src.vm.image import (
    CallSite,
    CodeObject,
    Constant,
    FunctionInfo,
    ModuleInfo,
    ProgramImage,
    SourceSpan,
    TypeInfo,
)
from src.vm.opcodes import BY_NAME, BY_OPCODE, OPCODES, decode_instruction, spec
from src.vm.verifier import VerificationError, verify_code, verify_image


def _span(builder: Builder) -> int:
    return builder.add_span(SourceSpan(0, 1, 0, 1, 1))


def _simple_code() -> CodeObject:
    builder = Builder("simple")
    span = _span(builder)
    first = builder.declare_local("a")
    second = builder.declare_local("b")
    builder.set_parameter_names(["a", "b"])
    builder.emit("LOAD_LOCAL", first, span=span)
    builder.emit("LOAD_LOCAL", second, span=span)
    builder.emit("ADD", span=span)
    builder.emit("RETURN", span=span)
    return builder.finish()


def _image(code: CodeObject) -> ProgramImage:
    return ProgramImage(
        entry_module=0,
        entry_code=0,
        modules=[ModuleInfo(name="main", path="main.po", code_index=0)],
        types=[],
        traits=[],
        functions=[FunctionInfo(name="main", code_index=0)],
        constants=[],
        call_sites=[],
        patterns=[],
        type_specs=[],
        sources=["main.po"],
        global_names=[],
        strings=[],
        codes=[code],
    )


class OpcodeRegistryTests(unittest.TestCase):
    def test_registry_is_consistent(self) -> None:
        self.assertGreater(len(OPCODES), 120)
        self.assertEqual(len(BY_NAME), len(OPCODES))
        self.assertEqual(len(BY_OPCODE), len(OPCODES))
        self.assertEqual([item.opcode for item in OPCODES], list(range(len(OPCODES))))

    def test_encoding_round_trip(self) -> None:
        for opcode in OPCODES:
            operands = []
            for operand in opcode.operands:
                if operand.width == "f64":
                    operands.append(1.5)
                elif operand.width in {"i64"}:
                    operands.append(-2)
                elif operand.width in {"i32"}:
                    operands.append(-1)
                else:
                    operands.append(1)
            from src.vm.opcodes import encode_operands
            payload = bytes([opcode.opcode]) + encode_operands(opcode, operands)
            decoded, operands_out, next_offset = decode_instruction(payload, 0)
            self.assertEqual(decoded.name, opcode.name)
            self.assertEqual(next_offset, len(payload))
            self.assertEqual(set(operands_out), {operand.name for operand in opcode.operands})


class BuilderTests(unittest.TestCase):
    def test_finish_and_span_table(self) -> None:
        code = _simple_code()
        self.assertEqual(code.parameter_count, 2)
        self.assertEqual(code.local_count, 2)
        self.assertEqual(len(code.span_table), 4)
        self.assertEqual(code.bytecode[0], BY_NAME["LOAD_LOCAL"].opcode)

    def test_label_patching(self) -> None:
        builder = Builder("jump")
        span = _span(builder)
        target = builder.new_label()
        builder.emit("JUMP", target, span=span)
        builder.emit("LOAD_NOVA", span=span)
        builder.place(target)
        builder.emit("LOAD_NOVA", span=span)
        builder.emit("RETURN", span=span)
        code = builder.finish()
        _, operands, _ = decode_instruction(code.bytecode, 0)
        jump_offset = operands["target"]
        self.assertEqual(jump_offset, 6)

    def test_unplaced_label_is_rejected(self) -> None:
        builder = Builder("bad")
        span = _span(builder)
        target = builder.new_label()
        builder.emit("JUMP", target, span=span)
        builder.emit("LOAD_NOVA", span=span)
        builder.emit("RETURN", span=span)
        with self.assertRaises(ValueError):
            builder.finish()


class ImageCodecTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        code = _simple_code()
        image = _image(code)
        image.call_sites.append(CallSite(dispatch="call", name="print", positional_count=1))
        image.types.append(TypeInfo(name="Point", kind="object"))
        payload = image.to_bytes()
        self.assertTrue(payload.startswith(b"PWB1"))
        restored = ProgramImage.from_bytes(payload)
        self.assertEqual(restored.entry_module, image.entry_module)
        self.assertEqual(restored.entry_code, image.entry_code)
        self.assertEqual(len(restored.codes), 1)
        self.assertEqual(restored.codes[0].bytecode, code.bytecode)
        self.assertEqual(restored.codes[0].local_names, code.local_names)
        self.assertEqual(restored.codes[0].spans, code.spans)
        self.assertEqual(restored.call_sites[0].name, "print")
        self.assertEqual(restored.types[0].name, "Point")

    def test_corruption_is_rejected(self) -> None:
        image = _image(_simple_code())
        payload = bytearray(image.to_bytes())
        payload[-1] ^= 0xFF
        with self.assertRaises(ValueError):
            ProgramImage.from_bytes(bytes(payload))


class VerifierTests(unittest.TestCase):
    def test_accepts_valid_code(self) -> None:
        code = _simple_code()
        verify_code(code, _image(code))

    def test_rejects_stack_underflow(self) -> None:
        builder = Builder("underflow")
        span = _span(builder)
        builder.emit("ADD", span=span)
        builder.emit("RETURN", span=span)
        code = builder.finish()
        with self.assertRaises(VerificationError):
            verify_code(code)

    def test_rejects_bad_constant(self) -> None:
        builder = Builder("constant")
        span = _span(builder)
        builder.emit("LOAD_STR", 5, span=span)
        builder.emit("RETURN", span=span)
        code = builder.finish()
        with self.assertRaises(VerificationError):
            verify_code(code)

    def test_rejects_bad_slot(self) -> None:
        builder = Builder("slot")
        span = _span(builder)
        builder.emit("LOAD_LOCAL", 3, span=span)
        builder.emit("RETURN", span=span)
        code = builder.finish()
        with self.assertRaises(VerificationError):
            verify_code(code)

    def test_rejects_jump_into_instruction(self) -> None:
        builder = Builder("jump")
        span = _span(builder)
        builder.emit("LOAD_INT", 1, span=span)
        builder.emit("JUMP", 1, span=span)
        builder.emit("LOAD_NOVA", span=span)
        builder.emit("RETURN", span=span)
        code = builder.finish()
        with self.assertRaises(VerificationError):
            verify_code(code)

    def test_rejects_missing_return(self) -> None:
        builder = Builder("fallthrough")
        span = _span(builder)
        builder.emit("LOAD_NOVA", span=span)
        code = builder.finish()
        with self.assertRaises(VerificationError):
            verify_code(code)

    def test_rejects_merge_mismatch(self) -> None:
        builder = Builder("merge")
        span = _span(builder)
        done = builder.new_label()
        builder.emit("LOAD_TRUE", span=span)
        builder.emit("JUMP_IF_FALSE", done, span=span)
        builder.emit("LOAD_NOVA", span=span)
        builder.place(done)
        builder.emit("RETURN", span=span)
        code = builder.finish()
        with self.assertRaises(VerificationError):
            verify_code(code)


if __name__ == "__main__":
    unittest.main()
