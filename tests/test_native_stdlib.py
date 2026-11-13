"""Native parity for the default standard library host bridge."""

from __future__ import annotations

import re
import unittest

from src.vm.native.build import ensure_runtime
from src.vm.native.compiler import NativeBuildError
from tests.helpers import run_source


SOURCE = (
    "use url;\n"
    "use json;\n"
    "use strings;\n"
    "use crypto;\n"
    "use time;\n"
    "\n"
    'print(strings.pad_left("x", 5)); print("|");\n'
    'print(strings.pad_right("x", 5, ".")); print("|");\n'
    'print(strings.parse_number(" 2.5 ")); print(" ");\n'
    'print(strings.format_number(1.256, 2)); print("\\n");\n'
    'print(json.stringify(["a" >> 1, "b" >> [1, 2]], 2));\n'
    'print("\\n");\n'
    'print(url.decode("a+b%26c")); print("\\n");\n'
    'query := url.parse_query("a=1&b=2&a=3&blank=");\n'
    'print(query["a"]); print(" "); print(query["b"]); print(" ");\n'
    'print(query["blank"]); print("\\n");\n'
    'print(url.query_build(["q" >> ["a", "b"], "page" >> 2]));\n'
    'print("\\n");\n'
    'print(crypto.hmac_sha256("key", "message")); print("\\n");\n'
    'print(size(crypto.random_token(8))); print(" ");\n'
    'print(crypto.constant_time_compare("abc", "abc")); print(" ");\n'
    'print(crypto.constant_time_compare("abc", "abd")); print("\\n");\n'
    'print(time.format_epoch(0, "%Y-%m-%dT%H:%M:%SZ")); print("\\n");\n'
    'print(time.format_epoch(1.25, "%S.%f")); print("\\n");\n'
    'print(size(time.now_iso())); print("\\n");\n'
)


ERROR_SOURCES = (
    (
        "random token zero",
        "use crypto;\nprint(crypto.random_token(0));\n",
    ),
    (
        "random token bool",
        "use crypto;\nprint(crypto.random_token(true));\n",
    ),
    (
        "format epoch bool",
        'use time;\nprint(time.format_epoch(true, "%Y"));\n',
    ),
    (
        "nested query value",
        'use url;\nprint(url.query_build(["a" >> [["b"]]]));\n',
    ),
    (
        "negative json indent",
        'use json;\nprint(json.stringify(["a" >> 1], -1));\n',
    ),
    (
        "bad log level",
        'use log;\nlog.set_level("trace");\n',
    ),
    (
        "bad integer text",
        'use strings;\nprint(strings.parse_int("x"));\n',
    ),
    (
        "bad number text",
        'use strings;\nprint(strings.parse_number("x"));\n',
    ),
    (
        "negative decimals",
        'use strings;\nprint(strings.format_number(1.2, -1));\n',
    ),
    (
        "long pad fill",
        'use strings;\nprint(strings.pad_left("x", 5, ".."));\n',
    ),
)

LOG_SOURCE = (
    "use log;\n"
    'log.set_level("debug");\n'
    'log.info("hello");\n'
    'log.debug("detail");\n'
    'log.with_fields("warn", "msg", ["k" >> 1, "ok" >> true]);\n'
    'print(log.is_enabled("debug")); print(" ");\n'
    'print(log.is_enabled("error")); print("\\n");\n'
    'log.access(7, "GET", "/x", 200, 1.25);\n'
)


def _normalize_log(text: str) -> str:
    return re.sub(
        r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ ",
        "",
        text,
        flags=re.MULTILINE,
    )


class NativeStdlibTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            ensure_runtime()
        except NativeBuildError as error:
            raise unittest.SkipTest(str(error))

    def test_standard_library_matches(self) -> None:
        python = run_source(SOURCE, engine="vm")
        native = run_source(SOURCE, engine="native")
        self.assertEqual(
            (native.returncode, native.stdout, native.stderr),
            (python.returncode, python.stdout, python.stderr),
        )

    def test_standard_library_errors_match(self) -> None:
        for name, source in ERROR_SOURCES:
            with self.subTest(case=name):
                python = run_source(source, engine="vm")
                native = run_source(source, engine="native")
                self.assertEqual(
                    (native.returncode, native.stdout, native.stderr),
                    (python.returncode, python.stdout, python.stderr),
                    name,
                )

    def test_script_arguments_match(self) -> None:
        source = (
            "use args;\n"
            'print(args.count()); print(" ");\n'
            'print(args.all()); print(" ");\n'
            'print(args.at(0)); print(" ");\n'
            'print(args.at(-1)); print("\\n");\n'
        )
        arguments = ("one", "two")
        python = run_source(source, engine="vm", args=arguments)
        native = run_source(source, engine="native", args=arguments)
        self.assertEqual(
            (native.returncode, native.stdout, native.stderr),
            (python.returncode, python.stdout, python.stderr),
        )

    def test_environment_matches(self) -> None:
        source = (
            "use env;\n"
            'print(env.get("POWANG_NATIVE_TEST")); print(" ");\n'
            'print(env.get_or("POWANG_NATIVE_TEST", "fallback"));\n'
            'print(" ");\n'
            'print(env.get_or("POWANG_NATIVE_MISSING", "fallback"));\n'
            'print(" ");\n'
            'print(env.has("POWANG_NATIVE_TEST")); print(" ");\n'
            'print(env.has("POWANG_NATIVE_MISSING")); print("\\n");\n'
        )
        environment = {"POWANG_NATIVE_TEST": "value"}
        python = run_source(source, engine="vm", env=environment)
        native = run_source(source, engine="native", env=environment)
        self.assertEqual(
            (native.returncode, native.stdout, native.stderr),
            (python.returncode, python.stdout, python.stderr),
        )

    def test_log_output_matches(self) -> None:
        python = run_source(LOG_SOURCE, engine="vm")
        native = run_source(LOG_SOURCE, engine="native")
        self.assertEqual(native.returncode, python.returncode)
        self.assertEqual(native.stdout, python.stdout)
        self.assertEqual(
            _normalize_log(native.stderr),
            _normalize_log(python.stderr),
        )


if __name__ == "__main__":
    unittest.main()
