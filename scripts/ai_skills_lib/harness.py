"""Harness-neutral contracts for isolated evaluation execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Literal, Protocol, runtime_checkable

from scripts.ai_skills_lib.runtime_environment import CASE_OWNED_ENVIRONMENT_NAMES


HarnessRole = Literal["actor", "judge"]
CapturedOutputKind = Literal["file", "directory"]


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
    response_schema: Mapping[str, object] | None = None

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
        if self.role == "actor" and self.response_schema is not None:
            raise ValueError("actor requests cannot provide a judge response schema")
        if self.response_schema is not None and not isinstance(
            self.response_schema, Mapping
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
    """Normalized observable result from one harness invocation."""

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


@runtime_checkable
class HarnessAdapter(Protocol):
    """Small boundary shared by behavior and trigger orchestration."""

    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        """Report configured capabilities or an actionable environmental failure."""

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        """Execute one request and return normalized observable evidence."""
