"""Pinned Docker Sandboxes lifecycle for model-backed evaluations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import threading
import tomllib
from typing import Iterator, Literal, Protocol

from scripts.ai_skills_lib.runtime_environment import CASE_OWNED_ENVIRONMENT_NAMES
from scripts.ai_skills_lib.secret_patterns import SECRET_PATTERNS


WorkerRole = Literal["actor", "judge"]

IPC_CLEANUP_SCRIPT = """import pathlib
import subprocess
import sys

uid = int(sys.argv[1])
proc_root = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path("/proc")
queue_root = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else pathlib.Path("/dev/mqueue")
tables = (("shm", "shmid", "-m"), ("msg", "msqid", "-q"), ("sem", "semid", "-s"))

for table, _, _ in tables:
    if not (proc_root / "sysvipc" / table).is_file():
        raise SystemExit("SysV IPC inspection surface is unavailable")

mountinfo = proc_root / "self" / "mountinfo"
if not mountinfo.is_file():
    raise SystemExit("mqueue inspection surface is unavailable")
has_mqueue_mount = False
for line in mountinfo.read_text(encoding="utf-8").splitlines():
    fields = line.split()
    try:
        separator = fields.index("-")
    except ValueError:
        continue
    if len(fields) > separator + 1 and fields[4] == str(queue_root):
        has_mqueue_mount = fields[separator + 1] == "mqueue"
        break
if not queue_root.is_dir() or not has_mqueue_mount:
    raise SystemExit("mqueue inspection surface is unavailable")

def owned_ids():
    found = []
    for table, identifier_name, flag in tables:
        path = proc_root / "sysvipc" / table
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue
        columns = lines[0].split()
        identifier_index = columns.index(identifier_name)
        uid_index = columns.index("uid")
        creator_uid_index = columns.index("cuid")
        for line in lines[1:]:
            values = line.split()
            if uid in (int(values[uid_index]), int(values[creator_uid_index])):
                found.append((flag, values[identifier_index]))
    return found

for flag, identifier in owned_ids():
    subprocess.run(("ipcrm", flag, identifier), check=True)

for queue in queue_root.iterdir():
    if queue.lstat().st_uid == uid:
        queue.unlink()

if owned_ids():
    raise SystemExit("UID-owned SysV IPC state remains")
if any(queue.lstat().st_uid == uid for queue in queue_root.iterdir()):
    raise SystemExit("UID-owned POSIX message queues remain")
"""


class ManifestError(ValueError):
    """The immutable evaluation runtime manifest is invalid."""


class SandboxRuntimeError(RuntimeError):
    """Docker Sandboxes could not establish a trustworthy execution boundary."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    lifecycle_failure: str | None = None


class ProcessRunner(Protocol):
    def run(self, argv: tuple[str, ...], *, timeout_seconds: int) -> CommandResult:
        """Run one bounded host process without invoking a shell."""


class SubprocessRunner:
    """Production process boundary used by the sandbox adapter."""

    def __init__(self, maximum_output_bytes: int) -> None:
        self._maximum_output_bytes = maximum_output_bytes

    def run(self, argv: tuple[str, ...], *, timeout_seconds: int) -> CommandResult:
        timed_out = False
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        stdout_buffer = bytearray()
        stderr_buffer = bytearray()
        stdout_budget = self._maximum_output_bytes // 2
        stderr_budget = self._maximum_output_bytes - stdout_budget
        truncation = {"stdout": False, "stderr": False}

        def drain(stream, buffer: bytearray, budget: int, key: str) -> None:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    return
                remaining = budget - len(buffer)
                if remaining > 0:
                    buffer.extend(chunk[:remaining])
                if len(chunk) > max(remaining, 0):
                    truncation[key] = True

        stdout_thread = threading.Thread(
            target=drain,
            args=(process.stdout, stdout_buffer, stdout_budget, "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=drain,
            args=(process.stderr, stderr_buffer, stderr_budget, "stderr"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            returncode = 124
        stdout_thread.join()
        stderr_thread.join()
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        return CommandResult(
            returncode=returncode,
            stdout=self._decode(stdout_buffer),
            stderr=self._decode(stderr_buffer),
            timed_out=timed_out,
            stdout_truncated=truncation["stdout"],
            stderr_truncated=truncation["stderr"],
        )

    @staticmethod
    def _decode(value: bytes) -> str:
        return value.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class NetworkPolicyPin:
    preset: str
    policy_id: str
    rules_sha256: str
    required_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class SbxPin:
    version: str
    revision: str
    network_policy: NetworkPolicyPin


@dataclass(frozen=True)
class CodexPin:
    agent: str
    version: str
    template: str
    allow_login_shell: bool
    fixture_environment_scope: str
    exec_flags: tuple[str, ...]


@dataclass(frozen=True)
class AuthenticationPin:
    service: str
    mode: str
    copy_host_credentials: bool


@dataclass(frozen=True)
class WorkerSettings:
    default_concurrency: int
    maximum_concurrency: int
    cpus: int
    memory: str
    reuse_scope: str
    separate_actor_and_judge_pools: bool


@dataclass(frozen=True)
class RuntimeLimits:
    preflight_timeout_seconds: int
    actor_timeout_seconds: int
    judge_timeout_seconds: int
    maximum_captured_output_bytes: int


@dataclass(frozen=True)
class MockServerPin:
    version: str
    image: str
    digest: str
    bind: str
    reuse_scope: str
    ca_scope: str
    maximum_expected_requests: int
    bundled_default_ca_sha256: str
    schema_release: str
    schema_source: str
    schema_path: Path
    schema_sha256: str
    reset_per_case: tuple[str, ...]
    passthrough: bool

    @property
    def image_reference(self) -> str:
        return f"{self.image}@{self.digest}"


@dataclass(frozen=True)
class CaseIsolation:
    fresh_worker_projection: bool
    fresh_home: bool
    fresh_workspace: bool
    fresh_codex_home_from_proxy_stubs: bool
    fresh_tmpdir: bool
    ephemeral_harness_session: bool
    durable_results_mounted_into_actor: bool
    reset_failure: str


@dataclass(frozen=True)
class EvalRuntimeManifest:
    schema_version: int
    runtime: str
    sbx: SbxPin
    codex: CodexPin
    authentication: AuthenticationPin
    workers: WorkerSettings
    limits: RuntimeLimits
    docker_engine: str
    mockserver: MockServerPin
    case_isolation: CaseIsolation

    @classmethod
    def load(cls, path: Path) -> EvalRuntimeManifest:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ManifestError(f"cannot read runtime manifest: {error}") from error
        root = _mapping(raw, "runtime manifest")
        _expect_keys(
            root,
            {
                "schema_version",
                "runtime",
                "sbx",
                "codex",
                "authentication",
                "workers",
                "limits",
                "fixtures",
                "case_isolation",
            },
            "runtime manifest",
        )

        sbx_raw = _section(root, "sbx", {"version", "revision", "network_policy"})
        network_policy_raw = _section(
            sbx_raw,
            "network_policy",
            {"preset", "policy_id", "rules_sha256", "required_rule_ids"},
        )
        codex_raw = _section(
            root,
            "codex",
            {
                "agent",
                "version",
                "template",
                "allow_login_shell",
                "fixture_environment_scope",
                "exec_flags",
            },
        )
        auth_raw = _section(root, "authentication", {"service", "mode", "copy_host_credentials"})
        workers_raw = _section(
            root,
            "workers",
            {
                "default_concurrency",
                "maximum_concurrency",
                "cpus",
                "memory",
                "reuse_scope",
                "separate_actor_and_judge_pools",
            },
        )
        limits_raw = _section(
            root,
            "limits",
            {
                "preflight_timeout_seconds",
                "actor_timeout_seconds",
                "judge_timeout_seconds",
                "maximum_captured_output_bytes",
            },
        )
        fixtures_raw = _section(root, "fixtures", {"docker_engine", "mockserver"})
        mockserver_raw = _section(
            fixtures_raw,
            "mockserver",
            {
                "version",
                "image",
                "digest",
                "bind",
                "reuse_scope",
                "ca_scope",
                "maximum_expected_requests",
                "bundled_default_ca_sha256",
                "schema",
                "reset_per_case",
                "passthrough",
            },
        )
        schema_raw = _section(mockserver_raw, "schema", {"release", "source", "path", "sha256"})
        isolation_raw = _section(
            root,
            "case_isolation",
            {
                "fresh_worker_projection",
                "fresh_home",
                "fresh_workspace",
                "fresh_codex_home_from_proxy_stubs",
                "fresh_tmpdir",
                "ephemeral_harness_session",
                "durable_results_mounted_into_actor",
                "reset_failure",
            },
        )

        template = _string(codex_raw, "template")
        if not re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", template):
            raise ManifestError("codex.template must be a fully qualified digest-bound image reference")
        mockserver_digest = _string(mockserver_raw, "digest")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", mockserver_digest):
            raise ManifestError("fixtures.mockserver.digest must be an immutable sha256 digest")

        maximum_concurrency = _integer(workers_raw, "maximum_concurrency")
        default_concurrency = _integer(workers_raw, "default_concurrency")
        if maximum_concurrency not in range(1, 5):
            raise ManifestError("workers.maximum_concurrency must be between 1 and 4")
        if default_concurrency not in range(1, maximum_concurrency + 1):
            raise ManifestError("workers.default_concurrency must not exceed maximum_concurrency")

        manifest = cls(
            schema_version=_integer(root, "schema_version"),
            runtime=_string(root, "runtime"),
            sbx=SbxPin(
                version=_plain_version(sbx_raw, "version"),
                revision=_hex_string(sbx_raw, "revision", 40),
                network_policy=NetworkPolicyPin(
                    preset=_string(network_policy_raw, "preset"),
                    policy_id=_string(network_policy_raw, "policy_id"),
                    rules_sha256=_hex_string(network_policy_raw, "rules_sha256", 64),
                    required_rule_ids=_string_tuple(network_policy_raw, "required_rule_ids"),
                ),
            ),
            codex=CodexPin(
                agent=_string(codex_raw, "agent"),
                version=_plain_version(codex_raw, "version"),
                template=template,
                allow_login_shell=_boolean(codex_raw, "allow_login_shell"),
                fixture_environment_scope=_string(codex_raw, "fixture_environment_scope"),
                exec_flags=_string_tuple(codex_raw, "exec_flags"),
            ),
            authentication=AuthenticationPin(
                service=_string(auth_raw, "service"),
                mode=_string(auth_raw, "mode"),
                copy_host_credentials=_boolean(auth_raw, "copy_host_credentials"),
            ),
            workers=WorkerSettings(
                default_concurrency=default_concurrency,
                maximum_concurrency=maximum_concurrency,
                cpus=_integer(workers_raw, "cpus"),
                memory=_string(workers_raw, "memory"),
                reuse_scope=_string(workers_raw, "reuse_scope"),
                separate_actor_and_judge_pools=_boolean(workers_raw, "separate_actor_and_judge_pools"),
            ),
            limits=RuntimeLimits(
                preflight_timeout_seconds=_positive_integer(limits_raw, "preflight_timeout_seconds"),
                actor_timeout_seconds=_positive_integer(limits_raw, "actor_timeout_seconds"),
                judge_timeout_seconds=_positive_integer(limits_raw, "judge_timeout_seconds"),
                maximum_captured_output_bytes=_positive_integer(limits_raw, "maximum_captured_output_bytes"),
            ),
            docker_engine=_string(fixtures_raw, "docker_engine"),
            mockserver=MockServerPin(
                version=_plain_version(mockserver_raw, "version"),
                image=_string(mockserver_raw, "image"),
                digest=mockserver_digest,
                bind=_string(mockserver_raw, "bind"),
                reuse_scope=_string(mockserver_raw, "reuse_scope"),
                ca_scope=_string(mockserver_raw, "ca_scope"),
                maximum_expected_requests=_positive_integer(
                    mockserver_raw, "maximum_expected_requests"
                ),
                bundled_default_ca_sha256=_hex_string(
                    mockserver_raw, "bundled_default_ca_sha256", 64
                ),
                schema_release=_string(schema_raw, "release"),
                schema_source=_string(schema_raw, "source"),
                schema_path=Path(_string(schema_raw, "path")),
                schema_sha256=_hex_string(schema_raw, "sha256", 64),
                reset_per_case=_string_tuple(mockserver_raw, "reset_per_case"),
                passthrough=_boolean(mockserver_raw, "passthrough"),
            ),
            case_isolation=CaseIsolation(
                fresh_worker_projection=_boolean(isolation_raw, "fresh_worker_projection"),
                fresh_home=_boolean(isolation_raw, "fresh_home"),
                fresh_workspace=_boolean(isolation_raw, "fresh_workspace"),
                fresh_codex_home_from_proxy_stubs=_boolean(
                    isolation_raw, "fresh_codex_home_from_proxy_stubs"
                ),
                fresh_tmpdir=_boolean(isolation_raw, "fresh_tmpdir"),
                ephemeral_harness_session=_boolean(isolation_raw, "ephemeral_harness_session"),
                durable_results_mounted_into_actor=_boolean(
                    isolation_raw, "durable_results_mounted_into_actor"
                ),
                reset_failure=_string(isolation_raw, "reset_failure"),
            ),
        )
        manifest._validate_policy()
        return manifest

    def _validate_policy(self) -> None:
        if self.schema_version != 1 or self.runtime != "docker-sandboxes":
            raise ManifestError("unsupported evaluation runtime schema or runtime")
        if self.sbx.network_policy.preset != "balanced":
            raise ManifestError("sbx.network_policy.preset must be balanced")
        required_balanced_rules = {
            "default-ai-services",
            "default-package-managers",
            "default-code-and-containers",
            "default-cloud-infrastructure",
            "default-os-packages",
            "default-cert-validation",
        }
        if set(self.sbx.network_policy.required_rule_ids) != required_balanced_rules:
            raise ManifestError("sbx.network_policy must declare every balanced preset rule")
        if self.codex.agent != "codex" or self.codex.allow_login_shell:
            raise ManifestError("codex runtime must use the codex agent with login shells disabled")
        required_flags = {
            "--json",
            "--ephemeral",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        }
        if not required_flags.issubset(self.codex.exec_flags) or "--ignore-user-config" in self.codex.exec_flags:
            raise ManifestError("codex.exec_flags must preserve the pinned isolated JSONL contract")
        if self.codex.fixture_environment_scope != "shell-subprocesses":
            raise ManifestError("fixture environment must be limited to shell subprocesses")
        if self.authentication.mode != "host-proxied-oauth" or self.authentication.copy_host_credentials:
            raise ManifestError("authentication must use host-proxied OAuth without copied credentials")
        if self.workers.cpus <= 0 or not re.fullmatch(r"[1-9][0-9]*[mg]", self.workers.memory):
            raise ManifestError("worker CPU and memory limits must be positive and explicit")
        if self.workers.reuse_scope != "one-cli-invocation":
            raise ManifestError("workers may only be reused for one CLI invocation")
        if not self.workers.separate_actor_and_judge_pools:
            raise ManifestError("actor and judge worker pools must remain separate")
        if self.docker_engine != "sandbox-private" or self.mockserver.passthrough:
            raise ManifestError("fixture networking must use a private engine with passthrough disabled")
        expected_schema_release = f"mockserver-{self.mockserver.version}"
        expected_schema_source = (
            "https://raw.githubusercontent.com/mock-server/mockserver/"
            f"{expected_schema_release}/mockserver-vscode/schemas/"
            "mockserver-expectation.schema.json"
        )
        expected_schema_path = (
            Path("schemas/vendor/mockserver")
            / self.mockserver.version
            / "expectations.schema.json"
        )
        if (
            self.mockserver.image != "mockserver/mockserver"
            or self.mockserver.bind != "microvm-loopback"
            or self.mockserver.reuse_scope != "worker"
            or self.mockserver.ca_scope != "worker"
            or self.mockserver.maximum_expected_requests != 128
            or self.mockserver.schema_release != expected_schema_release
            or self.mockserver.schema_source != expected_schema_source
            or self.mockserver.schema_path != expected_schema_path
            or self.mockserver.reset_per_case
            != ("expectations", "request_history", "fixture_files")
        ):
            raise ManifestError("mockserver isolation and schema policy cannot be weakened")
        isolation = self.case_isolation
        if not all(
            (
                isolation.fresh_worker_projection,
                isolation.fresh_home,
                isolation.fresh_workspace,
                isolation.fresh_codex_home_from_proxy_stubs,
                isolation.fresh_tmpdir,
                isolation.ephemeral_harness_session,
            )
        ) or isolation.durable_results_mounted_into_actor:
            raise ManifestError("case isolation invariants cannot be weakened")
        if isolation.reset_failure != "fail-case-and-recycle-worker":
            raise ManifestError("reset failures must fail the case and recycle the worker")


@dataclass(frozen=True)
class PreflightReport:
    available: bool
    details: tuple[str, ...]
    failure: str | None = None


@dataclass(frozen=True)
class SandboxWorker:
    id: str
    name: str
    role: WorkerRole
    slot: int
    host_root: Path


@dataclass(frozen=True)
class CaseWorkspace:
    """Fresh actor- or judge-visible directories for one attempted run."""

    case_id: str
    root: Path
    home: Path
    codex_home: Path
    tmpdir: Path
    workspace: Path
    skills: Path
    bootstrap: Path
    user_name: str
    uid: int


@dataclass
class CleanupTarget:
    name: str
    id: str | None
    host_root: Path
    removal_issued: bool = False
    sandbox_removed: bool = False


class SandboxRuntime:
    """Own invocation-scoped Docker Sandboxes workers and nothing else."""

    def __init__(
        self,
        *,
        manifest: EvalRuntimeManifest,
        process: ProcessRunner,
        repository_root: Path,
        results_root: Path,
        staging_root: Path,
        invocation_id: str,
        max_concurrency: int,
    ) -> None:
        self.manifest = manifest
        self.process = process
        self.repository_root = repository_root.resolve()
        self.results_root = results_root.resolve()
        self.staging_root = staging_root.resolve()
        self.invocation_id = _safe_identifier(invocation_id)
        if max_concurrency not in range(1, manifest.workers.maximum_concurrency + 1):
            raise SandboxRuntimeError(
                f"max_concurrency must be between 1 and {manifest.workers.maximum_concurrency}"
            )
        self.max_concurrency = max_concurrency
        for root in (self.results_root, self.staging_root):
            if (
                root == self.repository_root
                or root.is_relative_to(self.repository_root)
                or self.repository_root.is_relative_to(root)
            ):
                raise SandboxRuntimeError("result and staging roots must remain outside the repository")
        if self.results_root == self.staging_root or self.results_root.is_relative_to(self.staging_root):
            raise SandboxRuntimeError("durable results must remain outside worker staging roots")
        if self.staging_root.is_relative_to(self.results_root):
            raise SandboxRuntimeError("worker staging roots must remain outside durable results")
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self._workers: dict[tuple[WorkerRole, int], SandboxWorker] = {}
        self._cleanup_targets: dict[str, CleanupTarget] = {}
        self._case_sequences: dict[str, int] = {}
        self._active_cases: dict[str, CaseWorkspace] = {}
        self._proxy_state_digests: dict[str, tuple[str, str]] = {}
        self._busy_workers: set[tuple[WorkerRole, int]] = set()
        self._worker_condition = threading.Condition()
        self._closed = False

    def preflight(self) -> PreflightReport:
        """Validate host-side pinned runtime capabilities without exposing secrets."""
        try:
            timeout = self.manifest.limits.preflight_timeout_seconds
            version = self._checked(("sbx", "version"), timeout)
            expected_version = f"v{self.manifest.sbx.version}"
            if expected_version not in version.stdout or self.manifest.sbx.revision not in version.stdout:
                raise SandboxRuntimeError("Docker Sandboxes version or revision does not match the runtime pin")

            diagnose = self._json_command(("sbx", "diagnose", "--output", "json"), timeout)
            summary = _mapping(diagnose.get("summary"), "sbx diagnose summary")
            if summary.get("fail") != 0 or summary.get("warn") != 0:
                raise SandboxRuntimeError("Docker Sandboxes diagnostics did not pass cleanly")
            checks = diagnose.get("checks")
            if not isinstance(checks, list) or not checks:
                raise SandboxRuntimeError("Docker Sandboxes named diagnostics are unavailable")
            names: set[str] = set()
            for check in checks:
                if (
                    not isinstance(check, Mapping)
                    or not isinstance(check.get("name"), str)
                    or not check["name"]
                    or check["name"] in names
                    or check.get("status") != "pass"
                ):
                    raise SandboxRuntimeError(
                        "Docker Sandboxes named diagnostic did not pass"
                    )
                names.add(check["name"])
            if summary.get("pass") != len(checks) or any(
                summary.get(name) != 0 for name in ("warn", "fail", "skip")
            ):
                raise SandboxRuntimeError(
                    "Docker Sandboxes diagnostic summary does not match named checks"
                )

            secret = self._checked(
                ("sbx", "secret", "ls", "-g", "--service", self.manifest.authentication.service),
                timeout,
            )
            if "(oauth configured)" not in secret.stdout:
                raise SandboxRuntimeError("host-proxied OpenAI OAuth is not configured")

            templates = self._json_command(("sbx", "template", "ls", "--json"), timeout)
            self._verify_template(templates)

            policies = self._json_command(
                ("sbx", "policy", "ls", "--json", "--type", "network"), timeout
            )
            self._verify_network_policy(policies)
            self._probe_results_root()
        except (ManifestError, OSError, SandboxRuntimeError) as error:
            return PreflightReport(available=False, details=(), failure=str(error))
        return PreflightReport(
            available=True,
            details=(
                f"sbx v{self.manifest.sbx.version}",
                f"network policy {self.manifest.sbx.network_policy.preset}",
                "host-proxied OAuth configured",
                "pinned Codex template available",
            ),
        )

    def acquire_worker(self, role: WorkerRole, slot: int = 0) -> SandboxWorker:
        with self._worker_condition:
            if self._closed:
                raise SandboxRuntimeError("sandbox runtime is closed")
            if role not in ("actor", "judge"):
                raise SandboxRuntimeError("worker role must be actor or judge")
            if slot not in range(self.max_concurrency):
                raise SandboxRuntimeError("worker slot exceeds configured concurrency")
            key = (role, slot)
            existing = self._workers.get(key)
            if existing is not None:
                return existing

            name = f"ai-skills-{self.invocation_id}-{role}-{slot + 1}"
            if name in self._cleanup_targets:
                raise SandboxRuntimeError("a previous worker with this name is pending verified cleanup")
            if any(item.get("name") == name for item in self._list_sandboxes()):
                raise SandboxRuntimeError(
                    "sandbox worker name already exists and is not owned by this invocation"
                )
            host_root = self.staging_root / name
            host_root.mkdir(parents=True, exist_ok=False)
            command = (
                "sbx",
                "create",
                "--name",
                name,
                "--cpus",
                str(self.manifest.workers.cpus),
                "--memory",
                self.manifest.workers.memory,
                "--template",
                self.manifest.codex.template,
                self.manifest.codex.agent,
                str(host_root),
            )
            try:
                self._checked(command, self.manifest.limits.preflight_timeout_seconds)
                sandboxes = self._list_sandboxes()
                matches = [item for item in sandboxes if item.get("name") == name]
                if len(matches) != 1 or not isinstance(matches[0].get("id"), str):
                    raise SandboxRuntimeError(
                        "created sandbox identity could not be reconciled from sbx ls --json"
                    )
            except Exception as error:
                self._reconcile_failed_create(name, host_root, error)
            worker = SandboxWorker(
                id=matches[0]["id"],
                name=name,
                role=role,
                slot=slot,
                host_root=host_root,
            )
            self._cleanup_targets[name] = CleanupTarget(
                name=name,
                id=worker.id,
                host_root=host_root,
            )
            self._workers[key] = worker
            return worker

    @contextmanager
    def lease_worker(self, role: WorkerRole) -> Iterator[SandboxWorker]:
        """Lease one role-specific worker under the invocation-wide concurrency cap."""
        if role not in ("actor", "judge"):
            raise SandboxRuntimeError("worker role must be actor or judge")
        with self._worker_condition:
            while True:
                if self._closed:
                    raise SandboxRuntimeError("sandbox runtime is closed")
                if len(self._busy_workers) < self.max_concurrency:
                    available = next(
                        (
                            key
                            for key in self._workers
                            if key[0] == role and key not in self._busy_workers
                        ),
                        None,
                    )
                    if available is None:
                        available = next(
                            (
                                (role, slot)
                                for slot in range(self.max_concurrency)
                                if (role, slot) not in self._workers
                                and (role, slot) not in self._busy_workers
                            ),
                            None,
                        )
                    if available is not None:
                        self._busy_workers.add(available)
                        try:
                            worker = self.acquire_worker(*available)
                        except Exception:
                            self._busy_workers.remove(available)
                            self._worker_condition.notify_all()
                            raise
                        break
                self._worker_condition.wait()
        try:
            yield worker
        finally:
            with self._worker_condition:
                self._busy_workers.discard((worker.role, worker.slot))
                self._worker_condition.notify_all()

    def prepare_case(self, worker: SandboxWorker, case_id: str) -> CaseWorkspace:
        """Erase the mounted projection and create a fresh case-owned layout."""
        self._require_owned_worker(worker)
        try:
            previous = self._active_cases.pop(worker.id, None)
            if previous is not None:
                self._retire_case_identity(worker, previous)
            safe_case_id = _safe_identifier(case_id)
            case_root = worker.host_root / "case"
            if case_root.exists() or case_root.is_symlink():
                if case_root.is_dir() and not case_root.is_symlink():
                    shutil.rmtree(case_root)
                else:
                    case_root.unlink()
            case_root.mkdir(parents=True)
            directories = {
                "home": case_root / "home",
                "codex_home": case_root / "codex-home",
                "tmpdir": case_root / "tmp",
                "workspace": case_root / "workspace",
                "bootstrap": case_root / "bootstrap",
            }
            for directory in directories.values():
                directory.mkdir()
            skills = directories["codex_home"] / "skills"
            skills.mkdir()
            for directory in (
                directories["home"] / ".config",
                directories["home"] / ".cache",
                directories["home"] / ".local" / "share",
                directories["home"] / ".local" / "state",
                directories["home"] / ".gnupg",
                directories["tmpdir"] / "runtime",
            ):
                directory.mkdir(parents=True)
            sequence = self._case_sequences.get(worker.id, 0) + 1
            self._case_sequences[worker.id] = sequence
            uid = 20000 + sequence
            user_name = f"ai-eval-{sequence}"
            case = CaseWorkspace(
                case_id=safe_case_id,
                root=case_root,
                skills=skills,
                user_name=user_name,
                uid=uid,
                **directories,
            )
            self._prepare_case_identity(worker, case)
            self._active_cases[worker.id] = case
            return case
        except Exception as error:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"case reset failed and worker cleanup is pending: {cleanup_error}"
                ) from error
            raise SandboxRuntimeError(f"case reset failed: {error}") from error

    def execute(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        argv: Sequence[str],
        *,
        timeout_seconds: int,
        environment: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Execute direct arguments in a case and recycle the worker on timeout."""
        self._require_owned_worker(worker)
        if not argv or not all(isinstance(part, str) and part and "\x00" not in part for part in argv):
            raise SandboxRuntimeError("worker command must contain non-empty NUL-free arguments")
        if timeout_seconds <= 0:
            raise SandboxRuntimeError("worker command timeout must be positive")
        if case.root.parent != worker.host_root or not case.root.is_dir():
            raise SandboxRuntimeError("case workspace does not belong to the selected worker")
        rendered_environment = {
            **dict(environment or {}),
        }
        reserved = CASE_OWNED_ENVIRONMENT_NAMES & rendered_environment.keys()
        if reserved:
            raise SandboxRuntimeError("worker environment cannot override reserved case variables")
        rendered_environment.update(
            {
                "HOME": str(case.home),
                "CODEX_HOME": str(case.codex_home),
                "TMPDIR": str(case.tmpdir),
                "USER": case.user_name,
                "LOGNAME": case.user_name,
                "SHELL": "/bin/bash",
                "XDG_CONFIG_HOME": str(case.home / ".config"),
                "XDG_CACHE_HOME": str(case.home / ".cache"),
                "XDG_DATA_HOME": str(case.home / ".local" / "share"),
                "XDG_STATE_HOME": str(case.home / ".local" / "state"),
                "XDG_RUNTIME_DIR": str(case.tmpdir / "runtime"),
                "SSH_AUTH_SOCK": "",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GNUPGHOME": str(case.home / ".gnupg"),
                "DOCKER_HOST": "",
            }
        )
        command: list[str] = [
            "sbx",
            "exec",
            "--user",
            case.user_name,
            "--workdir",
            str(case.workspace),
        ]
        for name, value in sorted(rendered_environment.items()):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or not isinstance(value, str) or "\x00" in value:
                raise SandboxRuntimeError("worker environment contains an unsafe name or value")
            command.extend(("--env", f"{name}={value}"))
        command.append(worker.id)
        command.extend(argv)
        try:
            result = self.process.run(tuple(command), timeout_seconds=timeout_seconds)
        except BaseException as error:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"worker command was interrupted and cleanup failed: {cleanup_error}"
                ) from error
            raise
        if result.timed_out:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                result = replace(
                    result,
                    lifecycle_failure=(
                        "timed-out worker cleanup failed: "
                        f"{_safe_diagnostic(str(cleanup_error))}"
                    ),
                )
        return result

    def run_worker_control(
        self,
        worker: SandboxWorker,
        argv: tuple[str, ...],
        *,
        accepted_returncodes: tuple[int, ...] = (0,),
    ) -> CommandResult:
        """Run one checked runner-owned command as root in a private worker."""
        self._require_owned_worker(worker)
        if not argv or not all(
            isinstance(part, str) and part and "\x00" not in part for part in argv
        ):
            raise SandboxRuntimeError("worker control command contains unsafe arguments")
        if not accepted_returncodes or not all(
            isinstance(code, int) and not isinstance(code, bool) for code in accepted_returncodes
        ):
            raise SandboxRuntimeError("worker control command has invalid accepted return codes")
        try:
            result = self._worker_command(
                worker,
                argv,
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
        except BaseException as error:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"worker control command was interrupted and cleanup is pending: {cleanup_error}"
                ) from error
            raise
        if result.timed_out or result.returncode not in accepted_returncodes:
            try:
                self._discard_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"worker control command failed and cleanup is pending: {cleanup_error}"
                )
            raise SandboxRuntimeError(f"worker control command failed: {argv[0]}")
        return result

    def quiesce_case(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        """Terminate residual case processes before collecting final evidence."""
        self._require_owned_worker(worker)
        if self._active_cases.get(worker.id) is not case:
            raise SandboxRuntimeError("case is not active on the selected worker")
        try:
            self._admin_checked(
                worker,
                ("pkill", "-KILL", "-u", str(case.uid)),
                accepted=(0, 1),
            )
            self._clear_case_ipc(worker, case)
            process_check = self._worker_command(
                worker,
                ("pgrep", "-u", str(case.uid)),
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
            if process_check.returncode != 1 or process_check.stdout.strip():
                raise SandboxRuntimeError("case processes could not be quiesced")
        except Exception as error:
            try:
                self.invalidate_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"case quiescence failed and worker cleanup is pending: {cleanup_error}"
                ) from error
            if isinstance(error, SandboxRuntimeError):
                raise
            raise SandboxRuntimeError(f"case quiescence failed: {error}") from error

    def initialize_codex_home(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        """Copy only Docker's generated provider config and auth placeholder."""
        try:
            self._initialize_codex_home_unchecked(worker, case)
        except Exception as error:
            try:
                self.invalidate_worker(worker)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"Codex proxy setup failed and worker cleanup is pending: {cleanup_error}"
                ) from error
            raise

    def _initialize_codex_home_unchecked(
        self, worker: SandboxWorker, case: CaseWorkspace
    ) -> None:
        result = self._worker_command(
            worker,
            (
                "cp",
                "--",
                "/home/agent/.codex/config.toml",
                "/home/agent/.codex/auth.json",
                str(case.codex_home),
            ),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if result.timed_out or result.returncode != 0:
            raise SandboxRuntimeError("Docker-generated Codex proxy state could not be initialized")
        config_path = case.codex_home / "config.toml"
        auth_path = case.codex_home / "auth.json"
        if not config_path.is_file() or not auth_path.is_file():
            raise SandboxRuntimeError("Docker-generated Codex proxy state is incomplete")
        if config_path.stat().st_size > 1024 * 1024 or auth_path.stat().st_size > 1024 * 1024:
            raise SandboxRuntimeError("Docker-generated Codex proxy state is unexpectedly large")
        config = config_path.read_text(encoding="utf-8")
        auth = auth_path.read_text(encoding="utf-8")
        try:
            config_payload = tomllib.loads(config)
        except tomllib.TOMLDecodeError as error:
            raise SandboxRuntimeError("Docker-generated Codex config is not valid TOML") from error
        providers = config_payload.get("model_providers")
        sandboxd = providers.get("sandboxd") if isinstance(providers, Mapping) else None
        if config_payload.get("model_provider") != "sandboxd" or not isinstance(sandboxd, Mapping):
            raise SandboxRuntimeError("Docker-generated Codex config does not select the sandboxd provider")
        base_url = sandboxd.get("base_url")
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise SandboxRuntimeError("Docker-generated sandboxd provider has an invalid base URL")
        try:
            auth_payload = json.loads(auth)
        except json.JSONDecodeError as error:
            raise SandboxRuntimeError("Docker-generated auth placeholder is not valid JSON") from error
        if not isinstance(auth_payload, Mapping):
            raise SandboxRuntimeError("Docker-generated auth placeholder has an unsupported shape")
        literal_secret_patterns = tuple(
            pattern for pattern in SECRET_PATTERNS if pattern.name != "sensitive-assignment"
        )
        if any(pattern.regex.search(auth) for pattern in literal_secret_patterns):
            raise SandboxRuntimeError("Docker-generated auth state unexpectedly contains credential material")
        config_digest = _sha256_text(config)
        auth_digest = _sha256_text(auth)
        baseline = self._proxy_state_digests.setdefault(worker.id, (config_digest, auth_digest))
        if baseline != (config_digest, auth_digest):
            raise SandboxRuntimeError("immutable Docker-generated proxy state changed between cases")
        self._admin_checked(
            worker,
            ("chown", f"{case.uid}:{case.uid}", str(config_path), str(auth_path)),
        )
        self._admin_checked(worker, ("chmod", "0600", str(config_path), str(auth_path)))

    def close(self) -> None:
        with self._worker_condition:
            if self._closed:
                return
            if self._busy_workers:
                raise SandboxRuntimeError("cannot close the sandbox runtime while workers are leased")
            self._closed = True
        targets = tuple(self._cleanup_targets.values())
        try:
            for target in targets:
                self._remove_cleanup_target(target)
        except Exception:
            with self._worker_condition:
                self._closed = False
            raise
        self._workers.clear()
        self._cleanup_targets.clear()
        self._active_cases.clear()
        self._proxy_state_digests.clear()

    def _discard_worker(self, worker: SandboxWorker) -> None:
        self._require_owned_worker(worker)
        self._workers.pop((worker.role, worker.slot), None)
        self._active_cases.pop(worker.id, None)
        self._proxy_state_digests.pop(worker.id, None)
        target = self._cleanup_targets[worker.name]
        self._remove_cleanup_target(target)

    def invalidate_worker(self, worker: SandboxWorker) -> None:
        """Quarantine and remove a worker whose case setup cannot be trusted."""
        if self._workers.get((worker.role, worker.slot)) is worker:
            self._discard_worker(worker)

    def _remove_cleanup_target(self, target: CleanupTarget) -> None:
        if not target.sandbox_removed and target.id is None:
            matches = [
                item for item in self._list_sandboxes() if item.get("name") == target.name
            ]
            if not matches:
                target.sandbox_removed = True
                self._forget_worker_state(target)
            elif len(matches) == 1 and isinstance(matches[0].get("id"), str):
                target.id = matches[0]["id"]
            else:
                raise SandboxRuntimeError(
                    "pending worker cleanup identity remains ambiguous"
                )
        if not target.sandbox_removed and not target.removal_issued:
            assert target.id is not None
            self._checked(
                (
                    "sbx",
                    "exec",
                    "--user",
                    "root",
                    target.id,
                    "find",
                    str(target.host_root),
                    "-mindepth",
                    "1",
                    "-maxdepth",
                    "1",
                    "-exec",
                    "rm",
                    "-rf",
                    "--",
                    "{}",
                    "+",
                ),
                self.manifest.limits.preflight_timeout_seconds,
            )
            self._checked(
                ("sbx", "rm", "--force", target.id),
                self.manifest.limits.preflight_timeout_seconds,
            )
            target.removal_issued = True
        if not target.sandbox_removed:
            assert target.id is not None
            remaining_items = self._list_sandboxes()
            present = any(item.get("id") == target.id for item in remaining_items)
            if present:
                raise SandboxRuntimeError("worker cleanup could not be verified")
            target.sandbox_removed = True
            self._forget_worker_state(target)
        if target.host_root.exists():
            shutil.rmtree(target.host_root)
        if target.host_root.exists():
            raise SandboxRuntimeError("worker host staging cleanup could not be verified")
        self._cleanup_targets.pop(target.name, None)

    def _forget_worker_state(self, target: CleanupTarget) -> None:
        for key, worker in tuple(self._workers.items()):
            if worker.name != target.name:
                continue
            self._workers.pop(key, None)
            self._active_cases.pop(worker.id, None)
            self._proxy_state_digests.pop(worker.id, None)

    def _reconcile_failed_create(self, name: str, host_root: Path, error: Exception) -> None:
        try:
            matches = [item for item in self._list_sandboxes() if item.get("name") == name]
        except Exception as reconciliation_error:
            self._cleanup_targets[name] = CleanupTarget(
                name=name,
                id=None,
                host_root=host_root,
            )
            raise SandboxRuntimeError(
                "sandbox creation failed and unresolved cleanup is pending: "
                f"{reconciliation_error}"
            ) from error
        if len(matches) == 1 and isinstance(matches[0].get("id"), str):
            target = CleanupTarget(
                name=name,
                id=matches[0]["id"],
                host_root=host_root,
            )
            self._cleanup_targets[name] = target
            try:
                self._remove_cleanup_target(target)
            except Exception as cleanup_error:
                raise SandboxRuntimeError(
                    f"sandbox creation failed and verified cleanup is pending: {cleanup_error}"
                ) from error
            raise error
        if matches:
            self._cleanup_targets[name] = CleanupTarget(
                name=name,
                id=None,
                host_root=host_root,
            )
            raise SandboxRuntimeError(
                "sandbox creation failed and ambiguous cleanup is pending"
            ) from error
        if host_root.exists():
            shutil.rmtree(host_root)
        raise error

    def _require_owned_worker(self, worker: SandboxWorker) -> None:
        if self._workers.get((worker.role, worker.slot)) is not worker:
            raise SandboxRuntimeError("worker is not owned by this invocation")

    def _prepare_case_identity(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self._admin_checked(worker, ("chmod", "0700", "/home/agent"))
        self._admin_checked(worker, ("chmod", "0700", "/home/agent/.codex"))
        self._admin_checked(
            worker,
            ("chmod", "0600", "/home/agent/.codex/config.toml", "/home/agent/.codex/auth.json"),
        )
        self._admin_checked(
            worker,
            (
                "useradd",
                "--no-create-home",
                "--home-dir",
                str(case.home),
                "--shell",
                "/bin/bash",
                "--user-group",
                "--uid",
                str(case.uid),
                case.user_name,
            ),
        )
        self._admin_checked(worker, ("chown", "-R", f"{case.uid}:{case.uid}", str(case.root)))
        self._case_user_checked(
            worker,
            case,
            ("test", "!", "-r", "/var/run/docker.sock"),
            "case user can read the sandbox-private Docker socket",
        )
        self._case_user_checked(
            worker,
            case,
            ("test", "!", "-w", "/var/run/docker.sock"),
            "case user can write the sandbox-private Docker socket",
        )
        self._case_user_checked(
            worker,
            case,
            ("test", "!", "-r", "/home/agent/.codex/auth.json"),
            "case user can read the immutable proxy source",
        )

    def _retire_case_identity(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self._admin_checked(worker, ("pkill", "-KILL", "-u", str(case.uid)), accepted=(0, 1))
        self._clear_case_ipc(worker, case)
        self._admin_checked(worker, ("userdel", case.user_name), accepted=(0, 6))
        self._admin_checked(worker, ("groupdel", case.user_name), accepted=(0, 6))
        for directory in ("/tmp", "/var/tmp", "/dev/shm"):
            self._admin_checked(
                worker,
                ("find", directory, "-xdev", "-uid", str(case.uid), "-delete"),
            )
        process_check = self._worker_command(
            worker,
            ("pgrep", "-u", str(case.uid)),
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if process_check.returncode not in (1,) or process_check.stdout.strip():
            raise SandboxRuntimeError("previous case processes could not be cleared")
        for database in ("passwd", "group"):
            identity_check = self._worker_command(
                worker,
                ("getent", database, case.user_name),
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
            if identity_check.returncode != 2 or identity_check.stdout.strip():
                raise SandboxRuntimeError("previous case identity could not be cleared")
        for directory in ("/tmp", "/var/tmp", "/dev/shm"):
            residue = self._worker_command(
                worker,
                ("find", directory, "-xdev", "-uid", str(case.uid), "-print", "-quit"),
                user="root",
                timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
            )
            if residue.returncode != 0 or residue.stdout.strip():
                raise SandboxRuntimeError("previous case writable state could not be cleared")
        self._admin_checked(
            worker,
            (
                "find",
                str(case.root),
                "-mindepth",
                "1",
                "-maxdepth",
                "1",
                "-exec",
                "rm",
                "-rf",
                "--",
                "{}",
                "+",
            ),
        )

    def _clear_case_ipc(self, worker: SandboxWorker, case: CaseWorkspace) -> None:
        self._admin_checked(
            worker,
            ("python3", "-c", IPC_CLEANUP_SCRIPT, str(case.uid)),
        )

    def _admin_checked(
        self,
        worker: SandboxWorker,
        argv: Sequence[str],
        *,
        accepted: tuple[int, ...] = (0,),
    ) -> CommandResult:
        result = self._worker_command(
            worker,
            argv,
            user="root",
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if result.timed_out or result.returncode not in accepted:
            raise SandboxRuntimeError(f"case identity command failed: {argv[0]}")
        return result

    def _case_user_checked(
        self,
        worker: SandboxWorker,
        case: CaseWorkspace,
        argv: Sequence[str],
        failure: str,
    ) -> None:
        result = self._worker_command(
            worker,
            argv,
            user=case.user_name,
            timeout_seconds=self.manifest.limits.preflight_timeout_seconds,
        )
        if result.timed_out or result.returncode != 0:
            raise SandboxRuntimeError(failure)

    def _worker_command(
        self,
        worker: SandboxWorker,
        argv: Sequence[str],
        *,
        user: str,
        timeout_seconds: int,
    ) -> CommandResult:
        self._require_owned_worker(worker)
        command = ("sbx", "exec", "--user", user, worker.id, *argv)
        return self.process.run(command, timeout_seconds=timeout_seconds)

    def __enter__(self) -> SandboxRuntime:
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def _checked(self, argv: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        result = self.process.run(argv, timeout_seconds=timeout_seconds)
        if result.timed_out:
            raise SandboxRuntimeError(f"command timed out: {' '.join(argv[:2])}")
        if result.returncode != 0:
            diagnostic = _safe_diagnostic(result.stderr.strip() or result.stdout.strip() or "no diagnostic")
            raise SandboxRuntimeError(f"command failed: {' '.join(argv[:2])}: {diagnostic}")
        return result

    def _json_command(self, argv: tuple[str, ...], timeout_seconds: int) -> Mapping[str, object]:
        result = self._checked(argv, timeout_seconds)
        try:
            return _mapping(json.loads(result.stdout), "sbx JSON output")
        except json.JSONDecodeError as error:
            raise SandboxRuntimeError(f"invalid JSON from {' '.join(argv[:2])}") from error

    def _list_sandboxes(self) -> list[Mapping[str, object]]:
        payload = self._json_command(
            ("sbx", "ls", "--json"), self.manifest.limits.preflight_timeout_seconds
        )
        raw_items = payload.get("sandboxes")
        if not isinstance(raw_items, list) or not all(isinstance(item, Mapping) for item in raw_items):
            raise SandboxRuntimeError("sbx ls --json returned an invalid sandbox list")
        return list(raw_items)

    def _verify_template(self, payload: Mapping[str, object]) -> None:
        raw_images = payload.get("images")
        if not isinstance(raw_images, list):
            raise SandboxRuntimeError("sbx template ls --json returned an invalid image list")
        image_with_tag, digest = self.manifest.codex.template.rsplit("@sha256:", 1)
        repository, tag = image_with_tag.rsplit(":", 1)
        for image in raw_images:
            if not isinstance(image, Mapping):
                continue
            image_id = image.get("id")
            if (
                image.get("repository") == repository
                and image.get("tag") == tag
                and isinstance(image_id, str)
                and re.fullmatch(r"[0-9a-f]{12}", image_id) is not None
                and digest.startswith(image_id)
            ):
                return
        raise SandboxRuntimeError("pinned Codex template digest is not available")

    def _probe_results_root(self) -> None:
        probe = self.results_root / f".ai-skills-preflight-{self.invocation_id}"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                probe,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            os.write(descriptor, b"probe\n")
            os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.read(descriptor, 64) != b"probe\n":
                raise OSError("result root probe could not be read back")
            os.close(descriptor)
            descriptor = None
            probe.unlink()
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
            raise SandboxRuntimeError("durable result root write/delete probe failed") from error

    def _verify_network_policy(self, payload: Mapping[str, object]) -> None:
        raw_rules = payload.get("rules")
        if not isinstance(raw_rules, list):
            raise SandboxRuntimeError("sbx policy ls --json returned an invalid rule list")
        policy = self.manifest.sbx.network_policy
        by_id = {
            rule.get("id"): rule
            for rule in raw_rules
            if isinstance(rule, Mapping) and isinstance(rule.get("id"), str)
        }
        for rule_id in policy.required_rule_ids:
            rule = by_id.get(rule_id)
            if (
                not isinstance(rule, Mapping)
                or rule.get("policy_id") != policy.policy_id
                or rule.get("resource_type") != "network"
                or rule.get("decision") != "allow"
                or rule.get("origin") != "local"
                or rule.get("status") != "active"
            ):
                raise SandboxRuntimeError("active policy does not match the balanced preset")
        model_resources = by_id["default-ai-services"].get("resources")
        required_model_routes = {
            "**.openai.com:443",
            "chatgpt.com:443",
            "**.chatgpt.com:443",
        }
        if not isinstance(model_resources, list) or not required_model_routes.issubset(model_resources):
            raise SandboxRuntimeError("balanced policy does not expose the exact OpenAI model routes")
        if network_policy_sha256(payload) != policy.rules_sha256:
            raise SandboxRuntimeError("active balanced policy rule set does not match its immutable pin")


def network_policy_sha256(payload: Mapping[str, object]) -> str:
    """Hash the complete active network rule contract in a stable representation."""
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise SandboxRuntimeError("sbx policy ls --json returned an invalid rule list")
    normalized: list[dict[str, object]] = []
    identifiers: set[str] = set()
    scalar_fields = (
        "id",
        "policy_id",
        "scope",
        "applies_to",
        "resource_type",
        "decision",
        "origin",
        "status",
    )
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, Mapping):
            raise SandboxRuntimeError("sbx policy rule must be an object")
        values = {field: raw_rule.get(field) for field in scalar_fields}
        if not all(isinstance(value, str) and value for value in values.values()):
            raise SandboxRuntimeError("sbx policy rule metadata is invalid")
        identifier = values["id"]
        assert isinstance(identifier, str)
        if identifier in identifiers:
            raise SandboxRuntimeError("sbx policy rule identifiers must be unique")
        identifiers.add(identifier)
        resources = raw_rule.get("resources")
        if (
            not isinstance(resources, list)
            or not resources
            or not all(isinstance(resource, str) and resource for resource in resources)
            or len(resources) != len(set(resources))
        ):
            raise SandboxRuntimeError("sbx policy rule resources are invalid")
        normalized.append({**values, "resources": sorted(resources)})
    serialized = json.dumps(
        sorted(normalized, key=lambda item: str(item["id"])),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ManifestError(f"{label} must be a JSON object")
    return value


def _section(parent: Mapping[str, object], key: str, expected: set[str]) -> Mapping[str, object]:
    section = _mapping(parent.get(key), key)
    _expect_keys(section, expected, key)
    return section


def _expect_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise ManifestError(f"{label} has unknown keys: {', '.join(unknown)}")
    if missing:
        raise ManifestError(f"{label} is missing keys: {', '.join(missing)}")


def _string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ManifestError(f"{key} must be a non-empty string")
    return item


def _plain_version(value: Mapping[str, object], key: str) -> str:
    item = _string(value, key)
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", item):
        raise ManifestError(f"{key} must be an exact semantic version")
    return item


def _hex_string(value: Mapping[str, object], key: str, length: int) -> str:
    item = _string(value, key)
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", item):
        raise ManifestError(f"{key} must be {length} lowercase hexadecimal characters")
    return item


def _integer(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ManifestError(f"{key} must be an integer")
    return item


def _positive_integer(value: Mapping[str, object], key: str) -> int:
    item = _integer(value, key)
    if item <= 0:
        raise ManifestError(f"{key} must be positive")
    return item


def _boolean(value: Mapping[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ManifestError(f"{key} must be a boolean")
    return item


def _string_tuple(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    item = value.get(key)
    if not isinstance(item, list) or not item or not all(isinstance(part, str) and part for part in item):
        raise ManifestError(f"{key} must be a non-empty string array")
    return tuple(item)


def _safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9.+-]+", "-", value).strip("-")
    if not cleaned:
        raise SandboxRuntimeError("invocation id must contain a sandbox-safe character")
    return cleaned[:48]


def _safe_diagnostic(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.regex.sub("[REDACTED]", redacted)
    return redacted[:8192]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
