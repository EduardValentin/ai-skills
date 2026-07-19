"""Shared, runner-neutral mechanics for durable LLM-backed evaluation results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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


class ResultArtifactError(RuntimeError):
    """Raised when preserved evaluation evidence cannot be trusted."""

    exit_code = 2


@dataclass(frozen=True)
class ArtifactPaths:
    """Canonical paths for one durable evaluation result workspace."""

    root: Path
    response: Path
    transcript: Path
    execution_trace: Path
    timing: Path
    grading: Path
    manual_grading: Path
    feedback: Path
    benchmark: Path


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
    prompt_version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "model": self.model,
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

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "group_id": self.group_id,
            "variant": self.variant,
            "contributes_to_outcome": self.contributes_to_outcome,
            "required_variants": list(self.required_variants),
        }
        if self.compare_to is not None:
            value["compare_to"] = self.compare_to
        return value


@dataclass(frozen=True)
class JudgeGradingContext:
    """Caller-owned grading identity, scope, and aggregation policy."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    prompt_version: str
    graded_at: str
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

    def to_dict(self) -> dict[str, object]:
        return {
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


def create_result_workspace(
    command: str,
    *,
    results_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    now: datetime | None = None,
) -> ArtifactPaths:
    """Create one durable result workspace and return all canonical paths."""
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
    try:
        root.mkdir(parents=True, exist_ok=False)
        outputs = root / "outputs"
        outputs.mkdir()
    except FileExistsError as error:
        raise ResultArtifactError(f"result workspace already exists: {root}") from error
    except OSError as error:
        raise ResultArtifactError(f"cannot create result workspace {root}: {error}") from error
    return ArtifactPaths(
        root=root,
        response=outputs / "response.md",
        transcript=root / "transcript.md",
        execution_trace=root / "execution_trace.jsonl",
        timing=root / "timing.json",
        grading=root / "grading.json",
        manual_grading=root / "manual_grading.json",
        feedback=root / "feedback.json",
        benchmark=root / "benchmark.json",
    )


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
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise ResultArtifactError(f"invalid {schema_name} result: {error}") from error


def write_eval_run_artifacts(paths: ArtifactPaths, record: EvalRunRecord) -> None:
    """Write one complete generated run without touching manual review artifacts."""
    timing = record.timing.to_dict()
    grading = record.grading.to_dict()
    validate_result_document(timing, "timing.schema.json")
    validate_result_document(grading, "grading.schema.json")

    trace_text = "".join(
        f"{json.dumps(dict(event), sort_keys=True)}\n" for event in record.execution_trace
    )
    _write_json_once(paths.timing, timing, paths.root)
    _write_text_once(paths.response, record.response, paths.root)
    _write_text_once(paths.transcript, record.transcript, paths.root)
    _write_text_once(paths.execution_trace, trace_text, paths.root)
    _write_json_once(paths.grading, grading, paths.root)


def parse_judge_response(
    response: str,
    context: JudgeGradingContext,
    *,
    model: str | None = None,
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
        if not isinstance(raw_references, list):
            raise ResultArtifactError(
                "invalid judge response: evidence_refs must be an array"
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
        raise ResultArtifactError("judge execution timed out")
    if execution.failure:
        raise ResultArtifactError(f"judge execution failed: {execution.failure}")
    if execution.exit_code != 0:
        raise ResultArtifactError(f"judge execution failed with exit code {execution.exit_code}")
    if execution.model is None or execution.reasoning_effort is None:
        raise ResultArtifactError(
            "judge execution did not report model and reasoning metadata"
        )

    return JudgeInvocationResult(
        grading=parse_judge_response(
            execution.response,
            context,
            model=execution.model,
        ),
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


def aggregate_results(results_dir: Path, grade_source: str) -> dict[str, object]:
    """Aggregate preserved grades using only caller-provided generic metadata."""
    if grade_source not in ("judge", "manual", "both"):
        raise ResultArtifactError(
            "grade_source must be one of 'judge', 'manual', or 'both'"
        )
    root = results_dir.resolve()
    if not root.is_dir():
        raise ResultArtifactError(f"results directory does not exist: {results_dir}")

    timing_paths = sorted(root.rglob("timing.json"))
    generated_paths = sorted(root.rglob("grading.json"))
    if not timing_paths:
        raise ResultArtifactError(f"no timing.json attempt artifacts found under {results_dir}")
    timing_parents = {path.parent for path in timing_paths}
    grading_parents = {path.parent for path in generated_paths}
    if extra_grades := sorted(grading_parents - timing_parents):
        raise ResultArtifactError(
            f"generated grading.json has no timing.json attempt artifact: {extra_grades[0]}"
        )

    requested_sources = ("judge", "manual") if grade_source == "both" else (grade_source,)
    preserved: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = {
        source: [] for source in requested_sources
    }
    for timing_path in timing_paths:
        timing = _read_result_document(timing_path, "timing.schema.json", root)
        generated_path = timing_path.with_name("grading.json")
        generated = _read_result_document(generated_path, "grading.schema.json", root)
        _validate_grading_semantics(generated, expected_source="judge")
        _validate_matching_timing(generated, timing, timing_path)
        if timing["status"] != "completed":
            raise ResultArtifactError(
                f"run {generated['run_id']} is not trustworthy: timing status is {timing['status']}"
            )

        if "judge" in preserved:
            preserved["judge"].append((generated, timing))
        if "manual" in preserved:
            manual_path = generated_path.with_name("manual_grading.json")
            manual = _read_result_document(manual_path, "grading.schema.json", root)
            _validate_grading_semantics(manual, expected_source="manual")
            _validate_complete_manual_override(generated, manual, manual_path)
            preserved["manual"].append((manual, timing))

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
    return "\n".join(lines)


def _aggregate_source(
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> dict[str, object]:
    grouped: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = defaultdict(list)
    contributing: list[dict[str, object]] = []
    for grading, timing in records:
        grouped[grading["aggregation"]["group_id"]].append((grading, timing))
        if grading["aggregation"]["contributes_to_outcome"]:
            contributing.append(grading)

    groups = [_aggregate_group(group_id, grouped[group_id]) for group_id in sorted(grouped)]
    passed_cases = sum(_grading_passed(grading) for grading in contributing)
    total_cases = len(contributing)
    return {
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": total_cases - passed_cases,
            "pass_rate": passed_cases / total_cases if total_cases else 0.0,
        },
        "groups": groups,
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


def _validate_matching_timing(
    grading: Mapping[str, object], timing: Mapping[str, object], timing_path: Path
) -> None:
    for field in ("run_id", "skill_name", "case_id", "run_kind"):
        if grading[field] != timing[field]:
            raise ResultArtifactError(
                f"timing identity does not match grading in {timing_path}: {field}"
            )
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


def _grading_record_from_dict(document: Mapping[str, object]) -> GradingRecord:
    grader = document["grader"]
    aggregation = document["aggregation"]
    summary = document["summary"]
    return GradingRecord(
        run_id=document["run_id"],
        skill_name=document["skill_name"],
        case_id=document["case_id"],
        run_kind=document["run_kind"],
        grade_source=document["grade_source"],
        grader=GraderRecord(
            type=grader["type"],
            model=grader["model"],
            prompt_version=grader["prompt_version"],
        ),
        graded_at=document["graded_at"],
        assertion_results=tuple(
            AssertionResult(
                id=result["id"],
                kind=result["kind"],
                text=result["text"],
                passed=result["passed"],
                checked_by=result["checked_by"],
                evidence=result["evidence"],
                evidence_refs=tuple(result["evidence_refs"]),
            )
            for result in document["assertion_results"]
        ),
        summary=GradingSummary(
            passed=summary["passed"],
            failed=summary["failed"],
            total=summary["total"],
            pass_rate=summary["pass_rate"],
        ),
        aggregation=AggregationMetadata(
            group_id=aggregation["group_id"],
            variant=aggregation["variant"],
            contributes_to_outcome=aggregation["contributes_to_outcome"],
            required_variants=tuple(aggregation["required_variants"]),
            compare_to=aggregation.get("compare_to"),
        ),
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
    resolved_root = root.resolve()
    if path.is_symlink():
        raise ResultArtifactError(f"artifact path must not be a symlink: {path}")
    try:
        resolved_parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise ResultArtifactError(f"cannot resolve artifact path {path}: {error}") from error
    if not resolved_parent.is_relative_to(resolved_root):
        raise ResultArtifactError(f"artifact path escapes result workspace: {path}")


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must include timezone information")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
