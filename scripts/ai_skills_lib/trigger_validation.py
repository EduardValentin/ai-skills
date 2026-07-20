"""Trigger definition validation and installed-catalog pickup evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Literal
import uuid

from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.eval_core import (
    AggregationMetadata,
    AssertionResult,
    AttemptManifest,
    EvalRunRecord,
    GraderRecord,
    GradingRecord,
    GradingSummary,
    ResultArtifactError,
    ResultWorkspace,
    aggregate_results,
    create_attempt_workspace,
    create_result_workspace,
    declare_invocation,
    record_harness_timing,
    write_eval_run_artifacts,
    write_incomplete_attempt_artifacts,
    write_result_summary,
)
from scripts.ai_skills_lib.harness import HarnessAdapter, HarnessExecution, HarnessRequest
from scripts.ai_skills_lib.issues import ValidationIssue, print_grouped_issues
from scripts.ai_skills_lib.secret_patterns import bounded_redacted_runtime_text
from scripts.ai_skills_lib.static_validation import run_static_validation
from scripts.ai_skills_lib.trigger_definitions import (
    SkillTriggerQueries,
    TriggerDefinitionError,
    TriggerQuery,
    load_trigger_queries,
    validate_trigger_query_files,
)


@dataclass(frozen=True)
class TriggerAttemptOutcome:
    """The deterministic pickup decision, or execution error, for one actor run."""

    activated: bool | None
    matched_expectation: bool | None
    error: str | None = None
    run_number: int | None = None
    artifact_dir: Path | None = None


@dataclass(frozen=True)
class TriggerQueryClassification:
    """Threshold classification across every configured run of one query."""

    status: Literal["pass_stable", "pass_unstable", "fail", "error"]
    matching_runs: int
    completed_runs: int
    configured_runs: int


@dataclass(frozen=True)
class TriggerQueryResult:
    """Aggregate pickup outcome for one authored query."""

    skill_name: str
    query_id: str
    should_trigger: bool
    classification: TriggerQueryClassification
    attempts: tuple[TriggerAttemptOutcome, ...]


@dataclass(frozen=True)
class TriggerSuiteResult:
    """Command-level trigger result with an explicit exit contract."""

    query_results: tuple[TriggerQueryResult, ...]

    @property
    def exit_code(self) -> int:
        if any(result.classification.status == "error" for result in self.query_results):
            return 2
        if any(result.classification.status == "fail" for result in self.query_results):
            return 1
        return 0


class TriggerHarnessError(RuntimeError):
    """Raised when the selected harness cannot produce trustworthy pickup evidence."""


def classify_trigger_attempts(
    attempts: Sequence[TriggerAttemptOutcome],
    configured_runs: int,
) -> TriggerQueryClassification:
    """Apply the repository's explicit one-, two-, or three-run trigger policy."""
    if configured_runs not in (1, 2, 3):
        raise ValueError("configured trigger runs must be 1, 2, or 3")
    if len(attempts) != configured_runs:
        raise ValueError("trigger classification requires every configured attempt")
    completed = [attempt for attempt in attempts if attempt.error is None]
    matching_runs = sum(attempt.matched_expectation is True for attempt in completed)
    if len(completed) != configured_runs:
        status = "error"
    elif matching_runs == configured_runs:
        status = "pass_stable"
    elif configured_runs == 3 and matching_runs == 2:
        status = "pass_unstable"
    else:
        status = "fail"
    return TriggerQueryClassification(
        status=status,
        matching_runs=matching_runs,
        completed_runs=len(completed),
        configured_runs=configured_runs,
    )


def execute_trigger_queries(
    root: Path,
    adapter: HarnessAdapter,
    workspace: ResultWorkspace,
    *,
    runs: int,
    max_concurrency: int,
    actor_timeout_seconds: int = 900,
    skill_filter: str | None = None,
    query_filter: str | None = None,
) -> TriggerSuiteResult:
    """Load the validated catalog and run selected trigger cases."""
    _validate_trigger_execution_options(runs, max_concurrency, actor_timeout_seconds)
    return _execute_trigger_queries(
        root,
        adapter,
        workspace,
        definitions=load_trigger_queries(root),
        runs=runs,
        max_concurrency=max_concurrency,
        actor_timeout_seconds=actor_timeout_seconds,
        skill_filter=skill_filter,
        query_filter=query_filter,
    )


def _execute_trigger_queries(
    root: Path,
    adapter: HarnessAdapter,
    workspace: ResultWorkspace,
    *,
    definitions: tuple[SkillTriggerQueries, ...],
    runs: int,
    max_concurrency: int,
    actor_timeout_seconds: int,
    skill_filter: str | None,
    query_filter: str | None,
) -> TriggerSuiteResult:
    """Run selected trigger cases from one already validated full catalog."""
    _validate_trigger_execution_options(runs, max_concurrency, actor_timeout_seconds)
    loaded_definitions = definitions
    selected = _select_trigger_queries(loaded_definitions, skill_filter, query_filter)
    if not selected:
        raise TriggerDefinitionError(
            (
                ValidationIssue(
                    scope="trigger selection",
                    message="no trigger queries match the selected filters",
                ),
            )
        )
    minimum_pass_rate = 2 / 3 if runs == 3 else 1.0
    jobs = tuple(
        (
            definition,
            query,
            run_number,
            _trigger_attempt_manifest(
                definition.skill,
                query,
                run_number,
                runs,
                minimum_pass_rate,
            ),
        )
        for definition, query in selected
        for run_number in range(1, runs + 1)
    )
    declare_invocation(
        workspace,
        "validate triggers",
        tuple(job[3] for job in jobs),
    )

    capabilities = adapter.preflight(require_fixtures=False)
    if not capabilities.available:
        raise TriggerHarnessError(capabilities.failure or "selected harness is unavailable")
    if not capabilities.reports_successful_skill_reads:
        raise TriggerHarnessError(
            "selected harness does not expose deterministic successful skill-read evidence"
        )

    catalog = tuple(definition.skill.root for definition in loaded_definitions)
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        attempt_outcomes = tuple(
            executor.map(
                lambda job: _execute_trigger_attempt(
                    adapter,
                    workspace,
                    catalog,
                    job[0].skill,
                    job[1],
                    job[3],
                    capabilities.harness_name,
                    actor_timeout_seconds,
                ),
                jobs,
            )
        )

    outcomes_by_query: dict[tuple[str, str], list[TriggerAttemptOutcome]] = {}
    for (definition, query, _, _), outcome in zip(jobs, attempt_outcomes, strict=True):
        outcomes_by_query.setdefault((definition.skill.name, query.id), []).append(outcome)
    query_results = tuple(
        TriggerQueryResult(
            skill_name=definition.skill.name,
            query_id=query.id,
            should_trigger=query.should_trigger,
            classification=classify_trigger_attempts(
                outcomes_by_query[(definition.skill.name, query.id)],
                runs,
            ),
            attempts=tuple(outcomes_by_query[(definition.skill.name, query.id)]),
        )
        for definition, query in selected
    )
    return TriggerSuiteResult(query_results=query_results)


def _validate_trigger_execution_options(
    runs: int,
    max_concurrency: int,
    actor_timeout_seconds: int,
) -> None:
    if runs not in (1, 2, 3):
        raise ValueError("trigger runs must be 1, 2, or 3")
    if max_concurrency not in (1, 2, 3, 4):
        raise ValueError("maximum trigger concurrency must be between 1 and 4")
    if actor_timeout_seconds <= 0:
        raise ValueError("actor timeout must be positive")


def run_trigger_query_harness(
    root: Path,
    *,
    harness: str,
    runs: int,
    skill_filter: str | None,
    query_filter: str | None,
    results_dir: Path | None,
    max_concurrency: int,
) -> int:
    """Validate, announce, execute, aggregate, and summarize one trigger invocation."""
    static_issues = run_static_validation(root)
    if static_issues:
        print_grouped_issues(static_issues)
        print("validate triggers: INVALID STATIC CONTRACT")
        return 2
    try:
        definitions = load_trigger_queries(root)
        selected = _select_trigger_queries(definitions, skill_filter, query_filter)
        if not selected:
            raise TriggerDefinitionError(
                (
                    ValidationIssue(
                        scope="trigger selection",
                        message="no trigger queries match the selected filters",
                    ),
                )
            )
        workspace = create_result_workspace(
            "validate-triggers",
            results_dir=results_dir,
            repository_root=root,
        )
    except TriggerDefinitionError as error:
        print_grouped_issues(error.issues)
        print("validate triggers: INVALID DEFINITIONS")
        return 2
    except ResultArtifactError as error:
        print(f"validate triggers: FAILED: {error}")
        return 2

    actor_runs = len(selected) * runs
    selected_skill_count = len({definition.skill.name for definition, _ in selected})
    print(
        "trigger plan: "
        f"skills={selected_skill_count} catalog_skills={len(definitions)} "
        f"queries={len(selected)} actor_runs={actor_runs} judge_runs=0 "
        f"preflight_calls=1 max_concurrency={max_concurrency} results={workspace.root}"
    )
    if harness != "codex":
        failure = "Claude trigger evidence is not implemented"
        summary_failure = _persist_terminal_trigger_summary(
            workspace,
            decision="execution error",
            failure=failure,
        )
        if summary_failure is not None:
            failure = f"{failure}\nresult summary failed: {summary_failure}"
        print(f"validate triggers: FAILED: {failure}")
        _print_results_path(workspace)
        return 2

    from scripts.ai_skills_lib.codex_harness import CodexHarnessAdapter, CodexOutputError
    from scripts.ai_skills_lib.sandbox_runtime import (
        EvalRuntimeManifest,
        SandboxRuntime,
        SandboxRuntimeError,
        SubprocessRunner,
    )

    staging_root = workspace.root.parent / f".ai-skills-workers-{uuid.uuid4().hex[:12]}"
    runtime: SandboxRuntime | None = None
    result: TriggerSuiteResult | None = None
    failure: str | None = None
    cleanup_succeeded = False
    try:
        manifest = EvalRuntimeManifest.load(root / "config" / "eval-runtime.json")
        runtime = SandboxRuntime(
            manifest=manifest,
            process=SubprocessRunner(manifest.limits.maximum_captured_output_bytes),
            repository_root=root,
            results_root=workspace.root,
            staging_root=staging_root,
            invocation_id=f"triggers-{uuid.uuid4().hex[:10]}",
            max_concurrency=max_concurrency,
        )
        adapter = CodexHarnessAdapter(runtime, allowed_skill_root=root / "skills")
        result = _execute_trigger_queries(
            root,
            adapter,
            workspace,
            definitions=definitions,
            runs=runs,
            max_concurrency=max_concurrency,
            actor_timeout_seconds=manifest.limits.actor_timeout_seconds,
            skill_filter=skill_filter,
            query_filter=query_filter,
        )
    except (
        OSError,
        CodexOutputError,
        ResultArtifactError,
        SandboxRuntimeError,
        TriggerDefinitionError,
        TriggerHarnessError,
        ValueError,
    ) as error:
        failure = str(error)
    finally:
        if runtime is not None:
            try:
                runtime.close()
                cleanup_succeeded = True
            except Exception as error:
                failure = "\n".join(
                    part for part in (failure, f"sandbox cleanup failed: {error}") if part
                )
        if (cleanup_succeeded or runtime is None) and staging_root.exists():
            try:
                shutil.rmtree(staging_root)
            except OSError as error:
                failure = "\n".join(
                    part
                    for part in (failure, f"worker staging cleanup failed: {error}")
                    if part
                )

    if failure is not None or result is None:
        failure = failure or "trigger execution did not complete"
        summary_failure = _persist_terminal_trigger_summary(
            workspace,
            decision="execution error",
            result=result,
            failure=failure,
        )
        if summary_failure is not None:
            failure = f"{failure}\nresult summary failed: {summary_failure}"
        print(f"validate triggers: FAILED: {failure}")
        _print_results_path(workspace)
        return 2
    if result.exit_code != 2:
        try:
            aggregate_results(workspace.root, "judge", repository_root=root)
        except ResultArtifactError as error:
            failure = f"aggregation failed: {error}"
            summary_failure = _persist_terminal_trigger_summary(
                workspace,
                decision="execution error",
                result=result,
                failure=failure,
            )
            if summary_failure is not None:
                failure = f"{failure}\nresult summary failed: {summary_failure}"
            print(f"validate triggers: FAILED: {failure}")
            _print_results_path(workspace)
            return 2
    else:
        summary_failure = _persist_terminal_trigger_summary(
            workspace,
            decision="execution error",
            result=result,
        )
        if summary_failure is not None:
            print(f"validate triggers: FAILED: result summary failed: {summary_failure}")
            _print_results_path(workspace)
            return 2
    print(format_trigger_summary(result))
    _print_results_path(workspace)
    if result.exit_code == 0:
        print("validate triggers: OK")
    elif result.exit_code == 1:
        print("validate triggers: EXPECTATIONS FAILED")
    else:
        print("validate triggers: EXECUTION ERROR")
    return result.exit_code


def _print_results_path(workspace: ResultWorkspace) -> None:
    print(f"Results: {workspace.root}")


def _persist_terminal_trigger_summary(
    workspace: ResultWorkspace,
    *,
    decision: str,
    result: TriggerSuiteResult | None = None,
    failure: str | None = None,
) -> str | None:
    lines = [
        "# Trigger Evaluation",
        "",
        f"Decision: {decision}",
    ]
    if failure is not None:
        lines.extend(
            (
                "",
                "## Error",
                "",
                bounded_redacted_runtime_text(failure, 4096),
            )
        )
    if result is not None:
        details = format_trigger_summary(result)
        if details:
            lines.extend(("", "## Query Results", "", details))
    else:
        lines.extend(("", "No trigger attempt completed."))
    if not workspace.benchmark.exists():
        lines.extend(
            (
                "",
                "`benchmark.json` was not generated because the result set was not "
                "complete and trustworthy.",
            )
        )
    try:
        write_result_summary(workspace, "\n".join(lines))
    except ResultArtifactError as error:
        return str(error)
    return None


def format_trigger_summary(result: TriggerSuiteResult) -> str:
    """Render stable, unstable, failed, and errored query outcomes for humans."""
    lines: list[str] = []
    for query_result in result.query_results:
        classification = query_result.classification
        suffix = " INVESTIGATE" if classification.status == "pass_unstable" else ""
        lines.append(
            f"{query_result.skill_name}/{query_result.query_id}: "
            f"{classification.status} "
            f"({classification.matching_runs}/{classification.configured_runs} matched)"
            f"{suffix}"
        )
        for attempt in query_result.attempts:
            if attempt.error is None and attempt.matched_expectation is not False:
                continue
            state = "error" if attempt.error is not None else "mismatch"
            detail = (
                attempt.error
                if attempt.error is not None
                else f"activated={str(attempt.activated).lower()}"
            )
            artifact = (
                f" artifacts={attempt.artifact_dir}"
                if attempt.artifact_dir is not None
                else ""
            )
            lines.append(
                f"  run {attempt.run_number}: {state}: {detail}{artifact}"
            )
    return "\n".join(lines)


def _select_trigger_queries(
    definitions: Sequence[SkillTriggerQueries],
    skill_filter: str | None,
    query_filter: str | None,
) -> tuple[tuple[SkillTriggerQueries, TriggerQuery], ...]:
    return tuple(
        (definition, query)
        for definition in definitions
        for query in definition.queries
        if (skill_filter is None or definition.skill.name == skill_filter)
        and (query_filter is None or query.id == query_filter)
    )


def _execute_trigger_attempt(
    adapter: HarnessAdapter,
    workspace: ResultWorkspace,
    catalog: tuple[Path, ...],
    skill: SkillRecord,
    query: TriggerQuery,
    manifest: AttemptManifest,
    harness_name: str,
    actor_timeout_seconds: int,
) -> TriggerAttemptOutcome:
    run_id = manifest.run_id
    aggregation = manifest.aggregation
    run_number = aggregation.run_number
    assert run_number is not None
    paths = create_attempt_workspace(
        workspace,
        manifest,
    )
    request = HarnessRequest(
        role="actor",
        run_variant=run_id,
        prompt=query.query,
        timeout_seconds=actor_timeout_seconds,
        skill_sources=catalog,
        expected_skill=skill.name,
    )
    started_at = datetime.now(timezone.utc)
    try:
        execution = adapter.execute(request, paths.root)
    except Exception as error:
        diagnostic = bounded_redacted_runtime_text(str(error), 4096)
        ended_at = datetime.now(timezone.utc)
        execution = HarnessExecution(
            response="",
            trace=({"type": "harness_error", "message": diagnostic},),
            duration_ms=max(0, round((ended_at - started_at).total_seconds() * 1000)),
            total_tokens=None,
            input_tokens=None,
            output_tokens=None,
            cached_tokens=None,
            token_source="unavailable",
            successful_skill_reads=(),
            exit_code=None,
            failure=diagnostic or type(error).__name__,
            model=None,
            reasoning_effort=None,
            timed_out=False,
        )
    if (
        not execution.timed_out
        and execution.failure is None
        and execution.exit_code == 0
        and not _has_trustworthy_expected_skill_path(execution, skill.name)
    ):
        diagnostic = "harness did not prove the expected installed SKILL.md path"
        execution = replace(
            execution,
            trace=(*execution.trace, {"type": "evidence_error", "message": diagnostic}),
            failure=diagnostic,
        )
    ended_at = datetime.now(timezone.utc)
    timing = record_harness_timing(
        run_id=run_id,
        skill_name=skill.name,
        case_id=query.id,
        run_kind="trigger",
        harness_name=harness_name,
        started_at=started_at,
        ended_at=ended_at,
        execution=execution,
    )
    durable_response = bounded_redacted_runtime_text(execution.response, 65536)
    transcript = _trigger_transcript(query, execution)
    if timing.status != "completed":
        write_incomplete_attempt_artifacts(
            paths,
            response=durable_response,
            transcript=transcript,
            execution_trace=execution.trace,
            timing=timing,
        )
        return TriggerAttemptOutcome(
            activated=None,
            matched_expectation=None,
            error=execution.failure or f"harness timing status is {timing.status}",
            run_number=run_number,
            artifact_dir=paths.root,
        )

    expected_skill_path = execution.expected_skill_path
    assert expected_skill_path is not None
    activated = expected_skill_path in execution.successful_skill_reads
    matched = activated is query.should_trigger
    evidence = _trigger_evidence(skill.name, activated, execution)
    assertion = AssertionResult(
        id="expected-skill-activation",
        kind="trigger",
        text=(
            f"The installed harness {'loads' if query.should_trigger else 'does not load'} "
            f"the {skill.name} skill."
        ),
        passed=matched,
        checked_by="trigger_runner",
        evidence=evidence,
        evidence_refs=(
            {
                "artifact": "execution_trace.jsonl",
                "locator": (
                    "exact successful installed SKILL.md read"
                    if activated
                    else "absence of an exact successful installed SKILL.md read"
                ),
            },
        ),
    )
    grading = GradingRecord(
        run_id=run_id,
        skill_name=skill.name,
        case_id=query.id,
        run_kind="trigger",
        grade_source="judge",
        grader=GraderRecord(
            type="deterministic",
            model=None,
            reasoning_effort=None,
            prompt_version="trigger-runner-v1",
        ),
        graded_at=_timestamp(datetime.now(timezone.utc)),
        assertion_results=(assertion,),
        summary=GradingSummary(
            passed=int(matched),
            failed=int(not matched),
            total=1,
            pass_rate=float(matched),
        ),
        aggregation=aggregation,
        measurements={"trigger_rate": float(activated)},
    )
    write_eval_run_artifacts(
        paths,
        EvalRunRecord(
            response=durable_response,
            transcript=transcript,
            execution_trace=execution.trace,
            timing=timing,
            grading=grading,
        ),
    )
    return TriggerAttemptOutcome(
        activated=activated,
        matched_expectation=matched,
        run_number=run_number,
        artifact_dir=paths.root,
    )


def _trigger_attempt_manifest(
    skill: SkillRecord,
    query: TriggerQuery,
    run_number: int,
    configured_runs: int,
    minimum_pass_rate: float,
) -> AttemptManifest:
    return AttemptManifest(
        run_id=f"{skill.name}-{query.id}-run-{run_number}",
        skill_name=skill.name,
        case_id=query.id,
        run_kind="trigger",
        aggregation=AggregationMetadata(
            group_id=f"{skill.name}/{query.id}",
            variant="installed_harness",
            contributes_to_outcome=True,
            required_variants=("installed_harness",),
            minimum_pass_rate=minimum_pass_rate,
            configured_runs=configured_runs,
            run_number=run_number,
        ),
    )


def _trigger_transcript(query: TriggerQuery, execution: HarnessExecution) -> str:
    expectation = "load the skill" if query.should_trigger else "leave the skill unselected"
    durable_query = bounded_redacted_runtime_text(query.query, 16384)
    durable_response = bounded_redacted_runtime_text(execution.response, 65536)
    return (
        "# Trigger Query\n\n"
        f"{durable_query}\n\n"
        "# Expected Pickup\n\n"
        f"{expectation}\n\n"
        "# Harness Response\n\n"
        f"{durable_response}\n"
    )


def _has_trustworthy_expected_skill_path(
    execution: HarnessExecution,
    skill_name: str,
) -> bool:
    path = execution.expected_skill_path
    return bool(
        path is not None
        and path.is_absolute()
        and path.name == "SKILL.md"
        and path.parent.name == skill_name
    )


def _trigger_evidence(
    skill_name: str,
    activated: bool,
    execution: HarnessExecution,
) -> str:
    if not activated:
        return f"No successful exact installed SKILL.md read was recorded for {skill_name}."
    path = execution.expected_skill_path
    assert path is not None
    return f"The harness recorded a successful exact installed SKILL.md read at {path}."


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
