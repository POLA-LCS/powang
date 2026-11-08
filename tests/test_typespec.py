import unittest

from src import typespec as ts


class TypeSpecParsingTests(unittest.TestCase):
    def test_round_trip_nested(self) -> None:
        text = "arr[map[str, arr[tup[int, str]]]]"
        spec, end = ts.parse_type_text(text)
        self.assertEqual(end, len(text))
        self.assertEqual(ts.render(spec), text)

    def test_rest_tuple(self) -> None:
        spec = ts.type_of_str("tup[int, ...]")
        self.assertEqual(ts.render(spec), "tup[int, ...]")
        self.assertTrue(spec.rest)

    def test_function_type(self) -> None:
        spec = ts.type_of_str("fun[int, &str, bool]")
        self.assertIs(spec.kind, ts.Kind.FUNCTION)
        self.assertEqual(ts.render(spec), "fun[int, &str, bool]")

    def test_qualifiers(self) -> None:
        spec = ts.type_of_str("&arr[any]!")
        self.assertTrue(spec.reference)
        self.assertTrue(spec.const)
        self.assertEqual(ts.render(spec), "&arr[any]!")

    def test_any_alias(self) -> None:
        self.assertEqual(ts.render(ts.type_of_str("any")), "any")

    def test_union_round_trip(self) -> None:
        spec = ts.type_of_str("int | num | str")
        self.assertIs(spec.kind, ts.Kind.UNION)
        self.assertEqual(ts.render(spec), "int | num | str")

    def test_union_flattens_and_deduplicates(self) -> None:
        spec = ts.union([
            ts.type_of_str("int | num"),
            ts.type_of_str("num"),
            ts.type_of_str("str"),
        ])
        self.assertEqual(ts.render(spec), "int | num | str")


class TypeSpecRelationTests(unittest.TestCase):
    def test_rest_tuple_accepts_fixed(self) -> None:
        target = ts.type_of_str("tup[int, ...]")
        source = ts.type_of_str("tup[int, int, int]")
        self.assertTrue(ts.assignable(target, source))

    def test_array_any_accepts_element(self) -> None:
        self.assertTrue(ts.assignable(ts.type_of_str("arr[any]"), ts.type_of_str("arr[int]")))

    def test_array_is_not_tuple(self) -> None:
        self.assertFalse(ts.assignable(ts.type_of_str("tup[int]"), ts.type_of_str("arr[int]")))

    def test_mapping_value_covariance(self) -> None:
        self.assertTrue(ts.assignable(ts.type_of_str("map[str, any]"), ts.type_of_str("map[str, int]")))

    def test_join_numeric(self) -> None:
        self.assertEqual(ts.render(ts.join(ts.type_of_str("int"), ts.type_of_str("num"))), "num")

    def test_join_mixed(self) -> None:
        self.assertEqual(ts.render(ts.join(ts.type_of_str("int"), ts.type_of_str("str"))), "mixed")

    def test_union_has_no_unrelated_numeric_coercion(self) -> None:
        self.assertTrue(ts.assignable(ts.type_of_str("int | num"), ts.type_of_str("num")))
        self.assertFalse(ts.assignable(ts.type_of_str("int | str"), ts.type_of_str("num")))

    def test_source_union_requires_all_branches(self) -> None:
        self.assertTrue(ts.assignable(ts.type_of_str("num"), ts.type_of_str("int | num")))
        self.assertFalse(ts.assignable(ts.type_of_str("str"), ts.type_of_str("int | num")))


if __name__ == "__main__":
    unittest.main()
