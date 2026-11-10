"""Differential tests between the tree walker and the bytecode VM.

Each case runs in two subprocesses with an explicit engine flag. The harness
compares standard output, standard error and the exit code.
"""

from __future__ import annotations

import unittest

from src.vm.differential import compare_file, compare_source

from tests.helpers import ROOT


EXAMPLE_FILES = (
    "examples/arithmetics.po",
    "examples/collections.po",
    "examples/control-flow.po",
    "examples/functions.po",
    "examples/lambdas.po",
    "examples/match-patterns.po",
    "examples/enums.po",
    "examples/traits.po",
    "examples/operator-overloading.po",
    "examples/references.po",
    "examples/errors.po",
    "examples/async.po",
    "examples/tasks.po",
    "examples/concurrency.po",
    "examples/cross-module.po",
    "examples/modules.po",
    "examples/native-methods.po",
    "examples/slicing.po",
    "examples/type-construction.po",
    "examples/variadics.po",
)


INLINE_CASES = {
    "arithmetic": (
        "print(1 + 2 * 3); print(\"\\n\");\n"
        "print(2 +: 0.5); print(\"\\n\");\n"
        "print(10 / 3); print(\"\\n\");\n"
    ),
    "control": (
        "total := 0;\n"
        "for i >> 0 >> 5 {\n"
        "    if i == 2 { continue; }\n"
        "    if i == 4 { break; }\n"
        "    total += i;\n"
        "}\n"
        "print(total); print(\"\\n\");\n"
    ),
    "functions": (
        "fun greet(name: str = \"world\"): str >> $\"hi {name}\";\n"
        "print(greet()); print(\" \"); print(greet(\"Ada\")); print(\"\\n\");\n"
    ),
    "closures": (
        "base := 10;\n"
        "add := fun(value: int): int >> value + base;\n"
        "base = 20;\n"
        "print(add(1)); print(\"\\n\");\n"
    ),
    "containers": (
        "values := [1, 2, 3];\n"
        "values[0] = 9;\n"
        "print(values); print(\"\\n\");\n"
        "print(values[0 >> 2]); print(\"\\n\");\n"
    ),
    "maps": (
        "settings := [\"a\" >> 1];\n"
        "settings[\"b\"] = 2;\n"
        "print(settings); print(\"\\n\");\n"
    ),
    "types": (
        "type Point[+] {\n"
        "    | x: int;\n"
        "    | y: int;\n"
        "    fun this.sum(other: Point): int >> this.x + other.x;\n"
        "}\n"
        "first := Point.[1, 2];\n"
        "second := Point.[3, 4];\n"
        "print(first.sum(second)); print(\"\\n\");\n"
    ),
    "traits": (
        "trait Named {\n"
        "    | target: str;\n"
        "    fun describe(): str >> this.target;\n"
        "}\n"
        "type Person[+] { | target: str; }\n"
        "value: Named = Person.[\"Ada\"];\n"
        "print(value.describe()); print(\"\\n\");\n"
    ),
    "errors": (
        "try { error(\"boom\"); } catch problem {\n"
        "    print(problem.kind); print(\" \"); print(problem.message);\n"
        "} finally { print(\" done\"); }\n"
        "print(\"\\n\");\n"
    ),
    "references": (
        "fun bump(value: &int) { value += 1; }\n"
        "counter := 1;\n"
        "bump(&counter);\n"
        "print(counter); print(\"\\n\");\n"
    ),
    "async": (
        "async fun double(value: int): int >> value * 2;\n"
        "print(await double(21)); print(\"\\n\");\n"
    ),
    "spawn": (
        "async fun work(value: int): int >> value + 1;\n"
        "task := spawn work(4);\n"
        "print(await task); print(\"\\n\");\n"
    ),
    "match": (
        "value := [1, 2, 3];\n"
        "match value {\n"
        "    case [first, ...rest] >> print(first);\n"
        "}\n"
        "print(\"\\n\");\n"
    ),
}


class ExampleDifferentialTests(unittest.TestCase):
    def test_examples_match(self) -> None:
        failures: list[str] = []
        for relative in EXAMPLE_FILES:
            path = ROOT / relative
            if not path.exists():
                continue
            result = compare_file(path)
            if not result.equal:
                failures.append(result.report())
        self.assertEqual(failures, [], "\n".join(failures))


class InlineDifferentialTests(unittest.TestCase):
    def test_inline_corpus_matches(self) -> None:
        failures: list[str] = []
        for name, source in INLINE_CASES.items():
            result = compare_source(source, name=f"{name}.po")
            if not result.equal:
                failures.append(f"{name}: " + result.report())
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
