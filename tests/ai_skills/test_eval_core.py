from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

import scripts.ai_skills as cli
import scripts.ai_skills_lib.eval_core as eval_core
from scripts.ai_skills_lib.config import build_parser
from scripts.ai_skills_lib.eval_core import (
    AggregationMetadata,
    AssertionDefinition,
    AssertionResult,
    AttemptManifest,
    AttemptPaths,
    EvalRunRecord,
    GraderRecord,
    GradingRecord,
    GradingSummary,
    JudgeGradingContext,
    JudgeExecutionError,
    JudgeInvocationResult,
    ResultWorkspace,
    ResultArtifactError,
    TimingRecord,
    aggregate_results,
    benchmark_exit_code,
    combine_grading_results,
    create_attempt_workspace,
    create_result_workspace,
    default_results_root,
    format_benchmark_summary,
    invoke_judge,
    parse_judge_response,
    record_harness_timing,
    validate_result_document,
    write_incomplete_attempt_artifacts,
    write_eval_run_artifacts,
)
from scripts.ai_skills_lib.harness import HarnessExecution, HarnessRequest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas" / "ai-skills"


def load_schema(name: str) -> dict[str, object]:
    path = SCHEMA_ROOT / name
    if not path.is_file():
        raise AssertionError(f"missing offline result schema: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def sample_timing() -> dict[str, object]:
    return {
        "schema_version": "ai-skills.eval.timing.v1",
        "run_id": "run-with-skill",
        "skill_name": "ticket-workflow",
        "case_id": "intake",
        "run_kind": "with_skill",
        "harness": "codex",
        "model": "reported-model",
        "reasoning_effort": "medium",
        "started_at": "2026-07-19T10:00:00Z",
        "ended_at": "2026-07-19T10:00:01Z",
        "duration_ms": 1000,
        "total_tokens": None,
        "status": "completed",
        "exit_code": 0,
        "token_details": {
            "input": None,
            "output": None,
            "cached": None,
            "source": "unavailable",
        },
    }


def sample_grading(
    *,
    grade_source: str = "judge",
    grader_type: str = "llm",
) -> dict[str, object]:
    return {
        "schema_version": "ai-skills.eval.grading.v1",
        "run_id": "run-with-skill",
        "skill_name": "ticket-workflow",
        "case_id": "intake",
        "run_kind": "with_skill",
        "grade_source": grade_source,
        "grader": {
            "type": grader_type,
            "model": "reported-model" if grader_type == "llm" else None,
            "reasoning_effort": "high" if grader_type == "llm" else None,
            "prompt_version": "agent-skills-eval-v1",
        },
        "graded_at": "2026-07-19T10:00:02Z",
        "assertion_results": [
            {
                "id": "assertion-1",
                "kind": "assertion",
                "text": "The response identifies missing ticket context.",
                "passed": True,
                "checked_by": "judge" if grader_type == "llm" else "human",
                "evidence": "The response requests acceptance criteria.",
                "evidence_refs": [
                    {"artifact": "outputs/response.md", "locator": "paragraph 1"}
                ],
            }
        ],
        "summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0},
        "aggregation": {
            "group_id": "ticket-workflow/intake",
            "variant": "with_skill",
            "contributes_to_outcome": True,
            "required_variants": ["with_skill", "without_skill"],
            "compare_to": "without_skill",
        },
    }


def sample_benchmark() -> dict[str, object]:
    source_summary = {
        "summary": {
            "total_cases": 1,
            "passed_cases": 1,
            "failed_cases": 0,
            "pass_rate": 1.0,
        },
        "groups": [
            {
                "group_id": "ticket-workflow/intake",
                "skill_name": "ticket-workflow",
                "case_id": "intake",
                "variants": {
                    "with_skill": {
                        "runs": 1,
                        "passed": 1,
                        "failed": 0,
                        "pass_rate": 1.0,
                        "duration_ms_total": 1000,
                        "total_tokens": None,
                    },
                    "without_skill": {
                        "runs": 1,
                        "passed": 0,
                        "failed": 1,
                        "pass_rate": 0.0,
                        "duration_ms_total": 900,
                        "total_tokens": None,
                    },
                },
                "comparisons": [
                    {
                        "variant": "with_skill",
                        "baseline_variant": "without_skill",
                        "pass_rate_delta": 1.0,
                        "investigation_required": False,
                    }
                ],
            }
        ],
    }
    return {
        "schema_version": "ai-skills.eval.benchmark.v1",
        "generated_at": "2026-07-19T10:00:03Z",
        "grade_source": "judge",
        "source_summaries": {"judge": source_summary},
    }


def sample_judge_response() -> dict[str, object]:
    return {
        "assertion_results": [
            {
                "id": "assertion-1",
                "passed": True,
                "evidence": "The response requests acceptance criteria.",
                "evidence_refs": [
                    {"artifact": "outputs/response.md", "locator": "paragraph 1"}
                ],
            }
        ]
    }


class EvalArtifactSchemaTests(unittest.TestCase):
    def test_runtime_requirements_pin_jsonschema(self):
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("jsonschema==4.26.0", requirements.splitlines())

    def test_timing_schema_accepts_unavailable_token_counts(self):
        validator = Draft202012Validator(load_schema("timing.schema.json"))

        validator.validate(sample_timing())

    def test_grading_schema_preserves_guide_assertion_fields(self):
        validator = Draft202012Validator(load_schema("grading.schema.json"))
        grading = sample_grading()

        validator.validate(grading)
        for field in ("text", "passed", "evidence"):
            with self.subTest(field=field):
                invalid = copy.deepcopy(grading)
                del invalid["assertion_results"][0][field]
                with self.assertRaises(ValidationError):
                    validator.validate(invalid)

    def test_manual_and_generated_grading_share_one_schema(self):
        validator = Draft202012Validator(load_schema("grading.schema.json"))

        validator.validate(sample_grading())
        validator.validate(sample_grading(grade_source="manual", grader_type="human"))

    def test_llm_grading_requires_durable_model_and_reasoning_metadata(self):
        validator = Draft202012Validator(load_schema("grading.schema.json"))
        for field in ("model", "reasoning_effort"):
            invalid = sample_grading()
            invalid["grader"][field] = None
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    validator.validate(invalid)

        empty = sample_grading()
        empty["assertion_results"] = []
        empty["summary"] = {"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0}
        with self.assertRaises(ValidationError):
            validator.validate(empty)

    def test_benchmark_schema_accepts_generic_variant_and_comparison_summaries(self):
        validator = Draft202012Validator(load_schema("benchmark.schema.json"))

        validator.validate(sample_benchmark())

    def test_benchmark_schema_requires_exactly_the_declared_grade_sources(self):
        validator = Draft202012Validator(load_schema("benchmark.schema.json"))
        judge = sample_benchmark()
        manual_summary = copy.deepcopy(judge["source_summaries"]["judge"])
        invalid_documents = (
            judge | {"source_summaries": {"manual": manual_summary}},
            judge
            | {
                "grade_source": "manual",
                "source_summaries": {"judge": judge["source_summaries"]["judge"]},
            },
            judge
            | {
                "grade_source": "both",
                "source_summaries": {"judge": judge["source_summaries"]["judge"]},
            },
        )

        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(ValidationError):
                    validator.validate(document)

    def test_schema_validation_errors_do_not_echo_authored_values(self):
        secret_value = "FAKE_SECRET_VALUE_MUST_NOT_APPEAR"
        invalid = sample_grading()
        invalid["assertion_results"][0]["unexpected"] = secret_value

        with self.assertRaises(ResultArtifactError) as raised:
            validate_result_document(invalid, "grading.schema.json")

        message = str(raised.exception)
        self.assertNotIn(secret_value, message)
        self.assertRegex(message, r"grading\.schema\.json.*\$.*additionalProperties")

    def test_obsolete_grading_document_parser_is_removed(self):
        self.assertFalse(hasattr(eval_core, "_grading_record_from_dict"))


def generated_grading_record(
    *,
    run_id: str = "run-with-skill",
    run_kind: str = "with_skill",
    variant: str = "with_skill",
    contributes_to_outcome: bool = True,
    required_variants: tuple[str, ...] = ("with_skill", "without_skill"),
    compare_to: str | None = "without_skill",
    passed: bool = True,
) -> GradingRecord:
    return GradingRecord(
        run_id=run_id,
        skill_name="ticket-workflow",
        case_id="intake",
        run_kind=run_kind,
        grade_source="judge",
        grader=GraderRecord(
            type="llm",
            model="reported-model",
            reasoning_effort="high",
            prompt_version="agent-skills-eval-v1",
        ),
        graded_at="2026-07-19T10:00:02Z",
        assertion_results=(
            AssertionResult(
                id="assertion-1",
                kind="assertion",
                text="The response identifies missing ticket context.",
                passed=passed,
                checked_by="judge",
                evidence="The response requests acceptance criteria.",
                evidence_refs=(
                    {"artifact": "outputs/response.md", "locator": "paragraph 1"},
                ),
            ),
        ),
        summary=GradingSummary(
            passed=1 if passed else 0,
            failed=0 if passed else 1,
            total=1,
            pass_rate=1.0 if passed else 0.0,
        ),
        aggregation=AggregationMetadata(
            group_id="ticket-workflow/intake",
            variant=variant,
            contributes_to_outcome=contributes_to_outcome,
            required_variants=required_variants,
            compare_to=compare_to,
        ),
    )


def completed_harness_execution(*, with_usage: bool = True) -> HarnessExecution:
    return HarnessExecution(
        response="Please provide the acceptance criteria.",
        trace=({"event": "harness.completed", "exit_code": 0},),
        duration_ms=1000,
        total_tokens=12 if with_usage else None,
        input_tokens=8 if with_usage else None,
        output_tokens=4 if with_usage else None,
        cached_tokens=None,
        token_source="harness_report" if with_usage else "unavailable",
        successful_skill_reads=(),
        exit_code=0,
        failure=None,
        model="reported-model",
        reasoning_effort="medium",
        timed_out=False,
    )


def expected_judge_context() -> JudgeGradingContext:
    return JudgeGradingContext(
        run_id="run-with-skill",
        skill_name="ticket-workflow",
        case_id="intake",
        run_kind="with_skill",
        prompt_version="agent-skills-eval-v1",
        graded_at="2026-07-19T10:00:02Z",
        allowed_evidence_artifacts=(
            "outputs/response.md",
            "transcript.md",
            "execution_trace.jsonl",
        ),
        expected_assertions=(
            AssertionDefinition(
                id="assertion-1",
                kind="assertion",
                text="The response identifies missing ticket context.",
            ),
        ),
        aggregation=AggregationMetadata(
            group_id="ticket-workflow/intake",
            variant="with_skill",
            contributes_to_outcome=True,
            required_variants=("with_skill", "without_skill"),
            compare_to="without_skill",
        ),
    )


def sample_attempt_manifest(
    *,
    run_id: str = "run-candidate-1",
    variant: str = "candidate",
    contributes_to_outcome: bool = True,
    required_variants: tuple[str, ...] = ("candidate", "reference"),
    compare_to: str | None = "reference",
) -> AttemptManifest:
    return AttemptManifest(
        run_id=run_id,
        skill_name="ticket-workflow",
        case_id="intake",
        run_kind=variant,
        aggregation=AggregationMetadata(
            group_id="ticket-workflow/intake",
            variant=variant,
            contributes_to_outcome=contributes_to_outcome,
            required_variants=required_variants,
            compare_to=compare_to,
        ),
    )


def write_preserved_run(
    workspace: ResultWorkspace,
    *,
    run_id: str | None = None,
    variant: str,
    contributes_to_outcome: bool,
    passed: bool,
    required_variants: tuple[str, ...],
    compare_to: str | None = None,
) -> tuple[object, GradingRecord]:
    run_id = run_id or f"run-{variant}"
    execution = completed_harness_execution()
    timing = record_harness_timing(
        run_id=run_id,
        skill_name="ticket-workflow",
        case_id="intake",
        run_kind=variant,
        harness_name="codex",
        started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 7, 19, 10, 0, 1, tzinfo=timezone.utc),
        execution=execution,
    )
    grading = generated_grading_record(
        run_id=run_id,
        run_kind=variant,
        variant=variant,
        contributes_to_outcome=contributes_to_outcome,
        required_variants=required_variants,
        compare_to=compare_to,
        passed=passed,
    )
    paths = create_attempt_workspace(
        workspace,
        sample_attempt_manifest(
            run_id=run_id,
            variant=variant,
            contributes_to_outcome=contributes_to_outcome,
            required_variants=required_variants,
            compare_to=compare_to,
        ),
    )
    write_eval_run_artifacts(
        paths,
        EvalRunRecord(
            response=execution.response,
            transcript="# Transcript\n",
            execution_trace=execution.trace,
            timing=timing,
            grading=grading,
        ),
    )
    return paths, grading


def create_test_result_workspace(root: Path) -> ResultWorkspace:
    return create_result_workspace(
        "test evals",
        results_dir=root,
        repository_root=REPOSITORY_ROOT,
    )


def write_complete_manual_grading(paths, generated: GradingRecord, *, passed: bool) -> None:
    assertion = replace(
        generated.assertion_results[0],
        passed=passed,
        checked_by="human",
        evidence="Human review of the preserved response.",
    )
    manual = replace(
        generated,
        grade_source="manual",
        grader=GraderRecord(
            type="human",
            model=None,
            reasoning_effort=None,
            prompt_version="manual-review-v1",
        ),
        assertion_results=(assertion,),
        summary=GradingSummary(
            passed=1 if passed else 0,
            failed=0 if passed else 1,
            total=1,
            pass_rate=1.0 if passed else 0.0,
        ),
    )
    paths.manual_grading.write_text(
        f"{json.dumps(manual.to_dict(), indent=2)}\n",
        encoding="utf-8",
    )


class ResultWorkspaceTests(unittest.TestCase):
    def test_default_result_root_uses_xdg_or_local_state(self):
        self.assertEqual(
            default_results_root(environ={"XDG_STATE_HOME": "/tmp/custom-state"}),
            Path("/tmp/custom-state/ai-skills/results"),
        )
        self.assertEqual(
            default_results_root(environ={}, home=Path("/tmp/example-home")),
            Path("/tmp/example-home/.local/state/ai-skills/results"),
        )
        self.assertEqual(
            default_results_root(
                environ={"XDG_STATE_HOME": "relative-state"},
                home=Path("/tmp/example-home"),
            ),
            Path("/tmp/example-home/.local/state/ai-skills/results"),
        )

    def test_workspace_uses_external_default_and_explicit_override(self):
        now = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as state_directory:
            paths = create_result_workspace(
                "evals aggregate",
                environ={"XDG_STATE_HOME": state_directory},
                now=now,
            )
            expected_parent = (Path(state_directory) / "ai-skills/results").resolve()
            self.assertEqual(paths.root.parent, expected_parent)
            self.assertRegex(
                paths.root.name,
                r"^20260719T100000Z-evals-aggregate-[0-9a-f]{12}$",
            )
            self.assertTrue(paths.attempts.is_dir())
            self.assertFalse(paths.root.is_relative_to(REPOSITORY_ROOT))

            second = create_result_workspace(
                "evals aggregate",
                environ={"XDG_STATE_HOME": state_directory},
                now=now,
            )
            self.assertNotEqual(paths.root, second.root)

        with tempfile.TemporaryDirectory() as override_directory:
            override = Path(override_directory) / "preserved-results"
            paths = create_result_workspace("ignored", results_dir=override, now=now)
            self.assertEqual(paths.root, override.resolve())
            with self.assertRaisesRegex(ResultArtifactError, "already exists"):
                create_result_workspace("ignored", results_dir=override, now=now)

    def test_harness_timing_keeps_required_null_token_counts(self):
        timing = record_harness_timing(
            run_id="run-with-skill",
            skill_name="ticket-workflow",
            case_id="intake",
            run_kind="with_skill",
            harness_name="codex",
            started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 7, 19, 10, 0, 1, tzinfo=timezone.utc),
            execution=completed_harness_execution(with_usage=False),
        )

        self.assertIsNone(timing.total_tokens)
        self.assertIsNone(timing.token_details["input"])
        self.assertEqual(timing.duration_ms, 1000)
        self.assertEqual(timing.model, "reported-model")
        self.assertEqual(timing.reasoning_effort, "medium")
        with self.assertRaises(FrozenInstanceError):
            timing.duration_ms = 10

    def test_only_explicit_zero_harness_exit_with_model_metadata_is_completed(self):
        incomplete_executions = (
            replace(completed_harness_execution(), exit_code=2, failure=None),
            replace(completed_harness_execution(), exit_code=None, failure=None),
            replace(completed_harness_execution(), model=None),
            replace(completed_harness_execution(), reasoning_effort=None),
        )
        for execution in incomplete_executions:
            with self.subTest(execution=execution):
                timing = record_harness_timing(
                    run_id="run-failed",
                    skill_name="ticket-workflow",
                    case_id="intake",
                    run_kind="candidate",
                    harness_name="codex",
                    started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 7, 19, 10, 0, 1, tzinfo=timezone.utc),
                    execution=execution,
                )

                self.assertEqual(timing.status, "failed")

    def test_writes_schema_valid_human_and_machine_readable_run_artifacts(self):
        timing = record_harness_timing(
            run_id="run-with-skill",
            skill_name="ticket-workflow",
            case_id="intake",
            run_kind="with_skill",
            harness_name="codex",
            started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 7, 19, 10, 0, 1, tzinfo=timezone.utc),
            execution=completed_harness_execution(),
        )
        record = EvalRunRecord(
            response="Please provide the acceptance criteria.",
            transcript="# Prompt\nPerform intake.\n\n# Response\nPlease provide the criteria.\n",
            execution_trace=({"event": "harness.completed", "exit_code": 0},),
            timing=timing,
            grading=generated_grading_record(),
        )

        with tempfile.TemporaryDirectory() as directory:
            workspace = create_test_result_workspace(Path(directory) / "run")
            paths = create_attempt_workspace(
                workspace,
                sample_attempt_manifest(
                    run_id="run-with-skill",
                    variant="with_skill",
                    required_variants=("with_skill", "without_skill"),
                    compare_to="without_skill",
                ),
            )
            paths.manual_grading.write_text("manual review", encoding="utf-8")

            write_eval_run_artifacts(paths, record)

            self.assertEqual(paths.response.read_text(encoding="utf-8"), record.response)
            self.assertEqual(paths.transcript.read_text(encoding="utf-8"), record.transcript)
            trace_lines = paths.execution_trace.read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line) for line in trace_lines], list(record.execution_trace))
            Draft202012Validator(load_schema("timing.schema.json")).validate(
                json.loads(paths.timing.read_text(encoding="utf-8"))
            )
            Draft202012Validator(load_schema("grading.schema.json")).validate(
                json.loads(paths.grading.read_text(encoding="utf-8"))
            )
            self.assertEqual(paths.manual_grading.read_text(encoding="utf-8"), "manual review")

            with self.assertRaisesRegex(ResultArtifactError, "already exists"):
                write_eval_run_artifacts(paths, record)


class InvocationAttemptWorkspaceTests(unittest.TestCase):
    def test_invocation_and_attempt_workspaces_have_separate_owners(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            result_path = base / "state/results/invocation"

            workspace = create_result_workspace(
                "evals run",
                results_dir=result_path,
                repository_root=repository,
                now=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
            first = create_attempt_workspace(workspace, sample_attempt_manifest())
            second = create_attempt_workspace(workspace, sample_attempt_manifest())

            self.assertIsInstance(workspace, ResultWorkspace)
            self.assertIsInstance(first, AttemptPaths)
            self.assertEqual(workspace.benchmark, workspace.root / "benchmark.json")
            self.assertEqual(workspace.output_summary, workspace.root / "summary.md")
            self.assertEqual(first.root.parent, workspace.attempts)
            self.assertNotEqual(first.root, second.root)
            self.assertEqual(first.manifest, first.root / "attempt.json")
            manifest = json.loads(first.manifest.read_text(encoding="utf-8"))
            Draft202012Validator(load_schema("attempt.schema.json")).validate(manifest)
            self.assertEqual(manifest, sample_attempt_manifest().to_dict())
            self.assertFalse(first.timing.exists())

    def test_result_paths_inside_repository_or_through_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            inside = repository / "results"

            with self.assertRaisesRegex(ResultArtifactError, "outside the repository"):
                create_result_workspace(
                    "evals run",
                    results_dir=inside,
                    repository_root=repository,
                )

            symlink = base / "linked-repository"
            symlink.symlink_to(repository, target_is_directory=True)
            with self.assertRaisesRegex(ResultArtifactError, "outside the repository"):
                create_result_workspace(
                    "evals run",
                    results_dir=symlink / "results",
                    repository_root=repository,
                )

            with self.assertRaisesRegex(ResultArtifactError, "outside the repository"):
                create_result_workspace(
                    "evals run",
                    environ={"XDG_STATE_HOME": str(repository / "state")},
                    repository_root=repository,
                )

    def test_attempt_creation_revalidates_the_invocation_directory_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            workspace.attempts.rmdir()
            workspace.attempts.symlink_to(repository, target_is_directory=True)

            with self.assertRaisesRegex(ResultArtifactError, "attempts directory"):
                create_attempt_workspace(workspace, sample_attempt_manifest())

            forged_attempts = base / "different-invocation/attempts"
            forged_attempts.mkdir(parents=True)
            forged = replace(workspace, attempts=forged_attempts)
            with self.assertRaisesRegex(ResultArtifactError, "attempts directory"):
                create_attempt_workspace(forged, sample_attempt_manifest())

    def test_path_resolution_failure_is_a_result_artifact_error(self):
        with patch(
            "scripts.ai_skills_lib.eval_core.Path.resolve",
            side_effect=OSError("unresolvable path"),
        ):
            with self.assertRaisesRegex(ResultArtifactError, "cannot resolve result path"):
                create_result_workspace(
                    "evals run",
                    results_dir=Path("/tmp/result"),
                    repository_root=REPOSITORY_ROOT,
                )

    def test_incomplete_writer_preserves_available_evidence_without_a_grade(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            paths = create_attempt_workspace(workspace, sample_attempt_manifest())
            timing = replace(
                record_harness_timing(
                    run_id="run-candidate-1",
                    skill_name="ticket-workflow",
                    case_id="intake",
                    run_kind="candidate",
                    harness_name="codex",
                    started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 7, 19, 10, 0, 1, tzinfo=timezone.utc),
                    execution=completed_harness_execution(),
                ),
                status="failed",
                exit_code=2,
            )

            write_incomplete_attempt_artifacts(
                paths,
                response="partial response",
                transcript="# Partial transcript\n",
                execution_trace=({"event": "turn.failed"},),
                timing=timing,
            )

            self.assertEqual(paths.response.read_text(encoding="utf-8"), "partial response")
            self.assertIn("Partial transcript", paths.transcript.read_text(encoding="utf-8"))
            self.assertEqual(
                json.loads(paths.execution_trace.read_text(encoding="utf-8")),
                {"event": "turn.failed"},
            )
            self.assertEqual(
                json.loads(paths.timing.read_text(encoding="utf-8"))["status"],
                "failed",
            )
            self.assertFalse(paths.grading.exists())

    def test_trace_serialization_and_artifact_resolution_failures_are_untrustworthy(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            paths = create_attempt_workspace(workspace, sample_attempt_manifest())
            timing = replace(
                record_harness_timing(
                    run_id="run-candidate-1",
                    skill_name="ticket-workflow",
                    case_id="intake",
                    run_kind="candidate",
                    harness_name="codex",
                    started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
                    ended_at=datetime(2026, 7, 19, 10, 0, 1, tzinfo=timezone.utc),
                    execution=completed_harness_execution(),
                ),
                status="failed",
                exit_code=2,
            )

            with self.assertRaisesRegex(ResultArtifactError, "serialize.*trace"):
                write_incomplete_attempt_artifacts(
                    paths,
                    response="partial response",
                    transcript="# Partial transcript\n",
                    execution_trace=({"unsafe": object()},),
                    timing=timing,
                )
            self.assertEqual(
                json.loads(paths.timing.read_text(encoding="utf-8"))["status"],
                "failed",
            )
            self.assertEqual(paths.response.read_text(encoding="utf-8"), "partial response")
            self.assertIn("Partial transcript", paths.transcript.read_text(encoding="utf-8"))
            self.assertFalse(paths.grading.exists())

            fresh_paths = create_attempt_workspace(
                workspace,
                sample_attempt_manifest(run_id="run-candidate-2"),
            )
            with patch(
                "scripts.ai_skills_lib.eval_core.Path.resolve",
                side_effect=OSError("unresolvable artifact"),
            ):
                with self.assertRaisesRegex(ResultArtifactError, "resolve artifact path"):
                    write_incomplete_attempt_artifacts(
                        fresh_paths,
                        response="partial",
                        transcript=None,
                        execution_trace=(),
                        timing=replace(timing, run_id="run-candidate-2"),
                    )


class AggregationTests(unittest.TestCase):
    def test_generic_contribution_metadata_controls_outcome_and_variant_delta(self):
        required = ("candidate", "reference")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=False,
                required_variants=required,
                compare_to="reference",
            )
            write_preserved_run(
                workspace,
                variant="reference",
                contributes_to_outcome=False,
                passed=True,
                required_variants=required,
            )

            benchmark = aggregate_results(root, "judge")

            self.assertEqual(benchmark_exit_code(benchmark), 1)
            group = benchmark["source_summaries"]["judge"]["groups"][0]
            self.assertEqual(set(group["variants"]), {"candidate", "reference"})
            self.assertEqual(group["comparisons"][0]["pass_rate_delta"], -1.0)
            self.assertTrue(group["comparisons"][0]["investigation_required"])
            self.assertTrue((root / "benchmark.json").is_file())
            self.assertIn("candidate", (root / "summary.md").read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=required,
                compare_to="reference",
            )
            write_preserved_run(
                workspace,
                variant="reference",
                contributes_to_outcome=False,
                passed=False,
                required_variants=required,
            )

            self.assertEqual(benchmark_exit_code(aggregate_results(root, "judge")), 0)

    def test_aggregation_requires_every_caller_declared_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate", "reference"),
                compare_to="reference",
            )

            with self.assertRaisesRegex(ResultArtifactError, "missing required variants.*reference"):
                aggregate_results(root, "judge")

    def test_aggregation_rejects_an_attempt_with_timing_but_no_grade(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            incomplete_paths = create_attempt_workspace(
                workspace,
                sample_attempt_manifest(
                    run_id="incomplete-attempt",
                    variant="attempt",
                    required_variants=("attempt",),
                    compare_to=None,
                ),
            )
            timing = sample_timing() | {
                "run_id": "incomplete-attempt",
                "run_kind": "attempt",
                "model": "reported-model",
                "reasoning_effort": "medium",
                "status": "failed",
                "exit_code": 2,
            }
            incomplete_paths.timing.write_text(json.dumps(timing), encoding="utf-8")

            with self.assertRaisesRegex(ResultArtifactError, "grading.json"):
                aggregate_results(root, "judge")

    def test_aggregation_rejects_completed_timing_without_explicit_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            paths, _ = write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            timing = json.loads(paths.timing.read_text(encoding="utf-8"))
            timing["exit_code"] = None
            paths.timing.write_text(json.dumps(timing), encoding="utf-8")

            with self.assertRaisesRegex(ResultArtifactError, "explicit successful exit"):
                aggregate_results(root, "judge")

    def test_aggregation_is_anchored_to_attempt_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            paths, _ = write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            rogue = workspace.attempts / "rogue"
            rogue.mkdir()
            (rogue / "timing.json").write_bytes(paths.timing.read_bytes())
            (rogue / "grading.json").write_bytes(paths.grading.read_bytes())

            with self.assertRaisesRegex(ResultArtifactError, "attempt.json"):
                aggregate_results(root, "judge")

    def test_aggregation_rejects_noncanonical_attempt_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "results"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            external_attempt = base / "external-attempt"
            external_attempt.mkdir()
            (external_attempt / "attempt.json").write_text(
                json.dumps(sample_attempt_manifest().to_dict()),
                encoding="utf-8",
            )
            (workspace.attempts / "linked-attempt").symlink_to(
                external_attempt,
                target_is_directory=True,
            )

            with self.assertRaisesRegex(ResultArtifactError, "attempt entry.*symlink"):
                aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            (workspace.attempts / "not-an-attempt.txt").write_text(
                "invalid entry",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ResultArtifactError, "attempt entry.*directory"):
                aggregate_results(root, "judge")

    def test_aggregation_rejects_manifest_identity_or_policy_mismatch(self):
        mutations = (
            ("timing", "case_id", "different-case"),
            ("grading", "run_kind", "different-kind"),
            ("grading", "aggregation", {
                "group_id": "ticket-workflow/intake",
                "variant": "candidate",
                "contributes_to_outcome": False,
                "required_variants": ["candidate"],
            }),
        )
        for artifact, field, value in mutations:
            with self.subTest(artifact=artifact, field=field):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "results"
                    workspace = create_test_result_workspace(root)
                    paths, _ = write_preserved_run(
                        workspace,
                        variant="candidate",
                        contributes_to_outcome=True,
                        passed=True,
                        required_variants=("candidate",),
                    )
                    path = paths.timing if artifact == "timing" else paths.grading
                    document = json.loads(path.read_text(encoding="utf-8"))
                    document[field] = value
                    path.write_text(json.dumps(document), encoding="utf-8")

                    with self.assertRaisesRegex(ResultArtifactError, "attempt manifest"):
                        aggregate_results(root, "judge")

    def test_aggregation_rejects_duplicate_run_ids_and_unexpected_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "duplicates"
            workspace = create_test_result_workspace(root)
            for index in range(2):
                write_preserved_run(
                    workspace,
                    run_id="duplicate-run",
                    variant="candidate",
                    contributes_to_outcome=True,
                    passed=True,
                    required_variants=("candidate",),
                )
            with self.assertRaisesRegex(ResultArtifactError, "duplicate run_id"):
                aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "unexpected"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            paths = create_attempt_workspace(
                workspace,
                sample_attempt_manifest(
                    run_id="run-surprise",
                    variant="surprise",
                    required_variants=("surprise",),
                    compare_to=None,
                ),
            )
            manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
            manifest["aggregation"]["required_variants"] = ["candidate"]
            paths.manifest.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ResultArtifactError, "unexpected variant"):
                aggregate_results(root, "judge")

    def test_repeated_variants_require_equal_counts_and_consistent_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "counts"
            workspace = create_test_result_workspace(root)
            for index in range(2):
                write_preserved_run(
                    workspace,
                    run_id=f"candidate-{index}",
                    variant="candidate",
                    contributes_to_outcome=True,
                    passed=True,
                    required_variants=("candidate", "reference"),
                    compare_to="reference",
                )
            write_preserved_run(
                workspace,
                run_id="reference-0",
                variant="reference",
                contributes_to_outcome=False,
                passed=False,
                required_variants=("candidate", "reference"),
            )
            with self.assertRaisesRegex(ResultArtifactError, "unequal repeated-run counts"):
                aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "policy"
            workspace = create_test_result_workspace(root)
            for run_id, contributes, compare_to in (
                ("candidate-0", True, "reference"),
                ("candidate-1", False, None),
            ):
                write_preserved_run(
                    workspace,
                    run_id=run_id,
                    variant="candidate",
                    contributes_to_outcome=contributes,
                    passed=True,
                    required_variants=("candidate", "reference"),
                    compare_to=compare_to,
                )
            for index in range(2):
                write_preserved_run(
                    workspace,
                    run_id=f"reference-{index}",
                    variant="reference",
                    contributes_to_outcome=False,
                    passed=False,
                    required_variants=("candidate", "reference"),
                )
            with self.assertRaisesRegex(ResultArtifactError, "inconsistent.*candidate"):
                aggregate_results(root, "judge")

    def test_consistent_repeated_variants_aggregate_and_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            for index, candidate_passed in enumerate((True, False)):
                write_preserved_run(
                    workspace,
                    run_id=f"candidate-{index}",
                    variant="candidate",
                    contributes_to_outcome=True,
                    passed=candidate_passed,
                    required_variants=("candidate", "reference"),
                    compare_to="reference",
                )
                write_preserved_run(
                    workspace,
                    run_id=f"reference-{index}",
                    variant="reference",
                    contributes_to_outcome=False,
                    passed=False,
                    required_variants=("candidate", "reference"),
                )

            benchmark = aggregate_results(root, "judge")

            group = benchmark["source_summaries"]["judge"]["groups"][0]
            self.assertEqual(group["variants"]["candidate"]["runs"], 2)
            self.assertEqual(group["variants"]["reference"]["runs"], 2)
            self.assertEqual(group["comparisons"][0]["pass_rate_delta"], 0.5)

    def test_aggregation_rejects_a_source_without_contributing_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="reference",
                contributes_to_outcome=False,
                passed=True,
                required_variants=("reference",),
            )

            with self.assertRaisesRegex(ResultArtifactError, "no contributing outcomes"):
                aggregate_results(root, "judge")

    def test_aggregation_rejects_repository_containment_and_resolution_failures(self):
        with self.assertRaisesRegex(ResultArtifactError, "outside the repository"):
            aggregate_results(
                REPOSITORY_ROOT,
                "judge",
                repository_root=REPOSITORY_ROOT,
            )

        with tempfile.TemporaryDirectory() as directory:
            linked_repository = Path(directory) / "linked-repository"
            linked_repository.symlink_to(REPOSITORY_ROOT, target_is_directory=True)
            with self.assertRaisesRegex(ResultArtifactError, "outside the repository"):
                aggregate_results(
                    linked_repository,
                    "judge",
                    repository_root=REPOSITORY_ROOT,
                )

        with patch(
            "scripts.ai_skills_lib.eval_core.Path.resolve",
            side_effect=OSError("unresolvable path"),
        ):
            with self.assertRaisesRegex(ResultArtifactError, "cannot resolve result path"):
                aggregate_results(
                    Path("/tmp/results"),
                    "judge",
                    repository_root=REPOSITORY_ROOT,
                )

    def test_manual_is_a_complete_override_and_both_sources_remain_separate(self):
        required = ("candidate", "reference")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            candidate_paths, candidate = write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=required,
                compare_to="reference",
            )
            reference_paths, reference = write_preserved_run(
                workspace,
                variant="reference",
                contributes_to_outcome=False,
                passed=False,
                required_variants=required,
            )
            write_complete_manual_grading(candidate_paths, candidate, passed=False)
            write_complete_manual_grading(reference_paths, reference, passed=True)

            benchmark = aggregate_results(root, "both")

            self.assertEqual(set(benchmark["source_summaries"]), {"judge", "manual"})
            self.assertEqual(
                benchmark["source_summaries"]["judge"]["summary"]["failed_cases"], 0
            )
            self.assertEqual(
                benchmark["source_summaries"]["manual"]["summary"]["failed_cases"], 1
            )
            self.assertEqual(benchmark_exit_code(benchmark), 1)

    def test_manual_override_controls_both_source_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            paths, generated = write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=False,
                required_variants=("candidate",),
            )
            write_complete_manual_grading(paths, generated, passed=True)

            benchmark = aggregate_results(root, "both")

            self.assertEqual(
                benchmark["source_summaries"]["judge"]["summary"]["failed_cases"],
                1,
            )
            self.assertEqual(
                benchmark["source_summaries"]["manual"]["summary"]["failed_cases"],
                0,
            )
            self.assertEqual(benchmark_exit_code(benchmark), 0)

    def test_manual_override_rejects_partial_assertion_sets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            paths, generated = write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            manual = replace(
                generated,
                grade_source="manual",
                grader=GraderRecord(
                    type="human",
                    model=None,
                    reasoning_effort=None,
                    prompt_version="manual-review-v1",
                ),
                assertion_results=(),
                summary=GradingSummary(passed=0, failed=0, total=0, pass_rate=0.0),
            )
            paths.manual_grading.write_text(json.dumps(manual.to_dict()), encoding="utf-8")

            with self.assertRaisesRegex(ResultArtifactError, "assertion_results"):
                aggregate_results(root, "manual")

    def test_human_summary_prominently_labels_nonpositive_deltas(self):
        summary = format_benchmark_summary(sample_benchmark() | {
            "source_summaries": {
                "judge": {
                    **sample_benchmark()["source_summaries"]["judge"],
                    "groups": [
                        {
                            **sample_benchmark()["source_summaries"]["judge"]["groups"][0],
                            "comparisons": [
                                {
                                    "variant": "with_skill",
                                    "baseline_variant": "without_skill",
                                    "pass_rate_delta": 0.0,
                                    "investigation_required": True,
                                }
                            ],
                        }
                    ],
                }
            }
        })

        self.assertIn("with_skill", summary)
        self.assertIn("without_skill", summary)
        self.assertIn("INVESTIGATE", summary)


class JudgeBoundaryTests(unittest.TestCase):
    def test_parses_strict_judge_json_and_combines_deterministic_checks(self):
        judge_grading = parse_judge_response(
            json.dumps(sample_judge_response()),
            expected_judge_context(),
            model="actual-judge-model",
            reasoning_effort="high",
        )
        deterministic = AssertionResult(
            id="check-1",
            kind="check",
            text="Required artifact exists.",
            passed=False,
            checked_by="deterministic",
            evidence="The required artifact was absent.",
            evidence_refs=({"artifact": "execution_trace.jsonl", "locator": "event 3"},),
        )

        combined = combine_grading_results(judge_grading, (deterministic,))

        self.assertEqual([result.id for result in combined.assertion_results], ["check-1", "assertion-1"])
        self.assertEqual(combined.summary.failed, 1)
        self.assertEqual(combined.summary.total, 2)
        self.assertEqual(combined.grader.reasoning_effort, "high")

    def test_malformed_or_incomplete_judge_response_is_untrustworthy(self):
        for response in ("not json", json.dumps({"assertion_results": []})):
            with self.subTest(response=response):
                with self.assertRaises(ResultArtifactError) as raised:
                    parse_judge_response(response, expected_judge_context())
                self.assertEqual(raised.exception.exit_code, 2)

    def test_judge_cannot_change_expected_assertions_or_aggregation_policy(self):
        malicious_documents = []
        omitted = sample_judge_response()
        omitted["assertion_results"] = []
        malicious_documents.append(omitted)
        changed_policy = sample_judge_response()
        changed_policy["aggregation"] = {"contributes_to_outcome": False}
        malicious_documents.append(changed_policy)

        for document in malicious_documents:
            with self.subTest(document=document):
                with self.assertRaisesRegex(ResultArtifactError, "judge response"):
                    parse_judge_response(json.dumps(document), expected_judge_context())

    def test_judge_requires_allowed_evidence_for_every_assertion(self):
        no_evidence = sample_judge_response()
        no_evidence["assertion_results"][0]["evidence_refs"] = []
        disallowed = sample_judge_response()
        disallowed["assertion_results"][0]["evidence_refs"][0]["artifact"] = (
            "private/oracle.json"
        )

        for document in (no_evidence, disallowed):
            with self.subTest(document=document):
                with self.assertRaisesRegex(ResultArtifactError, "evidence"):
                    parse_judge_response(
                        json.dumps(document),
                        expected_judge_context(),
                        model="actual-judge-model",
                        reasoning_effort="high",
                    )

    def test_judge_invocation_calls_harness_once_and_does_not_retry_failure(self):
        class JudgeHarness:
            def __init__(self, execution: HarnessExecution):
                self.execution = execution
                self.calls = 0

            def execute(self, request, artifact_dir):
                self.calls += 1
                return self.execution

        request = HarnessRequest(
            role="judge",
            run_variant="semantic_grade",
            prompt="Grade the evidence.",
            timeout_seconds=30,
        )
        valid_execution = replace(
            completed_harness_execution(),
            response=json.dumps(sample_judge_response()),
            model="actual-judge-model",
        )
        adapter = JudgeHarness(valid_execution)

        invocation = invoke_judge(
            adapter,
            request,
            Path("artifacts"),
            expected_judge_context(),
        )

        self.assertEqual(adapter.calls, 1)
        self.assertIsInstance(invocation, JudgeInvocationResult)
        self.assertEqual(invocation.grading.grader.model, "actual-judge-model")
        self.assertEqual(invocation.grading.grader.reasoning_effort, "medium")
        self.assertEqual(invocation.execution.reasoning_effort, "medium")

        failed_adapter = JudgeHarness(
            replace(completed_harness_execution(), failure="authentication unavailable", exit_code=2)
        )
        with self.assertRaisesRegex(
            JudgeExecutionError, "authentication unavailable"
        ) as raised:
            invoke_judge(
                failed_adapter,
                request,
                Path("artifacts"),
                expected_judge_context(),
            )
        self.assertEqual(raised.exception.execution, failed_adapter.execution)
        self.assertEqual(raised.exception.execution.trace[0]["event"], "harness.completed")
        self.assertEqual(failed_adapter.calls, 1)

        for incomplete in (
            replace(valid_execution, exit_code=None),
            replace(valid_execution, model=None),
            replace(valid_execution, reasoning_effort=None),
        ):
            with self.subTest(incomplete=incomplete):
                with self.assertRaises(JudgeExecutionError) as raised:
                    invoke_judge(
                        JudgeHarness(incomplete),
                        request,
                        Path("artifacts"),
                        expected_judge_context(),
                    )
                self.assertEqual(raised.exception.execution, incomplete)

        malformed = replace(valid_execution, response="not json")
        with self.assertRaises(JudgeExecutionError) as raised:
            invoke_judge(
                JudgeHarness(malformed),
                request,
                Path("artifacts"),
                expected_judge_context(),
            )
        self.assertEqual(raised.exception.execution.response, "not json")


class AggregateCliTests(unittest.TestCase):
    def test_parser_returns_a_results_path_and_restricts_grade_source(self):
        parsed = build_parser().parse_args(
            [
                "evals",
                "aggregate",
                "--results-dir",
                "/tmp/preserved-results",
                "--grade-source",
                "manual",
            ]
        )

        self.assertEqual(parsed.results_dir, Path("/tmp/preserved-results"))
        self.assertEqual(parsed.grade_source, "manual")
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(
                    [
                        "evals",
                        "aggregate",
                        "--results-dir",
                        "/tmp/results",
                        "--grade-source",
                        "unknown",
                    ]
                )

    def test_aggregate_cli_reports_pass_failure_and_untrustworthy_exit_codes(self):
        required = ("candidate", "reference")
        for candidate_passed, expected_exit in ((True, 0), (False, 1)):
            with self.subTest(candidate_passed=candidate_passed):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "results"
                    workspace = create_test_result_workspace(root)
                    write_preserved_run(
                        workspace,
                        variant="candidate",
                        contributes_to_outcome=True,
                        passed=candidate_passed,
                        required_variants=required,
                        compare_to="reference",
                    )
                    write_preserved_run(
                        workspace,
                        variant="reference",
                        contributes_to_outcome=False,
                        passed=False,
                        required_variants=required,
                    )
                    output = StringIO()

                    with redirect_stdout(output):
                        result = cli.main(
                            [
                                "evals",
                                "aggregate",
                                "--results-dir",
                                str(root),
                                "--grade-source",
                                "judge",
                            ]
                        )

                    self.assertEqual(result, expected_exit)
                    self.assertIn(f"Results: {root.resolve()}", output.getvalue())
                    self.assertIn("candidate", output.getvalue())
                    self.assertTrue((root / "benchmark.json").is_file())

        output = StringIO()
        missing = Path("/tmp/ai-skills-missing-aggregate-results")
        with redirect_stdout(output):
            result = cli.main(
                [
                    "evals",
                    "aggregate",
                    "--results-dir",
                    str(missing),
                    "--grade-source",
                    "judge",
                ]
            )
        self.assertEqual(result, 2)
        self.assertIn("FAILED", output.getvalue())
        self.assertIn(f"Results: {missing.resolve()}", output.getvalue())

    def test_aggregate_cli_maps_benchmark_write_errors_to_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(root)
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            output = StringIO()

            with patch(
                "scripts.ai_skills_lib.eval_core.os.replace",
                side_effect=OSError("read-only result directory"),
            ):
                with redirect_stdout(output):
                    result = cli.main(
                        [
                            "evals",
                            "aggregate",
                            "--results-dir",
                            str(root),
                            "--grade-source",
                            "judge",
                        ]
                    )

            self.assertEqual(result, 2)
            self.assertIn("read-only result directory", output.getvalue())

    def test_aggregate_cli_maps_path_resolution_failures_to_exit_two(self):
        output = StringIO()
        with patch(
            "scripts.ai_skills.Path.resolve",
            side_effect=OSError("unresolvable path"),
        ):
            with redirect_stdout(output):
                result = cli.main(
                    [
                        "evals",
                        "aggregate",
                        "--results-dir",
                        "/tmp/results",
                        "--grade-source",
                        "judge",
                    ]
                )

        self.assertEqual(result, 2)
        self.assertIn("FAILED", output.getvalue())
        self.assertIn("cannot resolve result path", output.getvalue())

    def test_aggregate_cli_rejects_repository_paths(self):
        output = StringIO()
        with redirect_stdout(output):
            result = cli.main(
                [
                    "evals",
                    "aggregate",
                    "--results-dir",
                    str(REPOSITORY_ROOT),
                    "--grade-source",
                    "judge",
                ]
            )

        self.assertEqual(result, 2)
        self.assertIn("outside the repository", output.getvalue())


if __name__ == "__main__":
    unittest.main()
