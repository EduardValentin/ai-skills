"""Harness-neutral contracts for isolated evaluation execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Literal, Protocol, runtime_checkable

from scripts.ai_skills_lib.json_schema_policy import (
    MAX_JSON_SCHEMA_BYTES,
    MAX_JSON_SCHEMA_DEPTH,
    MAX_JSON_SCHEMA_NODES,
)
from scripts.ai_skills_lib.runtime_environment import CASE_OWNED_ENVIRONMENT_NAMES


HarnessRole = Literal["actor", "judge"]
CapturedOutputKind = Literal["file", "directory"]
_TRUSTED_SKILL_READ_COMMANDS = frozenset({"cat", "sed"})


def canonical_codex_skill_path(skill_name: str) -> PurePosixPath:
    """Return the actor-visible installed path for one Codex skill."""
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill_name) is None:
        raise ValueError("Codex skill name is not path safe")
    return PurePosixPath("/case/codex-home/skills") / skill_name / "SKILL.md"


def _require_contained_relative_path(path: PurePosixPath, label: str) -> None:
    if (
        path.is_absolute()
        or not path.parts
        or str(path) in ("", ".")
        or ".." in path.parts
        or "\\" in str(path)
    ):
        raise ValueError(f"{label} must be a contained relative path")


@dataclass(frozen=True)
class PreparedFile:
    """Immutable bytes captured from one validated repository file."""

    source: Path
    content: bytes
    executable: bool = False
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source, Path) or not isinstance(self.content, bytes):
            raise ValueError("prepared file requires a Path source and immutable bytes")
        if type(self.executable) is not bool:
            raise ValueError("prepared file executable state must be boolean")
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())


@dataclass(frozen=True)
class PreparedResponseSchema:
    """One bounded canonical judge schema snapshot bound and staged as exact bytes."""

    content: bytes
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.content, bytes)
            or not self.content.endswith(b"\n")
            or len(self.content) > MAX_JSON_SCHEMA_BYTES
        ):
            raise ValueError("prepared response schema requires bounded canonical bytes")
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())


@dataclass(frozen=True)
class PreparedSkillFile:
    """One immutable runtime file inside a prepared skill catalog entry."""

    relative_path: PurePosixPath
    content: bytes
    executable: bool
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_contained_relative_path(self.relative_path, "prepared skill file path")
        if not isinstance(self.content, bytes) or type(self.executable) is not bool:
            raise ValueError("prepared skill file requires immutable bytes and a mode")
        object.__setattr__(self, "sha256", hashlib.sha256(self.content).hexdigest())


@dataclass(frozen=True)
class PreparedSkillSource:
    """Exact actor-visible bytes for one catalog skill, frozen before preflight."""

    source_root: Path
    name: str
    files: tuple[PreparedSkillFile, ...]
    directories: tuple[PurePosixPath, ...] = field(default_factory=tuple)
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_root, Path):
            raise ValueError("prepared skill source root must be a Path")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.name):
            raise ValueError("prepared skill name is not path safe")
        if not isinstance(self.files, tuple) or not all(
            isinstance(item, PreparedSkillFile) for item in self.files
        ):
            raise ValueError("prepared skill files must be an immutable tuple")
        if not isinstance(self.directories, tuple) or not all(
            isinstance(path, PurePosixPath) for path in self.directories
        ):
            raise ValueError("prepared skill directories must be an immutable tuple")
        file_paths = tuple(item.relative_path for item in self.files)
        for path in self.directories:
            _require_contained_relative_path(path, "prepared skill directory path")
        if (
            len(file_paths) != len(set(file_paths))
            or len(self.directories) != len(set(self.directories))
            or set(file_paths) & set(self.directories)
            or PurePosixPath("SKILL.md") not in file_paths
        ):
            raise ValueError("prepared skill paths are incomplete or ambiguous")
        digest = hashlib.sha256()
        digest.update(self.name.encode("utf-8"))
        for path in sorted(self.directories, key=str):
            digest.update(b"D\0" + str(path).encode("utf-8") + b"\0")
        for item in sorted(self.files, key=lambda candidate: str(candidate.relative_path)):
            digest.update(b"F\0" + str(item.relative_path).encode("utf-8") + b"\0")
            digest.update(b"1" if item.executable else b"0")
            digest.update(bytes.fromhex(item.sha256))
        object.__setattr__(self, "sha256", digest.hexdigest())


@dataclass(frozen=True)
class CapturedOutputPath:
    """One descriptor-observed final actor output path."""

    path: PurePosixPath
    kind: CapturedOutputKind

    def __post_init__(self) -> None:
        _require_contained_relative_path(self.path, "captured output path")
        if self.kind not in ("file", "directory"):
            raise ValueError("captured output kind must be file or directory")


@dataclass(frozen=True)
class ActorInput:
    """One explicitly declared fixture file copied into an actor workspace."""

    source: Path
    destination: PurePosixPath
    prepared: PreparedFile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, Path) or not isinstance(
            self.destination, PurePosixPath
        ):
            raise ValueError("actor input requires Path source and PurePosixPath destination")
        _require_contained_relative_path(self.destination, "actor input destination")
        if self.prepared is not None and self.prepared.source != self.source:
            raise ValueError("prepared actor input source must match its declaration")


@dataclass(frozen=True)
class HarnessCapabilities:
    """Configured harness capabilities and actionable preflight state."""

    harness_name: str
    available: bool
    actor_model: str | None
    actor_reasoning_effort: str | None
    judge_model: str | None
    judge_reasoning_effort: str | None
    reports_token_usage: bool
    reports_successful_skill_reads: bool
    details: tuple[str, ...] = field(default_factory=tuple)
    failure: str | None = None


@dataclass(frozen=True)
class HarnessArtifactBinding:
    """Pinned runner-owned identities for one actor artifact destination."""

    attempt_identity: tuple[int, int, int]
    outputs_identity: tuple[int, int, int]
    repository_identity: tuple[int, int]

    def __post_init__(self) -> None:
        if (
            len(self.attempt_identity) != 3
            or len(self.outputs_identity) != 3
            or len(self.repository_identity) != 2
            or not all(
                type(value) is int
                for value in (
                    *self.attempt_identity,
                    *self.outputs_identity,
                    *self.repository_identity,
                )
            )
        ):
            raise ValueError("artifact binding requires exact filesystem identities")


@dataclass(frozen=True)
class HarnessExecutionBinding:
    """Fresh invocation and canonical request identity echoed by an adapter."""

    invocation_id: str
    run_id: str
    role: HarnessRole
    request_sha256: str
    binding_sha256: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", self.invocation_id):
            raise ValueError("execution binding invocation_id must be lowercase hex")
        if not self.run_id:
            raise ValueError("execution binding run_id must be non-empty")
        if self.role not in ("actor", "judge"):
            raise ValueError("execution binding role must be actor or judge")
        if not re.fullmatch(r"[0-9a-f]{64}", self.request_sha256):
            raise ValueError("execution binding request digest must be lowercase SHA-256")
        if self.binding_sha256 != _execution_binding_sha256(
            self.invocation_id,
            self.run_id,
            self.role,
            self.request_sha256,
        ):
            raise ValueError("execution binding digest does not match its fields")

    def to_dict(self) -> dict[str, str]:
        return {
            "invocation_id": self.invocation_id,
            "run_id": self.run_id,
            "role": self.role,
            "request_sha256": self.request_sha256,
            "binding_sha256": self.binding_sha256,
        }


@dataclass(frozen=True)
class HarnessRequest:
    """One actor or judge invocation requested from a selected harness."""

    role: HarnessRole
    run_variant: str
    prompt: str
    timeout_seconds: int
    skill_sources: tuple[Path | PreparedSkillSource, ...] = field(default_factory=tuple)
    expected_skill: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    shell_environment: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    actor_inputs: tuple[ActorInput, ...] = field(default_factory=tuple)
    fixture_root: Path | None = None
    fixture_initialization: Path | PreparedFile | None = None
    capture_outputs: bool = False
    artifact_binding: HarnessArtifactBinding | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    execution_binding: HarnessExecutionBinding | None = field(
        default=None,
        repr=False,
    )
    response_schema: Mapping[str, object] | PreparedResponseSchema | None = None

    def __post_init__(self) -> None:
        if self.role not in ("actor", "judge"):
            raise ValueError("role must be 'actor' or 'judge'")
        if not self.run_variant:
            raise ValueError("run_variant must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.role == "judge" and (self.skill_sources or self.expected_skill is not None):
            raise ValueError("judge requests cannot provision skill sources or an expected skill")
        if self.role == "judge" and self.shell_environment:
            raise ValueError("judge requests cannot receive actor shell environment")
        if self.role == "judge" and self.actor_inputs:
            raise ValueError("judge requests cannot receive actor input files")
        if self.role == "judge" and (
            self.fixture_root is not None or self.fixture_initialization is not None
        ):
            raise ValueError("judge requests cannot receive actor fixture provisioning")
        if type(self.capture_outputs) is not bool:
            raise ValueError("capture_outputs must be a boolean")
        if self.role == "judge" and self.capture_outputs:
            raise ValueError("judge requests cannot capture actor outputs")
        if self.role == "judge" and self.artifact_binding is not None:
            raise ValueError("judge requests cannot receive actor artifact bindings")
        if self.artifact_binding is not None and not self.capture_outputs:
            raise ValueError("actor artifact bindings require output capture")
        if (
            self.execution_binding is not None
            and self.execution_binding.role != self.role
        ):
            raise ValueError("request execution binding role must match the request")
        if self.role == "actor" and self.response_schema is not None:
            raise ValueError("actor requests cannot provide a judge response schema")
        if self.response_schema is not None and not isinstance(
            self.response_schema,
            (Mapping, PreparedResponseSchema),
        ):
            raise ValueError("response_schema must be a mapping")
        if not all(
            isinstance(source, (Path, PreparedSkillSource))
            for source in self.skill_sources
        ):
            raise ValueError("skill sources must be paths or prepared skill material")
        names: set[str] = set()
        for item in self.shell_environment:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item[0])
                or "\x00" in item[1]
                or item[0] in names
                or item[0] in CASE_OWNED_ENVIRONMENT_NAMES
            ):
                raise ValueError("shell environment must contain unique safe string pairs")
            names.add(item[0])
        destinations = [item.destination for item in self.actor_inputs]
        if len(destinations) != len(set(destinations)):
            raise ValueError("actor input destinations must be unique")
        has_fixture_material = bool(self.actor_inputs) or self.fixture_initialization is not None
        if has_fixture_material and self.fixture_root is None:
            raise ValueError("actor fixture material requires an exact case fixture root")
        if self.fixture_root is not None and not isinstance(self.fixture_root, Path):
            raise ValueError("fixture root must be a Path")
        if self.fixture_root is not None and not has_fixture_material:
            raise ValueError("fixture root requires actor fixture material")


@dataclass(frozen=True)
class HarnessExecution:
    """Normalized result; model fields are exact bound-request configuration."""

    response: str
    trace: tuple[Mapping[str, object], ...]
    duration_ms: int
    total_tokens: int | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    token_source: str
    successful_skill_reads: tuple[Path, ...]
    exit_code: int | None
    failure: str | None
    model: str | None
    reasoning_effort: str | None
    timed_out: bool
    expected_skill_path: Path | None = None
    captured_output_paths: tuple[CapturedOutputPath, ...] = field(default_factory=tuple)
    execution_binding: HarnessExecutionBinding | None = None


def validated_actor_skill_read_lifecycle(
    trace: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Return skill-read paths derived from one exact successful actor lifecycle."""
    state = "awaiting_thread"
    active_commands: dict[str, str] = {}
    active_tools: dict[str, str] = {}
    active_messages: set[str] = set()
    completed_commands: set[str] = set()
    completed_tools: set[str] = set()
    completed_messages: set[str] = set()
    eligible_read_command: str | None = None
    skill_reads: list[str] = []

    for event in trace:
        if not isinstance(event, Mapping):
            raise ValueError("actor lifecycle contains a non-object event")
        event_type = event.get("event")
        if state == "terminal":
            if event_type == "actor_output":
                continue
            raise ValueError("actor lifecycle contains unknown post-turn evidence")

        if event_type == "harness_thread_started":
            if state != "awaiting_thread":
                raise ValueError("actor thread start is missing, repeated, or out of order")
            state = "awaiting_turn"
            eligible_read_command = None
            continue
        if event_type == "harness_turn_started":
            if state != "awaiting_turn":
                raise ValueError("actor turn start is missing, repeated, or out of order")
            state = "in_turn"
            eligible_read_command = None
            continue
        if event_type == "harness_turn_completed":
            if (
                state != "in_turn"
                or active_commands
                or active_tools
                or active_messages
            ):
                raise ValueError(
                    "actor turn completion is out of order or has active items"
                )
            state = "terminal"
            eligible_read_command = None
            continue
        if state != "in_turn":
            raise ValueError("actor event appears outside the active turn")
        if event_type == "harness_failure":
            raise ValueError("actor lifecycle contains a harness failure")

        if event_type == "command_started":
            command_id = event.get("command_id")
            command = event.get("command")
            if (
                not isinstance(command_id, str)
                or not command_id
                or not isinstance(command, str)
                or not command
                or command_id in active_commands
                or command_id in active_tools
                or command_id in active_messages
                or command_id in completed_commands
                or command_id in completed_tools
                or command_id in completed_messages
            ):
                raise ValueError("actor command start is malformed or duplicated")
            active_commands[command_id] = command
            eligible_read_command = None
            continue

        if event_type == "command_completed":
            command_id = event.get("command_id")
            command = event.get("command")
            exit_code = event.get("exit_code")
            status = event.get("status")
            if (
                not isinstance(command_id, str)
                or not command_id
                or not isinstance(command, str)
                or not command
                or type(exit_code) is not int
                or status not in ("completed", "failed")
                or active_commands.get(command_id) != command
            ):
                raise ValueError(
                    "actor command completion is malformed or unmatched"
                )
            del active_commands[command_id]
            completed_commands.add(command_id)
            eligible_read_command = (
                command_id
                if (
                    exit_code == 0
                    and status == "completed"
                    and command in _TRUSTED_SKILL_READ_COMMANDS
                )
                else None
            )
            continue

        if event_type == "skill_read":
            command_id = event.get("command_id")
            path = event.get("path")
            if (
                not isinstance(command_id, str)
                or command_id != eligible_read_command
                or not isinstance(path, str)
                or not path
            ):
                raise ValueError(
                    "actor skill read is not bound to a successful trusted command"
                )
            skill_reads.append(path)
            eligible_read_command = None
            continue

        if event_type == "tool_started":
            tool_id = event.get("tool_id")
            tool_type = event.get("tool_type")
            if (
                not isinstance(tool_id, str)
                or not tool_id
                or not isinstance(tool_type, str)
                or re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", tool_type) is None
                or tool_id in active_commands
                or tool_id in active_tools
                or tool_id in active_messages
                or tool_id in completed_commands
                or tool_id in completed_tools
                or tool_id in completed_messages
            ):
                raise ValueError("actor tool start is malformed or duplicated")
            active_tools[tool_id] = tool_type
            eligible_read_command = None
            continue

        if event_type == "tool_completed":
            tool_id = event.get("tool_id")
            tool_type = event.get("tool_type")
            if (
                not isinstance(tool_id, str)
                or not tool_id
                or not isinstance(tool_type, str)
                or active_tools.get(tool_id) != tool_type
            ):
                raise ValueError("actor tool completion is malformed or unmatched")
            del active_tools[tool_id]
            completed_tools.add(tool_id)
            eligible_read_command = None
            continue

        if event_type == "agent_message_started":
            message_id = event.get("message_id")
            if (
                not isinstance(message_id, str)
                or not message_id
                or message_id in active_commands
                or message_id in active_tools
                or message_id in active_messages
                or message_id in completed_commands
                or message_id in completed_tools
                or message_id in completed_messages
            ):
                raise ValueError(
                    "actor message start is malformed or duplicated"
                )
            active_messages.add(message_id)
            eligible_read_command = None
            continue

        if event_type == "agent_message_completed":
            message_id = event.get("message_id")
            if message_id is None:
                if active_messages:
                    raise ValueError(
                        "actor message completion is missing its active item id"
                    )
            elif (
                not isinstance(message_id, str)
                or not message_id
                or message_id in completed_messages
                or message_id in active_commands
                or message_id in active_tools
            ):
                raise ValueError(
                    "actor message completion is malformed or duplicated"
                )
            elif message_id in active_messages:
                active_messages.remove(message_id)
                completed_messages.add(message_id)
            else:
                completed_messages.add(message_id)
            eligible_read_command = None
            continue

        raise ValueError("actor lifecycle contains an unknown in-turn event")

    if (
        state != "terminal"
        or active_commands
        or active_tools
        or active_messages
    ):
        raise ValueError("actor lifecycle is incomplete")
    return tuple(skill_reads)


def bind_harness_request(
    request: HarnessRequest,
    *,
    invocation_id: str,
    run_id: str,
) -> HarnessRequest:
    """Bind one exact request to a fresh evaluation invocation and logical run."""
    if request.execution_binding is not None:
        raise ValueError("harness request is already execution-bound")
    if isinstance(request.response_schema, Mapping):
        request = replace(
            request,
            response_schema=prepare_response_schema(request.response_schema),
        )
    request_sha256 = hashlib.sha256(
        _canonical_harness_request_bytes(request)
    ).hexdigest()
    return replace(
        request,
        execution_binding=HarnessExecutionBinding(
            invocation_id=invocation_id,
            run_id=run_id,
            role=request.role,
            request_sha256=request_sha256,
            binding_sha256=_execution_binding_sha256(
                invocation_id,
                run_id,
                request.role,
                request_sha256,
            ),
        ),
    )


def prepare_response_schema(
    response_schema: Mapping[str, object],
) -> PreparedResponseSchema:
    """Detach and canonically serialize one caller-owned response schema once."""
    materialized = _materialize_bounded_response_schema(response_schema)
    try:
        serialized = json.dumps(
            materialized,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
    except (
        TypeError,
        UnicodeError,
        ValueError,
        OverflowError,
        RecursionError,
        MemoryError,
        SystemError,
    ) as error:
        raise ValueError("response schema cannot be serialized safely") from error
    if len(serialized) > MAX_JSON_SCHEMA_BYTES:
        raise ValueError("response schema exceeds the 256 KiB byte limit")
    return PreparedResponseSchema(serialized)


def _materialize_bounded_response_schema(
    response_schema: Mapping[str, object],
) -> dict[str, object]:
    nodes = 0

    def materialize(value: object, depth: int) -> object:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_SCHEMA_NODES or depth > MAX_JSON_SCHEMA_DEPTH:
            raise ValueError("response schema exceeds structural limits")
        if isinstance(value, Mapping):
            expected_items = len(value)
            if expected_items > MAX_JSON_SCHEMA_NODES - nodes:
                raise ValueError("response schema exceeds structural limits")
            copied: dict[str, object] = {}
            observed_items = 0
            for key, nested in value.items():
                observed_items += 1
                if (
                    observed_items > expected_items
                    or not isinstance(key, str)
                    or key in copied
                ):
                    raise ValueError("response schema object is unstable")
                copied[key] = materialize(nested, depth + 1)
            if observed_items != expected_items or len(value) != expected_items:
                raise ValueError("response schema object changed while preparing")
            return copied
        if isinstance(value, (list, tuple)):
            expected_items = len(value)
            if expected_items > MAX_JSON_SCHEMA_NODES - nodes:
                raise ValueError("response schema exceeds structural limits")
            copied_items = [
                materialize(nested, depth + 1)
                for nested in value
            ]
            if len(copied_items) != expected_items or len(value) != expected_items:
                raise ValueError("response schema array changed while preparing")
            return copied_items
        if isinstance(value, str) or value is None or isinstance(value, bool):
            return value
        if isinstance(value, int):
            if value.bit_length() > MAX_JSON_SCHEMA_BYTES * 4:
                raise ValueError("response schema integer exceeds the byte limit")
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("response schema contains a non-finite number")
            return value
        raise TypeError("response schema must contain only JSON values")

    materialized = materialize(response_schema, 1)
    if not isinstance(materialized, dict):
        raise TypeError("response schema must be a JSON object")
    return materialized


def execution_binding_matches_request(
    execution: HarnessExecution,
    request: HarnessRequest,
) -> bool:
    """Return whether an adapter echoed the exact runner-created binding."""
    return (
        harness_request_matches_execution_binding(request)
        and execution.execution_binding == request.execution_binding
    )


def harness_request_matches_execution_binding(request: HarnessRequest) -> bool:
    """Return whether the bound digest still describes the exact request."""
    binding = request.execution_binding
    if binding is None or binding.role != request.role:
        return False
    try:
        request_sha256 = hashlib.sha256(
            _canonical_harness_request_bytes(request)
        ).hexdigest()
    except (
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        MemoryError,
        SystemError,
    ):
        return False
    return request_sha256 == binding.request_sha256


def execution_binding_from_document(
    document: Mapping[str, object],
) -> HarnessExecutionBinding:
    """Parse and self-verify one persisted execution binding."""
    try:
        return HarnessExecutionBinding(
            invocation_id=document["invocation_id"],  # type: ignore[arg-type]
            run_id=document["run_id"],  # type: ignore[arg-type]
            role=document["role"],  # type: ignore[arg-type]
            request_sha256=document["request_sha256"],  # type: ignore[arg-type]
            binding_sha256=document["binding_sha256"],  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("persisted execution binding is invalid") from error


def _execution_binding_sha256(
    invocation_id: str,
    run_id: str,
    role: HarnessRole,
    request_sha256: str,
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "invocation_id": invocation_id,
                "request_sha256": request_sha256,
                "role": role,
                "run_id": run_id,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _canonical_harness_request_bytes(request: HarnessRequest) -> bytes:
    def skill_source_document(
        source: Path | PreparedSkillSource,
    ) -> dict[str, object]:
        if isinstance(source, PreparedSkillSource):
            return {
                "kind": "prepared",
                "name": source.name,
                "sha256": source.sha256,
                "source_root": str(source.source_root),
            }
        return {"kind": "path", "path": str(source)}

    fixture_initialization: dict[str, object] | None
    if isinstance(request.fixture_initialization, PreparedFile):
        fixture_initialization = {
            "kind": "prepared",
            "source": str(request.fixture_initialization.source),
            "sha256": request.fixture_initialization.sha256,
            "executable": request.fixture_initialization.executable,
        }
    elif isinstance(request.fixture_initialization, Path):
        fixture_initialization = {
            "kind": "path",
            "path": str(request.fixture_initialization),
        }
    else:
        fixture_initialization = None
    artifact_binding = (
        {
            "attempt_identity": list(request.artifact_binding.attempt_identity),
            "outputs_identity": list(request.artifact_binding.outputs_identity),
            "repository_identity": list(
                request.artifact_binding.repository_identity
            ),
        }
        if request.artifact_binding is not None
        else None
    )
    document = {
        "role": request.role,
        "run_variant": request.run_variant,
        "prompt": request.prompt,
        "timeout_seconds": request.timeout_seconds,
        "skill_sources": [
            skill_source_document(source) for source in request.skill_sources
        ],
        "expected_skill": request.expected_skill,
        "model": request.model,
        "reasoning_effort": request.reasoning_effort,
        "shell_environment": [list(item) for item in request.shell_environment],
        "actor_inputs": [
            {
                "source": str(actor_input.source),
                "destination": actor_input.destination.as_posix(),
                "prepared_sha256": (
                    actor_input.prepared.sha256
                    if actor_input.prepared is not None
                    else None
                ),
                "prepared_executable": (
                    actor_input.prepared.executable
                    if actor_input.prepared is not None
                    else None
                ),
            }
            for actor_input in request.actor_inputs
        ],
        "fixture_root": (
            str(request.fixture_root)
            if request.fixture_root is not None
            else None
        ),
        "fixture_initialization": fixture_initialization,
        "capture_outputs": request.capture_outputs,
        "artifact_binding": artifact_binding,
        "response_schema": (
            {
                "kind": "prepared",
                "sha256": request.response_schema.sha256,
                "bytes": len(request.response_schema.content),
            }
            if isinstance(request.response_schema, PreparedResponseSchema)
            else request.response_schema
        ),
    }
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


@runtime_checkable
class HarnessAdapter(Protocol):
    """Small boundary shared by behavior and trigger orchestration."""

    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        """Report configured capabilities or an actionable environmental failure."""

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        """Execute one request and return normalized observable evidence."""
