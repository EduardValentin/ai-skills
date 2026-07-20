"""Shared, runner-neutral mechanics for durable LLM-backed evaluation results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import ctypes
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from scripts.ai_skills_lib.authored_content import (
    JsonPreflightError,
    preflight_bounded_json_structure,
)
from scripts.ai_skills_lib.harness import (
    HarnessAdapter,
    HarnessExecution,
    HarnessRequest,
)


_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "ai-skills"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MAX_JUDGE_RESPONSE_BYTES = 256 * 1024
_MAX_JUDGE_EVIDENCE_CHARS = 4096
_MAX_JUDGE_EVIDENCE_REFS = 16
_MAX_JUDGE_ARTIFACT_NAME_CHARS = 512
_MAX_JUDGE_LOCATOR_CHARS = 1024
_MAX_DECLARED_ATTEMPTS = 1024
_MAX_RESULT_JSON_FILE_BYTES = 4 * 1024 * 1024
_MAX_RESULT_JSON_NODES = 100_000
_MAX_RESULT_JSON_DEPTH = 32
_MAX_RESULT_JSON_SCALAR_BYTES = 64 * 1024
_MAX_RESULT_JSON_NUMBER_CHARS = 128
_MAX_RESULT_FILE_BYTES = 16 * 1024 * 1024
_MAX_RESULT_TREE_BYTES = 256 * 1024 * 1024
_MAX_RESULT_TREE_ENTRIES = 100_000
_MAX_RESULT_TREE_DEPTH = 40
_MAX_RESULT_ANCESTOR_DEPTH = 256
_MAX_RESULT_ENTRIES_PER_ATTEMPT = 4096
_MAX_RESULT_ROOT_ENTRIES = 4
_MAX_OFFLINE_SCHEMA_BYTES = 1024 * 1024
_RESULT_READ_CHUNK_BYTES = 64 * 1024

_ROOT_RESULT_FILES = frozenset(
    {"invocation.json", "benchmark.json", "summary.md"}
)
_ATTEMPT_RESULT_FILES = frozenset(
    {
        "attempt.json",
        "timing.json",
        "grading.json",
        "manual_grading.json",
        "feedback.json",
        "transcript.md",
        "execution_trace.jsonl",
    }
)
_REQUIRED_ATTEMPT_RESULT_FILES = frozenset(
    {"attempt.json"}
)
class ResultArtifactError(RuntimeError):
    """Raised when preserved evaluation evidence cannot be trusted."""

    exit_code = 2


class JudgeExecutionError(ResultArtifactError):
    """Raised with complete normalized evidence from an untrusted judge execution."""

    def __init__(self, message: str, execution: HarnessExecution):
        super().__init__(message)
        self.execution = execution


class _JsonBoundaryError(ValueError):
    """Internal marker for sanitized strict-JSON boundary failures."""


@dataclass(frozen=True)
class _StableFileRead:
    content: bytes
    metadata: tuple[int, ...]


@dataclass(frozen=True)
class _StableContentIdentity:
    metadata: tuple[int, ...]
    digest: bytes


@dataclass(frozen=True)
class _ResultTreeSnapshot:
    files: Mapping[tuple[str, ...], tuple[int, ...]]
    directories: Mapping[tuple[str, ...], tuple[int, ...]]
    total_bytes: int


@dataclass
class _ResultTreeScanState:
    entries: int = 0
    total_bytes: int = 0


@dataclass(frozen=True)
class ResultWorkspace:
    """Invocation-owned durable result and human-summary paths."""

    root: Path
    attempts: Path
    invocation_manifest: Path
    benchmark: Path
    output_summary: Path
    repository_root: Path


@dataclass(frozen=True)
class AttemptPaths:
    """Canonical paths for one declared evaluation attempt."""

    root: Path
    manifest: Path
    response: Path
    transcript: Path
    execution_trace: Path
    timing: Path
    grading: Path
    manual_grading: Path
    feedback: Path


@dataclass(frozen=True)
class TimingRecord:
    """Schema-compatible observable timing and token usage for one run."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    harness: str
    model: str | None
    reasoning_effort: str | None
    started_at: str
    ended_at: str
    duration_ms: int
    total_tokens: int | None
    status: str
    exit_code: int | None
    token_details: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "ai-skills.eval.timing.v1",
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "case_id": self.case_id,
            "run_kind": self.run_kind,
            "harness": self.harness,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "total_tokens": self.total_tokens,
            "status": self.status,
            "exit_code": self.exit_code,
            "token_details": dict(self.token_details),
        }


@dataclass(frozen=True)
class AssertionResult:
    """One guide-compatible assertion or deterministic check result."""

    id: str
    kind: str
    text: str
    passed: bool
    checked_by: str
    evidence: str
    evidence_refs: tuple[Mapping[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "passed": self.passed,
            "checked_by": self.checked_by,
            "evidence": self.evidence,
            "evidence_refs": [dict(reference) for reference in self.evidence_refs],
        }


@dataclass(frozen=True)
class AssertionDefinition:
    """Caller-owned identity and text for one assertion sent to a judge."""

    id: str
    kind: str
    text: str


@dataclass(frozen=True)
class GraderRecord:
    """Identity of the human, model, or deterministic grader."""

    type: str
    model: str | None
    reasoning_effort: str | None
    prompt_version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "prompt_version": self.prompt_version,
        }


@dataclass(frozen=True)
class GradingSummary:
    """Counts derived from all assertion results in one grading record."""

    passed: int
    failed: int
    total: int
    pass_rate: float

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "pass_rate": self.pass_rate,
        }


@dataclass(frozen=True)
class AggregationMetadata:
    """Caller-provided generic variant and outcome contribution metadata."""

    group_id: str
    variant: str
    contributes_to_outcome: bool
    required_variants: tuple[str, ...]
    compare_to: str | None = None
    minimum_pass_rate: float | None = None
    configured_runs: int | None = None
    run_number: int | None = None

    def __post_init__(self) -> None:
        repeated_fields = (
            self.minimum_pass_rate,
            self.configured_runs,
            self.run_number,
        )
        if any(value is not None for value in repeated_fields) and any(
            value is None for value in repeated_fields
        ):
            raise ValueError(
                "threshold aggregation requires pass rate, configured runs, and run number"
            )
        if self.minimum_pass_rate is not None and not 0 < self.minimum_pass_rate <= 1:
            raise ValueError("minimum pass rate must be greater than zero and at most one")
        if self.configured_runs is not None and (
            self.configured_runs < 1
            or self.run_number is None
            or not 1 <= self.run_number <= self.configured_runs
        ):
            raise ValueError("aggregation run number must belong to the configured run set")

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "group_id": self.group_id,
            "variant": self.variant,
            "contributes_to_outcome": self.contributes_to_outcome,
            "required_variants": list(self.required_variants),
        }
        if self.compare_to is not None:
            value["compare_to"] = self.compare_to
        if self.minimum_pass_rate is not None:
            value["minimum_pass_rate"] = self.minimum_pass_rate
            value["configured_runs"] = self.configured_runs
            value["run_number"] = self.run_number
        return value


@dataclass(frozen=True)
class AttemptManifest:
    """Immutable caller-owned identity and aggregation policy for one attempt."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    aggregation: AggregationMetadata

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "ai-skills.eval.attempt.v1",
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "case_id": self.case_id,
            "run_kind": self.run_kind,
            "aggregation": self.aggregation.to_dict(),
        }


@dataclass(frozen=True)
class JudgeGradingContext:
    """Caller-owned grading identity, scope, and aggregation policy."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    prompt_version: str
    graded_at: str
    allowed_evidence_artifacts: tuple[str, ...]
    expected_assertions: tuple[AssertionDefinition, ...]
    aggregation: AggregationMetadata


@dataclass(frozen=True)
class GradingRecord:
    """Complete generated or manual grade for one preserved run."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    grade_source: str
    grader: GraderRecord
    graded_at: str
    assertion_results: tuple[AssertionResult, ...]
    summary: GradingSummary
    aggregation: AggregationMetadata
    measurements: Mapping[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": "ai-skills.eval.grading.v1",
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "case_id": self.case_id,
            "run_kind": self.run_kind,
            "grade_source": self.grade_source,
            "grader": self.grader.to_dict(),
            "graded_at": self.graded_at,
            "assertion_results": [result.to_dict() for result in self.assertion_results],
            "summary": self.summary.to_dict(),
            "aggregation": self.aggregation.to_dict(),
        }
        if self.measurements:
            document["measurements"] = dict(self.measurements)
        return document


@dataclass(frozen=True)
class JudgeInvocationResult:
    """A generated grade together with its preservable model execution evidence."""

    grading: GradingRecord
    execution: HarnessExecution


@dataclass(frozen=True)
class EvalRunRecord:
    """Human-readable and structured artifacts produced for one run."""

    response: str
    transcript: str
    execution_trace: tuple[Mapping[str, object], ...]
    timing: TimingRecord
    grading: GradingRecord


def default_results_root(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the external durable result root without creating it."""
    environment = os.environ if environ is None else environ
    xdg_state_home = environment.get("XDG_STATE_HOME")
    configured_state_home = Path(xdg_state_home) if xdg_state_home else None
    state_home = (
        configured_state_home
        if configured_state_home is not None and configured_state_home.is_absolute()
        else (home or Path.home()) / ".local/state"
    )
    return state_home / "ai-skills" / "results"


def resolve_external_result_path(
    path: Path,
    *,
    repository_root: Path | None = None,
) -> Path:
    repository = _REPOSITORY_ROOT if repository_root is None else repository_root
    try:
        resolved_repository = repository.resolve(strict=True)
        resolved_path = path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise ResultArtifactError("cannot resolve result path") from error
    if resolved_path == resolved_repository or resolved_path.is_relative_to(resolved_repository):
        raise ResultArtifactError(
            f"result path must be outside the repository: {resolved_path}"
        )
    return resolved_path


def create_result_workspace(
    command: str,
    *,
    results_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    now: datetime | None = None,
    repository_root: Path | None = None,
) -> ResultWorkspace:
    """Create one external invocation workspace."""
    if results_dir is None:
        created_at = now or datetime.now(timezone.utc)
        timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        command_slug = re.sub(r"[^a-z0-9]+", "-", command.lower()).strip("-") or "results"
        unique_suffix = uuid.uuid4().hex[:12]
        root = default_results_root(environ=environ, home=home) / (
            f"{timestamp}-{command_slug}-{unique_suffix}"
        )
    else:
        root = results_dir
    root = resolve_external_result_path(root, repository_root=repository_root)
    repository = _REPOSITORY_ROOT if repository_root is None else repository_root
    try:
        resolved_repository = repository.resolve(strict=True)
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise ResultArtifactError(f"result workspace already exists: {root}") from error
    except OSError as error:
        raise ResultArtifactError(f"cannot create result workspace {root}") from error
    attempts = root / "attempts"
    try:
        attempts.mkdir()
    except OSError as error:
        raise _retained_workspace_error(root) from error
    return ResultWorkspace(
        root=root,
        attempts=attempts,
        invocation_manifest=root / "invocation.json",
        benchmark=root / "benchmark.json",
        output_summary=root / "summary.md",
        repository_root=resolved_repository,
    )


def write_result_summary(workspace: ResultWorkspace, text: str) -> None:
    """Atomically persist the invocation's terminal human-readable status."""
    if not text.strip():
        raise ResultArtifactError("result summary must be non-empty")
    _write_text_atomic(
        workspace.output_summary,
        f"{text.rstrip()}\n",
        workspace.root,
        replace_existing=True,
    )


def declare_invocation(
    workspace: ResultWorkspace,
    command: str,
    manifests: Sequence[AttemptManifest],
) -> None:
    """Persist the exact expected attempt set before external execution."""
    if not command:
        raise ResultArtifactError("invocation command must be non-empty")
    if not manifests:
        raise ResultArtifactError("invocation must declare at least one attempt")
    if len(manifests) > _MAX_DECLARED_ATTEMPTS:
        raise ResultArtifactError("invocation exceeds the declared attempt limit")
    run_ids = [manifest.run_id for manifest in manifests]
    if len(run_ids) != len(set(run_ids)):
        raise ResultArtifactError("invocation attempt run identifiers must be unique")
    document = {
        "schema_version": "ai-skills.eval.invocation.v1",
        "command": command,
        "attempts": [manifest.to_dict() for manifest in manifests],
    }
    validate_result_document(document, "invocation.schema.json")
    _write_json_once(workspace.invocation_manifest, document, workspace.root)


def create_attempt_workspace(
    workspace: ResultWorkspace,
    manifest: AttemptManifest,
) -> AttemptPaths:
    """Declare one attempt durably before any external execution."""
    document = manifest.to_dict()
    validate_result_document(document, "attempt.schema.json")
    if manifest.aggregation.variant not in manifest.aggregation.required_variants:
        raise ResultArtifactError(
            "attempt aggregation variant must be one of its required variants"
        )
    declared_attempts = _read_declared_attempts(workspace.root)
    if declared_attempts.get(manifest.run_id) != document:
        raise ResultArtifactError(
            "attempt does not match the immutable invocation manifest"
        )
    if workspace.root.is_symlink() or workspace.attempts.is_symlink():
        raise ResultArtifactError("invocation attempts directory must not be a symlink")
    try:
        invocation_root = workspace.root.resolve(strict=True)
        attempts_root = workspace.attempts.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ResultArtifactError("cannot resolve invocation attempts directory") from error
    expected_attempts_root = invocation_root / "attempts"
    if attempts_root != expected_attempts_root or not attempts_root.is_dir():
        raise ResultArtifactError("invocation attempts directory is not owned by its workspace")
    resolve_external_result_path(
        attempts_root,
        repository_root=workspace.repository_root,
    )

    run_slug = re.sub(r"[^a-z0-9]+", "-", manifest.run_id.lower()).strip("-") or "attempt"
    directory_name = f"{run_slug}-{uuid.uuid4().hex[:12]}"
    root = attempts_root / directory_name
    attempts_descriptor: int | None = None
    attempt_descriptor: int | None = None
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        attempts_descriptor = os.open(attempts_root, directory_flags)
        os.mkdir(directory_name, dir_fd=attempts_descriptor)
        attempt_descriptor = os.open(
            directory_name,
            directory_flags,
            dir_fd=attempts_descriptor,
        )
        os.mkdir("outputs", dir_fd=attempt_descriptor)
    except FileExistsError as error:
        raise ResultArtifactError(f"attempt workspace already exists: {root}") from error
    except OSError as error:
        raise ResultArtifactError(f"cannot create attempt workspace {root}") from error
    finally:
        if attempt_descriptor is not None:
            os.close(attempt_descriptor)
        if attempts_descriptor is not None:
            os.close(attempts_descriptor)
    outputs = root / "outputs"
    paths = AttemptPaths(
        root=root,
        manifest=root / "attempt.json",
        response=outputs / "response.md",
        transcript=root / "transcript.md",
        execution_trace=root / "execution_trace.jsonl",
        timing=root / "timing.json",
        grading=root / "grading.json",
        manual_grading=root / "manual_grading.json",
        feedback=root / "feedback.json",
    )
    _write_json_once(paths.manifest, document, paths.root)
    return paths


def record_harness_timing(
    *,
    run_id: str,
    skill_name: str,
    case_id: str,
    run_kind: str,
    harness_name: str,
    started_at: datetime,
    ended_at: datetime,
    execution: HarnessExecution,
) -> TimingRecord:
    """Build required timing evidence directly from normalized harness execution."""
    status = (
        "timeout"
        if execution.timed_out
        else "failed"
        if (
            execution.failure
            or execution.exit_code != 0
            or execution.model is None
            or execution.reasoning_effort is None
        )
        else "completed"
    )
    return TimingRecord(
        run_id=run_id,
        skill_name=skill_name,
        case_id=case_id,
        run_kind=run_kind,
        harness=harness_name,
        model=execution.model,
        reasoning_effort=execution.reasoning_effort,
        started_at=_format_timestamp(started_at),
        ended_at=_format_timestamp(ended_at),
        duration_ms=execution.duration_ms,
        total_tokens=execution.total_tokens,
        status=status,
        exit_code=execution.exit_code,
        token_details={
            "input": execution.input_tokens,
            "output": execution.output_tokens,
            "cached": execution.cached_tokens,
            "source": execution.token_source,
        },
    )


def validate_result_document(document: Mapping[str, object], schema_name: str) -> None:
    """Validate one result document against a repository-owned offline schema."""
    schema_path = _SCHEMA_ROOT / schema_name
    try:
        schema_bytes = _read_stable_path_file(
            schema_path,
            maximum_bytes=_MAX_OFFLINE_SCHEMA_BYTES,
            label="offline result schema",
        ).content
        schema = _parse_bounded_json(
            schema_bytes,
            label="offline result schema",
            maximum_bytes=_MAX_OFFLINE_SCHEMA_BYTES,
        )
        if not isinstance(schema, dict):
            raise ResultArtifactError("offline result schema must contain a JSON object")
        _validate_bounded_json_structure(
            document,
            label=f"{schema_name} result",
        )
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    except ValidationError as error:
        keyword = str(error.validator)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", keyword):
            keyword = "validation"
        raise ResultArtifactError(
            f"invalid {schema_name} result at {_safe_validation_path(error.absolute_path)}: "
            f"{keyword}"
        ) from error
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
        ValueError,
    ) as error:
        raise ResultArtifactError(
            f"cannot load or apply offline schema {schema_name}"
        ) from error


def write_eval_run_artifacts(paths: AttemptPaths, record: EvalRunRecord) -> None:
    """Write one complete generated run without touching manual review artifacts."""
    _require_declared_attempt_paths(paths)
    timing = record.timing.to_dict()
    grading = record.grading.to_dict()
    validate_result_document(timing, "timing.schema.json")
    validate_result_document(grading, "grading.schema.json")

    trace_text = _serialize_execution_trace(record.execution_trace)
    _write_json_once(paths.timing, timing, paths.root)
    _write_text_once(paths.response, record.response, paths.root)
    _write_text_once(paths.transcript, record.transcript, paths.root)
    _write_text_once(paths.execution_trace, trace_text, paths.root)
    _write_json_once(paths.grading, grading, paths.root)


def write_incomplete_attempt_artifacts(
    paths: AttemptPaths,
    *,
    response: str | None,
    transcript: str | None,
    execution_trace: Sequence[Mapping[str, object]],
    timing: TimingRecord,
) -> None:
    """Preserve available failed-attempt evidence without inventing a grade."""
    _require_declared_attempt_paths(paths)
    timing_document = timing.to_dict()
    validate_result_document(timing_document, "timing.schema.json")
    _write_json_once(paths.timing, timing_document, paths.root)
    if response is not None:
        _write_text_once(paths.response, response, paths.root)
    if transcript is not None:
        _write_text_once(paths.transcript, transcript, paths.root)
    trace_text = _serialize_execution_trace(execution_trace)
    _write_text_once(paths.execution_trace, trace_text, paths.root)


def parse_judge_response(
    response: str,
    context: JudgeGradingContext,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> GradingRecord:
    """Parse judge verdicts while retaining caller-owned scope and policy."""
    document = _parse_bounded_json(
        response,
        label="invalid judge response",
        maximum_bytes=_MAX_JUDGE_RESPONSE_BYTES,
    )
    if not isinstance(document, dict):
        raise ResultArtifactError("invalid judge response: expected a JSON object")
    if set(document) != {"assertion_results"}:
        raise ResultArtifactError(
            "invalid judge response: expected only assertion_results"
        )
    raw_results = document["assertion_results"]
    if not isinstance(raw_results, list):
        raise ResultArtifactError(
            "invalid judge response: assertion_results must be an array"
        )
    expected_ids = [definition.id for definition in context.expected_assertions]
    actual_ids = [
        result.get("id") if isinstance(result, dict) else None
        for result in raw_results
    ]
    if actual_ids != expected_ids:
        raise ResultArtifactError(
            "invalid judge response: did not return every expected assertion exactly once"
        )

    verdicts: list[tuple[bool, str, tuple[Mapping[str, str], ...]]] = []
    expected_result_fields = {"id", "passed", "evidence", "evidence_refs"}
    expected_reference_fields = {"artifact", "locator"}
    for result in raw_results:
        if not isinstance(result, dict) or set(result) != expected_result_fields:
            raise ResultArtifactError(
                "invalid judge response: assertion result fields are not allowed"
            )
        if type(result["passed"]) is not bool:
            raise ResultArtifactError(
                "invalid judge response: passed must be a boolean"
            )
        if (
            not isinstance(result["evidence"], str)
            or not result["evidence"]
            or len(result["evidence"]) > _MAX_JUDGE_EVIDENCE_CHARS
        ):
            raise ResultArtifactError(
                "invalid judge response: evidence must be a bounded non-empty string"
            )
        raw_references = result["evidence_refs"]
        if (
            not isinstance(raw_references, list)
            or not raw_references
            or len(raw_references) > _MAX_JUDGE_EVIDENCE_REFS
        ):
            raise ResultArtifactError(
                "invalid judge response: evidence_refs must contain bounded evidence"
            )
        references: list[Mapping[str, str]] = []
        for reference in raw_references:
            if (
                not isinstance(reference, dict)
                or set(reference) != expected_reference_fields
                or any(
                    not isinstance(reference[field], str) or not reference[field]
                    for field in expected_reference_fields
                )
                or len(reference["artifact"]) > _MAX_JUDGE_ARTIFACT_NAME_CHARS
                or len(reference["locator"]) > _MAX_JUDGE_LOCATOR_CHARS
            ):
                raise ResultArtifactError(
                    "invalid judge response: evidence reference is incomplete"
                )
            if reference["artifact"] not in context.allowed_evidence_artifacts:
                raise ResultArtifactError(
                    "invalid judge response: evidence artifact is not allowed"
                )
            references.append(reference)
        verdicts.append((result["passed"], result["evidence"], tuple(references)))

    assertion_results = tuple(
        AssertionResult(
            id=definition.id,
            kind=definition.kind,
            text=definition.text,
            passed=verdict[0],
            checked_by="judge",
            evidence=verdict[1],
            evidence_refs=verdict[2],
        )
        for definition, verdict in zip(
            context.expected_assertions, verdicts, strict=True
        )
    )
    grading = GradingRecord(
        run_id=context.run_id,
        skill_name=context.skill_name,
        case_id=context.case_id,
        run_kind=context.run_kind,
        grade_source="judge",
        grader=GraderRecord(
            type="llm",
            model=model,
            reasoning_effort=reasoning_effort,
            prompt_version=context.prompt_version,
        ),
        graded_at=context.graded_at,
        assertion_results=assertion_results,
        summary=_summarize_assertions(assertion_results),
        aggregation=context.aggregation,
    )
    validate_result_document(grading.to_dict(), "grading.schema.json")
    return grading


def invoke_judge(
    adapter: HarnessAdapter,
    request: HarnessRequest,
    artifact_dir: Path,
    context: JudgeGradingContext,
) -> JudgeInvocationResult:
    """Invoke one judge request exactly once and parse its trustworthy response."""
    if request.role != "judge":
        raise ValueError("judge invocation requires a request with role='judge'")
    execution = adapter.execute(request, artifact_dir)
    if execution.timed_out:
        raise JudgeExecutionError("judge execution timed out", execution)
    if execution.failure:
        raise JudgeExecutionError(
            f"judge execution failed: {execution.failure}", execution
        )
    if execution.exit_code != 0:
        raise JudgeExecutionError(
            f"judge execution failed with exit code {execution.exit_code}", execution
        )
    if execution.model is None or execution.reasoning_effort is None:
        raise JudgeExecutionError(
            "judge execution did not report model and reasoning metadata",
            execution,
        )
    try:
        grading = parse_judge_response(
            execution.response,
            context,
            model=execution.model,
            reasoning_effort=execution.reasoning_effort,
        )
    except ResultArtifactError as error:
        raise JudgeExecutionError(str(error), execution) from error

    return JudgeInvocationResult(
        grading=grading,
        execution=execution,
    )


def combine_grading_results(
    judge_grading: GradingRecord,
    deterministic_results: Sequence[AssertionResult],
) -> GradingRecord:
    """Prepend deterministic checks and recompute one complete generated grade."""
    assertion_results = (*deterministic_results, *judge_grading.assertion_results)
    identifiers = [result.id for result in assertion_results]
    if len(identifiers) != len(set(identifiers)):
        raise ResultArtifactError("grading assertion result identifiers must be unique")
    combined = replace(
        judge_grading,
        assertion_results=assertion_results,
        summary=_summarize_assertions(assertion_results),
    )
    validate_result_document(combined.to_dict(), "grading.schema.json")
    return combined


def aggregate_results(
    results_dir: Path,
    grade_source: str,
    *,
    repository_root: Path | None = None,
    terminal_decision: str | None = None,
) -> dict[str, object]:
    """Aggregate only complete attempts anchored by immutable declarations."""
    if grade_source not in ("judge", "manual", "both"):
        raise ResultArtifactError(
            "grade_source must be one of 'judge', 'manual', or 'both'"
        )
    if terminal_decision not in (None, "pass", "expectations failed"):
        raise ResultArtifactError(
            "aggregate terminal decision must be 'pass' or 'expectations failed'"
        )
    repository_identity = _resolved_repository_identity(repository_root)
    root = resolve_external_result_path(
        results_dir,
        repository_root=repository_root,
    )
    root_descriptor, root_metadata = _open_result_root(root, results_dir)
    try:
        _verify_result_root_outside_repository(
            root_descriptor,
            repository_identity,
        )
        invocation_read = _read_required_invocation(root_descriptor, root)
        invocation = _parse_result_document(
            invocation_read.content,
            root / "invocation.json",
            "invocation.schema.json",
        )
        declared_attempts = _declared_attempts(invocation)
        snapshot = _snapshot_result_tree(
            root_descriptor,
            root,
            declared_attempt_count=len(declared_attempts),
        )
        if snapshot.files.get(("invocation.json",)) != invocation_read.metadata:
            raise ResultArtifactError(
                "result invocation changed during bounded inventory"
            )
        attempt_directories = _validate_result_tree(snapshot, results_dir)

        requested_sources = (
            ("judge", "manual") if grade_source == "both" else (grade_source,)
        )
        preserved: dict[
            str,
            list[tuple[dict[str, object], dict[str, object]]],
        ] = {source: [] for source in requested_sources}
        run_ids: set[str] = set()
        for directory_name in attempt_directories:
            attempt_parts = ("attempts", directory_name)
            manifest_parts = (*attempt_parts, "attempt.json")
            manifest_path = root.joinpath(*manifest_parts)
            manifest = _read_snapshotted_result_document(
                root_descriptor,
                snapshot,
                manifest_parts,
                manifest_path,
                "attempt.schema.json",
            )
            run_id = manifest["run_id"]
            if run_id in run_ids:
                raise ResultArtifactError(
                    f"duplicate run_id in attempt manifests: {run_id}"
                )
            run_ids.add(run_id)
            if declared_attempts.get(run_id) != manifest:
                raise ResultArtifactError(
                    f"attempt does not match the immutable invocation manifest: {run_id}"
                )
            aggregation = manifest["aggregation"]
            if aggregation["variant"] not in aggregation["required_variants"]:
                raise ResultArtifactError(
                    f"unexpected variant in attempt manifest: {aggregation['variant']}"
                )

            timing_parts = (*attempt_parts, "timing.json")
            timing_path = root.joinpath(*timing_parts)
            timing = _read_snapshotted_result_document(
                root_descriptor,
                snapshot,
                timing_parts,
                timing_path,
                "timing.schema.json",
            )
            generated_parts = (*attempt_parts, "grading.json")
            generated_path = root.joinpath(*generated_parts)
            generated = _read_snapshotted_result_document(
                root_descriptor,
                snapshot,
                generated_parts,
                generated_path,
                "grading.schema.json",
            )
            _validate_grading_semantics(generated, expected_source="judge")
            _validate_artifact_matches_manifest(timing, manifest, timing_path)
            _validate_artifact_matches_manifest(generated, manifest, generated_path)
            if timing["status"] != "completed":
                raise ResultArtifactError(
                    f"attempt is not trustworthy: timing status is {timing['status']}"
                )
            _validate_completed_timing(timing, timing_path)

            if "judge" in preserved:
                preserved["judge"].append((generated, timing))
            if "manual" in preserved:
                manual_parts = (*attempt_parts, "manual_grading.json")
                manual_path = root.joinpath(*manual_parts)
                manual = _read_snapshotted_result_document(
                    root_descriptor,
                    snapshot,
                    manual_parts,
                    manual_path,
                    "grading.schema.json",
                )
                _validate_grading_semantics(manual, expected_source="manual")
                _validate_artifact_matches_manifest(manual, manifest, manual_path)
                _validate_complete_manual_override(generated, manual, manual_path)
                preserved["manual"].append((manual, timing))

        if run_ids != set(declared_attempts):
            raise ResultArtifactError(
                "attempt set does not match the immutable invocation manifest"
            )

        benchmark: dict[str, object] = {
            "schema_version": "ai-skills.eval.benchmark.v1",
            "generated_at": _format_timestamp(datetime.now(timezone.utc)),
            "grade_source": grade_source,
            "source_summaries": {
                source: _aggregate_source(records)
                for source, records in preserved.items()
            },
        }
        validate_result_document(benchmark, "benchmark.schema.json")
        resolved_terminal_decision = terminal_decision or (
            "expectations failed" if benchmark_exit_code(benchmark) else "pass"
        )
        final_snapshot = _snapshot_result_tree(
            root_descriptor,
            root,
            declared_attempt_count=len(declared_attempts),
        )
        if final_snapshot != snapshot:
            raise ResultArtifactError(
                "result tree changed during bounded aggregation"
            )
        _verify_open_result_root(root_descriptor, root, root_metadata)
        _verify_result_root_outside_repository(
            root_descriptor,
            repository_identity,
        )
        _write_aggregate_result_artifacts(
            root_descriptor,
            root,
            root_metadata,
            repository_identity,
            snapshot,
            benchmark,
            terminal_decision=resolved_terminal_decision,
            declared_attempt_count=len(declared_attempts),
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result aggregation exceeded bounded resource limits"
        ) from error
    finally:
        try:
            os.close(root_descriptor)
        except OSError as error:
            raise ResultArtifactError(
                "result aggregation could not release its directory handle"
            ) from error
    return benchmark


def benchmark_exit_code(benchmark: Mapping[str, object]) -> int:
    """Return 1 only when a caller-designated contributing result failed."""
    validate_result_document(benchmark, "benchmark.schema.json")
    source_summaries = benchmark["source_summaries"]
    effective_sources = (
        (source_summaries["manual"],)
        if benchmark["grade_source"] == "both"
        else tuple(source_summaries.values())
    )
    return 1 if any(
        source_summary["summary"]["failed_cases"]
        for source_summary in effective_sources
    ) else 0


def format_benchmark_summary(benchmark: Mapping[str, object]) -> str:
    """Render aggregate outcomes and prominently label non-positive deltas."""
    validate_result_document(benchmark, "benchmark.schema.json")
    lines = [f"Aggregate grade source: {benchmark['grade_source']}"]
    for source, source_summary in benchmark["source_summaries"].items():
        summary = source_summary["summary"]
        lines.append(
            f"{source}: {summary['passed_cases']}/{summary['total_cases']} contributing cases passed "
            f"({summary['pass_rate']:.4f})"
        )
        for group in source_summary["groups"]:
            variants = ", ".join(
                f"{name}={details['pass_rate']:.4f}"
                for name, details in group["variants"].items()
            )
            lines.append(f"  {group['group_id']}: {variants}")
            for comparison in group["comparisons"]:
                label = " INVESTIGATE: zero or negative delta" if comparison[
                    "investigation_required"
                ] else ""
                lines.append(
                    f"    {comparison['variant']} - {comparison['baseline_variant']} "
                    f"delta={comparison['pass_rate_delta']:+.4f}{label}"
                )
        for skill in source_summary["skill_summaries"]:
            measurements = ", ".join(
                f"{name}={details['mean']:.4f} (n={details['count']})"
                for name, details in skill["measurements"].items()
            )
            if measurements:
                lines.append(f"  {skill['skill_name']} measurements: {measurements}")
    return "\n".join(lines)


def _aggregate_source(
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> dict[str, object]:
    grouped: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = defaultdict(list)
    for grading, timing in records:
        grouped[grading["aggregation"]["group_id"]].append((grading, timing))

    groups = [_aggregate_group(group_id, grouped[group_id]) for group_id in sorted(grouped)]
    contributing_outcomes = [
        outcome
        for group_id in sorted(grouped)
        for outcome in _contributing_outcomes(group_id, grouped[group_id])
    ]
    if not contributing_outcomes:
        raise ResultArtifactError("grading source has no contributing outcomes")
    passed_cases = sum(contributing_outcomes)
    total_cases = len(contributing_outcomes)
    return {
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": total_cases - passed_cases,
            "pass_rate": passed_cases / total_cases if total_cases else 0.0,
        },
        "groups": groups,
        "skill_summaries": _aggregate_skill_summaries(grouped),
    }


def _aggregate_group(
    group_id: str,
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> dict[str, object]:
    skill_names = {grading["skill_name"] for grading, _ in records}
    case_ids = {grading["case_id"] for grading, _ in records}
    required_variant_sets = {
        tuple(sorted(grading["aggregation"]["required_variants"]))
        for grading, _ in records
    }
    if len(skill_names) != 1 or len(case_ids) != 1:
        raise ResultArtifactError(f"aggregation group {group_id!r} mixes skills or cases")
    if len(required_variant_sets) != 1:
        raise ResultArtifactError(f"aggregation group {group_id!r} has conflicting required variants")

    by_variant: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = defaultdict(list)
    for grading, timing in records:
        by_variant[grading["aggregation"]["variant"]].append((grading, timing))
    required_variants = set(next(iter(required_variant_sets)))
    missing = sorted(required_variants - set(by_variant))
    if missing:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} is missing required variants: {', '.join(missing)}"
        )
    unexpected = sorted(set(by_variant) - required_variants)
    if unexpected:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} has unexpected variants: {', '.join(unexpected)}"
        )
    run_counts = {variant: len(variant_records) for variant, variant_records in by_variant.items()}
    if len(set(run_counts.values())) != 1:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} has unequal repeated-run counts"
        )
    for variant, variant_records in by_variant.items():
        policies = {
            (
                grading["aggregation"]["contributes_to_outcome"],
                grading["aggregation"].get("compare_to"),
                grading["aggregation"].get("minimum_pass_rate"),
                grading["aggregation"].get("configured_runs"),
                grading["run_kind"],
            )
            for grading, _ in variant_records
        }
        if len(policies) != 1:
            raise ResultArtifactError(
                f"aggregation group {group_id!r} has inconsistent metadata for variant {variant!r}"
            )

    variants = {
        variant: _aggregate_variant(by_variant[variant]) for variant in sorted(by_variant)
    }
    comparison_pairs = {
        (grading["aggregation"]["variant"], grading["aggregation"].get("compare_to"))
        for grading, _ in records
        if grading["aggregation"].get("compare_to") is not None
    }
    comparisons: list[dict[str, object]] = []
    for variant, baseline in sorted(comparison_pairs):
        if baseline not in variants:
            raise ResultArtifactError(
                f"aggregation group {group_id!r} comparison baseline is missing: {baseline}"
            )
        delta = variants[variant]["pass_rate"] - variants[baseline]["pass_rate"]
        comparisons.append(
            {
                "variant": variant,
                "baseline_variant": baseline,
                "pass_rate_delta": delta,
                "investigation_required": delta <= 0,
            }
        )
    return {
        "group_id": group_id,
        "skill_name": next(iter(skill_names)),
        "case_id": next(iter(case_ids)),
        "variants": variants,
        "comparisons": comparisons,
    }


def _contributing_outcomes(
    group_id: str,
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> list[bool]:
    contributing = [
        grading
        for grading, _ in records
        if grading["aggregation"]["contributes_to_outcome"]
    ]
    if not contributing:
        return []
    thresholds = {
        grading["aggregation"].get("minimum_pass_rate") for grading in contributing
    }
    if thresholds == {None}:
        return [_grading_passed(grading) for grading in contributing]
    if None in thresholds or len(thresholds) != 1:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} has inconsistent outcome thresholds"
        )
    variants = {grading["aggregation"]["variant"] for grading in contributing}
    if len(variants) != 1:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} applies one threshold to multiple variants"
        )
    threshold = next(iter(thresholds))
    configured_runs = {
        grading["aggregation"].get("configured_runs") for grading in contributing
    }
    if len(configured_runs) != 1 or None in configured_runs:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} has inconsistent configured run counts"
        )
    configured_run_count = next(iter(configured_runs))
    run_numbers = [grading["aggregation"].get("run_number") for grading in contributing]
    if (
        len(contributing) != configured_run_count
        or len(set(run_numbers)) != configured_run_count
        or set(run_numbers) != set(range(1, configured_run_count + 1))
    ):
        raise ResultArtifactError(
            f"aggregation group {group_id!r} does not contain the complete configured run set"
        )
    pass_rate = sum(_grading_passed(grading) for grading in contributing) / len(contributing)
    return [pass_rate >= threshold]


def _aggregate_skill_summaries(
    grouped: Mapping[str, Sequence[tuple[dict[str, object], dict[str, object]]]],
) -> list[dict[str, object]]:
    by_skill: dict[str, list[tuple[str, Sequence[tuple[dict[str, object], dict[str, object]]]]]] = defaultdict(list)
    for group_id, records in grouped.items():
        skill_names = {grading["skill_name"] for grading, _ in records}
        if len(skill_names) != 1:
            raise ResultArtifactError(f"aggregation group {group_id!r} mixes skills")
        by_skill[next(iter(skill_names))].append((group_id, records))

    summaries: list[dict[str, object]] = []
    for skill_name in sorted(by_skill):
        outcomes: list[bool] = []
        measurements: dict[str, list[float]] = defaultdict(list)
        for group_id, records in by_skill[skill_name]:
            outcomes.extend(_contributing_outcomes(group_id, records))
            for grading, _ in records:
                for name, value in grading.get("measurements", {}).items():
                    measurements[name].append(value)
        summaries.append(
            {
                "skill_name": skill_name,
                "total_outcomes": len(outcomes),
                "passed_outcomes": sum(outcomes),
                "failed_outcomes": len(outcomes) - sum(outcomes),
                "pass_rate": sum(outcomes) / len(outcomes) if outcomes else 0.0,
                "measurements": {
                    name: {
                        "count": len(values),
                        "total": sum(values),
                        "mean": sum(values) / len(values),
                    }
                    for name, values in sorted(measurements.items())
                },
            }
        )
    return summaries


def _aggregate_variant(
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> dict[str, object]:
    passed = sum(_grading_passed(grading) for grading, _ in records)
    token_counts = [timing["total_tokens"] for _, timing in records]
    return {
        "runs": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "pass_rate": passed / len(records),
        "duration_ms_total": sum(timing["duration_ms"] for _, timing in records),
        "total_tokens": None if any(value is None for value in token_counts) else sum(token_counts),
    }


def _grading_passed(grading: Mapping[str, object]) -> bool:
    return grading["summary"]["failed"] == 0


def _parse_bounded_json(
    value: str | bytes,
    *,
    label: str,
    maximum_bytes: int | None = None,
    maximum_nodes: int | None = None,
    maximum_depth: int | None = None,
    maximum_scalar_bytes: int | None = None,
) -> object:
    maximum_bytes = (
        _MAX_RESULT_JSON_FILE_BYTES if maximum_bytes is None else maximum_bytes
    )
    maximum_nodes = _MAX_RESULT_JSON_NODES if maximum_nodes is None else maximum_nodes
    maximum_depth = _MAX_RESULT_JSON_DEPTH if maximum_depth is None else maximum_depth
    maximum_scalar_bytes = (
        _MAX_RESULT_JSON_SCALAR_BYTES
        if maximum_scalar_bytes is None
        else maximum_scalar_bytes
    )
    if min(
        maximum_bytes,
        maximum_nodes,
        maximum_depth,
        maximum_scalar_bytes,
    ) < 1:
        raise ResultArtifactError(f"{label} has invalid JSON boundary limits")
    if not isinstance(value, (str, bytes)):
        raise ResultArtifactError(f"{label} is not bounded JSON text")
    try:
        if isinstance(value, bytes):
            encoded_size = len(value)
            text = value.decode("utf-8")
        else:
            encoded_size = len(value.encode("utf-8"))
            text = value
    except (MemoryError, UnicodeError) as error:
        raise ResultArtifactError(f"{label} is not bounded UTF-8 JSON") from error
    if encoded_size > maximum_bytes:
        raise ResultArtifactError(f"{label} exceeds the JSON byte limit")
    try:
        preflight_bounded_json_structure(
            text,
            maximum_nodes=maximum_nodes,
            maximum_depth=maximum_depth,
            maximum_scalar_bytes=maximum_scalar_bytes,
            maximum_number_characters=_MAX_RESULT_JSON_NUMBER_CHARS,
        )
    except JsonPreflightError as error:
        if error.kind == "depth":
            raise ResultArtifactError(f"{label} exceeds the JSON depth limit") from error
        if error.kind == "nodes":
            raise ResultArtifactError(f"{label} exceeds the JSON node limit") from error
        if error.kind == "scalar":
            raise ResultArtifactError(f"{label} exceeds the JSON scalar limit") from error
        if error.kind == "nonfinite":
            raise ResultArtifactError(
                f"{label} contains a non-finite JSON number"
            ) from error
        raise ResultArtifactError(f"{label} is invalid bounded JSON") from error

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, item in pairs:
            if key in document:
                raise _JsonBoundaryError("contains a duplicate JSON key")
            document[key] = item
        return document

    def bounded_integer(token: str) -> int:
        if len(token) > _MAX_RESULT_JSON_NUMBER_CHARS:
            raise _JsonBoundaryError("exceeds the JSON scalar limit")
        return int(token)

    def bounded_float(token: str) -> float:
        if len(token) > _MAX_RESULT_JSON_NUMBER_CHARS:
            raise _JsonBoundaryError("exceeds the JSON scalar limit")
        result = float(token)
        if not math.isfinite(result):
            raise _JsonBoundaryError("contains a non-finite JSON number")
        return result

    def reject_constant(_: str) -> object:
        raise _JsonBoundaryError("contains a non-finite JSON number")

    try:
        document = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_int=bounded_integer,
            parse_float=bounded_float,
            parse_constant=reject_constant,
        )
    except _JsonBoundaryError as error:
        raise ResultArtifactError(f"{label} {error}") from error
    except (
        json.JSONDecodeError,
        MemoryError,
        OverflowError,
        RecursionError,
        UnicodeError,
        ValueError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} is invalid bounded JSON") from error
    _validate_bounded_json_structure(
        document,
        label=label,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
        maximum_scalar_bytes=maximum_scalar_bytes,
    )
    return document


def _validate_bounded_json_structure(
    document: object,
    *,
    label: str,
    maximum_nodes: int | None = None,
    maximum_depth: int | None = None,
    maximum_scalar_bytes: int | None = None,
) -> None:
    maximum_nodes = _MAX_RESULT_JSON_NODES if maximum_nodes is None else maximum_nodes
    maximum_depth = _MAX_RESULT_JSON_DEPTH if maximum_depth is None else maximum_depth
    maximum_scalar_bytes = (
        _MAX_RESULT_JSON_SCALAR_BYTES
        if maximum_scalar_bytes is None
        else maximum_scalar_bytes
    )
    pending: list[tuple[object, int]] = [(document, 1)]
    nodes = 0
    try:
        while pending:
            item, depth = pending.pop()
            if depth > maximum_depth:
                raise ResultArtifactError(f"{label} exceeds the JSON depth limit")
            nodes += 1
            if nodes > maximum_nodes:
                raise ResultArtifactError(f"{label} exceeds the JSON node limit")
            if isinstance(item, Mapping):
                if len(item) > maximum_nodes - nodes:
                    raise ResultArtifactError(f"{label} exceeds the JSON node limit")
                for key, child in item.items():
                    nodes += 1
                    if nodes > maximum_nodes:
                        raise ResultArtifactError(f"{label} exceeds the JSON node limit")
                    _validate_json_scalar(
                        key,
                        label=label,
                        maximum_scalar_bytes=maximum_scalar_bytes,
                    )
                    pending.append((child, depth + 1))
            elif isinstance(item, list):
                if len(item) > maximum_nodes - nodes:
                    raise ResultArtifactError(f"{label} exceeds the JSON node limit")
                pending.extend((child, depth + 1) for child in item)
            else:
                _validate_json_scalar(
                    item,
                    label=label,
                    maximum_scalar_bytes=maximum_scalar_bytes,
                )
    except ResultArtifactError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
        UnicodeError,
        ValueError,
    ) as error:
        raise ResultArtifactError(
            f"{label} exceeds bounded JSON structure limits"
        ) from error


def _validate_json_scalar(
    value: object,
    *,
    label: str,
    maximum_scalar_bytes: int,
) -> None:
    if isinstance(value, str):
        if len(value.encode("utf-8")) > maximum_scalar_bytes:
            raise ResultArtifactError(f"{label} exceeds the JSON scalar limit")
        return
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if value.bit_length() > _MAX_RESULT_JSON_NUMBER_CHARS * 4:
            raise ResultArtifactError(f"{label} exceeds the JSON scalar limit")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ResultArtifactError(f"{label} contains a non-finite JSON number")
        return
    raise ResultArtifactError(f"{label} contains a non-JSON scalar")


def _parse_result_document(
    content: bytes,
    path: Path,
    schema_name: str,
) -> dict[str, object]:
    document = _parse_bounded_json(
        content,
        label=f"cannot read trustworthy result {path}:",
    )
    if not isinstance(document, dict):
        raise ResultArtifactError(f"result artifact must contain a JSON object: {path}")
    if schema_name == "invocation.schema.json":
        attempts = document.get("attempts")
        if isinstance(attempts, list) and len(attempts) > _MAX_DECLARED_ATTEMPTS:
            raise ResultArtifactError("invocation exceeds the declared attempt limit")
    validate_result_document(document, schema_name)
    return document


def _read_result_document(
    path: Path, schema_name: str, root: Path
) -> dict[str, object]:
    _ensure_safe_artifact_path(root, path)
    content = _read_stable_path_file(
        path,
        maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
        label=f"cannot read trustworthy result {path}",
        limit_name="JSON byte limit",
    ).content
    return _parse_result_document(content, path, schema_name)


def _read_declared_attempts(root: Path) -> dict[str, dict[str, object]]:
    """Read the mandatory immutable declaration for one result workspace."""
    invocation_path = root / "invocation.json"
    try:
        invocation_metadata = os.stat(invocation_path, follow_symlinks=False)
    except (OSError, MemoryError, OverflowError, RuntimeError) as error:
        raise ResultArtifactError(
            f"results directory must contain one regular invocation.json: {root}"
        ) from error
    if not stat.S_ISREG(invocation_metadata.st_mode):
        raise ResultArtifactError(
            f"results directory must contain one regular invocation.json: {root}"
        )
    invocation = _read_result_document(
        invocation_path,
        "invocation.schema.json",
        root,
    )
    return _declared_attempts(invocation)


def _declared_attempts(
    invocation: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    try:
        attempts = invocation["attempts"]
        if len(attempts) > _MAX_DECLARED_ATTEMPTS:
            raise ResultArtifactError("invocation exceeds the declared attempt limit")
        declared_attempts: dict[str, dict[str, object]] = {}
        for attempt in attempts:
            run_id = attempt["run_id"]
            if run_id in declared_attempts:
                raise ResultArtifactError(
                    f"duplicate run_id in invocation manifest: {run_id}"
                )
            declared_attempts[run_id] = attempt
        return declared_attempts
    except ResultArtifactError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "invocation declaration exceeds bounded resource limits"
        ) from error


def _read_stable_path_file(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
    limit_name: str = "byte limit",
) -> _StableFileRead:
    parent_descriptor: int | None = None
    try:
        parent_descriptor = os.open(path.parent, _directory_open_flags())
        observed = os.stat(
            path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
            raise ResultArtifactError(
                f"{label} must be a regular non-symlink file"
            )
        return _read_stable_file_at(
            parent_descriptor,
            path.name,
            observed,
            maximum_bytes=maximum_bytes,
            label=label,
            limit_name=limit_name,
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} cannot be read safely") from error
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _read_stable_file_at(
    directory_descriptor: int,
    name: str,
    expected_metadata: os.stat_result,
    *,
    maximum_bytes: int,
    label: str,
    limit_name: str,
) -> _StableFileRead:
    if expected_metadata.st_size < 0 or expected_metadata.st_size > maximum_bytes:
        raise ResultArtifactError(f"{label} exceeds the {limit_name}")
    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(
            name,
            _regular_file_open_flags(),
            dir_fd=directory_descriptor,
        )
        opened = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _stable_result_metadata(expected_metadata)
            != _stable_result_metadata(opened)
        ):
            raise ResultArtifactError(f"{label} changed while being read")
        if opened.st_size < 0 or opened.st_size > maximum_bytes:
            raise ResultArtifactError(f"{label} exceeds the {limit_name}")

        remaining = opened.st_size
        content = bytearray()
        while remaining:
            chunk = os.read(
                file_descriptor,
                min(_RESULT_READ_CHUNK_BYTES, remaining),
            )
            if not chunk:
                raise ResultArtifactError(f"{label} changed while being read")
            content.extend(chunk)
            remaining -= len(chunk)
        if os.read(file_descriptor, 1):
            raise ResultArtifactError(f"{label} changed while being read")

        final = os.fstat(file_descriptor)
        current = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if (
            _stable_result_metadata(opened) != _stable_result_metadata(final)
            or _stable_result_metadata(final) != _stable_result_metadata(current)
        ):
            raise ResultArtifactError(f"{label} changed while being read")
        return _StableFileRead(
            content=bytes(content),
            metadata=_stable_result_metadata(final),
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} changed while being read") from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def _open_result_root(root: Path, requested_root: Path) -> tuple[int, tuple[int, ...]]:
    try:
        observed = os.stat(root, follow_symlinks=False)
    except (OSError, MemoryError, OverflowError, RuntimeError) as error:
        raise ResultArtifactError(
            f"results directory does not exist: {requested_root}"
        ) from error
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise ResultArtifactError(
            f"results directory must be a regular non-symlink directory: {requested_root}"
        )
    descriptor: int | None = None
    try:
        descriptor = os.open(root, _directory_open_flags())
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _stable_result_metadata(observed)
            != _stable_result_metadata(opened)
        ):
            raise ResultArtifactError(
                "results directory changed while opening bounded aggregation"
            )
        return descriptor, _stable_result_metadata(opened)
    except ResultArtifactError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ResultArtifactError(
            "results directory cannot be opened for bounded aggregation"
        ) from error


def _resolved_repository_identity(
    repository_root: Path | None,
) -> tuple[int, int]:
    repository = _REPOSITORY_ROOT if repository_root is None else repository_root
    try:
        resolved = repository.resolve(strict=True)
        metadata = os.stat(resolved, follow_symlinks=False)
    except (OSError, MemoryError, OverflowError, RuntimeError) as error:
        raise ResultArtifactError("cannot resolve result path") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise ResultArtifactError("cannot resolve result path")
    return metadata.st_dev, metadata.st_ino


def _verify_result_root_outside_repository(
    root_descriptor: int,
    repository_identity: tuple[int, int],
) -> None:
    current_descriptor: int | None = None
    try:
        current_descriptor = os.dup(root_descriptor)
        for _ in range(_MAX_RESULT_ANCESTOR_DEPTH):
            current = os.fstat(current_descriptor)
            current_identity = (current.st_dev, current.st_ino)
            if current_identity == repository_identity:
                raise ResultArtifactError(
                    "result path must be outside the repository"
                )
            parent_descriptor = os.open(
                "..",
                _directory_open_flags(),
                dir_fd=current_descriptor,
            )
            parent = os.fstat(parent_descriptor)
            parent_identity = (parent.st_dev, parent.st_ino)
            if parent_identity == current_identity:
                os.close(parent_descriptor)
                return
            os.close(current_descriptor)
            current_descriptor = parent_descriptor
        raise ResultArtifactError(
            "result path ancestry exceeds the verification depth limit"
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result path ancestry cannot be verified safely"
        ) from error
    finally:
        if current_descriptor is not None:
            os.close(current_descriptor)


def _verify_open_result_root(
    descriptor: int,
    root: Path,
    expected_metadata: tuple[int, ...],
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(root, follow_symlinks=False)
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "results directory changed during bounded aggregation"
        ) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or expected_metadata != _stable_result_metadata(opened)
        or expected_metadata != _stable_result_metadata(current)
    ):
        raise ResultArtifactError(
            "results directory changed during bounded aggregation"
        )


def _write_aggregate_result_artifacts(
    root_descriptor: int,
    root: Path,
    root_metadata: tuple[int, ...],
    repository_identity: tuple[int, int],
    snapshot: _ResultTreeSnapshot,
    benchmark: Mapping[str, object],
    *,
    terminal_decision: str,
    declared_attempt_count: int,
) -> None:
    try:
        payloads = (
            (
                "benchmark.json",
                f"{json.dumps(benchmark, indent=2, sort_keys=True)}\n".encode("utf-8"),
                _MAX_RESULT_JSON_FILE_BYTES,
            ),
            (
                "summary.md",
                (
                    "# Evaluation Aggregate\n\n"
                    f"Decision: {terminal_decision}\n\n"
                    "## Results\n\n"
                    f"{format_benchmark_summary(benchmark)}\n"
                ).encode("utf-8"),
                _MAX_RESULT_FILE_BYTES,
            ),
        )
    except ResultArtifactError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise ResultArtifactError(
            "cannot serialize aggregate result artifacts within resource limits"
        ) from error

    replaced_bytes = sum(
        snapshot.files.get((name,), (0, 0, 0, 0, 0))[4]
        for name, _, _ in payloads
    )
    payload_bytes = sum(len(content) for _, content, _ in payloads)
    if any(len(content) > limit for _, content, limit in payloads):
        raise ResultArtifactError(
            "aggregate result artifacts exceed the per-file byte limit"
        )
    if snapshot.total_bytes - replaced_bytes + payload_bytes > _MAX_RESULT_TREE_BYTES:
        raise ResultArtifactError(
            "aggregate result artifacts exceed the cumulative byte limit"
        )
    current_entries = len(snapshot.files) + len(snapshot.directories) - 1
    added_entries = sum(
        (name,) not in snapshot.files for name, _, _ in payloads
    )
    if (
        current_entries + added_entries
        > _result_tree_entry_limit(declared_attempt_count)
    ):
        raise ResultArtifactError(
            "aggregate result artifacts exceed the entry-count limit"
        )

    original_content: dict[str, bytes | None] = {}
    for name, _, maximum_bytes in payloads:
        if (name,) not in snapshot.files:
            original_content[name] = None
            continue
        original_content[name] = _read_snapshotted_file(
            root_descriptor,
            snapshot,
            (name,),
            maximum_bytes=maximum_bytes,
            label="aggregate result target",
            limit_name="byte limit",
        ).content

    written_metadata: dict[tuple[str, ...], tuple[int, ...]] = {}
    attempted_names: list[str] = []
    try:
        for name, content, maximum_bytes in payloads:
            attempted_names.append(name)
            written_metadata[(name,)] = _write_atomic_result_file_at(
                root_descriptor,
                name,
                content,
                expected_metadata=snapshot.files.get((name,)),
                maximum_bytes=maximum_bytes,
            )
            _verify_open_result_root_identity(
                root_descriptor,
                root,
                root_metadata,
            )
            _verify_result_root_outside_repository(
                root_descriptor,
                repository_identity,
            )
        try:
            os.fsync(root_descriptor)
        except OSError as error:
            raise ResultArtifactError(
                "cannot write aggregate result artifacts"
            ) from error

        post_write = _snapshot_result_tree(
            root_descriptor,
            root,
            declared_attempt_count=declared_attempt_count,
        )
        expected_files = dict(snapshot.files)
        expected_files.update(written_metadata)
        if post_write.files != expected_files:
            raise ResultArtifactError(
                "result tree changed while writing aggregate artifacts"
            )
        if set(post_write.directories) != set(snapshot.directories) or any(
            post_write.directories[relative] != metadata
            for relative, metadata in snapshot.directories.items()
            if relative
        ):
            raise ResultArtifactError(
                "result tree changed while writing aggregate artifacts"
            )
        _verify_open_result_root_identity(
            root_descriptor,
            root,
            root_metadata,
        )
        _verify_result_root_outside_repository(
            root_descriptor,
            repository_identity,
        )
    except BaseException as error:
        try:
            _rollback_aggregate_result_artifacts(
                root_descriptor,
                payloads,
                original_content,
                attempted_names,
            )
        except BaseException as rollback_error:
            if not isinstance(rollback_error, Exception):
                raise
            raise ResultArtifactError(
                "cannot rollback aggregate result artifacts"
            ) from rollback_error
        if not isinstance(error, Exception):
            raise
        if isinstance(error, ResultArtifactError):
            raise
        if isinstance(
            error,
            (OSError, MemoryError, OverflowError, RuntimeError, SystemError),
        ):
            raise ResultArtifactError(
                "cannot write aggregate result artifacts"
            ) from error
        raise


def _rollback_aggregate_result_artifacts(
    root_descriptor: int,
    payloads: Sequence[tuple[str, bytes, int]],
    original_content: Mapping[str, bytes | None],
    attempted_names: Sequence[str],
) -> None:
    payload_by_name = {
        name: (content, maximum_bytes)
        for name, content, maximum_bytes in payloads
    }
    for name in reversed(attempted_names):
        replacement, maximum_bytes = payload_by_name[name]
        _restore_aggregate_result_artifact(
            root_descriptor,
            name,
            replacement=replacement,
            original=original_content[name],
            maximum_bytes=maximum_bytes,
        )
    try:
        os.fsync(root_descriptor)
    except OSError as error:
        raise ResultArtifactError(
            "cannot rollback aggregate result artifacts"
        ) from error


def _restore_aggregate_result_artifact(
    root_descriptor: int,
    name: str,
    *,
    replacement: bytes,
    original: bytes | None,
    maximum_bytes: int,
) -> None:
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(
                name,
                _regular_file_open_flags(),
                dir_fd=root_descriptor,
            )
        except FileNotFoundError:
            return
        current = _fingerprint_result_descriptor(
            descriptor,
            maximum_bytes=maximum_bytes,
            label="aggregate result target during rollback",
        )
        original_digest = (
            None if original is None else hashlib.sha256(original).digest()
        )
        replacement_digest = hashlib.sha256(replacement).digest()
        if original_digest is not None and current.digest == original_digest:
            return
        if current.digest != replacement_digest:
            return
        if original is None:
            _remove_result_entry_for_descriptor(
                root_descriptor,
                name,
                descriptor,
                label="aggregate result target during rollback",
                expected_identity=current,
                maximum_bytes=maximum_bytes,
            )
            return
        expected_metadata = current.metadata
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                raise ResultArtifactError(
                    "cannot release aggregate result handles"
                ) from error
    _write_atomic_result_file_at(
        root_descriptor,
        name,
        original,
        expected_metadata=expected_metadata,
        maximum_bytes=maximum_bytes,
    )


def _write_atomic_result_file_at(
    root_descriptor: int,
    name: str,
    content: bytes,
    *,
    expected_metadata: tuple[int, ...] | None,
    maximum_bytes: int,
) -> tuple[int, ...]:
    existing_descriptor: int | None = None
    descriptor: int | None = None
    temporary_name = f".{name}.{uuid.uuid4().hex}.tmp"
    temporary_present = False
    result_metadata: tuple[int, ...] | None = None
    try:
        try:
            current = os.stat(
                name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if expected_metadata is not None:
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                )
        except OSError as error:
            raise ResultArtifactError(
                "cannot write aggregate result artifacts"
            ) from error
        else:
            if (
                expected_metadata is None
                or not stat.S_ISREG(current.st_mode)
                or _stable_result_metadata(current) != expected_metadata
            ):
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                )
            existing_descriptor = os.open(
                name,
                _regular_file_open_flags(),
                dir_fd=root_descriptor,
            )
            opened_existing = os.fstat(existing_descriptor)
            current_existing = os.stat(
                name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(opened_existing.st_mode)
                or _stable_result_metadata(opened_existing) != expected_metadata
                or _stable_result_metadata(current_existing) != expected_metadata
            ):
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                )

        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=root_descriptor,
        )
        temporary_present = True
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written < 1:
                raise ResultArtifactError(
                    "cannot write aggregate result artifacts"
                )
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
        staged = os.fstat(descriptor)
        if not stat.S_ISREG(staged.st_mode) or staged.st_size != len(content):
            raise ResultArtifactError(
                "cannot write aggregate result artifacts"
            )
        if expected_metadata is None:
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=root_descriptor,
                    dst_dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as error:
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                ) from error
            linked = os.fstat(descriptor)
            installed = os.stat(
                name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(installed.st_mode)
                or _stable_result_metadata(linked)
                != _stable_result_metadata(installed)
            ):
                raise ResultArtifactError(
                    "aggregate result target changed while writing"
                )
            _remove_result_entry_for_descriptor(
                root_descriptor,
                temporary_name,
                descriptor,
                label="aggregate temporary artifact",
            )
            temporary_present = False
        else:
            if existing_descriptor is None:
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                )
            _replace_existing_result_entry_at(
                root_descriptor,
                temporary_name,
                name,
                staged_descriptor=descriptor,
                existing_descriptor=existing_descriptor,
                expected_metadata=expected_metadata,
                maximum_bytes=maximum_bytes,
            )
            temporary_present = False
        final = os.fstat(descriptor)
        installed = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(installed.st_mode)
            or _stable_result_metadata(final)
            != _stable_result_metadata(installed)
        ):
            raise ResultArtifactError(
                "aggregate result target changed while writing"
            )
        result_metadata = _stable_result_metadata(final)
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "cannot write aggregate result artifacts"
        ) from error
    finally:
        cleanup_error: ResultArtifactError | None = None
        if temporary_present and descriptor is not None:
            try:
                _remove_result_entry_for_descriptor(
                    root_descriptor,
                    temporary_name,
                    descriptor,
                    label="aggregate temporary artifact",
                )
            except ResultArtifactError as error:
                cleanup_error = error
        for open_descriptor in (existing_descriptor, descriptor):
            if open_descriptor is None:
                continue
            try:
                os.close(open_descriptor)
            except OSError as error:
                if cleanup_error is None:
                    cleanup_error = ResultArtifactError(
                        "cannot release aggregate result handles"
                    )
                    cleanup_error.__cause__ = error
        if cleanup_error is not None:
            raise cleanup_error
    if result_metadata is None:
        raise ResultArtifactError("cannot write aggregate result artifacts")
    return result_metadata


def _remove_result_entry_for_descriptor(
    root_descriptor: int,
    name: str,
    open_descriptor: int,
    *,
    label: str,
    expected_identity: _StableContentIdentity | None = None,
    maximum_bytes: int | None = None,
) -> None:
    try:
        if expected_identity is None:
            opened_metadata = _stable_result_metadata(
                os.fstat(open_descriptor)
            )
        else:
            if maximum_bytes is None:
                raise ResultArtifactError(f"{label} has no fingerprint byte limit")
            current_identity = _fingerprint_result_descriptor(
                open_descriptor,
                maximum_bytes=maximum_bytes,
                expected_metadata=expected_identity.metadata,
                label=label,
            )
            if current_identity != expected_identity:
                raise ResultArtifactError(f"{label} changed during cleanup")
            opened_metadata = current_identity.metadata
        current = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(opened_metadata[2])
            or _stable_result_metadata(current)
            != opened_metadata
        ):
            raise ResultArtifactError(f"{label} changed during cleanup")
        os.unlink(name, dir_fd=root_descriptor)
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} changed during cleanup") from error


def _fingerprint_result_descriptor(
    descriptor: int,
    *,
    maximum_bytes: int,
    label: str,
    expected_metadata: tuple[int, ...] | None = None,
) -> _StableContentIdentity:
    try:
        positioned_read = getattr(os, "pread", None)
        if positioned_read is None or maximum_bytes < 0:
            raise ResultArtifactError(f"{label} cannot be fingerprinted safely")
        opened = os.fstat(descriptor)
        opened_metadata = _stable_result_metadata(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size < 0
            or opened.st_size > maximum_bytes
            or (
                expected_metadata is not None
                and opened_metadata != expected_metadata
            )
        ):
            raise ResultArtifactError(f"{label} changed while fingerprinting")

        digest = hashlib.sha256()
        offset = 0
        while offset < opened.st_size:
            chunk = positioned_read(
                descriptor,
                min(_RESULT_READ_CHUNK_BYTES, opened.st_size - offset),
                offset,
            )
            if not chunk:
                raise ResultArtifactError(f"{label} changed while fingerprinting")
            digest.update(chunk)
            offset += len(chunk)
        if positioned_read(descriptor, 1, offset):
            raise ResultArtifactError(f"{label} changed while fingerprinting")

        final_metadata = _stable_result_metadata(os.fstat(descriptor))
        if (
            final_metadata != opened_metadata
            or (
                expected_metadata is not None
                and final_metadata != expected_metadata
            )
        ):
            raise ResultArtifactError(f"{label} changed while fingerprinting")
        return _StableContentIdentity(
            metadata=final_metadata,
            digest=digest.digest(),
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
        TypeError,
        ValueError,
    ) as error:
        raise ResultArtifactError(f"{label} changed while fingerprinting") from error


def _replace_existing_result_entry_at(
    root_descriptor: int,
    temporary_name: str,
    name: str,
    *,
    staged_descriptor: int,
    existing_descriptor: int,
    expected_metadata: tuple[int, ...],
    maximum_bytes: int,
) -> None:
    exchanged = False
    rollback_descriptor: int | None = None
    try:
        expected_identity = _fingerprint_result_descriptor(
            existing_descriptor,
            maximum_bytes=maximum_bytes,
            expected_metadata=expected_metadata,
            label="aggregate result target",
        )
        current_before_exchange = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if _stable_result_metadata(current_before_exchange) != expected_metadata:
            raise ResultArtifactError(
                "aggregate result target changed before writing"
            )
        _atomic_exchange_result_entries(
            root_descriptor,
            temporary_name,
            name,
        )
        exchanged = True
        staged = os.fstat(staged_descriptor)
        installed = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        retained_identity = _fingerprint_result_descriptor(
            existing_descriptor,
            maximum_bytes=maximum_bytes,
            label="aggregate result target",
        )
        retained = os.stat(
            temporary_name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(installed.st_mode)
            or not stat.S_ISREG(retained.st_mode)
            or _stable_result_metadata(installed)
            != _stable_result_metadata(staged)
            or _stable_result_metadata(retained)
            != retained_identity.metadata
            or retained_identity.metadata[:-1]
            != expected_identity.metadata[:-1]
            or retained_identity.digest != expected_identity.digest
        ):
            raise ResultArtifactError(
                "aggregate result target changed while writing"
            )
        _remove_result_entry_for_descriptor(
            root_descriptor,
            temporary_name,
            existing_descriptor,
            label="aggregate result target",
            expected_identity=retained_identity,
            maximum_bytes=maximum_bytes,
        )
        exchanged = False
    except (
        ResultArtifactError,
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        if exchanged:
            try:
                rollback_descriptor = os.open(
                    temporary_name,
                    _regular_file_open_flags(),
                    dir_fd=root_descriptor,
                )
                rollback_identity = _fingerprint_result_descriptor(
                    rollback_descriptor,
                    maximum_bytes=maximum_bytes,
                    label="aggregate retained result target",
                )
                current_installed = os.stat(
                    name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                current_retained = os.stat(
                    temporary_name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                staged = os.fstat(staged_descriptor)
                if (
                    _stable_result_metadata(current_installed)
                    != _stable_result_metadata(staged)
                    or _stable_result_metadata(current_retained)
                    != rollback_identity.metadata
                ):
                    raise ResultArtifactError(
                        "aggregate result target changed during rollback"
                    )
                _atomic_exchange_result_entries(
                    root_descriptor,
                    temporary_name,
                    name,
                )
                restored_target = os.stat(
                    name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                restored_temporary = os.stat(
                    temporary_name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                staged = os.fstat(staged_descriptor)
                restored_retained = os.fstat(rollback_descriptor)
                if (
                    _stable_result_metadata(restored_target)
                    != _stable_result_metadata(restored_retained)
                    or _stable_result_metadata(restored_temporary)
                    != _stable_result_metadata(staged)
                ):
                    raise ResultArtifactError(
                        "aggregate result target changed during rollback"
                    )
                exchanged = False
            except ResultArtifactError as rollback_error:
                raise ResultArtifactError(
                    "aggregate result target changed during rollback"
                ) from rollback_error
        if isinstance(error, ResultArtifactError):
            raise error
        raise ResultArtifactError(
            "cannot atomically replace aggregate result target"
        ) from error
    finally:
        if rollback_descriptor is not None:
            try:
                os.close(rollback_descriptor)
            except OSError as error:
                raise ResultArtifactError(
                    "cannot release aggregate result handles"
                ) from error


def _atomic_exchange_result_entries(
    root_descriptor: int,
    first_name: str,
    second_name: str,
) -> None:
    try:
        library = ctypes.CDLL(None, use_errno=True)
        if hasattr(library, "renameatx_np"):
            exchange = library.renameatx_np
        elif hasattr(library, "renameat2"):
            exchange = library.renameat2
        else:
            raise ResultArtifactError(
                "atomic aggregate replacement is unsupported"
            )
        exchange.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        exchange.restype = ctypes.c_int
        result = exchange(
            root_descriptor,
            os.fsencode(first_name),
            root_descriptor,
            os.fsencode(second_name),
            0x00000002,
        )
        if result != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, "atomic aggregate replacement failed")
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
        TypeError,
        ValueError,
    ) as error:
        raise ResultArtifactError(
            "cannot atomically replace aggregate result target"
        ) from error


def _verify_open_result_root_identity(
    descriptor: int,
    root: Path,
    expected_metadata: tuple[int, ...],
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(root, follow_symlinks=False)
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "results directory changed while writing aggregate artifacts"
        ) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _stable_result_metadata(opened)[:3] != expected_metadata[:3]
        or _stable_result_metadata(current)[:3] != expected_metadata[:3]
    ):
        raise ResultArtifactError(
            "results directory changed while writing aggregate artifacts"
        )


def _read_required_invocation(
    root_descriptor: int,
    root: Path,
) -> _StableFileRead:
    try:
        observed = os.stat(
            "invocation.json",
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
    except (OSError, MemoryError, OverflowError, RuntimeError) as error:
        raise ResultArtifactError(
            f"results directory must contain one regular invocation.json: {root}"
        ) from error
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise ResultArtifactError(
            f"results directory must contain one regular invocation.json: {root}"
        )
    return _read_stable_file_at(
        root_descriptor,
        "invocation.json",
        observed,
        maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
        label=f"cannot read trustworthy result {root / 'invocation.json'}",
        limit_name="JSON byte limit",
    )


def _snapshot_result_tree(
    root_descriptor: int,
    root: Path,
    *,
    declared_attempt_count: int,
) -> _ResultTreeSnapshot:
    maximum_entries = _result_tree_entry_limit(declared_attempt_count)
    if maximum_entries < 1:
        raise ResultArtifactError("result tree has an invalid entry-count limit")
    try:
        initial_root = os.fstat(root_descriptor)
        if not stat.S_ISDIR(initial_root.st_mode):
            raise ResultArtifactError(
                "results directory changed during bounded inventory"
            )
        files: dict[tuple[str, ...], tuple[int, ...]] = {}
        directories: dict[tuple[str, ...], tuple[int, ...]] = {
            (): _stable_result_metadata(initial_root)
        }
        state = _ResultTreeScanState()
        _scan_result_directory(
            root_descriptor,
            (),
            files,
            directories,
            state,
            maximum_entries=maximum_entries,
            maximum_attempt_entries=declared_attempt_count + 1,
        )
        final_root = os.fstat(root_descriptor)
        current_root = os.stat(root, follow_symlinks=False)
        if (
            _stable_result_metadata(initial_root)
            != _stable_result_metadata(final_root)
            or _stable_result_metadata(final_root)
            != _stable_result_metadata(current_root)
        ):
            raise ResultArtifactError(
                "result tree changed during bounded inventory"
            )
        return _ResultTreeSnapshot(
            files=files,
            directories=directories,
            total_bytes=state.total_bytes,
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result tree cannot be inventoried within resource limits"
        ) from error


def _result_tree_entry_limit(declared_attempt_count: int) -> int:
    return min(
        _MAX_RESULT_TREE_ENTRIES,
        _MAX_RESULT_ROOT_ENTRIES
        + declared_attempt_count * _MAX_RESULT_ENTRIES_PER_ATTEMPT,
    )


def _scan_result_directory(
    directory_descriptor: int,
    parent_parts: tuple[str, ...],
    files: dict[tuple[str, ...], tuple[int, ...]],
    directories: dict[tuple[str, ...], tuple[int, ...]],
    state: _ResultTreeScanState,
    *,
    maximum_entries: int,
    maximum_attempt_entries: int,
) -> None:
    inspected: list[tuple[str, os.stat_result]] = []
    try:
        with os.scandir(directory_descriptor) as entries:
            for entry in entries:
                state.entries += 1
                if state.entries > maximum_entries:
                    raise ResultArtifactError(
                        "result tree exceeds the entry-count limit"
                    )
                if (
                    parent_parts == ("attempts",)
                    and len(inspected) >= maximum_attempt_entries
                ):
                    raise ResultArtifactError(
                        "attempt inventory exceeds the declared attempt count bound "
                        "for the immutable invocation manifest"
                    )
                inspected.append(
                    (entry.name, entry.stat(follow_symlinks=False))
                )
        inspected.sort(key=lambda item: item[0])
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result tree cannot inspect an entry within resource limits"
        ) from error

    for name, expected in inspected:
        relative = (*parent_parts, name)
        if len(relative) > _MAX_RESULT_TREE_DEPTH:
            raise ResultArtifactError(
                "result tree exceeds the directory depth limit"
            )
        if stat.S_ISLNK(expected.st_mode):
            raise ResultArtifactError(
                "attempt entry or result artifact must not be a symlink"
            )
        if stat.S_ISDIR(expected.st_mode):
            _scan_result_child_directory(
                directory_descriptor,
                name,
                expected,
                relative,
                files,
                directories,
                state,
                maximum_entries=maximum_entries,
                maximum_attempt_entries=maximum_attempt_entries,
            )
            continue
        if not stat.S_ISREG(expected.st_mode):
            raise ResultArtifactError("result tree contains a special file")
        if expected.st_size < 0 or expected.st_size > _MAX_RESULT_FILE_BYTES:
            raise ResultArtifactError(
                "result tree exceeds the per-file byte limit"
            )
        if state.total_bytes + expected.st_size > _MAX_RESULT_TREE_BYTES:
            raise ResultArtifactError(
                "result tree exceeds the cumulative byte limit"
            )
        state.total_bytes += expected.st_size
        files[relative] = _stable_result_metadata(expected)


def _scan_result_child_directory(
    parent_descriptor: int,
    name: str,
    expected: os.stat_result,
    relative: tuple[str, ...],
    files: dict[tuple[str, ...], tuple[int, ...]],
    directories: dict[tuple[str, ...], tuple[int, ...]],
    state: _ResultTreeScanState,
    *,
    maximum_entries: int,
    maximum_attempt_entries: int,
) -> None:
    child_descriptor: int | None = None
    try:
        child_descriptor = os.open(
            name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(child_descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _stable_result_metadata(expected)
            != _stable_result_metadata(opened)
        ):
            raise ResultArtifactError(
                "result tree changed during bounded inventory"
            )
        directories[relative] = _stable_result_metadata(opened)
        _scan_result_directory(
            child_descriptor,
            relative,
            files,
            directories,
            state,
            maximum_entries=maximum_entries,
            maximum_attempt_entries=maximum_attempt_entries,
        )
        final = os.fstat(child_descriptor)
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            _stable_result_metadata(opened) != _stable_result_metadata(final)
            or _stable_result_metadata(final) != _stable_result_metadata(current)
        ):
            raise ResultArtifactError(
                "result tree changed during bounded inventory"
            )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result tree changed during bounded inventory"
        ) from error
    finally:
        if child_descriptor is not None:
            os.close(child_descriptor)


def _validate_result_tree(
    snapshot: _ResultTreeSnapshot,
    results_dir: Path,
) -> tuple[str, ...]:
    root_files = {
        relative[0] for relative in snapshot.files if len(relative) == 1
    }
    root_directories = {
        relative[0]
        for relative in snapshot.directories
        if len(relative) == 1
    }
    if root_directories != {"attempts"}:
        if "attempts" not in root_directories:
            raise ResultArtifactError(
                f"results directory has no attempts: {results_dir}"
            )
        raise ResultArtifactError("result tree contains an undeclared result entry")
    if "invocation.json" not in root_files:
        raise ResultArtifactError(
            f"results directory must contain one regular invocation.json: {results_dir}"
        )
    if not root_files.issubset(_ROOT_RESULT_FILES):
        raise ResultArtifactError("result tree contains an undeclared result entry")

    direct_attempt_files = [
        relative
        for relative in snapshot.files
        if len(relative) == 2 and relative[0] == "attempts"
    ]
    if direct_attempt_files:
        raise ResultArtifactError("attempt entry must be a directory")
    attempt_directories = tuple(
        sorted(
            relative[1]
            for relative in snapshot.directories
            if len(relative) == 2 and relative[0] == "attempts"
        )
    )
    if not attempt_directories:
        raise ResultArtifactError(
            f"no attempt.json declarations found under {results_dir}"
        )

    for directory_name in attempt_directories:
        attempt_prefix = ("attempts", directory_name)
        direct_files = {
            relative[-1]
            for relative in snapshot.files
            if relative[:-1] == attempt_prefix
        }
        direct_directories = {
            relative[-1]
            for relative in snapshot.directories
            if relative[:-1] == attempt_prefix
        }
        missing = sorted(_REQUIRED_ATTEMPT_RESULT_FILES - direct_files)
        if missing:
            raise ResultArtifactError(
                "attempt entry must contain required control artifact "
                f"{missing[0]}"
            )
        if not direct_files.issubset(_ATTEMPT_RESULT_FILES):
            raise ResultArtifactError(
                "result tree contains an undeclared result entry"
            )
        if direct_directories != {"outputs"}:
            raise ResultArtifactError(
                "attempt entry must contain only its outputs directory"
            )
    return attempt_directories


def _read_snapshotted_result_document(
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    relative: tuple[str, ...],
    path: Path,
    schema_name: str,
) -> dict[str, object]:
    read = _read_snapshotted_file(
        root_descriptor,
        snapshot,
        relative,
        maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
        label=f"cannot read trustworthy result {path}",
        limit_name="JSON byte limit",
    )
    return _parse_result_document(read.content, path, schema_name)


def _read_snapshotted_file(
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    relative: tuple[str, ...],
    *,
    maximum_bytes: int,
    label: str,
    limit_name: str,
) -> _StableFileRead:
    expected_file = snapshot.files.get(relative)
    if expected_file is None:
        raise ResultArtifactError(f"{label} is missing from the bounded inventory")

    def descend(directory_descriptor: int, index: int) -> _StableFileRead:
        name = relative[index]
        if index == len(relative) - 1:
            try:
                observed = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except (
                OSError,
                MemoryError,
                OverflowError,
                RuntimeError,
                SystemError,
            ) as error:
                raise ResultArtifactError(f"{label} changed while being read") from error
            if (
                not stat.S_ISREG(observed.st_mode)
                or _stable_result_metadata(observed) != expected_file
            ):
                raise ResultArtifactError(f"{label} changed while being read")
            result = _read_stable_file_at(
                directory_descriptor,
                name,
                observed,
                maximum_bytes=maximum_bytes,
                label=label,
                limit_name=limit_name,
            )
            if result.metadata != expected_file:
                raise ResultArtifactError(f"{label} changed while being read")
            return result

        prefix = relative[: index + 1]
        expected_directory = snapshot.directories.get(prefix)
        if expected_directory is None:
            raise ResultArtifactError(f"{label} changed while being read")
        child_descriptor: int | None = None
        try:
            observed = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(observed.st_mode)
                or _stable_result_metadata(observed) != expected_directory
            ):
                raise ResultArtifactError(f"{label} changed while being read")
            child_descriptor = os.open(
                name,
                _directory_open_flags(),
                dir_fd=directory_descriptor,
            )
            opened = os.fstat(child_descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _stable_result_metadata(opened) != expected_directory
            ):
                raise ResultArtifactError(f"{label} changed while being read")
            result = descend(child_descriptor, index + 1)
            final = os.fstat(child_descriptor)
            current = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if (
                _stable_result_metadata(final) != expected_directory
                or _stable_result_metadata(current) != expected_directory
            ):
                raise ResultArtifactError(f"{label} changed while being read")
            return result
        except ResultArtifactError:
            raise
        except (
            OSError,
            MemoryError,
            OverflowError,
            RecursionError,
            RuntimeError,
            SystemError,
        ) as error:
            raise ResultArtifactError(f"{label} changed while being read") from error
        finally:
            if child_descriptor is not None:
                os.close(child_descriptor)

    return descend(root_descriptor, 0)


def _stable_result_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _regular_file_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _require_declared_attempt_paths(paths: AttemptPaths) -> None:
    """Confirm attempt writers operate only on one invocation-declared attempt."""
    attempts_root = paths.root.parent
    workspace_root = attempts_root.parent
    expected_paths = AttemptPaths(
        root=paths.root,
        manifest=paths.root / "attempt.json",
        response=paths.root / "outputs" / "response.md",
        transcript=paths.root / "transcript.md",
        execution_trace=paths.root / "execution_trace.jsonl",
        timing=paths.root / "timing.json",
        grading=paths.root / "grading.json",
        manual_grading=paths.root / "manual_grading.json",
        feedback=paths.root / "feedback.json",
    )
    try:
        resolved_workspace = workspace_root.resolve(strict=True)
        resolved_attempts = attempts_root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ResultArtifactError(
            "cannot resolve attempt artifact workspace"
        ) from error
    if (
        attempts_root.name != "attempts"
        or paths != expected_paths
        or attempts_root.is_symlink()
        or not attempts_root.is_dir()
        or paths.root.is_symlink()
        or not paths.root.is_dir()
        or resolved_attempts != resolved_workspace / "attempts"
    ):
        raise ResultArtifactError("attempt artifact paths are not owned by an invocation workspace")
    manifest = _read_result_document(paths.manifest, "attempt.schema.json", workspace_root)
    declared_attempts = _read_declared_attempts(workspace_root)
    if declared_attempts.get(manifest["run_id"]) != manifest:
        raise ResultArtifactError(
            "attempt does not match the immutable invocation manifest"
        )


def _validate_grading_semantics(
    grading: Mapping[str, object], *, expected_source: str
) -> None:
    if grading["grade_source"] != expected_source:
        raise ResultArtifactError(
            f"expected {expected_source} grading for run {grading['run_id']}, "
            f"got {grading['grade_source']}"
        )
    results = grading["assertion_results"]
    identifiers = [result["id"] for result in results]
    if len(identifiers) != len(set(identifiers)):
        raise ResultArtifactError(
            f"grading for run {grading['run_id']} has duplicate assertion identifiers"
        )
    passed = sum(bool(result["passed"]) for result in results)
    total = len(results)
    expected_summary = {
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "pass_rate": passed / total if total else 0.0,
    }
    if grading["summary"] != expected_summary:
        raise ResultArtifactError(f"grading summary does not match results for run {grading['run_id']}")
    aggregation = grading["aggregation"]
    if aggregation["variant"] not in aggregation["required_variants"]:
        raise ResultArtifactError(
            f"aggregation variant is not declared as required for run {grading['run_id']}"
        )


def _validate_complete_manual_override(
    generated: Mapping[str, object],
    manual: Mapping[str, object],
    manual_path: Path,
) -> None:
    identity_fields = ("run_id", "skill_name", "case_id", "run_kind", "aggregation")
    if any(generated[field] != manual[field] for field in identity_fields):
        raise ResultArtifactError(f"manual grading is not a complete override for {manual_path}")
    if generated.get("measurements", {}) != manual.get("measurements", {}):
        raise ResultArtifactError(f"manual grading is not a complete override for {manual_path}")
    generated_assertions = [
        (result["id"], result["kind"], result["text"])
        for result in generated["assertion_results"]
    ]
    manual_assertions = [
        (result["id"], result["kind"], result["text"])
        for result in manual["assertion_results"]
    ]
    if generated_assertions != manual_assertions:
        raise ResultArtifactError(f"manual grading is not a complete override for {manual_path}")


def _validate_artifact_matches_manifest(
    artifact: Mapping[str, object],
    manifest: Mapping[str, object],
    artifact_path: Path,
) -> None:
    for field in ("run_id", "skill_name", "case_id", "run_kind"):
        if artifact[field] != manifest[field]:
            raise ResultArtifactError(
                f"artifact does not match attempt manifest in {artifact_path}: {field}"
            )
    if "aggregation" in artifact and artifact["aggregation"] != manifest["aggregation"]:
        raise ResultArtifactError(
            f"artifact aggregation policy does not match attempt manifest in {artifact_path}"
        )


def _validate_completed_timing(
    timing: Mapping[str, object], timing_path: Path
) -> None:
    if timing["status"] == "completed" and timing["exit_code"] != 0:
        raise ResultArtifactError(
            f"completed timing lacks an explicit successful exit in {timing_path}"
        )
    if timing["status"] == "completed" and (
        timing["model"] is None or timing["reasoning_effort"] is None
    ):
        raise ResultArtifactError(
            f"completed timing lacks model or reasoning metadata in {timing_path}"
        )


def _summarize_assertions(results: Sequence[AssertionResult]) -> GradingSummary:
    passed = sum(result.passed for result in results)
    total = len(results)
    return GradingSummary(
        passed=passed,
        failed=total - passed,
        total=total,
        pass_rate=passed / total if total else 0.0,
    )


def _write_json_once(
    path: Path, value: Mapping[str, object], root: Path
) -> None:
    _write_text_once(
        path,
        f"{json.dumps(value, indent=2, sort_keys=True)}\n",
        root,
    )


def _write_json_atomic(
    path: Path, value: Mapping[str, object], root: Path
) -> None:
    _write_text_atomic(
        path,
        f"{json.dumps(value, indent=2, sort_keys=True)}\n",
        root,
        replace_existing=True,
    )


def _write_text_once(path: Path, text: str, root: Path) -> None:
    _write_text_atomic(path, text, root, replace_existing=False)


def _retained_workspace_error(path: Path) -> ResultArtifactError:
    return ResultArtifactError(
        f"cannot initialize result workspace; retained partial state at {path}"
    )


def _write_text_atomic(
    path: Path,
    text: str,
    root: Path,
    *,
    replace_existing: bool,
) -> None:
    _ensure_safe_artifact_path(root, path)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        if replace_existing:
            if path.is_symlink():
                raise ResultArtifactError(f"artifact target must not be a symlink: {path}")
            os.replace(temporary_path, path)
        else:
            os.link(temporary_path, path)
    except FileExistsError as error:
        raise ResultArtifactError(f"result artifact already exists: {path}") from error
    except ResultArtifactError:
        raise
    except OSError as error:
        raise ResultArtifactError(f"cannot write result artifact {path}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _ensure_safe_artifact_path(root: Path, path: Path) -> None:
    if path.is_symlink():
        raise ResultArtifactError(f"artifact path must not be a symlink: {path}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved_parent = path.parent.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ResultArtifactError(f"cannot resolve artifact path {path}") from error
    if not resolved_parent.is_relative_to(resolved_root):
        raise ResultArtifactError(f"artifact path escapes result workspace: {path}")


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must include timezone information")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_execution_trace(
    execution_trace: Sequence[Mapping[str, object]],
) -> str:
    try:
        return "".join(
            f"{json.dumps(dict(event), sort_keys=True)}\n"
            for event in execution_trace
        )
    except (TypeError, ValueError) as error:
        raise ResultArtifactError("cannot serialize normalized execution trace") from error


def _safe_validation_path(path: Sequence[object]) -> str:
    safe_fields = {
        "schema_version",
        "run_id",
        "skill_name",
        "case_id",
        "run_kind",
        "grader",
        "type",
        "model",
        "reasoning_effort",
        "prompt_version",
        "graded_at",
        "assertion_results",
        "id",
        "kind",
        "text",
        "passed",
        "checked_by",
        "evidence",
        "evidence_refs",
        "artifact",
        "locator",
        "summary",
        "aggregation",
        "group_id",
        "variant",
        "contributes_to_outcome",
        "required_variants",
        "compare_to",
        "source_summaries",
        "groups",
        "variants",
        "comparisons",
    }
    rendered = "$"
    for component in path:
        if isinstance(component, int):
            rendered += f"[{component}]"
        elif component in safe_fields:
            rendered += f".{component}"
        else:
            rendered += ".<property>"
    return rendered
