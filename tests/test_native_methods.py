"""Native type methods, set literals, &> pipelines and container locks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import assert_no_traceback, run_source  # noqa: E402


class LiteralTests(unittest.TestCase):
    def test_empty_literals(self) -> None:
        result = run_source(
            "a := []; t := .[]; m := [>>]; s := [/];\n"
            "print(a); print(\" \"); print(t); print(\" \");\n"
            "print(m); print(\" \"); print(s); print(\" \");\n"
            "print(typedeep(a)); print(\" \"); print(typedeep(t)); print(\" \");\n"
            "print(typedeep(m)); print(\" \"); print(typedeep(s)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[] [] [] [/] arr[any] tup map set[any]\n")

    def test_set_literal_deduplicates(self) -> None:
        result = run_source(
            "values := [/1, 2, 2, 3];\n"
            "print(values); print(\" \"); print(typedeep(values)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[/1, 2, 3] set[int]\n")

    def test_map_marker_with_entries_is_rejected(self) -> None:
        result = run_source('[>> "a" >> 1];\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only the empty map literal", result.combined)
        assert_no_traceback(self, result)


class ArrayMethodTests(unittest.TestCase):
    def test_push_pure_and_reference(self) -> None:
        result = run_source(
            "source := [1, 2];\n"
            "copy := source :> arr.push(3);\n"
            "source &> arr.push(3);\n"
            "print(copy); print(\" \"); print(source); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2, 3] [1, 2, 3]\n")

    def test_add_flattens_and_widens_union(self) -> None:
        result = run_source(
            "ints: arr[int] = [1, 2];\n"
            "nums: arr[num] = [2.5];\n"
            "combined := arr.add(ints, nums);\n"
            "print(combined); print(\" \"); print(typedeep(combined)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2, 2.5] arr[int | num]\n")

    def test_add_mutating_chain(self) -> None:
        result = run_source(
            "values := [1];\n"
            "values &> arr.add([2, 3]) :> arr.add([4]);\n"
            "print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2, 3, 4]\n")

    def test_pop_and_popget(self) -> None:
        result = run_source(
            "values := [1, 2, 3];\n"
            "removed := values &> arr.popget();\n"
            "values &> arr.pop(0);\n"
            "print(removed); print(\" \"); print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "3 [2]\n")

    def test_put_and_popval(self) -> None:
        result = run_source(
            "values := [1, 2, 1, 1];\n"
            "values &> arr.put(1, 9);\n"
            "values &> arr.popval(1, 1);\n"
            "print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[9, 2, 1, 1]\n")

    def test_postfix_popget(self) -> None:
        result = run_source(
            "values := [1, 2, 3];\n"
            "print(values :> arr.popget()); print(\" \"); print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "3 [1, 2, 3]\n")


class MapMethodTests(unittest.TestCase):
    def test_has_get_and_index_insert(self) -> None:
        result = run_source(
            "values := [>>];\n"
            "values[\"a\"] = 1;\n"
            "print(map.has(values, \"a\")); print(\" \");\n"
            "print(map.get(values, \"b\", 9)); print(\" \");\n"
            "print(values[\"a\"]); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "true 9 1\n")

    def test_map_get_without_fallback_throws(self) -> None:
        result = run_source(
            "values := [>>];\n"
            "print(map.get(values, \"missing\")); print(\"\\n\");\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Does not refers to a value", result.combined)

    def test_pop_and_popget(self) -> None:
        result = run_source(
            "values := [\"a\" >> 1, \"b\" >> 2];\n"
            "removed := values &> map.popget(\"a\");\n"
            "values &> map.pop(\"b\");\n"
            "print(removed); print(\" \"); print(size(values)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "1 0\n")

    def test_merge_and_keys_values(self) -> None:
        result = run_source(
            "first := [\"a\" >> 1];\n"
            "second := [\"b\" >> 2];\n"
            "merged := map.merge(first, second);\n"
            "print(map.keys(merged)); print(\" \"); print(map.values(merged)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[a, b] [1, 2]\n")


class StringMethodTests(unittest.TestCase):
    def test_arithmetic_methods(self) -> None:
        result = run_source(
            "print(\"ab\" :> str.add(\"cd\")); print(\" \");\n"
            "print(\"abab\" :> str.sub(\"ab\")); print(\" \");\n"
            "print(\"ab\" :> str.mul(2)); print(\" \");\n"
            "print(\"a,b,c\" :> str.div(\",\")); print(\" \");\n"
            "print(\"abab\" :> str.count(\"ab\")); print(\" \");\n"
            "print(\"ab\" :> str.reverse); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "abcd ab abab [a, b, c] 2 ba\n")

    def test_reference_string_rebinds(self) -> None:
        result = run_source(
            "text := \"a\";\n"
            "text &> str.add(\"b\");\n"
            "print(text); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "ab\n")


class TupleMethodTests(unittest.TestCase):
    def test_tuple_methods(self) -> None:
        result = run_source(
            "pair := .[1, 2];\n"
            "print(tup.get(pair, 1)); print(\" \");\n"
            "print(tup.to_arr(pair)); print(\" \");\n"
            "print(tup.add(pair, .[3])); print(\" \");\n"
            "print(tup.size(pair)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "2 [1, 2] [1, 2, 3] 2\n")


class SetMethodTests(unittest.TestCase):
    def test_set_operations(self) -> None:
        result = run_source(
            "first := [/1, 2, 3];\n"
            "second := [/3, 4];\n"
            "print(set.has(first, 2)); print(\" \");\n"
            "print(set.union(first, second)); print(\" \");\n"
            "print(set.intersection(first, second)); print(\" \");\n"
            "print(set.difference(first, second)); print(\" \");\n"
            "print(set.size(first)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "true [/1, 2, 3, 4] [/3] [/1, 2] 3\n")

    def test_set_popget(self) -> None:
        result = run_source(
            "values := [/1, 2];\n"
            "print(values &> set.popget(1)); print(\" \"); print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "true [/2]\n")


class PipelineTests(unittest.TestCase):
    def test_reference_pipeline_sugar(self) -> None:
        result = run_source(
            "values := [1, 2];\n"
            "values &> arr.push(3);\n"
            "print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2, 3]\n")

    def test_optional_parentheses_with_defaults(self) -> None:
        result = run_source(
            "use strings;\n"
            "print(\"a b c\" :> strings.split); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[a, b, c]\n")


class CopyAndLockTests(unittest.TestCase):
    def test_plain_parameter_is_a_deep_copy(self) -> None:
        result = run_source(
            "fun edit(values: arr[int]) { values[0] = 9; }\n"
            "values := [1, 2];\n"
            "edit(values);\n"
            "print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2]\n")

    def test_reference_parameter_mutates(self) -> None:
        result = run_source(
            "fun edit(values: &arr[int]) { values[0] = 9; }\n"
            "values := [1, 2];\n"
            "edit(&values);\n"
            "print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[9, 2]\n")

    def test_array_structure_and_element_locks(self) -> None:
        result = run_source(
            "values: arr[int]! = [1, 2];\n"
            "values[0] = 9;\n"
            "print(values); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[9, 2]\n")

        result = run_source(
            "values: arr[int]! = [1, 2];\n"
            "values &> arr.push(3);\n"
        )
        self.assertNotEqual(result.returncode, 0)

        result = run_source(
            "values: arr[int!] = [1, 2];\n"
            "values[0] = 9;\n"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_map_locks(self) -> None:
        result = run_source(
            "values: map[str, int]! = [\"a\" >> 1];\n"
            "values[\"a\"] = 2;\n"
            "print(values[\"a\"]); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "2\n")

        result = run_source("values: map[str, int]! = [>>];\nvalues[\"a\"] = 1;\n")
        self.assertNotEqual(result.returncode, 0)

        result = run_source("values: map[str, int!] = [\"a\" >> 1];\nvalues[\"a\"] = 2;\n")
        self.assertNotEqual(result.returncode, 0)


class GenericTypeTests(unittest.TestCase):
    def test_generic_type_construction(self) -> None:
        result = run_source(
            "type Box[+][T] { | value: T; }\n"
            "box := Box[int].[5];\n"
            "print(box.value); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "5\n")

    def test_generic_parameters_accept_both_orders(self) -> None:
        result = run_source(
            "type First[T][+] { value: T; }\n"
            "type Second[+][T] { value: T; }\n"
            "print(First[int].[].value); print(\" \"); print(Second[int].[].value); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "<any: undefined> <any: undefined>\n")

    def test_static_and_instance_method_markers(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun origin(): Point { return Point.[0]; }\n"
            "    fun this.get(): int { return this.x; }\n"
            "    fun .plus(value: int): int { return this.x + value; }\n"
            "}\n"
            "point := Point.origin();\n"
            "print(point.get()); print(\" \"); print(point.plus(5)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "0 5\n")

    def test_instance_call_rejects_static_method(self) -> None:
        result = run_source(
            "type Point[+] {\n"
            "    | x: int;\n"
            "    fun origin(): Point { return Point.[0]; }\n"
            "}\n"
            "point := Point.[1];\n"
            "point.origin();\n"
        )
        self.assertNotEqual(result.returncode, 0)


class FileAndTaskMethodTests(unittest.TestCase):
    def test_file_methods(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(prefix="powang-file-") as directory:
            target = (Path(directory) / "data.txt").as_posix()
            result = run_source(
                f'handle := file.open("{target}", "write");\n'
                'file.write(handle, "hello");\n'
                "handle.close();\n"
                f'handle = file.open("{target}", "read");\n'
                "print(handle.read()); print(\"\\n\");\n"
                "handle.close();\n"
            )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "hello\n")

    def test_task_methods(self) -> None:
        result = run_source(
            "fun work(): int { return 7; }\n"
            "handle := spawn work();\n"
            "print(task.status(handle)); print(\" \");\n"
            "print(handle.wait()); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn("7", result.stdout)


class WarningAndTypeErrorTests(unittest.TestCase):
    def test_single_element_tuple_warning(self) -> None:
        result = run_source("value := .[10];\nprint(value);\n")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn("single-element tuple", result.stderr)

    def test_tuple_qualifiers_are_rejected(self) -> None:
        for source in (
            "value: tup[int]! = .[1];\n",
            "value: tup[int!] = .[1];\n",
            "value: tup[int]!! = .[1];\n",
        ):
            with self.subTest(source=source):
                result = run_source(source)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("immutable by default", result.combined)

    def test_map_key_qualifier_is_rejected(self) -> None:
        result = run_source("value: map[str!, int] = [>>];\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("map keys are immutable by default", result.combined)

    def test_unknown_native_member_is_rejected(self) -> None:
        result = run_source("print([1, 2] :> arr.nope);\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no member named 'nope'", result.combined)

    def test_unknown_user_member_is_rejected(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; }\n"
            "point := Point.[1];\n"
            "print(point.missing);\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no member named 'missing'", result.combined)

    def test_unknown_user_method_is_rejected(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; }\n"
            "point := Point.[1];\n"
            "point.missing();\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no method named 'missing'", result.combined)


if __name__ == "__main__":
    unittest.main()
