"""The built-in Project configuration type."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import run_file, run_source, write_po  # noqa: E402


class ProjectRuntimeTests(unittest.TestCase):
    def test_project_member_access(self) -> None:
        result = run_source(
            "module project;\n"
            "export project: Project = Project.[\n"
            "    modules >> [\"host\"],\n"
            "    paths >> [\".\"],\n"
            "    logLevel >> \"debug\",\n"
            "    allowSystem >> true\n"
            "];\n"
            'print(project.logLevel); print(" ");\n'
            'print(project.allowSystem); print(" ");\n'
            'print(project.modules[0]); print(" ");\n'
            'print(project.paths[0]); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "debug true host .\n")

    def test_project_positional_construction(self) -> None:
        result = run_source(
            "module project;\n"
            "export project: Project = Project.[[\"x\"], [\".\"], \"info\", false];\n"
            'print(project.logLevel); print(" ");\n'
            'print(project.allowSystem); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "info false\n")

    def test_project_defaults(self) -> None:
        result = run_source(
            "module project;\n"
            "export project: Project = Project.[];\n"
            'print(project.logLevel); print(" ");\n'
            'print(size(project.modules)); print(" ");\n'
            'print(project.allowSystem); print("\\n");\n'
        )
        self.assertEqual(result.stdout, "info 0 false\n")

    def test_implicit_project_variable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="powang-project-") as directory:
            root = Path(directory)
            write_po(
                root,
                "project.po",
                "module project;\n"
                "export project: Project = Project.[\n"
                "    modules >> [],\n"
                "    paths >> [\".\"],\n"
                "    logLevel >> \"warning\",\n"
                "    allowSystem >> false\n"
                "];\n",
            )
            main_path = write_po(
                root,
                "main.po",
                'print(project.logLevel); print("\\n");\n',
            )
            result = run_file(main_path)
        self.assertEqual(result.stdout, "warning\n")


class ProjectDiagnosticTests(unittest.TestCase):
    def test_unknown_project_field(self) -> None:
        result = run_source(
            "module project;\n"
            "export project: Project = Project.[bogus >> 1];\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Project has no field named 'bogus'", result.combined)
        self.assertIn("modules, paths, logLevel, allowSystem", result.combined)

    def test_wrong_project_field_type(self) -> None:
        result = run_source(
            "module project;\n"
            "export project: Project = Project.[modules >> [1]];\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("expected arr[str]", result.combined)
        self.assertIn("arr[int]", result.combined)

    def test_unknown_project_member(self) -> None:
        result = run_source(
            "module project;\n"
            "export project: Project = Project.[];\n"
            "print(project.bogus);\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Project has no property named 'bogus'", result.combined)

    def test_project_cannot_be_redeclared(self) -> None:
        result = run_source(
            "type Project { | value: int; }\n",
            args=("--check",),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("a powang native type", result.combined)


if __name__ == "__main__":
    unittest.main()
