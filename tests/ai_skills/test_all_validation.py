from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import scripts.ai_skills as cli
import scripts.ai_skills_lib.all_validation as all_validation
import scripts.ai_skills_lib.eval_definitions as eval_definitions
import scripts.ai_skills_lib.eval_validation as eval_validation
import scripts.ai_skills_lib.trigger_definitions as trigger_definitions
import scripts.ai_skills_lib.trigger_validation as trigger_validation
from scripts.ai_skills_lib.eval_core import ResultArtifactError
from scripts.ai_skills_lib.eval_validation import BehaviorSuiteResult
from scripts.ai_skills_lib.harness import (
    HarnessCapabilities,
    HarnessExecution,
    HarnessRequest,
)
from scripts.ai_skills_lib.trigger_validation import TriggerSuiteResult


def _create_repository(root: Path) -> Path:
    repository = root / "repository"
    skill = repository / "skills" / "workflows" / "alpha"
    evals = skill / "evals"
    evals.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        (
            "---\n"
            "name: alpha\n"
            "description: Use for alpha work.\n"
            "metadata:\n"
            '  status: "public-ready"\n'
            '  tier: "standard"\n'
            '  config_mode: "none"\n'
            '  allows_tool_references: "false"\n'
            "---\n"
            "Complete alpha work.\n"
        ),
        encoding="utf-8",
    )
    (evals / "triggers.json").write_text(
        json.dumps(
            {
                "skill_name": "alpha",
                "queries": [
                    {
                        "id": "positive",
                        "query": "Use alpha.",
                        "should_trigger": True,
                    },
                    {
                        "id": "negative",
                        "query": "Summarize unrelated work.",
                        "should_trigger": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (evals / "evals.json").write_text(
        json.dumps(
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "core",
                        "prompt": "Perform alpha.",
                        "expected_output": "A complete alpha result.",
                        "assertions": ["The response completes alpha."],
                        "checks": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return repository


class CombinedHarness:
    def __init__(self, results_root: Path) -> None:
        self.results_root = results_root
        self.preflight_calls = 0
        self.requests: list[HarnessRequest] = []

    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        self.preflight_calls += 1
        trigger_manifest = self.results_root / "triggers" / "invocation.json"
        behavior_manifest = self.results_root / "evals" / "invocation.json"
        if not trigger_manifest.is_file() or not behavior_manifest.is_file():
            raise AssertionError("both sub-invocation manifests must precede preflight")
        return HarnessCapabilities(
            harness_name="recording",
            available=True,
            actor_model="actor",
            actor_reasoning_effort="high",
            judge_model="judge",
            judge_reasoning_effort="high",
            reports_token_usage=True,
            reports_successful_skill_reads=True,
        )

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        self.requests.append(request)
        response = "A complete alpha result."
        successful_reads: tuple[Path, ...] = ()
        expected_path: Path | None = None
        if request.role == "judge":
            response = json.dumps(
                {
                    "assertion_results": [
                        {
                            "id": "assertion-1",
                            "passed": True,
                            "evidence": "The response completes alpha.",
                            "evidence_refs": [
                                {
                                    "artifact": "outputs/response.md",
                                    "locator": "complete response",
                                }
                            ],
                        }
                    ]
                }
            )
        elif not request.capture_outputs:
            expected_path = Path(
                f"/sandbox/codex-home/skills/{request.expected_skill}/SKILL.md"
            )
            if request.prompt == "Use alpha.":
                successful_reads = (expected_path,)
        return HarnessExecution(
            response=response,
            trace=({"event": f"{request.role}.completed"},),
            duration_ms=10,
            total_tokens=5,
            input_tokens=3,
            output_tokens=2,
            cached_tokens=0,
            token_source="test",
            successful_skill_reads=successful_reads,
            exit_code=0,
            failure=None,
            model=f"{request.role}-model",
            reasoning_effort="high",
            timed_out=False,
            expected_skill_path=expected_path,
        )


class PendingTriggerHarness(CombinedHarness):
    def __init__(self, results_root: Path) -> None:
        super().__init__(results_root)
        self.positive_activations = [True, False, True]

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        execution = super().execute(request, artifact_dir)
        if request.role != "actor" or request.capture_outputs:
            return execution
        if request.prompt != "Use alpha.":
            return execution
        activated = self.positive_activations.pop(0)
        assert execution.expected_skill_path is not None
        return replace(
            execution,
            successful_skill_reads=(execution.expected_skill_path,) if activated else (),
        )


class PendingTriggerFailingBehaviorHarness(PendingTriggerHarness):
    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        execution = super().execute(request, artifact_dir)
        if request.role != "judge":
            return execution
        payload = json.loads(execution.response)
        payload["assertion_results"][0]["passed"] = False
        return replace(execution, response=json.dumps(payload))


class FailingSubrunHarness(CombinedHarness):
    def __init__(self, results_root: Path, failing_subrun: str) -> None:
        super().__init__(results_root)
        self.failing_subrun = failing_subrun

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        execution = super().execute(request, artifact_dir)
        is_trigger_actor = request.role == "actor" and not request.capture_outputs
        is_behavior_actor = request.role == "actor" and request.capture_outputs
        if not (
            (self.failing_subrun == "triggers" and is_trigger_actor)
            or (self.failing_subrun == "evals" and is_behavior_actor)
        ):
            return execution
        return replace(
            execution,
            successful_skill_reads=(),
            exit_code=1,
            failure=f"{self.failing_subrun} actor failed",
        )


class FailingPreflightHarness(CombinedHarness):
    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        super().preflight(require_fixtures=require_fixtures)
        raise trigger_validation.TriggerHarnessError("combined preflight failed")


class CompleteValidationTests(unittest.TestCase):
    def test_cli_runs_deterministic_gate_before_dispatching_model_suite(self) -> None:
        with (
            patch.object(cli, "run_ci_validation", return_value=[]),
            patch.object(cli, "run_unit_tests", return_value=0),
            patch.object(cli, "run_all_evaluation_harness", return_value=1) as run,
        ):
            result = cli.main(
                [
                    "validate",
                    "all",
                    "--harness",
                    "codex",
                    "--runs",
                    "3",
                    "--skill",
                    "alpha",
                    "--max-concurrency",
                    "4",
                    "--results-dir",
                    "/tmp/all-results",
                ]
            )

        self.assertEqual(result, 1)
        run.assert_called_once_with(
            cli.REPOSITORY_ROOT,
            harness="codex",
            runs=3,
            skill_filter="alpha",
            results_dir=Path("/tmp/all-results"),
            max_concurrency=4,
        )

    def test_deterministic_failure_prevents_model_suite_dispatch(self) -> None:
        with (
            patch.object(cli, "run_ci_validation", return_value=[]),
            patch.object(cli, "run_unit_tests", return_value=1),
            patch.object(cli, "run_all_evaluation_harness") as run,
            redirect_stdout(StringIO()),
        ):
            result = cli.main(["validate", "all", "--harness", "codex"])

        self.assertEqual(result, 1)
        run.assert_not_called()

    def test_trigger_and_behavior_runners_share_one_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            adapter = CombinedHarness(results)
            session = SimpleNamespace(
                adapter=adapter,
                manifest=SimpleNamespace(
                    limits=SimpleNamespace(
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )
                ),
                close=MagicMock(),
            )
            trigger_loader = MagicMock(
                wraps=trigger_definitions.load_trigger_queries
            )
            behavior_loader = MagicMock(
                wraps=eval_definitions.load_behavior_evals
            )

            with (
                patch.object(all_validation, "load_trigger_queries", trigger_loader),
                patch.object(trigger_validation, "load_trigger_queries", trigger_loader),
                patch.object(all_validation, "load_behavior_evals", behavior_loader),
                patch.object(eval_validation, "load_behavior_evals", behavior_loader),
                patch.object(
                    all_validation.CodexEvaluationRuntime,
                    "create",
                    return_value=session,
                ),
                redirect_stdout(StringIO()),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=1,
                    skill_filter=None,
                    results_dir=results,
                    max_concurrency=2,
                )

            self.assertEqual(result, 0)
            self.assertEqual(adapter.preflight_calls, 1)
            trigger_loader.assert_called_once_with(repository)
            behavior_loader.assert_called_once_with(repository)
            self.assertTrue((results / "triggers" / "invocation.json").is_file())
            self.assertTrue((results / "evals" / "invocation.json").is_file())
            for subrun in ("triggers", "evals"):
                self.assertIn(
                    "Decision: pass",
                    (results / subrun / "summary.md").read_text(encoding="utf-8"),
                )
            self.assertIn(
                "Decision: pass",
                (results / "summary.md").read_text(encoding="utf-8"),
            )
            session.close.assert_called_once_with()

    def test_combined_two_of_three_is_pending_review_without_trigger_aggregation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            adapter = PendingTriggerHarness(results)
            session = SimpleNamespace(
                adapter=adapter,
                manifest=SimpleNamespace(
                    limits=SimpleNamespace(
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )
                ),
                close=MagicMock(),
            )
            output = StringIO()

            with (
                patch.object(
                    all_validation.CodexEvaluationRuntime,
                    "create",
                    return_value=session,
                ),
                redirect_stdout(output),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=3,
                    skill_filter="alpha",
                    results_dir=results,
                    max_concurrency=1,
                )

            trigger_summary = (results / "triggers" / "summary.md").read_text(
                encoding="utf-8"
            )
            collection_summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 1)
            self.assertEqual(len(tuple((results / "triggers" / "attempts").iterdir())), 6)
            self.assertFalse((results / "triggers" / "benchmark.json").exists())
            self.assertTrue((results / "evals" / "benchmark.json").is_file())
            self.assertIn("Decision: pending review", trigger_summary)
            self.assertIn("run 2: mismatch", trigger_summary)
            self.assertIn("Decision: pending review", collection_summary)
            self.assertIn("pending_review", collection_summary)
            self.assertIn("validate all: PENDING REVIEW", output.getvalue())

    def test_combined_pending_review_precedes_behavior_expectation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            adapter = PendingTriggerFailingBehaviorHarness(results)
            session = SimpleNamespace(
                adapter=adapter,
                manifest=SimpleNamespace(
                    limits=SimpleNamespace(
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )
                ),
                close=MagicMock(),
            )
            output = StringIO()

            with (
                patch.object(
                    all_validation.CodexEvaluationRuntime,
                    "create",
                    return_value=session,
                ),
                redirect_stdout(output),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=3,
                    skill_filter="alpha",
                    results_dir=results,
                    max_concurrency=1,
                )

            collection_summary = (results / "summary.md").read_text(encoding="utf-8")
            behavior_summary = (results / "evals" / "summary.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(result, 1)
            self.assertIn("Decision: pending review", collection_summary)
            self.assertNotIn("Decision: expectations failed", collection_summary)
            self.assertIn("Decision: expectations failed", behavior_summary)
            self.assertIn("validate all: PENDING REVIEW", output.getvalue())

    def test_combined_execution_error_precedes_pending_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            adapter = PendingTriggerHarness(results)
            session = SimpleNamespace(
                adapter=adapter,
                manifest=SimpleNamespace(
                    limits=SimpleNamespace(
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )
                ),
                close=MagicMock(),
            )
            output = StringIO()

            with (
                patch.object(
                    all_validation.CodexEvaluationRuntime,
                    "create",
                    return_value=session,
                ),
                patch.object(
                    all_validation,
                    "execute_prepared_behavior_plan",
                    side_effect=RuntimeError("behavior execution raised"),
                ),
                redirect_stdout(output),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=3,
                    skill_filter="alpha",
                    results_dir=results,
                    max_concurrency=1,
                )

            trigger_summary = (results / "triggers" / "summary.md").read_text(
                encoding="utf-8"
            )
            collection_summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn("Decision: pending review", trigger_summary)
            self.assertIn("Decision: execution error", collection_summary)
            self.assertIn("validate all: EXECUTION ERROR", output.getvalue())

    def test_combined_exit_two_subruns_receive_terminal_summaries(self) -> None:
        for failing_subrun in ("triggers", "evals"):
            with self.subTest(failing_subrun=failing_subrun), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                repository = _create_repository(base)
                results = base / "results"
                adapter = FailingSubrunHarness(results, failing_subrun)
                session = SimpleNamespace(
                    adapter=adapter,
                    manifest=SimpleNamespace(
                        limits=SimpleNamespace(
                            actor_timeout_seconds=60,
                            judge_timeout_seconds=30,
                        )
                    ),
                    close=MagicMock(),
                )
                output = StringIO()

                with (
                    patch.object(
                        all_validation.CodexEvaluationRuntime,
                        "create",
                        return_value=session,
                    ),
                    redirect_stdout(output),
                ):
                    result = all_validation.run_all_evaluation_harness(
                        repository,
                        harness="codex",
                        runs=1,
                        skill_filter="alpha",
                        results_dir=results,
                        max_concurrency=1,
                    )

                failed_summary = (results / failing_subrun / "summary.md").read_text(
                    encoding="utf-8"
                )
                collection_summary = (results / "summary.md").read_text(
                    encoding="utf-8"
                )
                self.assertEqual(result, 2)
                self.assertTrue((results / "triggers" / "summary.md").is_file())
                self.assertTrue((results / "evals" / "summary.md").is_file())
                self.assertFalse((results / failing_subrun / "benchmark.json").exists())
                self.assertIn("Decision: execution error", failed_summary)
                self.assertIn(f"{failing_subrun} actor failed", failed_summary)
                self.assertIn("Decision: execution error", collection_summary)
                self.assertIn("validate all: EXECUTION ERROR", output.getvalue())

    def test_combined_preflight_failure_finalizes_both_created_subruns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            adapter = FailingPreflightHarness(results)
            session = SimpleNamespace(
                adapter=adapter,
                manifest=SimpleNamespace(
                    limits=SimpleNamespace(
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )
                ),
                close=MagicMock(),
            )

            with (
                patch.object(
                    all_validation.CodexEvaluationRuntime,
                    "create",
                    return_value=session,
                ),
                redirect_stdout(StringIO()),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=1,
                    skill_filter="alpha",
                    results_dir=results,
                    max_concurrency=1,
                )

            collection_summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            for subrun in ("triggers", "evals"):
                summary = (results / subrun / "summary.md").read_text(encoding="utf-8")
                self.assertIn("Decision: execution error", summary)
                self.assertIn("combined preflight failed", summary)
                self.assertFalse((results / subrun / "benchmark.json").exists())
            self.assertIn("Decision: execution error", collection_summary)
            self.assertIn("combined preflight failed", collection_summary)

    def test_combined_execution_exception_finalizes_each_created_subrun(self) -> None:
        for failing_subrun in ("triggers", "evals"):
            with self.subTest(failing_subrun=failing_subrun), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                repository = _create_repository(base)
                results = base / "results"
                adapter = CombinedHarness(results)
                session = SimpleNamespace(
                    adapter=adapter,
                    manifest=SimpleNamespace(
                        limits=SimpleNamespace(
                            actor_timeout_seconds=60,
                            judge_timeout_seconds=30,
                        )
                    ),
                    close=MagicMock(),
                )
                failure = RuntimeError(f"{failing_subrun} execution raised")
                patch_target = (
                    "execute_prepared_trigger_plan"
                    if failing_subrun == "triggers"
                    else "execute_prepared_behavior_plan"
                )

                with (
                    patch.object(
                        all_validation.CodexEvaluationRuntime,
                        "create",
                        return_value=session,
                    ),
                    patch.object(all_validation, patch_target, side_effect=failure),
                    redirect_stdout(StringIO()),
                ):
                    result = all_validation.run_all_evaluation_harness(
                        repository,
                        harness="codex",
                        runs=1,
                        skill_filter="alpha",
                        results_dir=results,
                        max_concurrency=1,
                    )

                collection_summary = (results / "summary.md").read_text(
                    encoding="utf-8"
                )
                self.assertEqual(result, 2)
                for subrun in ("triggers", "evals"):
                    self.assertTrue((results / subrun / "summary.md").is_file())
                failed_summary = (results / failing_subrun / "summary.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn(f"{failing_subrun} execution raised", failed_summary)
                self.assertIn(f"{failing_subrun} execution raised", collection_summary)

    def test_trigger_aggregation_failure_does_not_prevent_behavior_finalization(self) -> None:
        self._assert_aggregation_failure_isolated("triggers")

    def test_behavior_aggregation_failure_does_not_prevent_trigger_finalization(self) -> None:
        self._assert_aggregation_failure_isolated("evals")

    def test_collection_summary_reports_both_aggregation_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            adapter = CombinedHarness(results)
            session = SimpleNamespace(
                adapter=adapter,
                manifest=SimpleNamespace(
                    limits=SimpleNamespace(
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )
                ),
                close=MagicMock(),
            )

            with (
                patch.object(
                    all_validation.CodexEvaluationRuntime,
                    "create",
                    return_value=session,
                ),
                patch.object(
                    trigger_validation,
                    "aggregate_results",
                    side_effect=ResultArtifactError("trigger aggregate failed"),
                ),
                patch.object(
                    all_validation,
                    "aggregate_results",
                    side_effect=ResultArtifactError("behavior aggregate failed"),
                ),
                redirect_stdout(StringIO()),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=1,
                    skill_filter="alpha",
                    results_dir=results,
                    max_concurrency=1,
                )

            collection_summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn("trigger aggregate failed", collection_summary)
            self.assertIn("behavior aggregate failed", collection_summary)
            self.assertTrue((results / "triggers" / "summary.md").is_file())
            self.assertTrue((results / "evals" / "summary.md").is_file())

    def test_trigger_finalizer_exception_does_not_prevent_behavior_finalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            adapter = CombinedHarness(results)
            session = SimpleNamespace(
                adapter=adapter,
                manifest=SimpleNamespace(
                    limits=SimpleNamespace(
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )
                ),
                close=MagicMock(),
            )

            with (
                patch.object(
                    all_validation.CodexEvaluationRuntime,
                    "create",
                    return_value=session,
                ),
                patch.object(
                    all_validation,
                    "finalize_trigger_result",
                    side_effect=RuntimeError("trigger finalizer raised"),
                ),
                redirect_stdout(StringIO()),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=1,
                    skill_filter="alpha",
                    results_dir=results,
                    max_concurrency=1,
                )

            trigger_summary = (results / "triggers" / "summary.md").read_text(
                encoding="utf-8"
            )
            collection_summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn("trigger finalizer raised", trigger_summary)
            self.assertTrue((results / "evals" / "summary.md").is_file())
            self.assertTrue((results / "evals" / "benchmark.json").is_file())
            self.assertIn("trigger finalizer raised", collection_summary)

    def _assert_aggregation_failure_isolated(self, failing_subrun: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            adapter = CombinedHarness(results)
            session = SimpleNamespace(
                adapter=adapter,
                manifest=SimpleNamespace(
                    limits=SimpleNamespace(
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )
                ),
                close=MagicMock(),
            )
            trigger_aggregation = (
                {"side_effect": ResultArtifactError("trigger aggregate failed")}
                if failing_subrun == "triggers"
                else {"wraps": trigger_validation.aggregate_results}
            )
            behavior_aggregation = (
                {"side_effect": ResultArtifactError("behavior aggregate failed")}
                if failing_subrun == "evals"
                else {"wraps": all_validation.aggregate_results}
            )

            with (
                patch.object(
                    all_validation.CodexEvaluationRuntime,
                    "create",
                    return_value=session,
                ),
                patch.object(
                    trigger_validation,
                    "aggregate_results",
                    **trigger_aggregation,
                ),
                patch.object(
                    all_validation,
                    "aggregate_results",
                    **behavior_aggregation,
                ),
                redirect_stdout(StringIO()),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=1,
                    skill_filter="alpha",
                    results_dir=results,
                    max_concurrency=1,
                )

            failed_summary = (results / failing_subrun / "summary.md").read_text(
                encoding="utf-8"
            )
            sibling = "evals" if failing_subrun == "triggers" else "triggers"
            failure_message = (
                "trigger aggregate failed"
                if failing_subrun == "triggers"
                else "behavior aggregate failed"
            )
            collection_summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn(failure_message, failed_summary)
            self.assertTrue((results / sibling / "benchmark.json").is_file())
            self.assertTrue((results / sibling / "summary.md").is_file())
            self.assertIn(failure_message, collection_summary)

    def test_combined_trigger_limits_fail_before_workspace_creation(self) -> None:
        root = Path("/nonexistent/repository")
        skill = SimpleNamespace(name="alpha", root=root / "skills" / "alpha")
        trigger_definition = SimpleNamespace(
            skill=skill,
            queries=tuple(
                trigger_definitions.TriggerQuery(
                    id=f"query-{index}",
                    query=f"Query {index}.",
                    should_trigger=index == 0,
                )
                for index in range(129)
            ),
        )
        behavior_definition = SimpleNamespace(
            skill=skill,
            cases=(SimpleNamespace(id="core"),),
        )
        output = StringIO()

        with (
            patch.object(
                all_validation,
                "load_trigger_queries",
                return_value=(trigger_definition,),
            ),
            patch.object(
                all_validation,
                "load_behavior_evals",
                return_value=(behavior_definition,),
            ),
            patch.object(all_validation, "create_result_workspace") as create_results,
            redirect_stdout(output),
        ):
            result = all_validation.run_all_evaluation_harness(
                root,
                harness="codex",
                runs=1,
                skill_filter=None,
                results_dir=None,
                max_concurrency=2,
            )

        self.assertEqual(result, 2)
        create_results.assert_not_called()
        self.assertIn("128-query", output.getvalue())

    def test_combined_summary_write_failure_is_bounded_and_reports_result_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            diagnostic = "summary disk failure " + ("x" * 10_000)
            output = StringIO()

            with (
                patch.object(
                    all_validation,
                    "write_result_summary",
                    side_effect=ResultArtifactError(diagnostic),
                ),
                redirect_stdout(output),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="claude",
                    runs=1,
                    skill_filter=None,
                    results_dir=results,
                    max_concurrency=2,
                )

            rendered = output.getvalue()
            self.assertEqual(result, 2)
            self.assertIn("result summary failed", rendered)
            self.assertIn(f"Results: {results.resolve()}", rendered)
            self.assertIn("[TRUNCATED]", rendered)
            self.assertLess(len(rendered.encode("utf-8")), 6000)

    def test_post_collection_declaration_failure_writes_summary_and_result_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = _create_repository(base)
            results = base / "results"
            output = StringIO()

            with (
                patch.object(
                    all_validation,
                    "declare_trigger_plan",
                    side_effect=ResultArtifactError("cannot declare trigger plan"),
                ),
                redirect_stdout(output),
            ):
                result = all_validation.run_all_evaluation_harness(
                    repository,
                    harness="codex",
                    runs=1,
                    skill_filter=None,
                    results_dir=results,
                    max_concurrency=2,
                )

            rendered = output.getvalue()
            summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn("cannot declare trigger plan", rendered)
            self.assertIn(f"Results: {results.resolve()}", rendered)
            self.assertIn("Decision: execution error", summary)
            self.assertIn("cannot declare trigger plan", summary)

    def test_combined_summary_write_failure_after_runtime_start_never_escapes(self) -> None:
        for runtime_fails in (True, False):
            with self.subTest(runtime_fails=runtime_fails), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                repository = _create_repository(base)
                results = base / "results"
                adapter = CombinedHarness(results)
                session = SimpleNamespace(
                    adapter=adapter,
                    manifest=SimpleNamespace(
                        limits=SimpleNamespace(
                            actor_timeout_seconds=60,
                            judge_timeout_seconds=30,
                        )
                    ),
                    close=MagicMock(),
                )
                runtime_result = (
                    all_validation.EvaluationRuntimeError("runtime unavailable")
                    if runtime_fails
                    else session
                )
                runtime_kwargs = (
                    {"side_effect": runtime_result}
                    if runtime_fails
                    else {"return_value": runtime_result}
                )
                output = StringIO()

                with (
                    patch.object(
                        all_validation.CodexEvaluationRuntime,
                        "create",
                        **runtime_kwargs,
                    ),
                    patch.object(
                        all_validation,
                        "write_result_summary",
                        side_effect=ResultArtifactError("cannot persist summary"),
                    ),
                    redirect_stdout(output),
                ):
                    result = all_validation.run_all_evaluation_harness(
                        repository,
                        harness="codex",
                        runs=1,
                        skill_filter=None,
                        results_dir=results,
                        max_concurrency=2,
                    )

                self.assertEqual(result, 2)
                self.assertIn("result summary failed", output.getvalue())
                self.assertIn(f"Results: {results.resolve()}", output.getvalue())


if __name__ == "__main__":
    unittest.main()
