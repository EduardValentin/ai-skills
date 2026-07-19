"""Harness-neutral contracts for isolated evaluation execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable


HarnessRole = Literal["actor", "judge"]


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

    def __post_init__(self) -> None:
        if self.role not in ("actor", "judge"):
            raise ValueError("role must be 'actor' or 'judge'")
        if not self.run_variant:
            raise ValueError("run_variant must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.role == "judge" and (self.skill_sources or self.expected_skill is not None):
            raise ValueError("judge requests cannot provision skill sources or an expected skill")


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


@runtime_checkable
class HarnessAdapter(Protocol):
    """Small boundary shared by behavior and trigger orchestration."""

    def preflight(self) -> HarnessCapabilities:
        """Report configured capabilities or an actionable environmental failure."""

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        """Execute one request and return normalized observable evidence."""
