from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import scripts.ai_skills as cli
import scripts.ai_skills_lib.trigger_definitions as trigger_definitions
import scripts.ai_skills_lib.trigger_validation as trigger_validation
from scripts.ai_skills_lib.config import build_parser
from scripts.ai_skills_lib.eval_core import (
    ResultArtifactError,
    aggregate_results,
    benchmark_exit_code,
    create_result_workspace,
)
from scripts.ai_skills_lib.harness import (
    HarnessCapabilities,
    HarnessExecution,
    HarnessRequest,
)
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.trigger_validation import (
    TriggerAttemptOutcome,
    TriggerDefinitionError,
    TriggerHarnessError,
    classify_trigger_attempts,
    execute_trigger_queries,
    format_trigger_summary,
    load_trigger_queries,
    validate_trigger_query_files,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class TemporaryTriggerRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def add_skill(
        self,
        name: str,
        *,
        group: str = "workflows",
        trigger_document: dict[str, object] | None = None,
    ) -> Path:
        skill_root = self.root / "skills" / group / name
        evals_root = skill_root / "evals"
        evals_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text(
            "\n".join(
                (
                    "---",
                    f"name: {name}",
                    f"description: Use when testing {name}.",
                    "---",
                    "",
                    f"# {name}",
                    "",
                )
            ),
            encoding="utf-8",
        )
        document = trigger_document or {
            "skill_name": name,
            "queries": [
                {
                    "id": f"{name}-positive",
                    "query": f"Use the {name} workflow.",
                    "should_trigger": True,
                },
                {
                    "id": f"{name}-negative",
                    "query": "Summarize this unrelated note.",
                    "should_trigger": False,
                },
            ],
        }
        (evals_root / "triggers.json").write_text(
            json.dumps(document),
            encoding="utf-8",
        )
        return skill_root


def completed_execution(request: HarnessRequest, *, activated: bool) -> HarnessExecution:
    expected_path = Path(
        f"/sandbox/codex-home/skills/{request.expected_skill}/SKILL.md"
    )
    reads = (expected_path,) if activated else ()
    trace = (
        (
            {
                "type": "skill_read",
                "path": str(expected_path),
                "status": "completed",
            },
        )
        if activated
        else ({"type": "turn.completed"},)
    )
    return HarnessExecution(
        response="Actor response",
        trace=trace,
        duration_ms=50,
        total_tokens=10,
        input_tokens=6,
        output_tokens=4,
        cached_tokens=0,
        token_source="fake",
        successful_skill_reads=reads,
        exit_code=0,
        failure=None,
        model="fake-model",
        reasoning_effort="medium",
        timed_out=False,
        expected_skill_path=expected_path,
    )


class FakeTriggerHarness:
    def __init__(self, activations: list[bool] | None = None) -> None:
        self.activations = list(activations or [])
        self.requests: list[HarnessRequest] = []

    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        return HarnessCapabilities(
            harness_name="codex",
            available=True,
            actor_model="fake-model",
            actor_reasoning_effort="medium",
            judge_model="fake-model",
            judge_reasoning_effort="medium",
            reports_token_usage=True,
            reports_successful_skill_reads=True,
        )

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        self.requests.append(request)
        activated = self.activations.pop(0) if self.activations else "unrelated" not in request.prompt
        return completed_execution(request, activated=activated)


class TriggerDefinitionValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository = TemporaryTriggerRepository(Path(self.temporary_directory.name))

    def test_one_generic_validator_discovers_and_accepts_valid_skill_queries(self) -> None:
        self.repository.add_skill("alpha")
        self.repository.add_skill("beta", group="integrations")

        self.assertEqual(validate_trigger_query_files(self.repository.root), [])

    def test_skill_name_must_match_the_discovered_skill(self) -> None:
        self.repository.add_skill(
            "alpha",
            trigger_document={
                "skill_name": "beta",
                "queries": [
                    {"id": "positive", "query": "Use alpha.", "should_trigger": True},
                    {"id": "negative", "query": "Do not use alpha.", "should_trigger": False},
                ],
            },
        )

        issues = validate_trigger_query_files(self.repository.root)

        self.assertEqual(len(issues), 1)
        self.assertIn("must match skill name 'alpha'", issues[0].message)

    def test_query_ids_must_be_unique(self) -> None:
        self.repository.add_skill(
            "alpha",
            trigger_document={
                "skill_name": "alpha",
                "queries": [
                    {"id": "same", "query": "Use alpha.", "should_trigger": True},
                    {"id": "same", "query": "Do not use alpha.", "should_trigger": False},
                ],
            },
        )

        issues = validate_trigger_query_files(self.repository.root)

        self.assertEqual(len(issues), 1)
        self.assertIn("duplicate query id 'same'", issues[0].message)

    def test_schema_requires_positive_and_negative_queries(self) -> None:
        self.repository.add_skill(
            "alpha",
            trigger_document={
                "skill_name": "alpha",
                "queries": [
                    {"id": "positive", "query": "Use alpha.", "should_trigger": True}
                ],
            },
        )

        messages = [issue.message for issue in validate_trigger_query_files(self.repository.root)]

        self.assertTrue(any("should_trigger" in message for message in messages))

    def test_schema_rejects_authored_repetition_configuration(self) -> None:
        self.repository.add_skill(
            "alpha",
            trigger_document={
                "skill_name": "alpha",
                "queries": [
                    {
                        "id": "positive",
                        "query": "Use alpha.",
                        "should_trigger": True,
                        "runs_per_query": 3,
                    },
                    {"id": "negative", "query": "Do not use alpha.", "should_trigger": False},
                ],
            },
        )

        messages = [issue.message for issue in validate_trigger_query_files(self.repository.root)]

        self.assertTrue(any("additionalProperties" in message for message in messages))

    def test_schema_rejects_whitespace_only_queries(self) -> None:
        self.repository.add_skill(
            "alpha",
            trigger_document={
                "skill_name": "alpha",
                "queries": [
                    {"id": "positive", "query": "   ", "should_trigger": True},
                    {"id": "negative", "query": "Unrelated work.", "should_trigger": False},
                ],
            },
        )

        messages = [issue.message for issue in validate_trigger_query_files(self.repository.root)]

        self.assertTrue(any("pattern" in message for message in messages))

    def test_validated_loader_returns_typed_queries_for_every_skill(self) -> None:
        self.repository.add_skill("alpha")
        self.repository.add_skill("beta", group="integrations")

        definitions = load_trigger_queries(self.repository.root)

        self.assertEqual([definition.skill.name for definition in definitions], ["beta", "alpha"])
        self.assertEqual(definitions[0].queries[0].id, "beta-positive")

    def test_loader_discovers_and_reads_each_skill_in_one_pass(self) -> None:
        self.repository.add_skill("alpha")

        with patch.object(
            trigger_definitions,
            "discover_testable_skills",
            wraps=trigger_definitions.discover_testable_skills,
        ) as discover:
            load_trigger_queries(self.repository.root)

        discover.assert_called_once_with(self.repository.root)

    def test_discovery_failure_becomes_a_definition_error(self) -> None:
        skill = self.repository.add_skill("alpha")
        (skill / "SKILL.md").write_text("missing frontmatter", encoding="utf-8")

        with self.assertRaises(TriggerDefinitionError) as raised:
            load_trigger_queries(self.repository.root)

        self.assertTrue(raised.exception.issues)
        self.assertIn("cannot discover skills", raised.exception.issues[0].message)

    def test_trigger_file_must_be_a_contained_non_symlink_regular_file(self) -> None:
        skill = self.repository.add_skill("alpha")
        trigger_path = skill / "evals" / "triggers.json"
        outside = self.repository.root / "outside.json"
        outside.write_text(trigger_path.read_text(encoding="utf-8"), encoding="utf-8")
        trigger_path.unlink()
        trigger_path.symlink_to(outside)

        messages = [issue.message for issue in validate_trigger_query_files(self.repository.root)]

        self.assertTrue(any("contained non-symlink regular file" in message for message in messages))

    def test_secret_bearing_trigger_query_fails_without_echoing_the_value(self) -> None:
        secret = "sk-" + "A" * 30
        self.repository.add_skill(
            "alpha",
            trigger_document={
                "skill_name": "alpha",
                "queries": [
                    {
                        "id": "positive",
                        "query": f"Use alpha with {secret}.",
                        "should_trigger": True,
                    },
                    {"id": "negative", "query": "Unrelated work.", "should_trigger": False},
                ],
            },
        )

        issues = validate_trigger_query_files(self.repository.root)

        self.assertTrue(any("high-confidence secret" in issue.message for issue in issues))
        self.assertNotIn(secret, repr(issues))


class TriggerClassificationTests(unittest.TestCase):
    def test_unanimous_matching_runs_are_stable(self) -> None:
        for run_count in (1, 2, 3):
            attempts = tuple(
                TriggerAttemptOutcome(activated=True, matched_expectation=True)
                for _ in range(run_count)
            )
            with self.subTest(run_count=run_count):
                result = classify_trigger_attempts(attempts, run_count)
                self.assertEqual(result.status, "pass_stable")

    def test_two_of_three_is_unstable_but_meets_the_threshold(self) -> None:
        result = classify_trigger_attempts(
            (
                TriggerAttemptOutcome(activated=True, matched_expectation=True),
                TriggerAttemptOutcome(activated=False, matched_expectation=False),
                TriggerAttemptOutcome(activated=True, matched_expectation=True),
            ),
            3,
        )

        self.assertEqual(result.status, "pass_unstable")
        self.assertEqual(result.matching_runs, 2)

    def test_non_unanimous_two_run_result_fails(self) -> None:
        result = classify_trigger_attempts(
            (
                TriggerAttemptOutcome(activated=True, matched_expectation=True),
                TriggerAttemptOutcome(activated=False, matched_expectation=False),
            ),
            2,
        )

        self.assertEqual(result.status, "fail")

    def test_execution_error_is_not_averaged_into_the_threshold(self) -> None:
        result = classify_trigger_attempts(
            (
                TriggerAttemptOutcome(activated=True, matched_expectation=True),
                TriggerAttemptOutcome(
                    activated=None,
                    matched_expectation=None,
                    error="sandbox failed",
                ),
                TriggerAttemptOutcome(activated=True, matched_expectation=True),
            ),
            3,
        )

        self.assertEqual(result.status, "error")


class TriggerExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository_directory = tempfile.TemporaryDirectory()
        self.results_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.repository_directory.cleanup)
        self.addCleanup(self.results_directory.cleanup)
        self.repository = TemporaryTriggerRepository(Path(self.repository_directory.name))

    def workspace(self):
        return create_result_workspace(
            "trigger-test",
            results_dir=Path(self.results_directory.name) / "results",
            repository_root=self.repository.root,
        )

    def test_filters_select_cases_without_reducing_the_installed_catalog(self) -> None:
        alpha = self.repository.add_skill("alpha")
        beta = self.repository.add_skill("beta", group="integrations")
        adapter = FakeTriggerHarness([True])

        result = execute_trigger_queries(
            self.repository.root,
            adapter,
            self.workspace(),
            runs=1,
            max_concurrency=1,
            skill_filter="alpha",
            query_filter="alpha-positive",
        )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(adapter.requests), 1)
        request = adapter.requests[0]
        self.assertEqual(request.prompt, "Use the alpha workflow.")
        self.assertEqual(request.expected_skill, "alpha")
        self.assertEqual(set(request.skill_sources), {alpha, beta})

    def test_completed_run_writes_human_and_machine_reviewable_artifacts(self) -> None:
        self.repository.add_skill("alpha")
        adapter = FakeTriggerHarness([True])
        workspace = self.workspace()

        result = execute_trigger_queries(
            self.repository.root,
            adapter,
            workspace,
            runs=1,
            max_concurrency=1,
            query_filter="alpha-positive",
        )

        self.assertEqual(result.exit_code, 0)
        attempt = next(workspace.attempts.iterdir())
        grading = json.loads((attempt / "grading.json").read_text(encoding="utf-8"))
        timing = json.loads((attempt / "timing.json").read_text(encoding="utf-8"))
        self.assertEqual(grading["grader"]["type"], "deterministic")
        self.assertEqual(grading["assertion_results"][0]["checked_by"], "trigger_runner")
        self.assertTrue(grading["assertion_results"][0]["passed"])
        self.assertEqual(timing["run_kind"], "trigger")
        self.assertEqual((attempt / "outputs" / "response.md").read_text(), "Actor response")
        self.assertIn("Use the alpha workflow.", (attempt / "transcript.md").read_text())
        self.assertTrue((attempt / "execution_trace.jsonl").is_file())

    def test_durable_transcript_redacts_authored_fake_credentials(self) -> None:
        fake_value = "FAKE_trigger_test_token"
        self.repository.add_skill(
            "alpha",
            trigger_document={
                "skill_name": "alpha",
                "queries": [
                    {
                        "id": "alpha-positive",
                        "query": f"Use alpha with SERVICE_TOKEN={fake_value}.",
                        "should_trigger": True,
                    },
                    {
                        "id": "alpha-negative",
                        "query": "Summarize unrelated work.",
                        "should_trigger": False,
                    },
                ],
            },
        )
        workspace = self.workspace()

        execute_trigger_queries(
            self.repository.root,
            FakeTriggerHarness([True]),
            workspace,
            runs=1,
            max_concurrency=1,
            query_filter="alpha-positive",
        )

        attempt = next(workspace.attempts.iterdir())
        transcript = (attempt / "transcript.md").read_text(encoding="utf-8")
        self.assertNotIn(fake_value, transcript)
        self.assertIn("[REDACTED]", transcript)

    def test_negative_query_passes_when_exact_skill_read_is_absent(self) -> None:
        self.repository.add_skill("alpha")
        adapter = FakeTriggerHarness([False])

        result = execute_trigger_queries(
            self.repository.root,
            adapter,
            self.workspace(),
            runs=1,
            max_concurrency=1,
            query_filter="alpha-negative",
        )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.query_results[0].classification.status, "pass_stable")

    def test_unrelated_successful_skill_read_does_not_activate_the_target(self) -> None:
        self.repository.add_skill("alpha")

        class UnrelatedReadHarness(FakeTriggerHarness):
            def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
                execution = completed_execution(request, activated=False)
                return replace(
                    execution,
                    successful_skill_reads=(
                        Path("/sandbox/codex-home/skills/beta/SKILL.md"),
                    ),
                )

        result = execute_trigger_queries(
            self.repository.root,
            UnrelatedReadHarness(),
            self.workspace(),
            runs=1,
            max_concurrency=1,
            query_filter="alpha-positive",
        )

        self.assertEqual(result.exit_code, 1)

    def test_activation_evidence_cites_the_exact_expected_skill_read(self) -> None:
        self.repository.add_skill("alpha")

        class ExpectedReadAfterUnrelatedHarness(FakeTriggerHarness):
            def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
                execution = completed_execution(request, activated=True)
                assert execution.expected_skill_path is not None
                return replace(
                    execution,
                    successful_skill_reads=(
                        Path("/sandbox/codex-home/skills/beta/SKILL.md"),
                        execution.expected_skill_path,
                    ),
                )

        workspace = self.workspace()
        result = execute_trigger_queries(
            self.repository.root,
            ExpectedReadAfterUnrelatedHarness(),
            workspace,
            runs=1,
            max_concurrency=1,
            query_filter="alpha-positive",
        )

        attempt = next(workspace.attempts.iterdir())
        grading = json.loads((attempt / "grading.json").read_text(encoding="utf-8"))
        evidence = grading["assertion_results"][0]["evidence"]
        self.assertEqual(result.exit_code, 0)
        self.assertIn("/alpha/SKILL.md", evidence)
        self.assertNotIn("/beta/SKILL.md", evidence)

    def test_missing_expected_installed_path_is_an_evidence_error(self) -> None:
        self.repository.add_skill("alpha")

        class MissingExpectedPathHarness(FakeTriggerHarness):
            def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
                return replace(
                    completed_execution(request, activated=False),
                    expected_skill_path=None,
                )

        workspace = self.workspace()
        result = execute_trigger_queries(
            self.repository.root,
            MissingExpectedPathHarness(),
            workspace,
            runs=1,
            max_concurrency=1,
            query_filter="alpha-negative",
        )

        attempt = next(workspace.attempts.iterdir())
        timing = json.loads((attempt / "timing.json").read_text(encoding="utf-8"))
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(timing["status"], "failed")
        self.assertFalse((attempt / "grading.json").exists())

    def test_two_of_three_is_reported_as_unstable_without_hidden_retry(self) -> None:
        self.repository.add_skill("alpha")
        adapter = FakeTriggerHarness([True, False, True])
        workspace = self.workspace()

        result = execute_trigger_queries(
            self.repository.root,
            adapter,
            workspace,
            runs=3,
            max_concurrency=1,
            query_filter="alpha-positive",
        )
        benchmark = aggregate_results(
            workspace.root,
            "judge",
            repository_root=self.repository.root,
        )

        self.assertEqual(len(adapter.requests), 3)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.query_results[0].classification.status, "pass_unstable")
        self.assertEqual(benchmark_exit_code(benchmark), 0)
        self.assertEqual(
            benchmark["source_summaries"]["judge"]["summary"],
            {
                "total_cases": 1,
                "passed_cases": 1,
                "failed_cases": 0,
                "pass_rate": 1.0,
            },
        )
        skill_summary = benchmark["source_summaries"]["judge"]["skill_summaries"][0]
        self.assertEqual(skill_summary["skill_name"], "alpha")
        self.assertEqual(skill_summary["measurements"]["trigger_rate"]["count"], 3)
        self.assertAlmostEqual(
            skill_summary["measurements"]["trigger_rate"]["mean"],
            2 / 3,
        )
        self.assertIn("trigger_rate", workspace.output_summary.read_text(encoding="utf-8"))
        human_summary = format_trigger_summary(result)
        self.assertIn("INVESTIGATE", human_summary)
        self.assertIn("run 2: mismatch", human_summary)
        self.assertIn("artifacts=", human_summary)

    def test_aggregation_rejects_a_missing_configured_trigger_attempt(self) -> None:
        self.repository.add_skill("alpha")
        workspace = self.workspace()
        execute_trigger_queries(
            self.repository.root,
            FakeTriggerHarness([True, False, True]),
            workspace,
            runs=3,
            max_concurrency=1,
            query_filter="alpha-positive",
        )
        attempts = list(workspace.attempts.iterdir())
        manifests = [
            json.loads((attempt / "attempt.json").read_text(encoding="utf-8"))
            for attempt in attempts
        ]
        self.assertEqual(
            sorted(manifest["aggregation"]["run_number"] for manifest in manifests),
            [1, 2, 3],
        )
        self.assertTrue(
            all(manifest["aggregation"]["configured_runs"] == 3 for manifest in manifests)
        )
        failed_attempt = next(
            attempt
            for attempt in attempts
            if not json.loads((attempt / "grading.json").read_text(encoding="utf-8"))[
                "assertion_results"
            ][0]["passed"]
        )
        failed_run_id = json.loads(
            (failed_attempt / "attempt.json").read_text(encoding="utf-8")
        )["run_id"]
        shutil.rmtree(failed_attempt)
        invocation = json.loads(
            workspace.invocation_manifest.read_text(encoding="utf-8")
        )
        invocation["attempts"] = [
            attempt
            for attempt in invocation["attempts"]
            if attempt["run_id"] != failed_run_id
        ]
        workspace.invocation_manifest.write_text(
            json.dumps(invocation),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ResultArtifactError, "configured run set"):
            aggregate_results(
                workspace.root,
                "judge",
                repository_root=self.repository.root,
            )

    def test_invocation_manifest_prevents_deleting_an_entire_query_group(self) -> None:
        self.repository.add_skill("alpha")
        workspace = self.workspace()
        execute_trigger_queries(
            self.repository.root,
            FakeTriggerHarness([True, False]),
            workspace,
            runs=1,
            max_concurrency=1,
        )
        self.assertTrue(workspace.invocation_manifest.is_file())
        negative_attempt = next(
            attempt
            for attempt in workspace.attempts.iterdir()
            if json.loads((attempt / "attempt.json").read_text(encoding="utf-8"))[
                "case_id"
            ]
            == "alpha-negative"
        )
        shutil.rmtree(negative_attempt)

        with self.assertRaisesRegex(ResultArtifactError, "invocation manifest"):
            aggregate_results(
                workspace.root,
                "judge",
                repository_root=self.repository.root,
            )

    def test_harness_failure_preserves_incomplete_evidence_and_returns_error(self) -> None:
        self.repository.add_skill("alpha")

        class FailingHarness(FakeTriggerHarness):
            def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
                self.requests.append(request)
                return HarnessExecution(
                    response="Partial actor response",
                    trace=({"type": "turn.failed", "message": "native failure"},),
                    duration_ms=25,
                    total_tokens=None,
                    input_tokens=None,
                    output_tokens=None,
                    cached_tokens=None,
                    token_source="unavailable",
                    successful_skill_reads=(),
                    exit_code=1,
                    failure="native failure",
                    model="fake-model",
                    reasoning_effort="medium",
                    timed_out=False,
                )

        workspace = self.workspace()
        result = execute_trigger_queries(
            self.repository.root,
            FailingHarness(),
            workspace,
            runs=1,
            max_concurrency=1,
            query_filter="alpha-positive",
        )

        attempt = next(workspace.attempts.iterdir())
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.query_results[0].classification.status, "error")
        self.assertTrue((attempt / "timing.json").is_file())
        self.assertFalse((attempt / "grading.json").exists())
        human_summary = format_trigger_summary(result)
        self.assertIn("run 1: error", human_summary)
        self.assertIn("native failure", human_summary)

    def test_adapter_exception_is_preserved_as_an_incomplete_attempt(self) -> None:
        self.repository.add_skill("alpha")

        class RaisingHarness(FakeTriggerHarness):
            def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
                raise RuntimeError("native setup failure")

        workspace = self.workspace()
        result = execute_trigger_queries(
            self.repository.root,
            RaisingHarness(),
            workspace,
            runs=1,
            max_concurrency=1,
            query_filter="alpha-positive",
        )

        attempt = next(workspace.attempts.iterdir())
        timing = json.loads((attempt / "timing.json").read_text(encoding="utf-8"))
        trace = (attempt / "execution_trace.jsonl").read_text(encoding="utf-8")
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(timing["status"], "failed")
        self.assertIn("native setup failure", trace)
        self.assertFalse((attempt / "grading.json").exists())

    def test_preflight_requires_deterministic_skill_read_evidence(self) -> None:
        self.repository.add_skill("alpha")

        class UnsupportedHarness(FakeTriggerHarness):
            def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
                return HarnessCapabilities(
                    harness_name="claude",
                    available=True,
                    actor_model="fake-model",
                    actor_reasoning_effort="medium",
                    judge_model="fake-model",
                    judge_reasoning_effort="medium",
                    reports_token_usage=True,
                    reports_successful_skill_reads=False,
                )

        with self.assertRaisesRegex(TriggerHarnessError, "skill-read evidence"):
            execute_trigger_queries(
                self.repository.root,
                UnsupportedHarness(),
                self.workspace(),
                runs=1,
                max_concurrency=1,
            )


class TriggerCliTests(unittest.TestCase):
    def test_model_runner_stops_on_static_trust_boundary_issues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = StringIO()
            with (
                patch.object(
                    trigger_validation,
                    "run_static_validation",
                    return_value=[
                        ValidationIssue(scope="skills/alpha", message="unsafe topology")
                    ],
                    create=True,
                ),
                patch.object(trigger_validation, "create_result_workspace") as create_results,
                redirect_stdout(output),
            ):
                result = trigger_validation.run_trigger_query_harness(
                    root,
                    harness="codex",
                    runs=1,
                    skill_filter=None,
                    query_filter=None,
                    results_dir=None,
                    max_concurrency=2,
                )

        self.assertEqual(result, 2)
        create_results.assert_not_called()
        self.assertIn("unsafe topology", output.getvalue())

    def test_trigger_command_requires_harness_and_exposes_bounded_runner_options(self) -> None:
        parser = build_parser()

        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["validate", "triggers"])
        args = parser.parse_args(
            [
                "validate",
                "triggers",
                "--harness",
                "codex",
                "--runs",
                "3",
                "--max-concurrency",
                "4",
                "--skill",
                "alpha",
                "--query",
                "alpha-positive",
                "--results-dir",
                "/tmp/trigger-results",
            ]
        )

        self.assertEqual(args.harness, "codex")
        self.assertEqual(args.runs, 3)
        self.assertEqual(args.max_concurrency, 4)
        self.assertEqual(args.skill, "alpha")
        self.assertEqual(args.query, "alpha-positive")
        self.assertEqual(args.results_dir, Path("/tmp/trigger-results"))

    def test_post_workspace_harness_failure_writes_terminal_summary(self) -> None:
        with (
            tempfile.TemporaryDirectory() as repository_directory,
            tempfile.TemporaryDirectory() as results_directory,
        ):
            repository = TemporaryTriggerRepository(Path(repository_directory))
            repository.add_skill("alpha")
            results = Path(results_directory) / "run"
            runtime = MagicMock()
            manifest = SimpleNamespace(
                limits=SimpleNamespace(
                    maximum_captured_output_bytes=4096,
                    actor_timeout_seconds=60,
                )
            )
            with (
                patch.object(trigger_validation, "run_static_validation", return_value=[]),
                patch(
                    "scripts.ai_skills_lib.sandbox_runtime.EvalRuntimeManifest.load",
                    return_value=manifest,
                ),
                patch(
                    "scripts.ai_skills_lib.sandbox_runtime.SandboxRuntime",
                    return_value=runtime,
                ),
                patch("scripts.ai_skills_lib.codex_harness.CodexHarnessAdapter"),
                patch.object(
                    trigger_validation,
                    "_execute_trigger_queries",
                    side_effect=TriggerHarnessError("preflight unavailable"),
                ),
                redirect_stdout(StringIO()),
            ):
                result = trigger_validation.run_trigger_query_harness(
                    repository.root,
                    harness="codex",
                    runs=1,
                    skill_filter=None,
                    query_filter=None,
                    results_dir=results,
                    max_concurrency=1,
                )

            summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn("preflight unavailable", summary)
            self.assertIn("Decision: execution error", summary)
            self.assertFalse((results / "benchmark.json").exists())

    def test_errored_trigger_attempt_summary_links_its_artifacts(self) -> None:
        with (
            tempfile.TemporaryDirectory() as repository_directory,
            tempfile.TemporaryDirectory() as results_directory,
        ):
            repository = TemporaryTriggerRepository(Path(repository_directory))
            repository.add_skill("alpha")
            results = Path(results_directory) / "run"
            runtime = MagicMock()
            manifest = SimpleNamespace(
                limits=SimpleNamespace(
                    maximum_captured_output_bytes=4096,
                    actor_timeout_seconds=60,
                )
            )

            def errored_suite(*args, **kwargs):
                workspace = args[2]
                artifact_dir = workspace.attempts / "alpha-positive-run-1"
                artifact_dir.mkdir()
                return trigger_validation.TriggerSuiteResult(
                    query_results=(
                        trigger_validation.TriggerQueryResult(
                            skill_name="alpha",
                            query_id="alpha-positive",
                            should_trigger=True,
                            classification=trigger_validation.TriggerQueryClassification(
                                status="error",
                                matching_runs=0,
                                completed_runs=0,
                                configured_runs=1,
                            ),
                            attempts=(
                                TriggerAttemptOutcome(
                                    activated=None,
                                    matched_expectation=None,
                                    error="actor failed",
                                    run_number=1,
                                    artifact_dir=artifact_dir,
                                ),
                            ),
                        ),
                    )
                )

            with (
                patch.object(trigger_validation, "run_static_validation", return_value=[]),
                patch(
                    "scripts.ai_skills_lib.sandbox_runtime.EvalRuntimeManifest.load",
                    return_value=manifest,
                ),
                patch(
                    "scripts.ai_skills_lib.sandbox_runtime.SandboxRuntime",
                    return_value=runtime,
                ),
                patch("scripts.ai_skills_lib.codex_harness.CodexHarnessAdapter"),
                patch.object(
                    trigger_validation,
                    "_execute_trigger_queries",
                    side_effect=errored_suite,
                ),
                redirect_stdout(StringIO()),
            ):
                result = trigger_validation.run_trigger_query_harness(
                    repository.root,
                    harness="codex",
                    runs=1,
                    skill_filter=None,
                    query_filter=None,
                    results_dir=results,
                    max_concurrency=1,
                )

            summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn("actor failed", summary)
            self.assertIn(str(results / "attempts" / "alpha-positive-run-1"), summary)
            self.assertFalse((results / "benchmark.json").exists())

    def test_aggregation_failure_replaces_partial_summary_with_terminal_error(self) -> None:
        with (
            tempfile.TemporaryDirectory() as repository_directory,
            tempfile.TemporaryDirectory() as results_directory,
        ):
            repository = TemporaryTriggerRepository(Path(repository_directory))
            repository.add_skill("alpha")
            results = Path(results_directory) / "run"
            runtime = MagicMock()
            manifest = SimpleNamespace(
                limits=SimpleNamespace(
                    maximum_captured_output_bytes=4096,
                    actor_timeout_seconds=60,
                )
            )
            suite = trigger_validation.TriggerSuiteResult(
                query_results=(
                    trigger_validation.TriggerQueryResult(
                        skill_name="alpha",
                        query_id="alpha-positive",
                        should_trigger=True,
                        classification=trigger_validation.TriggerQueryClassification(
                            status="pass_stable",
                            matching_runs=1,
                            completed_runs=1,
                            configured_runs=1,
                        ),
                        attempts=(
                            TriggerAttemptOutcome(
                                activated=True,
                                matched_expectation=True,
                                run_number=1,
                            ),
                        ),
                    ),
                )
            )

            with (
                patch.object(trigger_validation, "run_static_validation", return_value=[]),
                patch(
                    "scripts.ai_skills_lib.sandbox_runtime.EvalRuntimeManifest.load",
                    return_value=manifest,
                ),
                patch(
                    "scripts.ai_skills_lib.sandbox_runtime.SandboxRuntime",
                    return_value=runtime,
                ),
                patch("scripts.ai_skills_lib.codex_harness.CodexHarnessAdapter"),
                patch.object(
                    trigger_validation,
                    "_execute_trigger_queries",
                    return_value=suite,
                ),
                patch.object(
                    trigger_validation,
                    "aggregate_results",
                    side_effect=ResultArtifactError("incomplete attempt set"),
                ),
                redirect_stdout(StringIO()),
            ):
                result = trigger_validation.run_trigger_query_harness(
                    repository.root,
                    harness="codex",
                    runs=1,
                    skill_filter=None,
                    query_filter=None,
                    results_dir=results,
                    max_concurrency=1,
                )

            summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn("aggregation failed: incomplete attempt set", summary)
            self.assertIn("Decision: execution error", summary)
            self.assertFalse((results / "benchmark.json").exists())

    def test_cli_dispatches_trigger_runner_without_running_a_model_in_unit_tests(self) -> None:
        with patch.object(cli, "run_trigger_query_harness", return_value=1) as run:
            result = cli.main(
                [
                    "validate",
                    "triggers",
                    "--harness",
                    "codex",
                    "--runs",
                    "2",
                    "--max-concurrency",
                    "3",
                    "--skill",
                    "alpha",
                    "--query",
                    "alpha-positive",
                ]
            )

        self.assertEqual(result, 1)
        run.assert_called_once_with(
            cli.REPOSITORY_ROOT,
            harness="codex",
            runs=2,
            skill_filter="alpha",
            query_filter="alpha-positive",
            results_dir=None,
            max_concurrency=3,
        )


if __name__ == "__main__":
    unittest.main()
