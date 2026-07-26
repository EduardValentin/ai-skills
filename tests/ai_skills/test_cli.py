from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import scripts.ai_skills as cli


class RuntimeValidationCliTests(unittest.TestCase):
    def test_trusted_launcher_ignores_attacker_python_startup_hooks(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            attacker = Path(temporary) / "attacker"
            marker = Path(temporary) / "imported-attacker-config"
            startup_marker = Path(temporary) / "sitecustomize-loaded"
            package = attacker / "scripts" / "ai_skills_lib"
            package.mkdir(parents=True)
            (attacker / "scripts" / "__init__.py").write_text("", encoding="utf-8")
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "config.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
                "raise RuntimeError('attacker config imported')\n",
                encoding="utf-8",
            )
            (attacker / "sitecustomize.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(startup_marker)!r}).write_text('loaded', encoding='utf-8')\n"
                "raise SystemExit(0)\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                (str(attacker), str(repository))
            )

            completed = subprocess.run(
                [str(repository / "scripts" / "ai-skills"), "--help"],
                cwd=attacker,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse(startup_marker.exists())

    def test_launcher_prefers_repository_scripts_package(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            attacker = Path(temporary) / "site-packages"
            marker = Path(temporary) / "imported-attacker-package"
            package = attacker / "scripts"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
                "raise RuntimeError('attacker scripts package imported')\n",
                encoding="utf-8",
            )
            command = (
                "import runpy, sys\n"
                f"sys.path.append({str(attacker)!r})\n"
                f"sys.argv = [{str(repository / 'scripts' / 'ai_skills.py')!r}, '--help']\n"
                f"runpy.run_path({str(repository / 'scripts' / 'ai_skills.py')!r}, "
                "run_name='__main__')\n"
            )

            completed = subprocess.run(
                [sys.executable, "-I", "-c", command],
                cwd=attacker,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(marker.exists())

    def test_launcher_does_not_expose_repository_root_to_dependency_imports(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            copied_repository = Path(temporary) / "repository"
            shutil.copytree(repository / "scripts", copied_repository / "scripts")
            shutil.copy2(
                repository / "requirements-test.txt",
                copied_repository / "requirements-test.txt",
            )
            marker = Path(temporary) / "shadow-dependency-imported"
            shadow = copied_repository / "strictyaml" / "__init__.py"
            shadow.parent.mkdir()
            shadow.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(copied_repository / "scripts" / "ai_skills.py"),
                    "validate",
                    "static",
                ],
                cwd=copied_repository,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertFalse(marker.exists())

    def test_direct_nonisolated_script_execution_is_rejected(self) -> None:
        repository = Path(__file__).resolve().parents[2]

        completed = subprocess.run(
            [sys.executable, str(repository / "scripts" / "ai_skills.py"), "--help"],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("scripts/ai-skills", completed.stderr)

    def test_unit_test_runner_ignores_python_startup_injection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests" / "ai_skills"
            tests.mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (tests / "__init__.py").write_text("", encoding="utf-8")
            (tests / "test_example.py").write_text(
                "import unittest\n"
                "class ExampleTests(unittest.TestCase):\n"
                "    def test_runs(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            attacker = root / "attacker"
            attacker.mkdir()
            marker = root / "sitecustomize-loaded"
            (attacker / "sitecustomize.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"PYTHONPATH": str(attacker), "PYTHONSTARTUP": str(attacker / "startup.py")},
            ):
                result = cli.run_unit_tests(root)

            self.assertEqual(result, 0)
            self.assertFalse(marker.exists())

    def test_unit_test_runner_does_not_expose_caller_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests" / "ai_skills"
            tests.mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (tests / "__init__.py").write_text("", encoding="utf-8")
            (tests / "test_environment.py").write_text(
                "import os\n"
                "import unittest\n"
                "class EnvironmentTests(unittest.TestCase):\n"
                "    def test_caller_credentials_are_absent(self):\n"
                "        self.assertNotIn('GITHUB_TOKEN', os.environ)\n"
                "        self.assertNotIn('AWS_SECRET_ACCESS_KEY', os.environ)\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "caller-secret",
                    "AWS_SECRET_ACCESS_KEY": "caller-secret",
                },
            ):
                result = cli.run_unit_tests(root)

        self.assertEqual(result, 0)

    def test_unit_test_runner_executes_unittest_and_pytest_test_styles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests" / "ai_skills"
            tests.mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (tests / "__init__.py").write_text("", encoding="utf-8")
            (tests / "test_unittest_style.py").write_text(
                "import unittest\n"
                "class PassingTests(unittest.TestCase):\n"
                "    def test_passes(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            hidden = tests / ".hidden"
            hidden.mkdir()
            (hidden / "__init__.py").write_text("", encoding="utf-8")
            (hidden / "testpytest_style.py").write_text(
                "def test_must_fail():\n"
                "    assert False\n",
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                result = cli.run_unit_tests(root)

        self.assertEqual(result, 1)

    def test_unit_test_runner_keeps_repository_imports_ahead_of_test_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests" / "ai_skills"
            tests.mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (tests / "__init__.py").write_text("", encoding="utf-8")
            canonical = root / "scripts" / "ai_skills_lib"
            canonical.mkdir(parents=True)
            (root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
            (canonical / "__init__.py").write_text("", encoding="utf-8")
            (canonical / "config.py").write_text(
                "SOURCE = 'canonical'\n",
                encoding="utf-8",
            )
            shadow = tests / "scripts" / "ai_skills_lib"
            shadow.mkdir(parents=True)
            (tests / "scripts" / "__init__.py").write_text("", encoding="utf-8")
            (shadow / "__init__.py").write_text("", encoding="utf-8")
            (shadow / "config.py").write_text(
                "SOURCE = 'shadow'\n",
                encoding="utf-8",
            )
            (tests / "test_import_precedence.py").write_text(
                "import unittest\n"
                "from scripts.ai_skills_lib import config\n"
                "class ImportPrecedenceTests(unittest.TestCase):\n"
                "    def test_uses_canonical_module(self):\n"
                "        self.assertEqual(config.SOURCE, 'canonical')\n",
                encoding="utf-8",
            )

            result = cli.run_unit_tests(root)

            self.assertEqual(result, 0)

    def test_unit_test_runner_rejects_a_symlinked_tests_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            outside = Path(temporary) / "outside"
            root.mkdir()
            test_root = outside / "ai_skills"
            test_root.mkdir(parents=True)
            (test_root / "test_external.py").write_text(
                "raise AssertionError('outside test executed')\n",
                encoding="utf-8",
            )
            (root / "tests").symlink_to(outside, target_is_directory=True)
            output = StringIO()

            with redirect_stdout(output):
                result = cli.run_unit_tests(root)

        self.assertEqual(result, 1)
        self.assertIn("non-symlink directory contained", output.getvalue())

    def test_unit_test_runner_rejects_zero_discovered_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests" / "ai_skills"
            tests.mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (tests / "__init__.py").write_text("", encoding="utf-8")

            result = cli.run_unit_tests(root)

        self.assertEqual(result, 1)

    def test_unit_test_runner_rejects_test_modules_inside_generated_caches(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests" / "ai_skills"
            cache = tests / ".pytest_cache"
            cache.mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (tests / "__init__.py").write_text("", encoding="utf-8")
            (tests / "test_anchor.py").write_text(
                "def test_anchor():\n"
                "    assert True\n",
                encoding="utf-8",
            )
            (cache / "testmust_run.py").write_text(
                "def test_must_run():\n"
                "    assert False\n",
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                result = cli.run_unit_tests(root)

        self.assertEqual(result, 1)

    def test_unit_test_runner_rejects_nested_tests_without_package_marker(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests" / "ai_skills"
            nested = tests / "nested"
            nested.mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (tests / "__init__.py").write_text("", encoding="utf-8")
            (tests / "testpassing.py").write_text(
                "import unittest\n"
                "class PassingTests(unittest.TestCase):\n"
                "    def test_passes(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            (nested / "testhidden.py").write_text(
                "raise AssertionError('must not be silently skipped')\n",
                encoding="utf-8",
            )
            output = StringIO()

            with redirect_stdout(output):
                result = cli.run_unit_tests(root)

        self.assertEqual(result, 1)
        self.assertIn("lacks a regular __init__.py", output.getvalue())

    def test_unit_test_runner_redacts_secret_shaped_layout_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests" / "ai_skills"
            secret = "githubToken=actual-prod-value"
            nested = tests / secret
            nested.mkdir(parents=True)
            (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
            (tests / "__init__.py").write_text("", encoding="utf-8")
            (tests / "test_anchor.py").write_text(
                "def test_anchor():\n"
                "    assert True\n",
                encoding="utf-8",
            )
            (nested / "testmust_run.py").write_text(
                "def test_must_run():\n"
                "    assert False\n",
                encoding="utf-8",
            )
            output = StringIO()

            with redirect_stdout(output):
                result = cli.run_unit_tests(root)

        self.assertEqual(result, 1)
        self.assertNotIn(secret, output.getvalue())
        self.assertNotIn("actual-prod-value", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())

    def test_cli_module_load_does_not_require_posix_directory_flags(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        code = (
            "import os, runpy;"
            "hasattr(os, 'O_DIRECTORY') and delattr(os, 'O_DIRECTORY');"
            "runpy.run_path('scripts/ai_skills.py', run_name='portable_ai_skills')"
        )

        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_validate_runtime_dispatches_only_to_model_free_runner(self) -> None:
        model_backed_error = AssertionError("model-backed handler must not run")

        with (
            patch.object(cli, "run_runtime_validation", return_value=1, create=True) as run_runtime,
            patch.object(cli, "run_trigger_query_harness", side_effect=model_backed_error),
            patch.object(cli, "run_behavior_eval_harness", side_effect=model_backed_error),
            patch.object(cli, "run_all_evaluation_harness", side_effect=model_backed_error),
        ):
            result = cli.main(["validate", "runtime"])

        self.assertEqual(result, 1)
        run_runtime.assert_called_once_with(cli.REPOSITORY_ROOT)

    def test_ci_all_runs_runtime_validation_as_a_deterministic_phase(self) -> None:
        order: list[str] = []

        with (
            patch.object(
                cli,
                "run_unit_tests",
                side_effect=lambda root: order.append("unit") or 0,
            ),
            patch.object(
                cli,
                "run_runtime_validation",
                side_effect=lambda root: order.append("runtime") or 1,
            ),
            patch.object(
                cli,
                "run_ci_validation",
                side_effect=lambda root: order.append("validation") or [],
            ),
        ):
            result = cli.main(["validate", "ci-all"])

        self.assertEqual(result, 1)
        self.assertEqual(order, ["validation", "unit", "runtime"])

    def test_ci_all_names_failed_phases_when_no_static_issues_exist(self) -> None:
        output = StringIO()

        with (
            patch.object(cli, "run_ci_validation", return_value=[]),
            patch.object(cli, "run_unit_tests", return_value=1),
            patch.object(cli, "run_runtime_validation", return_value=1),
            redirect_stdout(output),
        ):
            result = cli.main(["validate", "ci-all"])

        self.assertEqual(result, 1)
        self.assertIn("unit tests", output.getvalue())
        self.assertIn("runtime tests", output.getvalue())
        self.assertNotIn("0 validation issues", output.getvalue())

    def test_runtime_failure_blocks_validate_all_model_backed_handler(self) -> None:
        with (
            patch.object(cli, "run_ci_validation", return_value=[]),
            patch.object(cli, "run_unit_tests", return_value=0),
            patch.object(cli, "run_runtime_validation", return_value=1) as run_runtime,
            patch.object(cli, "run_all_evaluation_harness") as run_model_backed,
        ):
            result = cli.main(["validate", "all", "--harness", "codex"])

        self.assertEqual(result, 1)
        run_runtime.assert_called_once_with(cli.REPOSITORY_ROOT)
        run_model_backed.assert_not_called()

    def test_check_local_installs_dispatches_to_read_only_diagnostic(self) -> None:
        with patch.object(cli, "run_local_install_check", return_value=1) as check:
            result = cli.main(["check-local-installs", "--harness", "codex"])

        self.assertEqual(result, 1)
        check.assert_called_once_with(cli.REPOSITORY_ROOT, harness="codex")


if __name__ == "__main__":
    unittest.main()
