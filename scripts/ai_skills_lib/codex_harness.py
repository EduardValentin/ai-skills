"""Codex harness adapter for isolated Agent Skills evaluations."""

from __future__ import annotations

from collections.abc import Mapping
import json
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import time

from scripts.ai_skills_lib.harness import (
    ActorInput,
    HarnessCapabilities,
    HarnessExecution,
    HarnessRequest,
)
from scripts.ai_skills_lib.fixture_proxy import FixtureProxy, FixtureProxyError
from scripts.ai_skills_lib.sandbox_runtime import (
    CommandResult,
    SandboxRuntime,
    SandboxRuntimeError,
)
from scripts.ai_skills_lib.secret_patterns import (
    bounded_redacted_runtime_text,
    redact_runtime_secrets,
)


RUNTIME_ENTRIES = ("SKILL.md", "scripts", "references", "assets")
TEXT_RUNTIME_ENTRIES = RUNTIME_ENTRIES
DISABLED_FEATURES = (
    "apps",
    "browser_use",
    "computer_use",
    "enable_fanout",
    "goals",
    "hooks",
    "multi_agent",
    "plugins",
    "shell_snapshot",
    "workspace_dependencies",
)
SIMPLE_SKILL_READERS = frozenset(("cat", "sed"))
SHELL_EXECUTABLES = frozenset(("bash", "sh", "zsh"))
SHELL_CONTROL_TOKENS = frozenset((";", "&&", "||", "|", ">", ">>", "<", "2>", "2>>"))
MAX_DIAGNOSTIC_CHARS = 8192
MAX_TRACE_SCALAR_BYTES = 4096


class CodexOutputError(RuntimeError):
    """Codex setup or observable output is not trustworthy enough to grade."""


class CodexHarnessAdapter:
    """Execute Codex through the shared Docker Sandboxes runtime."""

    def __init__(
        self,
        runtime: SandboxRuntime,
        *,
        allowed_skill_root: Path | None = None,
        fixture_proxy: FixtureProxy | None = None,
    ) -> None:
        self.runtime = runtime
        self.allowed_skill_root = allowed_skill_root.resolve() if allowed_skill_root else None
        self.fixture_proxy = fixture_proxy
        self._capabilities: HarnessCapabilities | None = None

    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        runtime_report = self.runtime.preflight()
        if not runtime_report.available:
            return HarnessCapabilities(
                harness_name="codex",
                available=False,
                actor_model=None,
                actor_reasoning_effort=None,
                judge_model=None,
                judge_reasoning_effort=None,
                reports_token_usage=True,
                reports_successful_skill_reads=True,
                details=runtime_report.details,
                failure=runtime_report.failure,
            )
        try:
            worker = self.runtime.acquire_worker("actor")
            case = self.runtime.prepare_case(worker, "preflight")
            self.runtime.initialize_codex_home(worker, case)
            timeout = self.runtime.manifest.limits.preflight_timeout_seconds
            version = self.runtime.execute(worker, case, ("codex", "--version"), timeout_seconds=timeout)
            help_result = self.runtime.execute(
                worker, case, ("codex", "exec", "--help"), timeout_seconds=timeout
            )
            models_result = self.runtime.execute(
                worker, case, ("codex", "debug", "models"), timeout_seconds=timeout
            )
            for label, result in (
                ("version", version),
                ("exec help", help_result),
                ("model catalog", models_result),
            ):
                _require_success(result, f"Codex {label}")
            expected_version = f"codex-cli {self.runtime.manifest.codex.version}"
            if version.stdout.strip() != expected_version:
                raise CodexOutputError("Codex version does not match the runtime pin")
            missing_flags = [
                flag for flag in self.runtime.manifest.codex.exec_flags if flag not in help_result.stdout
            ]
            if missing_flags:
                raise CodexOutputError("pinned Codex does not expose every required execution flag")
            model, reasoning = _parse_default_model(models_result.stdout)
            if require_fixtures:
                if self.fixture_proxy is None:
                    raise CodexOutputError(
                        "fixture cases require a configured fixture proxy"
                    )
                self.fixture_proxy.preflight(worker, case)
            self.runtime.prepare_case(worker, "preflight-reset")
        except (
            CodexOutputError,
            FixtureProxyError,
            SandboxRuntimeError,
            OSError,
            ValueError,
        ) as error:
            return HarnessCapabilities(
                harness_name="codex",
                available=False,
                actor_model=None,
                actor_reasoning_effort=None,
                judge_model=None,
                judge_reasoning_effort=None,
                reports_token_usage=True,
                reports_successful_skill_reads=True,
                details=runtime_report.details,
                failure=str(error),
            )
        self._capabilities = HarnessCapabilities(
            harness_name="codex",
            available=True,
            actor_model=model,
            actor_reasoning_effort=reasoning,
            judge_model=model,
            judge_reasoning_effort=reasoning,
            reports_token_usage=True,
            reports_successful_skill_reads=True,
            details=(*runtime_report.details, expected_version, f"default model {model}/{reasoning}"),
            failure=None,
        )
        return self._capabilities

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        if request.fixture_initialization is not None and self.fixture_proxy is None:
            raise CodexOutputError("fixture request requires a configured fixture proxy")
        case_fixture_root = _resolve_case_fixture_root(
            request.fixture_root,
            self.allowed_skill_root,
        )
        if request.fixture_initialization is not None:
            assert case_fixture_root is not None
            _require_case_fixture_file(
                request.fixture_initialization,
                case_fixture_root,
                expected_name="mockserverInitialization.json",
            )
        durable_dir = artifact_dir.resolve()
        results_root = self.runtime.results_root.resolve()
        if durable_dir == results_root or not durable_dir.is_relative_to(results_root):
            raise CodexOutputError("durable artifact directory must be inside the runtime result root")
        with self.runtime.lease_worker(request.role) as worker:
            fixture_session = None
            try:
                fixture_trace: tuple[Mapping[str, object], ...] = ()
                case = self.runtime.prepare_case(worker, request.run_variant)
                if durable_dir == case.root or durable_dir.is_relative_to(case.root):
                    raise CodexOutputError("durable results cannot be mounted into an actor or judge case")
                durable_dir.mkdir(parents=True, exist_ok=True)
                self.runtime.initialize_codex_home(worker, case)

                if request.actor_inputs and self.allowed_skill_root is None:
                    raise CodexOutputError(
                        "actor input staging requires an explicit allowed repository skill root"
                    )
                if request.actor_inputs:
                    assert case_fixture_root is not None
                    _stage_actor_inputs(
                        request.actor_inputs,
                        case.workspace,
                        case_fixture_root,
                    )

                if request.skill_sources and self.allowed_skill_root is None:
                    raise CodexOutputError("skill projection requires an explicit allowed repository skill root")
                for source in request.skill_sources:
                    resolved = source.resolve()
                    if self.allowed_skill_root is None or not resolved.is_relative_to(self.allowed_skill_root):
                        raise CodexOutputError("skill source is outside the allowed repository skill root")
                    _validate_skill_name(resolved.name)
                    project_actor_skill(resolved, case.skills / resolved.name)

                if request.expected_skill:
                    _validate_skill_name(request.expected_skill)
                candidate_expected_path = (
                    case.skills / request.expected_skill / "SKILL.md" if request.expected_skill else None
                )
                expected_path = (
                    candidate_expected_path
                    if candidate_expected_path is not None and candidate_expected_path.is_file()
                    else None
                )
                expected_digest = _file_sha256(expected_path) if expected_path is not None else None
                expected_line_count = (
                    len(expected_path.read_text(encoding="utf-8").splitlines())
                    if expected_path is not None
                    else None
                )
                shell_environment = request.shell_environment
                if request.fixture_initialization is not None:
                    assert self.fixture_proxy is not None
                    fixture_session = self.fixture_proxy.prepare_case(
                        worker,
                        case,
                        request.fixture_initialization,
                        case_fixture_root,
                    )
                    shell_environment = _merge_shell_environment(
                        shell_environment,
                        fixture_session.shell_environment,
                    )
                command = self._codex_command(
                    request,
                    case.workspace,
                    shell_environment=shell_environment,
                )
                started = time.monotonic()
                result = self.runtime.execute(
                    worker,
                    case,
                    command,
                    timeout_seconds=request.timeout_seconds,
                )
                duration_ms = max(0, round((time.monotonic() - started) * 1000))
                parsed = _parse_codex_output(
                    result,
                    expected_path,
                    expected_digest,
                    expected_line_count,
                )
                lifecycle_failure = result.lifecycle_failure
                try:
                    if result.timed_out:
                        if fixture_session is not None:
                            assert self.fixture_proxy is not None
                            self.fixture_proxy.discard_worker_state(worker)
                    else:
                        self.runtime.quiesce_case(worker, case)
                    if fixture_session is not None and not result.timed_out:
                        assert self.fixture_proxy is not None
                        fixture_trace = self.fixture_proxy.collect_and_reset(
                            worker,
                            case,
                            fixture_session,
                        )
                except Exception as lifecycle_error:
                    if isinstance(lifecycle_error, FixtureProxyError):
                        fixture_trace = lifecycle_error.evidence
                    diagnostics = [
                        "post-execution lifecycle failed: "
                        f"{_redact(str(lifecycle_error))[:MAX_DIAGNOSTIC_CHARS]}"
                    ]
                    if fixture_session is not None:
                        assert self.fixture_proxy is not None
                        try:
                            self.fixture_proxy.discard_worker_state(worker)
                        except Exception as cleanup_error:
                            diagnostics.append(
                                "fixture state cleanup failed: "
                                f"{_redact(str(cleanup_error))[:MAX_DIAGNOSTIC_CHARS]}"
                            )
                    try:
                        self.runtime.invalidate_worker(worker)
                    except Exception as cleanup_error:
                        diagnostics.append(
                            "worker invalidation failed: "
                            f"{_redact(str(cleanup_error))[:MAX_DIAGNOSTIC_CHARS]}"
                        )
                    lifecycle_failure = "\n".join(
                        item for item in (lifecycle_failure, *diagnostics) if item
                    )[:MAX_DIAGNOSTIC_CHARS]
                model, reasoning = self._selected_model(request)
                failure = "\n".join(
                    item for item in (parsed.failure, lifecycle_failure) if item
                ) or None
                execution = HarnessExecution(
                    response=parsed.response,
                    trace=(*parsed.trace, *fixture_trace),
                    duration_ms=duration_ms,
                    total_tokens=parsed.total_tokens,
                    input_tokens=parsed.input_tokens,
                    output_tokens=parsed.output_tokens,
                    cached_tokens=parsed.cached_tokens,
                    token_source="codex_jsonl" if parsed.has_usage else "unavailable",
                    successful_skill_reads=parsed.successful_skill_reads,
                    exit_code=result.returncode,
                    failure=failure,
                    model=model,
                    reasoning_effort=reasoning,
                    timed_out=result.timed_out,
                )
            except Exception:
                if fixture_session is not None:
                    assert self.fixture_proxy is not None
                    self.fixture_proxy.discard_worker_state(worker)
                self.runtime.invalidate_worker(worker)
                raise
        return execution

    def _codex_command(
        self,
        request: HarnessRequest,
        workspace: Path,
        *,
        shell_environment: tuple[tuple[str, str], ...] | None = None,
    ) -> tuple[str, ...]:
        command: list[str] = ["codex", "exec", *self.runtime.manifest.codex.exec_flags]
        command.extend(("-c", "allow_login_shell=false"))
        command.extend(("-c", "shell_environment_policy.inherit=core"))
        command.extend(("-c", "shell_environment_policy.ignore_default_excludes=false"))
        for name, value in sorted(
            request.shell_environment if shell_environment is None else shell_environment
        ):
            command.extend(
                (
                    "-c",
                    f"shell_environment_policy.set.{name}={json.dumps(value, ensure_ascii=True)}",
                )
            )
        for feature in DISABLED_FEATURES:
            command.extend(("--disable", feature))
        if request.model:
            command.extend(("--model", request.model))
        if request.reasoning_effort:
            command.extend(("-c", f'model_reasoning_effort="{request.reasoning_effort}"'))
        command.extend(("-C", str(workspace), "--", request.prompt))
        return tuple(command)

    def _selected_model(self, request: HarnessRequest) -> tuple[str | None, str | None]:
        if request.model or request.reasoning_effort:
            defaults = self._capabilities
            default_model = None
            default_reasoning = None
            if defaults is not None and request.role == "judge":
                default_model = defaults.judge_model
                default_reasoning = defaults.judge_reasoning_effort
            elif defaults is not None:
                default_model = defaults.actor_model
                default_reasoning = defaults.actor_reasoning_effort
            return (
                request.model or default_model,
                request.reasoning_effort or default_reasoning,
            )
        if self._capabilities is None:
            return None, None
        if request.role == "judge":
            return self._capabilities.judge_model, self._capabilities.judge_reasoning_effort
        return self._capabilities.actor_model, self._capabilities.actor_reasoning_effort


def project_actor_skill(source: Path, destination: Path) -> None:
    """Copy one self-contained skill while preserving the eval oracle boundary."""
    if not source.is_dir() or not (source / "SKILL.md").is_file():
        raise CodexOutputError("skill projection source must contain SKILL.md")
    allowed = set(RUNTIME_ENTRIES) | {"evals"}
    unknown = sorted(path.name for path in source.iterdir() if path.name not in allowed)
    if unknown:
        raise CodexOutputError(f"skill projection contains unsupported root entries: {', '.join(unknown)}")
    if destination.exists() or destination.is_symlink():
        raise CodexOutputError("skill projection destination already exists")

    for entry_name in RUNTIME_ENTRIES:
        entry = source / entry_name
        if not entry.exists():
            continue
        _reject_symlinks(entry)
    for entry_name in TEXT_RUNTIME_ENTRIES:
        entry = source / entry_name
        if not entry.exists():
            continue
        paths = (entry,) if entry.is_file() else tuple(path for path in entry.rglob("*") if path.is_file())
        for path in paths:
            content = path.read_bytes()
            if re.search(rb"(?:^|[\s/'\"`(])(?:\.\.?[/\\])*evals[/\\]", content):
                raise CodexOutputError("actor runtime material must not reference evals content")

    destination.mkdir(parents=True)
    for entry_name in RUNTIME_ENTRIES:
        source_entry = source / entry_name
        if not source_entry.exists():
            continue
        destination_entry = destination / entry_name
        if source_entry.is_dir():
            shutil.copytree(source_entry, destination_entry)
        else:
            shutil.copy2(source_entry, destination_entry)
    for root, directories, files in os.walk(destination):
        for name in files:
            path = Path(root) / name
            path.chmod(0o555 if path.stat().st_mode & 0o111 else 0o444)
        for name in directories:
            (Path(root) / name).chmod(0o555)
    destination.chmod(0o555)


def _stage_actor_inputs(
    declarations: tuple[ActorInput, ...],
    workspace: Path,
    case_fixture_root: Path,
) -> None:
    input_root = case_fixture_root / "inputs"
    for declaration in declarations:
        source = _require_case_fixture_file(declaration.source, input_root)
        destination = workspace.joinpath(*declaration.destination.parts)
        if destination.exists() or destination.is_symlink():
            raise CodexOutputError("actor input destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        destination.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)


def _resolve_case_fixture_root(
    declared_root: Path | None,
    allowed_skill_root: Path | None,
) -> Path | None:
    if declared_root is None:
        return None
    if allowed_skill_root is None:
        raise CodexOutputError(
            "case fixture root requires an explicit allowed repository skill root"
        )
    root = _require_contained_path(declared_root, allowed_skill_root, require_directory=True)
    relative = root.relative_to(allowed_skill_root)
    if len(relative.parts) != 5 or relative.parts[2:4] != ("evals", "fixtures"):
        raise CodexOutputError(
            "case fixture root must be skills/<group>/<skill>/evals/fixtures/<case>"
        )
    return root


def _require_case_fixture_file(
    declared_path: Path,
    root: Path,
    *,
    expected_name: str | None = None,
) -> Path:
    source = _require_contained_path(declared_path, root, require_directory=False)
    if source == root or not source.is_file():
        raise CodexOutputError("fixture source must be a contained regular file")
    if expected_name is not None and source != root / expected_name:
        raise CodexOutputError(
            f"fixture initialization must be {expected_name} in the exact case fixture root"
        )
    return source


def _require_contained_path(
    declared_path: Path,
    root: Path,
    *,
    require_directory: bool,
) -> Path:
    try:
        resolved_root = root.resolve(strict=True)
        resolved = declared_path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CodexOutputError("case fixture root or source does not exist") from error
    if not resolved.is_relative_to(resolved_root):
        raise CodexOutputError("fixture source is outside the exact case fixture root")
    candidate = declared_path.absolute()
    if candidate.is_symlink():
        raise CodexOutputError("case fixture paths cannot contain symlinks")
    while candidate.resolve(strict=False) != resolved_root:
        if candidate.is_symlink():
            raise CodexOutputError("case fixture paths cannot contain symlinks")
        if candidate.parent == candidate:
            raise CodexOutputError("fixture source is outside the exact case fixture root")
        candidate = candidate.parent
    if require_directory and not resolved.is_dir():
        raise CodexOutputError("case fixture root must be a directory")
    return resolved


def _merge_shell_environment(
    declared: tuple[tuple[str, str], ...],
    fixture: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    merged = dict(declared)
    for name, value in fixture:
        existing = merged.get(name)
        if existing is not None and existing != value:
            raise CodexOutputError(
                f"declared shell environment conflicts with fixture-owned variable {name}"
            )
        merged[name] = value
    return tuple(sorted(merged.items()))


def _reject_symlinks(entry: Path) -> None:
    if entry.is_symlink():
        raise CodexOutputError("skill projection cannot contain symlinks")
    if entry.is_dir():
        for root, directories, files in os.walk(entry, followlinks=False):
            for name in (*directories, *files):
                if (Path(root) / name).is_symlink():
                    raise CodexOutputError("skill projection cannot contain symlinks")


def _validate_skill_name(name: str) -> None:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise CodexOutputError("skill name is not a path-safe Agent Skills name")


def _require_success(result: CommandResult, label: str) -> None:
    if result.timed_out:
        raise CodexOutputError(f"{label} timed out")
    if result.returncode != 0:
        message = _redact(result.stderr.strip() or result.stdout.strip() or "no diagnostic")
        raise CodexOutputError(f"{label} failed: {message[:MAX_DIAGNOSTIC_CHARS]}")


def _parse_default_model(raw: str) -> tuple[str, str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CodexOutputError("Codex model catalog was not valid JSON") from error
    if not isinstance(payload, Mapping) or not isinstance(payload.get("models"), list):
        raise CodexOutputError("Codex model catalog has an unsupported shape")
    for model in payload["models"]:
        if not isinstance(model, Mapping) or model.get("visibility") not in (None, "list"):
            continue
        slug = model.get("slug")
        reasoning = model.get("default_reasoning_level")
        if isinstance(slug, str) and slug and isinstance(reasoning, str) and reasoning:
            return slug, reasoning
    raise CodexOutputError("Codex model catalog does not expose a configured default")


class _ParsedCodexOutput:
    def __init__(
        self,
        *,
        response: str,
        trace: tuple[Mapping[str, object], ...],
        input_tokens: int | None,
        output_tokens: int | None,
        cached_tokens: int | None,
        successful_skill_reads: tuple[Path, ...],
        failure: str | None,
    ) -> None:
        self.response = response
        self.trace = trace
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cached_tokens = cached_tokens
        self.total_tokens = (
            input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None
        )
        self.has_usage = input_tokens is not None or output_tokens is not None or cached_tokens is not None
        self.successful_skill_reads = successful_skill_reads
        self.failure = failure


def _parse_codex_output(
    result: CommandResult,
    expected_skill_path: Path | None,
    expected_skill_digest: str | None,
    expected_skill_line_count: int | None,
) -> _ParsedCodexOutput:
    responses: list[str] = []
    trace: list[Mapping[str, object]] = []
    diagnostics: list[str] = []
    successful_reads: list[Path] = []
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    thread_started = 0
    turn_started = 0
    turn_completed = 0
    terminal_seen = False
    active_commands: set[str] = set()

    for line_number, line in enumerate(result.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            diagnostics.append(f"Codex emitted invalid JSONL at line {line_number}")
            continue
        if not isinstance(event, Mapping):
            diagnostics.append(f"Codex emitted a non-object JSONL event at line {line_number}")
            continue
        event_type = event.get("type")
        if terminal_seen:
            diagnostics.append("Codex emitted events after the terminal turn event")
            continue
        if event_type == "thread.started":
            thread_started += 1
            trace.append({"event": "harness_thread_started"})
        elif event_type == "turn.started":
            turn_started += 1
            trace.append({"event": "harness_turn_started"})
        elif event_type in ("item.started", "item.completed"):
            item = event.get("item")
            if not isinstance(item, Mapping):
                continue
            item_type = item.get("type")
            if event_type == "item.completed" and item_type == "agent_message":
                text = item.get("text")
                if isinstance(text, str):
                    responses.append(_redact(text))
            elif item_type == "command_execution":
                item_id = item.get("id")
                if not isinstance(item_id, str) or not item_id:
                    diagnostics.append("Codex command event is missing an item id")
                    continue
                if event_type == "item.started":
                    if item_id in active_commands:
                        diagnostics.append("Codex command item started more than once")
                    active_commands.add(item_id)
                elif item_id not in active_commands:
                    diagnostics.append("Codex command completion has no matching start event")
                else:
                    active_commands.remove(item_id)
                command = item.get("command")
                command_name = _command_name(command) if isinstance(command, str) else None
                normalized: dict[str, object] = {
                    "event": "command_completed" if event_type == "item.completed" else "command_started"
                }
                if command_name:
                    normalized["command"] = bounded_redacted_runtime_text(
                        command_name,
                        MAX_TRACE_SCALAR_BYTES,
                    )
                if event_type == "item.completed" and isinstance(item.get("exit_code"), int):
                    normalized["exit_code"] = item["exit_code"]
                trace.append(normalized)
                if (
                    event_type == "item.completed"
                    and expected_skill_path is not None
                    and item.get("exit_code") == 0
                    and item.get("status") == "completed"
                    and isinstance(command, str)
                    and _command_reads_exact_skill(
                        command,
                        expected_skill_path,
                        expected_skill_line_count,
                    )
                    and expected_skill_path not in successful_reads
                ):
                    successful_reads.append(expected_skill_path)
                    trace.append(
                        {
                            "event": "skill_read",
                            "path": bounded_redacted_runtime_text(
                                str(expected_skill_path),
                                MAX_TRACE_SCALAR_BYTES,
                            ),
                        }
                    )
        elif event_type == "turn.completed":
            turn_completed += 1
            terminal_seen = True
            usage = event.get("usage")
            if isinstance(usage, Mapping):
                input_tokens = _optional_nonnegative_integer(usage.get("input_tokens"))
                output_tokens = _optional_nonnegative_integer(usage.get("output_tokens"))
                cached_tokens = _optional_nonnegative_integer(usage.get("cached_input_tokens"))
            trace.append({"event": "harness_turn_completed"})
        elif event_type in ("error", "turn.failed"):
            if event_type == "turn.failed":
                terminal_seen = True
            message = _native_message(event)
            if message:
                diagnostics.append(message)
                trace.append({"event": "harness_failure", "message": message})

    if result.stdout_truncated or result.stderr_truncated:
        diagnostics.append("Codex output was truncated at the configured capture limit")
    if result.returncode == 0:
        if thread_started != 1 or turn_started != 1 or turn_completed != 1:
            diagnostics.append("successful Codex output requires one thread.started, turn.started, and turn.completed")
        if active_commands:
            diagnostics.append("Codex output ended with incomplete command events")
        if not responses:
            diagnostics.append("successful Codex output is missing a final agent response")
        if input_tokens is None or output_tokens is None:
            diagnostics.append("successful Codex turn.completed is missing token usage")
    if successful_reads and (
        result.timed_out
        or
        expected_skill_path is None
        or expected_skill_digest is None
        or not expected_skill_path.is_file()
        or _file_sha256(expected_skill_path) != expected_skill_digest
    ):
        successful_reads.clear()
        diagnostics.append("projected SKILL.md changed before activation evidence was finalized")
    stderr = _redact(result.stderr.strip())
    if stderr:
        diagnostics.append(stderr[:MAX_DIAGNOSTIC_CHARS])
    if result.timed_out and not diagnostics:
        diagnostics.append("Codex execution timed out")
    if result.returncode != 0 and not diagnostics:
        diagnostics.append(f"Codex exited with status {result.returncode}")
    failure = "\n".join(dict.fromkeys(diagnostics))[:MAX_DIAGNOSTIC_CHARS] or None
    return _ParsedCodexOutput(
        response=responses[-1] if responses else "",
        trace=tuple(trace),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        successful_skill_reads=tuple(successful_reads),
        failure=failure,
    )


def _command_name(command: str) -> str | None:
    tokens = _simple_command_tokens(command)
    return Path(tokens[0]).name if tokens else None


def _command_reads_exact_skill(
    command: str,
    expected_path: Path,
    expected_line_count: int | None,
) -> bool:
    tokens = _simple_command_tokens(command)
    if not tokens:
        return False
    expected = os.path.normpath(str(expected_path))
    reader = Path(tokens[0]).name
    arguments = list(tokens[1:])
    if reader == "cat":
        if arguments[:1] == ["--"]:
            arguments = arguments[1:]
        return len(arguments) == 1 and os.path.normpath(arguments[0]) == expected
    if reader == "sed":
        if len(arguments) == 4 and arguments[2] == "--":
            option, expression, _, operand = arguments
        elif len(arguments) == 3:
            option, expression, operand = arguments
        else:
            return False
        if option != "-n" or os.path.normpath(operand) != expected:
            return False
        match = re.fullmatch(r"1,(\$|[1-9][0-9]*)p", expression)
        if not match:
            return False
        if match.group(1) == "$":
            return True
        return expected_line_count is not None and int(match.group(1)) >= expected_line_count
    return False


def _simple_command_tokens(command: str) -> tuple[str, ...] | None:
    try:
        outer = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not outer:
        return None
    executable = Path(outer[0]).name
    if executable in SHELL_EXECUTABLES:
        if len(outer) != 3 or outer[1] not in ("-c", "-lc"):
            return None
        try:
            outer = shlex.split(outer[2], posix=True)
        except ValueError:
            return None
    if not outer or any(token in SHELL_CONTROL_TOKENS for token in outer):
        return None
    return tuple(outer)


def _optional_nonnegative_integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _native_message(event: Mapping[str, object]) -> str | None:
    raw: object = event.get("message")
    if raw is None and isinstance(event.get("error"), Mapping):
        raw = event["error"].get("message")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return _redact(raw.strip())[:MAX_DIAGNOSTIC_CHARS]


def _redact(value: str) -> str:
    return redact_runtime_secrets(value)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
