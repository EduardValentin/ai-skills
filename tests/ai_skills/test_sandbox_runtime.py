from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

from scripts.ai_skills_lib.sandbox_runtime import (
    CATALOG_RENAME_PROBE_SCRIPT,
    CaseWorkspace,
    CommandResult,
    EvalRuntimeManifest,
    IPC_CLEANUP_SCRIPT,
    ManifestError,
    SandboxRuntime,
    SandboxRuntimeError,
    SubprocessRunner,
    network_policy_sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "config" / "eval-runtime.json"


class FakeProcessRunner:
    def __init__(self, results: list[CommandResult] | None = None, side_effect=None) -> None:
        self.results = list(results or [])
        self.side_effect = side_effect
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def run(self, argv: tuple[str, ...], *, timeout_seconds: int) -> CommandResult:
        self.calls.append((argv, timeout_seconds))
        if self.side_effect is not None:
            override = self.side_effect(argv)
            if isinstance(override, CommandResult):
                return override
        if argv[:3] == ("sbx", "exec", "--user"):
            if len(argv) > 5 and argv[3] == "root" and argv[5] == "pgrep":
                return CommandResult(returncode=1, stdout="", stderr="")
            if len(argv) > 5 and argv[3] == "root" and argv[5] == "getent":
                return CommandResult(returncode=2, stdout="", stderr="")
            if argv[3] == "root" or (len(argv) > 5 and argv[5] == "test"):
                return completed()
            if (
                len(argv) > 7
                and argv[5:7] == ("python3", "-c")
                and argv[7] == CATALOG_RENAME_PROBE_SCRIPT
            ):
                return completed()
        if argv == ("sbx", "ls", "--json"):
            previous = self.calls[-2][0][:2] if len(self.calls) > 1 else ()
            if previous not in (("sbx", "create"), ("sbx", "rm")) and (
                not self.results or not self._is_sandbox_list(self.results[0])
            ):
                return completed(json.dumps({"sandboxes": []}))
        if not self.results:
            raise AssertionError(f"unexpected process call: {argv!r}")
        return self.results.pop(0)

    @staticmethod
    def _is_sandbox_list(result: CommandResult) -> bool:
        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError):
            return False
        return isinstance(payload, dict) and isinstance(payload.get("sandboxes"), list)


def completed(stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr=stderr)


def balanced_policy_payload() -> dict[str, object]:
    rule_ids = (
        "default-ai-services",
        "default-package-managers",
        "default-code-and-containers",
        "default-cloud-infrastructure",
        "default-os-packages",
        "default-cert-validation",
    )
    return {
        "rules": [
            {
                "id": rule_id,
                "policy_id": "local-policy",
                "scope": "global",
                "applies_to": "all",
                "resource_type": "network",
                "decision": "allow",
                "origin": "local",
                "status": "active",
                "resources": (
                    ["**.openai.com:443", "chatgpt.com:443", "**.chatgpt.com:443"]
                    if rule_id == "default-ai-services"
                    else [f"{rule_id}.invalid:443"]
                ),
            }
            for rule_id in rule_ids
        ]
    }


def valid_preflight_results() -> list[CommandResult]:
    return [
        completed("sbx version: v0.35.0 01e01520456e4126a9653471e7072e4d9b280321\n"),
        completed(
            json.dumps(
                {
                    "version": "1.0",
                    "checks": [{"name": "Authentication", "status": "pass"}],
                    "summary": {"pass": 1, "warn": 0, "fail": 0, "skip": 0},
                }
            )
        ),
        completed("SCOPE SERVICE SECRET\n(global) openai (oauth configured)\n"),
        completed(
            json.dumps(
                {
                    "images": [
                        {
                            "id": "943c52aa48a4",
                            "repository": "docker.io/docker/sandbox-templates",
                            "tag": "codex-docker",
                        }
                    ]
                }
            )
        ),
        completed(json.dumps(balanced_policy_payload())),
    ]


class EvalRuntimeManifestTests(unittest.TestCase):
    def test_loads_the_pinned_repository_manifest(self) -> None:
        manifest = EvalRuntimeManifest.load(MANIFEST_PATH)

        self.assertEqual(manifest.sbx.version, "0.35.0")
        self.assertEqual(manifest.codex.version, "0.142.4")
        self.assertEqual(manifest.sbx.network_policy.preset, "balanced")
        self.assertEqual(manifest.mockserver.maximum_expected_requests, 128)
        self.assertEqual(
            manifest.sbx.network_policy.rules_sha256,
            "bfda7227d418d394822f5747f3d030884a5c114741441c6fb3870a5235e904e2",
        )
        self.assertEqual(
            manifest.mockserver.bundled_default_ca_sha256,
            "26fc755116841c1c31ff004fb6c727b00de6d4b57b77557e09f2eaaae022b846",
        )
        self.assertEqual(manifest.workers.default_concurrency, 2)
        self.assertEqual(manifest.workers.maximum_concurrency, 4)

    def test_rejects_unknown_keys(self) -> None:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        raw["unexpected"] = True

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "unknown keys"):
                EvalRuntimeManifest.load(path)

    def test_rejects_a_floating_template_reference(self) -> None:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        raw["codex"]["template"] = "docker.io/docker/sandbox-templates:codex-docker"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "digest-bound"):
                EvalRuntimeManifest.load(path)

    def test_rejects_a_floating_mockserver_image(self) -> None:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        raw["fixtures"]["mockserver"].pop("digest")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "digest"):
                EvalRuntimeManifest.load(path)

    def test_rejects_weakened_mockserver_isolation_policy(self) -> None:
        changes = (
            (("image",), "untrusted/mockserver"),
            (("bind",), "all-interfaces"),
            (("reuse_scope",), "global"),
            (("ca_scope",), "global"),
            (("reset_per_case",), ["expectations"]),
            (("schema", "release"), "mockserver-latest"),
            (("schema", "source"), "https://example.invalid/schema.json"),
            (("schema", "path"), "/tmp/expectations.schema.json"),
        )
        for keys, value in changes:
            with self.subTest(keys=keys):
                raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
                target = raw["fixtures"]["mockserver"]
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value

                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "runtime.json"
                    path.write_text(json.dumps(raw), encoding="utf-8")
                    with self.assertRaisesRegex(ManifestError, "mockserver"):
                        EvalRuntimeManifest.load(path)

    def test_rejects_invalid_concurrency(self) -> None:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        raw["workers"]["maximum_concurrency"] = 5

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "maximum_concurrency"):
                EvalRuntimeManifest.load(path)


class SubprocessRunnerTests(unittest.TestCase):
    def test_caps_combined_captured_output_without_using_a_shell(self) -> None:
        runner = SubprocessRunner(maximum_output_bytes=100)

        result = runner.run(
            (
                sys.executable,
                "-c",
                "import sys; print('o' * 200); print('e' * 200, file=sys.stderr)",
            ),
            timeout_seconds=5,
        )

        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout.encode()), 50)
        self.assertLessEqual(len(result.stderr.encode()), 50)

    def test_kills_a_timed_out_process_and_preserves_bounded_partial_output(self) -> None:
        runner = SubprocessRunner(maximum_output_bytes=1000)

        result = runner.run(
            (
                sys.executable,
                "-c",
                "import sys,time; print('partial', flush=True); time.sleep(10)",
            ),
            timeout_seconds=1,
        )

        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, 124)
        self.assertIn("partial", result.stdout)


class SandboxRuntimeTests(unittest.TestCase):
    def test_ipc_cleanup_script_is_valid_python(self) -> None:
        compile(IPC_CLEANUP_SCRIPT, "<ipc-cleanup>", "exec")

    def test_ipc_cleanup_script_rejects_missing_sysv_table(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc_root, queue_root = self._ipc_inspection_fixture(Path(temporary))
            (proc_root / "sysvipc" / "sem").unlink()

            result = self._run_ipc_cleanup_script(proc_root, queue_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SysV IPC inspection", result.stderr)

    def test_ipc_cleanup_script_rejects_plain_mqueue_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc_root, queue_root = self._ipc_inspection_fixture(
                Path(temporary),
                mqueue_filesystem="tmpfs",
            )

            result = self._run_ipc_cleanup_script(proc_root, queue_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mqueue inspection", result.stderr)

    def test_ipc_cleanup_script_rejects_sysv_object_created_by_retiring_uid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc_root, queue_root = self._ipc_inspection_fixture(Path(temporary))
            (proc_root / "sysvipc" / "msg").write_text(
                "msqid uid cuid\n987654 12345 424242\n",
                encoding="utf-8",
            )

            result = self._run_ipc_cleanup_script(proc_root, queue_root)

        self.assertNotEqual(result.returncode, 0)

    def test_ipc_cleanup_script_accepts_complete_empty_inspection_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proc_root, queue_root = self._ipc_inspection_fixture(Path(temporary))

            result = self._run_ipc_cleanup_script(proc_root, queue_root)

        self.assertEqual(result.returncode, 0, result.stderr)

    @staticmethod
    def _run_ipc_cleanup_script(
        proc_root: Path,
        queue_root: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (
                sys.executable,
                "-c",
                IPC_CLEANUP_SCRIPT,
                "424242",
                str(proc_root),
                str(queue_root),
            ),
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _ipc_inspection_fixture(
        root: Path,
        *,
        mqueue_filesystem: str = "mqueue",
    ) -> tuple[Path, Path]:
        proc_root = root / "proc"
        sysvipc_root = proc_root / "sysvipc"
        sysvipc_root.mkdir(parents=True)
        for table, identifier in (("shm", "shmid"), ("msg", "msqid"), ("sem", "semid")):
            (sysvipc_root / table).write_text(
                f"{identifier} uid cuid\n",
                encoding="utf-8",
            )
        queue_root = root / "mqueue"
        queue_root.mkdir()
        mountinfo = proc_root / "self" / "mountinfo"
        mountinfo.parent.mkdir()
        mountinfo.write_text(
            f"36 25 0:32 / {queue_root} rw - {mqueue_filesystem} mqueue rw\n",
            encoding="utf-8",
        )
        return proc_root, queue_root

    def setUp(self) -> None:
        manifest = EvalRuntimeManifest.load(MANIFEST_PATH)
        policy = replace(
            manifest.sbx.network_policy,
            rules_sha256=network_policy_sha256(balanced_policy_payload()),
        )
        self.manifest = replace(manifest, sbx=replace(manifest.sbx, network_policy=policy))

    def test_rejects_result_or_staging_roots_that_contain_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            ancestor = REPOSITORY_ROOT.parent
            for results_root, staging_root in (
                (ancestor, Path(state) / "workers"),
                (Path(state) / "results", ancestor),
            ):
                with self.subTest(results_root=results_root, staging_root=staging_root):
                    with self.assertRaisesRegex(SandboxRuntimeError, "repository"):
                        SandboxRuntime(
                            manifest=self.manifest,
                            process=FakeProcessRunner(),
                            repository_root=REPOSITORY_ROOT,
                            results_root=results_root,
                            staging_root=staging_root,
                            invocation_id="unit-test",
                            max_concurrency=1,
                        )

    def test_preflight_uses_only_pinned_host_commands(self) -> None:
        process = FakeProcessRunner(valid_preflight_results())
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

            report = runtime.preflight()

        self.assertTrue(report.available)
        self.assertEqual(
            [call[0] for call in process.calls],
            [
                ("sbx", "version"),
                ("sbx", "diagnose", "--output", "json"),
                ("sbx", "secret", "ls", "-g", "--service", "openai"),
                ("sbx", "template", "ls", "--json"),
                ("sbx", "policy", "ls", "--json", "--type", "network"),
            ],
        )

    def test_preflight_rejects_a_template_digest_mismatch(self) -> None:
        results = valid_preflight_results()
        results[3] = completed(
            json.dumps(
                {
                    "images": [
                        {
                            "id": "000000000000",
                            "repository": "docker.io/docker/sandbox-templates",
                            "tag": "codex-docker",
                        }
                    ]
                }
            )
        )
        process = FakeProcessRunner(results)
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

            report = runtime.preflight()

        self.assertFalse(report.available)
        self.assertIn("template", report.failure or "")

    def test_preflight_rejects_an_invalid_short_template_id(self) -> None:
        results = valid_preflight_results()
        results[3] = completed(
            json.dumps(
                {
                    "images": [
                        {
                            "id": "9",
                            "repository": "docker.io/docker/sandbox-templates",
                            "tag": "codex-docker",
                        }
                    ]
                }
            )
        )
        process = FakeProcessRunner(results)
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

            report = runtime.preflight()

        self.assertFalse(report.available)
        self.assertIn("template", report.failure or "")

    def test_preflight_rejects_a_nonpassing_named_diagnostic(self) -> None:
        results = valid_preflight_results()
        results[1] = completed(
            json.dumps(
                {
                    "version": "1.0",
                    "checks": [{"name": "Authentication", "status": "fail"}],
                    "summary": {"pass": 1, "warn": 0, "fail": 0, "skip": 0},
                }
            )
        )
        process = FakeProcessRunner(results)
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

            report = runtime.preflight()

        self.assertFalse(report.available)
        self.assertIn("diagnostic", report.failure or "")

    def test_preflight_rejects_an_unwritable_result_root(self) -> None:
        process = FakeProcessRunner(valid_preflight_results())
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

            with mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.os.open",
                side_effect=PermissionError("result root is read-only"),
            ):
                report = runtime.preflight()

        self.assertFalse(report.available)
        self.assertIn("result root", report.failure or "")

    def test_preflight_rejects_an_incomplete_balanced_policy(self) -> None:
        results = valid_preflight_results()
        results[4] = completed(
            json.dumps(
                {
                    "rules": [
                        {
                            "id": "default-ai-services",
                            "policy_id": "local-policy",
                            "resource_type": "network",
                            "decision": "allow",
                            "origin": "local",
                            "status": "active",
                            "resources": ["evil-openai.com:443"],
                        }
                    ]
                }
            )
        )
        process = FakeProcessRunner(results)
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

            report = runtime.preflight()

        self.assertFalse(report.available)
        self.assertIn("balanced", report.failure or "")

    def test_preflight_rejects_an_extra_balanced_policy_resource(self) -> None:
        results = valid_preflight_results()
        payload = balanced_policy_payload()
        payload["rules"][0]["resources"].append("**:443")
        results[4] = completed(json.dumps(payload))
        process = FakeProcessRunner(results)
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

            report = runtime.preflight()

        self.assertFalse(report.available)
        self.assertIn("immutable pin", report.failure or "")

    def test_preflight_reports_a_missing_sbx_binary_as_unavailable(self) -> None:
        def missing_binary(_argv: tuple[str, ...]) -> None:
            raise FileNotFoundError("sbx was not found")

        process = FakeProcessRunner(side_effect=missing_binary)
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

            report = runtime.preflight()

        self.assertFalse(report.available)
        self.assertIn("not found", report.failure or "")

    def test_rejects_results_or_staging_inside_the_repository(self) -> None:
        process = FakeProcessRunner()

        with self.assertRaisesRegex(SandboxRuntimeError, "outside the repository"):
            SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=REPOSITORY_ROOT / "results",
                staging_root=REPOSITORY_ROOT.parent / "workers",
                invocation_id="unit-test",
                max_concurrency=2,
            )

    def test_creates_bounded_role_specific_workers_and_reuses_them(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "judge-id", "name": "ai-skills-unit-test-judge-1"}]})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )

            first_actor = runtime.acquire_worker("actor")
            second_actor = runtime.acquire_worker("actor")
            judge = runtime.acquire_worker("judge")

        self.assertIs(first_actor, second_actor)
        self.assertNotEqual(first_actor.name, judge.name)
        create_calls = [argv for argv, _ in process.calls if argv[:2] == ("sbx", "create")]
        self.assertEqual(len(create_calls), 2)
        self.assertIn("--cpus", create_calls[0])
        self.assertIn("--memory", create_calls[0])
        self.assertIn(self.manifest.codex.template, create_calls[0])

    def test_worker_leases_apply_one_global_limit_across_actor_and_judge_pools(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "judge-id", "name": "ai-skills-unit-test-judge-1"}]})),
            ]
        )
        judge_acquired = threading.Event()
        release_judge = threading.Event()
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )

            def lease_judge() -> None:
                with runtime.lease_worker("judge"):
                    judge_acquired.set()
                    release_judge.wait(timeout=2)

            with runtime.lease_worker("actor"):
                thread = threading.Thread(target=lease_judge)
                thread.start()
                time.sleep(0.05)
                self.assertFalse(judge_acquired.is_set())

            self.assertTrue(judge_acquired.wait(timeout=1))
            release_judge.set()
            thread.join(timeout=1)

        self.assertFalse(thread.is_alive())

    def test_cleanup_removes_only_invocation_owned_workers_and_verifies_absence(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "unrelated", "name": "personal-sandbox"}]})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            runtime.acquire_worker("actor")

            runtime.close()

        self.assertIn(
            (("sbx", "rm", "--force", "actor-id"), self.manifest.limits.preflight_timeout_seconds),
            process.calls,
        )
        self.assertNotIn("personal-sandbox", [part for argv, _ in process.calls for part in argv])

    def test_close_retries_host_cleanup_without_removing_the_sandbox_twice(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
                completed(),
                completed(json.dumps({"sandboxes": []})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            original_rmtree = __import__("shutil").rmtree
            failed = False

            def fail_once(path):
                nonlocal failed
                if Path(path) == worker.host_root and not failed:
                    failed = True
                    raise OSError("host cleanup failed")
                return original_rmtree(path)

            with mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.shutil.rmtree",
                side_effect=fail_once,
            ):
                with self.assertRaisesRegex(OSError, "host cleanup"):
                    runtime.close()
                runtime.close()

            self.assertFalse(worker.host_root.exists())

        remove_calls = [argv for argv, _ in process.calls if argv[:2] == ("sbx", "rm")]
        self.assertEqual(len(remove_calls), 1)

    def test_close_retries_only_absence_verification_after_successful_removal(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {
                                    "id": "actor-id",
                                    "name": "ai-skills-unit-test-actor-1",
                                }
                            ]
                        }
                    )
                ),
                completed(),
                CommandResult(returncode=1, stdout="", stderr="list unavailable"),
                completed(json.dumps({"sandboxes": []})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            runtime.acquire_worker("actor")

            with self.assertRaisesRegex(SandboxRuntimeError, "list unavailable"):
                runtime.close()
            runtime.close()

        purge_calls = [
            argv
            for argv, _ in process.calls
            if argv[:5] == ("sbx", "exec", "--user", "root", "actor-id")
            and len(argv) > 5
            and argv[5] == "find"
        ]
        remove_calls = [argv for argv, _ in process.calls if argv[:2] == ("sbx", "rm")]
        self.assertEqual(len(purge_calls), 1)
        self.assertEqual(len(remove_calls), 1)

    def test_failed_create_does_not_remove_an_unproven_same_named_sandbox(self) -> None:
        process = FakeProcessRunner(
            [
                completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {
                                    "id": "unrelated-id",
                                    "name": "ai-skills-unit-test-actor-1",
                                }
                            ]
                        }
                    )
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )

            with self.assertRaisesRegex(SandboxRuntimeError, "already exists"):
                runtime.acquire_worker("actor")

        self.assertFalse(any(argv[:2] == ("sbx", "rm") for argv, _ in process.calls))

    def test_create_timeout_removes_sandbox_when_name_was_proven_absent(self) -> None:
        sandbox_name = "ai-skills-unit-test-actor-1"
        process = FakeProcessRunner(
            [
                completed(json.dumps({"sandboxes": []})),
                CommandResult(
                    returncode=124,
                    stdout="",
                    stderr="create timed out",
                    timed_out=True,
                ),
                completed(
                    json.dumps(
                        {"sandboxes": [{"id": "actor-id", "name": sandbox_name}]}
                    )
                ),
                completed(),
                completed(json.dumps({"sandboxes": []})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )

            with self.assertRaises(SandboxRuntimeError):
                runtime.acquire_worker("actor")

        self.assertIn(
            ("sbx", "rm", "--force", "actor-id"),
            [argv for argv, _ in process.calls],
        )

    def test_create_timeout_keeps_unresolved_cleanup_retryable(self) -> None:
        sandbox_name = "ai-skills-unit-test-actor-1"
        process = FakeProcessRunner(
            [
                CommandResult(
                    returncode=124,
                    stdout="",
                    stderr="create timed out",
                    timed_out=True,
                ),
                CommandResult(returncode=1, stdout="", stderr="list unavailable"),
                completed(
                    json.dumps(
                        {"sandboxes": [{"id": "actor-id", "name": sandbox_name}]}
                    )
                ),
                completed(),
                completed(json.dumps({"sandboxes": []})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )

            with self.assertRaisesRegex(SandboxRuntimeError, "cleanup is pending"):
                runtime.acquire_worker("actor")
            host_root = Path(state) / "workers" / sandbox_name
            self.assertTrue(host_root.exists())

            runtime.close()

        self.assertIn(
            ("sbx", "rm", "--force", "actor-id"),
            [argv for argv, _ in process.calls],
        )

    def test_case_reset_replaces_every_actor_visible_directory(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            first = runtime.prepare_case(worker, "case-one")
            (first.home / "stale-home").write_text("stale", encoding="utf-8")
            (first.workspace / "stale-workspace").write_text("stale", encoding="utf-8")
            (first.skills / "stale-skill").mkdir()

            second = runtime.prepare_case(worker, "case-two")

            self.assertIsInstance(second, CaseWorkspace)
            self.assertEqual(second.case_id, "case-two")
            self.assertNotEqual(first.uid, second.uid)
            self.assertNotEqual(first.user_name, second.user_name)
            self.assertFalse((second.root / "home" / "stale-home").exists())
            self.assertFalse((second.root / "workspace" / "stale-workspace").exists())
            self.assertEqual(list(second.skills.iterdir()), [])
            self.assertEqual(
                {path.name for path in second.root.iterdir()},
                {"home", "codex-home", "tmp", "workspace", "bootstrap"},
            )
            self.assertEqual(second.skills.parent, second.codex_home)

        root_commands = [
            argv[5:]
            for argv, _ in process.calls
            if argv[:5] == ("sbx", "exec", "--user", "root", "actor-id")
        ]
        useradd_commands = [argv for argv in root_commands if argv[:1] == ("useradd",)]
        self.assertEqual(len(useradd_commands), 2)
        self.assertTrue(all("--user-group" in argv for argv in useradd_commands))
        self.assertIn(("userdel", first.user_name), root_commands)
        self.assertIn(("groupdel", first.user_name), root_commands)
        self.assertIn(("getent", "passwd", first.user_name), root_commands)
        self.assertIn(("getent", "group", first.user_name), root_commands)
        self.assertTrue(
            any(
                command[:1] == ("find",)
                and str(first.root) in command
                and "-mindepth" in command
                for command in root_commands
            )
        )

    def test_case_identity_cannot_access_worker_control_state(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}
                            ]
                        }
                    )
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "case-one")

        case_commands = [
            argv[5:]
            for argv, _ in process.calls
            if argv[:5] == ("sbx", "exec", "--user", case.user_name, "actor-id")
        ]
        self.assertIn(("test", "!", "-r", "/var/run/docker.sock"), case_commands)
        self.assertIn(("test", "!", "-w", "/var/run/docker.sock"), case_commands)
        self.assertIn(("test", "!", "-r", "/home/agent/.codex/auth.json"), case_commands)

    def test_case_layout_is_complete_before_identity_ownership_changes(self) -> None:
        missing_at_chown: list[Path] = []

        def inspect_chown(argv: tuple[str, ...]) -> None:
            if argv[:5] != ("sbx", "exec", "--user", "root", "actor-id"):
                return
            command = argv[5:]
            if command[:2] != ("chown", "-R"):
                return
            case_root = Path(command[-1])
            expected = (
                case_root / "home" / ".config",
                case_root / "home" / ".cache",
                case_root / "home" / ".local" / "share",
                case_root / "home" / ".local" / "state",
                case_root / "home" / ".gnupg",
                case_root / "tmp" / "runtime",
            )
            missing_at_chown.extend(path for path in expected if not path.is_dir())

        process = FakeProcessRunner(
            [
                completed(),
                completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}
                            ]
                        }
                    )
                ),
            ],
            side_effect=inspect_chown,
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")

            runtime.prepare_case(worker, "case-one")

        self.assertEqual(missing_at_chown, [])

    def test_executes_direct_arguments_with_case_scoped_environment(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
                completed("result"),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "case-one")

            result = runtime.execute(
                worker,
                case,
                ("printf", "%s", "hello world"),
                timeout_seconds=30,
                environment={"EXAMPLE": "value with spaces"},
            )

        self.assertEqual(result.stdout, "result")
        argv, timeout = process.calls[-1]
        self.assertEqual(timeout, 30)
        self.assertEqual(argv[:2], ("sbx", "exec"))
        self.assertIn(("--workdir", str(case.workspace)), tuple(zip(argv, argv[1:])))
        self.assertIn(("--env", f"HOME={case.home}"), tuple(zip(argv, argv[1:])))
        self.assertIn(("--env", f"CODEX_HOME={case.codex_home}"), tuple(zip(argv, argv[1:])))
        self.assertIn(("--env", f"TMPDIR={case.tmpdir}"), tuple(zip(argv, argv[1:])))
        self.assertIn(("--env", "EXAMPLE=value with spaces"), tuple(zip(argv, argv[1:])))
        self.assertIn(("--user", case.user_name), tuple(zip(argv, argv[1:])))
        self.assertEqual(argv[-3:], ("printf", "%s", "hello world"))
        self.assertNotIn("/bin/sh", argv)

    def test_timeout_recycles_the_worker_without_retrying_the_command(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
                CommandResult(returncode=124, stdout="partial", stderr="native timeout", timed_out=True),
                completed(),
                completed(json.dumps({"sandboxes": []})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "case-one")

            result = runtime.execute(worker, case, ("codex", "exec"), timeout_seconds=1)

        self.assertTrue(result.timed_out)
        codex_calls = [argv for argv, _ in process.calls if argv[-2:] == ("codex", "exec")]
        self.assertEqual(len(codex_calls), 1)
        self.assertIn(
            ("sbx", "rm", "--force", "actor-id"),
            [argv for argv, _ in process.calls],
        )

    def test_timeout_preserves_output_when_worker_cleanup_is_pending(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
                CommandResult(
                    returncode=124,
                    stdout="partial actor output",
                    stderr="native timeout",
                    timed_out=True,
                ),
                CommandResult(returncode=1, stdout="", stderr="remove failed"),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "case-one")

            result = runtime.execute(worker, case, ("codex", "exec"), timeout_seconds=1)

        self.assertTrue(result.timed_out)
        self.assertEqual(result.stdout, "partial actor output")
        self.assertIn("cleanup", result.lifecycle_failure or "")

    def test_worker_control_runs_as_root_and_quarantines_on_failure(self) -> None:
        def fail_control(argv: tuple[str, ...]) -> CommandResult | None:
            if argv[-1:] == ("false",):
                return CommandResult(returncode=9, stdout="", stderr="native control failure")
            return None

        process = FakeProcessRunner(
            [
                completed(),
                completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}
                            ]
                        }
                    )
                ),
                completed(),
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=fail_control,
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")

            with self.assertRaisesRegex(SandboxRuntimeError, "control"):
                runtime.run_worker_control(worker, ("false",))
            with self.assertRaisesRegex(SandboxRuntimeError, "not owned"):
                runtime.run_worker_control(worker, ("true",))

        self.assertIn(
            ("sbx", "exec", "--user", "root", "actor-id", "false"),
            [argv for argv, _ in process.calls],
        )

    def test_quiesces_case_processes_before_evidence_collection(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}
                            ]
                        }
                    )
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "case-one")

            runtime.quiesce_case(worker, case)

        commands = [argv[5:] for argv, _ in process.calls if argv[:5] == ("sbx", "exec", "--user", "root", "actor-id")]
        self.assertIn(("pkill", "-KILL", "-u", str(case.uid)), commands)
        self.assertIn(("pgrep", "-u", str(case.uid)), commands)
        ipc_commands = [
            command
            for command in commands
            if command[:2] == ("python3", "-c")
            and command[2] == IPC_CLEANUP_SCRIPT
        ]
        self.assertEqual(len(ipc_commands), 1)
        self.assertEqual(ipc_commands[0][-1], str(case.uid))

    def test_environment_rejects_unsafe_names_and_nul_values(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "case-one")

            with self.assertRaisesRegex(SandboxRuntimeError, "environment"):
                runtime.execute(
                    worker,
                    case,
                    ("true",),
                    timeout_seconds=1,
                    environment={"BAD-NAME": "value"},
                )
            for reserved in (
                "HOME",
                "CODEX_HOME",
                "TMPDIR",
                "USER",
                "LOGNAME",
                "SHELL",
                "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME",
                "XDG_DATA_HOME",
                "XDG_STATE_HOME",
                "XDG_RUNTIME_DIR",
                "SSH_AUTH_SOCK",
                "GIT_CONFIG_GLOBAL",
                "GNUPGHOME",
                "DOCKER_HOST",
            ):
                with self.subTest(reserved=reserved):
                    with self.assertRaisesRegex(SandboxRuntimeError, "reserved"):
                        runtime.execute(
                            worker,
                            case,
                            ("true",),
                            timeout_seconds=1,
                            environment={reserved: "/escape"},
                        )

    def test_initializes_only_docker_generated_proxy_state(self) -> None:
        def copy_proxy_state(argv: tuple[str, ...]) -> None:
            if argv[:2] != ("sbx", "exec") or "cp" not in argv:
                return
            target = Path(argv[-1])
            (target / "config.toml").write_text(
                'model_provider = "sandboxd"\n[model_providers.sandboxd]\nbase_url = "http://proxy"\n',
                encoding="utf-8",
            )
            (target / "auth.json").write_text(
                json.dumps({"OPENAI_API_KEY": "host-proxy-placeholder"}),
                encoding="utf-8",
            )

        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "actor-id", "name": "ai-skills-unit-test-actor-1"}]})),
                completed(),
            ],
            side_effect=copy_proxy_state,
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "case-one")

            runtime.initialize_codex_home(worker, case)

        copy_argv = next(argv for argv, _ in process.calls if "cp" in argv)
        self.assertIn("/home/agent/.codex/config.toml", copy_argv)
        self.assertIn("/home/agent/.codex/auth.json", copy_argv)

    def test_seals_the_complete_skill_catalog_against_case_user_mutation(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {
                                    "id": "actor-id",
                                    "name": "ai-skills-unit-test-actor-1",
                                }
                            ]
                        }
                    )
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "case-one")

            runtime.seal_skill_catalog(worker, case)

        commands = [argv for argv, _ in process.calls]
        self.assertIn(
            ("sbx", "exec", "--user", "root", "actor-id", "chown", "-R", "root:root", str(case.skills)),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "actor-id",
                "chown",
                "root:root",
                str(case.codex_home),
            ),
            commands,
        )
        for writable_path in (
            case.home,
            case.codex_home,
            case.tmpdir,
            case.workspace,
            case.bootstrap,
        ):
            self.assertIn(
                (
                    "sbx",
                    "exec",
                    "--user",
                    case.user_name,
                    "actor-id",
                    "test",
                    "-w",
                    str(writable_path),
                ),
                commands,
            )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "actor-id",
                "chown",
                "root:root",
                str(case.root),
            ),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "actor-id",
                "chmod",
                "0555",
                str(case.root),
            ),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "actor-id",
                "chmod",
                "1777",
                str(case.codex_home),
            ),
            commands,
        )
        self.assertIn(
            ("sbx", "exec", "--user", "root", "actor-id", "chmod", "0555", str(case.skills)),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                case.user_name,
                "actor-id",
                "test",
                "!",
                "-w",
                str(case.skills),
            ),
            commands,
        )
        rename_probes = {
            (argv[-2], argv[-1])
            for argv in commands
            if argv[:5]
            == ("sbx", "exec", "--user", case.user_name, "actor-id")
            and argv[5:7] == ("python3", "-c")
            and argv[7] == CATALOG_RENAME_PROBE_SCRIPT
        }
        self.assertEqual(
            rename_probes,
            {
                (
                    str(case.skills),
                    str(case.codex_home / ".skills-rename-probe"),
                ),
                (
                    str(case.codex_home),
                    str(case.root / ".codex-home-rename-probe"),
                ),
                (
                    str(case.root),
                    str(worker.host_root / ".case-rename-probe"),
                ),
            },
        )

    def test_case_reset_failure_quarantines_the_worker_before_cleanup(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "old-id", "name": "ai-skills-unit-test-actor-1"}]})),
                completed(),
                completed(json.dumps({"sandboxes": []})),
                completed(),
                completed(json.dumps({"sandboxes": [{"id": "new-id", "name": "ai-skills-unit-test-actor-1"}]})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )
            old_worker = runtime.acquire_worker("actor")
            runtime.prepare_case(old_worker, "first")
            original_rmtree = __import__("shutil").rmtree
            failed = False

            def fail_first_rmtree(path):
                nonlocal failed
                if not failed:
                    failed = True
                    raise OSError("reset failed")
                return original_rmtree(path)

            with mock.patch("scripts.ai_skills_lib.sandbox_runtime.shutil.rmtree", side_effect=fail_first_rmtree):
                with self.assertRaisesRegex(SandboxRuntimeError, "reset"):
                    runtime.prepare_case(old_worker, "second")

            replacement = runtime.acquire_worker("actor")

        self.assertEqual(old_worker.id, "old-id")
        self.assertEqual(replacement.id, "new-id")

    def test_identity_reconciliation_failure_verifies_the_requested_name_is_absent(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(json.dumps({"sandboxes": []})),
                completed(json.dumps({"sandboxes": []})),
            ]
        )
        with tempfile.TemporaryDirectory() as state:
            runtime = SandboxRuntime(
                manifest=self.manifest,
                process=process,
                repository_root=REPOSITORY_ROOT,
                results_root=Path(state) / "results",
                staging_root=Path(state) / "workers",
                invocation_id="unit-test",
                max_concurrency=1,
            )

            with self.assertRaisesRegex(SandboxRuntimeError, "identity"):
                runtime.acquire_worker("actor")

        self.assertEqual(
            [argv[:2] for argv, _ in process.calls],
            [("sbx", "ls"), ("sbx", "create"), ("sbx", "ls"), ("sbx", "ls")],
        )


if __name__ == "__main__":
    unittest.main()
