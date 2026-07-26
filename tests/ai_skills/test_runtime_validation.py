from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import signal
from subprocess import TimeoutExpired
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

import scripts.ai_skills_lib.runtime_validation as runtime_validation


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class RuntimeValidationRunnerTests(unittest.TestCase):
    def test_missing_runtime_test_root_is_a_successful_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = StringIO()

            with (
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(output),
            ):
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        run_process.assert_not_called()
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
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(output),
            ):
                run_process.side_effect = (
                    SimpleNamespace(returncode=0),
                    SimpleNamespace(returncode=0),
                )
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        self.assertEqual(
            [item.args[0][-1] for item in run_process.call_args_list],
            [
                "tests/runtime/alpha/test_alpha.py",
                "tests/runtime/zeta/test_zeta.py",
            ],
        )
        self.assertTrue(
            all(
                "--override-ini=python_files=test*.py"
                in item.args[0]
                for item in run_process.call_args_list
            )
        )
        self.assertTrue(
            all(
                item.kwargs["cwd"] != root
                and item.kwargs["timeout"]
                == runtime_validation.RUNTIME_SUITE_TIMEOUT_SECONDS
                for item in run_process.call_args_list
            )
        )
        text = output.getvalue()
        self.assertLess(text.index("Runtime suite: alpha"), text.index("Runtime suite: zeta"))
        self.assertIn("validate runtime: OK (2 suites passed)", text)

    def test_runs_every_test_star_module_in_a_runtime_suite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "tests" / "runtime" / "alpha"
            suite.mkdir(parents=True)
            (suite / "test_anchor.py").write_text(
                "def test_anchor():\n"
                "    assert True\n",
                encoding="utf-8",
            )
            (suite / "testmust_run.py").write_text(
                "def test_must_run():\n"
                "    assert False\n",
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 1)

    def test_rejects_test_modules_inside_generated_runtime_caches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "tests" / "runtime" / "alpha"
            cache = suite / "__pycache__"
            cache.mkdir(parents=True)
            (suite / "test_anchor.py").write_text(
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
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 1)

    def test_runtime_validation_redacts_secret_shaped_suite_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret = "githubToken=actual-prod-value"
            suite = root / "tests" / "runtime" / secret
            suite.mkdir(parents=True)
            (suite / "test_anchor.py").write_text(
                "def test_anchor():\n"
                "    assert True\n",
                encoding="utf-8",
            )
            output = StringIO()

            with (
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                    return_value=SimpleNamespace(returncode=0),
                ),
                redirect_stdout(output),
            ):
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        self.assertNotIn(secret, output.getvalue())
        self.assertNotIn("actual-prod-value", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())

    def test_each_runtime_suite_receives_a_fresh_repository_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "tests" / "runtime"
            for name in ("alpha", "beta"):
                suite = runtime_root / name
                suite.mkdir(parents=True, exist_ok=True)
                (suite / f"test_{name}.py").write_text("", encoding="utf-8")
            snapshot_roots: list[Path] = []

            def run_suite(*args, **kwargs):
                snapshot_root = kwargs["cwd"]
                snapshot_roots.append(snapshot_root)
                leaked = snapshot_root / "suite-one-state"
                if len(snapshot_roots) == 1:
                    leaked.write_text("private mutation", encoding="utf-8")
                else:
                    self.assertFalse(leaked.exists())
                return SimpleNamespace(returncode=0)

            with (
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(StringIO()),
            ):
                run_process.side_effect = run_suite
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        self.assertEqual(len(snapshot_roots), 2)
        self.assertNotEqual(snapshot_roots[0], snapshot_roots[1])

    def test_pytest_receives_only_the_isolated_test_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "tests" / "runtime" / "alpha"
            suite.mkdir(parents=True)
            (suite / "test_alpha.py").write_text("", encoding="utf-8")
            output = StringIO()

            with (
                patch.dict(
                    runtime_validation.os.environ,
                    {
                        "CALLER_SETTING": "must-not-pass",
                        "GITHUB_TOKEN": "must-not-pass",
                        "PYTHONDONTWRITEBYTECODE": "0",
                    },
                    clear=True,
                ),
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(output),
            ):
                run_process.return_value = SimpleNamespace(returncode=0)
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        environment = run_process.call_args.kwargs["env"]
        self.assertNotIn("CALLER_SETTING", environment)
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertEqual(environment["PATH"], os.defpath)
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], "/dev/null")
        self.assertNotEqual(environment["HOME"], os.environ.get("HOME"))

    def test_pytest_ignores_caller_options_and_plugin_injection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "tests" / "runtime" / "alpha"
            suite.mkdir(parents=True)
            (suite / "test_alpha.py").write_text("", encoding="utf-8")

            with (
                patch.dict(
                    runtime_validation.os.environ,
                    {
                        "PYTEST_ADDOPTS": "--collect-only",
                        "PYTEST_PLUGINS": "attacker_plugin",
                        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "0",
                        "PYTHONHOME": "/tmp/injected-python-home",
                        "PYTHONINSPECT": "1",
                        "PYTHONPATH": "/tmp/injected-python-path",
                        "PYTHONSTARTUP": "/tmp/injected-startup.py",
                        "PYTHONUSERBASE": "/tmp/injected-user-base",
                    },
                    clear=True,
                ),
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(StringIO()),
            ):
                run_process.return_value = SimpleNamespace(returncode=0)
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        environment = run_process.call_args.kwargs["env"]
        self.assertNotIn("PYTEST_ADDOPTS", environment)
        self.assertNotIn("PYTEST_PLUGINS", environment)
        for name in (
            "PYTHONHOME",
            "PYTHONINSPECT",
            "PYTHONPATH",
            "PYTHONSTARTUP",
            "PYTHONUSERBASE",
        ):
            self.assertNotIn(name, environment)
        self.assertEqual(environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertEqual(run_process.call_args.args[0][1:3], ["-I", "-m"])

    def test_runtime_output_with_a_secret_is_quarantined_and_fails(self) -> None:
        credential = "ghp_" + ("a" * 36)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "tests" / "runtime" / "alpha"
            suite.mkdir(parents=True)
            (suite / "test_alpha.py").write_text("", encoding="utf-8")
            output = StringIO()

            with (
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(output),
            ):
                run_process.return_value = SimpleNamespace(
                    returncode=0,
                    stdout=f"unsafe {credential}\n",
                    stderr="",
                )
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 1)
        self.assertNotIn(credential, output.getvalue())
        self.assertIn("quarantined", output.getvalue())

    def test_utf16_runtime_output_with_a_secret_is_quarantined(self) -> None:
        credential = "ghp_" + ("a" * 36)
        for encoding in ("utf-16-le", "utf-16-be"):
            with self.subTest(encoding=encoding):
                output = StringIO()
                completed = SimpleNamespace(
                    returncode=0,
                    stdout=credential.encode(encoding),
                    stderr=b"",
                )

                with redirect_stdout(output):
                    safe = runtime_validation.report_test_process_output(
                        completed,
                        "Runtime suite alpha",
                    )

                self.assertFalse(safe)
                self.assertNotIn(credential, output.getvalue())
                self.assertIn("quarantined", output.getvalue())

    def test_bounded_process_runner_terminates_when_output_exceeds_limit(
        self,
    ) -> None:
        runner = getattr(
            runtime_validation,
            "run_bounded_test_process",
            None,
        )
        self.assertIsNotNone(runner)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = runner(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    (
                        "import sys, time;"
                        "sys.stdout.buffer.write(b'x' * 8192);"
                        "sys.stdout.buffer.flush();"
                        "time.sleep(30)"
                    ),
                ],
                cwd=root,
                env=runtime_validation.isolated_test_environment(
                    root / "state"
                ),
                timeout=5,
                maximum_output_bytes=1024,
            )

        self.assertIn("stdout", completed.output_limit_exceeded)
        self.assertLessEqual(len(completed.stdout), 1024)
        self.assertNotEqual(completed.returncode, 0)

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_bounded_process_runner_cleans_up_descendants_after_parent_exit(
        self,
    ) -> None:
        runner = runtime_validation.run_bounded_test_process
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ready = root / "descendant-ready"
            terminated = root / "descendant-terminated"
            pid_path = root / "descendant.pid"
            descendant = (
                "import signal, sys, time\n"
                "from pathlib import Path\n"
                f"ready = Path({str(ready)!r})\n"
                f"terminated = Path({str(terminated)!r})\n"
                "def stop(signum, frame):\n"
                "    terminated.write_text('yes', encoding='utf-8')\n"
                "    raise SystemExit(0)\n"
                "signal.signal(signal.SIGTERM, stop)\n"
                "ready.write_text('yes', encoding='utf-8')\n"
                "time.sleep(30)\n"
            )
            parent = (
                "import subprocess, sys, time\n"
                "from pathlib import Path\n"
                f"ready = Path({str(ready)!r})\n"
                f"pid_path = Path({str(pid_path)!r})\n"
                f"child = subprocess.Popen([sys.executable, '-I', '-c', {descendant!r}])\n"
                "pid_path.write_text(str(child.pid), encoding='utf-8')\n"
                "deadline = time.monotonic() + 5\n"
                "while not ready.is_file() and time.monotonic() < deadline:\n"
                "    time.sleep(0.01)\n"
                "raise SystemExit(0 if ready.is_file() else 2)\n"
            )

            try:
                completed = runner(
                    [sys.executable, "-I", "-c", parent],
                    cwd=root,
                    env=runtime_validation.isolated_test_environment(
                        root / "state"
                    ),
                    timeout=10,
                )

                self.assertEqual(completed.returncode, 0)
                self.assertTrue(terminated.is_file())
            finally:
                if pid_path.is_file():
                    try:
                        os.kill(
                            int(pid_path.read_text(encoding="utf-8")),
                            signal.SIGKILL,
                        )
                    except ProcessLookupError:
                        pass

    @unittest.skipUnless(os.name == "posix", "requires POSIX process groups")
    def test_bounded_process_runner_cleans_up_stdio_detached_descendants(
        self,
    ) -> None:
        runner = runtime_validation.run_bounded_test_process
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ready = root / "detached-ready"
            terminated = root / "detached-terminated"
            pid_path = root / "detached.pid"
            descendant = (
                "import signal, time\n"
                "from pathlib import Path\n"
                f"ready = Path({str(ready)!r})\n"
                f"terminated = Path({str(terminated)!r})\n"
                "def stop(signum, frame):\n"
                "    terminated.write_text('yes', encoding='utf-8')\n"
                "    raise SystemExit(0)\n"
                "signal.signal(signal.SIGTERM, stop)\n"
                "ready.write_text('yes', encoding='utf-8')\n"
                "time.sleep(30)\n"
            )
            parent = (
                "import subprocess, sys, time\n"
                "from pathlib import Path\n"
                f"ready = Path({str(ready)!r})\n"
                f"pid_path = Path({str(pid_path)!r})\n"
                "child = subprocess.Popen(\n"
                f"    [sys.executable, '-I', '-c', {descendant!r}],\n"
                "    stdin=subprocess.DEVNULL,\n"
                "    stdout=subprocess.DEVNULL,\n"
                "    stderr=subprocess.DEVNULL,\n"
                ")\n"
                "pid_path.write_text(str(child.pid), encoding='utf-8')\n"
                "deadline = time.monotonic() + 5\n"
                "while not ready.is_file() and time.monotonic() < deadline:\n"
                "    time.sleep(0.01)\n"
                "raise SystemExit(0 if ready.is_file() else 2)\n"
            )

            try:
                completed = runner(
                    [sys.executable, "-I", "-c", parent],
                    cwd=root,
                    env=runtime_validation.isolated_test_environment(
                        root / "state"
                    ),
                    timeout=10,
                )

                self.assertEqual(completed.returncode, 0)
                self.assertTrue(terminated.is_file())
            finally:
                if pid_path.is_file():
                    try:
                        os.kill(
                            int(pid_path.read_text(encoding="utf-8")),
                            signal.SIGKILL,
                        )
                    except ProcessLookupError:
                        pass

    def test_sitecustomize_from_caller_pythonpath_cannot_skip_suite_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "tests" / "runtime" / "alpha"
            suite.mkdir(parents=True)
            executed = root / "test-executed"
            (suite / "test_alpha.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(executed)!r}).write_text('yes', encoding='utf-8')\n"
                "def test_execution():\n    assert True\n",
                encoding="utf-8",
            )
            injected = root / "injected"
            injected.mkdir()
            (injected / "sitecustomize.py").write_text(
                "import os\nos._exit(0)\n",
                encoding="utf-8",
            )

            with (
                patch.dict(
                    runtime_validation.os.environ,
                    {"PYTHONPATH": str(injected)},
                    clear=False,
                ),
                redirect_stdout(StringIO()),
            ):
                result = runtime_validation.run_runtime_validation(root)

            self.assertEqual(result, 0)
            self.assertEqual(executed.read_text(encoding="utf-8"), "yes")

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
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(output),
            ):
                run_process.side_effect = (
                    OSError("pytest process unavailable"),
                    SimpleNamespace(returncode=0),
                )
                try:
                    result = runtime_validation.run_runtime_validation(root)
                except OSError as error:
                    self.fail(f"runtime validation leaked a process error: {error}")

        self.assertEqual(result, 1)
        self.assertEqual(run_process.call_count, 2)
        self.assertIn(
            "Runtime suite alpha: FAILED (pytest process unavailable)",
            output.getvalue(),
        )
        self.assertIn(
            "validate runtime: FAILED (1 of 2 suites failed)",
            output.getvalue(),
        )

    def test_runtime_suite_timeout_fails_without_retrying(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "tests" / "runtime" / "alpha"
            suite.mkdir(parents=True)
            (suite / "test_alpha.py").write_text("", encoding="utf-8")
            output = StringIO()

            with (
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(output),
            ):
                run_process.side_effect = TimeoutExpired(
                    cmd=["pytest"],
                    timeout=runtime_validation.RUNTIME_SUITE_TIMEOUT_SECONDS,
                )
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 1)
        self.assertEqual(run_process.call_count, 1)
        self.assertIn("exceeded 300s timeout", output.getvalue())

    def test_runtime_validation_enforces_one_aggregate_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime_root = root / "tests" / "runtime"
            for name in ("alpha", "beta"):
                suite = runtime_root / name
                suite.mkdir(parents=True, exist_ok=True)
                (suite / f"test_{name}.py").write_text("", encoding="utf-8")
            output = StringIO()

            with (
                patch.object(
                    runtime_validation.time,
                    "monotonic",
                    side_effect=(0.0, 899.0),
                ),
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(output),
            ):
                run_process.side_effect = TimeoutExpired(
                    cmd=["pytest"],
                    timeout=1,
                )
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 1)
        self.assertEqual(run_process.call_count, 1)
        self.assertEqual(run_process.call_args.kwargs["timeout"], 1.0)
        self.assertIn("aggregate runtime validation exceeded", output.getvalue())

    def test_snapshot_materializes_contained_skill_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / "tests" / "runtime" / "alpha"
            suite.mkdir(parents=True)
            (suite / "test_alpha.py").write_text("", encoding="utf-8")
            assets = root / "skills" / "workflows" / "alpha" / "assets"
            assets.mkdir(parents=True)
            target = assets / "source.txt"
            target.write_text("contained asset\n", encoding="utf-8")
            (assets / "linked.txt").symlink_to(target.name)
            observed = False

            def inspect_snapshot(*args, **kwargs):
                nonlocal observed
                linked = (
                    Path(kwargs["cwd"])
                    / "skills"
                    / "workflows"
                    / "alpha"
                    / "assets"
                    / "linked.txt"
                )
                self.assertTrue(linked.is_file())
                self.assertFalse(linked.is_symlink())
                self.assertEqual(
                    linked.read_text(encoding="utf-8"),
                    "contained asset\n",
                )
                observed = True
                return SimpleNamespace(returncode=0)

            with (
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                    side_effect=inspect_snapshot,
                ),
                redirect_stdout(StringIO()),
            ):
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 0)
        self.assertTrue(observed)

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

    def test_symlinked_tests_parent_cannot_supply_runtime_suites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repository"
            outside = Path(directory) / "outside"
            root.mkdir()
            suite = outside / "runtime" / "external"
            suite.mkdir(parents=True)
            (suite / "test_external.py").write_text(
                "def test_external(): pass\n",
                encoding="utf-8",
            )
            (root / "tests").symlink_to(outside, target_is_directory=True)
            output = StringIO()

            with (
                patch.object(
                    runtime_validation,
                    "run_bounded_test_process",
                ) as run_process,
                redirect_stdout(output),
            ):
                result = runtime_validation.run_runtime_validation(root)

        self.assertEqual(result, 1)
        run_process.assert_not_called()
        self.assertIn("non-symlink directory contained", output.getvalue())

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
                    patch.object(
                        runtime_validation,
                        "run_bounded_test_process",
                    ) as run_process,
                    redirect_stdout(output),
                ):
                    result = runtime_validation.run_runtime_validation(root)

                self.assertEqual(result, 1)
                run_process.assert_not_called()
                self.assertIn("validate runtime: FAILED", output.getvalue())

    def test_nested_hidden_entries_and_symlinks_fail_before_pytest(self) -> None:
        builders = {
            "hidden file": lambda suite, outside: (
                suite / "nested" / ".hidden.py"
            ).write_text("", encoding="utf-8"),
            "file symlink": lambda suite, outside: (
                suite / "nested" / "linked.py"
            ).symlink_to(outside / "outside.py"),
            "directory symlink": lambda suite, outside: (
                suite / "nested" / "linked"
            ).symlink_to(outside, target_is_directory=True),
            "broken symlink": lambda suite, outside: (
                suite / "nested" / "broken"
            ).symlink_to(outside / "missing"),
            "cache-named symlink": lambda suite, outside: (
                suite / "nested" / "__pycache__"
            ).symlink_to(outside, target_is_directory=True),
        }
        for label, build in builders.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                suite = root / "tests" / "runtime" / "alpha"
                nested = suite / "nested"
                outside = root / "outside"
                nested.mkdir(parents=True)
                outside.mkdir()
                (suite / "test_alpha.py").write_text("", encoding="utf-8")
                (outside / "outside.py").write_text("", encoding="utf-8")
                build(suite, outside)

                with (
                    patch.object(
                        runtime_validation,
                        "run_bounded_test_process",
                    ) as run_process,
                    redirect_stdout(StringIO()),
                ):
                    result = runtime_validation.run_runtime_validation(root)

                self.assertEqual(result, 1)
                run_process.assert_not_called()

    def test_snapshot_file_swap_to_fifo_is_rejected_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test_file = root / "tests" / "runtime" / "alpha" / "test_alpha.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_alpha(): pass\n", encoding="utf-8")
            parked = test_file.with_name("test_alpha.parked")
            real_open = runtime_validation.os.open
            replaced = False

            def replace_with_fifo(path, flags, *args, **kwargs):
                nonlocal replaced
                if (
                    path == test_file.name
                    and kwargs.get("dir_fd") is not None
                    and not replaced
                ):
                    test_file.rename(parked)
                    os.mkfifo(test_file)
                    replaced = True
                return real_open(path, flags, *args, **kwargs)

            with (
                patch.object(
                    runtime_validation.os,
                    "open",
                    side_effect=replace_with_fifo,
                ),
                self.assertRaisesRegex(
                    runtime_validation.RuntimeTestLayoutError,
                    "changed while being opened",
                ),
                runtime_validation.materialized_test_repository(root),
            ):
                pass

            self.assertTrue(replaced)

    def test_runtime_discovery_enforces_entry_and_depth_limits(self) -> None:
        for limit_name, limit_value in (
            ("MAXIMUM_TEST_TREE_ENTRIES", 2),
            ("MAXIMUM_TEST_TREE_DEPTH", 0),
        ):
            with self.subTest(limit=limit_name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                nested = root / "tests" / "runtime" / "alpha" / "nested"
                nested.mkdir(parents=True)
                (nested / "test_alpha.py").write_text(
                    "def test_alpha(): pass\n",
                    encoding="utf-8",
                )

                with (
                    patch.object(runtime_validation, limit_name, limit_value),
                    patch.object(
                        runtime_validation,
                        "run_bounded_test_process",
                    ) as run_process,
                    redirect_stdout(StringIO()),
                ):
                    result = runtime_validation.run_runtime_validation(root)

                self.assertEqual(result, 1)
                run_process.assert_not_called()


class RuntimeTestDependencyTests(unittest.TestCase):
    def test_pytest_and_http_mock_dependencies_are_exactly_pinned(self) -> None:
        requirements = (REPOSITORY_ROOT / "requirements-test.txt").read_text(
            encoding="utf-8"
        )

        self.assertIn("pytest==9.1.1", requirements.splitlines())
        self.assertIn("responses==0.26.2", requirements.splitlines())


if __name__ == "__main__":
    unittest.main()
