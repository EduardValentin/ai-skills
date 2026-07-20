"""Harness-neutral contracts for isolated evaluation execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
from typing import Literal, Protocol, runtime_checkable

from scripts.ai_skills_lib.runtime_environment import CASE_OWNED_ENVIRONMENT_NAMES


HarnessRole = Literal["actor", "judge"]


@dataclass(frozen=True)
class ActorInput:
    """One explicitly declared fixture file copied into an actor workspace."""

    source: Path
    destination: PurePosixPath

    def __post_init__(self) -> None:
        if not isinstance(self.source, Path) or not isinstance(
            self.destination, PurePosixPath
        ):
            raise ValueError("actor input requires Path source and PurePosixPath destination")
        if (
            self.destination.is_absolute()
            or not self.destination.parts
            or str(self.destination) in ("", ".")
            or ".." in self.destination.parts
        ):
            raise ValueError("actor input destination must be a contained relative path")


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
    skill_sources: tuple[Path, ...] = field(default_factory=tuple)
    expected_skill: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    shell_environment: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    actor_inputs: tuple[ActorInput, ...] = field(default_factory=tuple)
    fixture_root: Path | None = None
    fixture_initialization: Path | None = None

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


@runtime_checkable
class HarnessAdapter(Protocol):
    """Small boundary shared by behavior and trigger orchestration."""

    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        """Report configured capabilities or an actionable environmental failure."""

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        """Execute one request and return normalized observable evidence."""
