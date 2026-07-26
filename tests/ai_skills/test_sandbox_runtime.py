from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

from scripts.ai_skills_lib.evaluation_runtime import (
    CodexEvaluationRuntime,
    EvaluationRuntimeError,
)
from scripts.ai_skills_lib.sandbox_runtime import (
    CATALOG_RENAME_PROBE_SCRIPT,
    CASE_CGROUP_EXEC_SCRIPT,
    CASE_CGROUP_REMOVE_SCRIPT,
    CASE_CGROUP_SETUP_SCRIPT,
    CASE_CGROUP_TERMINATE_SCRIPT,
    CASE_FILESYSTEM_CLEANUP_SCRIPT,
    CASE_FILESYSTEM_PROBE_SCRIPT,
    CASE_PRIVILEGE_LOCKDOWN_SCRIPT,
    CASE_PRIVILEGE_PROBE_SCRIPT,
    CaseWorkspace,
    CommandResult,
    DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT,
    EvalRuntimeManifest,
    IPC_CLEANUP_SCRIPT,
    ManifestError,
    OWNERSHIP_MARKER_PROBE_SCRIPT,
    PROCESS_FULLY_TERMINATED,
    PUBLIC_SKILL_CATALOG_PROBE_SCRIPT,
    ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
    ProcessTerminationOutcome,
    SandboxRuntime,
    SandboxRuntimeError,
    SandboxWorker,
    SubprocessRunner,
    WORKER_MOUNT_PROTECT_SCRIPT,
    WORKER_MOUNT_RESTORE_SCRIPT,
    network_policy_sha256,
    process_termination_outcome,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPOSITORY_ROOT / "config" / "eval-runtime.json"
OWNERSHIP_MARKER_NAME = ".ai-skills-sandbox-owner"
DOCKER_CODEX_PROXY_CONFIG = """\
# Codex configuration for Docker sandbox
# This configuration enables "yolo mode" - no approvals, full access

approval_policy = "never"
sandbox_mode = "danger-full-access"
mcp_oauth_credentials_store = "file"

model_provider = "sandboxd"

[model_providers.sandboxd]
name = "Sandbox Proxy"
base_url = "https://chatgpt.com/backend-api/codex"
experimental_bearer_token = "oai-oat01-proxy-managed"
requires_openai_auth = false
"""
DOCKER_CODEX_PROXY_AUTH = '{\n  "OPENAI_API_KEY": "proxy-managed"\n}\n'


class FakeProcessRunner:
    def __init__(self, results: list[CommandResult] | None = None, side_effect=None) -> None:
        self.results = list(results or [])
        self.side_effect = side_effect
        self.calls: list[tuple[tuple[str, ...], int]] = []
        self.sandboxes: dict[str, str] = {}

    def run(self, argv: tuple[str, ...], *, timeout_seconds: int) -> CommandResult:
        self.calls.append((argv, timeout_seconds))
        if self.side_effect is not None:
            override = self.side_effect(argv)
            if isinstance(override, CommandResult):
                if argv == ("sbx", "ls", "--json"):
                    self._remember_sandbox_list(override)
                return override
        if argv[:3] == ("sbx", "exec", "--user"):
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if len(argv) > 5 and argv[3] == "root" and argv[5] == "getent":
                return CommandResult(returncode=2, stdout="", stderr="")
            if len(argv) > 6 and argv[3] == "root" and argv[5:7] == ("stat", "--format=%a"):
                return completed("700\n")
            if CASE_CGROUP_EXEC_SCRIPT in argv:
                script_index = argv.index(CASE_CGROUP_EXEC_SCRIPT)
                wrapped = argv[script_index + 3 :]
                if wrapped[:1] == ("test",) or (
                    wrapped[:2] == ("python3", "-c")
                    and len(wrapped) > 2
                    and wrapped[2]
                    in (
                        CATALOG_RENAME_PROBE_SCRIPT,
                        CASE_PRIVILEGE_PROBE_SCRIPT,
                        DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT,
                        PUBLIC_SKILL_CATALOG_PROBE_SCRIPT,
                        ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
                    )
                ):
                    return completed()
            elif argv[3] == "root":
                return completed()
            if len(argv) > 5 and argv[5] == "test":
                return completed()
            if (
                len(argv) > 7
                and argv[5:7] == ("python3", "-c")
                and argv[7]
                in (
                    CATALOG_RENAME_PROBE_SCRIPT,
                    CASE_PRIVILEGE_PROBE_SCRIPT,
                    DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT,
                    PUBLIC_SKILL_CATALOG_PROBE_SCRIPT,
                    ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
                )
            ):
                return completed()
        if argv == ("sbx", "ls", "--json"):
            previous = self.calls[-2][0][:2] if len(self.calls) > 1 else ()
            if previous not in (("sbx", "create"), ("sbx", "rm")) and (
                not self.results or not self._is_sandbox_list(self.results[0])
            ):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in self.sandboxes.items()
                            ]
                        }
                    )
                )
        if not self.results:
            raise AssertionError(f"unexpected process call: {argv!r}")
        result = self.results.pop(0)
        if argv == ("sbx", "ls", "--json"):
            self._remember_sandbox_list(result)
        return result

    @staticmethod
    def _is_sandbox_list(result: CommandResult) -> bool:
        try:
            payload = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError):
            return False
        return isinstance(payload, dict) and isinstance(payload.get("sandboxes"), list)

    def _remember_sandbox_list(self, result: CommandResult) -> None:
        if not self._is_sandbox_list(result):
            return
        payload = json.loads(result.stdout)
        self.sandboxes = {
            item["id"]: item["name"]
            for item in payload["sandboxes"]
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("name"), str)
        }


def completed(stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr=stderr)


def discard_sandbox_by_name(sandboxes: dict[str, str], name: str) -> None:
    matching_ids = [sandbox_id for sandbox_id, candidate in sandboxes.items() if candidate == name]
    if len(matching_ids) != 1:
        raise AssertionError(f"sandbox name did not resolve exactly once: {name!r}")
    sandboxes.pop(matching_ids[0])


def ownership_marker_probe_result(argv: tuple[str, ...]) -> CommandResult | None:
    if (
        len(argv) != 9
        or argv[:4] != ("sbx", "exec", "--user", "root")
        or argv[5:7] != ("python3", "-c")
        or Path(argv[8]).name != OWNERSHIP_MARKER_NAME
    ):
        return None
    marker = Path(argv[8])
    if not marker.is_file() or marker.is_symlink():
        return CommandResult(returncode=1, stdout="", stderr="")
    return completed(hashlib.sha256(marker.read_bytes()).hexdigest())


def cgroup_wrapped_case_command(argv: tuple[str, ...]) -> tuple[str, ...] | None:
    if CASE_CGROUP_EXEC_SCRIPT not in argv:
        return None
    script_index = argv.index(CASE_CGROUP_EXEC_SCRIPT)
    if len(argv) <= script_index + 3:
        return None
    return argv[script_index + 3 :]


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
        self.assertEqual(manifest.mockserver.reuse_scope, "case")
        self.assertEqual(manifest.mockserver.ca_scope, "case")
        self.assertEqual(manifest.case_isolation.writable_filesystem, "tmpfs")
        self.assertEqual(manifest.case_isolation.maximum_writable_bytes, 268435456)
        self.assertEqual(manifest.case_isolation.maximum_writable_inodes, 32768)

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

    def test_rejects_changes_to_the_pinned_case_filesystem_quota(self) -> None:
        changes = (
            ("writable_filesystem", "ext4"),
            ("maximum_writable_bytes", 268435457),
            ("maximum_writable_inodes", 32769),
        )
        for key, value in changes:
            with self.subTest(key=key):
                raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
                raw["case_isolation"][key] = value

                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "runtime.json"
                    path.write_text(json.dumps(raw), encoding="utf-8")
                    with self.assertRaisesRegex(ManifestError, "pinned tmpfs"):
                        EvalRuntimeManifest.load(path)


class SubprocessRunnerTests(unittest.TestCase):
    def test_closes_child_stdin_independently_of_the_calling_terminal(self) -> None:
        runner = SubprocessRunner(maximum_output_bytes=100)

        with mock.patch(
            "scripts.ai_skills_lib.sandbox_runtime.subprocess.Popen",
            wraps=subprocess.Popen,
        ) as popen:
            result = runner.run(
                (sys.executable, "-c", "print('complete')"),
                timeout_seconds=5,
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(popen.call_args.kwargs.get("stdin"), subprocess.DEVNULL)

    def test_popen_failure_reports_that_no_process_started(self) -> None:
        with mock.patch(
            "scripts.ai_skills_lib.sandbox_runtime.subprocess.Popen",
            side_effect=OSError("spawn failed"),
        ):
            with self.assertRaises(OSError) as raised:
                SubprocessRunner(maximum_output_bytes=100).run(
                    ("sbx", "create"),
                    timeout_seconds=5,
                )

        outcome = process_termination_outcome(raised.exception)
        self.assertEqual(
            outcome,
            ProcessTerminationOutcome(
                process_started=False,
                leader_reaped=False,
                process_group_absent=True,
                drains_stopped=True,
            ),
        )

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
        self.assertTrue(result.process_outcome.fully_terminated_and_reaped)

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

    def test_base_exception_terminates_kills_and_reaps_the_process_group(self) -> None:
        class InterruptedProcess:
            def __init__(self) -> None:
                self.pid = 424242
                self.stdout = io.BytesIO()
                self.stderr = io.BytesIO()
                self.returncode: int | None = None
                self.wait_calls = 0

            def wait(self, timeout=None):
                self.wait_calls += 1
                if self.wait_calls == 1:
                    raise KeyboardInterrupt()
                self.returncode = -signal.SIGKILL
                return self.returncode

        process = InterruptedProcess()
        runner = SubprocessRunner(maximum_output_bytes=100)
        def prove_group_absent(_pid: int, signal_number: int) -> None:
            if signal_number == 0:
                raise ProcessLookupError()

        with (
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.subprocess.Popen",
                return_value=process,
            ),
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.os.killpg",
                side_effect=prove_group_absent,
            ) as kill_group,
        ):
            with self.assertRaises(KeyboardInterrupt) as raised:
                runner.run(("sbx", "create"), timeout_seconds=5)

        signals = [call.args[1] for call in kill_group.call_args_list]
        self.assertIn(signal.SIGTERM, signals)
        self.assertIn(signal.SIGKILL, signals)
        self.assertIn(0, signals)
        self.assertGreaterEqual(process.wait_calls, 2)
        self.assertEqual(process.returncode, -signal.SIGKILL)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.stderr.closed)
        outcome = process_termination_outcome(raised.exception)
        self.assertIsNotNone(outcome)
        self.assertTrue(outcome.fully_terminated_and_reaped)

    def test_thread_setup_interruptions_still_settle_the_started_process(self) -> None:
        class Process:
            def __init__(self) -> None:
                self.pid = 424243
                self.stdout = io.BytesIO()
                self.stderr = io.BytesIO()
                self.returncode: int | None = None

            def wait(self, timeout=None):
                self.returncode = -signal.SIGKILL
                return self.returncode

        def prove_group_absent(_pid: int, signal_number: int) -> None:
            if signal_number == 0:
                raise ProcessLookupError()

        for setup_patch in ("constructor", "start"):
            with self.subTest(setup_patch=setup_patch):
                process = Process()
                patches = [
                    mock.patch(
                        "scripts.ai_skills_lib.sandbox_runtime.subprocess.Popen",
                        return_value=process,
                    ),
                    mock.patch(
                        "scripts.ai_skills_lib.sandbox_runtime.os.killpg",
                        side_effect=prove_group_absent,
                    ),
                ]
                if setup_patch == "constructor":
                    patches.append(
                        mock.patch(
                            "scripts.ai_skills_lib.sandbox_runtime.threading.Thread",
                            side_effect=KeyboardInterrupt(),
                        )
                    )
                else:
                    patches.append(
                        mock.patch(
                            "scripts.ai_skills_lib.sandbox_runtime.threading.Thread.start",
                            side_effect=KeyboardInterrupt(),
                        )
                    )
                with patches[0], patches[1], patches[2]:
                    with self.assertRaises(KeyboardInterrupt) as raised:
                        SubprocessRunner(maximum_output_bytes=100).run(
                            ("sbx", "create"),
                            timeout_seconds=5,
                        )

                outcome = process_termination_outcome(raised.exception)
                self.assertIsNotNone(outcome)
                self.assertTrue(outcome.fully_terminated_and_reaped)
                self.assertTrue(process.stdout.closed)
                self.assertTrue(process.stderr.closed)

    def test_blocked_waits_and_drains_have_bounded_incomplete_outcome(self) -> None:
        class BlockedStream:
            def read(self, _size: int) -> bytes:
                return b""

            def fileno(self) -> int:
                return 99

            def close(self) -> None:
                raise AssertionError("a live drain's buffered stream must not block cleanup")

        class BlockedProcess:
            def __init__(self) -> None:
                self.pid = 424244
                self.stdout = BlockedStream()
                self.stderr = BlockedStream()
                self.returncode = None
                self.wait_calls = 0

            def wait(self, timeout=None):
                self.wait_calls += 1
                if self.wait_calls == 1:
                    raise KeyboardInterrupt()
                raise subprocess.TimeoutExpired(("sbx", "create"), timeout)

        class BlockedThread:
            def __init__(self, *args, **kwargs) -> None:
                self.join_timeouts: list[float | None] = []

            def start(self) -> None:
                return None

            def is_alive(self) -> bool:
                return True

            def join(self, timeout=None) -> None:
                self.join_timeouts.append(timeout)

        process = BlockedProcess()
        threads = [BlockedThread(), BlockedThread()]

        def prove_group_absent(_pid: int, signal_number: int) -> None:
            if signal_number == 0:
                raise ProcessLookupError()

        with (
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.subprocess.Popen",
                return_value=process,
            ),
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.threading.Thread",
                side_effect=threads,
            ),
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.os.killpg",
                side_effect=prove_group_absent,
            ),
            mock.patch("scripts.ai_skills_lib.sandbox_runtime.os.close"),
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.PROCESS_KILL_GRACE_SECONDS",
                0.01,
            ),
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.PROCESS_DRAIN_JOIN_SECONDS",
                0.01,
            ),
        ):
            with self.assertRaises(KeyboardInterrupt) as raised:
                SubprocessRunner(maximum_output_bytes=100).run(
                    ("sbx", "create"),
                    timeout_seconds=5,
                )

        outcome = process_termination_outcome(raised.exception)
        self.assertIsNotNone(outcome)
        self.assertFalse(outcome.fully_terminated_and_reaped)
        self.assertFalse(outcome.leader_reaped)
        self.assertFalse(outcome.drains_stopped)
        self.assertLessEqual(process.wait_calls, 3)
        self.assertTrue(all(thread.join_timeouts for thread in threads))
        self.assertTrue(
            all(
                timeout is not None
                for thread in threads
                for timeout in thread.join_timeouts
            )
        )

    def test_surviving_process_group_member_is_reported_as_unsettled(self) -> None:
        class ReapedLeader:
            def __init__(self) -> None:
                self.pid = 424245
                self.stdout = io.BytesIO()
                self.stderr = io.BytesIO()
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

        process = ReapedLeader()
        with (
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.subprocess.Popen",
                return_value=process,
            ),
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.os.killpg",
                return_value=None,
            ) as kill_group,
            mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.PROCESS_GROUP_PROOF_SECONDS",
                0,
            ),
        ):
            with self.assertRaisesRegex(
                SandboxRuntimeError,
                "termination and reaping",
            ) as raised:
                SubprocessRunner(maximum_output_bytes=100).run(
                    ("sbx", "create"),
                    timeout_seconds=5,
                )

        outcome = process_termination_outcome(raised.exception)
        self.assertIsNotNone(outcome)
        self.assertTrue(outcome.leader_reaped)
        self.assertFalse(outcome.process_group_absent)
        self.assertFalse(outcome.fully_terminated_and_reaped)
        self.assertGreaterEqual(kill_group.call_count, 1)
        self.assertTrue(
            all(call.args == (process.pid, 0) for call in kill_group.call_args_list),
            "a reaped leader's numeric process-group ID must only be observed",
        )

    def test_completed_leader_is_not_reaped_until_its_descendants_are_terminated(
        self,
    ) -> None:
        script = (
            "import os,time;"
            "child=os.fork();"
            "(time.sleep(30) if child == 0 else print(child, flush=True));"
            "os._exit(0)"
        )

        result = SubprocessRunner(maximum_output_bytes=1024).run(
            (sys.executable, "-c", script),
            timeout_seconds=5,
        )

        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertTrue(result.process_outcome.fully_terminated_and_reaped)


class SandboxRuntimeTests(unittest.TestCase):
    def test_case_filesystem_scripts_are_valid_python(self) -> None:
        compile(CASE_FILESYSTEM_PROBE_SCRIPT, "<case-filesystem-probe>", "exec")
        compile(CASE_FILESYSTEM_CLEANUP_SCRIPT, "<case-filesystem-cleanup>", "exec")
        compile(WORKER_MOUNT_PROTECT_SCRIPT, "<worker-mount-protect>", "exec")
        compile(WORKER_MOUNT_RESTORE_SCRIPT, "<worker-mount-restore>", "exec")
        compile(
            DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT,
            "<directory-write-denial-probe>",
            "exec",
        )
        compile(
            PUBLIC_SKILL_CATALOG_PROBE_SCRIPT,
            "<public-skill-catalog-probe>",
            "exec",
        )
        compile(
            ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
            "<root-filesystem-write-denial-probe>",
            "exec",
        )
        compile(CASE_PRIVILEGE_LOCKDOWN_SCRIPT, "<case-privilege-lockdown>", "exec")
        compile(CASE_PRIVILEGE_PROBE_SCRIPT, "<case-privilege-probe>", "exec")
        compile(CASE_CGROUP_SETUP_SCRIPT, "<case-cgroup-setup>", "exec")
        compile(CASE_CGROUP_EXEC_SCRIPT, "<case-cgroup-exec>", "exec")
        compile(CASE_CGROUP_TERMINATE_SCRIPT, "<case-cgroup-terminate>", "exec")
        compile(CASE_CGROUP_REMOVE_SCRIPT, "<case-cgroup-remove>", "exec")

    def test_root_filesystem_probe_rejects_writable_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            root = temporary / "root"
            root.mkdir()
            mountinfo = temporary / "mountinfo"
            mountinfo.write_text(
                f"1 0 0:1 / {root.resolve()} ro - ext4 /dev/root ro\n",
                encoding="utf-8",
            )
            nested = root / "read-only-directory"
            nested.mkdir()
            writable = nested / "writable.txt"
            writable.write_text("state", encoding="utf-8")
            root.chmod(0o555)
            nested.chmod(0o555)
            writable.chmod(0o666)
            try:
                result = subprocess.run(
                    (
                        sys.executable,
                        "-c",
                        ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
                        str(root),
                        str(mountinfo),
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                )
            finally:
                writable.chmod(0o600)
                nested.chmod(0o700)
                root.chmod(0o700)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("writable root filesystem file", result.stderr)

    def test_root_filesystem_probe_rejects_uninspectable_traversable_directory(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            root = temporary / "root"
            root.mkdir()
            mountinfo = temporary / "mountinfo"
            mountinfo.write_text(
                f"1 0 0:1 / {root.resolve()} ro - ext4 /dev/root ro\n",
                encoding="utf-8",
            )
            hidden = root / "execute-only"
            hidden.mkdir()
            writable = hidden / "writable.txt"
            writable.write_text("state", encoding="utf-8")
            root.chmod(0o555)
            hidden.chmod(0o111)
            writable.chmod(0o666)
            try:
                result = subprocess.run(
                    (
                        sys.executable,
                        "-c",
                        ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
                        str(root),
                        str(mountinfo),
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                )
            finally:
                hidden.chmod(0o700)
                writable.chmod(0o600)
                root.chmod(0o700)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "cannot inspect actor-traversable root filesystem directory",
            result.stderr,
        )

    def test_root_filesystem_probe_rejects_writable_secondary_mount(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            root = temporary / "root"
            secondary_mount = root / "mnt" / "cache"
            secondary_mount.mkdir(parents=True)
            mountinfo = temporary / "mountinfo"
            mountinfo.write_text(
                (
                    f"1 0 0:1 / {root.resolve()} ro - ext4 /dev/root ro\n"
                    f"2 1 0:2 / {secondary_mount.resolve()} rw - tmpfs cache rw\n"
                ),
                encoding="utf-8",
            )
            root.chmod(0o555)
            secondary_mount.parent.chmod(0o555)
            secondary_mount.chmod(0o777)
            try:
                result = subprocess.run(
                    (
                        sys.executable,
                        "-c",
                        ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
                        str(root),
                        str(mountinfo),
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                )
            finally:
                secondary_mount.chmod(0o700)
                secondary_mount.parent.chmod(0o700)
                root.chmod(0o700)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "writable filesystem mount outside case tmpfs",
            result.stderr,
        )

    def test_root_filesystem_probe_accepts_declared_stacked_case_mount(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            root = temporary / "root"
            case_mount = root / "case"
            case_mount.mkdir(parents=True)
            mountinfo = temporary / "mountinfo"
            mountinfo.write_text(
                (
                    f"1 0 0:1 / {root.resolve()} ro - ext4 /dev/root ro\n"
                    f"2 1 0:2 / {case_mount.resolve()} rw - tmpfs original rw\n"
                    f"3 2 0:3 / {case_mount.resolve()} rw - tmpfs selected rw\n"
                ),
                encoding="utf-8",
            )
            root.chmod(0o555)
            case_mount.parent.chmod(0o555)
            case_mount.chmod(0o777)
            try:
                result = subprocess.run(
                    (
                        sys.executable,
                        "-c",
                        ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
                        str(root),
                        str(mountinfo),
                        str(case_mount),
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                )
            finally:
                case_mount.chmod(0o700)
                case_mount.parent.chmod(0o700)
                root.chmod(0o700)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cgroup_termination_is_idempotent_for_a_stably_empty_group(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cgroup = Path(directory)
            (cgroup / "cgroup.procs").write_text("", encoding="ascii")
            (cgroup / "cgroup.events").write_text(
                "populated 0\nfrozen 1\n",
                encoding="ascii",
            )
            (cgroup / "cgroup.freeze").write_text("", encoding="ascii")
            (cgroup / "cgroup.kill").write_text("", encoding="ascii")

            result = subprocess.run(
                (
                    sys.executable,
                    "-c",
                    CASE_CGROUP_TERMINATE_SCRIPT,
                    str(cgroup),
                    "1",
                ),
                capture_output=True,
                text=True,
                check=False,
            )
            kill_contents = (cgroup / "cgroup.kill").read_text(encoding="ascii")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertEqual(kill_contents, "")

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

    def test_preflight_accepts_an_update_notice_for_the_pinned_binary(self) -> None:
        results = valid_preflight_results()
        results[1] = completed(
            json.dumps(
                {
                    "version": "1.0",
                    "checks": [
                        {"name": "CLI binary", "status": "pass"},
                        {
                            "name": "Binary version",
                            "status": "warn",
                            "message": "update available: v0.37.0 (running v0.35.0)",
                        },
                    ],
                    "summary": {"pass": 1, "warn": 1, "fail": 0, "skip": 0},
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

        self.assertTrue(report.available, report.failure)

    def test_preflight_rejects_an_unrecognized_diagnostic_warning(self) -> None:
        results = valid_preflight_results()
        results[1] = completed(
            json.dumps(
                {
                    "version": "1.0",
                    "checks": [
                        {
                            "name": "Authentication",
                            "status": "warn",
                            "message": "authentication may be unavailable",
                        }
                    ],
                    "summary": {"pass": 0, "warn": 1, "fail": 0, "skip": 0},
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
            actor_marker = first_actor.host_root / OWNERSHIP_MARKER_NAME
            judge_marker = judge.host_root / OWNERSHIP_MARKER_NAME

            self.assertNotEqual(
                actor_marker.read_text(encoding="ascii"),
                judge_marker.read_text(encoding="ascii"),
            )
            self.assertEqual(actor_marker.stat().st_mode & 0o777, 0o600)
            self.assertEqual(judge_marker.stat().st_mode & 0o777, 0o600)

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

    def test_worker_lease_releases_acquisition_reservation_on_base_exception(self) -> None:
        process = FakeProcessRunner()
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
            worker = SandboxWorker(
                id="actor-id",
                name="ai-skills-unit-test-actor-1",
                role="actor",
                slot=0,
                host_root=Path(state) / "workers" / "actor",
            )
            with mock.patch.object(
                runtime,
                "acquire_worker",
                side_effect=(KeyboardInterrupt(), worker),
            ) as acquire:
                with self.assertRaises(KeyboardInterrupt):
                    with runtime.lease_worker("actor"):
                        self.fail("interrupted acquisition must not yield a worker")

                with runtime.lease_worker("actor") as acquired:
                    self.assertIs(acquired, worker)

        self.assertEqual(acquire.call_count, 2)

    def test_worker_lease_releases_reservation_when_handoff_is_interrupted(self) -> None:
        process = FakeProcessRunner()
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
            worker = SandboxWorker(
                id="actor-id",
                name="ai-skills-unit-test-actor-1",
                role="actor",
                slot=0,
                host_root=Path(state) / "workers" / "actor",
            )
            with (
                mock.patch.object(runtime, "acquire_worker", return_value=worker) as acquire,
                mock.patch.object(
                    runtime,
                    "_handoff_leased_worker",
                    side_effect=(KeyboardInterrupt(), worker),
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    with runtime.lease_worker("actor"):
                        self.fail("interrupted handoff must not yield a worker")

                with runtime.lease_worker("actor") as acquired:
                    self.assertIs(acquired, worker)

        self.assertEqual(acquire.call_count, 2)

    def test_worker_lease_release_interruption_cannot_leave_busy_reservation(self) -> None:
        process = FakeProcessRunner()
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
            worker = SandboxWorker(
                id="actor-id",
                name="ai-skills-unit-test-actor-1",
                role="actor",
                slot=0,
                host_root=Path(state) / "workers" / "actor",
            )
            with (
                mock.patch.object(runtime, "acquire_worker", return_value=worker),
                mock.patch.object(
                    runtime,
                    "_release_worker_reservation",
                    side_effect=KeyboardInterrupt(),
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    with runtime.lease_worker("actor") as acquired:
                        self.assertIs(acquired, worker)

            self.assertEqual(runtime._busy_workers, set())
            with mock.patch.object(runtime, "acquire_worker", return_value=worker):
                with runtime.lease_worker("actor") as acquired:
                    self.assertIs(acquired, worker)

    def test_close_interruption_outside_target_cleanup_remains_retryable(self) -> None:
        process = FakeProcessRunner()
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
            original_clear = runtime._clear_terminal_runtime_state
            clear_calls = 0

            def interrupt_once() -> None:
                nonlocal clear_calls
                clear_calls += 1
                if clear_calls == 1:
                    raise KeyboardInterrupt()
                original_clear()

            with mock.patch.object(
                runtime,
                "_clear_terminal_runtime_state",
                side_effect=interrupt_once,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    runtime.close()
                self.assertFalse(runtime._closed)
                self.assertFalse(runtime._closing)
                self.assertFalse(runtime.sandbox_cleanup_completed)

                runtime.close()

            self.assertTrue(runtime._closed)
            self.assertFalse(runtime._closing)
            self.assertTrue(runtime.sandbox_cleanup_completed)

    def test_close_interruption_immediately_after_claim_remains_retryable(self) -> None:
        class InterruptValuesOnce(dict):
            def __init__(self) -> None:
                super().__init__()
                self.interrupted = False

            def values(self):
                if not self.interrupted:
                    self.interrupted = True
                    raise KeyboardInterrupt()
                return super().values()

        process = FakeProcessRunner()
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
            runtime._cleanup_targets = InterruptValuesOnce()

            with self.assertRaises(KeyboardInterrupt):
                runtime.close()

            self.assertFalse(runtime._closed)
            self.assertFalse(runtime._closing)
            self.assertFalse(runtime.sandbox_cleanup_completed)

            runtime.close()

            self.assertTrue(runtime._closed)
            self.assertFalse(runtime._closing)
            self.assertTrue(runtime.sandbox_cleanup_completed)

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

        ownership_probe = next(
            argv
            for argv, _ in process.calls
            if OWNERSHIP_MARKER_PROBE_SCRIPT in argv
        )
        self.assertEqual(ownership_probe[4], "ai-skills-unit-test-actor-1")
        self.assertIn(
            (
                ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
                self.manifest.limits.preflight_timeout_seconds,
            ),
            process.calls,
        )
        self.assertNotIn("personal-sandbox", [part for argv, _ in process.calls for part in argv])

    def test_worker_execution_rejects_same_name_with_a_replacement_id(self) -> None:
        sandboxes: dict[str, str] = {}

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                sandboxes["actor-id"] = argv[argv.index("--name") + 1]
                return completed()
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                return completed()
            if argv[:3] == ("sbx", "rm", "--force"):
                discard_sandbox_by_name(sandboxes, argv[3])
                return completed()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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
            calls_before_replacement = len(process.calls)
            sandboxes = {"replacement-id": worker.name}

            with self.assertRaisesRegex(SandboxRuntimeError, "identity no longer matches"):
                runtime.run_worker_control(worker, ("true",))

        replacement_calls = [
            argv for argv, _ in process.calls[calls_before_replacement:]
        ]
        self.assertFalse(
            any(argv[:2] in (("sbx", "exec"), ("sbx", "rm")) for argv in replacement_calls)
        )

    def test_cleanup_rejects_same_name_with_a_replacement_id(self) -> None:
        sandboxes: dict[str, str] = {}

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                sandboxes["actor-id"] = argv[argv.index("--name") + 1]
                return completed()
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                return completed()
            if argv[:3] == ("sbx", "rm", "--force"):
                discard_sandbox_by_name(sandboxes, argv[3])
                return completed()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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
            calls_before_replacement = len(process.calls)
            sandboxes = {"replacement-id": worker.name}

            with self.assertRaisesRegex(SandboxRuntimeError, "identity no longer matches"):
                runtime.close()

        replacement_calls = [
            argv for argv, _ in process.calls[calls_before_replacement:]
        ]
        self.assertFalse(
            any(argv[:2] in (("sbx", "exec"), ("sbx", "rm")) for argv in replacement_calls)
        )

    def test_cleanup_rejects_replacement_created_during_removal(self) -> None:
        sandboxes: dict[str, str] = {}

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                sandboxes["actor-id"] = argv[argv.index("--name") + 1]
                return completed()
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                return completed()
            if argv[:3] == ("sbx", "rm", "--force"):
                name = argv[3]
                discard_sandbox_by_name(sandboxes, name)
                sandboxes["replacement-id"] = name
                return completed()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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

            with self.assertRaisesRegex(
                SandboxRuntimeError,
                "identity no longer matches",
            ):
                runtime.close()

            self.assertEqual(sandboxes, {"replacement-id": worker.name})

    def test_close_attempts_every_target_and_recovers_by_exact_identity(self) -> None:
        sandboxes = {"unrelated-id": "personal-sandbox"}
        cleanup_failures = {"ai-skills-unit-test-actor-1"}

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                name = argv[argv.index("--name") + 1]
                worker_id = "actor-id" if "-actor-" in name else "judge-id"
                sandboxes[worker_id] = name
                return completed()
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                worker_name = argv[4]
                if worker_name in cleanup_failures:
                    cleanup_failures.remove(worker_name)
                    return CommandResult(
                        returncode=1,
                        stdout="",
                        stderr="initial cleanup failed",
                    )
                return completed()
            if argv[:3] == ("sbx", "rm", "--force"):
                discard_sandbox_by_name(sandboxes, argv[3])
                return completed()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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
            actor = runtime.acquire_worker("actor")
            judge = runtime.acquire_worker("judge")

            runtime.close()

        cleanup_attempts = [
            argv[4]
            for argv, _ in process.calls
            if argv[:4] == ("sbx", "exec", "--user", "root")
        ]
        self.assertIn(actor.name, cleanup_attempts)
        self.assertIn(judge.name, cleanup_attempts)
        purge_attempts = [
            argv[4]
            for argv, _ in process.calls
            if argv[:4] == ("sbx", "exec", "--user", "root")
            and len(argv) > 5
            and argv[5] == "find"
        ]
        self.assertEqual(purge_attempts.count(actor.name), 1)
        remove_targets = [
            argv[3]
            for argv, _ in process.calls
            if argv[:3] == ("sbx", "rm", "--force")
        ]
        self.assertIn(actor.name, remove_targets)
        self.assertIn(judge.name, remove_targets)
        self.assertNotIn("personal-sandbox", remove_targets)

    def test_close_finishes_all_targets_before_propagating_interruption(self) -> None:
        sandboxes: dict[str, str] = {}
        actor_interrupted = False

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            nonlocal actor_interrupted
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                name = argv[argv.index("--name") + 1]
                worker_id = "actor-id" if "-actor-" in name else "judge-id"
                sandboxes[worker_id] = name
                return completed()
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                if argv[4] == "ai-skills-unit-test-actor-1" and not actor_interrupted:
                    actor_interrupted = True
                    raise KeyboardInterrupt()
                return completed()
            if argv[:3] == ("sbx", "rm", "--force"):
                discard_sandbox_by_name(sandboxes, argv[3])
                return completed()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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
            actor = runtime.acquire_worker("actor")
            judge = runtime.acquire_worker("judge")

            with self.assertRaises(KeyboardInterrupt):
                runtime.close()

            self.assertTrue(runtime.sandbox_cleanup_completed)
            self.assertFalse(actor.host_root.exists())
            self.assertFalse(judge.host_root.exists())

        remove_targets = [
            argv[3]
            for argv, _ in process.calls
            if argv[:3] == ("sbx", "rm", "--force")
        ]
        self.assertIn(actor.name, remove_targets)
        self.assertIn(judge.name, remove_targets)

    def test_close_removes_read_only_projection_after_quarantined_worker_is_destroyed(
        self,
    ) -> None:
        sandboxes: dict[str, str] = {}

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                name = argv[argv.index("--name") + 1]
                sandboxes["actor-id"] = name
                return completed()
            if argv[:3] == ("sbx", "rm", "--force"):
                discard_sandbox_by_name(sandboxes, argv[3])
                return completed()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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
            read_only_skill = worker.host_root / "case" / "codex-home" / "skills" / "example-skill"
            read_only_skill.mkdir(parents=True)
            (read_only_skill / "SKILL.md").write_text("fixture", encoding="utf-8")
            read_only_skill.chmod(0o555)
            runtime._cleanup_targets[worker.name].discard_without_export = True

            try:
                runtime.close()
            finally:
                if read_only_skill.exists():
                    read_only_skill.chmod(0o755)

            self.assertTrue(runtime.sandbox_cleanup_completed)
            self.assertFalse(worker.host_root.exists())

    def test_interrupted_close_reports_unresolved_cleanup_and_retains_host_staging(self) -> None:
        sandboxes: dict[str, str] = {}
        interrupt_cleanup = False

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                name = argv[argv.index("--name") + 1]
                sandboxes["actor-id"] = name
                return completed()
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                if interrupt_cleanup:
                    raise KeyboardInterrupt()
                return completed()
            if argv[:3] == ("sbx", "rm", "--force"):
                if interrupt_cleanup:
                    raise KeyboardInterrupt()
                discard_sandbox_by_name(sandboxes, argv[3])
                return completed()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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
            interrupt_cleanup = True

            with self.assertRaises(KeyboardInterrupt):
                runtime.close()

            self.assertFalse(runtime.sandbox_cleanup_completed)
            self.assertTrue(worker.host_root.exists())

        self.assertIn("actor-id", sandboxes)

    def test_close_aggregates_bounded_redacted_failures_after_all_targets(self) -> None:
        sandboxes: dict[str, str] = {}
        secret = "sk-abcdefghijklmnopqrstuvwxyz123456"

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                name = argv[argv.index("--name") + 1]
                worker_id = "actor-id" if "-actor-" in name else "judge-id"
                sandboxes[worker_id] = name
                return completed()
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr=f"cleanup refused for {argv[4]} {secret} " + ("x" * 10000),
                )
            if argv[:3] == ("sbx", "rm", "--force"):
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr=f"removal refused for {argv[3]} {secret} " + ("y" * 10000),
                )
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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
            actor = runtime.acquire_worker("actor")
            judge = runtime.acquire_worker("judge")

            with self.assertRaises(SandboxRuntimeError) as raised:
                runtime.close()

            self.assertTrue(actor.host_root.exists())
            self.assertTrue(judge.host_root.exists())

        diagnostic = str(raised.exception)
        self.assertIn(actor.name, diagnostic)
        self.assertIn(judge.name, diagnostic)
        self.assertNotIn(secret, diagnostic)
        self.assertLessEqual(len(diagnostic.encode("utf-8")), 8192)
        cleanup_attempts = [
            argv[4]
            for argv, _ in process.calls
            if argv[:4] == ("sbx", "exec", "--user", "root")
        ]
        self.assertIn(actor.name, cleanup_attempts)
        self.assertIn(judge.name, cleanup_attempts)
        purge_attempts = [
            argv[4]
            for argv, _ in process.calls
            if argv[:4] == ("sbx", "exec", "--user", "root")
            and len(argv) > 5
            and argv[5] == "find"
        ]
        self.assertEqual(purge_attempts.count(actor.name), 1)
        self.assertEqual(purge_attempts.count(judge.name), 1)
        remove_targets = [
            argv[3]
            for argv, _ in process.calls
            if argv[:3] == ("sbx", "rm", "--force")
        ]
        self.assertCountEqual(remove_targets, [actor.name, judge.name])

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
                with self.assertRaisesRegex(SandboxRuntimeError, "host cleanup"):
                    runtime.close()
                runtime.close()

            self.assertFalse(worker.host_root.exists())

        remove_calls = [argv for argv, _ in process.calls if argv[:2] == ("sbx", "rm")]
        self.assertEqual(len(remove_calls), 1)

    def test_close_reconciles_absence_after_successful_removal(self) -> None:
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

            runtime.close()

        purge_calls = [
            argv
            for argv, _ in process.calls
            if argv[:5] == (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
            )
            and len(argv) > 5
            and argv[5] == "find"
        ]
        remove_calls = [argv for argv, _ in process.calls if argv[:2] == ("sbx", "rm")]
        self.assertEqual(len(purge_calls), 1)
        self.assertEqual(len(remove_calls), 1)

    def test_absent_sandbox_does_not_settle_an_unreaped_removal_process(self) -> None:
        sandboxes: dict[str, str] = {}
        unproven = ProcessTerminationOutcome(
            process_started=True,
            leader_reaped=True,
            process_group_absent=False,
            drains_stopped=True,
        )

        def run_command(argv: tuple[str, ...]) -> CommandResult:
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                return completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {"id": sandbox_id, "name": name}
                                for sandbox_id, name in sandboxes.items()
                            ]
                        }
                    )
                )
            if argv[:2] == ("sbx", "create"):
                sandboxes["actor-id"] = argv[argv.index("--name") + 1]
                return completed()
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                return completed()
            if argv == (
                "sbx",
                "rm",
                "--force",
                "ai-skills-unit-test-actor-1",
            ):
                sandboxes.pop("actor-id", None)
                return CommandResult(
                    returncode=0,
                    stdout="",
                    stderr="",
                    process_outcome=unproven,
                )
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=run_command)
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

            with self.assertRaisesRegex(
                SandboxRuntimeError,
                "removal process termination is unproven",
            ):
                runtime.close()

            target = runtime._cleanup_targets[worker.name]
            self.assertTrue(target.removal_started)
            self.assertFalse(target.removal_process_settled)
            self.assertFalse(runtime.sandbox_cleanup_completed)
            self.assertTrue(worker.host_root.exists())
            self.assertEqual(sandboxes, {})

            with self.assertRaisesRegex(
                SandboxRuntimeError,
                "removal process termination is unproven",
            ):
                runtime.close()

        remove_calls = [
            argv for argv, _ in process.calls if argv[:3] == ("sbx", "rm", "--force")
        ]
        self.assertEqual(
            remove_calls,
            [("sbx", "rm", "--force", "ai-skills-unit-test-actor-1")],
        )

    def test_evaluation_runtime_removes_staging_after_trustworthy_cleanup(self) -> None:
        runtime = mock.Mock()
        with tempfile.TemporaryDirectory() as state:
            staging_root = Path(state) / "workers"
            staging_root.mkdir()
            (staging_root / "evidence.txt").write_text("temporary", encoding="utf-8")
            evaluation_runtime = CodexEvaluationRuntime(
                manifest=object(),
                adapter=mock.Mock(),
                runtime=runtime,
                staging_root=staging_root,
            )

            evaluation_runtime.close()

            self.assertFalse(staging_root.exists())
        runtime.close.assert_called_once_with()

    def test_evaluation_runtime_preserves_staging_when_cleanup_is_incomplete(self) -> None:
        runtime = mock.Mock()
        secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
        runtime.close.side_effect = SandboxRuntimeError(
            f"cleanup incomplete {secret} " + ("x" * 10000)
        )
        with tempfile.TemporaryDirectory() as state:
            staging_root = Path(state) / "workers"
            staging_root.mkdir()
            evidence = staging_root / "evidence.txt"
            evidence.write_text("temporary", encoding="utf-8")
            evaluation_runtime = CodexEvaluationRuntime(
                manifest=object(),
                adapter=mock.Mock(),
                runtime=runtime,
                staging_root=staging_root,
            )

            with self.assertRaises(EvaluationRuntimeError) as raised:
                evaluation_runtime.close()

            self.assertTrue(evidence.exists())

        diagnostic = str(raised.exception)
        self.assertIn("sandbox cleanup failed", diagnostic)
        self.assertNotIn(secret, diagnostic)
        self.assertLessEqual(len(diagnostic.encode("utf-8")), 8192)

    def test_evaluation_runtime_removes_staging_after_completed_interrupted_cleanup(self) -> None:
        runtime = mock.Mock()
        runtime.sandbox_cleanup_completed = True
        runtime.close.side_effect = KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as state:
            staging_root = Path(state) / "workers"
            staging_root.mkdir()
            evidence = staging_root / "evidence.txt"
            evidence.write_text("temporary", encoding="utf-8")
            evaluation_runtime = CodexEvaluationRuntime(
                manifest=object(),
                adapter=mock.Mock(),
                runtime=runtime,
                staging_root=staging_root,
            )

            with self.assertRaises(KeyboardInterrupt):
                evaluation_runtime.close()

            self.assertFalse(staging_root.exists())

    def test_evaluation_runtime_retains_staging_after_unresolved_interruption(self) -> None:
        runtime = mock.Mock()
        runtime.sandbox_cleanup_completed = False
        runtime.close.side_effect = KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as state:
            staging_root = Path(state) / "workers"
            staging_root.mkdir()
            evidence = staging_root / "evidence.txt"
            evidence.write_text("temporary", encoding="utf-8")
            evaluation_runtime = CodexEvaluationRuntime(
                manifest=object(),
                adapter=mock.Mock(),
                runtime=runtime,
                staging_root=staging_root,
            )

            with self.assertRaises(KeyboardInterrupt) as raised:
                evaluation_runtime.close()

            self.assertTrue(evidence.exists())
            self.assertIn("staging was retained", " ".join(raised.exception.__notes__))

    def test_evaluation_runtime_bounds_and_redacts_host_staging_failures(self) -> None:
        runtime = mock.Mock()
        secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
        with tempfile.TemporaryDirectory() as state:
            staging_root = Path(state) / "workers"
            staging_root.mkdir()
            evidence = staging_root / "evidence.txt"
            evidence.write_text("temporary", encoding="utf-8")
            evaluation_runtime = CodexEvaluationRuntime(
                manifest=object(),
                adapter=mock.Mock(),
                runtime=runtime,
                staging_root=staging_root,
            )

            with mock.patch(
                "scripts.ai_skills_lib.evaluation_runtime.shutil.rmtree",
                side_effect=OSError(f"host cleanup failed {secret} " + ("x" * 10000)),
            ):
                with self.assertRaises(EvaluationRuntimeError) as raised:
                    evaluation_runtime.close()

            self.assertTrue(evidence.exists())

        diagnostic = str(raised.exception)
        self.assertIn("worker staging cleanup failed", diagnostic)
        self.assertNotIn(secret, diagnostic)
        self.assertLessEqual(len(diagnostic.encode("utf-8")), 8192)

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

    def test_unsettled_create_retains_preregistered_nonce_and_staging(self) -> None:
        sandbox_name = "ai-skills-unit-test-actor-1"
        create_interrupted = False
        allow_cleanup = False
        runtime_reference: list[SandboxRuntime] = []

        def interrupt_create(argv: tuple[str, ...]) -> CommandResult:
            nonlocal create_interrupted
            if argv == ("sbx", "ls", "--json"):
                if create_interrupted and not allow_cleanup:
                    raise KeyboardInterrupt()
                return completed(json.dumps({"sandboxes": []}))
            if argv[:2] == ("sbx", "create"):
                runtime = runtime_reference[0]
                self.assertIn(sandbox_name, runtime._cleanup_targets)
                marker = Path(argv[-1]) / OWNERSHIP_MARKER_NAME
                self.assertRegex(marker.read_text(encoding="ascii"), r"^[0-9a-f]{64}\n$")
                create_interrupted = True
                raise KeyboardInterrupt()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=interrupt_create)
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
            runtime_reference.append(runtime)

            with self.assertRaises(KeyboardInterrupt):
                runtime.acquire_worker("actor")

            target = runtime._cleanup_targets[sandbox_name]
            self.assertIsNone(target.id)
            self.assertTrue(target.host_root.exists())
            self.assertTrue((target.host_root / OWNERSHIP_MARKER_NAME).is_file())

            allow_cleanup = True
            with self.assertRaisesRegex(SandboxRuntimeError, "termination is unproven"):
                runtime.close()
            with self.assertRaisesRegex(SandboxRuntimeError, "termination is unproven"):
                runtime.close()
            self.assertTrue(target.host_root.exists())
            self.assertTrue(target.ownership_marker.is_file())
            self.assertFalse(runtime.sandbox_cleanup_completed)

    def test_only_fully_terminated_process_outcome_settles_create(self) -> None:
        sandbox_name = "ai-skills-unit-test-actor-1"
        process = FakeProcessRunner(
            [
                CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="create failed",
                    process_outcome=ProcessTerminationOutcome(
                        process_started=True,
                        leader_reaped=True,
                        process_group_absent=False,
                        drains_stopped=True,
                    ),
                ),
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

            with self.assertRaisesRegex(SandboxRuntimeError, "definitively terminated"):
                runtime.acquire_worker("actor")

            target = runtime._cleanup_targets[sandbox_name]
            self.assertTrue(target.create_started)
            self.assertFalse(target.create_process_settled)
            self.assertTrue(target.host_root.exists())
            self.assertTrue(target.ownership_marker.is_file())

    def test_settled_create_retains_evidence_past_old_window_until_delayed_appearance(
        self,
    ) -> None:
        sandbox_name = "ai-skills-unit-test-actor-1"
        post_create_listings = 0
        sandbox_present = False

        def delayed_registration(argv: tuple[str, ...]) -> CommandResult:
            nonlocal post_create_listings, sandbox_present
            marker_result = ownership_marker_probe_result(argv)
            if marker_result is not None:
                return marker_result
            if argv == ("sbx", "ls", "--json"):
                if post_create_listings or any(
                    call[0][:2] == ("sbx", "create") for call in process.calls
                ):
                    post_create_listings += 1
                sandboxes = (
                    [{"id": "actor-id", "name": sandbox_name}]
                    if sandbox_present
                    else []
                )
                return completed(json.dumps({"sandboxes": sandboxes}))
            if argv[:2] == ("sbx", "create"):
                return CommandResult(
                    returncode=124,
                    stdout="",
                    stderr="create timed out",
                    timed_out=True,
                    process_outcome=PROCESS_FULLY_TERMINATED,
                )
            if argv[:4] == ("sbx", "exec", "--user", "root"):
                return completed()
            if argv == (
                "sbx",
                "rm",
                "--force",
                "ai-skills-unit-test-actor-1",
            ):
                sandbox_present = False
                return completed()
            raise AssertionError(f"unexpected process call: {argv!r}")

        process = FakeProcessRunner(side_effect=delayed_registration)
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

            with self.assertRaisesRegex(SandboxRuntimeError, "authoritative"):
                runtime.acquire_worker("actor")

            target = runtime._cleanup_targets[sandbox_name]
            self.assertTrue(target.create_process_settled)
            self.assertTrue(target.ownership_marker.is_file())
            with self.assertRaisesRegex(SandboxRuntimeError, "authoritative"):
                runtime.close()
            time.sleep(1.1)
            with self.assertRaisesRegex(SandboxRuntimeError, "authoritative"):
                runtime.close()
            self.assertTrue(target.host_root.exists())
            self.assertTrue(target.ownership_marker.is_file())

            sandbox_present = True
            runtime.close()

            self.assertFalse(target.host_root.exists())

        self.assertGreaterEqual(post_create_listings, 6)
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            [argv for argv, _ in process.calls],
        )

    def test_create_timeout_refuses_same_named_candidate_without_nonce_proof(self) -> None:
        sandbox_name = "ai-skills-unit-test-actor-1"

        def reject_marker_probe(argv: tuple[str, ...]) -> CommandResult | None:
            if (
                argv[:4] == ("sbx", "exec", "--user", "root")
                and len(argv) == 9
                and argv[5:7] == ("python3", "-c")
            ):
                return completed("0" * 64)
            return None

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
                        {"sandboxes": [{"id": "impostor-id", "name": sandbox_name}]}
                    )
                ),
            ],
            side_effect=reject_marker_probe,
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

            with self.assertRaisesRegex(SandboxRuntimeError, "ownership"):
                runtime.acquire_worker("actor")

            target = runtime._cleanup_targets[sandbox_name]
            self.assertIsNone(target.id)
            self.assertTrue(target.host_root.exists())

        self.assertNotIn(
            ("sbx", "rm", "--force", "impostor-id"),
            [argv for argv, _ in process.calls],
        )

    def test_create_timeout_removes_sandbox_only_after_exact_nonce_proof(self) -> None:
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
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            [argv for argv, _ in process.calls],
        )
        marker_probes = [
            argv
            for argv, _ in process.calls
            if argv[:4] == ("sbx", "exec", "--user", "root")
            and len(argv) == 9
            and argv[5:7] == ("python3", "-c")
            and Path(argv[8]).name == OWNERSHIP_MARKER_NAME
        ]
        self.assertEqual(len(marker_probes), 1)

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
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
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
            self.assertEqual(
                {path.name for path in second.skills.iterdir()},
                {".system"},
            )
            self.assertEqual(list((second.skills / ".system").iterdir()), [])
            self.assertEqual(
                {path.name for path in second.root.iterdir()},
                {
                    "home",
                    "codex-home",
                    "tmp",
                    "workspace",
                    "bootstrap",
                    ".system-var-tmp",
                    ".system-dev-shm",
                    ".system-run-lock",
                    ".system-run-secrets",
                },
            )
            self.assertEqual(second.skills.parent, second.codex_home)

        root_commands = [
            argv[5:]
            for argv, _ in process.calls
            if argv[:5] == (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
            )
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
            wrapped
            for argv, _ in process.calls
            if (wrapped := cgroup_wrapped_case_command(argv)) is not None
        ]
        commands = [argv for argv, _ in process.calls]
        setup_index = next(
            index
            for index, argv in enumerate(commands)
            if len(argv) > 7 and argv[7] == CASE_CGROUP_SETUP_SCRIPT
        )
        first_case_command_index = next(
            index
            for index, argv in enumerate(commands)
            if cgroup_wrapped_case_command(argv) is not None
        )
        self.assertLess(setup_index, first_case_command_index)
        self.assertEqual(
            commands[setup_index][-1],
            str(case.cgroup_path),
        )
        self.assertIn(("test", "!", "-r", "/var/run/docker.sock"), case_commands)
        self.assertIn(("test", "!", "-w", "/var/run/docker.sock"), case_commands)
        self.assertIn(("test", "!", "-r", "/home/agent/.codex/auth.json"), case_commands)
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "chmod",
                "0755",
                "/var/lib/pebble/default",
            ),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "chmod",
                "0700",
                "/opt/containerd",
                "/run/containerd",
            ),
            commands,
        )

    def test_missing_cgroup_v2_controls_discards_worker_before_case_execution(self) -> None:
        def reject_cgroup_setup(argv: tuple[str, ...]) -> CommandResult | None:
            if len(argv) > 7 and argv[7] == CASE_CGROUP_SETUP_SCRIPT:
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="required cgroup v2 lifecycle controls are unavailable",
                )
            return None

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
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=reject_cgroup_setup,
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

            with self.assertRaisesRegex(SandboxRuntimeError, "reset"):
                runtime.prepare_case(worker, "case-one")

        commands = [argv for argv, _ in process.calls]
        self.assertFalse(
            any(cgroup_wrapped_case_command(argv) is not None for argv in commands)
        )
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            commands,
        )

    def test_case_layout_is_complete_before_identity_ownership_changes(self) -> None:
        missing_at_chown: list[Path] = []

        def inspect_chown(argv: tuple[str, ...]) -> None:
            if argv[:5] != (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
            ):
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

    def test_execute_uses_one_verified_tmpfs_quota_for_all_case_writable_paths(self) -> None:
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
            (case.workspace / "seed.txt").write_text("seed", encoding="utf-8")

            result = runtime.execute(worker, case, ("true",), timeout_seconds=30)
            runtime.quiesce_case(worker, case)

        self.assertEqual(result.stdout, "result")
        self.assertEqual(case.host_staging_root, case.root)
        self.assertEqual(
            case.host_export_bridge,
            Path("/run/ai-skills-evals") / case.filesystem_source / "host",
        )
        commands = [argv for argv, _ in process.calls]
        tmpfs_mount = next(
            argv
            for argv in commands
            if argv[:7]
            == (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "mount",
                "-t",
            )
        )
        self.assertEqual(tmpfs_mount[7], "tmpfs")
        mount_options = tmpfs_mount[tmpfs_mount.index("-o") + 1].split(",")
        self.assertIn(
            f"size={self.manifest.case_isolation.maximum_writable_bytes}",
            mount_options,
        )
        self.assertIn(
            f"nr_inodes={self.manifest.case_isolation.maximum_writable_inodes}",
            mount_options,
        )
        self.assertIn("nosuid", mount_options)
        self.assertIn("nodev", mount_options)
        self.assertEqual(tmpfs_mount[-2], case.filesystem_source)
        self.assertEqual(tmpfs_mount[-1], str(case.root))
        worker_mount_protect = next(
            argv for argv in commands if WORKER_MOUNT_PROTECT_SCRIPT in argv
        )
        self.assertEqual(worker_mount_protect[-1], str(worker.host_root))
        bridge_bind = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "mount",
            "--bind",
            str(case.root),
            str(case.host_export_bridge),
        )
        self.assertIn(bridge_bind, commands)
        self.assertLess(
            commands.index(bridge_bind), commands.index(worker_mount_protect)
        )
        self.assertLess(
            commands.index(worker_mount_protect), commands.index(tmpfs_mount)
        )

        worker_write_probe = next(
            wrapped
            for command in commands
            if (wrapped := cgroup_wrapped_case_command(command)) is not None
            and wrapped[:3]
            == ("python3", "-c", DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT)
        )
        self.assertEqual(
            worker_write_probe[-1],
            str(worker.host_root / ".worker-write-probe"),
        )
        root_write_probe = next(
            wrapped
            for command in commands
            if (wrapped := cgroup_wrapped_case_command(command)) is not None
            and wrapped[:3]
            == ("python3", "-c", ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT)
        )
        self.assertEqual(
            root_write_probe,
            (
                "python3",
                "-c",
                ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT,
                "/",
                "/proc/self/mountinfo",
                str(case.root),
                "/tmp",
                "/var/tmp",
                "/dev/shm",
                "/run/lock",
                "/run/secrets",
            ),
        )

        expected_binds = {
            (str(case.tmpdir), "/tmp"),
            (str(case.system_var_tmp), "/var/tmp"),
            (str(case.system_dev_shm), "/dev/shm"),
            (str(case.system_run_lock), "/run/lock"),
            (str(case.system_run_secrets), "/run/secrets"),
        }
        actual_binds = {
            (argv[-2], argv[-1])
            for argv in commands
            if argv[:7]
            == (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "mount",
                "--bind",
            )
        }
        self.assertTrue(expected_binds.issubset(actual_binds))
        probes = [
            argv
            for argv in commands
            if len(argv) > 7
            and argv[:7]
            == (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "python3",
                "-c",
            )
            and argv[7] == CASE_FILESYSTEM_PROBE_SCRIPT
        ]
        self.assertGreaterEqual(len(probes), 2)
        self.assertEqual(probes[0][8], str(case.root))
        self.assertEqual(probes[0][9], case.filesystem_source)
        self.assertEqual(
            probes[0][10],
            str(self.manifest.case_isolation.maximum_writable_bytes),
        )
        self.assertEqual(
            probes[0][11],
            str(self.manifest.case_isolation.maximum_writable_inodes),
        )
        privilege_lockdowns = [
            argv
            for argv in commands
            if len(argv) > 7
            and argv[:7]
            == (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "python3",
                "-c",
            )
            and argv[7] == CASE_PRIVILEGE_LOCKDOWN_SCRIPT
        ]
        privilege_probes = [
            argv
            for argv in commands
            if (
                (wrapped := cgroup_wrapped_case_command(argv)) is not None
                and wrapped[:3]
                == ("python3", "-c", CASE_PRIVILEGE_PROBE_SCRIPT)
            )
        ]
        self.assertEqual(len(privilege_lockdowns), 1)
        self.assertGreaterEqual(len(privilege_probes), 2)
        seed_copy = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "cp",
            "--archive",
            "--one-file-system",
            "--",
            f"{case.host_export_bridge}/.",
            f"{case.root}/",
        )
        export_copy = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "cp",
            "--archive",
            "--one-file-system",
            "--",
            f"{case.root}/.",
            f"{case.host_export_bridge}/",
        )
        staging_root_restore = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "chmod",
            "0700",
            str(case.root),
        )
        staging_tree_restore = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "chmod",
            "-R",
            "u+rwX",
            str(case.root),
        )
        bridge_tree_reopen = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "chmod",
            "-R",
            "u+rwX",
            str(case.host_export_bridge),
        )
        self.assertIn(seed_copy, commands)
        self.assertIn(export_copy, commands)
        self.assertIn(bridge_tree_reopen, commands)
        self.assertIn(staging_tree_restore, commands)
        self.assertIn(staging_root_restore, commands)
        self.assertLess(commands.index(bridge_tree_reopen), commands.index(export_copy))
        root_lock = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "chmod",
            "0555",
            str(case.root),
        )
        self.assertIn(root_lock, commands)
        ownership_handoff = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "chown",
            "-R",
            f"{case.uid}:{case.uid}",
            str(case.root),
        )
        ownership_handoffs = [
            index for index, command in enumerate(commands) if command == ownership_handoff
        ]
        self.assertEqual(len(ownership_handoffs), 2)
        self.assertLess(commands.index(seed_copy), commands.index(root_lock))
        self.assertLess(commands.index(seed_copy), ownership_handoffs[-1])
        self.assertLess(ownership_handoffs[-1], commands.index(root_lock))
        self.assertLess(commands.index(root_lock), commands.index(probes[0]))
        cleanup_index = next(
            index
            for index, argv in enumerate(commands)
            if len(argv) > 7 and argv[7] == CASE_FILESYSTEM_CLEANUP_SCRIPT
        )
        self.assertEqual(
            commands[cleanup_index][-10:],
            (
                "/tmp",
                "/tmp",
                "/var/tmp",
                "/.system-var-tmp",
                "/dev/shm",
                "/.system-dev-shm",
                "/run/lock",
                "/.system-run-lock",
                "/run/secrets",
                "/.system-run-secrets",
            ),
        )
        worker_mount_restore = next(
            argv for argv in commands if WORKER_MOUNT_RESTORE_SCRIPT in argv
        )
        self.assertEqual(worker_mount_restore[-1], str(worker.host_root))
        actor_index = next(
            index
            for index, argv in enumerate(commands)
            if argv[:4] == ("sbx", "exec", "--user", "root")
            and "--workdir" in argv
            and cgroup_wrapped_case_command(argv) == ("true",)
        )
        self.assertLess(commands.index(seed_copy), actor_index)
        self.assertLess(commands.index(privilege_lockdowns[0]), actor_index)
        self.assertLess(commands.index(privilege_probes[-1]), actor_index)
        root_probe_index = next(
            index
            for index, command in enumerate(commands)
            if cgroup_wrapped_case_command(command) == root_write_probe
        )
        self.assertLess(root_probe_index, actor_index)
        self.assertLess(actor_index, commands.index(export_copy))
        self.assertLess(commands.index(export_copy), cleanup_index)
        self.assertLess(cleanup_index, commands.index(worker_mount_restore))
        self.assertLess(
            commands.index(worker_mount_restore), commands.index(staging_tree_restore)
        )
        self.assertLess(
            commands.index(staging_tree_restore), commands.index(staging_root_restore)
        )
        self.assertLess(cleanup_index, commands.index(staging_root_restore))

    def test_mount_verification_failure_recycles_worker_before_actor_execution(self) -> None:
        def fail_mount_probe(argv: tuple[str, ...]) -> CommandResult | None:
            if len(argv) > 7 and argv[7] == CASE_FILESYSTEM_PROBE_SCRIPT:
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="tmpfs quota mismatch",
                )
            return None

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
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=fail_mount_probe,
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

            with self.assertRaises(SandboxRuntimeError):
                runtime.execute(worker, case, ("actor-command",), timeout_seconds=30)

        commands = [argv for argv, _ in process.calls]
        self.assertFalse(
            any(
                cgroup_wrapped_case_command(argv) == ("actor-command",)
                for argv in commands
            )
        )
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            commands,
        )
        self.assertFalse(
            any(
                argv[:8]
                == (
                    "sbx",
                    "exec",
                    "--user",
                    "root",
                    "ai-skills-unit-test-actor-1",
                    "cp",
                    "--archive",
                    "--one-file-system",
                )
                and argv[-2:] == (f"{case.root}/.", f"{case.host_export_bridge}/")
                for argv in commands
            )
        )

    def test_writable_root_filesystem_path_recycles_worker_before_actor_execution(
        self,
    ) -> None:
        def fail_root_write_probe(argv: tuple[str, ...]) -> CommandResult | None:
            wrapped = cgroup_wrapped_case_command(argv)
            if (
                wrapped is not None
                and wrapped[:3]
                == ("python3", "-c", ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT)
            ):
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="writable root filesystem path: /unexpected",
                )
            return None

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
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=fail_root_write_probe,
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

            with self.assertRaisesRegex(
                SandboxRuntimeError,
                r"root filesystem exposes writable state.*writable root filesystem path: /unexpected",
            ):
                runtime.execute(
                    worker,
                    case,
                    ("actor-command",),
                    timeout_seconds=30,
                )

        commands = [argv for argv, _ in process.calls]
        self.assertFalse(
            any(
                cgroup_wrapped_case_command(argv) == ("actor-command",)
                for argv in commands
            )
        )
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            commands,
        )

    def test_uninspectable_traversable_root_directory_recycles_worker(self) -> None:
        def fail_root_write_probe(argv: tuple[str, ...]) -> CommandResult | None:
            wrapped = cgroup_wrapped_case_command(argv)
            if (
                wrapped is not None
                and wrapped[:3]
                == ("python3", "-c", ROOT_FILESYSTEM_WRITE_DENIAL_PROBE_SCRIPT)
            ):
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr=(
                        "cannot inspect actor-traversable root filesystem "
                        "directory: /execute-only"
                    ),
                )
            return None

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
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=fail_root_write_probe,
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

            with self.assertRaisesRegex(
                SandboxRuntimeError,
                "root filesystem exposes writable state",
            ):
                runtime.execute(
                    worker,
                    case,
                    ("actor-command",),
                    timeout_seconds=30,
                )

        commands = [argv for argv, _ in process.calls]
        self.assertFalse(
            any(
                cgroup_wrapped_case_command(argv) == ("actor-command",)
                for argv in commands
            )
        )
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            commands,
        )

    def test_nested_mount_verification_failure_blocks_host_export(self) -> None:
        mount_probes = 0

        def fail_export_mount_probe(argv: tuple[str, ...]) -> CommandResult | None:
            nonlocal mount_probes
            if len(argv) > 7 and argv[7] == CASE_FILESYSTEM_PROBE_SCRIPT:
                mount_probes += 1
                if mount_probes == 2:
                    return CommandResult(
                        returncode=1,
                        stdout="",
                        stderr="unexpected nested mount beneath case quota",
                    )
            return None

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
                completed("actor result"),
                completed(),
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=fail_export_mount_probe,
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
            runtime.execute(worker, case, ("actor-command",), timeout_seconds=30)

            with self.assertRaises(SandboxRuntimeError):
                runtime.quiesce_case(worker, case)

        commands = [argv for argv, _ in process.calls]
        export_copy_prefix = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "cp",
            "--archive",
            "--one-file-system",
        )
        self.assertEqual(mount_probes, 2)
        self.assertFalse(
            any(
                argv[: len(export_copy_prefix)] == export_copy_prefix
                and argv[-2:] == (f"{case.root}/.", f"{case.host_export_bridge}/")
                for argv in commands
            )
        )
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            commands,
        )

    def test_privilege_boundary_failure_recycles_worker_before_actor_execution(self) -> None:
        privilege_probes = 0

        def fail_active_privilege_probe(argv: tuple[str, ...]) -> CommandResult | None:
            nonlocal privilege_probes
            wrapped = cgroup_wrapped_case_command(argv)
            if (
                wrapped is not None
                and wrapped[:3]
                == ("python3", "-c", CASE_PRIVILEGE_PROBE_SCRIPT)
            ):
                privilege_probes += 1
                if privilege_probes == 2:
                    return CommandResult(
                        returncode=1,
                        stdout="",
                        stderr="mount creation unexpectedly succeeded",
                    )
            return None

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
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=fail_active_privilege_probe,
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

            with self.assertRaises(SandboxRuntimeError):
                runtime.execute(worker, case, ("actor-command",), timeout_seconds=30)

        commands = [argv for argv, _ in process.calls]
        self.assertEqual(privilege_probes, 2)
        self.assertFalse(
            any(
                cgroup_wrapped_case_command(argv) == ("actor-command",)
                for argv in commands
            )
        )
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            commands,
        )

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
        self.assertIn(("--user", "root"), tuple(zip(argv, argv[1:])))
        self.assertIn(CASE_CGROUP_EXEC_SCRIPT, argv)
        self.assertIn(str(case.cgroup_path), argv)
        self.assertIn(str(case.uid), argv)
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
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
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
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "false",
            ),
            [argv for argv, _ in process.calls],
        )

    def test_quiesces_case_cgroup_before_ipc_and_evidence_collection(self) -> None:
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

        commands = [
            argv[5:]
            for argv, _ in process.calls
            if argv[:5]
            == (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
            )
        ]
        cgroup_commands = [
            command
            for command in commands
            if command[:3] == ("python3", "-c", CASE_CGROUP_TERMINATE_SCRIPT)
        ]
        self.assertEqual(len(cgroup_commands), 1)
        self.assertEqual(cgroup_commands[0][3], str(case.cgroup_path))
        ipc_commands = [
            command
            for command in commands
            if command[:2] == ("python3", "-c")
            and command[2] == IPC_CLEANUP_SCRIPT
        ]
        self.assertEqual(len(ipc_commands), 1)
        self.assertEqual(ipc_commands[0][-1], str(case.uid))
        self.assertLess(
            commands.index(cgroup_commands[0]),
            commands.index(ipc_commands[0]),
        )
        remove_commands = [
            command
            for command in commands
            if command[:3] == ("python3", "-c", CASE_CGROUP_REMOVE_SCRIPT)
        ]
        self.assertEqual(len(remove_commands), 1)
        self.assertEqual(remove_commands[0][-1], str(case.cgroup_path))
        self.assertLess(
            commands.index(ipc_commands[0]),
            commands.index(remove_commands[0]),
        )
        self.assertFalse(any(command[:1] in (("pkill",), ("pgrep",)) for command in commands))
        self.assertLess(
            CASE_CGROUP_TERMINATE_SCRIPT.index('"cgroup.freeze").write_text("1'),
            CASE_CGROUP_TERMINATE_SCRIPT.index('"cgroup.kill").write_text("1'),
        )
        self.assertIn('state.get("populated") == "0"', CASE_CGROUP_TERMINATE_SCRIPT)
        self.assertIn('"cgroup.procs"', CASE_CGROUP_TERMINATE_SCRIPT)

    def test_quiesce_accepts_successful_cgroup_control_with_host_warning(self) -> None:
        def add_host_warning(argv: tuple[str, ...]) -> CommandResult | None:
            if len(argv) > 7 and argv[7] == CASE_CGROUP_TERMINATE_SCRIPT:
                return completed(
                    stderr=(
                        "WARN: could not acquire docker hub refresh lock, "
                        "proceeding without cross-process lock"
                    )
                )
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
            ],
            side_effect=add_host_warning,
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

        self.assertIn(case.filesystem_source, runtime._quiesced_cases)

    def test_case_reset_does_not_revisit_quiesced_kernel_state(self) -> None:
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
            first = runtime.prepare_case(worker, "case-one")

            runtime.quiesce_case(worker, first)
            second = runtime.prepare_case(worker, "case-two")

        commands = [argv for argv, _ in process.calls]
        self.assertEqual(second.case_id, "case-two")
        self.assertEqual(
            sum(CASE_CGROUP_TERMINATE_SCRIPT in command for command in commands),
            1,
        )
        self.assertEqual(
            sum(CASE_CGROUP_REMOVE_SCRIPT in command for command in commands),
            1,
        )
        run_lock_setup = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "mkdir",
            "--parents",
            "/run/lock",
            "/run/secrets",
        )
        self.assertIn(run_lock_setup, commands)

    def test_ambiguous_cgroup_population_discards_worker_before_ipc_or_export(self) -> None:
        def report_fork_churn(argv: tuple[str, ...]) -> CommandResult | None:
            if len(argv) > 7 and argv[7] == CASE_CGROUP_TERMINATE_SCRIPT:
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="case cgroup population could not be proven empty",
                )
            return None

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
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=report_fork_churn,
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

            with self.assertRaisesRegex(
                SandboxRuntimeError,
                "case cgroup population could not be proven empty",
            ):
                runtime.quiesce_case(worker, case)

        commands = [argv for argv, _ in process.calls]
        self.assertFalse(
            any(
                len(argv) > 7
                and argv[5:7] == ("python3", "-c")
                and argv[7] == IPC_CLEANUP_SCRIPT
                for argv in commands
            )
        )
        self.assertFalse(
            any(
                argv[:8]
                == (
                    "sbx",
                    "exec",
                    "--user",
                    "root",
                    "ai-skills-unit-test-actor-1",
                    "cp",
                    "--archive",
                    "--one-file-system",
                )
                and argv[-2:] == (f"{case.root}/.", f"{case.host_export_bridge}/")
                for argv in commands
            )
        )
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            commands,
        )

    def test_close_quarantines_cgroup_ambiguity_and_destroys_without_export(self) -> None:
        def reject_cgroup_termination(argv: tuple[str, ...]) -> CommandResult | None:
            if len(argv) > 7 and argv[7] == CASE_CGROUP_TERMINATE_SCRIPT:
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="fork churn prevented a stable empty observation",
                )
            return None

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
                completed(json.dumps({"sandboxes": []})),
            ],
            side_effect=reject_cgroup_termination,
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

            runtime.close()

            self.assertTrue(runtime.sandbox_cleanup_completed)

        commands = [argv for argv, _ in process.calls]
        self.assertEqual(
            sum(
                1
                for argv in commands
                if len(argv) > 7 and argv[7] == CASE_CGROUP_TERMINATE_SCRIPT
            ),
            1,
        )
        self.assertFalse(
            any(len(argv) > 7 and argv[7] == IPC_CLEANUP_SCRIPT for argv in commands)
        )
        self.assertFalse(
            any(
                argv[:8]
                == (
                    "sbx",
                    "exec",
                    "--user",
                    "root",
                    "ai-skills-unit-test-actor-1",
                    "cp",
                    "--archive",
                    "--one-file-system",
                )
                and argv[-2:] == (f"{case.root}/.", f"{case.host_export_bridge}/")
                for argv in commands
            )
        )
        self.assertIn(
            ("sbx", "rm", "--force", "ai-skills-unit-test-actor-1"),
            commands,
        )

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
                DOCKER_CODEX_PROXY_CONFIG,
                encoding="utf-8",
            )
            (target / "auth.json").write_text(
                DOCKER_CODEX_PROXY_AUTH,
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
        profile_handoff = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "chown",
            f"{case.uid}:{case.uid}",
            str(case.codex_home / "config.toml"),
            str(case.codex_home / "auth.json"),
        )
        self.assertIn(profile_handoff, [argv for argv, _ in process.calls])

    def test_proxy_profile_read_is_bounded_after_post_stat_growth(self) -> None:
        def copy_proxy_state(argv: tuple[str, ...]) -> None:
            if argv[:2] != ("sbx", "exec") or "cp" not in argv:
                return
            target = Path(argv[-1])
            (target / "config.toml").write_text(
                DOCKER_CODEX_PROXY_CONFIG,
                encoding="utf-8",
            )
            (target / "auth.json").write_text(
                DOCKER_CODEX_PROXY_AUTH,
                encoding="utf-8",
            )

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
            config_path = case.codex_home / "config.toml"
            real_read = os.read
            grew = False

            def grow_after_stat(descriptor: int, size: int) -> bytes:
                nonlocal grew
                if (
                    not grew
                    and config_path.exists()
                    and os.fstat(descriptor).st_ino == config_path.stat().st_ino
                ):
                    with config_path.open("ab") as stream:
                        stream.write(b"x" * (1024 * 1024 + 1))
                    grew = True
                return real_read(descriptor, size)

            with mock.patch(
                "scripts.ai_skills_lib.sandbox_runtime.os.read",
                side_effect=grow_after_stat,
            ):
                with self.assertRaisesRegex(
                    SandboxRuntimeError,
                    "changed while being read",
                ):
                    runtime._initialize_codex_home_unchecked(worker, case)

            self.assertTrue(grew)

    def test_proxy_profile_reader_does_not_use_unbounded_path_reads(self) -> None:
        def copy_proxy_state(argv: tuple[str, ...]) -> None:
            if argv[:2] != ("sbx", "exec") or "cp" not in argv:
                return
            target = Path(argv[-1])
            (target / "config.toml").write_text(
                DOCKER_CODEX_PROXY_CONFIG,
                encoding="utf-8",
            )
            (target / "auth.json").write_text(
                DOCKER_CODEX_PROXY_AUTH,
                encoding="utf-8",
            )

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

            with mock.patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("unbounded pathname read used"),
            ):
                runtime._initialize_codex_home_unchecked(worker, case)

    def test_proxy_profile_replacement_at_handoff_is_rejected(self) -> None:
        replaced = False

        def copy_or_replace_proxy_state(argv: tuple[str, ...]) -> None:
            nonlocal replaced
            if argv[:2] != ("sbx", "exec"):
                return
            if "cp" in argv:
                target = Path(argv[-1])
                (target / "config.toml").write_text(
                    DOCKER_CODEX_PROXY_CONFIG,
                    encoding="utf-8",
                )
                (target / "auth.json").write_text(
                    DOCKER_CODEX_PROXY_AUTH,
                    encoding="utf-8",
                )
                return
            if (
                len(argv) > 7
                and argv[5] == "chown"
                and argv[-2].endswith("/config.toml")
                and argv[-1].endswith("/auth.json")
                and not replaced
            ):
                config_path = Path(argv[-2])
                parked = config_path.with_name("config.toml.parked")
                config_path.rename(parked)
                config_path.write_text(
                    DOCKER_CODEX_PROXY_CONFIG,
                    encoding="utf-8",
                )
                replaced = True

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
            ],
            side_effect=copy_or_replace_proxy_state,
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

            with self.assertRaisesRegex(
                SandboxRuntimeError,
                "changed before profile handoff",
            ):
                runtime._initialize_codex_home_unchecked(worker, case)

            self.assertTrue(replaced)

    def test_rejects_noncanonical_docker_codex_config_on_first_handoff(self) -> None:
        cases = {
            "unexpected comment": DOCKER_CODEX_PROXY_CONFIG
            + "# unexpected first-case comment\n",
            "alternate whitespace": DOCKER_CODEX_PROXY_CONFIG.replace(
                'approval_policy = "never"',
                'approval_policy="never"',
            ),
            "alternate ordering": DOCKER_CODEX_PROXY_CONFIG.replace(
                'approval_policy = "never"\nsandbox_mode = "danger-full-access"',
                'sandbox_mode = "danger-full-access"\napproval_policy = "never"',
            ),
            "opaque suffix": DOCKER_CODEX_PROXY_CONFIG + "opaque-suffix",
            "unexpected trailing byte": DOCKER_CODEX_PROXY_CONFIG + " ",
            "non-UTF-8 byte": DOCKER_CODEX_PROXY_CONFIG.encode("utf-8") + b"\xff",
        }

        for label, config in cases.items():
            with self.subTest(label=label):
                self._assert_codex_proxy_profile_rejected_before_handoff(
                    config=config,
                    auth=DOCKER_CODEX_PROXY_AUTH,
                    error_pattern="config bytes do not match",
                )

    def test_rejects_noncanonical_docker_codex_auth_on_first_handoff(self) -> None:
        cases = {
            "alternate whitespace": '{"OPENAI_API_KEY":"proxy-managed"}\n',
            "alternate indentation": '{\n    "OPENAI_API_KEY": "proxy-managed"\n}\n',
            "missing final newline": DOCKER_CODEX_PROXY_AUTH.removesuffix("\n"),
            "opaque suffix": DOCKER_CODEX_PROXY_AUTH + "opaque-suffix",
            "unexpected trailing byte": DOCKER_CODEX_PROXY_AUTH + " ",
            "non-UTF-8 byte": DOCKER_CODEX_PROXY_AUTH.encode("utf-8") + b"\xff",
        }

        for label, auth in cases.items():
            with self.subTest(label=label):
                self._assert_codex_proxy_profile_rejected_before_handoff(
                    config=DOCKER_CODEX_PROXY_CONFIG,
                    auth=auth,
                    error_pattern="placeholder bytes do not match",
                )

    def test_rejects_unexpected_docker_codex_config_before_profile_handoff(self) -> None:
        cases = {
            "provider": DOCKER_CODEX_PROXY_CONFIG
            + "\n[model_providers.unexpected]\nbase_url = \"https://example.invalid\"\n",
            "endpoint": DOCKER_CODEX_PROXY_CONFIG.replace(
                "https://chatgpt.com/backend-api/codex",
                "https://example.invalid/backend-api/codex",
            ),
            "headers": DOCKER_CODEX_PROXY_CONFIG
            + "\n[model_providers.sandboxd.http_headers]\nAuthorization = \"opaque-value\"\n",
            "mcp": DOCKER_CODEX_PROXY_CONFIG
            + "\n[mcp_servers.unexpected]\ncommand = \"credential-reader\"\n",
            "tool": "web_search = \"live\"\n" + DOCKER_CODEX_PROXY_CONFIG,
            "unknown": "unexpected = \"value\"\n" + DOCKER_CODEX_PROXY_CONFIG,
            "malformed type": DOCKER_CODEX_PROXY_CONFIG.replace(
                'requires_openai_auth = false',
                'requires_openai_auth = "false"',
            ),
        }

        for label, config in cases.items():
            with self.subTest(label=label):
                with mock.patch(
                    "scripts.ai_skills_lib.sandbox_runtime."
                    "_PINNED_DOCKER_CODEX_CONFIG_BYTES",
                    config.encode("utf-8"),
                ):
                    self._assert_codex_proxy_profile_rejected_before_handoff(
                        config=config,
                        auth=DOCKER_CODEX_PROXY_AUTH,
                    )

    def test_rejects_unexpected_docker_codex_auth_before_profile_handoff(self) -> None:
        cases = {
            "opaque token": '{"OPENAI_API_KEY": "opaque-value-1234567890"}',
            "unknown": '{"OPENAI_API_KEY": "proxy-managed", "unexpected": "value"}',
            "malformed value type": '{"OPENAI_API_KEY": 123}',
            "malformed root type": '[{"OPENAI_API_KEY": "proxy-managed"}]',
            "duplicate field": (
                '{"OPENAI_API_KEY": "opaque-value", '
                '"OPENAI_API_KEY": "proxy-managed"}'
            ),
        }

        for label, auth in cases.items():
            with self.subTest(label=label):
                with mock.patch(
                    "scripts.ai_skills_lib.sandbox_runtime."
                    "_PINNED_DOCKER_CODEX_AUTH_BYTES",
                    auth.encode("utf-8"),
                ):
                    self._assert_codex_proxy_profile_rejected_before_handoff(
                        config=DOCKER_CODEX_PROXY_CONFIG,
                        auth=auth,
                    )

    def test_keeps_profile_digest_immutable_after_raw_and_shape_validation(self) -> None:
        def copy_proxy_state(argv: tuple[str, ...]) -> None:
            if argv[:2] != ("sbx", "exec") or "cp" not in argv:
                return
            target = Path(argv[-1])
            (target / "config.toml").write_text(
                DOCKER_CODEX_PROXY_CONFIG,
                encoding="utf-8",
            )
            (target / "auth.json").write_text(
                DOCKER_CODEX_PROXY_AUTH,
                encoding="utf-8",
            )

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
                completed(json.dumps({"sandboxes": []})),
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
            runtime._proxy_state_digests[worker.id] = ("0" * 64, "0" * 64)

            with self.assertRaisesRegex(SandboxRuntimeError, "changed between cases"):
                runtime.initialize_codex_home(worker, case)

        profile_handoffs = [
            argv
            for argv, _ in process.calls
            if argv[:7]
            == (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "chown",
                f"{case.uid}:{case.uid}",
            )
        ]
        self.assertEqual(len(profile_handoffs), 1)

    def _assert_codex_proxy_profile_rejected_before_handoff(
        self,
        *,
        config: str | bytes,
        auth: str | bytes,
        error_pattern: str = "Docker-generated",
    ) -> None:
        def copy_proxy_state(argv: tuple[str, ...]) -> None:
            if argv[:2] != ("sbx", "exec") or "cp" not in argv:
                return
            target = Path(argv[-1])
            config_bytes = config.encode("utf-8") if isinstance(config, str) else config
            auth_bytes = auth.encode("utf-8") if isinstance(auth, str) else auth
            (target / "config.toml").write_bytes(config_bytes)
            (target / "auth.json").write_bytes(auth_bytes)

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
                completed(json.dumps({"sandboxes": []})),
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

            with self.assertRaisesRegex(SandboxRuntimeError, error_pattern):
                runtime.initialize_codex_home(worker, case)

        profile_handoff_prefix = (
            "sbx",
            "exec",
            "--user",
            "root",
            "ai-skills-unit-test-actor-1",
            "chown",
            f"{case.uid}:{case.uid}",
        )
        self.assertFalse(
            any(argv[:7] == profile_handoff_prefix for argv, _ in process.calls)
        )

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

            runtime.seal_skill_catalog(worker, case)
            runtime.execute(worker, case, ("true",), timeout_seconds=30)

        commands = [argv for argv, _ in process.calls]
        wrapped_commands = [
            wrapped
            for argv in commands
            if (wrapped := cgroup_wrapped_case_command(argv)) is not None
        ]
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "chown",
                "-R",
                "root:root",
                str(case.skills),
            ),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "chown",
                "-R",
                f"{case.uid}:{case.uid}",
                str(case.skills / ".system"),
            ),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "chmod",
                "0700",
                str(case.skills / ".system"),
            ),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
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
                ("test", "-w", str(writable_path)),
                wrapped_commands,
            )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
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
                "ai-skills-unit-test-actor-1",
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
                "ai-skills-unit-test-actor-1",
                "chmod",
                "1777",
                str(case.codex_home),
            ),
            commands,
        )
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-actor-1",
                "chmod",
                "1777",
                str(case.skills),
            ),
            commands,
        )
        self.assertIn(
            (
                "python3",
                "-c",
                PUBLIC_SKILL_CATALOG_PROBE_SCRIPT,
                str(case.skills),
            ),
            wrapped_commands,
        )
        rename_probes = {
            (wrapped[-2], wrapped[-1])
            for wrapped in wrapped_commands
            if wrapped[:3] == ("python3", "-c", CATALOG_RENAME_PROBE_SCRIPT)
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

    def test_seals_the_judge_skill_catalog_empty_and_read_only(self) -> None:
        process = FakeProcessRunner(
            [
                completed(),
                completed(
                    json.dumps(
                        {
                            "sandboxes": [
                                {
                                    "id": "judge-id",
                                    "name": "ai-skills-unit-test-judge-1",
                                }
                            ]
                        }
                    )
                ),
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
            worker = runtime.acquire_worker("judge")
            case = runtime.prepare_case(worker, "case-one")

            runtime.seal_skill_catalog(worker, case)
            runtime.execute(worker, case, ("true",), timeout_seconds=30)

        commands = [argv for argv, _ in process.calls]
        wrapped_commands = [
            wrapped
            for argv in commands
            if (wrapped := cgroup_wrapped_case_command(argv)) is not None
        ]
        self.assertIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-judge-1",
                "chmod",
                "0555",
                str(case.skills),
                str(case.skills / ".system"),
            ),
            commands,
        )
        self.assertNotIn(
            (
                "sbx",
                "exec",
                "--user",
                "root",
                "ai-skills-unit-test-judge-1",
                "chmod",
                "1777",
                str(case.skills),
            ),
            commands,
        )
        self.assertIn(
            (
                "python3",
                "-c",
                DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT,
                str(case.skills / ".judge-write-probe"),
            ),
            wrapped_commands,
        )
        self.assertIn(
            (
                "python3",
                "-c",
                DIRECTORY_WRITE_DENIAL_PROBE_SCRIPT,
                str(case.skills / ".system" / ".judge-write-probe"),
            ),
            wrapped_commands,
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

    def test_empty_listings_never_authorize_unknown_create_evidence_deletion(self) -> None:
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

            with self.assertRaisesRegex(SandboxRuntimeError, "authoritative"):
                runtime.acquire_worker("actor")
            target = runtime._cleanup_targets["ai-skills-unit-test-actor-1"]
            self.assertTrue(target.host_root.exists())
            self.assertTrue(target.ownership_marker.is_file())
            self.assertFalse(runtime.sandbox_cleanup_completed)

        self.assertEqual(
            [argv[:2] for argv, _ in process.calls],
            [("sbx", "ls"), ("sbx", "create"), ("sbx", "ls"), ("sbx", "ls")],
        )


if __name__ == "__main__":
    unittest.main()
