"""Seeded grammar-based fuzzer for differential VM testing.

The generator produces syntactically valid Powang programs from a small grammar
of literals, expressions, statements and declarations. The checker may reject a
generated program. That is still a valid differential case because both engines
must report the same error text and exit code.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .differential import DiffResult, compare_source


_BINARY_OPERATORS = ("+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">=")
_UNARY_OPERATORS = ("!", "-", "[-]")


def _literal(rng: random.Random) -> str:
    choice = rng.randrange(6)
    if choice == 0:
        return str(rng.randint(-5, 20))
    if choice == 1:
        return f"{rng.uniform(-5.0, 20.0):.2f}"
    if choice == 2:
        return '"' + rng.choice(("a", "bc", "hello", "x y")) + '"'
    if choice == 3:
        return "'" + rng.choice(("a", "b", "z")) + "'"
    if choice == 4:
        return rng.choice(("true", "false"))
    return "nova"


def _expression(rng: random.Random, depth: int = 0) -> str:
    if depth >= 3 or rng.random() < 0.35:
        return _literal(rng)
    choice = rng.randrange(5)
    if choice == 0:
        return f"({_expression(rng, depth + 1)} {rng.choice(_BINARY_OPERATORS)} {_expression(rng, depth + 1)})"
    if choice == 1:
        return f"({rng.choice(_UNARY_OPERATORS)}{_expression(rng, depth + 1)})"
    if choice == 2:
        return f"size({_expression(rng, depth + 1)})"
    if choice == 3:
        return f"typeof({_expression(rng, depth + 1)})"
    return f"$\"value={_expression(rng, depth + 1)}\""


def _statement(rng: random.Random, depth: int = 0) -> str:
    choice = rng.randrange(8)
    if choice == 0:
        return f"print({_expression(rng)});"
    if choice == 1:
        return f"value_{depth} := {_expression(rng)};"
    if choice == 2 and depth < 2:
        return (
            f"if {_expression(rng)} {{\n    {_statement(rng, depth + 1)}\n}} "
            f"else {{\n    {_statement(rng, depth + 1)}\n}}"
        )
    if choice == 3 and depth < 2:
        count = rng.randint(0, 4)
        return (
            f"for index >> 0 >> {count} {{\n"
            f"    {_statement(rng, depth + 1)}\n"
            f"}}"
        )
    if choice == 4 and depth < 2:
        return (
            "try {\n"
            f"    {_statement(rng, depth + 1)}\n"
            "} catch problem {\n"
            '    print(problem.kind);\n'
            "}"
        )
    if choice == 5:
        return f"values_{depth} := [{_expression(rng)}, {_expression(rng)}];"
    if choice == 6 and depth < 2:
        return (
            "match " + _expression(rng) + " {\n"
            "    case 0 >> print(0);\n"
            "    case _ >> print(1);\n"
            "}"
        )
    return f"print({_expression(rng)});"


def generate_program(rng: random.Random) -> str:
    """Generate one syntactically valid program."""
    lines: list[str] = []
    function_count = rng.randint(0, 2)
    for index in range(function_count):
        lines.append(
            f"fun generated_{index}(value: int): int {{\n"
            f"    return value * {rng.randint(0, 5)} + {rng.randint(0, 9)};\n"
            f"}}"
        )
    statement_count = rng.randint(2, 6)
    for index in range(statement_count):
        lines.append(_statement(rng, index))
    if function_count and rng.random() < 0.5:
        lines.append(f"print(generated_0({rng.randint(0, 9)}));")
    return "\n".join(lines) + "\n"


@dataclass
class FuzzFailure:
    seed: int
    index: int
    source: str
    diff: Optional[DiffResult] = None
    path: Optional[Path] = None


@dataclass
class FuzzReport:
    seed: int
    generated: int
    skipped: int = 0
    failures: list[FuzzFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def report(self) -> str:
        lines = [
            f"fuzz seed={self.seed} generated={self.generated} "
            f"skipped={self.skipped} failures={len(self.failures)}"
        ]
        for failure in self.failures:
            lines.append(f"  case {failure.index} seed {failure.seed}")
            if failure.diff is not None:
                lines.append("  " + failure.diff.report().replace("\n", "\n  "))
            if failure.path is not None:
                lines.append(f"  saved: {failure.path}")
        return "\n".join(lines)


def run_fuzz(seed: int, count: int, *, fail_directory: Path | str | None = None,
             fail_fast: bool = True) -> FuzzReport:
    rng = random.Random(seed)
    report = FuzzReport(seed=seed, generated=0)
    output_directory = Path(fail_directory) if fail_directory is not None else None
    if output_directory is not None:
        output_directory.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        source = generate_program(rng)
        report.generated += 1
        result = compare_source(source, name=f"fuzz_{seed}_{index}.po")
        if result.equal:
            continue
        saved = None
        if output_directory is not None:
            saved = output_directory / f"fuzz_{seed}_{index}.po"
            saved.write_text(source, encoding="utf-8", newline="\n")
        report.failures.append(FuzzFailure(
            seed=seed, index=index, source=source, diff=result, path=saved,
        ))
        if fail_fast:
            break
    return report
