from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import call, patch

import scripts.ai_skills_lib.runtime_validation as runtime_validation


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class RuntimeValidationRunnerTests(unittest.TestCase):
    def test_missing_runtime_test_root_is_a_successful_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = StringIO()

            with (
                patch.object(runtime_validation, "subprocess", create=True) as subprocess,
                redirect_stdout(output),
            ):
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        subprocess.run.assert_not_called()
        self.assertIn(
            "validate runtime: OK (no runtime test suites found)",
            output.getvalue(),
        )

    def test_runs_discovered_suite_directories_with_pytest_in_name_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "tests" / "runtime"
            (runtime_root / "zeta").mkdir(parents=True)
            (runtime_root / "alpha").mkdir()
            (runtime_root / "zeta" / "test_zeta.py").write_text("", encoding="utf-8")
            (runtime_root / "alpha" / "test_alpha.py").write_text("", encoding="utf-8")
            output = StringIO()

            with (
                patch.object(runtime_validation, "subprocess", create=True) as subprocess,
                redirect_stdout(output),
            ):
                subprocess.run.side_effect = (
                    SimpleNamespace(returncode=0),
                    SimpleNamespace(returncode=0),
                )
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        self.assertEqual(
            subprocess.run.call_args_list,
            [
                call(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-ra",
                        "tests/runtime/alpha",
                    ],
                    cwd=root,
                    check=False,
                ),
                call(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-ra",
                        "tests/runtime/zeta",
                    ],
                    cwd=root,
                    check=False,
                ),
            ],
        )
        text = output.getvalue()
        self.assertLess(text.index("Runtime suite: alpha"), text.index("Runtime suite: zeta"))
        self.assertIn("validate runtime: OK (2 suites passed)", text)

    def test_process_error_fails_suite_and_continues_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "tests" / "runtime"
            (runtime_root / "alpha").mkdir(parents=True)
            (runtime_root / "beta").mkdir()
            (runtime_root / "alpha" / "test_alpha.py").write_text("", encoding="utf-8")
            (runtime_root / "beta" / "test_beta.py").write_text("", encoding="utf-8")
            output = StringIO()

            with (
                patch.object(runtime_validation, "subprocess", create=True) as subprocess,
                redirect_stdout(output),
            ):
                subprocess.run.side_effect = (
                    OSError("pytest process unavailable"),
                    SimpleNamespace(returncode=0),
                )
                try:
                    result = runtime_validation.run_runtime_validation(root)
                except OSError as error:
                    self.fail(f"runtime validation leaked a process error: {error}")

        self.assertEqual(result, 1)
        self.assertEqual(subprocess.run.call_count, 2)
        self.assertIn(
            "Runtime suite alpha: FAILED (pytest process unavailable)",
            output.getvalue(),
        )
        self.assertIn(
            "validate runtime: FAILED (1 of 2 suites failed)",
            output.getvalue(),
        )

    def test_existing_empty_runtime_root_fails_instead_of_passing_vacuously(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests" / "runtime").mkdir(parents=True)
            output = StringIO()

            with redirect_stdout(output):
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 1)
        self.assertIn("contains no runtime test suites", output.getvalue())

    def test_broken_runtime_root_symlink_fails_instead_of_looking_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests" / "runtime").symlink_to(
                root / "missing-runtime-root",
                target_is_directory=True,
            )
            output = StringIO()

            with redirect_stdout(output):
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 1)
        self.assertIn("must be a non-symlink directory", output.getvalue())

    def test_unsupported_runtime_root_entries_fail_without_running_pytest(self) -> None:
        entry_builders = {
            "root file": lambda runtime_root: (runtime_root / "test_root.py").write_text(
                "", encoding="utf-8"
            ),
            "hidden directory": lambda runtime_root: (runtime_root / ".hidden").mkdir(),
            "empty suite": lambda runtime_root: (runtime_root / "empty").mkdir(),
            "symlink": lambda runtime_root: (runtime_root / "linked").symlink_to(
                runtime_root / "missing", target_is_directory=True
            ),
        }
        for label, build in entry_builders.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime_root = root / "tests" / "runtime"
                runtime_root.mkdir(parents=True)
                build(runtime_root)
                output = StringIO()

                with (
                    patch.object(runtime_validation, "subprocess", create=True) as subprocess,
                    redirect_stdout(output),
                ):
                    result = runtime_validation.run_runtime_validation(root)

                self.assertEqual(result, 1)
                subprocess.run.assert_not_called()
                self.assertIn("validate runtime: FAILED", output.getvalue())


class RuntimeTestDependencyTests(unittest.TestCase):
    def test_pytest_and_http_mock_dependencies_are_exactly_pinned(self) -> None:
        requirements = (REPOSITORY_ROOT / "requirements-test.txt").read_text(
            encoding="utf-8"
        )

        self.assertIn("pytest==9.1.1", requirements.splitlines())
        self.assertIn("responses==0.26.2", requirements.splitlines())


if __name__ == "__main__":
    unittest.main()
