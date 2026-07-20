from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import unittest

from scripts.ai_skills_lib.codex_harness import (
    CodexHarnessAdapter,
    CodexOutputError,
    project_actor_skill,
)
from scripts.ai_skills_lib.harness import ActorInput, HarnessRequest
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


def command_result(stdout: str = "", *, returncode: int = 0, stderr: str = "", timed_out: bool = False):
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
    )


def codex_jsonl(expected_skill_path: Path | None = None) -> str:
    events: list[dict[str, object]] = [
        {"type": "thread.started", "thread_id": "private-thread-id"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": "working"}},
    ]
    if expected_skill_path is not None:
        command = f"/bin/bash -lc \"sed -n '1,240p' {expected_skill_path}\""
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
                        "aggregated_output": "the entire private skill body",
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
        self.case_sequence = 0
        self.remove_case_on_lease_release = False
        self.quiesce_error: Exception | None = None

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

    def invalidate_worker(self, worker: SandboxWorker) -> None:
        self.invalidated_workers.append(worker)

    def quiesce_case(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self.quiesced_cases.append((worker, case))
        if self.quiesce_error is not None:
            raise self.quiesce_error

    def execute(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        argv: tuple[str, ...],
        *,
        timeout_seconds: int,
        environment: dict[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append((worker, case, argv, timeout_seconds, dict(environment or {})))
        if not self.execution_results:
            raise AssertionError(f"unexpected execution: {argv!r}")
        return self.execution_results.pop(0)


class FakeFixtureProxy:
    def __init__(self) -> None:
        self.prepared: list[tuple[SandboxWorker, CaseWorkspace, Path, Path]] = []
        self.collected: list[tuple[SandboxWorker, CaseWorkspace, FixtureSession]] = []
        self.discarded: list[SandboxWorker] = []
        self.collect_error: FixtureProxyError | None = None
        self.preflighted: list[tuple[SandboxWorker, CaseWorkspace]] = []

    def preflight(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self.preflighted.append((worker, case))

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


class CodexHarnessAdapterTests(unittest.TestCase):
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
            fixture_proxy = FakeFixtureProxy()
            adapter = CodexHarnessAdapter(runtime, fixture_proxy=fixture_proxy)

            capabilities = adapter.preflight(require_fixtures=True)

        self.assertTrue(capabilities.available, capabilities.failure)
        self.assertEqual(len(fixture_proxy.preflighted), 1)
        self.assertEqual(fixture_proxy.preflighted[0][1].case_id, "preflight")

    def test_execute_projects_skill_invokes_pinned_flags_and_normalizes_evidence(self) -> None:
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
            request = HarnessRequest(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
                skill_sources=(skill,),
                expected_skill="example",
            )
            artifact_dir = runtime.results_root / "with-skill"
            artifact_dir.mkdir()

            execution = adapter.execute(request, artifact_dir)
            projected_skill_exists = expected_path.is_file()

        self.assertEqual(execution.response, "final response")
        self.assertEqual(execution.total_tokens, 25)
        self.assertEqual(execution.input_tokens, 20)
        self.assertEqual(execution.output_tokens, 5)
        self.assertEqual(execution.cached_tokens, 7)
        self.assertEqual(execution.successful_skill_reads, (expected_path,))
        self.assertNotIn("the entire private skill body", json.dumps(execution.trace))
        self.assertNotIn("private-thread-id", json.dumps(execution.trace))
        codex_argv = runtime.calls[-1][2]
        for flag in MANIFEST.codex.exec_flags:
            self.assertIn(flag, codex_argv)
        self.assertIn("allow_login_shell=false", codex_argv)
        self.assertEqual(codex_argv[-2:], ("--", "Perform the scenario."))
        self.assertNotIn("--ignore-user-config", codex_argv)
        self.assertTrue(projected_skill_exists)

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
                HarnessRequest(
                    role="actor",
                    run_variant="candidate",
                    prompt="Perform the scenario.",
                    timeout_seconds=60,
                    skill_sources=(skill,),
                    expected_skill="example",
                ),
                runtime.results_root / "with-skill",
            )

        self.assertEqual(execution.successful_skill_reads, (expected_path,))

    def test_fixture_environment_is_applied_only_to_codex_shell_subprocesses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            adapter = CodexHarnessAdapter(runtime)
            request = HarnessRequest(
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
                HarnessRequest(
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
                    HarnessRequest(
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
                    HarnessRequest(
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
                    HarnessRequest(
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
            request = HarnessRequest(
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
        self.assertEqual(prepared_path, fixture)
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
                HarnessRequest(
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
                HarnessRequest(
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

    def test_preserves_native_evidence_when_post_execution_cleanup_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = FakeSandboxRuntime(root, [command_result(codex_jsonl())])
            runtime.quiesce_error = RuntimeError("case quiescence failed")
            adapter = CodexHarnessAdapter(runtime)

            execution = adapter.execute(
                HarnessRequest(
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
                    HarnessRequest(
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
            runtime = FakeSandboxRuntime(root)
            adapter = CodexHarnessAdapter(runtime)
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
            request = HarnessRequest(
                role="actor",
                run_variant="candidate",
                prompt="Perform the scenario.",
                timeout_seconds=60,
                expected_skill="example",
            )
            artifact_dir = runtime.results_root / "ambiguous"
            artifact_dir.mkdir()

            execution = adapter.execute(request, artifact_dir)

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
            request = HarnessRequest(
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
            request = HarnessRequest(
                role="actor",
                run_variant="candidate-one",
                prompt="Perform the scenario.",
                timeout_seconds=60,
            )

            truncated = adapter.execute(request, runtime.results_root / "truncated")
            incomplete = adapter.execute(
                HarnessRequest(
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
            request = HarnessRequest(
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
            request = HarnessRequest(
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
            request = HarnessRequest(
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

    def test_command_trace_scalar_is_bounded_and_secret_redacted(self) -> None:
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
                HarnessRequest(
                    role="actor",
                    run_variant="redacted-command",
                    prompt="Run the command.",
                    timeout_seconds=60,
                ),
                runtime.results_root / "redacted-command",
            )

        serialized = json.dumps(execution.trace)
        self.assertNotIn("FAKE_command_secret", serialized)
        self.assertIn("[REDACTED]", serialized)
        self.assertNotIn("FAKE_response_secret", execution.response)


if __name__ == "__main__":
    unittest.main()
