from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from scripts.ai_skills_lib import codex_harness
from scripts.ai_skills_lib.codex_harness import (
    CodexHarnessAdapter,
    CodexOutputError,
    project_actor_skill,
)
from scripts.ai_skills_lib.harness import (
    ActorInput,
    HarnessArtifactBinding,
    HarnessRequest,
    PreparedFile,
    bind_harness_request,
)
from scripts.ai_skills_lib.fixture_proxy import FixtureProxyError, FixtureSession
from scripts.ai_skills_lib.sandbox_runtime import (
    CaseWorkspace,
    CommandResult,
    EvalRuntimeManifest,
    PreflightReport,
    SandboxWorker,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = EvalRuntimeManifest.load(REPOSITORY_ROOT / "config" / "eval-runtime.json")
EXAMPLE_SKILL_CONTENT = "---\nname: example\n---\nFollow me.\n"


def bound_harness_request(**kwargs: object) -> HarnessRequest:
    arguments = dict(kwargs)
    arguments["skill_sources"] = tuple(
        source
        if not isinstance(source, Path)
        else codex_harness.prepare_actor_skill_source(source)
        for source in arguments.get("skill_sources", ())
    )
    fixture_root = arguments.get("fixture_root")
    if isinstance(fixture_root, Path):
        arguments["actor_inputs"] = tuple(
            actor_input
            if actor_input.prepared is not None
            else codex_harness.prepare_actor_input(
                actor_input.source,
                actor_input.destination,
                fixture_root,
            )
            for actor_input in arguments.get("actor_inputs", ())
        )
        fixture_initialization = arguments.get("fixture_initialization")
        if isinstance(fixture_initialization, Path):
            arguments["fixture_initialization"] = (
                codex_harness.prepare_fixture_initialization(
                    fixture_initialization,
                    fixture_root,
                )
            )
    request = HarnessRequest(**arguments)
    return bind_harness_request(
        request,
        invocation_id="0" * 32,
        run_id=f"unit-{request.run_variant}",
    )


def prepare_bound_artifact_directory(path: Path) -> HarnessArtifactBinding:
    outputs = path / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    attempt = path.stat()
    output = outputs.stat()
    repository = REPOSITORY_ROOT.stat()
    return HarnessArtifactBinding(
        attempt_identity=(attempt.st_dev, attempt.st_ino, attempt.st_mode),
        outputs_identity=(output.st_dev, output.st_ino, output.st_mode),
        repository_identity=(repository.st_dev, repository.st_ino),
    )


def command_result(stdout: str = "", *, returncode: int = 0, stderr: str = "", timed_out: bool = False):
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
    )


def codex_jsonl(
    expected_skill_path: Path | None = None,
    *,
    skill_output: str = EXAMPLE_SKILL_CONTENT,
) -> str:
    events: list[dict[str, object]] = [
        {"type": "thread.started", "thread_id": "private-thread-id"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": "working"}},
    ]
    if expected_skill_path is not None:
        command = (
            f"/bin/bash -c \"/usr/bin/sed -n '1,240p' {expected_skill_path}\""
        )
        events.extend(
            [
                {
                    "type": "item.started",
                    "item": {
                        "id": "command-1",
                        "type": "command_execution",
                        "command": command,
                        "status": "in_progress",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "command-1",
                        "type": "command_execution",
                        "command": command,
                        "exit_code": 0,
                        "status": "completed",
                        "aggregated_output": skill_output,
                    },
                },
            ]
        )
    events.extend(
        [
            {
                "type": "item.completed",
                "item": {"id": "message-2", "type": "agent_message", "text": "final response"},
            },
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 20,
                    "cached_input_tokens": 7,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 2,
                },
            },
        ]
    )
    return "\n".join(json.dumps(event) for event in events) + "\n"


def create_case_fixture(root: Path) -> tuple[Path, Path, Path]:
    skills_root = root / "skills"
    fixture_root = (
        skills_root / "integrations" / "example" / "evals" / "fixtures" / "case"
    )
    fixture_root.mkdir(parents=True)
    initialization = fixture_root / "mockserverInitialization.json"
    initialization.write_text("[]", encoding="utf-8")
    return skills_root, fixture_root, initialization


class FakeSandboxRuntime:
    def __init__(self, state: Path, execution_results: list[CommandResult] | None = None) -> None:
        self.manifest = MANIFEST
        self.state = state
        self.results_root = state / "results"
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.execution_results = list(execution_results or [])
        self.calls: list[tuple[SandboxWorker, CaseWorkspace, tuple[str, ...], int, dict[str, str]]] = []
        self.worker = SandboxWorker(
            id="worker-id",
            name="unit-worker",
            role="actor",
            slot=0,
            host_root=state / "worker",
        )
        self.last_case: CaseWorkspace | None = None
        self.invalidated_workers: list[SandboxWorker] = []
        self.quiesced_cases: list[tuple[SandboxWorker, CaseWorkspace]] = []
        self.sealed_catalogs: list[tuple[SandboxWorker, CaseWorkspace]] = []
        self.case_sequence = 0
        self.remove_case_on_lease_release = False
        self.quiesce_error: Exception | None = None
        self.projection_protected = False
        self.lifecycle_events: list[str] = []

    def preflight(self) -> PreflightReport:
        return PreflightReport(available=True, details=("runtime ready",))

    def acquire_worker(self, role: str, slot: int = 0) -> SandboxWorker:
        if role != self.worker.role:
            self.worker = SandboxWorker(
                id=f"{role}-id",
                name=f"unit-{role}",
                role=role,
                slot=slot,
                host_root=self.state / role,
            )
        self.worker.host_root.mkdir(parents=True, exist_ok=True)
        return self.worker

    @contextmanager
    def lease_worker(self, role: str):
        try:
            yield self.acquire_worker(role)
        finally:
            if self.remove_case_on_lease_release and self.last_case is not None:
                for root, directories, _ in os.walk(self.last_case.root):
                    Path(root).chmod(0o755)
                    for name in directories:
                        (Path(root) / name).chmod(0o755)
                shutil.rmtree(self.last_case.root)

    def prepare_case(self, worker: SandboxWorker, case_id: str) -> CaseWorkspace:
        self.lifecycle_events.append(f"prepare:{case_id}")
        self.projection_protected = False
        self.case_sequence += 1
        root = worker.host_root / "case"
        root.mkdir(parents=True, exist_ok=True)
        home = root / "home"
        codex_home = root / "codex-home"
        tmpdir = root / "tmp"
        workspace = root / "workspace"
        skills = codex_home / "skills"
        bootstrap = root / "bootstrap"
        for path in (home, codex_home, tmpdir, workspace, skills, bootstrap):
            path.mkdir(parents=True, exist_ok=True)
        (skills / ".system").mkdir(exist_ok=True)
        self.last_case = CaseWorkspace(
            case_id=case_id,
            root=root,
            home=home,
            codex_home=codex_home,
            tmpdir=tmpdir,
            workspace=workspace,
            skills=skills,
            bootstrap=bootstrap,
            user_name=f"ai-eval-{self.case_sequence}",
            uid=20000 + self.case_sequence,
        )
        return self.last_case

    def initialize_codex_home(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        (case.codex_home / "config.toml").write_text(
            'model_provider = "sandboxd"\n[model_providers.sandboxd]\nbase_url = "http://host-proxy"\n',
            encoding="utf-8",
        )
        (case.codex_home / "auth.json").write_text(
            json.dumps({"auth_mode": "host-proxy-placeholder"}),
            encoding="utf-8",
        )

    def seal_skill_catalog(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self.sealed_catalogs.append((worker, case))
        case.skills.chmod(0o555)

    def invalidate_worker(self, worker: SandboxWorker) -> None:
        self.lifecycle_events.append("invalidate")
        self.projection_protected = False
        self.invalidated_workers.append(worker)

    def quiesce_case(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self.lifecycle_events.append(f"quiesce:{case.case_id}")
        self.quiesced_cases.append((worker, case))
        if self.quiesce_error is not None:
            raise self.quiesce_error
        self.projection_protected = False

    def mutate_worker_host(self, worker: SandboxWorker, path: Path) -> None:
        if self.projection_protected and path.is_relative_to(worker.host_root):
            raise OSError(errno.EROFS, "read-only worker projection", path)
        self.lifecycle_events.append(f"mutate:{path.relative_to(worker.host_root)}")

    def execute(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        argv: tuple[str, ...],
        *,
        timeout_seconds: int,
        environment: dict[str, str] | None = None,
    ) -> CommandResult:
        self.lifecycle_events.append(f"execute:{case.case_id}:{argv[0]}")
        self.projection_protected = True
        self.calls.append((worker, case, argv, timeout_seconds, dict(environment or {})))
        if argv == ("fixture-probe",):
            return command_result()
        if not self.execution_results:
            raise AssertionError(f"unexpected execution: {argv!r}")
        return self.execution_results.pop(0)


class FakeFixtureProxy:
    def __init__(self, runtime: FakeSandboxRuntime | None = None) -> None:
        self.runtime = runtime
        self.prepared: list[tuple[SandboxWorker, CaseWorkspace, Path, Path]] = []
        self.collected: list[tuple[SandboxWorker, CaseWorkspace, FixtureSession]] = []
        self.discarded: list[SandboxWorker] = []
        self.collect_error: BaseException | None = None
        self.preflighted: list[tuple[SandboxWorker, CaseWorkspace]] = []
        self.retired_preflights: list[SandboxWorker] = []
        self.retire_error: Exception | None = None

    def preflight(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self.preflighted.append((worker, case))
        if self.runtime is not None:
            self.runtime.lifecycle_events.append("fixture-probe")
            self.runtime.execute(
                worker,
                case,
                ("fixture-probe",),
                timeout_seconds=1,
            )

    def retire_preflight(self, worker: SandboxWorker) -> None:
        if self.runtime is not None:
            self.runtime.mutate_worker_host(
                worker,
                worker.host_root / "fixture-control",
            )
            self.runtime.lifecycle_events.append("fixture-retire")
        self.retired_preflights.append(worker)
        if self.retire_error is not None:
            raise self.retire_error

    def prepare_case(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        initialization_path: Path,
        case_fixture_root: Path,
    ) -> FixtureSession:
        self.prepared.append((worker, case, initialization_path, case_fixture_root))
        return FixtureSession(
            worker_id=worker.id,
            case_id=case.case_id,
            definition_sha256="a" * 64,
            public_ca_sha256="b" * 64,
            shell_environment=(
                ("HTTPS_PROXY", "http://127.0.0.1:1080"),
                ("SSL_CERT_FILE", str(case.bootstrap / "mockserver-ca.pem")),
            ),
        )

    def collect_and_reset(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        session: FixtureSession,
    ) -> tuple[dict[str, object], ...]:
        self.collected.append((worker, case, session))
        if self.collect_error is not None:
            raise self.collect_error
        return (
            {
                "event": "fixture_request",
                "method": "GET",
                "host": "api.example.com",
                "path": "/v1/example",
            },
        )

    def discard_worker_state(self, worker: SandboxWorker) -> None:
        self.discarded.append(worker)


class SkillProjectionTests(unittest.TestCase):
    def test_projects_only_runtime_entries_and_omits_evals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example"
            destination = root / "projection" / "example"
            (source / "scripts").mkdir(parents=True)
            (source / "references").mkdir()
            (source / "assets").mkdir()
            (source / "evals").mkdir()
            (source / "SKILL.md").write_text("---\nname: example\n---\nUse the script.\n", encoding="utf-8")
            (source / "scripts" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (source / "scripts" / "run.sh").chmod(0o755)
            (source / "references" / "guide.md").write_text("Guide\n", encoding="utf-8")
            (source / "assets" / "template.txt").write_text("Template\n", encoding="utf-8")
            (source / "evals" / "evals.json").write_text('{"private": true}\n', encoding="utf-8")

            project_actor_skill(source, destination)

            self.assertEqual(
                {path.name for path in destination.iterdir()},
                {"SKILL.md", "scripts", "references", "assets"},
            )
            self.assertFalse((destination / "evals").exists())
            self.assertEqual((destination / "scripts" / "run.sh").stat().st_mode & 0o777, 0o555)
            self.assertEqual((destination / "SKILL.md").stat().st_mode & 0o777, 0o444)

    def test_rejects_symlinks_and_runtime_references_to_evals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example"
            source.mkdir()
            (source / "SKILL.md").write_text("Read evals/evals.json.\n", encoding="utf-8")
            with self.assertRaisesRegex(CodexOutputError, "evals"):
                project_actor_skill(source, root / "first")

            (source / "SKILL.md").write_text("Safe instructions.\n", encoding="utf-8")
            (source / "scripts").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(CodexOutputError, "symlink"):
                project_actor_skill(source, root / "second")

    def test_rejects_assets_that_reference_eval_oracle_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example"
            (source / "assets").mkdir(parents=True)
            (source / "SKILL.md").write_text("Safe instructions.\n", encoding="utf-8")
            (source / "assets" / "instructions.txt").write_text(
                "Read ../evals/evals.json.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(CodexOutputError, "evals"):
                project_actor_skill(source, root / "projection")

    def test_allows_external_urls_containing_an_evals_path_segment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example"
            source.mkdir()
            (source / "SKILL.md").write_text(
                "See https://docs.example.test/evals/authoring-guide.\n",
                encoding="utf-8",
            )

            project_actor_skill(source, root / "projection")

            self.assertTrue((root / "projection" / "SKILL.md").is_file())

    def test_prepared_projection_uses_frozen_bytes_after_source_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example"
            source.mkdir()
            skill_path = source / "SKILL.md"
            original = b"---\nname: example\n---\nOriginal instructions.\n"
            skill_path.write_bytes(original)
            prepared = codex_harness.prepare_actor_skill_source(source)
            skill_path.write_text("mutated after preparation\n", encoding="utf-8")

            destination = root / "projection" / "example"
            codex_harness.project_prepared_actor_skill(prepared, destination)

            self.assertEqual((destination / "SKILL.md").read_bytes(), original)

    def test_prepared_projection_uses_frozen_bytes_after_source_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "example"
            source.mkdir()
            original = b"---\nname: example\n---\nOriginal instructions.\n"
            (source / "SKILL.md").write_bytes(original)
            prepared = codex_harness.prepare_actor_skill_source(source)
            shutil.rmtree(source)

            destination = root / "projection" / "example"
            codex_harness.project_prepared_actor_skill(prepared, destination)

            self.assertEqual((destination / "SKILL.md").read_bytes(), original)


class ActorWorkspaceCaptureTests(unittest.TestCase):
    def snapshot(self, workspace: Path, **overrides):
        limits = {
            "maximum_bytes": 1024,
            "maximum_file_bytes": 1024,
            "maximum_entries": 16,
            "maximum_directories": 8,
            "maximum_depth": 4,
        }
        limits.update(overrides)
        return codex_harness._snapshot_actor_workspace(workspace, **limits)

    def test_snapshot_enforces_entry_directory_and_depth_limits(self) -> None:
        cases = (
            ("entry-count", {"maximum_entries": 1}, ("a.txt", "b.txt")),
            ("directory-count", {"maximum_directories": 2}, ("a/", "b/")),
            ("depth", {"maximum_depth": 1}, ("a/b.txt",)),
        )
        for label, limits, entries in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                for relative in entries:
                    path = workspace / relative.rstrip("/")
                    if relative.endswith("/"):
                        path.mkdir(parents=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("x", encoding="utf-8")

                with self.assertRaisesRegex(CodexOutputError, "limit"):
                    self.snapshot(workspace, **limits)

    def test_snapshot_enforces_per_file_and_cumulative_byte_limits(self) -> None:
        cases = (
            ("per-file", {"maximum_file_bytes": 1}, (b"xx",)),
            ("cumulative", {"maximum_bytes": 1}, (b"x", b"y")),
        )
        for label, limits, contents in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                for index, content in enumerate(contents):
                    (workspace / f"{index}.bin").write_bytes(content)

                with self.assertRaisesRegex(CodexOutputError, "byte limit"):
                    self.snapshot(workspace, **limits)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFOs")
    def test_snapshot_rejects_special_files_without_reading_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            os.mkfifo(workspace / "pipe")

            with self.assertRaisesRegex(CodexOutputError, "special files"):
                self.snapshot(workspace)

    def test_snapshot_rejects_a_file_replaced_between_stat_and_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            artifact = workspace / "artifact.txt"
            artifact.write_text("original", encoding="utf-8")
            real_open = os.open
            replaced = False

            def replace_before_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal replaced
                if path == artifact.name and dir_fd is not None and not replaced:
                    artifact.unlink()
                    artifact.write_text("replacement", encoding="utf-8")
                    replaced = True
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with mock.patch.object(codex_harness.os, "open", side_effect=replace_before_open):
                with self.assertRaisesRegex(CodexOutputError, "changed while snapshotting"):
                    self.snapshot(workspace)

    def test_snapshot_rejects_a_file_mutated_during_descriptor_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            artifact = workspace / "artifact.txt"
            artifact.write_bytes(b"a" * 128)
            real_read = os.read
            mutated = False

            def mutate_after_read(file_descriptor: int, size: int) -> bytes:
                nonlocal mutated
                content = real_read(file_descriptor, size)
                if content and not mutated:
                    artifact.write_bytes(b"b" * 128)
                    mutated = True
                return content

            with mock.patch.object(codex_harness.os, "read", side_effect=mutate_after_read):
                with self.assertRaisesRegex(CodexOutputError, "changed while snapshotting"):
                    self.snapshot(workspace)

    def test_snapshot_rejects_a_directory_changed_after_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "existing.txt").write_text("stable", encoding="utf-8")
            real_scandir = os.scandir

            @contextmanager
            def mutate_after_enumeration(directory_descriptor: int):
                with real_scandir(directory_descriptor) as iterator:
                    yield iterator
                (workspace / "late.txt").write_text("late", encoding="utf-8")

            with mock.patch.object(
                codex_harness.os,
                "scandir",
                side_effect=mutate_after_enumeration,
            ):
                with self.assertRaisesRegex(CodexOutputError, "changed while snapshotting"):
                    self.snapshot(workspace)

    def test_snapshot_rejects_a_file_changed_before_path_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            artifact = workspace / "artifact.txt"
            artifact.write_bytes(b"original")
            real_stat = os.stat
            mutated = False

            def mutate_before_path_stat(path, *, dir_fd=None, follow_symlinks=True):
                nonlocal mutated
                if path == artifact.name and dir_fd is not None and not mutated:
                    artifact.write_bytes(b"changed!")
                    mutated = True
                return real_stat(
                    path,
                    dir_fd=dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with mock.patch.object(
                codex_harness.os,
                "stat",
                side_effect=mutate_before_path_stat,
            ):
                with self.assertRaisesRegex(CodexOutputError, "changed while snapshotting"):
                    self.snapshot(workspace)

    def test_capture_reserves_response_file_and_entire_subtree(self) -> None:
        for relative in ("response.md", "response.md/evidence.txt"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workspace = root / "workspace"
                output_root = root / "results" / "outputs"
                workspace.mkdir()
                initial = self.snapshot(workspace)
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("actor-owned\n", encoding="utf-8")

                with self.assertRaisesRegex(CodexOutputError, "response.md"):
                    codex_harness._capture_actor_outputs(
                        workspace,
                        output_root,
                        initial,
                        maximum_bytes=1024,
                    )

    def test_capture_rejects_a_new_empty_response_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output_root = root / "results" / "outputs"
            workspace.mkdir()
            initial = self.snapshot(workspace)
            (workspace / "response.md").mkdir()

            with self.assertRaisesRegex(CodexOutputError, "response.md"):
                codex_harness._capture_actor_outputs(
                    workspace,
                    output_root,
                    initial,
                    maximum_bytes=1024,
                )

    def test_capture_omits_unchanged_inputs_in_the_reserved_namespace(self) -> None:
        for relative in ("response.md", "response.md/context.txt"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workspace = root / "workspace"
                output_root = root / "results" / "outputs"
                workspace.mkdir()
                reserved_input = workspace / relative
                reserved_input.parent.mkdir(parents=True, exist_ok=True)
                reserved_input.write_text("unchanged input\n", encoding="utf-8")
                initial = self.snapshot(workspace)
                (workspace / "result.txt").write_text("actor output\n", encoding="utf-8")

                codex_harness._capture_actor_outputs(
                    workspace,
                    output_root,
                    initial,
                    maximum_bytes=1024,
                )

                self.assertEqual(
                    (output_root / "result.txt").read_text(encoding="utf-8"),
                    "actor output\n",
                )
                self.assertFalse((output_root / "response.md").exists())

    def test_capture_records_new_empty_directories_from_descriptor_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output_root = root / "results" / "outputs"
            workspace.mkdir()
            initial = self.snapshot(workspace)
            (workspace / "empty-result").mkdir()

            captured = codex_harness._capture_actor_outputs(
                workspace,
                output_root,
                initial,
                maximum_bytes=1024,
            )

            self.assertTrue((output_root / "empty-result").is_dir())
            self.assertIn(
                (PurePosixPath("empty-result"), "directory"),
                tuple((item.path, item.kind) for item in captured.paths),
            )

    def test_capture_quarantines_secret_bytes_with_bounded_references(self) -> None:
        credential = "gh" + "p_" + ("a" * 36)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output_root = root / "results" / "outputs"
            workspace.mkdir()
            initial = self.snapshot(
                workspace,
                maximum_bytes=4096,
                maximum_entries=64,
            )
            for index in range(24):
                (workspace / f"result-{index:02d}.txt").write_text(
                    credential,
                    encoding="utf-8",
                )

            captured = codex_harness._capture_actor_outputs(
                workspace,
                output_root,
                initial,
                maximum_bytes=4096,
            )

            durable = b"".join(
                path.read_bytes() for path in sorted(output_root.iterdir())
            )
            serialized_trace = json.dumps(captured.trace)
            secret_event = next(
                event
                for event in captured.trace
                if event.get("event") == "actor_output_secret_quarantine"
            )
            self.assertNotIn(credential.encode("utf-8"), durable)
            self.assertNotIn(credential, serialized_trace)
            self.assertIsNotNone(captured.failure)
            self.assertTrue(secret_event["finding_count_truncated"])
            self.assertLessEqual(
                len(secret_event["references"]),
                codex_harness.MAX_SECRET_EVIDENCE_REFERENCES,
            )
            self.assertTrue(
                all(
                    path.read_text(encoding="utf-8").startswith("[QUARANTINED")
                    for path in output_root.iterdir()
                )
            )

    def test_quarantined_low_entropy_secret_omits_original_size_and_digest(self) -> None:
        secret_content = b"Cookie: session=abc\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output_root = root / "results" / "outputs"
            workspace.mkdir()
            initial = self.snapshot(workspace)
            (workspace / "result.txt").write_bytes(secret_content)

            captured = codex_harness._capture_actor_outputs(
                workspace,
                output_root,
                initial,
                maximum_bytes=1024,
            )

            file_event = next(
                event
                for event in captured.trace
                if event.get("event") == "actor_output"
                and event.get("kind") == "file"
            )
            serialized_trace = json.dumps(captured.trace)
            self.assertTrue(file_event["quarantined"])
            self.assertNotIn("bytes", file_event)
            self.assertNotIn("sha256", file_event)
            self.assertNotIn(
                hashlib.sha256(secret_content).hexdigest(),
                serialized_trace,
            )
            self.assertTrue(
                (output_root / "result.txt")
                .read_text(encoding="utf-8")
                .startswith("[QUARANTINED")
            )

    def test_capture_redacts_secret_material_from_durable_paths(self) -> None:
        credential = "gh" + "p_" + ("a" * 36)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output_root = root / "results" / "outputs"
            workspace.mkdir()
            initial = self.snapshot(workspace)
            (workspace / credential).write_text("otherwise safe", encoding="utf-8")

            captured = codex_harness._capture_actor_outputs(
                workspace,
                output_root,
                initial,
                maximum_bytes=1024,
            )

            durable_paths = tuple(
                path.relative_to(output_root).as_posix()
                for path in output_root.rglob("*")
            )
            self.assertIsNotNone(captured.failure)
            self.assertNotIn(credential, json.dumps(captured.trace))
            self.assertTrue(all(credential not in path for path in durable_paths))
            self.assertTrue(
                any(path.startswith(".secret-quarantine-") for path in durable_paths)
            )

    def test_capture_rejects_changes_and_deletions_in_the_reserved_subtree(self) -> None:
        for action in ("modify", "delete"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                workspace = root / "workspace"
                output_root = root / "results" / "outputs"
                reserved_input = workspace / "response.md" / "context.txt"
                reserved_input.parent.mkdir(parents=True)
                reserved_input.write_text("original input\n", encoding="utf-8")
                initial = self.snapshot(workspace)
                if action == "modify":
                    reserved_input.write_text("changed input\n", encoding="utf-8")
                else:
                    reserved_input.unlink()

                with self.assertRaisesRegex(CodexOutputError, "response.md"):
                    codex_harness._capture_actor_outputs(
                        workspace,
                        output_root,
                        initial,
                        maximum_bytes=1024,
                    )

    def test_capture_rejects_destination_relocated_inside_repository_before_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()
            initial = self.snapshot(workspace)
            (workspace / "result.txt").write_text(
                "actor output\n",
                encoding="utf-8",
            )
            external_parent = root / "external"
            output_root = external_parent / "attempt" / "outputs"
            output_root.mkdir(parents=True)
            attempt = output_root.parent.stat()
            outputs = output_root.stat()
            repository_stat = repository.stat()
            binding = HarnessArtifactBinding(
                attempt_identity=(
                    attempt.st_dev,
                    attempt.st_ino,
                    attempt.st_mode,
                ),
                outputs_identity=(
                    outputs.st_dev,
                    outputs.st_ino,
                    outputs.st_mode,
                ),
                repository_identity=(
                    repository_stat.st_dev,
                    repository_stat.st_ino,
                ),
            )
            real_write = codex_harness._write_captured_workspace_file
            relocated = repository / "external"
            redirected = False

            def redirect_after_staging(destination, record):
                nonlocal redirected
                real_write(destination, record)
                if not redirected:
                    external_parent.rename(relocated)
                    external_parent.symlink_to(
                        relocated,
                        target_is_directory=True,
                    )
                    redirected = True

            with mock.patch.object(
                codex_harness,
                "_write_captured_workspace_file",
                side_effect=redirect_after_staging,
            ):
                with self.assertRaises(CodexOutputError):
                    codex_harness._capture_actor_outputs(
                        workspace,
                        output_root,
                        initial,
                        maximum_bytes=1024,
                        artifact_binding=binding,
                    )

            self.assertTrue(redirected)
            self.assertEqual(
                tuple((relocated / "attempt" / "outputs").iterdir()),
                (),
            )


class CodexHarnessAdapterTests(unittest.TestCase):
    def test_execute_requires_a_runner_created_execution_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeSandboxRuntime(Path(directory))
            adapter = CodexHarnessAdapter(runtime)
            request = HarnessRequest(
                role="actor",
                run_variant="unbound",
                prompt="Perform the scenario.",
                timeout_seconds=60,
            )

            with self.assertRaisesRegex(CodexOutputError, "execution binding"):
                adapter.execute(request, runtime.results_root / "unbound")

        self.assertEqual(runtime.case_sequence, 0)

    def test_execute_rejects_a_request_changed_after_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeSandboxRuntime(Path(directory))
            adapter = CodexHarnessAdapter(runtime)
            request = bound_harness_request(
                role="actor",
                run_variant="bound",
                prompt="Perform the original scenario.",
                timeout_seconds=60,
            )

            with self.assertRaisesRegex(CodexOutputError, "execution binding"):
                adapter.execute(
                    replace(request, prompt="Perform a different scenario."),
                    runtime.results_root / "changed",
                )

        self.assertEqual(runtime.case_sequence, 0)

    def test_execute_rejects_live_path_material_after_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                EXAMPLE_SKILL_CONTENT,
                encoding="utf-8",
            )
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skill.parent)
            request = bind_harness_request(
                HarnessRequest(
                    role="actor",
                    run_variant="live-path",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    skill_sources=(skill,),
                    expected_skill="example",
                ),
                invocation_id="c" * 32,
                run_id="live-path",
            )

            with self.assertRaisesRegex(CodexOutputError, "prepared skill bytes"):
                adapter.execute(request, runtime.results_root / "live-path")

        self.assertEqual(runtime.case_sequence, 0)

    def test_preflight_reports_pinned_codex_and_discovered_defaults(self) -> None:
        models = {
            "models": [
                {
                    "slug": "configured-model",
                    "default_reasoning_level": "high",
                    "visibility": "list",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeSandboxRuntime(
                Path(directory),
                [
                    command_result("codex-cli 0.142.4\n"),
                    command_result("--json --ephemeral --ignore-rules --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox"),
                    command_result(json.dumps(models)),
                ],
            )
            adapter = CodexHarnessAdapter(runtime)

            capabilities = adapter.preflight()

        self.assertTrue(capabilities.available)
        self.assertEqual(capabilities.actor_model, "configured-model")
        self.assertEqual(capabilities.actor_reasoning_effort, "high")
        self.assertEqual(capabilities.judge_model, "configured-model")
        self.assertEqual(capabilities.judge_reasoning_effort, "high")
        self.assertEqual(runtime.case_sequence, 2)
        self.assertEqual([call[2][0:2] for call in runtime.calls], [("codex", "--version"), ("codex", "exec"), ("codex", "debug")])

    def test_execution_does_not_report_preflight_defaults_as_observed_metadata(
        self,
    ) -> None:
        models = {
            "models": [
                {
                    "slug": "configured-model",
                    "default_reasoning_level": "high",
                    "visibility": "list",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeSandboxRuntime(
                Path(directory),
                [
                    command_result("codex-cli 0.142.4\n"),
                    command_result(
                        "--json --ephemeral --ignore-rules "
                        "--skip-git-repo-check "
                        "--dangerously-bypass-approvals-and-sandbox"
                    ),
                    command_result(json.dumps(models)),
                ],
            )
            adapter = CodexHarnessAdapter(runtime)
            capabilities = adapter.preflight()
            runtime.execution_results.append(
                command_result(codex_jsonl())
            )

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="implicit-default",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "implicit-default",
            )

        self.assertTrue(capabilities.available)
        self.assertIsNone(execution.model)
        self.assertIsNone(execution.reasoning_effort)

    def test_preflight_proves_fixture_runtime_before_fixture_cases_are_scheduled(self) -> None:
        models = {
            "models": [
                {
                    "slug": "configured-model",
                    "default_reasoning_level": "high",
                    "visibility": "list",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeSandboxRuntime(
                Path(directory),
                [
                    command_result("codex-cli 0.142.4\n"),
                    command_result(
                        "--json --ephemeral --ignore-rules --skip-git-repo-check "
                        "--dangerously-bypass-approvals-and-sandbox"
                    ),
                    command_result(json.dumps(models)),
                ],
            )
            fixture_proxy = FakeFixtureProxy(runtime)
            adapter = CodexHarnessAdapter(runtime, fixture_proxy=fixture_proxy)

            capabilities = adapter.preflight(require_fixtures=True)

        self.assertTrue(capabilities.available, capabilities.failure)
        self.assertEqual(len(fixture_proxy.preflighted), 1)
        fixture_case = fixture_proxy.preflighted[0][1]
        self.assertEqual(fixture_case.case_id, "fixture-preflight")
        self.assertEqual(runtime.quiesced_cases, [(runtime.worker, fixture_case)])
        self.assertEqual(fixture_proxy.retired_preflights, [runtime.worker])
        codex_cases = [call[1] for call in runtime.calls if call[2][0] == "codex"]
        self.assertEqual({case.case_id for case in codex_cases}, {"codex-preflight"})
        self.assertTrue(all(case is not fixture_case for case in codex_cases))
        self.assertEqual(
            runtime.lifecycle_events,
            [
                "prepare:fixture-preflight",
                "fixture-probe",
                "execute:fixture-preflight:fixture-probe",
                "quiesce:fixture-preflight",
                "mutate:fixture-control",
                "fixture-retire",
                "prepare:codex-preflight",
                "execute:codex-preflight:codex",
                "execute:codex-preflight:codex",
                "execute:codex-preflight:codex",
                "prepare:preflight-reset",
            ],
        )

    def test_fixture_preflight_quiescence_failure_invalidates_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeSandboxRuntime(Path(directory))
            runtime.quiesce_error = RuntimeError("case reset failed")
            fixture_proxy = FakeFixtureProxy(runtime)
            adapter = CodexHarnessAdapter(runtime, fixture_proxy=fixture_proxy)

            capabilities = adapter.preflight(require_fixtures=True)

        self.assertFalse(capabilities.available)
        self.assertIn("case reset failed", capabilities.failure or "")
        self.assertEqual(runtime.invalidated_workers, [runtime.worker])
        self.assertEqual(fixture_proxy.discarded, [runtime.worker])
        self.assertEqual(fixture_proxy.retired_preflights, [])

    def test_fixture_preflight_retirement_failure_invalidates_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = FakeSandboxRuntime(Path(directory))
            fixture_proxy = FakeFixtureProxy(runtime)
            fixture_proxy.retire_error = FixtureProxyError(
                "fixture sidecar cleanup failed"
            )
            adapter = CodexHarnessAdapter(runtime, fixture_proxy=fixture_proxy)

            capabilities = adapter.preflight(require_fixtures=True)

        self.assertFalse(capabilities.available)
        self.assertIn("fixture sidecar cleanup failed", capabilities.failure or "")
        self.assertEqual(runtime.invalidated_workers, [runtime.worker])
        self.assertEqual(fixture_proxy.discarded, [runtime.worker])
        self.assertEqual(fixture_proxy.retired_preflights, [runtime.worker])

    def test_execute_projects_skill_invokes_pinned_flags_and_normalizes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(EXAMPLE_SKILL_CONTENT, encoding="utf-8")
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skill.parent)
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "candidate")
            expected_path = case.skills / "example" / "SKILL.md"
            runtime.execution_results.append(command_result(codex_jsonl(expected_path)))
            request = bound_harness_request(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
                skill_sources=(skill,),
                expected_skill="example",
            )
            artifact_dir = runtime.results_root / "with-skill"

            execution = adapter.execute(request, artifact_dir)
            projected_skill_exists = expected_path.is_file()
            logical_expected_path = Path(
                "/case/codex-home/skills/example/SKILL.md"
            )

        self.assertEqual(execution.response, "final response")
        self.assertEqual(execution.total_tokens, 25)
        self.assertEqual(execution.input_tokens, 20)
        self.assertEqual(execution.output_tokens, 5)
        self.assertEqual(execution.cached_tokens, 7)
        self.assertEqual(execution.execution_binding, request.execution_binding)
        self.assertEqual(
            execution.successful_skill_reads,
            (logical_expected_path,),
        )
        self.assertEqual(execution.expected_skill_path, logical_expected_path)
        self.assertEqual(
            tuple(
                event.get("path")
                for event in execution.trace
                if event.get("event") == "skill_read"
            ),
            (str(logical_expected_path),),
        )
        self.assertNotIn(str(expected_path.parent.parent.parent), json.dumps(execution.trace))
        self.assertNotIn(EXAMPLE_SKILL_CONTENT, json.dumps(execution.trace))
        self.assertNotIn("private-thread-id", json.dumps(execution.trace))
        codex_argv = runtime.calls[-1][2]
        for flag in MANIFEST.codex.exec_flags:
            self.assertIn(flag, codex_argv)
        self.assertIn("allow_login_shell=false", codex_argv)
        self.assertEqual(codex_argv[-2:], ("--", "Perform the scenario."))
        self.assertNotIn("--ignore-user-config", codex_argv)
        self.assertTrue(projected_skill_exists)
        self.assertEqual(len(runtime.sealed_catalogs), 1)

    def test_actor_command_keeps_the_manifest_dangerous_profile_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            adapter = CodexHarnessAdapter(runtime)

            adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="actor-profile",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "actor-profile",
            )

        command = runtime.calls[-1][2]
        expected_command = ["codex", "exec", *MANIFEST.codex.exec_flags]
        expected_command.extend(("-c", "allow_login_shell=false"))
        expected_command.extend(("-c", "shell_environment_policy.inherit=core"))
        expected_command.extend(
            ("-c", "shell_environment_policy.ignore_default_excludes=false")
        )
        expected_command.extend(
            ("-c", 'shell_environment_policy.set.BASH_ENV="/dev/null"')
        )
        expected_command.extend(
            ("-c", 'shell_environment_policy.set.ENV="/dev/null"')
        )
        for feature in codex_harness.DISABLED_FEATURES:
            expected_command.extend(("--disable", feature))
        expected_command.extend(
            (
                "-C",
                str(runtime.last_case.workspace),
                "--",
                "Perform the scenario.",
            )
        )
        self.assertEqual(command, tuple(expected_command))

    def test_judge_stages_schema_and_uses_a_restricted_codex_profile(self) -> None:
        response_schema = {
            "type": "object",
            "properties": {"passed": {"type": "boolean"}},
            "required": ["passed"],
            "additionalProperties": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            adapter = CodexHarnessAdapter(runtime)
            observed_schema: dict[str, object] = {}
            original_execute = runtime.execute

            def inspect_judge_profile(*args, **kwargs):
                command = args[2]
                schema_path = Path(command[command.index("--output-schema") + 1])
                metadata = schema_path.lstat()
                observed_schema.update(
                    {
                        "path": schema_path,
                        "is_regular": stat.S_ISREG(metadata.st_mode),
                        "is_symlink": schema_path.is_symlink(),
                        "mode": stat.S_IMODE(metadata.st_mode),
                        "uid": metadata.st_uid,
                        "document": json.loads(schema_path.read_text(encoding="utf-8")),
                    }
                )
                return original_execute(*args, **kwargs)

            runtime.execute = inspect_judge_profile
            adapter.execute(
                bound_harness_request(
                    role="judge",
                    run_variant="semantic-grade",
                    prompt="Grade the supplied evidence.",
                    timeout_seconds=30,
                    response_schema=response_schema,
                ),
                runtime.results_root / "judge-profile",
            )

            command = runtime.calls[-1][2]
            schema_path = Path(observed_schema["path"])
            self.assertEqual(schema_path.parent, runtime.last_case.workspace)

        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        for flag in MANIFEST.codex.exec_flags:
            if flag != "--dangerously-bypass-approvals-and-sandbox":
                self.assertIn(flag, command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertTrue(observed_schema["is_regular"])
        self.assertFalse(observed_schema["is_symlink"])
        self.assertEqual(observed_schema["mode"] & 0o222, 0)
        if hasattr(os, "geteuid"):
            self.assertEqual(observed_schema["uid"], os.geteuid())
        self.assertEqual(observed_schema["document"], response_schema)

        config_overrides = tuple(
            command[index + 1]
            for index, value in enumerate(command[:-1])
            if value == "-c"
        )
        for override in (
            'approval_policy="never"',
            "features.shell_tool=false",
            'web_search="disabled"',
            "tools.web_search=false",
            "features.remote_plugin=false",
            "features.skill_mcp_dependency_install=false",
            "skills.bundled.enabled=false",
            "skills.include_instructions=false",
        ):
            self.assertIn(override, config_overrides)
        developer_override = next(
            value
            for value in config_overrides
            if value.startswith("developer_instructions=")
        )
        developer_instructions = json.loads(developer_override.split("=", 1)[1])
        self.assertIn("untrusted", developer_instructions)
        self.assertIn("ignore", developer_instructions.lower())
        self.assertIn("only supplied evidence", developer_instructions)
        self.assertIn("requested schema", developer_instructions)
        self.assertIn("oracle", developer_instructions)

    def test_judge_fails_when_codex_populates_the_skill_catalog(self) -> None:
        class BundledSkillRuntime(FakeSandboxRuntime):
            def execute(self, worker, case, argv, **kwargs):
                result = super().execute(worker, case, argv, **kwargs)
                if argv[:2] == ("codex", "exec"):
                    case.skills.chmod(0o755)
                    bundled = case.skills / ".system" / "bundled-skill"
                    bundled.mkdir(parents=True)
                    (bundled / "SKILL.md").write_text(
                        "Bundled judge instructions.\n",
                        encoding="utf-8",
                    )
                    case.skills.chmod(0o555)
                return result

        response_schema = {
            "type": "object",
            "properties": {"passed": {"type": "boolean"}},
            "required": ["passed"],
            "additionalProperties": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            runtime = BundledSkillRuntime(
                Path(directory),
                [command_result(codex_jsonl())],
            )
            execution = CodexHarnessAdapter(runtime).execute(
                bound_harness_request(
                    role="judge",
                    run_variant="bundled-skill-check",
                    prompt="Grade the supplied evidence.",
                    timeout_seconds=30,
                    response_schema=response_schema,
                ),
                runtime.results_root / "bundled-skill-check",
            )

        self.assertIn(
            "judge skill catalog must contain only an empty .system directory",
            execution.failure or "",
        )
        self.assertEqual(runtime.invalidated_workers, [runtime.worker])

    def test_judge_requires_a_valid_closed_response_schema_before_worker_setup(self) -> None:
        invalid_schemas = (
            None,
            {"type": "not-a-json-schema-type"},
            {"$ref": "https://example.com/remote-schema.json"},
        )
        for response_schema in invalid_schemas:
            with self.subTest(response_schema=response_schema), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime = FakeSandboxRuntime(root)
                adapter = CodexHarnessAdapter(runtime)

                with self.assertRaisesRegex(CodexOutputError, "judge response schema"):
                    adapter.execute(
                        bound_harness_request(
                            role="judge",
                            run_variant="semantic-grade",
                            prompt="Grade the supplied evidence.",
                            timeout_seconds=30,
                            response_schema=response_schema,
                        ),
                        runtime.results_root / "judge-invalid-schema",
                    )

                self.assertEqual(runtime.case_sequence, 0)
                self.assertEqual(runtime.calls, [])

    def test_judge_schema_enforces_the_fixed_byte_limit_before_worker_setup(self) -> None:
        response_schema = {
            "type": "object",
            "description": "x" * codex_harness.MAX_JSON_SCHEMA_BYTES,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root)

            with self.assertRaisesRegex(ValueError, "256 KiB byte limit"):
                bound_harness_request(
                    role="judge",
                    run_variant="oversized-schema",
                    prompt="Grade the supplied evidence.",
                    timeout_seconds=30,
                    response_schema=response_schema,
                )

            self.assertEqual(runtime.case_sequence, 0)
            self.assertEqual(runtime.calls, [])

    def test_judge_schema_resource_failures_are_bounded_domain_errors(self) -> None:
        response_schema = {"type": "object", "additionalProperties": False}
        failures = (
            (
                codex_harness,
                "strict_bounded_json_loads",
                MemoryError(),
            ),
            (
                codex_harness,
                "build_safe_json_schema_validator",
                SystemError("schema allocator failed"),
            ),
        )
        for owner, attribute, resource_error in failures:
            with self.subTest(resource_error=type(resource_error).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime = FakeSandboxRuntime(root)
                request = bound_harness_request(
                    role="judge",
                    run_variant="resource-failure",
                    prompt="Grade the supplied evidence.",
                    timeout_seconds=30,
                    response_schema=response_schema,
                )
                with mock.patch.object(owner, attribute, side_effect=resource_error):
                    with self.assertRaises(CodexOutputError) as raised:
                        CodexHarnessAdapter(runtime).execute(
                            request,
                            runtime.results_root / "resource-failure",
                        )

                self.assertIn("judge response schema", str(raised.exception))
                self.assertLess(len(str(raised.exception)), 128)
                self.assertEqual(runtime.case_sequence, 0)
                self.assertEqual(runtime.calls, [])

    def test_captures_only_created_or_modified_actor_workspace_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills" / "workflows" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: example\n---\nFollow me.\n",
                encoding="utf-8",
            )
            fixture_root = skill / "evals" / "fixtures" / "case"
            inputs = fixture_root / "inputs"
            inputs.mkdir(parents=True)
            unchanged = inputs / "request.md"
            changed = inputs / "draft.md"
            unchanged.write_text("request\n", encoding="utf-8")
            changed.write_text("draft\n", encoding="utf-8")
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=root / "skills")
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "candidate")
            expected_path = case.skills / "example" / "SKILL.md"
            runtime.execution_results.append(command_result(codex_jsonl(expected_path)))
            original_execute = runtime.execute

            def execute_with_outputs(*args, **kwargs):
                selected_case = args[1]
                (selected_case.workspace / "draft.md").write_text(
                    "completed\n", encoding="utf-8"
                )
                generated = selected_case.workspace / "reports" / "result.json"
                generated.parent.mkdir()
                generated.write_text('{"ok": true}\n', encoding="utf-8")
                return original_execute(*args, **kwargs)

            runtime.execute = execute_with_outputs
            artifact_dir = runtime.results_root / "with-skill"
            artifact_binding = prepare_bound_artifact_directory(
                artifact_dir
            )

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="candidate",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    skill_sources=(skill,),
                    expected_skill="example",
                    actor_inputs=(
                        ActorInput(unchanged, PurePosixPath("request.md")),
                        ActorInput(changed, PurePosixPath("draft.md")),
                    ),
                    fixture_root=fixture_root,
                    capture_outputs=True,
                    artifact_binding=artifact_binding,
                ),
                artifact_dir,
            )
            outputs = artifact_dir / "outputs"
            self.assertFalse((outputs / "request.md").exists())
            self.assertEqual((outputs / "draft.md").read_text(), "completed\n")
            self.assertEqual(
                (outputs / "reports" / "result.json").read_text(),
                '{"ok": true}\n',
            )
            self.assertIn(
                "actor_output", {event.get("event") for event in execution.trace}
            )

    def test_actor_output_capture_rejects_reserved_or_unsafe_files(self) -> None:
        for output_kind in ("reserved", "symlink"):
            with self.subTest(output_kind=output_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
                adapter = CodexHarnessAdapter(runtime)
                original_execute = runtime.execute

                def execute_with_unsafe_output(*args, **kwargs):
                    selected_case = args[1]
                    if output_kind == "reserved":
                        (selected_case.workspace / "response.md").write_text(
                            "collision\n", encoding="utf-8"
                        )
                    else:
                        (selected_case.workspace / "escape").symlink_to(root)
                    return original_execute(*args, **kwargs)

                runtime.execute = execute_with_unsafe_output
                artifact_dir = runtime.results_root / output_kind
                artifact_binding = prepare_bound_artifact_directory(
                    artifact_dir
                )

                execution = adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant=output_kind,
                        prompt="Perform the scenario.",
                        timeout_seconds=60,
                        capture_outputs=True,
                        artifact_binding=artifact_binding,
                    ),
                    artifact_dir,
                )
                self.assertIn("actor output capture", execution.failure or "")
                self.assertFalse(any((artifact_dir / "outputs").iterdir()))

    def test_actor_output_secret_is_quarantined_and_marks_execution_untrustworthy(self) -> None:
        credential = "gh" + "p_" + ("a" * 36)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            adapter = CodexHarnessAdapter(runtime)
            original_execute = runtime.execute

            def execute_with_secret_output(*args, **kwargs):
                selected_case = args[1]
                (selected_case.workspace / "result.txt").write_text(
                    credential,
                    encoding="utf-8",
                )
                return original_execute(*args, **kwargs)

            runtime.execute = execute_with_secret_output
            artifact_dir = runtime.results_root / "secret-output"
            artifact_binding = prepare_bound_artifact_directory(artifact_dir)

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="secret-output",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    capture_outputs=True,
                    artifact_binding=artifact_binding,
                ),
                artifact_dir,
            )

            durable = (artifact_dir / "outputs" / "result.txt").read_text(
                encoding="utf-8"
            )
            serialized_trace = json.dumps(execution.trace)
            self.assertIn("high-confidence secret", execution.failure or "")
            self.assertTrue(durable.startswith("[QUARANTINED"))
            self.assertNotIn(credential, durable)
            self.assertNotIn(credential, serialized_trace)

    def test_actor_workspace_rejects_oversized_file_before_reading_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            (workspace / "large.bin").write_bytes(b"1234")

            with mock.patch.object(
                codex_harness.os,
                "read",
                side_effect=AssertionError("oversized file must not be read"),
            ):
                with self.assertRaisesRegex(CodexOutputError, "per-file byte limit"):
                    codex_harness._snapshot_actor_workspace(
                        workspace,
                        maximum_bytes=100,
                        maximum_file_bytes=3,
                    )

    def test_initial_actor_workspace_limit_fails_before_codex_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skills" / "workflows" / "example"
            fixture_root = skill / "evals" / "fixtures" / "case"
            inputs = fixture_root / "inputs"
            inputs.mkdir(parents=True)
            source = inputs / "large.bin"
            source.write_bytes(b"12345")
            runtime = FakeSandboxRuntime(root)
            runtime.manifest = replace(
                runtime.manifest,
                limits=replace(
                    runtime.manifest.limits,
                    maximum_captured_output_bytes=4,
                ),
            )
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=root / "skills")
            artifact_dir = runtime.results_root / "candidate"
            artifact_binding = prepare_bound_artifact_directory(artifact_dir)

            with self.assertRaisesRegex(CodexOutputError, "byte limit"):
                adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="candidate",
                        prompt="Perform the scenario.",
                        timeout_seconds=60,
                        actor_inputs=(
                            ActorInput(source, PurePosixPath("large.bin")),
                        ),
                        fixture_root=fixture_root,
                        capture_outputs=True,
                        artifact_binding=artifact_binding,
                    ),
                    artifact_dir,
                )

            self.assertEqual(runtime.calls, [])

    def test_actor_output_capture_fails_closed_when_source_mutates_during_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            output_root = root / "results" / "outputs"
            workspace.mkdir()
            source = workspace / "result.txt"
            source.write_bytes(b"original")
            real_read = os.read
            mutated = False

            def read_then_mutate(descriptor: int, count: int) -> bytes:
                nonlocal mutated
                chunk = real_read(descriptor, count)
                if chunk and not mutated:
                    mutated = True
                    source.write_bytes(b"changed-content")
                return chunk

            with mock.patch.object(
                codex_harness.os,
                "read",
                side_effect=read_then_mutate,
            ):
                with self.assertRaisesRegex(CodexOutputError, "changed while being read"):
                    codex_harness._capture_actor_outputs(
                        workspace,
                        output_root,
                        {},
                        maximum_bytes=100,
                    )

            self.assertTrue(output_root.is_dir())
            self.assertFalse(any(output_root.iterdir()))

    def test_finalizes_skill_read_evidence_before_releasing_the_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: example\n---\nFollow me.\n", encoding="utf-8")
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skill.parent)
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "candidate")
            expected_path = case.skills / "example" / "SKILL.md"
            runtime.execution_results.append(command_result(codex_jsonl(expected_path)))
            runtime.remove_case_on_lease_release = True

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="candidate",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    skill_sources=(skill,),
                    expected_skill="example",
                ),
                runtime.results_root / "with-skill",
            )

        self.assertEqual(
            execution.successful_skill_reads,
            (Path("/case/codex-home/skills/example/SKILL.md"),),
        )

    def test_expected_projection_integrity_is_verified_even_without_a_skill_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: example\n---\nFollow me.\n",
                encoding="utf-8",
            )
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skill.parent)
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "candidate")
            expected_path = case.skills / "example" / "SKILL.md"
            runtime.execution_results.append(command_result(codex_jsonl()))
            original_quiesce = runtime.quiesce_case

            def remove_projection(
                selected_worker: SandboxWorker,
                selected_case: CaseWorkspace,
            ) -> None:
                original_quiesce(selected_worker, selected_case)
                selected_case.skills.chmod(0o755)
                expected_path.parent.chmod(0o755)
                expected_path.unlink()

            runtime.quiesce_case = remove_projection

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="candidate",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    skill_sources=(skill,),
                    expected_skill="example",
                ),
                runtime.results_root / "without-read",
            )

        self.assertIn("projected SKILL.md changed", execution.failure or "")
        self.assertEqual(execution.successful_skill_reads, ())

    def test_timeout_cleanup_is_not_reported_as_projection_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: example\n---\nFollow me.\n",
                encoding="utf-8",
            )
            runtime = FakeSandboxRuntime(
                root,
                [command_result("", returncode=124, timed_out=True)],
            )
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skill.parent)
            original_execute = runtime.execute

            def execute_and_remove_projection(*args, **kwargs):
                result = original_execute(*args, **kwargs)
                assert runtime.last_case is not None
                for directory_path, child_directories, _ in os.walk(runtime.last_case.root):
                    Path(directory_path).chmod(0o755)
                    for child in child_directories:
                        (Path(directory_path) / child).chmod(0o755)
                shutil.rmtree(runtime.last_case.root)
                return result

            runtime.execute = execute_and_remove_projection

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="candidate",
                    prompt="Perform the scenario.",
                    timeout_seconds=1,
                    skill_sources=(skill,),
                    expected_skill="example",
                ),
                runtime.results_root / "timeout",
            )

        self.assertTrue(execution.timed_out)
        self.assertNotIn("projected SKILL.md changed", execution.failure or "")
        self.assertFalse(
            any(event.get("event") == "projection_integrity_failure" for event in execution.trace)
        )

    def test_lifecycle_invalidation_is_not_reported_as_projection_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: example\n---\nFollow me.\n",
                encoding="utf-8",
            )
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            runtime.quiesce_error = RuntimeError("case reset failed")
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skill.parent)
            original_invalidate = runtime.invalidate_worker

            def invalidate_and_remove_projection(worker: SandboxWorker) -> None:
                original_invalidate(worker)
                assert runtime.last_case is not None
                for directory_path, child_directories, _ in os.walk(runtime.last_case.root):
                    Path(directory_path).chmod(0o755)
                    for child in child_directories:
                        (Path(directory_path) / child).chmod(0o755)
                shutil.rmtree(runtime.last_case.root)

            runtime.invalidate_worker = invalidate_and_remove_projection

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="candidate",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    skill_sources=(skill,),
                    expected_skill="example",
                ),
                runtime.results_root / "lifecycle-failure",
            )

        self.assertIn("post-execution lifecycle failed: case reset failed", execution.failure or "")
        self.assertNotIn("projected SKILL.md changed", execution.failure or "")
        self.assertFalse(
            any(event.get("event") == "projection_integrity_failure" for event in execution.trace)
        )

    def test_fixture_environment_is_applied_only_to_codex_shell_subprocesses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            adapter = CodexHarnessAdapter(runtime)
            request = bound_harness_request(
                role="actor",
                run_variant="fixture",
                prompt="Call the fixture API.",
                timeout_seconds=60,
                shell_environment=(
                    ("HTTPS_PROXY", "http://127.0.0.1:1080"),
                    ("SSL_CERT_FILE", "/case/bootstrap/mockserver-ca.pem"),
                ),
            )

            adapter.execute(request, runtime.results_root / "fixture")

        codex_argv = runtime.calls[-1][2]
        self.assertIn(
            'shell_environment_policy.set.HTTPS_PROXY="http://127.0.0.1:1080"',
            codex_argv,
        )
        self.assertIn(
            'shell_environment_policy.set.SSL_CERT_FILE="/case/bootstrap/mockserver-ca.pem"',
            codex_argv,
        )
        self.assertEqual(runtime.calls[-1][4], {})

    def test_stages_only_declared_actor_input_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root = root / "skills"
            input_root = skills_root / "workflows" / "example" / "evals" / "fixtures" / "case" / "inputs"
            input_root.mkdir(parents=True)
            declared = input_root / "request.md"
            undeclared = input_root / "oracle.md"
            declared.write_text("actor input\n", encoding="utf-8")
            undeclared.write_text("hidden oracle\n", encoding="utf-8")
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skills_root)

            adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="fixture-input",
                    prompt="Use request.md.",
                    timeout_seconds=60,
                    actor_inputs=(
                        ActorInput(
                            source=declared,
                            destination=PurePosixPath("request.md"),
                        ),
                    ),
                    fixture_root=input_root.parent,
                ),
                runtime.results_root / "fixture-input",
            )
            workspace = runtime.last_case.workspace
            staged_content = (workspace / "request.md").read_text(encoding="utf-8")
            undeclared_exists = (workspace / "oracle.md").exists()

        self.assertEqual(staged_content, "actor input\n")
        self.assertFalse(undeclared_exists)

    def test_exposes_declared_bin_commands_on_the_actor_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            skills_root = root / "skills"
            input_root = (
                skills_root
                / "workflows"
                / "example"
                / "evals"
                / "fixtures"
                / "case"
                / "inputs"
            )
            command = input_root / "bin" / "gh"
            command.parent.mkdir(parents=True)
            command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            command.chmod(0o755)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skills_root)

            adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="fixture-command",
                    prompt="Use the available gh command.",
                    timeout_seconds=60,
                    actor_inputs=(
                        ActorInput(
                            source=command,
                            destination=PurePosixPath("bin/gh"),
                            prepared=PreparedFile(
                                source=command,
                                content=command.read_bytes(),
                                executable=True,
                            ),
                        ),
                    ),
                    fixture_root=input_root.parent,
                ),
                runtime.results_root / "fixture-command",
            )

        actor_path = (
            f"{runtime.last_case.workspace}/bin:"
            f"{codex_harness.ACTOR_BASE_PATH}"
        )
        self.assertIn(
            f"shell_environment_policy.set.PATH={json.dumps(actor_path)}",
            runtime.calls[-1][2],
        )
        self.assertEqual(runtime.calls[-1][4], {})

    def test_does_not_add_non_executable_bin_inputs_to_the_actor_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root = root / "skills"
            input_root = (
                skills_root
                / "workflows"
                / "example"
                / "evals"
                / "fixtures"
                / "case"
                / "inputs"
            )
            data_file = input_root / "bin" / "command-contract.txt"
            data_file.parent.mkdir(parents=True)
            data_file.write_text("documentation only\n", encoding="utf-8")
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skills_root)

            adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="fixture-data",
                    prompt="Read bin/command-contract.txt.",
                    timeout_seconds=60,
                    actor_inputs=(
                        ActorInput(
                            source=data_file,
                            destination=PurePosixPath("bin/command-contract.txt"),
                        ),
                    ),
                    fixture_root=input_root.parent,
                ),
                runtime.results_root / "fixture-data",
            )

        self.assertFalse(
            any("shell_environment_policy.set.PATH=" in part for part in runtime.calls[-1][2])
        )

    def test_rejects_actor_inputs_outside_the_declared_fixture_input_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root = root / "skills"
            fixture_root = (
                skills_root / "workflows" / "example" / "evals" / "fixtures" / "case"
            )
            (fixture_root / "inputs").mkdir(parents=True)
            outside = root / "outside.md"
            outside.write_text("outside\n", encoding="utf-8")
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skills_root)

            with self.assertRaisesRegex(CodexOutputError, "fixture source"):
                adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="fixture-input",
                        prompt="Use the input.",
                        timeout_seconds=60,
                        actor_inputs=(
                            ActorInput(
                                source=outside,
                                destination=PurePosixPath("outside.md"),
                            ),
                        ),
                        fixture_root=fixture_root,
                    ),
                    runtime.results_root / "outside-input",
                )

        self.assertEqual(runtime.calls, [])

    def test_rejects_actor_input_from_a_sibling_fixture_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root = root / "skills"
            selected_root = (
                skills_root / "workflows" / "example" / "evals" / "fixtures" / "selected"
            )
            sibling_root = selected_root.parent / "sibling"
            selected_root.mkdir(parents=True)
            sibling_inputs = sibling_root / "inputs"
            sibling_inputs.mkdir(parents=True)
            sibling_input = sibling_inputs / "request.md"
            sibling_input.write_text("wrong case\n", encoding="utf-8")
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skills_root)

            with self.assertRaisesRegex(CodexOutputError, "case fixture root"):
                adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="selected",
                        prompt="Use the input.",
                        timeout_seconds=60,
                        actor_inputs=(
                            ActorInput(
                                source=sibling_input,
                                destination=PurePosixPath("request.md"),
                            ),
                        ),
                        fixture_root=selected_root,
                    ),
                    runtime.results_root / "sibling-input",
                )

        self.assertEqual(runtime.calls, [])

    def test_rejects_fixture_initialization_from_a_sibling_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root = root / "skills"
            selected_root = (
                skills_root / "integrations" / "example" / "evals" / "fixtures" / "selected"
            )
            sibling_root = selected_root.parent / "sibling"
            selected_root.mkdir(parents=True)
            sibling_root.mkdir()
            sibling_fixture = sibling_root / "mockserverInitialization.json"
            sibling_fixture.write_text("[]", encoding="utf-8")
            runtime = FakeSandboxRuntime(root)
            fixture_proxy = FakeFixtureProxy()
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=skills_root,
                fixture_proxy=fixture_proxy,
            )

            with self.assertRaisesRegex(CodexOutputError, "case fixture root"):
                adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="selected",
                        prompt="Call the fixture API.",
                        timeout_seconds=60,
                        fixture_root=selected_root,
                        fixture_initialization=sibling_fixture,
                    ),
                    runtime.results_root / "sibling-fixture",
                )

        self.assertEqual(fixture_proxy.prepared, [])

    def test_fixture_is_prepared_and_collected_inside_the_same_codex_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root, fixture_root, fixture = create_case_fixture(root)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            fixture_proxy = FakeFixtureProxy()
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=skills_root,
                fixture_proxy=fixture_proxy,
            )
            request = bound_harness_request(
                role="actor",
                run_variant="fixture",
                prompt="Call the fixture API.",
                timeout_seconds=60,
                fixture_root=fixture_root,
                fixture_initialization=fixture,
            )

            execution = adapter.execute(request, runtime.results_root / "fixture-owned")

        prepared_worker, prepared_case, prepared_path, prepared_root = fixture_proxy.prepared[0]
        collected_worker, collected_case, _ = fixture_proxy.collected[0]
        self.assertIs(prepared_worker, collected_worker)
        self.assertIs(prepared_case, collected_case)
        self.assertIs(runtime.quiesced_cases[0][1], prepared_case)
        self.assertIsInstance(prepared_path, PreparedFile)
        self.assertEqual(prepared_path.source, fixture.resolve())
        self.assertEqual(prepared_root, fixture_root.resolve())
        self.assertTrue(any(event.get("event") == "fixture_request" for event in execution.trace))
        self.assertIn(
            'shell_environment_policy.set.HTTPS_PROXY="http://127.0.0.1:1080"',
            runtime.calls[-1][2],
        )

    def test_timed_out_fixture_run_recycles_proxy_state_without_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root, fixture_root, fixture = create_case_fixture(root)
            runtime = FakeSandboxRuntime(
                root,
                [command_result(codex_jsonl(), returncode=124, timed_out=True)],
            )
            fixture_proxy = FakeFixtureProxy()
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=skills_root,
                fixture_proxy=fixture_proxy,
            )

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="fixture-timeout",
                    prompt="Call the fixture API.",
                    timeout_seconds=1,
                    fixture_root=fixture_root,
                    fixture_initialization=fixture,
                ),
                runtime.results_root / "fixture-timeout",
            )

        self.assertTrue(execution.timed_out)
        self.assertEqual(runtime.quiesced_cases, [])
        self.assertEqual(fixture_proxy.collected, [])
        self.assertEqual(fixture_proxy.discarded, [runtime.worker])

    def test_preserves_sanitized_fixture_evidence_when_verification_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root, fixture_root, fixture = create_case_fixture(root)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            fixture_proxy = FakeFixtureProxy()
            fixture_proxy.collect_error = FixtureProxyError(
                "fixture request sequence did not match",
                evidence=(
                    {
                        "event": "fixture_request",
                        "method": "GET",
                        "host": "api.example.com",
                        "path": "/unexpected",
                    },
                ),
            )
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=skills_root,
                fixture_proxy=fixture_proxy,
            )

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="fixture-mismatch",
                    prompt="Call the fixture API.",
                    timeout_seconds=60,
                    fixture_root=fixture_root,
                    fixture_initialization=fixture,
                ),
                runtime.results_root / "fixture-mismatch",
            )

        self.assertEqual(execution.response, "final response")
        self.assertTrue(
            any(event.get("path") == "/unexpected" for event in execution.trace)
        )
        self.assertIn("request sequence", execution.failure or "")

    def test_post_capture_interruption_discards_fixture_state_and_recycles_worker(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_root, fixture_root, fixture = create_case_fixture(root)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            fixture_proxy = FakeFixtureProxy()
            fixture_proxy.collect_error = KeyboardInterrupt()
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=skills_root,
                fixture_proxy=fixture_proxy,
            )

            with self.assertRaises(KeyboardInterrupt):
                artifact_dir = runtime.results_root / "fixture-interruption"
                artifact_binding = prepare_bound_artifact_directory(
                    artifact_dir
                )
                adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="fixture-interruption",
                        prompt="Call the fixture API.",
                        timeout_seconds=60,
                        fixture_root=fixture_root,
                        fixture_initialization=fixture,
                        capture_outputs=True,
                        artifact_binding=artifact_binding,
                    ),
                    artifact_dir,
                )

        self.assertIn(runtime.worker, fixture_proxy.discarded)
        self.assertIn(runtime.worker, runtime.invalidated_workers)

    def test_preserves_native_evidence_when_post_execution_cleanup_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            runtime.quiesce_error = RuntimeError("case quiescence failed")
            adapter = CodexHarnessAdapter(runtime)

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="cleanup-failure",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "cleanup-failure",
            )

        self.assertEqual(execution.response, "final response")
        self.assertTrue(any(event.get("event") == "harness_turn_completed" for event in execution.trace))
        self.assertIn("post-execution lifecycle failed", execution.failure or "")
        self.assertIn("case quiescence failed", execution.failure or "")
        self.assertEqual(runtime.invalidated_workers, [runtime.worker])

    def test_fixture_request_requires_a_configured_proxy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, fixture_root, fixture = create_case_fixture(root)
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime)

            with self.assertRaisesRegex(CodexOutputError, "fixture proxy"):
                adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="fixture",
                        prompt="Call the fixture API.",
                        timeout_seconds=60,
                        fixture_root=fixture_root,
                        fixture_initialization=fixture,
                    ),
                    runtime.results_root / "missing-proxy",
                )

    def test_failed_or_ambiguous_commands_are_not_activation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: example\n---\nFollow me.\n",
                encoding="utf-8",
            )
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skill.parent)
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "candidate")
            expected = case.skills / "example" / "SKILL.md"
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": f"cat {expected}",
                        "exit_code": 1,
                        "status": "failed",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": f"echo {expected}",
                        "exit_code": 0,
                        "status": "completed",
                    },
                },
                {"type": "item.completed", "item": {"type": "agent_message", "text": str(expected)}},
                {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
            ]
            runtime.execution_results.append(command_result("\n".join(json.dumps(event) for event in events)))
            request = bound_harness_request(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
                skill_sources=(skill,),
                expected_skill="example",
            )
            artifact_dir = runtime.results_root / "ambiguous"
            artifact_dir.mkdir()

            execution = adapter.execute(request, artifact_dir)

        self.assertEqual(execution.successful_skill_reads, ())

    def test_skill_read_requires_trusted_reader_and_exact_skill_bytes(self) -> None:
        cases = (
            (
                "untrusted reader",
                lambda output: output.replace("/usr/bin/sed", "sed"),
            ),
            (
                "forged output",
                lambda output: output.replace(
                    json.dumps(EXAMPLE_SKILL_CONTENT)[1:-1],
                    json.dumps("forged skill output\n")[1:-1],
                ),
            ),
        )
        for label, mutate in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                skill = root / "source" / "example"
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    EXAMPLE_SKILL_CONTENT,
                    encoding="utf-8",
                )
                runtime = FakeSandboxRuntime(root)
                adapter = CodexHarnessAdapter(
                    runtime,
                    allowed_skill_root=skill.parent,
                )
                worker = runtime.acquire_worker("actor")
                case = runtime.prepare_case(worker, "candidate")
                expected = case.skills / "example" / "SKILL.md"
                runtime.execution_results.append(
                    command_result(mutate(codex_jsonl(expected)))
                )

                execution = adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="candidate",
                        prompt="Perform the scenario.",
                        timeout_seconds=60,
                        skill_sources=(skill,),
                        expected_skill="example",
                    ),
                    runtime.results_root / label.replace(" ", "-"),
                )

            self.assertEqual(execution.successful_skill_reads, ())

    def test_skill_read_requires_matching_started_and_completed_commands(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                EXAMPLE_SKILL_CONTENT,
                encoding="utf-8",
            )
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=skill.parent,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "candidate")
            expected = case.skills / "example" / "SKILL.md"
            events = [
                json.loads(line)
                for line in codex_jsonl(expected).splitlines()
            ]
            for event in events:
                if event.get("type") == "item.started":
                    event["item"]["command"] = (
                        '/bin/bash -c "/bin/echo unrelated"'
                    )
            runtime.execution_results.append(
                command_result(
                    "\n".join(json.dumps(event) for event in events)
                )
            )

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="candidate",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    skill_sources=(skill,),
                    expected_skill="example",
                ),
                runtime.results_root / "command-mismatch",
            )

        self.assertEqual(execution.successful_skill_reads, ())
        self.assertIsNotNone(execution.failure)

    def test_skill_read_requires_an_exact_integer_zero_exit_code(self) -> None:
        for invalid_exit_code in (False, 0.0):
            with (
                self.subTest(exit_code=invalid_exit_code),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                skill = root / "source" / "example"
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    EXAMPLE_SKILL_CONTENT,
                    encoding="utf-8",
                )
                runtime = FakeSandboxRuntime(root)
                adapter = CodexHarnessAdapter(
                    runtime,
                    allowed_skill_root=skill.parent,
                )
                worker = runtime.acquire_worker("actor")
                case = runtime.prepare_case(worker, "candidate")
                expected = case.skills / "example" / "SKILL.md"
                events = [
                    json.loads(line)
                    for line in codex_jsonl(expected).splitlines()
                ]
                for event in events:
                    if event.get("type") == "item.completed" and (
                        event.get("item", {}).get("type")
                        == "command_execution"
                    ):
                        event["item"]["exit_code"] = invalid_exit_code
                runtime.execution_results.append(
                    command_result(
                        "\n".join(json.dumps(event) for event in events)
                    )
                )

                execution = adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="candidate",
                        prompt="Perform the scenario.",
                        timeout_seconds=60,
                        skill_sources=(skill,),
                        expected_skill="example",
                    ),
                    runtime.results_root / "invalid-exit-code",
                )

            self.assertEqual(execution.successful_skill_reads, ())
            self.assertIsNotNone(execution.failure)

    def test_skill_read_completion_requires_a_consistent_terminal_status(
        self,
    ) -> None:
        for label, status_update in (
            ("missing", None),
            ("failed-with-zero-exit", "failed"),
        ):
            with self.subTest(status=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                skill = root / "source" / "example"
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    EXAMPLE_SKILL_CONTENT,
                    encoding="utf-8",
                )
                runtime = FakeSandboxRuntime(root)
                adapter = CodexHarnessAdapter(
                    runtime,
                    allowed_skill_root=skill.parent,
                )
                worker = runtime.acquire_worker("actor")
                case = runtime.prepare_case(worker, "candidate")
                expected = case.skills / "example" / "SKILL.md"
                events = [
                    json.loads(line)
                    for line in codex_jsonl(expected).splitlines()
                ]
                for event in events:
                    item = event.get("item", {})
                    if (
                        event.get("type") == "item.completed"
                        and item.get("type") == "command_execution"
                    ):
                        if status_update is None:
                            item.pop("status", None)
                        else:
                            item["status"] = status_update
                runtime.execution_results.append(
                    command_result(
                        "\n".join(json.dumps(event) for event in events)
                    )
                )

                execution = adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="candidate",
                        prompt="Perform the scenario.",
                        timeout_seconds=60,
                        skill_sources=(skill,),
                        expected_skill="example",
                    ),
                    runtime.results_root / label,
                )

            self.assertEqual(execution.successful_skill_reads, ())
            self.assertIsNotNone(execution.failure)

    def test_skill_read_rejects_noncanonical_path_operands(self) -> None:
        alias_builders = (
            ("parent-segment", lambda expected: f"{expected.parent}/redirect/../SKILL.md"),
            ("current-segment", lambda expected: f"{expected.parent}/./SKILL.md"),
            (
                "duplicate-separator",
                lambda expected: str(expected).replace("/skills/", "/skills//"),
            ),
        )
        for index, (label, build_alias) in enumerate(alias_builders):
            with self.subTest(alias=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                skill = root / "source" / "example"
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    EXAMPLE_SKILL_CONTENT,
                    encoding="utf-8",
                )
                runtime = FakeSandboxRuntime(root)
                adapter = CodexHarnessAdapter(
                    runtime,
                    allowed_skill_root=skill.parent,
                )
                worker = runtime.acquire_worker("actor")
                case = runtime.prepare_case(worker, "candidate")
                expected = case.skills / "example" / "SKILL.md"
                alias = build_alias(expected)
                runtime.execution_results.append(
                    command_result(
                        codex_jsonl(expected).replace(
                            str(expected),
                            alias,
                        )
                    )
                )

                execution = adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant=f"candidate-{index}",
                        prompt="Perform the scenario.",
                        timeout_seconds=60,
                        skill_sources=(skill,),
                        expected_skill="example",
                    ),
                    runtime.results_root / f"noncanonical-{index}",
                )

                self.assertEqual(
                    execution.successful_skill_reads,
                    (),
                )

    def test_skill_read_rejects_untrusted_or_login_shell_wrappers(self) -> None:
        wrappers = ("bash -c", "/tmp/bash -c", "/bin/bash -lc")
        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                skill = root / "source" / "example"
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    EXAMPLE_SKILL_CONTENT,
                    encoding="utf-8",
                )
                runtime = FakeSandboxRuntime(root)
                adapter = CodexHarnessAdapter(
                    runtime,
                    allowed_skill_root=skill.parent,
                )
                worker = runtime.acquire_worker("actor")
                case = runtime.prepare_case(worker, "candidate")
                expected = case.skills / "example" / "SKILL.md"
                output = codex_jsonl(expected).replace("/bin/bash -c", wrapper)
                runtime.execution_results.append(command_result(output))

                execution = adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant="candidate",
                        prompt="Perform the scenario.",
                        timeout_seconds=60,
                        skill_sources=(skill,),
                        expected_skill="example",
                    ),
                    runtime.results_root / wrapper.replace("/", "-").replace(" ", "-"),
                )

            self.assertEqual(execution.successful_skill_reads, ())

    def test_rejects_ambiguous_or_partial_skill_read_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime)
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "candidate")
            expected = case.skills / "example" / "SKILL.md"
            expected.parent.mkdir()
            expected.write_text("line one\nline two\n", encoding="utf-8")
            commands = (
                f"cat --help {expected}",
                f"cat {expected} /tmp/other",
                f"sed -n '2,240p' {expected}",
                f"sed -n '1,1p' {expected}",
            )
            events = [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": command,
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
                for command in commands
            ]
            events.extend(
                [
                    {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
                    {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
                ]
            )
            runtime.execution_results.append(command_result("\n".join(json.dumps(event) for event in events)))
            request = bound_harness_request(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
                expected_skill="example",
            )

            execution = adapter.execute(request, runtime.results_root / "partial")

        self.assertEqual(execution.successful_skill_reads, ())

    def test_marks_truncated_or_incomplete_success_output_untrustworthy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime)
            complete = codex_jsonl()
            runtime.execution_results.extend(
                [
                    CommandResult(
                        returncode=0,
                        stdout=complete,
                        stderr="",
                        stdout_truncated=True,
                    ),
                    command_result(
                        json.dumps(
                            {
                                "type": "item.completed",
                                "item": {"type": "agent_message", "text": "no terminal event"},
                            }
                        )
                    ),
                ]
            )
            request = bound_harness_request(
                role="actor",
                run_variant="candidate-one",
                prompt="Perform the scenario.",
                timeout_seconds=60,
            )

            truncated = adapter.execute(request, runtime.results_root / "truncated")
            incomplete = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="candidate-two",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "incomplete",
            )

        self.assertIn("truncated", truncated.failure or "")
        self.assertIn("turn.completed", incomplete.failure or "")

    def test_rejects_path_escaping_expected_skill_names_before_codex_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime)
            request = bound_harness_request(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
                expected_skill="../outside",
            )

            with self.assertRaisesRegex(CodexOutputError, "path-safe"):
                adapter.execute(request, runtime.results_root / "escape")

        self.assertEqual(runtime.calls, [])

    def test_rejects_durable_artifacts_outside_the_runtime_results_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime)
            request = bound_harness_request(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
            )

            with self.assertRaisesRegex(CodexOutputError, "result"):
                adapter.execute(request, root / "outside-results")

        self.assertEqual(runtime.calls, [])

    def test_native_failure_is_forwarded_bounded_and_secret_redacted(self) -> None:
        events = [
            {"type": "turn.failed", "error": {"message": "upstream said sk-abcdefghijklmnopqrstuvwxyz"}}
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(
                root,
                [
                    command_result(
                        "\n".join(json.dumps(event) for event in events),
                        returncode=1,
                        stderr="native failure sk-abcdefghijklmnopqrstuvwxyz",
                    )
                ],
            )
            adapter = CodexHarnessAdapter(runtime)
            request = bound_harness_request(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
            )
            artifact_dir = runtime.results_root / "native-failure"
            artifact_dir.mkdir()

            execution = adapter.execute(request, artifact_dir)
            raw_artifact_exists = any(path.name.startswith("raw") for path in artifact_dir.iterdir())

        self.assertIsNotNone(execution.failure)
        self.assertIn("native failure", execution.failure or "")
        self.assertNotIn("sk-", execution.failure or "")
        self.assertFalse(raw_artifact_exists)

    def test_successful_status_stderr_does_not_fail_structured_codex_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(
                root,
                [
                    command_result(
                        codex_jsonl(),
                        stderr="Reading additional input from stdin...",
                    )
                ],
            )
            adapter = CodexHarnessAdapter(runtime)
            request = bound_harness_request(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
            )

            execution = adapter.execute(request, runtime.results_root / "status-stderr")

        self.assertIsNone(execution.failure)
        self.assertEqual(execution.exit_code, 0)
        self.assertEqual(execution.response, "final response")

    def test_agent_response_secret_is_redacted_and_marks_execution_untrustworthy(self) -> None:
        credential = "gh" + "p_" + ("a" * 36)
        events = [
            {"type": "thread.started", "thread_id": "private"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "message-1",
                    "type": "agent_message",
                    "text": f"result {credential}",
                },
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(
                root,
                [command_result("\n".join(json.dumps(event) for event in events))],
            )

            execution = CodexHarnessAdapter(runtime).execute(
                bound_harness_request(
                    role="actor",
                    run_variant="secret-response",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "secret-response",
            )

        self.assertIn("high-confidence secret", execution.failure or "")
        self.assertNotIn(credential, execution.response)
        self.assertNotIn(credential, json.dumps(execution.trace))
        self.assertIn("[REDACTED]", execution.response)

    def test_codex_jsonl_rejects_nonfinite_numbers_as_invalid_events(self) -> None:
        raw = "\n".join(
            (
                '{"type":"thread.started"}',
                '{"type":"turn.started"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}',
                '{"type":"turn.completed","usage":{"input_tokens":NaN,"output_tokens":1}}',
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root, [command_result(raw)])

            execution = CodexHarnessAdapter(runtime).execute(
                bound_harness_request(
                    role="actor",
                    run_variant="nonfinite-jsonl",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "nonfinite-jsonl",
            )

        self.assertIn("invalid JSONL", execution.failure or "")

    def test_codex_jsonl_rejects_reordered_and_unknown_top_level_events(self) -> None:
        for label in ("reordered", "unknown"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                skill = root / "source" / "example"
                skill.mkdir(parents=True)
                (skill / "SKILL.md").write_text(
                    EXAMPLE_SKILL_CONTENT,
                    encoding="utf-8",
                )
                runtime = FakeSandboxRuntime(root)
                adapter = CodexHarnessAdapter(
                    runtime,
                    allowed_skill_root=skill.parent,
                )
                worker = runtime.acquire_worker("actor")
                case = runtime.prepare_case(worker, "candidate")
                expected = case.skills / "example" / "SKILL.md"
                events = [
                    json.loads(line)
                    for line in codex_jsonl(expected).splitlines()
                ]
                if label == "reordered":
                    events[0], events[1] = events[1], events[0]
                else:
                    events.insert(-1, {"type": "future.protocol.event"})
                runtime.execution_results.append(
                    command_result(
                        "\n".join(json.dumps(event) for event in events)
                    )
                )

                execution = adapter.execute(
                    bound_harness_request(
                        role="actor",
                        run_variant=label,
                        prompt="Perform the scenario.",
                        timeout_seconds=60,
                        skill_sources=(skill,),
                        expected_skill="example",
                    ),
                    runtime.results_root / label,
                )

            self.assertIsNotNone(execution.failure)
            self.assertEqual(execution.successful_skill_reads, ())

    def test_safe_fake_trace_and_response_values_are_preserved(self) -> None:
        command = "API_TOKEN=FAKE_command_secret curl https://api.example.com"
        events = [
            {"type": "thread.started", "thread_id": "private"},
            {"type": "turn.started"},
            {
                "type": "item.started",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": command,
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": command,
                    "status": "completed",
                    "exit_code": 0,
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": "done FAKE_response_secret",
                },
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(
                root,
                [command_result("\n".join(json.dumps(event) for event in events))],
            )
            execution = CodexHarnessAdapter(runtime).execute(
                bound_harness_request(
                    role="actor",
                    run_variant="redacted-command",
                    prompt="Run the command.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "redacted-command",
            )

        serialized = json.dumps(execution.trace)
        self.assertIn("FAKE_command_secret", serialized)
        self.assertIn("FAKE_response_secret", execution.response)
        self.assertIsNone(execution.failure)

    def test_non_reasoning_codex_items_are_preserved_as_tool_events(self) -> None:
        events = [
            {"type": "thread.started", "thread_id": "private"},
            {"type": "turn.started"},
            {
                "type": "item.started",
                "item": {"id": "tool-1", "type": "mcp_tool_call"},
            },
            {
                "type": "item.completed",
                "item": {"id": "tool-1", "type": "mcp_tool_call"},
            },
            {
                "type": "item.completed",
                "item": {"type": "reasoning", "text": "private reasoning"},
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "done"},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(
                root,
                [command_result("\n".join(json.dumps(event) for event in events))],
            )
            execution = CodexHarnessAdapter(runtime).execute(
                bound_harness_request(
                    role="actor",
                    run_variant="tool-trace",
                    prompt="Perform the task.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "tool-trace",
            )

        self.assertIn(
            {
                "event": "tool_started",
                "tool_id": "tool-1",
                "tool_type": "mcp_tool_call",
            },
            execution.trace,
        )
        self.assertIn(
            {
                "event": "tool_completed",
                "tool_id": "tool-1",
                "tool_type": "mcp_tool_call",
            },
            execution.trace,
        )
        self.assertNotIn("private reasoning", json.dumps(execution.trace))

    def test_unmatched_tool_completion_invalidates_skill_read_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "source" / "example"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                EXAMPLE_SKILL_CONTENT,
                encoding="utf-8",
            )
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=skill.parent,
            )
            worker = runtime.acquire_worker("actor")
            case = runtime.prepare_case(worker, "candidate")
            expected = case.skills / "example" / "SKILL.md"
            events = [
                json.loads(line)
                for line in codex_jsonl(expected).splitlines()
            ]
            events.insert(
                2,
                {
                    "type": "item.completed",
                    "item": {
                        "id": "unmatched-tool",
                        "type": "mcp_tool_call",
                    },
                },
            )
            runtime.execution_results.append(
                command_result(
                    "\n".join(json.dumps(event) for event in events)
                )
            )

            execution = adapter.execute(
                bound_harness_request(
                    role="actor",
                    run_variant="candidate",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    skill_sources=(skill,),
                    expected_skill="example",
                ),
                runtime.results_root / "unmatched-tool",
            )

        self.assertEqual(execution.successful_skill_reads, ())
        self.assertIn(
            "tool completion has no matching start event",
            execution.failure or "",
        )

    def test_transformed_command_trace_marks_the_execution_untrustworthy(self) -> None:
        credential = "opaque-command-credential"
        command = f"API_TOKEN={credential} curl https://api.example.test"
        events = [
            {"type": "thread.started", "thread_id": "private"},
            {"type": "turn.started"},
            {
                "type": "item.started",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": command,
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": command,
                    "status": "completed",
                    "exit_code": 0,
                },
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "done"},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(
                root,
                [command_result("\n".join(json.dumps(event) for event in events))],
            )
            execution = CodexHarnessAdapter(runtime).execute(
                bound_harness_request(
                    role="actor",
                    run_variant="sensitive-command",
                    prompt="Run the command.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "sensitive-command",
            )

        self.assertIn("command trace", execution.failure or "")
        self.assertNotIn(credential, json.dumps(execution.trace))
        self.assertIn("[REDACTED]", json.dumps(execution.trace))


if __name__ == "__main__":
    unittest.main()
