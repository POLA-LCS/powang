"""Tooling tests for the bytecode VM.

Covers the engine flag, the ``powang vm`` command line surface, trace mode,
golden disassembly and the opcode handler coverage guard.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from src.state import fresh_state, set_state
from src.vm.builder import Builder
from src.vm.compiler import compile_source
from src.vm.disasm import disassemble_code, disassemble_image
from src.vm.image import ProgramImage, SourceSpan
from src.vm.interpreter import VM, VMRunOptions
from src.vm.opcodes import OPCODES
from src.vm.trace import TextTraceSink
from src.vm.verifier import verify_code, verify_image

from tests.helpers import ROOT, run_command, run_source


class EngineFlagTests(unittest.TestCase):
    def test_engine_flag_runs_vm(self) -> None:
        source = 'print("vm"); print("\\n");\n'
        result = run_source(source, engine="vm")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "vm\n")

    def test_environment_engine_runs_vm(self) -> None:
        source = 'print("env"); print("\\n");\n'
        result = run_source(source, env={"POWANG_ENGINE": "vm"})
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "env\n")

    def test_invalid_engine_is_a_usage_error(self) -> None:
        result = run_source('print("x");\n', engine="nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid engine", result.combined)

    def test_tree_and_vm_outputs_match(self) -> None:
        source = (
            "total := 0;\n"
            "for index >> 0 >> 5 { total += index; }\n"
            'print(total); print("\\n");\n'
        )
        tree = run_source(source, engine="tree")
        vm = run_source(source, engine="vm")
        self.assertEqual(tree.stdout, "10\n")
        self.assertEqual(tree.stdout, vm.stdout)
        self.assertEqual(tree.stderr, vm.stderr)
        self.assertEqual(tree.returncode, vm.returncode)


class CommandLineTests(unittest.TestCase):
    def test_vm_help(self) -> None:
        result = run_command(["vm", "--help"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("powang vm usage", result.stdout)

    def test_vm_disasm(self) -> None:
        result = run_command(["vm", "disasm", "examples/arithmetics.po"])
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn("code arithmetics", result.stdout)
        self.assertIn("call_sites:", result.stdout)

    def test_vm_run(self) -> None:
        result = run_command(["vm", "run", "examples/arithmetics.po"])
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertTrue(result.stdout.startswith("10\n4\n21\n"))

    def test_vm_diff(self) -> None:
        result = run_command(["vm", "diff", "examples/arithmetics.po"])
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn("differential result: equal", result.stdout)

    def test_vm_trace(self) -> None:
        result = run_command(["vm", "run", "--trace", "examples/arithmetics.po"])
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn("instruction", result.stdout)

    def test_vm_disasm_json(self) -> None:
        import json

        result = run_command(
            ["vm", "disasm", "--json", "examples/arithmetics.po"]
        )
        self.assertEqual(result.returncode, 0, result.combined)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["format"], 1)
        self.assertGreater(len(payload["codes"]), 0)

    def test_vm_cache_is_optional_and_reused(self) -> None:
        first = run_command(
            ["vm", "run", "--vm-cache", "examples/arithmetics.po"]
        )
        second = run_command(
            ["vm", "run", "--vm-cache", "examples/arithmetics.po"]
        )
        self.assertEqual(first.returncode, 0, first.combined)
        self.assertEqual(second.returncode, 0, second.combined)
        self.assertEqual(first.stdout, second.stdout)
        cache = ROOT / ".powang" / "cache" / "bytecode"
        self.assertTrue(cache.is_dir())

    def test_seeded_fuzzer(self) -> None:
        from src.vm.fuzz import run_fuzz

        report = run_fuzz(1, 20, fail_fast=True)
        self.assertTrue(report.ok, report.report())


class DisassemblyTests(unittest.TestCase):
    def test_golden_core_sequence(self) -> None:
        source = "value := 1 + 2;\nprint(value);\n"
        state = fresh_state()
        set_state(state)
        image = compile_source(
            source, path="golden.po", module_name="golden",
            check=False, state=state,
        )
        verify_image(image)
        text = disassemble_image(image)
        self.assertIn("LOAD_INT 1", text)
        self.assertIn("LOAD_INT 2", text)
        self.assertIn("ADD", text)
        self.assertIn("RETURN", text)
        self.assertIn("constant", text)
        self.assertIn("call_site", text)

    def test_every_opcode_is_mentioned_by_the_interpreter(self) -> None:
        source = (ROOT / "src" / "vm" / "interpreter.py").read_text(
            encoding="utf-8"
        )
        missing = [opcode.name for opcode in OPCODES if f'"{opcode.name}"' not in source]
        self.assertEqual(missing, [])


class TraceTests(unittest.TestCase):
    def test_trace_sink_records_instructions_and_returns(self) -> None:
        from src.vm.modules import evaluate_program_image

        state = fresh_state()
        set_state(state)
        image = compile_source(
            "fun add(a: int, b: int): int >> a + b;\nprint(add(1, 2));\n",
            path="trace.po", module_name="trace", check=False, state=state,
        )
        verify_image(image)
        stream = io.StringIO()
        sink = TextTraceSink(stream)
        evaluate_program_image(image, state, VMRunOptions(trace=True, trace_sink=sink))
        output = stream.getvalue()
        self.assertIn("instruction", output)
        self.assertIn("LOAD_LOCAL", output)
        self.assertIn("RETURN", output)


class ReplTests(unittest.TestCase):
    def test_vm_repl_persists_declarations(self) -> None:
        payload = (
            "fun f(): int >> 7;\n"
            "println(f());\n"
            "type Point[+] { | x: int; }\n"
            "println(Point.[3].x);\n"
        )
        tree = run_command([], input_text=payload)
        vm = run_command(["--engine=vm"], input_text=payload)
        self.assertEqual(tree.returncode, 0, tree.combined)
        self.assertEqual(vm.returncode, 0, vm.combined)
        self.assertEqual(tree.stdout, vm.stdout)
        self.assertIn("7\n", vm.stdout)
        self.assertIn("3\n", vm.stdout)


class ImageTests(unittest.TestCase):
    def test_compiled_image_round_trips(self) -> None:
        state = fresh_state()
        set_state(state)
        image = compile_source(
            "type Point[+] { | x: int; | y: int; }\n"
            "point := Point.[1, 2];\n"
            "print(point.x);\n",
            path="image.po", module_name="image", check=False, state=state,
        )
        payload = image.to_bytes()
        restored = ProgramImage.from_bytes(payload)
        self.assertEqual(len(restored.codes), len(image.codes))
        self.assertEqual(len(restored.types), len(image.types))
        self.assertEqual(len(restored.call_sites), len(image.call_sites))
        verify_image(restored)


if __name__ == "__main__":
    unittest.main()
