from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from io import StringIO
import json
import os
from pathlib import Path
import shutil
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
    declare_invocation,
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
        "skill_summaries": [
            {
                "skill_name": "ticket-workflow",
                "total_outcomes": 1,
                "passed_outcomes": 1,
                "failed_outcomes": 0,
                "pass_rate": 1.0,
                "measurements": {},
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

    def test_runtime_requirements_pin_fixture_control_crypto(self):
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("PyJWT==2.13.0", requirements.splitlines())
        self.assertIn("cryptography==49.0.0", requirements.splitlines())

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
    group_id: str = "ticket-workflow/intake",
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
            group_id=group_id,
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
    group_id: str = "ticket-workflow/intake",
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
            group_id=group_id,
            variant=variant,
            contributes_to_outcome=contributes_to_outcome,
            required_variants=required_variants,
            compare_to=compare_to,
        ),
    )


def preserved_run_manifest(
    *,
    run_id: str | None = None,
    group_id: str = "ticket-workflow/intake",
    variant: str,
    contributes_to_outcome: bool,
    required_variants: tuple[str, ...],
    compare_to: str | None = None,
) -> AttemptManifest:
    return sample_attempt_manifest(
        run_id=run_id or f"run-{variant}",
        group_id=group_id,
        variant=variant,
        contributes_to_outcome=contributes_to_outcome,
        required_variants=required_variants,
        compare_to=compare_to,
    )


def write_preserved_run(
    workspace: ResultWorkspace,
    *,
    run_id: str | None = None,
    group_id: str = "ticket-workflow/intake",
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
        group_id=group_id,
        variant=variant,
        contributes_to_outcome=contributes_to_outcome,
        required_variants=required_variants,
        compare_to=compare_to,
        passed=passed,
    )
    paths = create_attempt_workspace(
        workspace,
        preserved_run_manifest(
            run_id=run_id,
            group_id=group_id,
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


def create_test_result_workspace(
    root: Path,
    *manifests: AttemptManifest,
) -> ResultWorkspace:
    workspace = create_result_workspace(
        "test evals",
        results_dir=root,
        repository_root=REPOSITORY_ROOT,
    )
    if manifests:
        declare_invocation(workspace, "test evals", manifests)
    return workspace


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

    def test_workspace_initialization_failure_retains_and_reports_empty_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            root = (base / "state/results").resolve()
            original_mkdir = Path.mkdir

            def fail_attempts_directory(path, *args, **kwargs):
                if path == root / "attempts":
                    raise OSError("cannot initialize attempts")
                return original_mkdir(path, *args, **kwargs)

            with patch(
                "scripts.ai_skills_lib.eval_core.Path.mkdir",
                new=fail_attempts_directory,
            ):
                with self.assertRaises(ResultArtifactError) as raised:
                    create_result_workspace(
                        "evals run",
                        results_dir=root,
                        repository_root=repository,
                    )

            self.assertIn(f"retained partial state at {root}", str(raised.exception))
            self.assertTrue(root.is_dir())
            self.assertEqual(list(root.iterdir()), [])
            with self.assertRaisesRegex(ResultArtifactError, "already exists"):
                create_result_workspace(
                    "evals run",
                    results_dir=root,
                    repository_root=repository,
                )
            self.assertTrue(root.is_dir())

    def test_workspace_rollback_retains_concurrently_injected_children(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            root = (base / "state/results").resolve()
            injected_marker = root / "concurrent" / "marker.txt"
            original_mkdir = Path.mkdir

            def inject_child_then_fail(path, *args, **kwargs):
                if path == root / "attempts":
                    original_mkdir(injected_marker.parent)
                    injected_marker.write_text("retain me", encoding="utf-8")
                    raise OSError("unbounded failure detail " * 10_000)
                return original_mkdir(path, *args, **kwargs)

            with patch(
                "scripts.ai_skills_lib.eval_core.Path.mkdir",
                new=inject_child_then_fail,
            ):
                with self.assertRaises(ResultArtifactError) as raised:
                    create_result_workspace(
                        "evals run",
                        results_dir=root,
                        repository_root=repository,
                    )

            message = str(raised.exception)
            self.assertIn(f"retained partial state at {root}", message)
            self.assertLessEqual(len(message), 1100)
            self.assertNotIn("unbounded failure detail", message)
            self.assertEqual(injected_marker.read_text(encoding="utf-8"), "retain me")

    def test_retained_workspace_error_preserves_a_long_path_in_full(self):
        path = Path("/synthetic-results") / ("x" * 4096)

        message = str(eval_core._retained_workspace_error(path))

        self.assertEqual(
            message,
            f"cannot initialize result workspace; retained partial state at {path}",
        )

    def test_workspace_failure_retains_identity_swapped_root_and_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            root = (base / "state/results").resolve()
            displaced_root = root.with_name("displaced-results")
            original_marker = displaced_root / "original.txt"
            replacement_marker = root / "replacement.txt"
            original_mkdir = Path.mkdir

            def replace_root_then_fail(path, *args, **kwargs):
                if path == root / "attempts":
                    (root / "original.txt").write_text("original", encoding="utf-8")
                    root.rename(displaced_root)
                    original_mkdir(root)
                    replacement_marker.write_text("replacement", encoding="utf-8")
                    raise OSError("attempt initialization failed")
                return original_mkdir(path, *args, **kwargs)

            with patch(
                "scripts.ai_skills_lib.eval_core.Path.mkdir",
                new=replace_root_then_fail,
            ):
                with self.assertRaises(ResultArtifactError) as raised:
                    create_result_workspace(
                        "evals run",
                        results_dir=root,
                        repository_root=repository,
                    )

            self.assertIn(f"retained partial state at {root}", str(raised.exception))
            self.assertEqual(original_marker.read_text(encoding="utf-8"), "original")
            self.assertEqual(replacement_marker.read_text(encoding="utf-8"), "replacement")

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
            manifest = sample_attempt_manifest(
                run_id="run-with-skill",
                variant="with_skill",
                required_variants=("with_skill", "without_skill"),
                compare_to="without_skill",
            )
            workspace = create_test_result_workspace(Path(directory) / "run", manifest)
            paths = create_attempt_workspace(workspace, manifest)
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

    def test_complete_writer_rejects_unsafe_evidence_paths_before_persisting(self):
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
        grading = generated_grading_record()
        grading = replace(
            grading,
            assertion_results=(
                replace(
                    grading.assertion_results[0],
                    evidence_refs=(
                        {"artifact": "../outside.txt", "locator": "untrusted path"},
                    ),
                ),
            ),
        )
        record = EvalRunRecord(
            response="Please provide the acceptance criteria.",
            transcript="# Transcript\n",
            execution_trace=({"event": "harness.completed", "exit_code": 0},),
            timing=timing,
            grading=grading,
        )

        with tempfile.TemporaryDirectory() as directory:
            manifest = sample_attempt_manifest(
                run_id="run-with-skill",
                variant="with_skill",
                required_variants=("with_skill", "without_skill"),
                compare_to="without_skill",
            )
            workspace = create_test_result_workspace(Path(directory) / "run", manifest)
            paths = create_attempt_workspace(workspace, manifest)

            with self.assertRaisesRegex(
                ResultArtifactError,
                "grading evidence artifact path is invalid",
            ):
                write_eval_run_artifacts(paths, record)

            self.assertFalse(paths.timing.exists())
            self.assertFalse(paths.response.exists())
            self.assertFalse(paths.transcript.exists())
            self.assertFalse(paths.execution_trace.exists())
            self.assertFalse(paths.grading.exists())


class InvocationAttemptWorkspaceTests(unittest.TestCase):
    def test_attempt_creation_requires_a_declared_invocation_membership(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            declared = sample_attempt_manifest()
            with self.assertRaisesRegex(ResultArtifactError, "regular invocation.json"):
                create_attempt_workspace(workspace, declared)

            declare_invocation(workspace, "evals run", (declared,))
            with self.assertRaisesRegex(ResultArtifactError, "immutable invocation manifest"):
                create_attempt_workspace(
                    workspace,
                    sample_attempt_manifest(run_id="undeclared-attempt"),
                )

    def test_attempt_artifact_writers_require_the_retained_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            manifest = sample_attempt_manifest()
            declare_invocation(workspace, "evals run", (manifest,))
            paths = create_attempt_workspace(workspace, manifest)
            workspace.invocation_manifest.unlink()
            timing = record_harness_timing(
                run_id=manifest.run_id,
                skill_name=manifest.skill_name,
                case_id=manifest.case_id,
                run_kind=manifest.run_kind,
                harness_name="codex",
                started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
                ended_at=datetime(2026, 7, 19, 10, 0, 1, tzinfo=timezone.utc),
                execution=completed_harness_execution(),
            )
            record = EvalRunRecord(
                response="response",
                transcript="transcript",
                execution_trace=(),
                timing=timing,
                grading=generated_grading_record(
                    run_id=manifest.run_id,
                    run_kind=manifest.run_kind,
                    variant=manifest.aggregation.variant,
                    required_variants=manifest.aggregation.required_variants,
                    compare_to=manifest.aggregation.compare_to,
                ),
            )

            with self.assertRaisesRegex(ResultArtifactError, "regular invocation.json"):
                write_eval_run_artifacts(paths, record)
            with self.assertRaisesRegex(ResultArtifactError, "regular invocation.json"):
                write_incomplete_attempt_artifacts(
                    paths,
                    response=None,
                    transcript=None,
                    execution_trace=(),
                    timing=timing,
                )

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
            first_manifest = sample_attempt_manifest()
            second_manifest = sample_attempt_manifest(run_id="run-candidate-2")
            declare_invocation(workspace, "evals run", (first_manifest, second_manifest))
            first = create_attempt_workspace(workspace, first_manifest)
            second = create_attempt_workspace(workspace, second_manifest)

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
            declare_invocation(workspace, "evals run", (sample_attempt_manifest(),))
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
            manifest = sample_attempt_manifest()
            declare_invocation(workspace, "evals run", (manifest,))
            paths = create_attempt_workspace(workspace, manifest)
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
            first_manifest = sample_attempt_manifest()
            second_manifest = sample_attempt_manifest(run_id="run-candidate-2")
            declare_invocation(workspace, "evals run", (first_manifest, second_manifest))
            paths = create_attempt_workspace(workspace, first_manifest)
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
                second_manifest,
            )
            with patch(
                "scripts.ai_skills_lib.eval_core.Path.resolve",
                side_effect=OSError("unresolvable artifact"),
            ):
                with self.assertRaisesRegex(ResultArtifactError, "resolve.*artifact"):
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=required,
                    compare_to="reference",
                ),
                preserved_run_manifest(
                    variant="reference",
                    contributes_to_outcome=False,
                    required_variants=required,
                ),
            )
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

            benchmark = aggregate_results(
                root,
                "judge",
                terminal_decision="expectations failed",
            )

            self.assertEqual(benchmark_exit_code(benchmark), 1)
            group = benchmark["source_summaries"]["judge"]["groups"][0]
            self.assertEqual(set(group["variants"]), {"candidate", "reference"})
            self.assertEqual(group["comparisons"][0]["pass_rate_delta"], -1.0)
            self.assertTrue(group["comparisons"][0]["investigation_required"])
            self.assertTrue((root / "benchmark.json").is_file())
            failed_summary = (root / "summary.md").read_text(encoding="utf-8")
            self.assertIn("Decision: expectations failed", failed_summary)
            self.assertIn("candidate", failed_summary)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=required,
                    compare_to="reference",
                ),
                preserved_run_manifest(
                    variant="reference",
                    contributes_to_outcome=False,
                    required_variants=required,
                ),
            )
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

            self.assertEqual(
                benchmark_exit_code(
                    aggregate_results(
                        root,
                        "judge",
                        terminal_decision="pass",
                    )
                ),
                0,
            )
            self.assertIn(
                "Decision: pass",
                (root / "summary.md").read_text(encoding="utf-8"),
            )

    def test_aggregation_requires_every_caller_declared_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate", "reference"),
                    compare_to="reference",
                ),
            )
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
            incomplete_manifest = sample_attempt_manifest(
                run_id="incomplete-attempt",
                variant="attempt",
                required_variants=("attempt",),
                compare_to=None,
            )
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
                incomplete_manifest,
            )
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            incomplete_paths = create_attempt_workspace(
                workspace,
                incomplete_manifest,
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
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
                    workspace = create_test_result_workspace(
                        root,
                        preserved_run_manifest(
                            variant="candidate",
                            contributes_to_outcome=True,
                            required_variants=("candidate",),
                        ),
                    )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    run_id="duplicate-run",
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
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
            surprise_manifest = sample_attempt_manifest(
                run_id="run-surprise",
                variant="surprise",
                required_variants=("surprise",),
                compare_to=None,
            )
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
                surprise_manifest,
            )
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            paths = create_attempt_workspace(
                workspace,
                surprise_manifest,
            )
            manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
            manifest["aggregation"]["required_variants"] = ["candidate"]
            paths.manifest.write_text(json.dumps(manifest), encoding="utf-8")
            invocation = json.loads(
                workspace.invocation_manifest.read_text(encoding="utf-8")
            )
            invocation["attempts"][1] = manifest
            workspace.invocation_manifest.write_text(json.dumps(invocation), encoding="utf-8")
            with self.assertRaisesRegex(ResultArtifactError, "unexpected variant"):
                aggregate_results(root, "judge")

    def test_repeated_variants_require_equal_counts_and_consistent_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "counts"
            workspace = create_test_result_workspace(
                root,
                *(
                    preserved_run_manifest(
                        run_id=f"candidate-{index}",
                        variant="candidate",
                        contributes_to_outcome=True,
                        required_variants=("candidate", "reference"),
                        compare_to="reference",
                    )
                    for index in range(2)
                ),
                preserved_run_manifest(
                    run_id="reference-0",
                    variant="reference",
                    contributes_to_outcome=False,
                    required_variants=("candidate", "reference"),
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    run_id="candidate-0",
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate", "reference"),
                    compare_to="reference",
                ),
                preserved_run_manifest(
                    run_id="candidate-1",
                    variant="candidate",
                    contributes_to_outcome=False,
                    required_variants=("candidate", "reference"),
                ),
                *(
                    preserved_run_manifest(
                        run_id=f"reference-{index}",
                        variant="reference",
                        contributes_to_outcome=False,
                        required_variants=("candidate", "reference"),
                    )
                    for index in range(2)
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                *(
                    manifest
                    for index in range(2)
                    for manifest in (
                        preserved_run_manifest(
                            run_id=f"candidate-{index}",
                            variant="candidate",
                            contributes_to_outcome=True,
                            required_variants=("candidate", "reference"),
                            compare_to="reference",
                        ),
                        preserved_run_manifest(
                            run_id=f"reference-{index}",
                            variant="reference",
                            contributes_to_outcome=False,
                            required_variants=("candidate", "reference"),
                        ),
                    )
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="reference",
                    contributes_to_outcome=False,
                    required_variants=("reference",),
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=required,
                    compare_to="reference",
                ),
                preserved_run_manifest(
                    variant="reference",
                    contributes_to_outcome=False,
                    required_variants=required,
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
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
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
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


class UntrustedAggregationBoundaryTests(unittest.TestCase):
    def _complete_workspace(
        self,
        root: Path,
        *,
        with_manual: bool = False,
    ) -> tuple[ResultWorkspace, AttemptPaths, GradingRecord]:
        manifest = preserved_run_manifest(
            variant="candidate",
            contributes_to_outcome=True,
            required_variants=("candidate",),
        )
        workspace = create_test_result_workspace(root, manifest)
        paths, generated = write_preserved_run(
            workspace,
            variant="candidate",
            contributes_to_outcome=True,
            passed=True,
            required_variants=("candidate",),
        )
        if with_manual:
            write_complete_manual_grading(paths, generated, passed=True)
        return workspace, paths, generated

    def _prepend_duplicate_key(self, path: Path, key: str) -> None:
        original = path.read_text(encoding="utf-8")
        self.assertTrue(original.lstrip().startswith("{"))
        leading_whitespace = original[: len(original) - len(original.lstrip())]
        document = original.lstrip()
        path.write_text(
            f'{leading_whitespace}{{"{key}": "RAW_DUPLICATE_VALUE",{document[1:]}',
            encoding="utf-8",
        )

    def _set_evidence_artifact(self, grading_path: Path, artifact: str) -> None:
        document = json.loads(grading_path.read_text(encoding="utf-8"))
        document["assertion_results"][0]["evidence_refs"][0]["artifact"] = artifact
        grading_path.write_text(json.dumps(document), encoding="utf-8")

    def test_aggregation_requires_every_gradable_attempt_artifact(self):
        required_artifacts = (
            ("manifest", "attempt.json"),
            ("timing", "timing.json"),
            ("grading", "grading.json"),
            ("response", "outputs/response.md"),
            ("transcript", "transcript.md"),
            ("execution_trace", "execution_trace.jsonl"),
        )
        for path_attribute, relative_path in required_artifacts:
            with self.subTest(artifact=relative_path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                _, paths, _ = self._complete_workspace(root)
                aggregate_results(root, "judge")
                benchmark_before = (root / "benchmark.json").read_bytes()
                summary_before = (root / "summary.md").read_bytes()
                getattr(paths, path_attribute).unlink()

                with self.assertRaises(ResultArtifactError) as raised:
                    aggregate_results(root, "judge")

                self.assertIn(relative_path, str(raised.exception))
                self.assertEqual((root / "benchmark.json").read_bytes(), benchmark_before)
                self.assertEqual((root / "summary.md").read_bytes(), summary_before)

    def test_aggregation_rejects_dangling_generated_and_manual_evidence(self):
        cases = (
            ("judge", "grading"),
            ("manual", "manual_grading"),
        )
        for grade_source, grading_attribute in cases:
            with self.subTest(grade_source=grade_source), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                _, paths, _ = self._complete_workspace(root, with_manual=True)
                self._set_evidence_artifact(
                    getattr(paths, grading_attribute),
                    "outputs/missing-evidence.txt",
                )

                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "evidence artifact does not resolve to a regular snapshotted artifact",
                ):
                    aggregate_results(root, grade_source)

    def test_aggregation_rejects_noncanonical_or_disallowed_evidence_paths(self):
        invalid_artifacts = (
            "../timing.json",
            "/etc/passwd",
            "outputs/../timing.json",
            "outputs//response.md",
            "outputs\\response.md",
            "outputs",
            "attempt.json",
            "grading.json",
            "timing.json/child",
            "execution_trace.jsonl/child",
            "outputs/response.md/child",
        )
        for artifact in invalid_artifacts:
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                _, paths, _ = self._complete_workspace(root)
                self._set_evidence_artifact(paths.grading, artifact)

                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "grading evidence artifact",
                ):
                    aggregate_results(root, "judge")

    def test_aggregation_rejects_symlinked_evidence_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "results"
            _, paths, _ = self._complete_workspace(root)
            outside = base / "outside-evidence.txt"
            outside.write_text("outside\n", encoding="utf-8")
            cited = paths.root / "outputs" / "cited.txt"
            cited.symlink_to(outside)
            self._set_evidence_artifact(paths.grading, "outputs/cited.txt")

            with self.assertRaisesRegex(ResultArtifactError, "symlink"):
                aggregate_results(root, "judge")

    def test_aggregation_accepts_regular_snapshotted_output_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            _, paths, _ = self._complete_workspace(root)
            cited = paths.root / "outputs" / "reports" / "result.txt"
            cited.parent.mkdir()
            cited.write_text("captured evidence\n", encoding="utf-8")
            self._set_evidence_artifact(
                paths.grading,
                "outputs/reports/result.txt",
            )

            benchmark = aggregate_results(root, "judge")

            self.assertEqual(benchmark_exit_code(benchmark), 0)

    def test_aggregation_accepts_regular_snapshotted_control_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            _, paths, _ = self._complete_workspace(root)
            self._set_evidence_artifact(paths.grading, "timing.json")

            benchmark = aggregate_results(root, "judge")

            self.assertEqual(benchmark_exit_code(benchmark), 0)

    def test_aggregation_rejects_control_evidence_replaced_with_a_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            _, paths, _ = self._complete_workspace(root)
            self._set_evidence_artifact(paths.grading, "timing.json")
            paths.timing.unlink()
            paths.timing.mkdir()

            with self.assertRaisesRegex(ResultArtifactError, "attempt entry"):
                aggregate_results(root, "judge")

    def test_every_parsed_result_artifact_rejects_duplicate_json_keys(self):
        cases = (
            ("invocation", "command"),
            ("attempt", "run_id"),
            ("timing", "run_id"),
            ("grading", "run_id"),
            ("manual_grading", "run_id"),
        )
        for artifact, key in cases:
            with self.subTest(artifact=artifact):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "results"
                    workspace, paths, _ = self._complete_workspace(
                        root,
                        with_manual=True,
                    )
                    targets = {
                        "invocation": workspace.invocation_manifest,
                        "attempt": paths.manifest,
                        "timing": paths.timing,
                        "grading": paths.grading,
                        "manual_grading": paths.manual_grading,
                    }
                    self._prepend_duplicate_key(targets[artifact], key)

                    with self.assertRaisesRegex(
                        ResultArtifactError,
                        "duplicate JSON key",
                    ) as raised:
                        aggregate_results(root, "both")

                    self.assertNotIn("RAW_DUPLICATE_VALUE", str(raised.exception))

    def test_oversized_json_and_huge_scalars_are_rejected_before_schema_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "oversized-json"
            _, paths, _ = self._complete_workspace(root)
            paths.grading.write_bytes(
                b"{" + b" " * eval_core._MAX_RESULT_JSON_FILE_BYTES
            )

            with self.assertRaisesRegex(ResultArtifactError, "JSON byte limit"):
                aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "huge-scalar"
            _, paths, _ = self._complete_workspace(root)
            document = json.loads(paths.grading.read_text(encoding="utf-8"))
            document["assertion_results"][0]["evidence"] = (
                "RAW_HUGE_SCALAR" + "x" * eval_core._MAX_RESULT_JSON_SCALAR_BYTES
            )
            paths.grading.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ResultArtifactError, "JSON scalar limit") as raised:
                aggregate_results(root, "judge")

            self.assertNotIn("RAW_HUGE_SCALAR", str(raised.exception))

    def test_deep_and_node_heavy_json_are_rejected_with_structural_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "deep-json"
            _, paths, _ = self._complete_workspace(root)
            document = json.loads(paths.grading.read_text(encoding="utf-8"))
            nested: object = "leaf"
            for _ in range(eval_core._MAX_RESULT_JSON_DEPTH + 1):
                nested = [nested]
            document["unexpected"] = nested
            paths.grading.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ResultArtifactError, "JSON depth limit"):
                aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "node-heavy-json"
            _, paths, _ = self._complete_workspace(root)
            document = json.loads(paths.grading.read_text(encoding="utf-8"))
            document["unexpected"] = [
                None for _ in range(eval_core._MAX_RESULT_JSON_NODES + 1)
            ]
            paths.grading.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ResultArtifactError, "JSON node limit"):
                aggregate_results(root, "judge")

    def test_structural_json_limits_precede_materialization(self):
        hostile_values = (
            (
                "[" * (eval_core._MAX_RESULT_JSON_DEPTH + 1)
                + "0"
                + "]" * (eval_core._MAX_RESULT_JSON_DEPTH + 1),
                "JSON depth limit",
            ),
            (
                "[" + ",".join("0" for _ in range(eval_core._MAX_RESULT_JSON_NODES)) + "]",
                "JSON node limit",
            ),
        )
        real_loads = json.loads

        for hostile, expected_error in hostile_values:
            with self.subTest(expected_error=expected_error), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "hostile-json"
                _, paths, _ = self._complete_workspace(root)
                paths.grading.write_text(hostile, encoding="utf-8")

                def reject_hostile_materialization(value, *args, **kwargs):
                    if value == hostile:
                        raise AssertionError(
                            "structurally hostile JSON reached json.loads"
                        )
                    return real_loads(value, *args, **kwargs)

                with patch.object(
                    eval_core.json,
                    "loads",
                    side_effect=reject_hostile_materialization,
                ):
                    with self.assertRaisesRegex(ResultArtifactError, expected_error):
                        aggregate_results(root, "judge")

    def test_invocation_attempt_count_and_tree_entry_count_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "attempt-count"
            workspace = create_test_result_workspace(root)
            attempt = sample_attempt_manifest(
                variant="candidate",
                required_variants=("candidate",),
                compare_to=None,
            ).to_dict()
            invocation = {
                "schema_version": "ai-skills.eval.invocation.v1",
                "command": "test evals",
                "attempts": [
                    attempt | {"run_id": f"attempt-{index}"}
                    for index in range(eval_core._MAX_DECLARED_ATTEMPTS + 1)
                ],
            }
            workspace.invocation_manifest.write_text(
                json.dumps(invocation),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ResultArtifactError, "declared attempt limit"):
                aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "entry-count"
            _, paths, _ = self._complete_workspace(root)
            for index in range(2):
                (paths.root / "outputs" / f"captured-{index}.txt").write_text(
                    "captured",
                    encoding="utf-8",
                )

            with patch.object(eval_core, "_MAX_RESULT_TREE_ENTRIES", 11):
                with self.assertRaisesRegex(ResultArtifactError, "entry-count limit"):
                    aggregate_results(root, "judge")

    def test_attempt_inventory_and_directory_depth_are_declaration_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "attempt-inventory"
            workspace, _, _ = self._complete_workspace(root)
            for index in range(2):
                (workspace.attempts / f"undeclared-{index}").mkdir()

            with self.assertRaisesRegex(
                ResultArtifactError,
                "declared attempt count bound",
            ):
                aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "directory-depth"
            _, paths, _ = self._complete_workspace(root)
            nested = paths.root / "outputs"
            for index in range(eval_core._MAX_RESULT_TREE_DEPTH):
                nested /= f"level-{index}"
                nested.mkdir()

            with self.assertRaisesRegex(ResultArtifactError, "directory depth limit"):
                aggregate_results(root, "judge")

    def test_exact_resource_limits_remain_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "exact-limits"
            _, paths, _ = self._complete_workspace(root)
            nested = paths.root / "outputs"
            for index in range(eval_core._MAX_RESULT_TREE_DEPTH - 3):
                nested /= f"level-{index}"
                nested.mkdir()

            with patch.object(
                eval_core,
                "_format_timestamp",
                return_value="2026-07-20T10:00:00Z",
            ):
                aggregate_results(root, "judge")
                entries = sum(1 for _ in root.rglob("*"))
                files = [path for path in root.rglob("*") if path.is_file()]
                total_bytes = sum(path.stat().st_size for path in files)
                maximum_file_bytes = max(path.stat().st_size for path in files)

                with (
                    patch.object(eval_core, "_MAX_DECLARED_ATTEMPTS", 1),
                    patch.object(eval_core, "_MAX_RESULT_TREE_ENTRIES", entries),
                    patch.object(
                        eval_core,
                        "_MAX_RESULT_FILE_BYTES",
                        maximum_file_bytes,
                    ),
                    patch.object(eval_core, "_MAX_RESULT_TREE_BYTES", total_bytes),
                ):
                    benchmark = aggregate_results(root, "judge")

            self.assertEqual(benchmark_exit_code(benchmark), 0)

    def test_per_file_and_cumulative_result_bytes_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "per-file"
            _, paths, _ = self._complete_workspace(root)
            captured = paths.root / "outputs" / "captured.bin"
            captured.write_bytes(b"x" * 1025)

            with patch.object(eval_core, "_MAX_RESULT_FILE_BYTES", 1024):
                with self.assertRaisesRegex(ResultArtifactError, "per-file byte limit"):
                    aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cumulative"
            self._complete_workspace(root)
            total_bytes = sum(
                path.stat().st_size for path in root.rglob("*") if path.is_file()
            )

            with patch.object(eval_core, "_MAX_RESULT_TREE_BYTES", total_bytes - 1):
                with self.assertRaisesRegex(ResultArtifactError, "cumulative byte limit"):
                    aggregate_results(root, "judge")

    def test_symlinks_and_fifos_are_rejected_without_reading_special_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "symlink"
            _, paths, _ = self._complete_workspace(root)
            outside = root.parent / "outside-grading.json"
            outside.write_text("RAW_OUTSIDE_CONTENT", encoding="utf-8")
            paths.grading.unlink()
            paths.grading.symlink_to(outside)

            with self.assertRaisesRegex(ResultArtifactError, "symlink") as raised:
                aggregate_results(root, "judge")

            self.assertNotIn("RAW_OUTSIDE_CONTENT", str(raised.exception))

        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO creation is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fifo"
            _, paths, _ = self._complete_workspace(root)
            paths.grading.unlink()
            os.mkfifo(paths.grading)

            with patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("unbounded path read"),
            ):
                with self.assertRaisesRegex(ResultArtifactError, "special file"):
                    aggregate_results(root, "judge")

    def test_inventory_resource_failures_are_sanitized_result_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "resource-failure"
            self._complete_workspace(root)

            with patch(
                "scripts.ai_skills_lib.eval_core.os.scandir",
                side_effect=OSError("RAW_RESOURCE_FAILURE"),
            ):
                with self.assertRaises(ResultArtifactError) as raised:
                    aggregate_results(root, "judge")

            self.assertNotIn("RAW_RESOURCE_FAILURE", str(raised.exception))

    def test_file_mutation_during_a_bounded_read_fails_without_content_disclosure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mutation"
            _, paths, _ = self._complete_workspace(root)
            target_inode = paths.grading.stat().st_ino
            real_read = os.read
            mutated = False

            def mutate_after_read(descriptor: int, count: int) -> bytes:
                nonlocal mutated
                chunk = real_read(descriptor, count)
                if not mutated and os.fstat(descriptor).st_ino == target_inode:
                    with paths.grading.open("ab") as artifact:
                        artifact.write(b"RAW_MUTATED_CONTENT")
                    mutated = True
                return chunk

            with patch("scripts.ai_skills_lib.eval_core.os.read", new=mutate_after_read):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "changed while being read",
                ) as raised:
                    aggregate_results(root, "judge")

            self.assertTrue(mutated)
            self.assertNotIn("RAW_MUTATED_CONTENT", str(raised.exception))

    def test_undeclared_trees_are_rejected_but_captured_outputs_remain_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "undeclared"
            workspace, _, _ = self._complete_workspace(root)
            rogue = workspace.root / "undeclared" / "nested"
            rogue.mkdir(parents=True)
            (rogue / "artifact.txt").write_text("untrusted", encoding="utf-8")

            with self.assertRaisesRegex(ResultArtifactError, "undeclared result entry"):
                aggregate_results(root, "judge")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "captured-output"
            _, paths, generated = self._complete_workspace(root, with_manual=True)
            report = paths.root / "outputs" / "reports" / "result.json"
            report.parent.mkdir()
            report.write_text('{"status":"captured"}\n', encoding="utf-8")
            for control_name in (
                "attempt.json",
                "timing.json",
                "grading.json",
                "manual_grading.json",
                "invocation.json",
                "feedback.json",
            ):
                (report.parent / control_name).write_text(
                    '{"status":"captured"}\n',
                    encoding="utf-8",
                )

            benchmark = aggregate_results(root, "both")

            self.assertEqual(set(benchmark["source_summaries"]), {"judge", "manual"})
            self.assertEqual(report.read_text(encoding="utf-8"), '{"status":"captured"}\n')
            self.assertEqual(generated.run_id, "run-candidate")

    def test_root_replacement_during_atomic_outputs_fails_without_writing_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "results"
            self._complete_workspace(root)
            displaced = base / "displaced-results"
            replacement_marker = root / "replacement-marker.txt"
            real_link = os.link
            replaced = False

            def replace_root_before_output(source, target, *args, **kwargs):
                nonlocal replaced
                if not replaced:
                    root.rename(displaced)
                    root.mkdir()
                    replacement_marker.write_text("replacement", encoding="utf-8")
                    replaced = True
                return real_link(source, target, *args, **kwargs)

            with patch(
                "scripts.ai_skills_lib.eval_core.os.link",
                new=replace_root_before_output,
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "results directory changed",
                ):
                    aggregate_results(root, "judge")

            self.assertTrue(replaced)
            self.assertEqual(
                replacement_marker.read_text(encoding="utf-8"),
                "replacement",
            )
            self.assertFalse((root / "benchmark.json").exists())
            self.assertFalse((root / "summary.md").exists())
            self.assertFalse((displaced / "benchmark.json").exists())
            self.assertFalse((displaced / "summary.md").exists())

    def test_second_aggregate_replacement_failure_rolls_back_both_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            with patch.object(
                eval_core,
                "_format_timestamp",
                return_value="2026-07-20T10:00:00Z",
            ):
                aggregate_results(root, "judge")
            original_pair = {
                name: (root / name).read_bytes()
                for name in ("benchmark.json", "summary.md")
            }
            real_exchange = eval_core._atomic_exchange_result_entries

            def fail_summary_exchange(root_descriptor, first_name, second_name):
                if second_name == "summary.md":
                    raise ResultArtifactError("injected second replacement failure")
                return real_exchange(root_descriptor, first_name, second_name)

            with (
                patch.object(
                    eval_core,
                    "_atomic_exchange_result_entries",
                    side_effect=fail_summary_exchange,
                ),
                patch.object(
                    eval_core,
                    "_format_timestamp",
                    return_value="2026-07-20T10:00:01Z",
                ),
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "second replacement failure",
                ):
                    aggregate_results(root, "judge")

            self.assertEqual(
                {
                    name: (root / name).read_bytes()
                    for name in ("benchmark.json", "summary.md")
                },
                original_pair,
            )

    def test_second_aggregate_creation_failure_removes_the_first_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            real_link = os.link

            def fail_summary_link(source, target, *args, **kwargs):
                if target == "summary.md":
                    raise OSError("injected second creation failure")
                return real_link(source, target, *args, **kwargs)

            with patch(
                "scripts.ai_skills_lib.eval_core.os.link",
                side_effect=fail_summary_link,
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "cannot write aggregate result artifacts",
                ):
                    aggregate_results(root, "judge")

            self.assertFalse((root / "benchmark.json").exists())
            self.assertFalse((root / "summary.md").exists())

    def test_post_write_verification_failure_rolls_back_both_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            with patch.object(
                eval_core,
                "_format_timestamp",
                return_value="2026-07-20T10:00:00Z",
            ):
                aggregate_results(root, "judge")
            original_pair = {
                name: (root / name).read_bytes()
                for name in ("benchmark.json", "summary.md")
            }
            real_snapshot = eval_core._snapshot_result_tree
            snapshot_calls = 0

            def fail_post_write_verification(*args, **kwargs):
                nonlocal snapshot_calls
                snapshot_calls += 1
                if snapshot_calls == 3:
                    raise ResultArtifactError("injected aggregate verification failure")
                return real_snapshot(*args, **kwargs)

            with (
                patch.object(
                    eval_core,
                    "_snapshot_result_tree",
                    side_effect=fail_post_write_verification,
                ),
                patch.object(
                    eval_core,
                    "_format_timestamp",
                    return_value="2026-07-20T10:00:01Z",
                ),
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "verification failure",
                ):
                    aggregate_results(root, "judge")

            self.assertEqual(snapshot_calls, 3)
            self.assertEqual(
                {
                    name: (root / name).read_bytes()
                    for name in ("benchmark.json", "summary.md")
                },
                original_pair,
            )

    def test_ancestor_redirection_after_path_validation_cannot_enter_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            external_parent = base / "external"
            root = external_parent / "results"
            self._complete_workspace(root)
            resolved_root = root.resolve(strict=True)
            relocated_parent = repository / "external"
            relocated = relocated_parent / "results"
            real_open = os.open
            redirected = False

            def redirect_ancestor_before_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal redirected
                if (
                    not redirected
                    and dir_fd is None
                    and os.fspath(path) == os.fspath(resolved_root)
                ):
                    external_parent.rename(relocated_parent)
                    external_parent.symlink_to(
                        relocated_parent,
                        target_is_directory=True,
                    )
                    redirected = True
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with patch(
                "scripts.ai_skills_lib.eval_core.os.open",
                new=redirect_ancestor_before_open,
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "outside the repository",
                ):
                    aggregate_results(
                        root,
                        "judge",
                        repository_root=repository,
                    )

            self.assertTrue(redirected)
            self.assertFalse((relocated / "benchmark.json").exists())
            self.assertFalse((relocated / "summary.md").exists())

    def test_injected_aggregate_target_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            injected_content = b"RAW_INJECTED_AGGREGATE_TARGET"
            real_link = os.link
            injected = False

            def inject_target_before_install(source, target, *args, **kwargs):
                nonlocal injected
                if not injected and target == "benchmark.json":
                    target_descriptor = os.open(
                        target,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=kwargs["dst_dir_fd"],
                    )
                    try:
                        os.write(target_descriptor, injected_content)
                    finally:
                        os.close(target_descriptor)
                    injected = True
                return real_link(source, target, *args, **kwargs)

            with patch(
                "scripts.ai_skills_lib.eval_core.os.link",
                new=inject_target_before_install,
            ):
                with self.assertRaises(ResultArtifactError) as raised:
                    aggregate_results(root, "judge")

            self.assertTrue(injected)
            self.assertEqual((root / "benchmark.json").read_bytes(), injected_content)
            self.assertNotIn("RAW_INJECTED_AGGREGATE_TARGET", str(raised.exception))

    def test_existing_aggregate_target_mutation_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            with patch.object(
                eval_core,
                "_format_timestamp",
                return_value="2026-07-20T10:00:00Z",
            ):
                aggregate_results(root, "judge")

            injected_content = b"RAW_MUTATED_AGGREGATE_TARGET"
            real_stat = os.stat
            mutated = False

            def mutate_after_target_check(path, *args, **kwargs):
                nonlocal mutated
                observed = real_stat(path, *args, **kwargs)
                if (
                    not mutated
                    and path == "benchmark.json"
                    and kwargs.get("dir_fd") is not None
                ):
                    target_descriptor = os.open(
                        path,
                        os.O_WRONLY | os.O_TRUNC,
                        dir_fd=kwargs["dir_fd"],
                    )
                    try:
                        os.write(target_descriptor, injected_content)
                    finally:
                        os.close(target_descriptor)
                    mutated = True
                return observed

            with (
                patch(
                    "scripts.ai_skills_lib.eval_core.os.stat",
                    new=mutate_after_target_check,
                ),
                patch.object(
                    eval_core,
                    "_format_timestamp",
                    return_value="2026-07-20T10:00:01Z",
                ),
            ):
                with self.assertRaisesRegex(ResultArtifactError, "target changed") as raised:
                    aggregate_results(root, "judge")

            self.assertTrue(mutated)
            self.assertEqual((root / "benchmark.json").read_bytes(), injected_content)
            self.assertNotIn("RAW_MUTATED_AGGREGATE_TARGET", str(raised.exception))

    def test_existing_target_replacement_at_atomic_exchange_is_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            with patch.object(
                eval_core,
                "_format_timestamp",
                return_value="2026-07-20T10:00:00Z",
            ):
                aggregate_results(root, "judge")

            injected_content = b"RAW_EXCHANGE_TARGET"
            real_exchange = eval_core._atomic_exchange_result_entries
            replaced = False

            def replace_target_before_exchange(
                root_descriptor,
                first_name,
                second_name,
            ):
                nonlocal replaced
                if not replaced and second_name == "benchmark.json":
                    os.unlink(second_name, dir_fd=root_descriptor)
                    target_descriptor = os.open(
                        second_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=root_descriptor,
                    )
                    try:
                        os.write(target_descriptor, injected_content)
                    finally:
                        os.close(target_descriptor)
                    replaced = True
                return real_exchange(root_descriptor, first_name, second_name)

            with (
                patch.object(
                    eval_core,
                    "_atomic_exchange_result_entries",
                    new=replace_target_before_exchange,
                ),
                patch.object(
                    eval_core,
                    "_format_timestamp",
                    return_value="2026-07-20T10:00:01Z",
                ),
            ):
                with self.assertRaisesRegex(ResultArtifactError, "target changed") as raised:
                    aggregate_results(root, "judge")

            self.assertTrue(replaced)
            self.assertEqual((root / "benchmark.json").read_bytes(), injected_content)
            self.assertNotIn("RAW_EXCHANGE_TARGET", str(raised.exception))

    def test_same_size_restored_mtime_mutation_after_exchange_restores_each_output(self):
        for output_name in ("benchmark.json", "summary.md"):
            with self.subTest(output_name=output_name):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "results"
                    self._complete_workspace(root)
                    with patch.object(
                        eval_core,
                        "_format_timestamp",
                        return_value="2026-07-20T10:00:00Z",
                    ):
                        aggregate_results(root, "judge")

                    real_exchange = eval_core._atomic_exchange_result_entries
                    mutated_content: bytes | None = None
                    retained_ctime: int | None = None

                    def mutate_retained_output_after_exchange(
                        root_descriptor,
                        first_name,
                        second_name,
                    ):
                        nonlocal mutated_content, retained_ctime
                        result = real_exchange(
                            root_descriptor,
                            first_name,
                            second_name,
                        )
                        if mutated_content is None and second_name == output_name:
                            retained = root / first_name
                            original = retained.read_bytes()
                            original_metadata = retained.stat()
                            mutated_content = bytes([original[0] ^ 1]) + original[1:]
                            retained.write_bytes(mutated_content)
                            os.utime(
                                retained,
                                ns=(
                                    original_metadata.st_atime_ns,
                                    original_metadata.st_mtime_ns,
                                ),
                            )
                            mutated_metadata = retained.stat()
                            retained_ctime = mutated_metadata.st_ctime_ns
                            self.assertEqual(mutated_metadata.st_size, len(original))
                            self.assertEqual(
                                mutated_metadata.st_mtime_ns,
                                original_metadata.st_mtime_ns,
                            )
                            self.assertNotEqual(
                                mutated_metadata.st_ctime_ns,
                                original_metadata.st_ctime_ns,
                            )
                        return result

                    with (
                        patch.object(
                            eval_core,
                            "_atomic_exchange_result_entries",
                            new=mutate_retained_output_after_exchange,
                        ),
                        patch.object(
                            eval_core,
                            "_format_timestamp",
                            return_value="2026-07-20T10:00:01Z",
                        ),
                    ):
                        with self.assertRaisesRegex(
                            ResultArtifactError,
                            "target changed",
                        ):
                            aggregate_results(root, "judge")

                    self.assertIsNotNone(mutated_content)
                    self.assertIsNotNone(retained_ctime)
                    self.assertEqual((root / output_name).read_bytes(), mutated_content)

    def test_ctime_only_mutation_before_retained_cleanup_restores_each_output(self):
        for output_name in ("benchmark.json", "summary.md"):
            with self.subTest(output_name=output_name):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "results"
                    self._complete_workspace(root)
                    with patch.object(
                        eval_core,
                        "_format_timestamp",
                        return_value="2026-07-20T10:00:00Z",
                    ):
                        aggregate_results(root, "judge")

                    original_content = (root / output_name).read_bytes()
                    real_stat = os.stat
                    touched = False

                    def touch_retained_output_after_stat(path, *args, **kwargs):
                        nonlocal touched
                        observed = real_stat(path, *args, **kwargs)
                        if (
                            not touched
                            and isinstance(path, str)
                            and path.startswith(f".{output_name}.")
                            and path.endswith(".tmp")
                            and kwargs.get("dir_fd") is not None
                        ):
                            os.utime(
                                path,
                                ns=(observed.st_atime_ns, observed.st_mtime_ns),
                                dir_fd=kwargs["dir_fd"],
                                follow_symlinks=False,
                            )
                            touched = True
                            self.assertNotEqual(
                                real_stat(path, *args, **kwargs).st_ctime_ns,
                                observed.st_ctime_ns,
                            )
                        return observed

                    with (
                        patch(
                            "scripts.ai_skills_lib.eval_core.os.stat",
                            new=touch_retained_output_after_stat,
                        ),
                        patch.object(
                            eval_core,
                            "_format_timestamp",
                            return_value="2026-07-20T10:00:01Z",
                        ),
                    ):
                        with self.assertRaisesRegex(
                            ResultArtifactError,
                            "target changed",
                        ):
                            aggregate_results(root, "judge")

                    self.assertTrue(touched)
                    self.assertEqual((root / output_name).read_bytes(), original_content)

    def test_same_size_mutation_during_existing_descriptor_read_fails_closed(self):
        if not hasattr(os, "pread"):
            self.skipTest("descriptor-positioned reads are unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            with patch.object(
                eval_core,
                "_format_timestamp",
                return_value="2026-07-20T10:00:00Z",
            ):
                aggregate_results(root, "judge")

            target = root / "benchmark.json"
            target_inode = target.stat().st_ino
            real_pread = os.pread
            mutated_content: bytes | None = None

            def mutate_during_descriptor_read(descriptor, count, offset):
                nonlocal mutated_content
                chunk = real_pread(descriptor, count, offset)
                if (
                    mutated_content is None
                    and offset == 0
                    and os.fstat(descriptor).st_ino == target_inode
                ):
                    original = target.read_bytes()
                    original_metadata = target.stat()
                    mutated_content = bytes([original[0] ^ 1]) + original[1:]
                    target.write_bytes(mutated_content)
                    os.utime(
                        target,
                        ns=(
                            original_metadata.st_atime_ns,
                            original_metadata.st_mtime_ns,
                        ),
                    )
                return chunk

            with (
                patch(
                    "scripts.ai_skills_lib.eval_core.os.pread",
                    new=mutate_during_descriptor_read,
                    create=True,
                ),
                patch.object(
                    eval_core,
                    "_format_timestamp",
                    return_value="2026-07-20T10:00:01Z",
                ),
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "target changed",
                ):
                    aggregate_results(root, "judge")

            self.assertIsNotNone(mutated_content)
            self.assertEqual(target.read_bytes(), mutated_content)

    def test_replaced_staging_name_is_not_removed_during_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            injected_content = b"RAW_REPLACED_STAGING_FILE"
            real_link = os.link
            replacement_name: str | None = None

            def replace_staging_name_after_link(source, target, *args, **kwargs):
                nonlocal replacement_name
                result = real_link(source, target, *args, **kwargs)
                if replacement_name is None and target == "benchmark.json":
                    source_descriptor = kwargs["src_dir_fd"]
                    os.unlink(source, dir_fd=source_descriptor)
                    replacement_descriptor = os.open(
                        source,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=source_descriptor,
                    )
                    try:
                        os.write(replacement_descriptor, injected_content)
                    finally:
                        os.close(replacement_descriptor)
                    replacement_name = source
                return result

            with patch(
                "scripts.ai_skills_lib.eval_core.os.link",
                new=replace_staging_name_after_link,
            ):
                with self.assertRaisesRegex(ResultArtifactError, "temporary") as raised:
                    aggregate_results(root, "judge")

            self.assertIsNotNone(replacement_name)
            replacement = root / replacement_name
            self.assertEqual(replacement.read_bytes(), injected_content)
            self.assertNotIn("RAW_REPLACED_STAGING_FILE", str(raised.exception))

    def test_aggregate_descriptor_release_failure_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            self._complete_workspace(root)
            real_open = os.open
            real_close = os.close
            staging_descriptor: int | None = None
            close_failed = False

            def record_staging_descriptor(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal staging_descriptor
                descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
                if (
                    isinstance(path, str)
                    and path.startswith(".benchmark.json.")
                    and path.endswith(".tmp")
                ):
                    staging_descriptor = descriptor
                return descriptor

            def fail_staging_close(descriptor):
                nonlocal close_failed
                if not close_failed and descriptor == staging_descriptor:
                    real_close(descriptor)
                    close_failed = True
                    raise OSError("RAW_DESCRIPTOR_RELEASE_FAILURE")
                return real_close(descriptor)

            with (
                patch(
                    "scripts.ai_skills_lib.eval_core.os.open",
                    new=record_staging_descriptor,
                ),
                patch(
                    "scripts.ai_skills_lib.eval_core.os.close",
                    new=fail_staging_close,
                ),
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "release aggregate result handles",
                ) as raised:
                    aggregate_results(root, "judge")

            self.assertTrue(close_failed)
            self.assertNotIn("RAW_DESCRIPTOR_RELEASE_FAILURE", str(raised.exception))


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

    def test_judge_response_rejects_duplicate_json_keys(self):
        valid = json.dumps(sample_judge_response())
        duplicate = '{"assertion_results": [],' + valid[1:]

        with self.assertRaisesRegex(ResultArtifactError, "duplicate JSON key"):
            parse_judge_response(duplicate, expected_judge_context())

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

    def test_judge_response_content_and_reference_counts_are_bounded(self):
        oversized_evidence = sample_judge_response()
        oversized_evidence["assertion_results"][0]["evidence"] = "x" * 4097
        excessive_references = sample_judge_response()
        reference = {
            "artifact": "outputs/response.md",
            "locator": "response paragraph",
        }
        excessive_references["assertion_results"][0]["evidence_refs"] = [
            reference for _ in range(17)
        ]

        for document in (oversized_evidence, excessive_references):
            with self.subTest(document=document):
                with self.assertRaisesRegex(ResultArtifactError, "bounded"):
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
    def _aggregate_cli(self, root: Path) -> tuple[int, str]:
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
        return result, output.getvalue()

    def _complete_comparison_workspace(self, root: Path):
        required = ("candidate", "reference")
        workspace = create_test_result_workspace(
            root,
            preserved_run_manifest(
                variant="candidate",
                contributes_to_outcome=True,
                required_variants=required,
                compare_to="reference",
            ),
            preserved_run_manifest(
                variant="reference",
                contributes_to_outcome=False,
                required_variants=required,
            ),
        )
        candidate_paths, _ = write_preserved_run(
            workspace,
            variant="candidate",
            contributes_to_outcome=True,
            passed=True,
            required_variants=required,
            compare_to="reference",
        )
        reference_paths, _ = write_preserved_run(
            workspace,
            variant="reference",
            contributes_to_outcome=False,
            passed=False,
            required_variants=required,
        )
        return workspace, candidate_paths, reference_paths

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
                    workspace = create_test_result_workspace(
                        root,
                        preserved_run_manifest(
                            variant="candidate",
                            contributes_to_outcome=True,
                            required_variants=required,
                            compare_to="reference",
                        ),
                        preserved_run_manifest(
                            variant="reference",
                            contributes_to_outcome=False,
                            required_variants=required,
                        ),
                    )
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

    def test_aggregate_cli_rejects_missing_or_unreadable_invocation_and_artifacts(self):
        for case in ("removed", "symlink", "directory", "non_utf8_grading"):
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "results"
                    workspace, candidate_paths, _ = self._complete_comparison_workspace(root)
                    if case == "removed":
                        workspace.invocation_manifest.unlink()
                    elif case == "symlink":
                        external_manifest = root.parent / "external-invocation.json"
                        external_manifest.write_bytes(workspace.invocation_manifest.read_bytes())
                        workspace.invocation_manifest.unlink()
                        workspace.invocation_manifest.symlink_to(external_manifest)
                    elif case == "directory":
                        workspace.invocation_manifest.unlink()
                        workspace.invocation_manifest.mkdir()
                    else:
                        candidate_paths.grading.write_bytes(b"\xff")

                    result, output = self._aggregate_cli(root)

                    self.assertEqual(result, 2)
                    self.assertIn("FAILED", output)
                    if case == "non_utf8_grading":
                        self.assertIn("cannot read trustworthy result", output)
                    else:
                        self.assertIn("regular invocation.json", output)

    def test_aggregate_cli_rejects_missing_or_injected_complete_behavior_groups(self):
        required = ("candidate", "reference")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "missing-group"
            primary_group = "ticket-workflow/primary"
            removed_group = "ticket-workflow/removed"
            workspace = create_test_result_workspace(
                root,
                *(
                    preserved_run_manifest(
                        run_id=f"{group.rsplit('/', 1)[1]}-{variant}",
                        group_id=group,
                        variant=variant,
                        contributes_to_outcome=variant == "candidate",
                        required_variants=required,
                        compare_to="reference" if variant == "candidate" else None,
                    )
                    for group in (primary_group, removed_group)
                    for variant in required
                ),
            )
            removed_paths = []
            for group in (primary_group, removed_group):
                for variant in required:
                    paths, _ = write_preserved_run(
                        workspace,
                        run_id=f"{group.rsplit('/', 1)[1]}-{variant}",
                        group_id=group,
                        variant=variant,
                        contributes_to_outcome=variant == "candidate",
                        passed=True,
                        required_variants=required,
                        compare_to="reference" if variant == "candidate" else None,
                    )
                    if group == removed_group:
                        removed_paths.append(paths)
            for paths in removed_paths:
                shutil.rmtree(paths.root)

            result, output = self._aggregate_cli(root)

            self.assertEqual(result, 2)
            self.assertIn("attempt set does not match", output)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "injected-group"
            workspace, candidate_paths, reference_paths = self._complete_comparison_workspace(root)
            for source, run_id in (
                (candidate_paths, "injected-candidate"),
                (reference_paths, "injected-reference"),
            ):
                target = workspace.attempts / run_id
                shutil.copytree(source.root, target)
                for artifact_name in ("attempt.json", "timing.json", "grading.json"):
                    artifact_path = target / artifact_name
                    document = json.loads(artifact_path.read_text(encoding="utf-8"))
                    document["run_id"] = run_id
                    if "aggregation" in document:
                        document["aggregation"]["group_id"] = "ticket-workflow/injected"
                    artifact_path.write_text(json.dumps(document), encoding="utf-8")

            result, output = self._aggregate_cli(root)

            self.assertEqual(result, 2)
            self.assertIn("immutable invocation manifest", output)

    def test_aggregate_cli_maps_benchmark_write_errors_to_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
            write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            output = StringIO()

            with patch(
                "scripts.ai_skills_lib.eval_core.os.link",
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
            self.assertIn("cannot write aggregate result artifacts", output.getvalue())
            self.assertNotIn("read-only result directory", output.getvalue())

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
