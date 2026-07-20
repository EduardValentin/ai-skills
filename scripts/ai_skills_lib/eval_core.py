"""Shared, runner-neutral mechanics for durable LLM-backed evaluation results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from scripts.ai_skills_lib.harness import (
    HarnessAdapter,
    HarnessExecution,
    HarnessRequest,
)


_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "ai-skills"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ResultArtifactError(RuntimeError):
    """Raised when preserved evaluation evidence cannot be trusted."""

    exit_code = 2


class JudgeExecutionError(ResultArtifactError):
    """Raised with complete normalized evidence from an untrusted judge execution."""

    def __init__(self, message: str, execution: HarnessExecution):
        super().__init__(message)
        self.execution = execution


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
        raise ResultArtifactError(f"cannot resolve result path: {error}") from error
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
        attempts = root / "attempts"
        attempts.mkdir()
    except FileExistsError as error:
        raise ResultArtifactError(f"result workspace already exists: {root}") from error
    except OSError as error:
        raise ResultArtifactError(f"cannot create result workspace {root}: {error}") from error
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
    if workspace.invocation_manifest.exists():
        invocation = _read_result_document(
            workspace.invocation_manifest,
            "invocation.schema.json",
            workspace.root,
        )
        declared = [
            attempt
            for attempt in invocation["attempts"]
            if attempt["run_id"] == manifest.run_id
        ]
        if declared != [document]:
            raise ResultArtifactError(
                "attempt does not match the immutable invocation manifest"
            )
    if workspace.root.is_symlink() or workspace.attempts.is_symlink():
        raise ResultArtifactError("invocation attempts directory must not be a symlink")
    try:
        invocation_root = workspace.root.resolve(strict=True)
        attempts_root = workspace.attempts.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ResultArtifactError(f"cannot resolve invocation attempts directory: {error}") from error
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
        raise ResultArtifactError(f"cannot create attempt workspace {root}: {error}") from error
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
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    except ValidationError as error:
        keyword = str(error.validator)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", keyword):
            keyword = "validation"
        raise ResultArtifactError(
            f"invalid {schema_name} result at {_safe_validation_path(error.absolute_path)}: "
            f"{keyword}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ResultArtifactError(f"cannot load offline schema {schema_name}: {error}") from error


def write_eval_run_artifacts(paths: AttemptPaths, record: EvalRunRecord) -> None:
    """Write one complete generated run without touching manual review artifacts."""
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
    try:
        document = json.loads(response)
    except json.JSONDecodeError as error:
        raise ResultArtifactError(f"invalid judge response JSON: {error}") from error
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
        if not isinstance(result["evidence"], str) or not result["evidence"]:
            raise ResultArtifactError(
                "invalid judge response: evidence must be a non-empty string"
            )
        raw_references = result["evidence_refs"]
        if not isinstance(raw_references, list) or not raw_references:
            raise ResultArtifactError(
                "invalid judge response: evidence_refs must contain evidence"
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
) -> dict[str, object]:
    """Aggregate only complete attempts anchored by immutable declarations."""
    if grade_source not in ("judge", "manual", "both"):
        raise ResultArtifactError(
            "grade_source must be one of 'judge', 'manual', or 'both'"
        )
    root = resolve_external_result_path(
        results_dir,
        repository_root=repository_root,
    )
    if not root.is_dir():
        raise ResultArtifactError(f"results directory does not exist: {results_dir}")
    attempts_root = root / "attempts"
    if attempts_root.is_symlink() or not attempts_root.is_dir():
        raise ResultArtifactError(f"results directory has no attempts: {results_dir}")
    invocation_path = root / "invocation.json"
    declared_attempts: dict[str, dict[str, object]] | None = None
    if invocation_path.exists() or invocation_path.is_symlink():
        invocation = _read_result_document(
            invocation_path,
            "invocation.schema.json",
            root,
        )
        declared_attempts = {}
        for attempt in invocation["attempts"]:
            run_id = attempt["run_id"]
            if run_id in declared_attempts:
                raise ResultArtifactError(
                    f"duplicate run_id in invocation manifest: {run_id}"
                )
            declared_attempts[run_id] = attempt

    try:
        attempt_entries = sorted(attempts_root.iterdir())
    except OSError as error:
        raise ResultArtifactError(f"cannot inventory attempt entries: {error}") from error
    manifest_paths: list[Path] = []
    for entry in attempt_entries:
        if entry.is_symlink():
            raise ResultArtifactError(f"attempt entry must not be a symlink: {entry}")
        if not entry.is_dir():
            raise ResultArtifactError(f"attempt entry must be a directory: {entry}")
        manifest_path = entry / "attempt.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ResultArtifactError(
                f"attempt entry must contain one readable attempt.json: {entry}"
            )
        nested_manifests = list(entry.rglob("attempt.json"))
        if nested_manifests != [manifest_path]:
            raise ResultArtifactError(
                f"attempt entry must contain exactly one attempt.json: {entry}"
            )
        manifest_paths.append(manifest_path)
    if not manifest_paths:
        raise ResultArtifactError(f"no attempt.json declarations found under {results_dir}")
    declared_parents = {path.parent for path in manifest_paths}
    for artifact_name in ("timing.json", "grading.json", "manual_grading.json"):
        for artifact_path in sorted(root.rglob(artifact_name)):
            if artifact_path.parent not in declared_parents:
                raise ResultArtifactError(
                    f"undeclared attempt artifact {artifact_name}: {artifact_path}"
                )

    requested_sources = ("judge", "manual") if grade_source == "both" else (grade_source,)
    preserved: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = {
        source: [] for source in requested_sources
    }
    run_ids: set[str] = set()
    thresholded_attempts = False
    for manifest_path in manifest_paths:
        manifest = _read_result_document(manifest_path, "attempt.schema.json", root)
        run_id = manifest["run_id"]
        if run_id in run_ids:
            raise ResultArtifactError(f"duplicate run_id in attempt manifests: {run_id}")
        run_ids.add(run_id)
        if declared_attempts is not None and declared_attempts.get(run_id) != manifest:
            raise ResultArtifactError(
                f"attempt does not match the immutable invocation manifest: {run_id}"
            )
        aggregation = manifest["aggregation"]
        thresholded_attempts = thresholded_attempts or (
            "minimum_pass_rate" in aggregation
        )
        if aggregation["variant"] not in aggregation["required_variants"]:
            raise ResultArtifactError(
                f"unexpected variant in attempt manifest: {aggregation['variant']}"
            )

        timing_path = manifest_path.with_name("timing.json")
        timing = _read_result_document(timing_path, "timing.schema.json", root)
        generated_path = timing_path.with_name("grading.json")
        generated = _read_result_document(generated_path, "grading.schema.json", root)
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
            manual_path = generated_path.with_name("manual_grading.json")
            manual = _read_result_document(manual_path, "grading.schema.json", root)
            _validate_grading_semantics(manual, expected_source="manual")
            _validate_artifact_matches_manifest(manual, manifest, manual_path)
            _validate_complete_manual_override(generated, manual, manual_path)
            preserved["manual"].append((manual, timing))

    if declared_attempts is not None and run_ids != set(declared_attempts):
        raise ResultArtifactError(
            "attempt set does not match the immutable invocation manifest"
        )
    if thresholded_attempts and declared_attempts is None:
        raise ResultArtifactError(
            "threshold aggregation requires an immutable invocation manifest"
        )

    benchmark: dict[str, object] = {
        "schema_version": "ai-skills.eval.benchmark.v1",
        "generated_at": _format_timestamp(datetime.now(timezone.utc)),
        "grade_source": grade_source,
        "source_summaries": {
            source: _aggregate_source(records) for source, records in preserved.items()
        },
    }
    validate_result_document(benchmark, "benchmark.schema.json")
    _write_json_atomic(root / "benchmark.json", benchmark, root)
    _write_text_atomic(
        root / "summary.md",
        f"{format_benchmark_summary(benchmark)}\n",
        root,
        replace_existing=True,
    )
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


def _read_result_document(
    path: Path, schema_name: str, root: Path
) -> dict[str, object]:
    _ensure_safe_artifact_path(root, path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ResultArtifactError(f"cannot read trustworthy result {path}: {error}") from error
    if not isinstance(document, dict):
        raise ResultArtifactError(f"result artifact must contain a JSON object: {path}")
    validate_result_document(document, schema_name)
    return document


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
        raise ResultArtifactError(f"cannot write result artifact {path}: {error}") from error
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
        raise ResultArtifactError(f"cannot resolve artifact path {path}: {error}") from error
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
