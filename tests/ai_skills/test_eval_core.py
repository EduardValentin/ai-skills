from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from io import StringIO
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
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
    AssertionContract,
    AssertionDefinition,
    AssertionResult,
    AttemptManifest,
    AttemptPaths,
    EvalRunRecord,
    GraderRecord,
    GradingBasisRecord,
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
    canonical_document_sha256,
    combine_grading_results,
    create_attempt_workspace,
    create_result_workspace,
    declare_invocation,
    default_results_root,
    digest_evidence_bundle,
    format_benchmark_summary,
    invoke_judge,
    parse_judge_response,
    prepare_exact_judge_evidence,
    record_harness_timing,
    validate_result_document,
    write_incomplete_attempt_artifacts,
    write_eval_run_artifacts,
)
from scripts.ai_skills_lib.harness import (
    bind_harness_request,
    CapturedOutputPath,
    HarnessExecution,
    HarnessRequest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEST_JUDGE_CONTROL = "TEST_JUDGE_CONTROL\n"
TEST_INVOCATION_ID = "0" * 32
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas" / "ai-skills"


def load_schema(name: str) -> dict[str, object]:
    path = SCHEMA_ROOT / name
    if not path.is_file():
        raise AssertionError(f"missing offline result schema: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def sample_timing() -> dict[str, object]:
    return {
        "schema_version": "ai-skills.eval.timing.v1",
        "invocation_id": TEST_INVOCATION_ID,
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
        "execution_binding": None,
        "successful_skill_reads": [],
        "expected_skill_path": None,
    }


def sample_grading(
    *,
    grade_source: str = "judge",
    grader_type: str = "llm",
) -> dict[str, object]:
    return {
        "schema_version": "ai-skills.eval.grading.v1",
        "invocation_id": TEST_INVOCATION_ID,
        "run_id": "run-with-skill",
        "skill_name": "ticket-workflow",
        "case_id": "intake",
        "run_kind": "with_skill",
        "evidence_sha256": "0" * 64,
        "grade_source": grade_source,
        "grader": {
            "type": grader_type,
            "model": "reported-model" if grader_type == "llm" else None,
            "reasoning_effort": "high" if grader_type == "llm" else None,
            "prompt_version": "agent-skills-eval-v1",
            **(
                {"reviewer_label": "schema test reviewer"}
                if grader_type == "human"
                else {}
            ),
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
        "invocation_id": TEST_INVOCATION_ID,
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

    def test_grading_basis_uses_the_declared_judge_scalar_bounds(self):
        control = "x" * (eval_core._MAX_RESULT_JSON_SCALAR_BYTES + 1024)
        basis = replace(
            generated_grading_basis(),
            judge_control=control,
            invocation_id=TEST_INVOCATION_ID,
        ).to_dict()

        validate_result_document(basis, "grading-basis.schema.json")
        parsed = eval_core._parse_result_document(
            json.dumps(basis).encode("utf-8"),
            Path("grading_basis.json"),
            "grading-basis.schema.json",
        )

        self.assertEqual(parsed["judge_control"], control)

        basis["judge_control"] = "x" * (eval_core.MAX_JUDGE_PROMPT_BYTES + 1)
        with self.assertRaisesRegex(ResultArtifactError, "JSON scalar limit"):
            eval_core._parse_result_document(
                json.dumps(basis).encode("utf-8"),
                Path("grading_basis.json"),
                "grading-basis.schema.json",
            )


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


def generated_grading_basis(
    *,
    run_id: str = "run-with-skill",
    run_kind: str = "with_skill",
    passed: bool = True,
    actor_output_files: tuple[tuple[str, bytes], ...] = (),
) -> GradingBasisRecord:
    evidence = {
        "outputs/response.md": "Please provide the acceptance criteria.",
        "transcript.md": "# Transcript\n",
        "execution_trace.jsonl": json.dumps(
            {"event": "harness.completed", "exit_code": 0},
            sort_keys=True,
        ),
    }
    for path, content in actor_output_files:
        evidence[f"outputs/{path}"] = content.decode("utf-8")
    _, judge_prompt = prepare_exact_judge_evidence(
        evidence,
        control_prefix=TEST_JUDGE_CONTROL,
    )
    return GradingBasisRecord(
        run_id=run_id,
        skill_name="ticket-workflow",
        case_id="intake",
        run_kind=run_kind,
        judge_response=json.dumps(
            {
                "assertion_results": [
                    {
                        "id": "assertion-1",
                        "passed": passed,
                        "evidence": "The response requests acceptance criteria.",
                        "evidence_refs": [
                            {
                                "artifact": "outputs/response.md",
                                "locator": "paragraph 1",
                            }
                        ],
                    }
                ]
            },
            sort_keys=True,
        ),
        judge_control=TEST_JUDGE_CONTROL,
        judge_prompt_sha256=hashlib.sha256(
            judge_prompt.encode("utf-8")
        ).hexdigest(),
        allowed_evidence_artifacts=tuple(evidence),
        judge_model="reported-model",
        judge_reasoning_effort="high",
        judge_duration_ms=10,
        judge_total_tokens=6,
        judge_prompt_version="agent-skills-eval-v1",
        graded_at="2026-07-19T10:00:02Z",
        deterministic_checks=(),
        deterministic_schemas=(),
        deterministic_results=(),
        judge_execution_binding=execution_binding_for_test(
            role="judge",
            run_id=run_id,
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


def execution_binding_for_test(
    *,
    role: str,
    run_id: str,
    invocation_id: str = TEST_INVOCATION_ID,
):
    request = HarnessRequest(
        role=role,
        run_variant=run_id,
        prompt="Bound test request.",
        timeout_seconds=30,
        model="reported-model",
        reasoning_effort="medium",
    )
    return bind_harness_request(
        request,
        invocation_id=invocation_id,
        run_id=run_id,
    ).execution_binding


def expected_judge_context() -> JudgeGradingContext:
    return JudgeGradingContext(
        invocation_id=TEST_INVOCATION_ID,
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
        runtime_input_sha256="0" * 64,
        scenario_definition_sha256=canonical_document_sha256(
            {"scenario": "ticket-workflow/intake"}
        ),
        deterministic_input_sha256=canonical_document_sha256(
            {"checks": [], "schemas": []}
        ),
        judge_control_sha256=hashlib.sha256(
            TEST_JUDGE_CONTROL.encode("utf-8")
        ).hexdigest(),
        assertion_contract=(
            AssertionContract(
                id="assertion-1",
                kind="assertion",
                text="The response identifies missing ticket context.",
                checked_by="judge",
            ),
        ),
        aggregation=AggregationMetadata(
            group_id=group_id,
            variant=variant,
            contributes_to_outcome=contributes_to_outcome,
            required_variants=required_variants,
            compare_to=compare_to,
        ),
    )


def sample_trigger_attempt_manifest(
    *,
    run_number: int,
    expected_activation: bool = True,
    scenario_definition_sha256: str = "a" * 64,
) -> AttemptManifest:
    expected_text = (
        "The installed harness "
        f"{'loads' if expected_activation else 'does not load'} "
        "the ticket-workflow skill."
    )
    return AttemptManifest(
        run_id=f"trigger-run-{run_number}",
        skill_name="ticket-workflow",
        case_id="pickup",
        run_kind="trigger",
        runtime_input_sha256=scenario_definition_sha256,
        scenario_definition_sha256=scenario_definition_sha256,
        expected_activation=expected_activation,
        expected_skill_catalog_path=(
            "codex-home/skills/ticket-workflow/SKILL.md"
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
            group_id="ticket-workflow/pickup",
            variant="installed_harness",
            contributes_to_outcome=True,
            required_variants=("installed_harness",),
            minimum_pass_rate=2 / 3,
            configured_runs=3,
            run_number=run_number,
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
    actor_file_count: int = 0,
) -> tuple[object, GradingRecord]:
    run_id = run_id or f"run-{variant}"
    execution = completed_harness_execution()
    execution = replace(
        execution,
        execution_binding=execution_binding_for_test(
            role="actor",
            run_id=run_id,
            invocation_id=workspace.invocation_id,
        ),
    )
    timing = record_harness_timing(
        invocation_id=workspace.invocation_id,
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
    actor_output_files: list[tuple[str, bytes]] = []
    for index in range(actor_file_count):
        name = f"actor-created-{index:04}.txt"
        (paths.root / "outputs" / name).write_bytes(b"")
        actor_output_files.append((name, b""))
    grading = write_eval_run_artifacts(
        paths,
        EvalRunRecord(
            response=execution.response,
            transcript="# Transcript\n",
            execution_trace=(
                *execution.trace,
                {
                    "event": "judge_harness_event",
                    "detail": {"event": "judge.completed"},
                },
                {
                    "event": "judge_completed",
                    "duration_ms": 10,
                    "total_tokens": 6,
                    "model": "reported-model",
                    "reasoning_effort": "high",
                },
            ),
            timing=timing,
            grading=grading,
            grading_basis=generated_grading_basis(
                run_id=run_id,
                run_kind=variant,
                passed=passed,
                actor_output_files=tuple(actor_output_files),
            ),
        ),
        actor_output_files=tuple(actor_output_files),
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
    workspace.invocation_id = TEST_INVOCATION_ID
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
            reviewer_label="deterministic test reviewer",
        ),
        graded_at="2026-07-19T10:00:03Z",
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


def rebind_persisted_grading_to_current_evidence(paths: AttemptPaths) -> None:
    outputs_root = paths.root / "outputs"
    directories = tuple(
        path.relative_to(paths.root).as_posix()
        for path in outputs_root.rglob("*")
        if path.is_dir()
    )
    evidence_paths = {
        paths.manifest,
        paths.timing,
        paths.response,
        paths.transcript,
        paths.execution_trace,
        *(
            (paths.grading_basis,)
            if paths.grading_basis.is_file()
            else ()
        ),
        *(
            path
            for path in outputs_root.rglob("*")
            if path.is_file()
        ),
    }
    evidence_sha256 = digest_evidence_bundle(
        directories,
        tuple(
            (path.relative_to(paths.root).as_posix(), path.read_bytes())
            for path in evidence_paths
        ),
    )
    for grading_path in (paths.grading, paths.manual_grading):
        if not grading_path.is_file():
            continue
        document = json.loads(grading_path.read_text(encoding="utf-8"))
        document["evidence_sha256"] = evidence_sha256
        grading_path.write_text(
            f"{json.dumps(document, indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )


class CodexSkillEvidencePathTests(unittest.TestCase):
    def test_canonical_codex_skill_path_uses_the_logical_case_root(self):
        self.assertEqual(
            eval_core.canonical_codex_skill_path("ticket-workflow"),
            PurePosixPath(
                "/case/codex-home/skills/ticket-workflow/SKILL.md"
            ),
        )

    def test_codex_skill_evidence_path_rejects_a_foreign_absolute_root(self):
        self.assertEqual(
            eval_core.classify_codex_skill_evidence_path(
                (
                    "/attacker-controlled/case/codex-home/skills/"
                    "ticket-workflow/SKILL.md"
                ),
                "ticket-workflow",
            ),
            eval_core.StructuredSkillPathKind.NONCANONICAL,
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
            original_mkdir = os.mkdir

            def fail_attempts_directory(path, mode=0o777, *, dir_fd=None):
                if path == "attempts" and dir_fd is not None:
                    raise OSError("cannot initialize attempts")
                return original_mkdir(path, mode, dir_fd=dir_fd)

            with patch(
                "scripts.ai_skills_lib.eval_core.os.mkdir",
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
            original_mkdir = os.mkdir

            def inject_child_then_fail(path, mode=0o777, *, dir_fd=None):
                if path == "attempts" and dir_fd is not None:
                    injected_marker.parent.mkdir()
                    injected_marker.write_text("retain me", encoding="utf-8")
                    raise OSError("unbounded failure detail " * 10_000)
                return original_mkdir(path, mode, dir_fd=dir_fd)

            with patch(
                "scripts.ai_skills_lib.eval_core.os.mkdir",
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
            original_mkdir = os.mkdir

            def replace_root_then_fail(path, mode=0o777, *, dir_fd=None):
                if path == "attempts" and dir_fd is not None:
                    (root / "original.txt").write_text("original", encoding="utf-8")
                    root.rename(displaced_root)
                    original_mkdir(root, 0o777)
                    replacement_marker.write_text("replacement", encoding="utf-8")
                    raise OSError("attempt initialization failed")
                return original_mkdir(path, mode, dir_fd=dir_fd)

            with patch(
                "scripts.ai_skills_lib.eval_core.os.mkdir",
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
            invocation_id=TEST_INVOCATION_ID,
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
            replace(completed_harness_execution(), failure=""),
            replace(completed_harness_execution(), model=None),
            replace(completed_harness_execution(), reasoning_effort=None),
        )
        for execution in incomplete_executions:
            with self.subTest(execution=execution):
                timing = record_harness_timing(
                    invocation_id=TEST_INVOCATION_ID,
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
            invocation_id=TEST_INVOCATION_ID,
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
            persisted_grading = json.loads(
                paths.grading.read_text(encoding="utf-8")
            )
            Draft202012Validator(load_schema("grading.schema.json")).validate(
                persisted_grading
            )
            self.assertRegex(persisted_grading["evidence_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(paths.manual_grading.read_text(encoding="utf-8"), "manual review")

            with self.assertRaisesRegex(ResultArtifactError, "already exists"):
                write_eval_run_artifacts(paths, record)
            self.assertTrue(paths.grading.is_file())
            self.assertEqual(
                paths.response.read_text(encoding="utf-8"),
                record.response,
            )

    def test_complete_writer_removes_grade_when_post_write_guard_fails(self):
        manifest = sample_attempt_manifest(
            run_id="run-with-skill",
            variant="with_skill",
            required_variants=("with_skill", "without_skill"),
            compare_to="without_skill",
        )
        timing = record_harness_timing(
            invocation_id=TEST_INVOCATION_ID,
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
            response="Please provide the acceptance criteria.",
            transcript="# Transcript\n",
            execution_trace=({"event": "harness.completed"},),
            timing=timing,
            grading=generated_grading_record(),
        )

        with tempfile.TemporaryDirectory() as directory:
            workspace = create_test_result_workspace(
                Path(directory) / "run",
                manifest,
            )
            paths = create_attempt_workspace(workspace, manifest)
            stages: list[bool] = []

            def guard(response_written: bool) -> None:
                stages.append(response_written)
                if response_written:
                    raise ResultArtifactError("actor outputs changed")

            with self.assertRaisesRegex(ResultArtifactError, "actor outputs changed"):
                write_eval_run_artifacts(
                    paths,
                    record,
                    completion_guard=guard,
                )

            self.assertEqual(stages, [False, True])
            self.assertTrue(paths.timing.is_file())
            self.assertFalse(paths.grading.exists())
            self.assertEqual(list((paths.root / "outputs").iterdir()), [])

    def test_publication_failure_removes_grade_and_quarantines_actor_outputs(self):
        manifest = sample_attempt_manifest(
            variant="candidate",
            required_variants=("candidate",),
            compare_to=None,
        )
        timing = record_harness_timing(
            invocation_id=TEST_INVOCATION_ID,
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
            response="Please provide the acceptance criteria.",
            transcript="# Transcript\n",
            execution_trace=({"event": "harness.completed"},),
            timing=timing,
            grading=generated_grading_record(
                run_id=manifest.run_id,
                run_kind=manifest.run_kind,
                variant=manifest.aggregation.variant,
                required_variants=manifest.aggregation.required_variants,
                compare_to=None,
            ),
            grading_basis=generated_grading_basis(
                run_id=manifest.run_id,
                run_kind=manifest.run_kind,
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            workspace = create_test_result_workspace(root, manifest)
            paths = create_attempt_workspace(workspace, manifest)
            actor_file = paths.root / "outputs" / "actor-created.txt"
            actor_file.write_text("actor output", encoding="utf-8")
            real_publish = eval_core._write_persisted_attempt_artifacts

            def publish_then_fail(*args, **kwargs):
                real_publish(*args, **kwargs)
                raise ResultArtifactError("injected durability failure")

            with (
                patch.object(
                    eval_core,
                    "_write_persisted_attempt_artifacts",
                    side_effect=publish_then_fail,
                ),
                self.assertRaisesRegex(
                    ResultArtifactError,
                    "injected durability failure",
                ),
            ):
                write_eval_run_artifacts(
                    paths,
                    record,
                    actor_output_files=(
                        ("actor-created.txt", b"actor output"),
                    ),
                )

            self.assertFalse(paths.grading.exists())
            self.assertEqual(list((paths.root / "outputs").iterdir()), [])
            with self.assertRaisesRegex(
                ResultArtifactError,
                "required persisted artifact",
            ):
                aggregate_results(root, "judge")

    def test_complete_writer_rejects_unsafe_evidence_paths_before_persisting(self):
        timing = record_harness_timing(
            invocation_id=TEST_INVOCATION_ID,
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
    def test_invocation_rejects_mixed_trigger_query_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "trigger run",
                results_dir=base / "results",
                repository_root=repository,
            )
            manifests = (
                sample_trigger_attempt_manifest(run_number=1),
                sample_trigger_attempt_manifest(
                    run_number=2,
                    expected_activation=False,
                    scenario_definition_sha256="b" * 64,
                ),
                sample_trigger_attempt_manifest(run_number=3),
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "mixes scenario definitions or immutable contracts",
            ):
                declare_invocation(workspace, "trigger run", manifests)

            self.assertFalse(workspace.invocation_manifest.exists())

    def test_invocation_rejects_mixed_behavior_scenario_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            required = ("with_skill", "without_skill")
            with_skill = sample_attempt_manifest(
                run_id="run-with-skill",
                variant="with_skill",
                required_variants=required,
                compare_to="without_skill",
            )
            without_skill = replace(
                sample_attempt_manifest(
                    run_id="run-without-skill",
                    variant="without_skill",
                    contributes_to_outcome=False,
                    required_variants=required,
                    compare_to=None,
                ),
                scenario_definition_sha256="f" * 64,
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "mixes scenario definitions or immutable contracts",
            ):
                declare_invocation(
                    workspace,
                    "evals run",
                    (with_skill, without_skill),
                )

            self.assertFalse(workspace.invocation_manifest.exists())

    def test_invocation_rejects_different_judge_controls_within_behavior_group(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            required = ("with_skill", "without_skill")
            with_skill = sample_attempt_manifest(
                run_id="run-with-skill",
                variant="with_skill",
                required_variants=required,
                compare_to="without_skill",
            )
            without_skill = replace(
                sample_attempt_manifest(
                    run_id="run-without-skill",
                    variant="without_skill",
                    contributes_to_outcome=False,
                    required_variants=required,
                    compare_to=None,
                ),
                judge_control_sha256="f" * 64,
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "must share one judge control",
            ):
                declare_invocation(
                    workspace,
                    "evals run",
                    (with_skill, without_skill),
                )

            self.assertFalse(workspace.invocation_manifest.exists())

    def test_invocation_writer_enforces_the_result_json_byte_ceiling(self):
        manifest = sample_attempt_manifest()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            exact_workspace = create_result_workspace(
                "evals run",
                results_dir=base / "exact-results",
                repository_root=repository,
            )
            document = eval_core._invocation_document(
                exact_workspace.invocation_id,
                "evals run",
                (manifest,),
            )
            exact_size = len(
                eval_core._serialize_json_document(document).encode("utf-8")
            )
            with patch.object(
                eval_core,
                "_MAX_RESULT_JSON_FILE_BYTES",
                exact_size,
            ):
                declare_invocation(
                    exact_workspace,
                    "evals run",
                    (manifest,),
                )

            oversized_workspace = create_result_workspace(
                "evals run",
                results_dir=base / "oversized-results",
                repository_root=repository,
            )
            oversized_document = eval_core._invocation_document(
                oversized_workspace.invocation_id,
                "evals run",
                (manifest,),
            )
            oversized_size = len(
                eval_core._serialize_json_document(oversized_document).encode(
                    "utf-8"
                )
            )
            with (
                patch.object(
                    eval_core,
                    "_MAX_RESULT_JSON_FILE_BYTES",
                    oversized_size - 1,
                ),
                self.assertRaisesRegex(
                    ResultArtifactError,
                    "JSON byte limit",
                ),
            ):
                declare_invocation(
                    oversized_workspace,
                    "evals run",
                    (manifest,),
                )

            self.assertFalse(oversized_workspace.invocation_manifest.exists())

    def test_grading_basis_serialization_enforces_the_result_json_byte_ceiling(
        self,
    ):
        document = generated_grading_basis().to_dict()
        exact_size = len(
            eval_core._serialize_json_document(document).encode("utf-8")
        )

        with patch.object(
            eval_core,
            "_MAX_RESULT_JSON_FILE_BYTES",
            exact_size,
        ):
            eval_core._serialize_json_document(document)
        with (
            patch.object(
                eval_core,
                "_MAX_RESULT_JSON_FILE_BYTES",
                exact_size - 1,
            ),
            self.assertRaisesRegex(
                ResultArtifactError,
                "JSON byte limit",
            ),
        ):
            eval_core._serialize_json_document(document)

    def test_invocation_write_is_descriptor_anchored_across_root_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            displaced = base / "displaced-results"
            redirected = base / "redirected"
            redirected.mkdir()
            real_write = eval_core._write_atomic_result_file_at
            replaced = False

            def replace_root_before_write(*args, **kwargs):
                nonlocal replaced
                if not replaced:
                    workspace.root.rename(displaced)
                    workspace.root.symlink_to(
                        redirected,
                        target_is_directory=True,
                    )
                    replaced = True
                return real_write(*args, **kwargs)

            with patch.object(
                eval_core,
                "_write_atomic_result_file_at",
                side_effect=replace_root_before_write,
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "results directory changed",
                ):
                    declare_invocation(
                        workspace,
                        "evals run",
                        (sample_attempt_manifest(),),
                    )

            self.assertTrue(replaced)
            self.assertFalse((redirected / "invocation.json").exists())

    def test_attempt_creation_rejects_replaced_attempts_parent_without_writing_outside(self):
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
            displaced_attempts = base / "displaced-attempts"
            outside = base / "outside"
            outside.mkdir()
            outside_marker = outside / "marker.txt"
            outside_marker.write_text("unrelated", encoding="utf-8")
            original_read = eval_core._read_pinned_invocation_at
            replaced = False

            def replace_attempts_after_read(*args, **kwargs):
                nonlocal replaced
                result = original_read(*args, **kwargs)
                if not replaced:
                    workspace.attempts.rename(displaced_attempts)
                    workspace.attempts.symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                    replaced = True
                return result

            with patch.object(
                eval_core,
                "_read_pinned_invocation_at",
                side_effect=replace_attempts_after_read,
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "invocation attempts directory was replaced",
                ):
                    create_attempt_workspace(workspace, manifest)

            self.assertTrue(replaced)
            self.assertEqual(
                outside_marker.read_text(encoding="utf-8"),
                "unrelated",
            )
            self.assertEqual(tuple(outside.iterdir()), (outside_marker,))

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
                invocation_id=paths.invocation_id,
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
            self.assertEqual(
                manifest,
                sample_attempt_manifest().to_dict()
                | {"invocation_id": workspace.invocation_id},
            )
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

    def test_relocated_workspace_cannot_write_after_moving_inside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            external_parent = base / "external"
            workspace = create_result_workspace(
                "evals run",
                results_dir=external_parent / "results",
                repository_root=repository,
            )
            manifest = sample_attempt_manifest()
            declare_invocation(workspace, "evals run", (manifest,))
            relocated_parent = repository / "external"
            external_parent.rename(relocated_parent)
            external_parent.symlink_to(
                relocated_parent,
                target_is_directory=True,
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "outside the repository",
            ):
                eval_core.write_result_summary(workspace, "must not persist")
            with self.assertRaisesRegex(
                ResultArtifactError,
                "outside the repository",
            ):
                create_attempt_workspace(workspace, manifest)

            relocated_root = relocated_parent / "results"
            self.assertFalse((relocated_root / "summary.md").exists())
            self.assertEqual(tuple((relocated_root / "attempts").iterdir()), ())

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
            rejected_output = paths.root / "outputs" / "nested" / "credential.txt"
            rejected_output.parent.mkdir()
            rejected_output.write_text(
                "ghp_" + ("a" * 36),
                encoding="utf-8",
            )
            timing = replace(
                record_harness_timing(
                    invocation_id=paths.invocation_id,
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
            self.assertEqual(
                tuple(path.name for path in (paths.root / "outputs").iterdir()),
                ("response.md",),
            )
            self.assertFalse(rejected_output.exists())
            self.assertFalse(paths.grading.exists())

    def test_trace_serialization_and_replaced_attempt_fail_closed(self):
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
                    invocation_id=paths.invocation_id,
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
            displaced_attempt = fresh_paths.root.with_name("displaced-attempt")
            fresh_paths.root.rename(displaced_attempt)
            fresh_paths.root.mkdir()
            outside_marker = fresh_paths.root / "outside.txt"
            outside_marker.write_text("unrelated", encoding="utf-8")
            with self.assertRaisesRegex(
                ResultArtifactError,
                "attempt workspace was replaced",
            ):
                write_incomplete_attempt_artifacts(
                    fresh_paths,
                    response="partial",
                    transcript=None,
                    execution_trace=(),
                    timing=replace(timing, run_id="run-candidate-2"),
                )
            self.assertEqual(
                outside_marker.read_text(encoding="utf-8"),
                "unrelated",
            )

    def test_failed_completion_cleanup_never_unlinks_from_a_replacement_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            manifest = sample_attempt_manifest()
            workspace = create_result_workspace(
                "evals run",
                results_dir=base / "results",
                repository_root=repository,
            )
            declare_invocation(workspace, "evals run", (manifest,))
            paths = create_attempt_workspace(workspace, manifest)
            timing = record_harness_timing(
                invocation_id=paths.invocation_id,
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
            displaced_attempt = paths.root.with_name("displaced-attempt")
            outside = base / "outside"
            outside.mkdir()
            outside_grading = outside / "grading.json"
            outside_grading.write_text("unrelated", encoding="utf-8")

            def replace_attempt(response_written: bool) -> None:
                if not response_written:
                    return
                paths.root.rename(displaced_attempt)
                paths.root.symlink_to(outside, target_is_directory=True)
                raise ResultArtifactError("post-write guard failed")

            with self.assertRaisesRegex(
                ResultArtifactError,
                "post-write guard failed",
            ):
                write_eval_run_artifacts(
                    paths,
                    record,
                    completion_guard=replace_attempt,
                )

            self.assertEqual(
                outside_grading.read_text(encoding="utf-8"),
                "unrelated",
            )


class AggregationTests(unittest.TestCase):
    def test_attempt_capacity_reserves_final_result_bytes_at_the_exact_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            manifest = preserved_run_manifest(
                variant="candidate",
                contributes_to_outcome=True,
                required_variants=("candidate",),
            )
            workspace = create_test_result_workspace(root, manifest)
            paths = create_attempt_workspace(workspace, manifest)
            artifact = eval_core._ATTEMPT_ARTIFACT_BY_ATTRIBUTE["response"]
            content = b"response"
            prepared = ((artifact, content.decode("utf-8"), content),)
            current_bytes = sum(
                path.stat().st_size
                for path in root.rglob("*")
                if path.is_file()
            )
            finalization_bytes = sum(
                eval_core._ROOT_FINALIZATION_BYTE_RESERVES.values()
            )
            exact_limit = current_bytes + len(content) + finalization_bytes

            with patch.object(eval_core, "_MAX_RESULT_TREE_BYTES", exact_limit):
                eval_core._require_persisted_attempt_capacity(paths, prepared)

            with (
                patch.object(
                    eval_core,
                    "_MAX_RESULT_TREE_BYTES",
                    exact_limit - 1,
                ),
                self.assertRaisesRegex(
                    ResultArtifactError,
                    "cumulative result-tree byte limit",
                ),
            ):
                eval_core._require_persisted_attempt_capacity(paths, prepared)

    def test_attempt_entry_budget_remains_aggregatable_at_its_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            manifests = (
                preserved_run_manifest(
                    run_id="run-intake",
                    group_id="ticket-workflow/intake",
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
                preserved_run_manifest(
                    run_id="run-planning",
                    group_id="ticket-workflow/planning",
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
            workspace = create_test_result_workspace(root, *manifests)
            with patch.object(
                eval_core,
                "_MAX_RESULT_ENTRIES_PER_ATTEMPT",
                16,
            ):
                write_preserved_run(
                    workspace,
                    run_id="run-intake",
                    group_id="ticket-workflow/intake",
                    variant="candidate",
                    contributes_to_outcome=True,
                    passed=True,
                    required_variants=("candidate",),
                    actor_file_count=5,
                )
                write_preserved_run(
                    workspace,
                    run_id="run-planning",
                    group_id="ticket-workflow/planning",
                    variant="candidate",
                    contributes_to_outcome=True,
                    passed=True,
                    required_variants=("candidate",),
                    actor_file_count=5,
                )

                benchmark = aggregate_results(root, "judge")

            self.assertEqual(benchmark_exit_code(benchmark), 0)

    def test_attempt_writer_rejects_one_entry_over_its_complete_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            manifest = preserved_run_manifest(
                variant="candidate",
                contributes_to_outcome=True,
                required_variants=("candidate",),
            )
            workspace = create_test_result_workspace(root, manifest)

            with (
                patch.object(
                    eval_core,
                    "_MAX_RESULT_ENTRIES_PER_ATTEMPT",
                    16,
                ),
                self.assertRaisesRegex(
                    ResultArtifactError,
                    "per-attempt entry-count limit",
                ),
            ):
                write_preserved_run(
                    workspace,
                    variant="candidate",
                    contributes_to_outcome=True,
                    passed=True,
                    required_variants=("candidate",),
                    actor_file_count=6,
                )

    def test_aggregation_rejects_a_completed_attempt_from_an_older_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            manifest = preserved_run_manifest(
                variant="candidate",
                contributes_to_outcome=True,
                required_variants=("candidate",),
            )
            old_workspace = create_result_workspace(
                "test evals",
                results_dir=base / "old-results",
                repository_root=repository,
            )
            declare_invocation(old_workspace, "test evals", (manifest,))
            old_paths, _ = write_preserved_run(
                old_workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            current_workspace = create_result_workspace(
                "test evals",
                results_dir=base / "current-results",
                repository_root=repository,
            )
            declare_invocation(current_workspace, "test evals", (manifest,))
            current_paths = create_attempt_workspace(current_workspace, manifest)
            self.assertNotEqual(
                old_workspace.invocation_id,
                current_workspace.invocation_id,
            )

            shutil.rmtree(current_paths.root)
            shutil.copytree(old_paths.root, current_paths.root)

            with self.assertRaisesRegex(
                ResultArtifactError,
                "immutable invocation manifest",
            ):
                aggregate_results(
                    current_workspace.root,
                    "judge",
                    repository_root=repository,
                )

    def test_attempt_declaration_is_part_of_the_complete_evidence_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            manifest = preserved_run_manifest(
                variant="candidate",
                contributes_to_outcome=True,
                required_variants=("candidate",),
            )
            workspace = create_test_result_workspace(root, manifest)
            paths, _ = write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            attempt = json.loads(paths.manifest.read_text(encoding="utf-8"))
            invocation = json.loads(
                workspace.invocation_manifest.read_text(encoding="utf-8")
            )
            attempt["runtime_input_sha256"] = "1" * 64
            invocation["attempts"][0]["runtime_input_sha256"] = "1" * 64
            paths.manifest.write_text(
                f"{json.dumps(attempt, indent=2, sort_keys=True)}\n",
                encoding="utf-8",
            )
            workspace.invocation_manifest.write_text(
                f"{json.dumps(invocation, indent=2, sort_keys=True)}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "complete preserved evidence",
            ):
                aggregate_results(root, "judge")

    def test_aggregation_rejects_actor_configuration_drift_across_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            manifests = (
                preserved_run_manifest(
                    run_id="run-intake",
                    group_id="ticket-workflow/intake",
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
                preserved_run_manifest(
                    run_id="run-planning",
                    group_id="ticket-workflow/planning",
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
            workspace = create_test_result_workspace(root, *manifests)
            write_preserved_run(
                workspace,
                run_id="run-intake",
                group_id="ticket-workflow/intake",
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            drifted_paths, _ = write_preserved_run(
                workspace,
                run_id="run-planning",
                group_id="ticket-workflow/planning",
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            timing = json.loads(
                drifted_paths.timing.read_text(encoding="utf-8")
            )
            timing["model"] = "drifted-actor-model"
            drifted_paths.timing.write_text(
                f"{json.dumps(timing, indent=2, sort_keys=True)}\n",
                encoding="utf-8",
            )
            rebind_persisted_grading_to_current_evidence(drifted_paths)

            with self.assertRaisesRegex(
                ResultArtifactError,
                "invocation mixes actor model configurations",
            ):
                aggregate_results(root, "judge")

    def test_manual_aggregation_checks_generated_judge_config_across_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            manifests = (
                preserved_run_manifest(
                    run_id="run-intake",
                    group_id="ticket-workflow/intake",
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
                preserved_run_manifest(
                    run_id="run-planning",
                    group_id="ticket-workflow/planning",
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                ),
            )
            workspace = create_test_result_workspace(root, *manifests)
            first_paths, first_grading = write_preserved_run(
                workspace,
                run_id="run-intake",
                group_id="ticket-workflow/intake",
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            second_paths, second_grading = write_preserved_run(
                workspace,
                run_id="run-planning",
                group_id="ticket-workflow/planning",
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            write_complete_manual_grading(first_paths, first_grading, passed=True)
            write_complete_manual_grading(second_paths, second_grading, passed=True)

            grading = json.loads(
                second_paths.grading.read_text(encoding="utf-8")
            )
            grading["grader"]["model"] = "drifted-judge-model"
            second_paths.grading.write_text(
                f"{json.dumps(grading, indent=2, sort_keys=True)}\n",
                encoding="utf-8",
            )
            basis = json.loads(
                second_paths.grading_basis.read_text(encoding="utf-8")
            )
            basis["judge_model"] = "drifted-judge-model"
            second_paths.grading_basis.write_text(
                f"{json.dumps(basis, indent=2, sort_keys=True)}\n",
                encoding="utf-8",
            )
            trace_events = [
                json.loads(line)
                for line in second_paths.execution_trace.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            for event in trace_events:
                if event.get("event") == "judge_completed":
                    event["model"] = "drifted-judge-model"
            second_paths.execution_trace.write_text(
                "".join(
                    f"{json.dumps(event, sort_keys=True)}\n"
                    for event in trace_events
                ),
                encoding="utf-8",
            )
            rebind_persisted_grading_to_current_evidence(second_paths)
            generated = json.loads(
                second_paths.grading.read_text(encoding="utf-8")
            )
            manual = json.loads(
                second_paths.manual_grading.read_text(encoding="utf-8")
            )
            manual["evidence_sha256"] = generated["evidence_sha256"]
            second_paths.manual_grading.write_text(
                f"{json.dumps(manual, indent=2, sort_keys=True)}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "invocation mixes judge model configurations",
            ):
                aggregate_results(root, "manual")

    def test_aggregation_rejects_paired_model_configuration_drift(self):
        for role in ("actor", "judge"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
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
                write_preserved_run(
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
                    passed=True,
                    required_variants=required,
                )
                if role == "actor":
                    timing = json.loads(
                        reference_paths.timing.read_text(encoding="utf-8")
                    )
                    timing["model"] = "drifted-actor-model"
                    reference_paths.timing.write_text(
                        f"{json.dumps(timing, indent=2, sort_keys=True)}\n",
                        encoding="utf-8",
                    )
                else:
                    grading = json.loads(
                        reference_paths.grading.read_text(encoding="utf-8")
                    )
                    grading["grader"]["model"] = "drifted-judge-model"
                    reference_paths.grading.write_text(
                        f"{json.dumps(grading, indent=2, sort_keys=True)}\n",
                        encoding="utf-8",
                    )
                    basis = json.loads(
                        reference_paths.grading_basis.read_text(encoding="utf-8")
                    )
                    basis["judge_model"] = "drifted-judge-model"
                    reference_paths.grading_basis.write_text(
                        f"{json.dumps(basis, indent=2, sort_keys=True)}\n",
                        encoding="utf-8",
                    )
                    trace_events = [
                        json.loads(line)
                        for line in reference_paths.execution_trace.read_text(
                            encoding="utf-8"
                        ).splitlines()
                    ]
                    for event in trace_events:
                        if event.get("event") == "judge_completed":
                            event["model"] = "drifted-judge-model"
                    reference_paths.execution_trace.write_text(
                        "".join(
                            f"{json.dumps(event, sort_keys=True)}\n"
                            for event in trace_events
                        ),
                        encoding="utf-8",
                    )
                rebind_persisted_grading_to_current_evidence(reference_paths)

                with self.assertRaisesRegex(
                    ResultArtifactError,
                    f"mixes {role} model configurations",
                ):
                    aggregate_results(root, "judge")

    def test_behavior_aggregation_rejects_a_grade_rewritten_after_judging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            manifest = preserved_run_manifest(
                variant="candidate",
                contributes_to_outcome=True,
                required_variants=("candidate",),
            )
            workspace = create_test_result_workspace(root, manifest)
            paths, _ = write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=False,
                required_variants=("candidate",),
            )
            grading = json.loads(paths.grading.read_text(encoding="utf-8"))
            grading["assertion_results"][0]["passed"] = True
            grading["summary"] = {
                "passed": 1,
                "failed": 0,
                "total": 1,
                "pass_rate": 1.0,
            }
            paths.grading.write_text(
                f"{json.dumps(grading, indent=2, sort_keys=True)}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "exactly derived from the preserved judge result",
            ):
                aggregate_results(root, "judge")

    def test_behavior_aggregation_requires_the_preserved_judge_basis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            manifest = preserved_run_manifest(
                variant="candidate",
                contributes_to_outcome=True,
                required_variants=("candidate",),
            )
            workspace = create_test_result_workspace(root, manifest)
            paths, _ = write_preserved_run(
                workspace,
                variant="candidate",
                contributes_to_outcome=True,
                passed=True,
                required_variants=("candidate",),
            )
            paths.grading_basis.unlink()

            with self.assertRaisesRegex(
                ResultArtifactError,
                "complete preserved evidence",
            ):
                aggregate_results(root, "judge")

    def test_behavior_aggregation_rejects_outputs_changed_after_grading(self):
        required = ("with_skill", "without_skill")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            workspace = create_test_result_workspace(
                root,
                preserved_run_manifest(
                    variant="with_skill",
                    contributes_to_outcome=True,
                    required_variants=required,
                    compare_to="without_skill",
                ),
                preserved_run_manifest(
                    variant="without_skill",
                    contributes_to_outcome=False,
                    required_variants=required,
                ),
            )
            candidate, _ = write_preserved_run(
                workspace,
                variant="with_skill",
                contributes_to_outcome=True,
                passed=True,
                required_variants=required,
                compare_to="without_skill",
            )
            write_preserved_run(
                workspace,
                variant="without_skill",
                contributes_to_outcome=False,
                passed=False,
                required_variants=required,
            )
            (candidate.root / "outputs" / "late.json").write_text(
                '{"state":"changed"}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "does not match the complete preserved evidence",
            ):
                aggregate_results(root, "judge")

    def test_aggregation_rejects_fixed_evidence_changed_after_grading(self):
        mutations = {
            "response": lambda paths: paths.response.write_text(
                "changed response\n",
                encoding="utf-8",
            ),
            "transcript": lambda paths: paths.transcript.write_text(
                "changed transcript\n",
                encoding="utf-8",
            ),
            "execution trace": lambda paths: paths.execution_trace.write_text(
                '{"event":"changed"}\n',
                encoding="utf-8",
            ),
        }
        for artifact, mutate in mutations.items():
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                manifest = preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                )
                workspace = create_test_result_workspace(root, manifest)
                paths, _ = write_preserved_run(
                    workspace,
                    variant="candidate",
                    contributes_to_outcome=True,
                    passed=True,
                    required_variants=("candidate",),
                )
                mutate(paths)

                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "does not match the complete preserved evidence",
                ):
                    aggregate_results(root, "judge")

    def test_aggregation_rejects_terminal_decisions_that_contradict_the_benchmark(self):
        cases = (
            (True, "expectations failed"),
            (False, "pass"),
        )
        for passed, terminal_decision in cases:
            with self.subTest(
                passed=passed,
                terminal_decision=terminal_decision,
            ), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                manifest = preserved_run_manifest(
                    variant="candidate",
                    contributes_to_outcome=True,
                    required_variants=("candidate",),
                )
                workspace = create_test_result_workspace(root, manifest)
                write_preserved_run(
                    workspace,
                    variant="candidate",
                    contributes_to_outcome=True,
                    passed=passed,
                    required_variants=("candidate",),
                )

                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "terminal decision contradicts benchmark outcome",
                ):
                    aggregate_results(
                        root,
                        "judge",
                        terminal_decision=terminal_decision,
                    )

                self.assertFalse((root / "benchmark.json").exists())
                self.assertFalse((root / "summary.md").exists())

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
            rebind_persisted_grading_to_current_evidence(paths)

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
                json.dumps(
                    sample_attempt_manifest().to_dict()
                    | {"invocation_id": TEST_INVOCATION_ID}
                ),
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
                    reviewer_label="deterministic test reviewer",
                ),
                assertion_results=(),
                summary=GradingSummary(passed=0, failed=0, total=0, pass_rate=0.0),
            )
            paths.manual_grading.write_text(json.dumps(manual.to_dict()), encoding="utf-8")

            with self.assertRaisesRegex(ResultArtifactError, "assertion_results"):
                aggregate_results(root, "manual")

    def test_manual_override_requires_human_assertion_authority(self):
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
            write_complete_manual_grading(paths, generated, passed=True)
            manual = json.loads(paths.manual_grading.read_text(encoding="utf-8"))
            manual["assertion_results"][0]["checked_by"] = "judge"
            paths.manual_grading.write_text(
                json.dumps(manual),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ResultArtifactError,
                "must be checked by a human",
            ):
                aggregate_results(root, "manual")

    def test_manual_override_preserves_deterministic_results_and_evidence(self):
        generated = sample_grading()
        generated["assertion_results"][0].update(
            {
                "passed": False,
                "checked_by": "deterministic",
                "evidence": "The required artifact was absent.",
                "evidence_refs": [
                    {
                        "artifact": "outputs/response.md",
                        "locator": "required artifact check",
                    }
                ],
            }
        )
        generated["summary"] = {
            "passed": 0,
            "failed": 1,
            "total": 1,
            "pass_rate": 0.0,
        }
        manual = copy.deepcopy(generated)
        manual.update(
            {
                "grade_source": "manual",
                "graded_at": "2026-07-19T10:00:03Z",
                "grader": {
                    "type": "human",
                    "model": None,
                    "reasoning_effort": None,
                    "prompt_version": "manual-review-v1",
                    "reviewer_label": "deterministic test reviewer",
                },
            }
        )
        manual["assertion_results"][0]["checked_by"] = "human"
        manual_path = Path("manual_grading.json")

        eval_core._validate_complete_manual_override(
            generated,
            manual,
            sample_timing(),
            manual_path,
        )

        mutations = (
            ("passed", True),
            ("evidence", "Human review says the artifact exists."),
            (
                "evidence_refs",
                [
                    {
                        "artifact": "outputs/response.md",
                        "locator": "different locator",
                    }
                ],
            ),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(manual)
                changed["assertion_results"][0][field] = value
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "cannot override deterministic assertion",
                ):
                    eval_core._validate_complete_manual_override(
                        generated,
                        changed,
                        sample_timing(),
                        manual_path,
                    )

    def test_manual_override_requires_distinct_human_reviewer_provenance(self):
        invalid_updates = (
            (
                "missing reviewer",
                lambda manual, generated: manual["grader"].pop(
                    "reviewer_label", None
                ),
                "grading.schema",
            ),
            (
                "model-backed human",
                lambda manual, generated: manual["grader"].update(
                    {"model": "judge-model"}
                ),
                "grading.schema",
            ),
            (
                "reused generated timestamp",
                lambda manual, generated: manual.update(
                    {"graded_at": generated["graded_at"]}
                ),
                "timestamp",
            ),
            (
                "backdated review",
                lambda manual, generated: manual.update(
                    {"graded_at": "2026-07-19T09:59:59Z"}
                ),
                "timestamp",
            ),
        )
        for label, mutate, expected in invalid_updates:
            with (
                self.subTest(label=label),
                tempfile.TemporaryDirectory() as directory,
            ):
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
                write_complete_manual_grading(paths, generated, passed=True)
                generated_document = json.loads(
                    paths.grading.read_text(encoding="utf-8")
                )
                manual = json.loads(
                    paths.manual_grading.read_text(encoding="utf-8")
                )
                mutate(manual, generated_document)
                paths.manual_grading.write_text(
                    json.dumps(manual),
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(ResultArtifactError, expected):
                    aggregate_results(root, "manual")

    def test_without_skill_aggregation_rejects_target_and_noncanonical_skill_paths(
        self,
    ):
        path_cases = (
            (
                "canonical_target",
                (
                    "/sandbox/case/codex-home/skills/"
                    "ticket-workflow/SKILL.md"
                ),
            ),
            (
                "dotdot_target_alias",
                (
                    "/sandbox/case/codex-home/skills/"
                    "beta/../ticket-workflow/SKILL.md"
                ),
            ),
            (
                "dotdot_other_alias",
                (
                    "/sandbox/case/codex-home/skills/"
                    "ticket-workflow/../beta/SKILL.md"
                ),
            ),
            (
                "dot_segment",
                (
                    "/sandbox/case/codex-home/skills/"
                    "./ticket-workflow/SKILL.md"
                ),
            ),
            (
                "duplicate_separator",
                (
                    "/sandbox/case/codex-home/skills//"
                    "ticket-workflow/SKILL.md"
                ),
            ),
            (
                "platform_separator_ambiguity",
                (
                    "\\sandbox\\case\\codex-home\\skills\\"
                    "ticket-workflow\\SKILL.md"
                ),
            ),
            (
                "unstructured_absolute",
                "/sandbox/case/ticket-workflow/SKILL.md",
            ),
        )
        evidence_kinds = (
            "successful_skill_reads",
            "expected_skill_path",
            "skill_read",
        )
        for evidence_kind in evidence_kinds:
            for case_name, path_text in path_cases:
                with (
                    self.subTest(
                        evidence_kind=evidence_kind,
                        case_name=case_name,
                    ),
                    tempfile.TemporaryDirectory() as directory,
                ):
                    root = Path(directory) / "results"
                    manifest = preserved_run_manifest(
                        variant="without_skill",
                        contributes_to_outcome=False,
                        required_variants=("without_skill",),
                    )
                    workspace = create_test_result_workspace(root, manifest)
                    paths, _ = write_preserved_run(
                        workspace,
                        variant="without_skill",
                        contributes_to_outcome=False,
                        passed=True,
                        required_variants=("without_skill",),
                    )
                    if evidence_kind == "skill_read":
                        events = [
                            json.loads(line)
                            for line in paths.execution_trace.read_text(
                                encoding="utf-8"
                            ).splitlines()
                        ]
                        events.insert(
                            1,
                            {
                                "event": "skill_read",
                                "path": path_text,
                            },
                        )
                        paths.execution_trace.write_text(
                            "".join(
                                f"{json.dumps(event, sort_keys=True)}\n"
                                for event in events
                            ),
                            encoding="utf-8",
                        )
                        basis = json.loads(
                            paths.grading_basis.read_text(encoding="utf-8")
                        )
                        actor_trace = "\n".join(
                            json.dumps(event, sort_keys=True)
                            for event in events
                            if event.get("event")
                            not in {
                                "judge_harness_event",
                                "judge_completed",
                            }
                        )
                        _, judge_prompt = prepare_exact_judge_evidence(
                            {
                                "outputs/response.md": (
                                    paths.response.read_text(encoding="utf-8")
                                ),
                                "transcript.md": paths.transcript.read_text(
                                    encoding="utf-8"
                                ),
                                "execution_trace.jsonl": actor_trace,
                            },
                            control_prefix=basis["judge_control"],
                        )
                        basis["judge_prompt_sha256"] = hashlib.sha256(
                            judge_prompt.encode("utf-8")
                        ).hexdigest()
                        paths.grading_basis.write_text(
                            json.dumps(basis),
                            encoding="utf-8",
                        )
                    else:
                        timing = json.loads(
                            paths.timing.read_text(encoding="utf-8")
                        )
                        timing[evidence_kind] = (
                            [path_text]
                            if evidence_kind == "successful_skill_reads"
                            else path_text
                        )
                        paths.timing.write_text(
                            json.dumps(timing),
                            encoding="utf-8",
                        )
                    rebind_persisted_grading_to_current_evidence(paths)

                    with self.assertRaisesRegex(
                        ResultArtifactError,
                        "without_skill",
                    ):
                        aggregate_results(root, "judge")

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
        grading_basis = grading_path.parent / "grading_basis.json"
        if grading_path.name == "grading.json" and grading_basis.is_file():
            basis = json.loads(grading_basis.read_text(encoding="utf-8"))
            response = json.loads(basis["judge_response"])
            response["assertion_results"][0]["evidence_refs"][0][
                "artifact"
            ] = artifact
            basis["judge_response"] = json.dumps(response, sort_keys=True)
            grading_basis.write_text(json.dumps(basis), encoding="utf-8")

    def _admit_judged_evidence(
        self,
        paths: AttemptPaths,
        *artifacts: str,
    ) -> None:
        basis = json.loads(paths.grading_basis.read_text(encoding="utf-8"))
        allowed = basis["allowed_evidence_artifacts"]
        for artifact in artifacts:
            if artifact not in allowed:
                allowed.append(artifact)
        trace_events = [
            json.loads(line)
            for line in paths.execution_trace.read_text(encoding="utf-8").splitlines()
        ]
        actor_trace = "\n".join(
            json.dumps(event, sort_keys=True)
            for event in trace_events
            if event.get("event") not in {"judge_harness_event", "judge_completed"}
        )
        evidence = {
            "outputs/response.md": paths.response.read_text(encoding="utf-8"),
            "transcript.md": paths.transcript.read_text(encoding="utf-8"),
            "execution_trace.jsonl": actor_trace,
        }
        for artifact in allowed:
            if artifact in evidence:
                continue
            evidence[artifact] = (paths.root / artifact).read_text(encoding="utf-8")
        _, judge_prompt = prepare_exact_judge_evidence(
            evidence,
            control_prefix=basis["judge_control"],
        )
        basis["judge_prompt_sha256"] = hashlib.sha256(
            judge_prompt.encode("utf-8")
        ).hexdigest()
        paths.grading_basis.write_text(json.dumps(basis), encoding="utf-8")

    def test_behavior_aggregation_requires_isolated_judge_lifecycle_evidence(self):
        cases = ("missing judge lifecycle", "forbidden judge tool")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                _, paths, _ = self._complete_workspace(root)
                trace_path = paths.execution_trace
                events = [
                    json.loads(line)
                    for line in trace_path.read_text(encoding="utf-8").splitlines()
                ]
                if case == "missing judge lifecycle":
                    events = [
                        event
                        for event in events
                        if event.get("event") != "judge_harness_event"
                    ]
                    expected = "missing judge harness evidence"
                else:
                    wrapper = next(
                        event
                        for event in events
                        if event.get("event") == "judge_harness_event"
                    )
                    wrapper["detail"] = {"event": "tool_completed"}
                    expected = "judge isolation was violated"
                trace_path.write_text(
                    "".join(
                        f"{json.dumps(event, sort_keys=True)}\n"
                        for event in events
                    ),
                    encoding="utf-8",
                )
                rebind_persisted_grading_to_current_evidence(paths)

                with self.assertRaisesRegex(ResultArtifactError, expected):
                    aggregate_results(root, "judge")

    def test_behavior_aggregation_accepts_a_near_limit_actor_trace_with_judge_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            _, paths, _ = self._complete_workspace(root)
            existing_events = [
                json.loads(line)
                for line in paths.execution_trace.read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            judge_events = [
                event
                for event in existing_events
                if event.get("event")
                in {"judge_harness_event", "judge_completed"}
            ]
            actor_events: list[dict[str, object]] = []
            actor_trace = ""
            index = 0
            while True:
                event = {
                    "event": "actor_trace_detail",
                    "index": index,
                    "detail": "x" * 3000,
                }
                candidate_events = (*actor_events, event)
                candidate = "\n".join(
                    json.dumps(
                        item,
                        sort_keys=True,
                        ensure_ascii=True,
                        allow_nan=False,
                    )
                    for item in candidate_events
                )
                if (
                    len(candidate.encode("utf-8"))
                    > eval_core.MAX_JUDGE_ARTIFACT_BYTES
                ):
                    break
                actor_events.append(event)
                actor_trace = candidate
                index += 1

            best_event: dict[str, object] | None = None
            best_trace = actor_trace
            for filler_size in range(1, 4097):
                event = {
                    "event": "actor_trace_tail",
                    "detail": "y" * filler_size,
                }
                candidate = "\n".join(
                    json.dumps(
                        item,
                        sort_keys=True,
                        ensure_ascii=True,
                        allow_nan=False,
                    )
                    for item in (*actor_events, event)
                )
                if (
                    len(candidate.encode("utf-8"))
                    > eval_core.MAX_JUDGE_ARTIFACT_BYTES
                ):
                    break
                best_event = event
                best_trace = candidate
            if best_event is not None:
                actor_events.append(best_event)
                actor_trace = best_trace

            preserved = "".join(
                f"{json.dumps(event, sort_keys=True)}\n"
                for event in (*actor_events, *judge_events)
            )
            self.assertLessEqual(
                len(actor_trace.encode("utf-8")),
                eval_core.MAX_JUDGE_ARTIFACT_BYTES,
            )
            self.assertGreater(
                len(preserved.encode("utf-8")),
                eval_core.MAX_JUDGE_ARTIFACT_BYTES,
            )
            paths.execution_trace.write_text(
                preserved,
                encoding="utf-8",
            )
            self._admit_judged_evidence(paths)
            rebind_persisted_grading_to_current_evidence(paths)

            benchmark = aggregate_results(root, "judge")

            self.assertEqual(benchmark["grade_source"], "judge")

    def test_behavior_aggregation_revalidates_exact_judge_evidence_bytes(self):
        cases = (
            ("NUL", b"unsafe\x00evidence"),
            ("UTF-8", b"\xff\xfe"),
        )
        for expected, content in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "results"
                _, paths, _ = self._complete_workspace(root)
                captured = paths.root / "outputs" / "captured.bin"
                captured.write_bytes(content)
                rebind_persisted_grading_to_current_evidence(paths)

                with self.assertRaisesRegex(ResultArtifactError, expected):
                    aggregate_results(root, "judge")

    def test_behavior_aggregation_does_not_admit_timing_as_judge_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            _, paths, _ = self._complete_workspace(root)
            basis_path = paths.grading_basis
            grading_path = paths.grading
            basis = json.loads(basis_path.read_text(encoding="utf-8"))
            grading = json.loads(grading_path.read_text(encoding="utf-8"))
            basis["allowed_evidence_artifacts"].append("timing.json")
            judge_response = json.loads(basis["judge_response"])
            judge_response["assertion_results"][0]["evidence_refs"][0][
                "artifact"
            ] = "timing.json"
            basis["judge_response"] = json.dumps(judge_response, sort_keys=True)
            grading["assertion_results"][0]["evidence_refs"][0][
                "artifact"
            ] = "timing.json"
            basis_path.write_text(json.dumps(basis), encoding="utf-8")
            grading_path.write_text(json.dumps(grading), encoding="utf-8")
            rebind_persisted_grading_to_current_evidence(paths)

            with self.assertRaisesRegex(
                ResultArtifactError,
                "evidence set does not match",
            ):
                aggregate_results(root, "judge")

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
            self._admit_judged_evidence(
                paths,
                "outputs/reports/result.txt",
            )
            rebind_persisted_grading_to_current_evidence(paths)

            benchmark = aggregate_results(root, "judge")

            self.assertEqual(benchmark_exit_code(benchmark), 0)

    def test_aggregation_rejects_timing_as_judge_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            _, paths, _ = self._complete_workspace(root)
            self._set_evidence_artifact(paths.grading, "timing.json")
            rebind_persisted_grading_to_current_evidence(paths)

            with self.assertRaisesRegex(
                ResultArtifactError,
                "evidence artifact is not allowed",
            ):
                aggregate_results(root, "judge")

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
            rebind_persisted_grading_to_current_evidence(paths)

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
            self._admit_judged_evidence(
                paths,
                *sorted(
                    path.relative_to(paths.root).as_posix()
                    for path in paths.root.joinpath("outputs").rglob("*")
                    if path.is_file() and path != paths.response
                ),
            )
            rebind_persisted_grading_to_current_evidence(paths)

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
                return replace(
                    self.execution,
                    execution_binding=request.execution_binding,
                )

        request = HarnessRequest(
            role="judge",
            run_variant="semantic_grade",
            prompt="Grade the evidence.",
            timeout_seconds=30,
            model="actual-judge-model",
            reasoning_effort="medium",
        )
        valid_execution = replace(
            completed_harness_execution(),
            response=json.dumps(sample_judge_response()),
            model="actual-judge-model",
            trace=({"event": "judge.completed"},),
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
        self.assertEqual(
            raised.exception.execution,
            replace(
                failed_adapter.execution,
                execution_binding=raised.exception.execution.execution_binding,
            ),
        )
        self.assertIsNotNone(raised.exception.execution.execution_binding)
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
                self.assertEqual(
                    raised.exception.execution,
                    replace(
                        incomplete,
                        execution_binding=(
                            raised.exception.execution.execution_binding
                        ),
                    ),
                )

        malformed = replace(valid_execution, response="not json")
        with self.assertRaises(JudgeExecutionError) as raised:
            invoke_judge(
                JudgeHarness(malformed),
                request,
                Path("artifacts"),
                expected_judge_context(),
            )
        self.assertEqual(raised.exception.execution.response, "not json")

    def test_judge_invocation_requires_one_exact_successful_lifecycle(self):
        class JudgeHarness:
            def __init__(self, trace):
                self.trace = trace

            def execute(self, request, artifact_dir):
                return replace(
                    completed_harness_execution(),
                    response=json.dumps(sample_judge_response()),
                    model="actual-judge-model",
                    trace=self.trace,
                    execution_binding=request.execution_binding,
                )

        request = HarnessRequest(
            role="judge",
            run_variant="semantic_grade",
            prompt="Grade the evidence.",
            timeout_seconds=30,
            model="actual-judge-model",
            reasoning_effort="medium",
        )
        exact_codex_lifecycle = (
            {"event": "harness_thread_started"},
            {"event": "harness_turn_started"},
            {"event": "harness_turn_completed"},
        )
        invocation = invoke_judge(
            JudgeHarness(exact_codex_lifecycle),
            request,
            Path("artifacts"),
            expected_judge_context(),
        )
        self.assertEqual(invocation.execution.trace, exact_codex_lifecycle)

        invalid_traces = (
            (),
            (
                *exact_codex_lifecycle,
                {"event": "harness_failure"},
            ),
        )
        for trace in invalid_traces:
            with self.subTest(trace=trace):
                with self.assertRaises(JudgeExecutionError):
                    invoke_judge(
                        JudgeHarness(trace),
                        request,
                        Path("artifacts"),
                        expected_judge_context(),
                    )

    def test_judge_rejects_execution_replayed_from_another_invocation(self):
        stale_invocation_id = "f" * 32

        class ReplayHarness:
            def execute(self, request, artifact_dir):
                stale_request = bind_harness_request(
                    replace(request, execution_binding=None),
                    invocation_id=stale_invocation_id,
                    run_id=expected_judge_context().run_id,
                )
                return replace(
                    completed_harness_execution(),
                    response=json.dumps(sample_judge_response()),
                    model="actual-judge-model",
                    trace=(
                        {"event": "harness_thread_started"},
                        {"event": "harness_turn_started"},
                        {"event": "harness_turn_completed"},
                    ),
                    execution_binding=stale_request.execution_binding,
                )

        request = HarnessRequest(
            role="judge",
            run_variant="semantic_grade",
            prompt="Grade the evidence.",
            timeout_seconds=30,
            model="actual-judge-model",
            reasoning_effort="medium",
        )

        with self.assertRaisesRegex(JudgeExecutionError, "execution binding"):
            invoke_judge(
                ReplayHarness(),
                request,
                Path("artifacts"),
                expected_judge_context(),
            )

    def test_judge_adapter_exception_is_bounded_and_quarantines_secrets(self):
        secret = "sk-" + ("a" * 48)

        class RaisingJudgeHarness:
            def execute(self, request, artifact_dir):
                raise RuntimeError(
                    f"Authorization: Bearer {secret} " + ("detail " * 10_000)
                )

        request = HarnessRequest(
            role="judge",
            run_variant="semantic_grade",
            prompt="Grade the evidence.",
            timeout_seconds=30,
            model="actual-judge-model",
            reasoning_effort="medium",
        )

        with self.assertRaises(JudgeExecutionError) as raised:
            invoke_judge(
                RaisingJudgeHarness(),
                request,
                Path("artifacts"),
                expected_judge_context(),
            )

        message = str(raised.exception)
        execution = raised.exception.execution
        self.assertNotIn(secret, message)
        self.assertNotIn(secret, execution.failure or "")
        self.assertLessEqual(len(message.encode("utf-8")), 8192)
        self.assertEqual(execution.trace[0]["event"], "judge_adapter_error")

    def test_judge_isolation_rejects_skill_tool_and_actor_output_access(self):
        class JudgeHarness:
            def __init__(self, execution: HarnessExecution):
                self.execution = execution

            def execute(self, request, artifact_dir):
                return replace(
                    self.execution,
                    execution_binding=request.execution_binding,
                )

        request = HarnessRequest(
            role="judge",
            run_variant="semantic_grade",
            prompt="Grade the evidence.",
            timeout_seconds=30,
            model="actual-judge-model",
            reasoning_effort="medium",
        )
        valid = replace(
            completed_harness_execution(),
            response=json.dumps(sample_judge_response()),
            model="actual-judge-model",
        )
        violations = (
            replace(valid, successful_skill_reads=(Path("/tmp/SKILL.md"),)),
            replace(valid, expected_skill_path=Path("/tmp/SKILL.md")),
            replace(
                valid,
                captured_output_paths=(
                    CapturedOutputPath(
                        path=PurePosixPath("report.json"),
                        kind="file",
                    ),
                ),
            ),
            replace(valid, trace=({"event": "command_completed"},)),
            replace(valid, trace=({"event": "tool_completed"},)),
        )
        for execution in violations:
            with self.subTest(execution=execution):
                with self.assertRaisesRegex(
                    JudgeExecutionError,
                    "judge isolation was violated",
                ):
                    invoke_judge(
                        JudgeHarness(execution),
                        request,
                        Path("artifacts"),
                        expected_judge_context(),
                    )


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
