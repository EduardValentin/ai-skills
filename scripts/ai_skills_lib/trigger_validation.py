"""Trigger definition validation and installed-catalog pickup evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import scripts.ai_skills_lib.actor_evidence as actor_evidence
from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.eval_core import (
    AggregationMetadata,
    AssertionContract,
    AssertionResult,
    AttemptManifest,
    BoundPreflightReceipt,
    EvalRunRecord,
    GraderRecord,
    GradingRecord,
    GradingSummary,
    ResultArtifactError,
    ResultWorkspace,
    StructuredSkillPathKind,
    TerminalDecision as _TerminalDecision,
    aggregate_results,
    capabilities_from_preflight_receipt,
    canonical_document_sha256,
    classify_codex_skill_evidence_path,
    create_attempt_workspace,
    create_result_workspace,
    declare_invocation,
    enforce_execution_binding,
    enforce_execution_configuration,
    preflight_bound_invocations,
    record_harness_timing,
    resolve_terminal_decision as _resolve_terminal_decision,
    write_eval_run_artifacts,
    write_incomplete_attempt_artifacts,
    write_result_summary,
)
from scripts.ai_skills_lib.evaluation_runtime import CodexEvaluationRuntime
from scripts.ai_skills_lib.harness import (
    HarnessAdapter,
    HarnessArtifactBinding,
    HarnessExecution,
    HarnessRequest,
    PreparedSkillSource,
    bind_harness_request,
    validated_actor_skill_read_lifecycle,
)
from scripts.ai_skills_lib.issues import ValidationIssue, print_grouped_issues
from scripts.ai_skills_lib.secret_patterns import bounded_redacted_runtime_text
from scripts.ai_skills_lib.static_validation import run_pre_model_validation
from scripts.ai_skills_lib.trigger_definitions import (
    SkillTriggerQueries,
    TriggerDefinitionError,
    TriggerQuery,
    load_trigger_queries,
    validate_trigger_query_files,
)


_MAX_SELECTED_QUERIES = 128
_MAX_MODEL_CALLS = 384


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

    status: Literal["pass_stable", "pending_review", "fail", "error"]
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
    def requires_review(self) -> bool:
        return any(
            result.classification.status == "pending_review"
            for result in self.query_results
        )

    @property
    def has_failed_expectations(self) -> bool:
        return any(
            result.classification.status == "fail" for result in self.query_results
        )

    @property
    def exit_code(self) -> int:
        if any(result.classification.status == "error" for result in self.query_results):
            return 2
        if self.has_failed_expectations or self.requires_review:
            return 1
        return 0


@dataclass(frozen=True)
class TriggerFinalization:
    """Durable terminal state shared by standalone and combined trigger runners."""

    terminal: _TerminalDecision
    benchmark: dict[str, object] | None
    failures: tuple[str, ...] = ()


class TriggerHarnessError(RuntimeError):
    """Raised when the selected harness cannot produce trustworthy pickup evidence."""


@dataclass(frozen=True)
class PreparedTriggerAttempt:
    """One immutable trigger attempt selected before runtime preflight."""

    definition: SkillTriggerQueries
    query: TriggerQuery
    run_number: int
    manifest: AttemptManifest


@dataclass(frozen=True)
class PreparedTriggerPlan:
    """The exact trigger catalog, selection, and attempt set for one invocation."""

    definitions: tuple[SkillTriggerQueries, ...]
    selected: tuple[tuple[SkillTriggerQueries, TriggerQuery], ...]
    attempts: tuple[PreparedTriggerAttempt, ...]
    catalog: tuple[PreparedSkillSource, ...]
    runs: int

    def __post_init__(self) -> None:
        if not isinstance(self.catalog, tuple) or not all(
            isinstance(source, PreparedSkillSource) for source in self.catalog
        ):
            raise ValueError("prepared trigger catalog must contain prepared skill material")
        expected_names = tuple(definition.skill.name for definition in self.definitions)
        if tuple(source.name for source in self.catalog) != expected_names:
            raise ValueError("prepared trigger catalog must cover the complete catalog")

    @property
    def manifests(self) -> tuple[AttemptManifest, ...]:
        return tuple(attempt.manifest for attempt in self.attempts)


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
        status = "pending_review"
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
    preflight_receipt: BoundPreflightReceipt | None = None,
) -> TriggerSuiteResult:
    """Load the validated catalog and run selected trigger cases."""
    _validate_trigger_execution_options(runs, max_concurrency, actor_timeout_seconds)
    definitions = load_trigger_queries(root)
    return _execute_trigger_queries(
        root,
        adapter,
        workspace,
        definitions=definitions,
        runs=runs,
        max_concurrency=max_concurrency,
        actor_timeout_seconds=actor_timeout_seconds,
        skill_filter=skill_filter,
        query_filter=query_filter,
        preflight_receipt=preflight_receipt,
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
    preflight_receipt: BoundPreflightReceipt | None = None,
    prepared_plan: PreparedTriggerPlan | None = None,
    invocation_declared: bool = False,
) -> TriggerSuiteResult:
    """Run selected trigger cases from one already validated full catalog."""
    _validate_trigger_execution_options(runs, max_concurrency, actor_timeout_seconds)
    plan = prepared_plan or prepare_trigger_plan(
        definitions,
        runs=runs,
        skill_filter=skill_filter,
        query_filter=query_filter,
    )
    if plan.runs != runs:
        raise TriggerHarnessError("prepared trigger plan run count does not match execution")
    if not invocation_declared:
        declare_trigger_plan(workspace, plan)
    return execute_prepared_trigger_plan(
        adapter,
        workspace,
        plan,
        max_concurrency=max_concurrency,
        actor_timeout_seconds=actor_timeout_seconds,
        preflight_receipt=preflight_receipt,
    )


def prepare_trigger_plan(
    definitions: Sequence[SkillTriggerQueries],
    *,
    runs: int,
    skill_filter: str | None,
    query_filter: str | None,
) -> PreparedTriggerPlan:
    """Freeze one validated trigger selection and its exact attempt manifests."""
    if runs not in (1, 2, 3):
        raise ValueError("trigger runs must be 1, 2, or 3")
    loaded_definitions = tuple(definitions)
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
    _validate_selected_trigger_queries(selected, runs)
    from scripts.ai_skills_lib.codex_harness import (
        CodexOutputError,
        prepare_actor_skill_source,
    )

    try:
        catalog = tuple(
            prepare_actor_skill_source(definition.skill.root)
            for definition in loaded_definitions
        )
    except (CodexOutputError, OSError, RuntimeError) as error:
        diagnostic = bounded_redacted_runtime_text(str(error), 4096)
        raise TriggerHarnessError(
            f"trigger material preparation failed: {diagnostic}"
        ) from error
    minimum_pass_rate = 2 / 3 if runs == 3 else 1.0
    attempts = tuple(
        PreparedTriggerAttempt(
            definition=definition,
            query=query,
            run_number=run_number,
            manifest=_trigger_attempt_manifest(
                definition.skill,
                query,
                run_number,
                runs,
                minimum_pass_rate,
                runtime_input_sha256=_trigger_runtime_input_sha256(
                    definition.skill,
                    query,
                    catalog,
                ),
            ),
        )
        for definition, query in selected
        for run_number in range(1, runs + 1)
    )
    return PreparedTriggerPlan(
        definitions=loaded_definitions,
        selected=selected,
        attempts=attempts,
        catalog=catalog,
        runs=runs,
    )


def declare_trigger_plan(workspace: ResultWorkspace, plan: PreparedTriggerPlan) -> None:
    """Persist a prepared trigger plan before any runtime preflight."""
    _verify_trigger_plan_contract(plan)
    declare_invocation(workspace, "validate triggers", plan.manifests)


def execute_prepared_trigger_plan(
    adapter: HarnessAdapter,
    workspace: ResultWorkspace,
    plan: PreparedTriggerPlan,
    *,
    max_concurrency: int,
    actor_timeout_seconds: int,
    preflight_receipt: BoundPreflightReceipt | None = None,
) -> TriggerSuiteResult:
    """Execute exactly one already declared immutable trigger plan."""
    _validate_trigger_execution_options(
        plan.runs,
        max_concurrency,
        actor_timeout_seconds,
    )
    _verify_trigger_plan_inputs(plan)
    receipt = preflight_receipt or preflight_bound_invocations(
        adapter,
        ((workspace, "validate triggers", plan.manifests),),
        require_fixtures=False,
    )
    capabilities = capabilities_from_preflight_receipt(
        receipt,
        adapter,
        workspace,
        "validate triggers",
        plan.manifests,
        require_fixtures=False,
    )
    if not capabilities.available:
        raise TriggerHarnessError(capabilities.failure or "selected harness is unavailable")
    if not capabilities.reports_successful_skill_reads:
        raise TriggerHarnessError(
            "selected harness does not expose deterministic successful skill-read evidence"
        )
    if (
        capabilities.actor_model is None
        or capabilities.actor_reasoning_effort is None
    ):
        raise TriggerHarnessError(
            "selected harness preflight did not pin the actor model configuration"
        )

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        attempt_outcomes = tuple(
            executor.map(
                lambda attempt: _execute_trigger_attempt(
                    adapter,
                    workspace,
                    plan.catalog,
                    attempt.definition.skill,
                    attempt.query,
                    attempt.manifest,
                    capabilities.harness_name,
                    capabilities.actor_model,
                    capabilities.actor_reasoning_effort,
                    actor_timeout_seconds,
                ),
                plan.attempts,
            )
        )

    outcomes_by_query: dict[tuple[str, str], list[TriggerAttemptOutcome]] = {}
    for attempt, outcome in zip(plan.attempts, attempt_outcomes, strict=True):
        outcomes_by_query.setdefault(
            (attempt.definition.skill.name, attempt.query.id),
            [],
        ).append(outcome)
    query_results = tuple(
        TriggerQueryResult(
            skill_name=definition.skill.name,
            query_id=query.id,
            should_trigger=query.should_trigger,
            classification=classify_trigger_attempts(
                outcomes_by_query[(definition.skill.name, query.id)],
                plan.runs,
            ),
            attempts=tuple(outcomes_by_query[(definition.skill.name, query.id)]),
        )
        for definition, query in plan.selected
    )
    return TriggerSuiteResult(query_results=query_results)


def finalize_trigger_result(
    root: Path,
    workspace: ResultWorkspace,
    result: TriggerSuiteResult | None,
    *,
    execution_failure: str | None = None,
) -> TriggerFinalization:
    """Persist one trigger terminal state without escaping finalization failures."""
    if execution_failure is not None or result is None:
        failure = execution_failure or "trigger execution did not complete"
        terminal = _resolve_terminal_decision(
            execution_error=True,
            pending_review=False,
            expectation_failure=False,
        )
        summary_failure = _persist_terminal_trigger_summary(
            workspace,
            decision=terminal.durable_label,
            result=result,
            failure=failure,
        )
        failures = [failure]
        if summary_failure is not None:
            failures.append(f"result summary failed: {summary_failure}")
        return TriggerFinalization(
            terminal=terminal,
            benchmark=None,
            failures=tuple(failures),
        )

    terminal = _resolve_terminal_decision(
        execution_error=result.exit_code == 2,
        pending_review=result.requires_review,
        expectation_failure=result.has_failed_expectations,
    )
    if terminal.key in ("execution_error", "pending_review"):
        summary_failure = _persist_terminal_trigger_summary(
            workspace,
            decision=terminal.durable_label,
            result=result,
        )
        if summary_failure is None:
            return TriggerFinalization(terminal=terminal, benchmark=None)
        failure = f"result summary failed: {summary_failure}"
        return TriggerFinalization(
            terminal=_resolve_terminal_decision(
                execution_error=True,
                pending_review=result.requires_review,
                expectation_failure=result.has_failed_expectations,
            ),
            benchmark=None,
            failures=(failure,),
        )

    try:
        benchmark = aggregate_results(
            workspace.root,
            "judge",
            repository_root=root,
            terminal_decision=terminal.durable_label,
        )
    except Exception as error:
        failure = f"aggregation failed: {error}"
        summary_failure = _persist_terminal_trigger_summary(
            workspace,
            decision="execution error",
            result=result,
            failure=failure,
        )
        failures = [failure]
        if summary_failure is not None:
            failures.append(f"result summary failed: {summary_failure}")
        return TriggerFinalization(
            terminal=_resolve_terminal_decision(
                execution_error=True,
                pending_review=False,
                expectation_failure=result.has_failed_expectations,
            ),
            benchmark=None,
            failures=tuple(failures),
        )
    return TriggerFinalization(
        terminal=terminal,
        benchmark=benchmark,
    )


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
    try:
        validation_issues = run_pre_model_validation(root)
    except RuntimeError as error:
        print(f"validate triggers: DETERMINISTIC GATE FAILED: {error}")
        return 2
    if validation_issues:
        print_grouped_issues(validation_issues)
        print("validate triggers: INVALID DETERMINISTIC CONTRACT")
        return 2
    workspace: ResultWorkspace | None = None
    try:
        _validate_trigger_execution_options(runs, max_concurrency, 1)
        definitions = load_trigger_queries(root)
        plan = prepare_trigger_plan(
            definitions,
            runs=runs,
            skill_filter=skill_filter,
            query_filter=query_filter,
        )
        workspace = create_result_workspace(
            "validate-triggers",
            results_dir=results_dir,
            repository_root=root,
        )
        declare_trigger_plan(workspace, plan)
    except TriggerDefinitionError as error:
        print_grouped_issues(error.issues)
        print("validate triggers: INVALID DEFINITIONS")
        return 2
    except Exception as error:
        failure = str(error)
        if workspace is not None:
            finalization = finalize_trigger_result(
                root,
                workspace,
                None,
                execution_failure=failure,
            )
            failure = "\n".join(finalization.failures)
        print(
            "validate triggers: FAILED: "
            f"{bounded_redacted_runtime_text(failure, 4096)}"
        )
        if workspace is not None:
            _print_results_path(workspace)
            print(f"validate triggers: {finalization.terminal.console_label}")
        return 2

    actor_runs = len(plan.attempts)
    selected_skill_count = len(
        {definition.skill.name for definition, _ in plan.selected}
    )
    print(
        "trigger plan: "
        f"skills={selected_skill_count} catalog_skills={len(definitions)} "
        f"queries={len(plan.selected)} actor_runs={actor_runs} judge_runs=0 "
        f"preflight_calls=1 max_concurrency={max_concurrency} results={workspace.root}"
    )
    if harness != "codex":
        failure = "Claude trigger evidence is not implemented"
        finalization = finalize_trigger_result(
            root,
            workspace,
            None,
            execution_failure=failure,
        )
        failure = "\n".join(finalization.failures)
        print(f"validate triggers: FAILED: {failure}")
        _print_results_path(workspace)
        print(f"validate triggers: {finalization.terminal.console_label}")
        return finalization.terminal.exit_code

    session: CodexEvaluationRuntime | None = None
    result: TriggerSuiteResult | None = None
    failure: str | None = None
    try:
        session = CodexEvaluationRuntime.create(
            root,
            workspace.root,
            invocation_label="triggers",
            max_concurrency=max_concurrency,
        )
        result = _execute_trigger_queries(
            root,
            session.adapter,
            workspace,
            definitions=definitions,
            runs=runs,
            max_concurrency=max_concurrency,
            actor_timeout_seconds=session.manifest.limits.actor_timeout_seconds,
            skill_filter=skill_filter,
            query_filter=query_filter,
            prepared_plan=plan,
            invocation_declared=True,
        )
    except Exception as error:
        failure = str(error)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as error:
                failure = "\n".join(
                    part for part in (failure, str(error)) if part
                )

    finalization = finalize_trigger_result(
        root,
        workspace,
        result,
        execution_failure=failure,
    )
    if result is not None:
        print(format_trigger_summary(result))
    if finalization.failures:
        rendered_failures = "\n".join(finalization.failures)
        print(
            "validate triggers: FAILED: "
            f"{bounded_redacted_runtime_text(rendered_failures, 4096)}"
        )
    _print_results_path(workspace)
    print(f"validate triggers: {finalization.terminal.console_label}")
    return finalization.terminal.exit_code


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
        if result.requires_review:
            lines.extend(
                (
                    "",
                    "## Review Required",
                    "",
                    "A two-of-three query has one discordant failed run. Investigate "
                    "that run before explicitly aggregating these preserved attempts "
                    "as a trusted pass.",
                )
            )
    else:
        lines.extend(("", "No trigger attempt completed."))
    if not workspace.benchmark.exists():
        explanation = (
            "`benchmark.json` was not generated while human review is pending."
            if result is not None and result.requires_review
            else "`benchmark.json` was not generated because the result set was not "
            "complete and trustworthy."
        )
        lines.extend(("", explanation))
    try:
        write_result_summary(workspace, "\n".join(lines))
    except Exception as error:
        return bounded_redacted_runtime_text(str(error), 4096)
    return None


def format_trigger_summary(result: TriggerSuiteResult) -> str:
    """Render stable, review-pending, failed, and errored query outcomes."""
    lines: list[str] = []
    for query_result in result.query_results:
        classification = query_result.classification
        suffix = (
            " REVIEW REQUIRED: investigate the discordant failed run before aggregation"
            if classification.status == "pending_review"
            else ""
        )
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


def _validate_selected_trigger_queries(
    selected: Sequence[tuple[SkillTriggerQueries, TriggerQuery]],
    runs: int,
) -> None:
    query_count = len(selected)
    model_calls = query_count * runs
    if model_calls > _MAX_MODEL_CALLS:
        raise TriggerHarnessError(
            f"selected trigger invocation exceeds the {_MAX_MODEL_CALLS}-call limit"
        )
    if query_count > _MAX_SELECTED_QUERIES:
        raise TriggerHarnessError(
            f"selected trigger queries exceed the {_MAX_SELECTED_QUERIES}-query limit"
        )


def _execute_trigger_attempt(
    adapter: HarnessAdapter,
    workspace: ResultWorkspace,
    catalog: tuple[PreparedSkillSource, ...],
    skill: SkillRecord,
    query: TriggerQuery,
    manifest: AttemptManifest,
    harness_name: str,
    actor_model: str,
    actor_reasoning_effort: str,
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
        model=actor_model,
        reasoning_effort=actor_reasoning_effort,
        capture_outputs=True,
        artifact_binding=HarnessArtifactBinding(
            attempt_identity=paths.attempt_identity,
            outputs_identity=paths.directory_identities[("outputs",)],
            repository_identity=paths.repository_identity,
        ),
    )
    request = bind_harness_request(
        request,
        invocation_id=paths.invocation_id,
        run_id=run_id,
    )
    started_at = datetime.now(timezone.utc)
    try:
        execution = adapter.execute(request, paths.root)
    except Exception as error:
        execution = actor_evidence.failed_actor_execution(
            error,
            request,
            started_at,
        )
    execution = enforce_execution_binding(execution, request)
    execution = enforce_execution_configuration(
        execution,
        expected_model=actor_model,
        expected_reasoning_effort=actor_reasoning_effort,
        role="actor",
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
    execution, durable_response = actor_evidence.prepare_durable_actor_execution(
        execution
    )
    activation, activation_error = _validated_trigger_activation(
        execution,
        skill.name,
    )
    if activation_error is not None:
        execution = replace(
            execution,
            trace=(
                *execution.trace,
                {"event": "evidence_error", "message": activation_error},
            ),
            failure="\n".join(
                part for part in (execution.failure, activation_error) if part
            ),
        )
    else:
        assert activation is not None
        execution = replace(
            execution,
            trace=(
                *execution.trace,
                {
                    "event": "trigger_activation_evidence",
                    "expected_skill_path": str(execution.expected_skill_path),
                    "expected_skill_catalog_path": (
                        manifest.expected_skill_catalog_path
                    ),
                    "successful_exact_read": activation,
                },
            ),
        )
    ended_at = datetime.now(timezone.utc)
    timing = record_harness_timing(
        invocation_id=paths.invocation_id,
        run_id=run_id,
        skill_name=skill.name,
        case_id=query.id,
        run_kind="trigger",
        harness_name=harness_name,
        started_at=started_at,
        ended_at=ended_at,
        execution=execution,
    )
    transcript = _trigger_transcript(query, durable_response)
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

    try:
        output_snapshot = actor_evidence.snapshot_captured_outputs(
            paths.root / "outputs",
            expected_parent_identity=paths.attempt_identity,
            expected_root_identity=paths.directory_identities[("outputs",)],
        )
    except ResultArtifactError as error:
        write_incomplete_attempt_artifacts(
            paths,
            response=durable_response,
            transcript=transcript,
            execution_trace=(
                *execution.trace,
                {
                    "event": "evidence_error",
                    "message": str(error),
                },
            ),
            timing=timing,
        )
        return TriggerAttemptOutcome(
            activated=None,
            matched_expectation=None,
            error=str(error),
            run_number=run_number,
            artifact_dir=paths.root,
        )

    assert activation is not None
    activated = activation
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
                    "trigger_activation_evidence successful_exact_read=true"
                    if activated
                    else "trigger_activation_evidence successful_exact_read=false"
                ),
            },
        ),
    )
    grading = GradingRecord(
        invocation_id=paths.invocation_id,
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
        measurements={
            "trigger_rate": float(activated),
            "expected_trigger_rate": float(query.should_trigger),
        },
    )
    try:
        write_eval_run_artifacts(
            paths,
            EvalRunRecord(
                response=durable_response,
                transcript=transcript,
                execution_trace=execution.trace,
                timing=timing,
                grading=grading,
            ),
            actor_output_directories=tuple(
                path.as_posix() for path in output_snapshot.directories
            ),
            actor_output_files=tuple(
                (file.path.as_posix(), file.content)
                for file in output_snapshot.files
            ),
            completion_guard=lambda response_written: (
                actor_evidence.require_unchanged_output_snapshot(
                    paths.root / "outputs",
                    output_snapshot,
                    runner_response=(
                        durable_response if response_written else None
                    ),
                    expected_parent_identity=paths.attempt_identity,
                    repository_identity=paths.repository_identity,
                )
            ),
        )
    except ResultArtifactError as error:
        return TriggerAttemptOutcome(
            activated=None,
            matched_expectation=None,
            error=str(error),
            run_number=run_number,
            artifact_dir=paths.root,
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
    *,
    runtime_input_sha256: str,
) -> AttemptManifest:
    expected_text = (
        f"The installed harness "
        f"{'loads' if query.should_trigger else 'does not load'} "
        f"the {skill.name} skill."
    )
    return AttemptManifest(
        run_id=_injective_trigger_run_id(skill.name, query.id, run_number),
        skill_name=skill.name,
        case_id=query.id,
        run_kind="trigger",
        runtime_input_sha256=runtime_input_sha256,
        scenario_definition_sha256=runtime_input_sha256,
        expected_activation=query.should_trigger,
        expected_skill_catalog_path=(
            f"codex-home/skills/{skill.name}/SKILL.md"
        ),
        assertion_contract=(
            AssertionContract(
                id="expected-skill-activation",
                kind="trigger",
                text=expected_text,
                checked_by="trigger_runner",
            ),
        ),
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


def _trigger_runtime_input_sha256(
    skill: SkillRecord,
    query: TriggerQuery,
    catalog: Sequence[PreparedSkillSource],
) -> str:
    return canonical_document_sha256(
        {
            "kind": "trigger",
            "skill_name": skill.name,
            "query_id": query.id,
            "query": query.query,
            "should_trigger": query.should_trigger,
            "actor_catalog": [
                {"name": source.name, "sha256": source.sha256}
                for source in catalog
            ],
        }
    )


def _verify_trigger_plan_inputs(plan: PreparedTriggerPlan) -> None:
    _verify_trigger_plan_contract(plan)
    for attempt in plan.attempts:
        actual = _trigger_runtime_input_sha256(
            attempt.definition.skill,
            attempt.query,
            plan.catalog,
        )
        if (
            actual != attempt.manifest.runtime_input_sha256
            or actual != attempt.manifest.scenario_definition_sha256
        ):
            raise TriggerHarnessError(
                f"prepared trigger inputs changed after declaration: "
                f"{attempt.manifest.run_id}"
            )


def _verify_trigger_plan_contract(plan: PreparedTriggerPlan) -> None:
    if plan.runs not in (1, 2, 3):
        raise TriggerHarnessError("prepared trigger plan has an invalid run count")
    selected_by_key: dict[
        tuple[str, str],
        tuple[SkillTriggerQueries, TriggerQuery],
    ] = {}
    for definition, query in plan.selected:
        if definition not in plan.definitions or query not in definition.queries:
            raise TriggerHarnessError(
                "prepared trigger selection is not bound to its loaded definition"
            )
        key = (definition.skill.name, query.id)
        if key in selected_by_key:
            raise TriggerHarnessError(
                "prepared trigger selection contains duplicate query identities"
            )
        selected_by_key[key] = (definition, query)

    expected_keys = {
        (definition.skill.name, query.id, run_number)
        for definition, query in plan.selected
        for run_number in range(1, plan.runs + 1)
    }
    actual_keys = {
        (
            attempt.definition.skill.name,
            attempt.query.id,
            attempt.run_number,
        )
        for attempt in plan.attempts
    }
    if len(plan.attempts) != len(expected_keys) or actual_keys != expected_keys:
        raise TriggerHarnessError(
            "prepared trigger plan does not contain the exact configured run set"
        )

    minimum_pass_rate = 2 / 3 if plan.runs == 3 else 1.0
    for attempt in plan.attempts:
        selected = selected_by_key.get(
            (attempt.definition.skill.name, attempt.query.id)
        )
        if (
            selected is None
            or attempt.definition != selected[0]
            or attempt.query != selected[1]
        ):
            raise TriggerHarnessError(
                "prepared trigger attempt is not bound to its selected query"
            )
        expected_manifest = _trigger_attempt_manifest(
            attempt.definition.skill,
            attempt.query,
            attempt.run_number,
            plan.runs,
            minimum_pass_rate,
            runtime_input_sha256=_trigger_runtime_input_sha256(
                attempt.definition.skill,
                attempt.query,
                plan.catalog,
            ),
        )
        if attempt.manifest != replace(
            expected_manifest,
            runtime_input_sha256=attempt.manifest.runtime_input_sha256,
            scenario_definition_sha256=(
                attempt.manifest.scenario_definition_sha256
            ),
        ):
            raise TriggerHarnessError(
                "prepared trigger attempt has inconsistent identity, "
                f"expectation, or aggregation policy: {attempt.manifest.run_id}"
            )


def _injective_trigger_run_id(
    skill_name: str,
    query_id: str,
    run_number: int,
) -> str:
    rendered_run = str(run_number)
    return (
        f"s{len(skill_name)}-{skill_name}-"
        f"q{len(query_id)}-{query_id}-"
        f"r{len(rendered_run)}-{rendered_run}"
    )


def _trigger_transcript(query: TriggerQuery, durable_response: str) -> str:
    expectation = "load the skill" if query.should_trigger else "leave the skill unselected"
    durable_query = bounded_redacted_runtime_text(query.query, 16384)
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
    return (
        classify_codex_skill_evidence_path(
            execution.expected_skill_path,
            skill_name,
        )
        is StructuredSkillPathKind.CANONICAL_TARGET
    )


def _validated_trigger_activation(
    execution: HarnessExecution,
    skill_name: str,
) -> tuple[bool | None, str | None]:
    expected = execution.expected_skill_path
    if (
        classify_codex_skill_evidence_path(expected, skill_name)
        is not StructuredSkillPathKind.CANONICAL_TARGET
    ):
        return (
            None,
            "trigger execution has no canonical expected installed SKILL.md path",
        )
    read_classifications = tuple(
        classify_codex_skill_evidence_path(path, skill_name)
        for path in execution.successful_skill_reads
    )
    if any(
        classification is StructuredSkillPathKind.NONCANONICAL
        for classification in read_classifications
    ):
        return (
            None,
            "harness successful_skill_reads contains a noncanonical logical "
            "Codex skill path",
        )
    field_matches = sum(
        classification is StructuredSkillPathKind.CANONICAL_TARGET
        for classification in read_classifications
    )
    try:
        lifecycle_skill_reads = validated_actor_skill_read_lifecycle(
            execution.trace
        )
    except ValueError as error:
        return None, f"trigger actor lifecycle is invalid: {error}"
    trace_classifications = tuple(
        classify_codex_skill_evidence_path(path, skill_name)
        for path in lifecycle_skill_reads
    )
    if any(
        classification is StructuredSkillPathKind.NONCANONICAL
        for classification in trace_classifications
    ):
        return (
            None,
            "harness trace contains a noncanonical logical Codex skill_read path",
        )
    trace_matches = sum(
        classification is StructuredSkillPathKind.CANONICAL_TARGET
        for classification in trace_classifications
    )
    field_activated = field_matches == 1
    trace_activated = trace_matches == 1
    if (
        field_matches > 1
        or trace_matches > 1
        or field_activated is not trace_activated
    ):
        return (
            None,
            "harness skill-read metadata does not match the preserved exact "
            "SKILL.md trace evidence",
        )
    return field_activated, None


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
