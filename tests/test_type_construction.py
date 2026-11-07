"""Type construction, access defaults, unions and typedeep."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import assert_no_traceback, run_file, run_source, write_po  # noqa: E402
from src.lexer.token import LexerTokenType  # noqa: E402
from src.lexer.tokenizer import Tokenizer  # noqa: E402


class TokenizerTests(unittest.TestCase):
    def test_single_pipe_is_a_token(self) -> None:
        tokenizer = Tokenizer("a | b")
        tokens = []
        while True:
            token = tokenizer.getNextToken()
            tokens.append(token)
            if token.type == LexerTokenType.END_OF_FILE:
                break
        self.assertEqual(tokens[1].type, LexerTokenType.PIPE)

    def test_logical_or_still_wins(self) -> None:
        tokenizer = Tokenizer("a || b")
        self.assertEqual(tokenizer.getNextToken().type, LexerTokenType.IDENTIFIER)
        self.assertEqual(tokenizer.getNextToken().type, LexerTokenType.OR)


class AccessDefaultTests(unittest.TestCase):
    def test_public_default(self) -> None:
        result = run_source(
            "type PublicType[+] {\n"
            "    id: int;\n"
            "}\n"
            "value := PublicType.[];\n"
            "value.id = 7;\n"
            "print(value.id); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "7\n")
        self.assertEqual(result.stderr, "")

    def test_private_default(self) -> None:
        result = run_source(
            "type PrivateType[-] {\n"
            "    secret: str;\n"
            "    + fun this.reveal(): str { return this.secret; }\n"
            "    + fun this.assign(value: str): str { this.secret = value; return this.secret; }\n"
            "}\n"
            "value := PrivateType.[];\n"
            "value.assign(\"hidden\");\n"
            "print(value.reveal()); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "hidden\n")

    def test_plain_type_requires_explicit_access(self) -> None:
        result = run_source("type Legacy { value: int; }\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no default access", result.combined)
        assert_no_traceback(self, result)

    def test_redundant_specifier_warns(self) -> None:
        result = run_source(
            "type T[+] {\n"
            "    + value: int;\n"
            "}\n"
            "item := T.[];\n"
            "print(item.value);\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertIn("[WARNING]", result.stderr)
        self.assertIn("unnecessary access specifier '+'", result.stderr)
        self.assertEqual(result.stdout, "<int: undefined>")

    def test_no_warnings_flag_suppresses_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-test-") as directory:
            path = write_po(
                directory,
                "warning.po",
                "type T[+] { + value: int; }\nitem := T.[];\nprint(item.value);\n",
            )
            result = run_file(path, "--no-warnings")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stderr, "")


class ConstructorMemberTests(unittest.TestCase):
    def test_generated_constructor_positional(self) -> None:
        result = run_source(
            "type Person[+] {\n"
            "    id: int!;\n"
            "    | name: str;\n"
            "    | address: str;\n"
            "    age: num;\n"
            "    - cache: int;\n"
            "}\n"
            "person := Person.[\"Ada\", \"London\"];\n"
            "print(person.name); print(\" \"); print(person.address); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "Ada London\n")

    def test_generated_constructor_named(self) -> None:
        result = run_source(
            "type Person[+] {\n"
            "    | name: str;\n"
            "    | address: str;\n"
            "}\n"
            "person := Person.[name >> \"Ada\", address >> \"London\"];\n"
            "print(person.name); print(\" \"); print(person.address); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "Ada London\n")

    def test_legacy_tuple_cast_uses_constructor(self) -> None:
        result = run_source(
            "type Person[+] {\n"
            "    | name: str;\n"
            "    | address: str;\n"
            "}\n"
            "person := .[\"Ada\", \"London\"] as Person;\n"
            "print(person.name); print(\" \"); print(person.address); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "Ada London\n")

    def test_missing_named_argument_is_reported(self) -> None:
        result = run_source(
            "type Person[+] {\n"
            "    | name: str;\n"
            "    | address: str;\n"
            "}\n"
            "person := Person.[name >> \"Ada\"];\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing", result.combined.lower())
        self.assertIn("address", result.combined)

    def test_unknown_named_argument_is_reported(self) -> None:
        result = run_source(
            "type Person[+] { | name: str; }\n"
            "person := Person.[nome >> \"Ada\"];\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no parameter named 'nome'", result.combined)

    def test_duplicate_named_argument_is_reported(self) -> None:
        result = run_source(
            "type Person[+] { | name: str; }\n"
            "person := Person.[name >> \"Ada\", name >> \"Grace\"];\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("more than once", result.combined)

    def test_unknown_named_argument_without_check(self) -> None:
        result = run_source(
            "type Person[+] { | name: str; }\n"
            "person := Person.[nome >> \"Ada\"];\n",
            args=("--no-check",),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no parameter named 'nome'", result.combined)

    def test_duplicate_named_argument_without_check(self) -> None:
        result = run_source(
            "type Person[+] { | name: str; }\n"
            "person := Person.[name >> \"Ada\", name >> \"Grace\"];\n",
            args=("--no-check",),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("more than once", result.combined)

    def test_mixed_arguments_are_rejected(self) -> None:
        result = run_source(
            "type Person[+] {\n"
            "    | name: str;\n"
            "    | address: str;\n"
            "}\n"
            "person := Person.[\"Ada\", address >> \"London\"];\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Named and positional arguments cannot be mixed", result.combined)

    def test_private_constructor_parameter(self) -> None:
        result = run_source(
            "type PrivateType[-] {\n"
            "    | value: int;\n"
            "    + fun this.reveal(): int { return this.value; }\n"
            "}\n"
            "item := PrivateType.[5];\n"
            "print(item.reveal()); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "5\n")

    def test_private_constructor_parameter_is_not_public(self) -> None:
        result = run_source(
            "type PrivateType[-] { | value: int; }\n"
            "item := PrivateType.[5];\n"
            "print(item.value);\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("private property", result.combined)

    def test_const_keyword_member_with_pipe_is_rejected(self) -> None:
        result = run_source("type Broken[+] { | const value: int; }\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("const keyword cannot be combined with |", result.combined)

    def test_write_once_constructor_parameter(self) -> None:
        result = run_source(
            "type Token[+] {\n"
            "    | value: int!;\n"
            "}\n"
            "first := Token.[1];\n"
            "second := Token.[2];\n"
            "print(first.value); print(\" \"); print(second.value); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "1 2\n")

    def test_second_write_to_const_parameter_fails(self) -> None:
        result = run_source(
            "type Token[+] {\n"
            "    | value: int!;\n"
            "    + fun this.change(): int { this.value = 9; return this.value; }\n"
            "}\n"
            "item := Token.[1];\n"
            "item.change();\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[CONST ERROR]", result.combined)

    def test_explicit_constructor_body_hook_runs_after_assignments(self) -> None:
        result = run_source(
            "type Person[+] {\n"
            "    | name: str;\n"
            "    | address: str;\n"
            "\n"
            "    fun constructor {\n"
            "        print(this.name); print(\" \"); print(this.address); print(\"\\n\");\n"
            "    }\n"
            "}\n"
            "Person.[\"Ada\", \"London\"];\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "Ada London\n")
        self.assertEqual(result.stderr, "")

    def test_explicit_parameters_suppress_generation_with_warning(self) -> None:
        result = run_source(
            "type Person[+] {\n"
            "    | name: str;\n"
            "    fun constructor(name: str) { this.name = name; }\n"
            "}\n"
            "person := Person.[\"Ada\"];\n"
            "print(person.name); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "Ada\n")
        self.assertIn("constructor members", result.stderr)
        self.assertIn("ignored", result.stderr)


class NativeConstructionTests(unittest.TestCase):
    def test_scalar_construction(self) -> None:
        result = run_source(
            "print(int.[42]); print(\" \");\n"
            "print(num.[2]); print(\" \");\n"
            "print(str.[25]); print(\" \");\n"
            "print(bool.[0]); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "42 2.0 25 false\n")

    def test_scalar_construction_truncates_like_cast(self) -> None:
        result = run_source("print(int.[2.9]); print(\"\\n\");\n")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "2\n")

    def test_array_and_tuple_construction(self) -> None:
        result = run_source(
            "items := arr.[2, 3, 4];\n"
            "pair := tup.[2, 3.14, \"\"];\n"
            "print(items); print(\" \"); print(typedeep(items)); print(\"\\n\");\n"
            "print(pair); print(\" \"); print(typedeep(pair)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[2, 3, 4] arr[int]\n[2, 3.14, ] tup[int, num, str]\n")

    def test_typed_array_and_tuple_construction(self) -> None:
        result = run_source(
            "items := arr[int].[1, 2, 3];\n"
            "pair := tup[int, str].[2, \"hi\"];\n"
            "print(items); print(\" \"); print(pair); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2, 3] [2, hi]\n")

    def test_typed_construction_applies_implicit_scalar_casts(self) -> None:
        result = run_source(
            "flags := arr[bool].[2, 0];\n"
            "numbers := arr[int].[2.9];\n"
            "print(flags); print(\" \"); print(numbers); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[true, false] [2]\n")

    def test_typed_construction_rejects_assignment_incompatible_cast(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-test-") as directory:
            path = write_po(
                directory,
                "typed.po",
                "pair := tup[int, str].[2, 3];\n",
            )
            result = run_file(path, "--no-check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected str", result.combined)

    def test_typed_tuple_arity_is_checked(self) -> None:
        result = run_source("pair := tup[int, str].[2];\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("arity", result.combined.lower())

    def test_typed_tuple_element_type_is_checked(self) -> None:
        result = run_source("pair := tup[int, str].[2, 3];\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected str", result.combined)

    def test_rest_tuple_construction(self) -> None:
        result = run_source(
            "values := tup[int, ...].[1, 2, 3];\n"
            "print(values); print(\" \"); print(typedeep(values)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2, 3] tup[int, int, int]\n")

    def test_rest_tuple_construction_checks_elements(self) -> None:
        result = run_source("values := tup[int, ...].[1, \"two\"];\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected int", result.combined)

    def test_nova_construction(self) -> None:
        result = run_source("print(typeof(nova.[])); print(\"\\n\");\n")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "nova\n")

    def test_mixed_array_infers_union(self) -> None:
        result = run_source(
            "items := arr.[2, 3.14];\n"
            "print(typedeep(items)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "arr[int | num]\n")

    def test_union_element_type_rejects_unlisted_branch(self) -> None:
        result = run_source("items := arr[int | str].[3.14];\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected int | str", result.combined)

    def test_literal_sugar_matches_canonical_construction(self) -> None:
        result = run_source(
            "print([1, 2, 3] == arr[int].[1, 2, 3]); print(\" \");\n"
            "print([\"a\" >> 2] == map.[\"a\" >> 2]); print(\" \");\n"
            "print(.[2, 3.14] == tup[int, num].[2, 3.14]); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "true true true\n")

    def test_map_construction_last_duplicate_wins(self) -> None:
        result = run_source(
            "items := map.[\"a\" >> 1, \"a\" >> 2];\n"
            "print(items[\"a\"]); print(\" \"); print(size(items)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "2 1\n")

    def test_map_key_must_be_hashable(self) -> None:
        result = run_source("items := map.[[1] >> 2];\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unhashable key", result.combined)

    def test_index_access_is_not_construction(self) -> None:
        result = run_source(
            "items: arr[int] = [10, 20];\n"
            "print(items[0]); print(\" \"); print(arr.[30, 40]); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "10 [30, 40]\n")


class UnionAnnotationTests(unittest.TestCase):
    def test_union_accepts_each_branch(self) -> None:
        result = run_source(
            "value: int | num = 2;\n"
            "value = 2.5;\n"
            "print(value); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "2.5\n")

    def test_union_rejects_unlisted_type(self) -> None:
        result = run_source("value: int | str = 3.14;\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected int | str", result.combined)

    def test_union_array_annotation(self) -> None:
        result = run_source(
            "values: arr[int | num] = [1, 2.5];\n"
            "print(values); print(\" \"); print(typedeep(values)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2.5] arr[int | num]\n")

    def test_union_alias(self) -> None:
        result = run_source(
            "type Mixed >> int | str;\n"
            "value: Mixed = 1;\n"
            "value = \"text\";\n"
            "print(value); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "text\n")

    def test_union_property_keeps_concrete_value(self) -> None:
        result = run_source(
            "type Record[+] { | value: int | str; }\n"
            "record := Record.[\"hi\"];\n"
            "print(record.value); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "hi\n")

    def test_union_object_value_prints_and_typeof(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; }\n"
            "fun show(value: Point | str) { print(value); print(\" \"); }\n"
            "show(Point.[1]);\n"
            "print(typeof(Point.[1])); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "<type: Point> Point\n")

    def test_union_rejects_other_user_type(self) -> None:
        result = run_source(
            "type First[+] { | x: int; }\n"
            "type Second[+] { | y: int; }\n"
            "value: First | str = Second.[1];\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected", result.combined)

    def test_union_container_branches(self) -> None:
        result = run_source(
            "values: arr[int] | str = [1, 2];\n"
            "pair: tup[int, str] | int = .[1, \"a\"];\n"
            "print(values); print(\" \"); print(pair); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "[1, 2] [1, a]\n")

    def test_weak_union_accepts_nova(self) -> None:
        result = run_source(
            "value: @(int | str) = nova;\n"
            "print(typeof(value)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "nova\n")

    def test_union_overload_scores_best_branch(self) -> None:
        result = run_source(
            "fun pick(value: int | str): str { return \"union\"; }\n"
            "fun pick(value: bool): str { return \"bool\"; }\n"
            "print(pick(\"hi\")); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "union\n")

    def test_named_constructor_overload_uses_argument_type(self) -> None:
        result = run_source(
            "type Choice[+] {\n"
            "    x: int;\n"
            "    fun constructor(x: str) { this.x = 0; }\n"
            "    fun constructor(x: int) { this.x = x; }\n"
            "}\n"
            "choice := Choice.[x >> 5];\n"
            "print(choice.x); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "5\n")

    def test_union_cast_with_user_type_branch(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; }\n"
            "point := [7] as Point | int;\n"
            "print(point.x); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "7\n")

    def test_union_const_qualifier_in_type_check(self) -> None:
        result = run_source(
            "value: int | str = 1;\n"
            "print(value :: (int | str)!); print(\" \"); print(value :: int!); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "false false\n")

    def test_const_union_qualifier_positive(self) -> None:
        result = run_source(
            "value: (int | str)! = 1;\n"
            "print(value :: (int | str)!); print(\" \"); print(value :: int!); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "true true\n")

    def test_union_object_survives_assignment_parameter_return_and_property(self) -> None:
        result = run_source(
            "type Item[+] { | value: int; }\n"
            "type Holder[+] { | item: Item | str; }\n"
            "fun identity(value: Item | str): Item | str { return value; }\n"
            "fun show(value: Item | str): str { return format(\"{0}\", value); }\n"
            "first: Item | str = Item.[5];\n"
            "second: Item | str = first;\n"
            "holder := Holder.[second];\n"
            "print(show(identity(second))); print(\" \"); print(holder.item); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "<type: Item> <type: Item>\n")

    def test_union_iterable_and_match_use_concrete_value(self) -> None:
        result = run_source(
            "values: arr | str = [1, 2];\n"
            "for value >> values { print(value); print(\" \"); }\n"
            "subject: int | str = 1;\n"
            "match subject {\n"
            "    case 1 >> print(\"one\\n\");\n"
            "    case _ >> print(\"other\\n\");\n"
            "}\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "1 2 one\n")

    def test_bare_container_union_casts_keep_container(self) -> None:
        result = run_source(
            "array_value := [1, 2] as arr | str;\n"
            "tuple_value := .[1, 2] as tup | str;\n"
            "map_value := [\"a\" >> 1] as map | str;\n"
            "print(typedeep(array_value)); print(\" \");\n"
            "print(typedeep(tuple_value)); print(\" \");\n"
            "print(typedeep(map_value)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "arr[int] tup[int, int] map\n")

    def test_empty_map_accepts_typed_map_union(self) -> None:
        result = run_source(
            "value: map[str, int] | str = map.[];\n"
            "print(typedeep(value)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "map\n")

    def test_union_enum_keeps_variant_formatting(self) -> None:
        result = run_source(
            "type Color enum { RED, GREEN, BLUE }\n"
            "value: Color | str = Color.RED;\n"
            "print(value); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "<Color: RED>\n")


class TypeDeepTests(unittest.TestCase):
    def test_typedeep_reports_structure(self) -> None:
        result = run_source(
            "print(typedeep(tup.[2, 3.14])); print(\" \");\n"
            "print(typedeep([1, 2.5])); print(\" \");\n"
            "print(typedeep(7)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "tup[int, num] arr[int | num] int\n")

    def test_typeof_stays_shallow(self) -> None:
        result = run_source(
            "print(typeof(tup.[2, 3.14])); print(\" \");\n"
            "print(typeof([1, 2])); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "tup arr\n")

    def test_typedeep_user_type(self) -> None:
        result = run_source(
            "type Point[+] { | x: int; | y: int; }\n"
            "print(typedeep(Point.[1, 2])); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "Point\n")

    def test_typedeep_union_value_uses_concrete_payload(self) -> None:
        result = run_source(
            "value: arr | str = [1, 2];\n"
            "print(typedeep(value)); print(\"\\n\");\n"
        )
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "arr[int]\n")


class CheckModeTests(unittest.TestCase):
    def test_check_accepts_valid_construction(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-test-") as directory:
            path = write_po(
                directory,
                "valid.po",
                "type Person[+] { | name: str; | address: str; }\n"
                "person := Person.[name >> \"Ada\", address >> \"London\"];\n"
                "print(person.name);\n",
            )
            result = run_file(path, "--check")
        self.assertEqual(result.returncode, 0, result.combined)
        self.assertEqual(result.stdout, "")

    def test_check_rejects_invalid_instantiation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-test-") as directory:
            path = write_po(
                directory,
                "invalid.po",
                "type Person[+] { | name: str; | address: str; }\n"
                "person := Person.[\"Ada\"];\n",
            )
            result = run_file(path, "--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("address", result.combined)


if __name__ == "__main__":
    unittest.main()
