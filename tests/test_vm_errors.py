"""Error text and position parity between the two engines.

Each case asserts that the tree walker and the VM produce identical standard
output, standard error and exit code, and that the expected diagnostic family
appears in the VM output. A case may pass extra command line arguments.
"""

from __future__ import annotations

import unittest

from tests.helpers import run_source


CASES = {
    "undefined_identifier": (
        "print(missing);\n",
        "IDENTIFIER ERROR",
        (),
    ),
    "type_mismatch": (
        "value: int = \"text\";\n",
        "TYPE ERROR",
        (),
    ),
    "index_out_of_range": (
        "values := [1, 2];\nprint(values[5]);\n",
        "INDEX ERROR",
        (),
    ),
    "invalid_cast": (
        "print(\"abc\" as int);\n",
        "RUNTIME ERROR",
        (),
    ),
    "unsupported_operation": (
        "print(1 % \"x\");\n",
        "OPERATION ERROR",
        (),
    ),
    "argument_count": (
        "fun one(value: int): int >> value;\none(1, 2);\n",
        "TYPE ERROR",
        (),
    ),
    "missing_key": (
        "values := [\"a\" >> 1];\nprint(values[\"b\"]);\n",
        "KEY ERROR",
        (),
    ),
    "const_lock": (
        "value: int! = 1;\nvalue = 2;\n",
        "CONST ERROR",
        (),
    ),
    "user_error": (
        "error(\"boom\", \"detail\");\n",
        "USER ERROR",
        (),
    ),
    "module_mutation": (
        "use strings;\nstrings.trim = 1;\n",
        "MODULE ERROR",
        ("--no-check",),
    ),
    "recursion": (
        "fun down(n: int): int { if n <= 0 { return 0; } return down(n - 1); }\n"
        "print(down(890));\n",
        "RECURSION ERROR",
        (),
    ),
    "function_redeclare": (
        "fun pick(value: int): int >> 1;\nfun pick(value: int): int >> 2;\n",
        "REDEFINE ERROR",
        (),
    ),
    "safe_access_map": (
        "values := [\"a\" >> 1];\nprint(values?.a);\n",
        "SYNTAX ERROR",
        (),
    ),
}


class ErrorParityTests(unittest.TestCase):
    def test_error_cases_match(self) -> None:
        failures: list[str] = []
        for name, (source, marker, args) in CASES.items():
            tree = run_source(source, engine="tree", args=args)
            vm = run_source(source, engine="vm", args=args)
            if tree.returncode != vm.returncode:
                failures.append(
                    f"{name}: exit {tree.returncode} != {vm.returncode}"
                )
                continue
            if tree.stdout != vm.stdout or tree.stderr != vm.stderr:
                failures.append(
                    f"{name}: output differs\n tree={tree.combined}\n vm={vm.combined}"
                )
                continue
            if tree.returncode == 0:
                failures.append(f"{name}: expected a failure but both succeeded")
                continue
            if marker not in vm.combined:
                failures.append(
                    f"{name}: expected {marker}\n vm={vm.combined}"
                )
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
