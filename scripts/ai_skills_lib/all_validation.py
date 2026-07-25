"""One-preflight orchestration for the complete model-backed validation suite."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from scripts.ai_skills_lib.eval_core import (
    ResultWorkspace,
    TerminalDecision,
    create_result_workspace,
    format_benchmark_summary,
    preflight_bound_invocations,
    resolve_terminal_decision,
    write_result_summary,
)
from scripts.ai_skills_lib.eval_definitions import (
    BehaviorDefinitionError,
    load_behavior_evals,
)
from scripts.ai_skills_lib.eval_validation import (
    BehaviorFinalization,
    BehaviorHarnessError,
    BehaviorSuiteResult,
    _persist_terminal_behavior_summary,
    declare_behavior_plan,
    execute_prepared_behavior_plan,
    finalize_behavior_result,
    format_behavior_summary,
    prepare_behavior_plan,
)
from scripts.ai_skills_lib.evaluation_runtime import (
    CodexEvaluationRuntime,
    EvaluationRuntimeError,
)
from scripts.ai_skills_lib.secret_patterns import bounded_redacted_runtime_text
from scripts.ai_skills_lib.trigger_definitions import (
    TriggerDefinitionError,
    load_trigger_queries,
)
from scripts.ai_skills_lib.trigger_validation import (
    TriggerFinalization,
    TriggerHarnessError,
    TriggerSuiteResult,
    _persist_terminal_trigger_summary,
    declare_trigger_plan,
    execute_prepared_trigger_plan,
    finalize_trigger_result,
    format_trigger_summary,
    prepare_trigger_plan,
)


def run_all_evaluation_harness(
    root: Path,
    *,
    harness: str,
    runs: int,
    skill_filter: str | None,
    results_dir: Path | None,
    max_concurrency: int,
) -> int:
    """Run triggers and behavior evals through one preflighted runtime."""
    collection: ResultWorkspace | None = None
    trigger_workspace: ResultWorkspace | None = None
    behavior_workspace: ResultWorkspace | None = None
    try:
        if max_concurrency not in (1, 2, 3, 4):
            raise ValueError("maximum evaluation concurrency must be between 1 and 4")
        trigger_definitions = load_trigger_queries(root)
        behavior_definitions = load_behavior_evals(root)
        trigger_plan = prepare_trigger_plan(
            trigger_definitions,
            runs=runs,
            skill_filter=skill_filter,
            query_filter=None,
        )
        behavior_plan = prepare_behavior_plan(
            behavior_definitions,
            skill_filter=skill_filter,
            case_filter=None,
        )
        collection = create_result_workspace(
            "validate-all",
            results_dir=results_dir,
            repository_root=root,
        )
        trigger_workspace = create_result_workspace(
            "validate-triggers",
            results_dir=collection.root / "triggers",
            repository_root=root,
        )
        behavior_workspace = create_result_workspace(
            "validate-evals",
            results_dir=collection.root / "evals",
            repository_root=root,
        )
        declare_trigger_plan(trigger_workspace, trigger_plan)
        declare_behavior_plan(behavior_workspace, behavior_plan)
    except (BehaviorDefinitionError, TriggerDefinitionError) as error:
        print("validate all: INVALID DEFINITIONS")
        for issue in error.issues:
            print(f"{issue.scope}: {issue.message}")
        return 2
    except Exception as error:
        failure = str(error)
        if collection is None:
            print(
                "validate all: FAILED: "
                f"{bounded_redacted_runtime_text(failure, 4096)}"
            )
            return 2
        return _finish_all_run(
            root,
            collection,
            trigger_workspace=trigger_workspace,
            behavior_workspace=behavior_workspace,
            trigger_execution_failure=failure,
            behavior_execution_failure=failure,
            collection_failures=(failure,),
        )

    trigger_count = len(trigger_plan.selected)
    behavior_count = len(behavior_plan.selected)
    trigger_actor_runs = len(trigger_plan.attempts)
    behavior_actor_runs = len(behavior_plan.attempts)
    print(
        "all plan: "
        f"trigger_queries={trigger_count} behavior_cases={behavior_count} "
        f"actor_runs={trigger_actor_runs + behavior_actor_runs} "
        f"judge_runs={behavior_actor_runs} preflight_calls=1 "
        f"max_concurrency={max_concurrency} results={collection.root}"
    )
    if harness != "codex":
        failure = "Claude model-backed validation is not implemented"
        return _finish_all_run(
            root,
            collection,
            trigger_workspace=trigger_workspace,
            behavior_workspace=behavior_workspace,
            trigger_execution_failure=failure,
            behavior_execution_failure=failure,
            collection_failures=(failure,),
        )

    session: CodexEvaluationRuntime | None = None
    trigger_result: TriggerSuiteResult | None = None
    behavior_result: BehaviorSuiteResult | None = None
    trigger_execution_failure: str | None = None
    behavior_execution_failure: str | None = None
    collection_failures: list[str] = []
    phase = "runtime setup"
    try:
        session = CodexEvaluationRuntime.create(
            root,
            collection.root,
            invocation_label="all",
            max_concurrency=max_concurrency,
        )
        phase = "preflight"
        preflight_receipt = preflight_bound_invocations(
            session.adapter,
            (
                (
                    trigger_workspace,
                    "validate triggers",
                    trigger_plan.manifests,
                ),
                (
                    behavior_workspace,
                    "validate evals",
                    behavior_plan.manifests,
                ),
            ),
            require_fixtures=behavior_plan.require_fixtures,
        )
        capabilities = preflight_receipt.capabilities
        if not capabilities.available:
            raise BehaviorHarnessError(
                capabilities.failure or "selected harness is unavailable"
            )
        if not capabilities.reports_successful_skill_reads:
            raise TriggerHarnessError(
                "selected harness does not expose deterministic successful skill-read evidence"
            )

        phase = "trigger execution"
        trigger_result = execute_prepared_trigger_plan(
            session.adapter,
            trigger_workspace,
            trigger_plan,
            max_concurrency=max_concurrency,
            actor_timeout_seconds=session.manifest.limits.actor_timeout_seconds,
            preflight_receipt=preflight_receipt,
        )
        phase = "behavior execution"
        behavior_result = execute_prepared_behavior_plan(
            session.adapter,
            behavior_workspace,
            behavior_plan,
            max_concurrency=max_concurrency,
            actor_timeout_seconds=session.manifest.limits.actor_timeout_seconds,
            judge_timeout_seconds=session.manifest.limits.judge_timeout_seconds,
            preflight_receipt=preflight_receipt,
        )
    except Exception as error:
        failure = str(error) or type(error).__name__
        collection_failures.append(failure)
        if phase in ("runtime setup", "preflight"):
            trigger_execution_failure = failure
            behavior_execution_failure = failure
        elif phase == "trigger execution":
            trigger_execution_failure = failure
            behavior_execution_failure = (
                "behavior execution did not start because trigger execution failed: "
                f"{failure}"
            )
        else:
            behavior_execution_failure = failure
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as error:
                close_failure = f"runtime close failed: {str(error) or type(error).__name__}"
                collection_failures.append(close_failure)
                trigger_execution_failure = _join_failures(
                    trigger_execution_failure,
                    close_failure,
                )
                behavior_execution_failure = _join_failures(
                    behavior_execution_failure,
                    close_failure,
                )

    return _finish_all_run(
        root,
        collection,
        trigger_workspace=trigger_workspace,
        behavior_workspace=behavior_workspace,
        trigger_result=trigger_result,
        behavior_result=behavior_result,
        trigger_execution_failure=trigger_execution_failure,
        behavior_execution_failure=behavior_execution_failure,
        collection_failures=collection_failures,
    )


def _finish_all_run(
    root: Path,
    collection: ResultWorkspace,
    *,
    trigger_workspace: ResultWorkspace | None,
    behavior_workspace: ResultWorkspace | None,
    trigger_result: TriggerSuiteResult | None = None,
    behavior_result: BehaviorSuiteResult | None = None,
    trigger_execution_failure: str | None = None,
    behavior_execution_failure: str | None = None,
    collection_failures: Sequence[str] = (),
) -> int:
    """Finalize each created sub-run independently, then finalize the collection."""
    trigger_finalization = (
        _finalize_trigger_subrun_safely(
            root,
            trigger_workspace,
            trigger_result,
            execution_failure=trigger_execution_failure,
        )
        if trigger_workspace is not None
        else None
    )
    behavior_finalization = (
        _finalize_behavior_subrun_safely(
            root,
            behavior_workspace,
            behavior_result,
            execution_failure=behavior_execution_failure,
        )
        if behavior_workspace is not None
        else None
    )

    failures: list[str] = []
    for failure in collection_failures:
        _append_unique_failure(failures, failure)
    if trigger_finalization is not None:
        for failure in trigger_finalization.failures:
            _append_unique_failure(failures, f"trigger sub-run: {failure}")
    if behavior_finalization is not None:
        for failure in behavior_finalization.failures:
            _append_unique_failure(failures, f"behavior sub-run: {failure}")

    has_execution_error = bool(collection_failures) or any(
        finalization is not None
        and finalization.terminal.key == "execution_error"
        for finalization in (trigger_finalization, behavior_finalization)
    )
    has_pending_review = (
        trigger_finalization is not None
        and trigger_finalization.terminal.key == "pending_review"
    )
    has_expectation_failure = any(
        finalization is not None
        and finalization.terminal.key == "expectations_failed"
        for finalization in (trigger_finalization, behavior_finalization)
    )
    terminal = resolve_terminal_decision(
        execution_error=has_execution_error,
        pending_review=has_pending_review,
        expectation_failure=has_expectation_failure,
    )

    sections: list[str] = []
    if trigger_result is not None:
        sections.append(format_trigger_summary(trigger_result))
    if behavior_result is not None:
        sections.append(format_behavior_summary(behavior_result))
    if trigger_finalization is not None and trigger_finalization.benchmark is not None:
        sections.append(format_benchmark_summary(trigger_finalization.benchmark))
    if behavior_finalization is not None and behavior_finalization.benchmark is not None:
        sections.append(format_benchmark_summary(behavior_finalization.benchmark))
    details = "\n".join(section for section in sections if section)

    summary_failure = _write_all_summary(
        collection,
        terminal=terminal,
        details=details,
        failures=failures,
    )
    if summary_failure is not None:
        _append_unique_failure(
            failures,
            f"result summary failed: {summary_failure}",
        )
        terminal = resolve_terminal_decision(
            execution_error=True,
            pending_review=terminal.key == "pending_review",
            expectation_failure=terminal.key == "expectations_failed",
        )

    if details:
        print(details)
    if failures:
        rendered_failures = "\n".join(failures)
        print(
            "validate all: FAILED: "
            f"{bounded_redacted_runtime_text(rendered_failures, 4096)}"
        )
    print(f"Results: {collection.root}")
    print(f"validate all: {terminal.console_label}")
    return terminal.exit_code


def _write_all_summary(
    collection: ResultWorkspace,
    *,
    terminal: TerminalDecision,
    details: str | None = None,
    failures: Sequence[str] = (),
) -> str | None:
    lines = [
        "# Complete Skill Validation",
        "",
        f"Decision: {terminal.durable_label}",
        "",
    ]
    if failures:
        lines.extend(("## Errors", ""))
        for failure in failures:
            rendered = bounded_redacted_runtime_text(failure, 4096).replace(
                "\n",
                "\n  ",
            )
            lines.append(f"- {rendered}")
        lines.append("")
    if details:
        lines.extend(("## Results", "", details))
    lines.extend(
        (
            "",
            "## Sub-runs",
            "",
            "- `triggers/`",
            "- `evals/`",
        )
    )
    try:
        write_result_summary(collection, "\n".join(lines))
    except Exception as error:
        return bounded_redacted_runtime_text(str(error), 4096)
    return None


def _finalize_trigger_subrun_safely(
    root: Path,
    workspace: ResultWorkspace,
    result: TriggerSuiteResult | None,
    *,
    execution_failure: str | None,
) -> TriggerFinalization:
    try:
        return finalize_trigger_result(
            root,
            workspace,
            result,
            execution_failure=execution_failure,
        )
    except Exception as error:
        failure = f"trigger finalizer failed: {str(error) or type(error).__name__}"
        terminal = resolve_terminal_decision(
            execution_error=True,
            pending_review=result.requires_review if result is not None else False,
            expectation_failure=(
                result.has_failed_expectations if result is not None else False
            )
        )
        summary_failure = _persist_trigger_summary_safely(
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


def _finalize_behavior_subrun_safely(
    root: Path,
    workspace: ResultWorkspace,
    result: BehaviorSuiteResult | None,
    *,
    execution_failure: str | None,
) -> BehaviorFinalization:
    try:
        return finalize_behavior_result(
            root,
            workspace,
            result,
            execution_failure=execution_failure,
        )
    except Exception as error:
        failure = f"behavior finalizer failed: {str(error) or type(error).__name__}"
        terminal = resolve_terminal_decision(
            execution_error=True,
            pending_review=False,
            expectation_failure=result.exit_code == 1 if result is not None else False,
        )
        summary_failure = _persist_behavior_summary_safely(
            workspace,
            decision=terminal.durable_label,
            result=result,
            failure=failure,
        )
        failures = [failure]
        if summary_failure is not None:
            failures.append(f"result summary failed: {summary_failure}")
        return BehaviorFinalization(
            terminal=terminal,
            benchmark=None,
            failures=tuple(failures),
        )


def _persist_trigger_summary_safely(
    workspace: ResultWorkspace,
    *,
    decision: str,
    result: TriggerSuiteResult | None,
    failure: str,
) -> str | None:
    try:
        return _persist_terminal_trigger_summary(
            workspace,
            decision=decision,
            result=result,
            failure=failure,
        )
    except Exception as error:
        return bounded_redacted_runtime_text(str(error), 4096)


def _persist_behavior_summary_safely(
    workspace: ResultWorkspace,
    *,
    decision: str,
    result: BehaviorSuiteResult | None,
    failure: str | None = None,
) -> str | None:
    try:
        return _persist_terminal_behavior_summary(
            workspace,
            decision=decision,
            result=result,
            failure=failure,
        )
    except Exception as error:
        return bounded_redacted_runtime_text(str(error), 4096)


def _append_unique_failure(failures: list[str], failure: str) -> None:
    if failure and failure not in failures:
        failures.append(failure)


def _join_failures(first: str | None, second: str) -> str:
    return "\n".join(part for part in (first, second) if part)
