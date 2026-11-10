"""Bytecode VM runtime and differential tests.

Every case runs on both engines and requires identical standard output,
standard error and exit code. Expected output is asserted as well so a case
cannot pass by failing the same way on both engines.
"""

from __future__ import annotations

import unittest

from tests.helpers import assert_no_traceback, run_source


def run_both(case: unittest.TestCase, source: str) -> tuple[str, str]:
    tree = run_source(source, engine="tree")
    vm = run_source(source, engine="vm")
    case.assertEqual(tree.returncode, vm.returncode,
                     f"exit mismatch\n tree={tree.combined}\n vm={vm.combined}")
    case.assertEqual(tree.stdout, vm.stdout,
                     f"stdout mismatch\n tree={tree.combined}\n vm={vm.combined}")
    case.assertEqual(tree.stderr, vm.stderr,
                     f"stderr mismatch\n tree={tree.combined}\n vm={vm.combined}")
    assert_no_traceback(case, vm)
    return tree.stdout, vm.stdout


class CoreExpressionTests(unittest.TestCase):
    def test_literals_and_arithmetic(self) -> None:
        source = (
            "print(1 + 2 * 3); print(\"\\n\");\n"
            "print(10 / 3); print(\"\\n\");\n"
            "print(10 % 3); print(\"\\n\");\n"
            "print(2.5 + 1.5); print(\"\\n\");\n"
            "print(true && false); print(\" \"); print(true || false); print(\"\\n\");\n"
            "print(!false); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "7\n3\n1\n4.0\nfalse true\ntrue\n")

    def test_comparison_and_typed(self) -> None:
        source = (
            "print(1 < 2); print(\" \"); print(2 <= 2); print(\" \");\n"
            "print(2 > 3); print(\" \"); print(3 >= 3); print(\"\\n\");\n"
            "print(1 == 1.0); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "true true false true\ntrue\n")

    def test_interpolation_and_casts(self) -> None:
        source = (
            "value := 42;\n"
            "text := $\"value={value} char={'a'} bool={true}\";\n"
            "print(text); print(\"\\n\");\n"
            "print(12 as str); print(\"\\n\");\n"
            "print('b' as str + 'c'); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "value=42 char=a bool=true\n12\nbc\n")


class VariableAndControlTests(unittest.TestCase):
    def test_variables_and_scopes(self) -> None:
        source = (
            "x := 1;\n"
            "x = x + 2;\n"
            "if true { y := 5; print(y); }\n"
            "print(\"\\n\");\n"
            "print(x); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "5\n3\n")

    def test_if_else(self) -> None:
        source = (
            "fun classify(value: int): str {\n"
            "    if value < 0 { return \"neg\"; } else { return \"nonneg\"; }\n"
            "}\n"
            "print(classify(-1)); print(\" \"); print(classify(0)); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "neg nonneg\n")

    def test_for_loop_break_continue(self) -> None:
        source = (
            "total := 0;\n"
            "for index >> 0 >> 10 {\n"
            "    if index == 2 { continue; }\n"
            "    if index == 5 { break; }\n"
            "    total += index;\n"
            "}\n"
            "print(total); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "8\n")

    def test_for_each_and_loop(self) -> None:
        source = (
            "total := 0;\n"
            "for value >> [1, 2, 3] { total += value; }\n"
            "print(total); print(\" \" );\n"
            "count := 0;\n"
            "loop if count < 3 { count += 1; }\n"
            "print(count); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "6 3\n")

    def test_labeled_loops(self) -> None:
        source = (
            "total := 0;\n"
            "for |outer| first >> 0 >> 3 {\n"
            "    for second >> 0 >> 3 {\n"
            "        if second == 1 { continue outer; }\n"
            "        total += first * 10 + second;\n"
            "    }\n"
            "}\n"
            "print(total); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "30\n")


class FunctionTests(unittest.TestCase):
    def test_function_defaults_and_named(self) -> None:
        source = (
            "fun greet(name: str = \"world\", punctuation: str = \"!\"): str {\n"
            "    return $\"hello {name}{punctuation}\";\n"
            "}\n"
            "print(greet()); print(\"\\n\");\n"
            "print(greet(\"Ada\")); print(\"\\n\");\n"
            "print(greet(punctuation >> \"?\")); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "hello world!\nhello Ada!\nhello world?\n")

    def test_recursion(self) -> None:
        source = (
            "fun fact(value: int): int {\n"
            "    if value <= 1 { return 1; }\n"
            "    return value * fact(value - 1);\n"
            "}\n"
            "print(fact(6)); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "720\n")

    def test_lambdas_and_closures(self) -> None:
        source = (
            "factor := 3;\n"
            "times := fun(value: int): int >> value * factor;\n"
            "print(times(4)); print(\"\\n\");\n"
            "apply := fun(function: fun[int, int], value: int): int >> function(value);\n"
            "print(apply(times, 5)); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "12\n15\n")

    def test_overloads(self) -> None:
        source = (
            "fun pick(value: int): str >> \"int\";\n"
            "fun pick(value: str): str >> \"str\";\n"
            "print(pick(1)); print(\" \"); print(pick(\"x\")); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "int str\n")

    def test_variadics_and_spread(self) -> None:
        source = (
            "fun sum(values: int...): int {\n"
            "    total := 0;\n"
            "    for value >> values { total += value; }\n"
            "    return total;\n"
            "}\n"
            "print(sum(1, 2, 3)); print(\" \");\n"
            "print(sum(...[4, 5])); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "6 9\n")


class ContainerTests(unittest.TestCase):
    def test_arrays_and_indexing(self) -> None:
        source = (
            "values := [1, 2, 3];\n"
            "values[0] = 9;\n"
            "print(values); print(\"\\n\");\n"
            "print(values[-1]); print(\" \");\n"
            "print(values[0 >> 2]); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "[9, 2, 3]\n3 [9, 2]\n")

    def test_maps_and_sets(self) -> None:
        source = (
            "values := [\"a\" >> 1, \"b\" >> 2];\n"
            "values[\"c\"] = 3;\n"
            "print(values); print(\"\\n\");\n"
            "unique := [/1, 2, 2, 3];\n"
            "print(unique); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "[a >> 1, b >> 2, c >> 3]\n[/1, 2, 3]\n")

    def test_tuples(self) -> None:
        source = (
            "pair := .[1, 2];\n"
            "print(pair); print(\" \");\n"
            "print(pair[0] + pair[1]); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "[1, 2] 3\n")

    def test_copy_semantics(self) -> None:
        source = (
            "first := [1, 2];\n"
            "second := first;\n"
            "second[0] = 9;\n"
            "print(first); print(\" \"); print(second); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "[1, 2] [9, 2]\n")

    def test_strings_and_characters(self) -> None:
        source = (
            "text := \"abc\";\n"
            "print(text[0]); print(\" \"); print(text[-1]); print(\"\\n\");\n"
            "print(text[0 >> 2]); print(\"\\n\");\n"
            "print('a' < 'b'); print(\"\\n\");\n"
            "print([-]text); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "a c\nab\ntrue\ncba\n")


class TypeAndTraitTests(unittest.TestCase):
    def test_user_types_and_methods(self) -> None:
        source = (
            "type Point[+] {\n"
            "    | x: int;\n"
            "    | y: int;\n"
            "    fun constructor(px: int, py: int): Point {\n"
            "        this.x = px;\n"
            "        this.y = py;\n"
            "    }\n"
            "    fun this.sum(other: Point): int {\n"
            "        return this.x + other.x + this.y + other.y;\n"
            "    }\n"
            "}\n"
            "first := Point.[1, 2];\n"
            "second := Point.[3, 4];\n"
            "print(first.sum(second)); print(\"\\n\");\n"
            "copy := first;\n"
            "copy.x = 9;\n"
            "print(first.x); print(\" \"); print(copy.x); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "10\n1 9\n")

    def test_static_methods(self) -> None:
        source = (
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun zero(): Point >> Point.[0];\n"
            "}\n"
            "value := Point.zero();\n"
            "print(value.x); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "0\n")

    def test_enums(self) -> None:
        source = (
            "type Color enum {\n    RED,\n    GREEN,\n    BLUE,\n}\n"
            "value := Color.GREEN;\n"
            "print(value.name); print(\"\\n\");\n"
            "print(value == Color.GREEN); print(\" \");\n"
            "print(value == Color.RED); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "GREEN\ntrue false\n")

    def test_traits_and_default_methods(self) -> None:
        source = (
            "trait Named {\n"
            "    | target: str;\n"
            "    fun describe(): str >> $\"name={this.target}\";\n"
            "}\n"
            "type Person[+] {\n"
            "    | target: str;\n"
            "}\n"
            "value: Named = Person.[\"Ada\"];\n"
            "print(value.describe()); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "name=Ada\n")

    def test_operator_overloading(self) -> None:
        source = (
            "type Vector[+] {\n"
            "    | x: int;\n"
            "    | y: int;\n"
            "    fun constructor(px: int, py: int): Vector {\n"
            "        this.x = px; this.y = py;\n"
            "    }\n"
            "    fun this.add(other: Vector): Vector {\n"
            "        return Vector.[this.x + other.x, this.y + other.y];\n"
            "    }\n"
            "    fun this.compare(other: Vector): int >> this.x - other.x;\n"
            "}\n"
            "first := Vector.[1, 2];\n"
            "second := Vector.[3, 4];\n"
            "sum := first + second;\n"
            "print(sum.x); print(\" \"); print(sum.y); print(\"\\n\");\n"
            "print(first < second); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "4 6\ntrue\n")


class ErrorTests(unittest.TestCase):
    def test_try_catch_finally(self) -> None:
        source = (
            "try {\n"
            "    error(\"boom\", \"first\");\n"
            "} catch problem {\n"
            "    print(problem.kind); print(\" \");\n"
            "    print(problem.message); print(\" \");\n"
            "    print(problem.details[0]); print(\"\\n\");\n"
            "} finally {\n"
            "    print(\"finally\"); print(\"\\n\");\n"
            "}\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "USER boom first\nfinally\n")

    def test_postfix_propagation(self) -> None:
        source = (
            "fun risky(value: int): int? {\n"
            "    if value < 0 { return fail(\"VALUE\", \"negative\"); }\n"
            "    return value * 2;\n"
            "}\n"
            "fun caller(value: int): int? {\n"
            "    result := risky(value)?;\n"
            "    return result + 1;\n"
            "}\n"
            "print(caller(3)); print(\"\\n\");\n"
            "error_value := caller(-1);\n"
            "print(error_value.kind); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "7\nVALUE\n")

    def test_try_finally_return_and_break(self) -> None:
        source = (
            "fun pick(): int {\n"
            "    try {\n"
            "        return 5;\n"
            "    } finally {\n"
            "        print(\"cleanup\"); print(\" \");\n"
            "    }\n"
            "}\n"
            "print(pick()); print(\"\\n\");\n"
            "for index >> 0 >> 3 {\n"
            "    try {\n"
            "        if index == 1 { break; }\n"
            "    } finally {\n"
            "        print(index);\n"
            "    }\n"
            "}\n"
            "print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "cleanup 5\n01\n")

    def test_error_frames(self) -> None:
        source = (
            "fun inner(): int {\n"
            "    return 1 + \"x\";\n"
            "}\n"
            "try {\n"
            "    inner();\n"
            "} catch problem {\n"
            "    print(problem.kind); print(\"\\n\");\n"
            "}\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "OPERATION\n")


class ReferenceTests(unittest.TestCase):
    def test_reference_parameter(self) -> None:
        source = (
            "fun increment(value: &int) {\n"
            "    value += 1;\n"
            "}\n"
            "counter := 10;\n"
            "increment(&counter);\n"
            "print(counter); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "11\n")

    def test_reference_pipeline(self) -> None:
        source = (
            "fun add_ten(value: &int) {\n"
            "    value += 10;\n"
            "}\n"
            "values := [1, 2];\n"
            "values[0] &> add_ten;\n"
            "print(values[0]); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "11\n")


class AsyncTests(unittest.TestCase):
    def test_async_await(self) -> None:
        source = (
            "async fun double(value: int): int >> value * 2;\n"
            "result := await double(21);\n"
            "print(result); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "42\n")

    def test_spawn_and_await(self) -> None:
        source = (
            "async fun triple(value: int): int >> value * 3;\n"
            "handle := spawn triple(7);\n"
            "print(await handle); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "21\n")

    def test_top_level_await(self) -> None:
        source = (
            "async fun value(): int >> 9;\n"
            "print(await value()); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "9\n")


class ExceptionEdgeTests(unittest.TestCase):
    def test_error_inside_catch_reaches_outer_handler(self) -> None:
        source = (
            "try {\n"
            "    try { error(\"inner\"); } catch p { error(\"from-catch\"); }\n"
            "} catch outer {\n"
            "    print(\"outer: \"); print(outer.message); print(\"\\n\");\n"
            "}\n"
            "print(\"done\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "outer: from-catch\ndone\n")

    def test_error_inside_catch_runs_outer_finally(self) -> None:
        source = (
            "try {\n"
            "    try { error(\"inner\"); } catch p { error(\"from-catch\"); }\n"
            "} finally { print(\"outer finally\\n\"); }\n"
        )
        out, _ = run_both(self, source)
        self.assertTrue(out.startswith("outer finally\n"))
        self.assertIn("from-catch", out)

    def test_propagate_runs_finally(self) -> None:
        source = (
            "fun risky(): int? {\n"
            "    try { return fail(\"VALUE\", \"x\")?; }\n"
            "    finally { print(\"finally\\n\"); }\n"
            "}\n"
            "print(risky().kind); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "finally\nVALUE\n")

    def test_propagate_runs_nested_finally(self) -> None:
        source = (
            "fun risky(): int? {\n"
            "    try {\n"
            "        try { return fail(\"VALUE\", \"x\")?; }\n"
            "        finally { print(\"inner finally\\n\"); }\n"
            "    } finally { print(\"outer finally\\n\"); }\n"
            "}\n"
            "print(risky().kind); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "inner finally\nouter finally\nVALUE\n")

    def test_break_inside_finally_discards_pending_error(self) -> None:
        source = (
            "for i >> 0 >> 2 {\n"
            "    try { error(\"boom\"); } finally {\n"
            "        print(\"inner\\n\");\n"
            "        if i == 0 { break; }\n"
            "    }\n"
            "}\n"
            "print(\"after\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "inner\nafter\n")

    def test_catch_binding_does_not_leak(self) -> None:
        source = (
            "x := 1;\n"
            "try { error(\"x\"); } catch x { print(x.message); print(\"\\n\"); }\n"
            "print(x); print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "x\n1\n")

    def test_forward_reference_is_an_identifier_error(self) -> None:
        source = "print(x); x := 1;\n"
        tree = run_source(source, engine="tree")
        vm = run_source(source, engine="vm")
        self.assertEqual(tree.returncode, 1)
        self.assertEqual(vm.returncode, 1)
        self.assertIn("IDENTIFIER ERROR", vm.stdout)

    def test_deep_recursion_is_a_language_error(self) -> None:
        source = (
            "fun down(n: int): int {\n"
            "    if n <= 0 { return 0; }\n"
            "    return down(n - 1);\n"
            "}\n"
            "print(down(890)); print(\"\\n\");\n"
        )
        tree = run_source(source, engine="tree")
        vm = run_source(source, engine="vm")
        self.assertEqual(tree.returncode, 1)
        self.assertEqual(vm.returncode, 1)
        self.assertIn("RECURSION ERROR", vm.stdout)
        self.assertIn("Maximum evaluation depth exceeded", vm.stdout)


class BlockScopeTests(unittest.TestCase):
    def test_try_local_is_hidden_in_catch(self) -> None:
        source = (
            "try { hidden := 1; error(\"x\"); }\n"
            "catch problem { print(hidden); }\n"
        )
        tree = run_source(source, engine="tree")
        vm = run_source(source, engine="vm")
        self.assertEqual(tree.returncode, 1)
        self.assertEqual(vm.returncode, 1)
        self.assertIn("IDENTIFIER ERROR", vm.stdout)

    def test_catch_binding_is_hidden_after_catch(self) -> None:
        source = "try { } catch problem { inner := 5; }\nprint(inner);\n"
        tree = run_source(source, engine="tree")
        vm = run_source(source, engine="vm")
        self.assertEqual(tree.returncode, 1)
        self.assertEqual(vm.returncode, 1)
        self.assertIn("IDENTIFIER ERROR", vm.stdout)

    def test_loop_variable_is_hidden_after_loop(self) -> None:
        source = "for index >> 0 >> 2 { print(index); }\nprint(index);\n"
        tree = run_source(source, engine="tree")
        vm = run_source(source, engine="vm")
        self.assertEqual(tree.returncode, 1)
        self.assertEqual(vm.returncode, 1)
        self.assertIn("IDENTIFIER ERROR", vm.stdout)

    def test_match_binding_is_hidden_after_case(self) -> None:
        source = "match [1] { case [value] >> print(value); }\nprint(value);\n"
        tree = run_source(source, engine="tree")
        vm = run_source(source, engine="vm")
        self.assertEqual(tree.returncode, 1)
        self.assertEqual(vm.returncode, 1)
        self.assertIn("IDENTIFIER ERROR", vm.stdout)

    def test_top_level_redeclare_is_an_error(self) -> None:
        source = "value := 1;\nvalue := 2;\n"
        tree = run_source(source, engine="tree", args=("--no-check",))
        vm = run_source(source, engine="vm", args=("--no-check",))
        self.assertEqual(tree.returncode, 1)
        self.assertEqual(vm.returncode, 1)
        self.assertIn("REDEFINE ERROR", vm.stdout)

    def test_break_and_continue_clean_up_block_scopes(self) -> None:
        source = (
            "for index >> 0 >> 3 {\n"
            "    if index == 1 { marker := 5; break; }\n"
            "    if index == 2 { marker := 6; continue; }\n"
            "    print(index);\n"
            "}\n"
            "print(\"done\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "0done\n")

    def test_catch_scope_restores_on_error(self) -> None:
        source = (
            "outer := 1;\n"
            "try {\n"
            "    inner := 2;\n"
            "    error(\"x\");\n"
            "} catch problem {\n"
            "    print(outer); print(\" \"); print(problem.kind); print(\"\\n\");\n"
            "}\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "1 USER\n")

    def test_if_declaration_does_not_leak(self) -> None:
        source = (
            "maybe: @str = nova;\n"
            "if name := maybe { print(\"yes\"); } else { print(\"no\"); }\n"
            "print(\"\\n\");\n"
            "if name := maybe { print(\"yes\"); } else { print(\"no\"); }\n"
            "print(\"\\n\");\n"
        )
        out, _ = run_both(self, source)
        self.assertEqual(out, "no\nno\n")


if __name__ == "__main__":
    unittest.main()

