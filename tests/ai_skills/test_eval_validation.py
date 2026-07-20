from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import hashlib
from io import StringIO
import json
from pathlib import Path, PurePosixPath
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import scripts.ai_skills as cli
from scripts.ai_skills_lib.authored_content import (
    BoundedJsonError,
    SENSITIVE_TEXT_QUARANTINE,
    strict_bounded_json_loads,
)
import scripts.ai_skills_lib.eval_validation as eval_validation
import scripts.ai_skills_lib.eval_checks as eval_checks
from scripts.ai_skills_lib.config import build_parser
from scripts.ai_skills_lib.eval_checks import evaluate_deterministic_checks
from scripts.ai_skills_lib.eval_core import (
    ResultArtifactError,
    aggregate_results,
    create_result_workspace,
)
from scripts.ai_skills_lib.eval_definitions import (
    BehaviorCheck,
    BehaviorDefinitionError,
    load_behavior_evals,
    validate_behavior_eval_files,
)
from scripts.ai_skills_lib.eval_validation import execute_behavior_evals
from scripts.ai_skills_lib.harness import (
    CapturedOutputPath,
    HarnessCapabilities,
    HarnessExecution,
    HarnessRequest,
)


class RecordingBehaviorHarness:
    def __init__(
        self,
        *,
        failed_variants: tuple[str, ...] = (),
        actor_failure_variant: str | None = None,
        actor_response: str = "A complete result.",
        actor_trace_factory: Callable[
            [], tuple[Mapping[str, object], ...]
        ] | None = None,
        captured_report_text: str = '{"status": "ok"}\n',
        judge_response: str | None = None,
        judge_timed_out: bool = False,
    ) -> None:
        self.failed_variants = failed_variants
        self.actor_failure_variant = actor_failure_variant
        self.actor_response = actor_response
        self.actor_trace_factory = actor_trace_factory
        self.captured_report_text = captured_report_text
        self.judge_response = judge_response
        self.judge_timed_out = judge_timed_out
        self.preflight_calls: list[bool] = []
        self.requests: list[tuple[HarnessRequest, Path]] = []
        self.expected_invocation_manifest: Path | None = None

    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        if (
            self.expected_invocation_manifest is not None
            and not self.expected_invocation_manifest.is_file()
        ):
            raise AssertionError("behavior invocation must be declared before preflight")
        self.preflight_calls.append(require_fixtures)
        return HarnessCapabilities(
            harness_name="recording",
            available=True,
            actor_model="actor-model",
            actor_reasoning_effort="high",
            judge_model="judge-model",
            judge_reasoning_effort="high",
            reports_token_usage=True,
            reports_successful_skill_reads=True,
        )

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        self.requests.append((request, artifact_dir))
        if request.role == "actor":
            outputs = artifact_dir / "outputs"
            outputs.mkdir(exist_ok=True)
            (outputs / "report.json").write_text(
                self.captured_report_text, encoding="utf-8"
            )
            failed = request.run_variant == self.actor_failure_variant
            return HarnessExecution(
                response=self.actor_response,
                trace=(
                    self.actor_trace_factory()
                    if self.actor_trace_factory is not None
                    else ({"event": "actor.completed"},)
                ),
                duration_ms=20,
                total_tokens=12,
                input_tokens=8,
                output_tokens=4,
                cached_tokens=0,
                token_source="test",
                successful_skill_reads=(),
                exit_code=2 if failed else 0,
                failure="actor failed" if failed else None,
                model="actor-model",
                reasoning_effort="high",
                timed_out=False,
            )
        passed = not any(
            variant in request.run_variant for variant in self.failed_variants
        )
        response = {
            "assertion_results": [
                {
                    "id": "assertion-1",
                    "passed": passed,
                    "evidence": "The preserved response provides concrete evidence.",
                    "evidence_refs": [
                        {
                            "artifact": "outputs/response.md",
                            "locator": "complete response",
                        }
                    ],
                }
            ]
        }
        return HarnessExecution(
            response=self.judge_response or json.dumps(response),
            trace=({"event": "judge.completed"},),
            duration_ms=10,
            total_tokens=6,
            input_tokens=4,
            output_tokens=2,
            cached_tokens=0,
            token_source="test",
            successful_skill_reads=(),
            exit_code=None if self.judge_timed_out else 0,
            failure=None,
            model="judge-model",
            reasoning_effort="high",
            timed_out=self.judge_timed_out,
        )


class MutatingPreflightBehaviorHarness(RecordingBehaviorHarness):
    def __init__(self, mutation) -> None:
        super().__init__()
        self.mutation = mutation

    def preflight(self, *, require_fixtures: bool = False) -> HarnessCapabilities:
        self.mutation()
        return super().preflight(require_fixtures=require_fixtures)


class TemporaryBehaviorRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "skills").mkdir(parents=True)

    def add_skill(
        self,
        name: str,
        *,
        group: str = "workflows",
        document: object | None = None,
    ) -> Path:
        skill_root = self.root / "skills" / group / name
        evals_root = skill_root / "evals"
        evals_root.mkdir(parents=True)
        (skill_root / "SKILL.md").write_text(
            (
                "---\n"
                f"name: {name}\n"
                f"description: Use for {name}.\n"
                "metadata:\n"
                '  status: \"public-ready\"\n'
                '  tier: \"standard\"\n'
                '  config_mode: \"none\"\n'
                '  allows_tool_references: \"false\"\n'
                "---\n"
                "Follow the workflow.\n"
            ),
            encoding="utf-8",
        )
        if document is None:
            document = {
                "skill_name": name,
                "evals": [
                    {
                        "id": f"{name}-core",
                        "prompt": f"Perform the {name} task.",
                        "expected_output": "A complete user-facing result.",
                        "assertions": ["The result completes the requested task."],
                        "checks": [],
                    }
                ],
            }
        (evals_root / "evals.json").write_text(
            json.dumps(document),
            encoding="utf-8",
        )
        return skill_root


class BehaviorDefinitionValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository = TemporaryBehaviorRepository(Path(self.temporary_directory.name))

    def assert_issue(self, expected: str) -> None:
        issues = validate_behavior_eval_files(self.repository.root)
        self.assertTrue(
            any(expected in issue.message for issue in issues),
            f"missing issue containing {expected!r}: {issues!r}",
        )

    def test_one_generic_validator_discovers_and_loads_valid_behavior_cases(self) -> None:
        alpha = self.repository.add_skill("alpha")
        self.repository.add_skill("beta", group="integrations")

        self.assertEqual(validate_behavior_eval_files(self.repository.root), [])
        definitions = load_behavior_evals(self.repository.root)

        self.assertEqual([definition.skill.name for definition in definitions], ["beta", "alpha"])
        self.assertEqual(definitions[1].skill.root, alpha)
        self.assertEqual(definitions[1].cases[0].id, "alpha-core")
        self.assertEqual(definitions[1].cases[0].assertions[0].id, "assertion-1")

    def test_identity_unique_ids_and_nonempty_assertions_are_required(self) -> None:
        self.repository.add_skill(
            "alpha",
            document={
                "skill_name": "wrong",
                "evals": [
                    {
                        "id": "duplicate",
                        "prompt": "One.",
                        "expected_output": "One.",
                        "assertions": [],
                        "checks": [],
                    },
                    {
                        "id": "duplicate",
                        "prompt": "Two.",
                        "expected_output": "Two.",
                        "assertions": ["A result exists."],
                        "checks": [],
                    },
                ],
            },
        )

        self.assert_issue("skill_name 'wrong' must match")
        self.assert_issue("duplicate eval id 'duplicate'")
        self.assert_issue("schema error")

    def test_check_schema_rejects_prose_matching_unknown_fields_and_unsafe_paths(self) -> None:
        for index, check in enumerate((
            {"type": "contains", "text": "exact words"},
            {"type": "file_exists", "path": "../escape.txt"},
            {"type": "path_absent", "path": "/tmp/absolute"},
            {"type": "exit_code", "expected": 0, "extra": True},
            {"type": "exit_code", "expected": 2},
            {"type": "response_protocol", "format": "yaml"},
        )):
            with self.subTest(check=check):
                repository = TemporaryBehaviorRepository(
                    Path(self.temporary_directory.name)
                    / f"{check['type'].replace('_', '-')}-{index}"
                )
                repository.add_skill(
                    "alpha",
                    document={
                        "skill_name": "alpha",
                        "evals": [
                            {
                                "id": "alpha-core",
                                "prompt": "Perform alpha.",
                                "expected_output": "A result.",
                                "assertions": ["The result is complete."],
                                "checks": [check],
                            }
                        ],
                    },
                )
                self.assertTrue(validate_behavior_eval_files(repository.root))

    def test_actor_files_must_exist_below_the_exact_case_inputs_directory(self) -> None:
        skill = self.repository.add_skill(
            "alpha",
            document={
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Use the provided context.",
                        "expected_output": "A result based on the context.",
                        "assertions": ["The result uses the provided context."],
                        "files": ["fixtures/other/inputs/context.txt"],
                        "checks": [],
                    }
                ],
            },
        )
        other = skill / "evals" / "fixtures" / "other" / "inputs"
        other.mkdir(parents=True)
        (other / "context.txt").write_text("context", encoding="utf-8")

        self.assert_issue("must stay below fixtures/alpha-core/inputs")

        document = json.loads((skill / "evals" / "evals.json").read_text())
        document["evals"][0]["files"] = ["fixtures/alpha-core/inputs/missing.txt"]
        (skill / "evals" / "evals.json").write_text(json.dumps(document), encoding="utf-8")
        self.assert_issue("actor input does not exist")

        inputs = skill / "evals" / "fixtures" / "alpha-core" / "inputs"
        inputs.mkdir(parents=True)
        (inputs / "context.txt").write_text("context", encoding="utf-8")
        document["evals"][0]["files"] = ["fixtures/alpha-core/inputs/context.txt"]
        (skill / "evals" / "evals.json").write_text(json.dumps(document), encoding="utf-8")
        self.assert_issue("must name staged actor input 'context.txt'")

        document["evals"][0]["prompt"] = "Use context.txt as the provided context."
        (skill / "evals" / "evals.json").write_text(json.dumps(document), encoding="utf-8")
        self.assertEqual(validate_behavior_eval_files(self.repository.root), [])

    def test_paths_must_be_canonical_and_actor_input_aliases_are_rejected(self) -> None:
        skill = self.repository.add_skill(
            "alpha",
            document={
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Use nested/context.txt and write report.json.",
                        "expected_output": "A report based on the context.",
                        "assertions": ["The report uses the supplied context."],
                        "files": [
                            "fixtures/alpha-core/inputs/nested/context.txt",
                            "fixtures/alpha-core/inputs/nested//context.txt",
                        ],
                        "checks": [
                            {"type": "file_exists", "path": "./report.json"},
                        ],
                    }
                ],
            },
        )
        context = skill / "evals" / "fixtures" / "alpha-core" / "inputs" / "nested" / "context.txt"
        context.parent.mkdir(parents=True)
        context.write_text("context", encoding="utf-8")

        self.assert_issue("must be a canonical relative path")
        self.assert_issue("aliases another actor input")

        document = json.loads((skill / "evals" / "evals.json").read_text())
        document["evals"][0]["files"] = ["fixtures/alpha-core/inputs/\u0000"]
        document["evals"][0]["checks"] = []
        (skill / "evals" / "evals.json").write_text(json.dumps(document), encoding="utf-8")
        self.assert_issue("must be a canonical relative path")

    def test_runner_schemas_allow_only_same_document_fragment_references(self) -> None:
        skill = self.repository.add_skill(
            "alpha",
            document={
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Write report.json.",
                        "expected_output": "A schema-valid report.",
                        "assertions": ["The report is complete."],
                        "checks": [
                            {
                                "type": "json_schema",
                                "path": "report.json",
                                "schema": "fixtures/alpha-core/report.schema.json",
                            }
                        ],
                    }
                ],
            },
        )
        schema = skill / "evals" / "fixtures" / "alpha-core" / "report.schema.json"
        schema.parent.mkdir(parents=True)
        schema.write_text(
            json.dumps(
                {
                    "$defs": {"report": {"type": "object"}},
                    "$ref": "#/$defs/report",
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(validate_behavior_eval_files(self.repository.root), [])

        for keyword, target, expected in (
            (
                "$ref",
                "https://schemas.example.test/report.json",
                "external JSON Schema reference",
            ),
            (
                "$dynamicRef",
                "file:///private/report.json",
                "not allowed by the safe subset",
            ),
        ):
            with self.subTest(keyword=keyword):
                schema.write_text(json.dumps({keyword: target}), encoding="utf-8")
                self.assert_issue(expected)

    def test_definition_size_limits_are_enforced_before_execution(self) -> None:
        oversized_documents = (
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": f"case-{index}",
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                    }
                    for index in range(129)
                ],
            },
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "x" * 16385,
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                    }
                ],
            },
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": [f"Assertion {index}." for index in range(65)],
                    }
                ],
            },
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Run.",
                        "expected_output": "x" * 8193,
                        "assertions": ["The result is complete."],
                    }
                ],
            },
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": ["x" * 4097],
                    }
                ],
            },
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                        "files": [
                            f"fixtures/alpha-core/inputs/input-{index}.txt"
                            for index in range(65)
                        ],
                    }
                ],
            },
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                        "checks": [
                            {"type": "exit_code", "expected": 0}
                            for _ in range(65)
                        ],
                    }
                ],
            },
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "a" * 65,
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                    }
                ],
            },
            {
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Run.",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                        "checks": [
                            {"type": "file_exists", "path": "x" * 513}
                        ],
                    }
                ],
            },
        )
        for index, document in enumerate(oversized_documents):
            with self.subTest(index=index):
                repository = TemporaryBehaviorRepository(
                    Path(self.temporary_directory.name) / f"bounds-{index}"
                )
                repository.add_skill("alpha", document=document)
                issues = validate_behavior_eval_files(repository.root)
                self.assertTrue(
                    any("schema error" in issue.message for issue in issues),
                    issues,
                )

    def test_definition_and_oracle_utf8_byte_limits_are_enforced(self) -> None:
        oversized_file = self.repository.add_skill("oversized-file")
        definition_path = oversized_file / "evals" / "evals.json"
        definition_path.write_text(
            definition_path.read_text(encoding="utf-8")
            + (" " * (2 * 1024 * 1024)),
            encoding="utf-8",
        )
        oracle_document = {
            "skill_name": "oversized-oracle",
            "evals": [
                {
                    "id": "core",
                    "prompt": "Run.",
                    "expected_output": "A result.",
                    "assertions": [("\U0001f600" * 4096) for _ in range(64)],
                }
            ],
        }
        oversized_oracle = self.repository.add_skill(
            "oversized-oracle",
            document=oracle_document,
        )
        (oversized_oracle / "evals" / "evals.json").write_text(
            json.dumps(oracle_document, ensure_ascii=False),
            encoding="utf-8",
        )

        issues = validate_behavior_eval_files(self.repository.root)

        self.assertTrue(any("2 MiB definition limit" in issue.message for issue in issues))
        self.assertTrue(any("320 KiB UTF-8 limit" in issue.message for issue in issues))
        self.assertTrue(oversized_oracle.is_dir())

    def test_rejects_real_private_state_requests_but_allows_fixture_scenarios(self) -> None:
        skill = self.repository.add_skill(
            "alpha",
            document={
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Use my saved production token to query the live account.",
                        "expected_output": "A result.",
                        "assertions": ["The result is complete."],
                    }
                ],
            },
        )

        self.assert_issue("requires real private credentials or session state")

        document = json.loads((skill / "evals" / "evals.json").read_text())
        document["evals"][0]["prompt"] = (
            "Use my real inbox fixture with FAKE_SERVICE_TOKEN. Never open my real inbox."
        )
        (skill / "evals" / "evals.json").write_text(json.dumps(document), encoding="utf-8")
        self.assertEqual(validate_behavior_eval_files(self.repository.root), [])

    def test_installable_skill_content_must_not_reference_eval_oracles(self) -> None:
        installable_locations = ("SKILL.md", "scripts/run.sh", "references/guide.md", "assets/template.txt")
        for index, relative in enumerate(installable_locations):
            with self.subTest(relative=relative):
                repository = TemporaryBehaviorRepository(
                    Path(self.temporary_directory.name) / f"oracle-{index}"
                )
                skill = repository.add_skill("alpha")
                target = skill / relative
                if relative == "SKILL.md":
                    target.write_text(
                        target.read_text(encoding="utf-8")
                        + "Read evals/fixtures/alpha-core/oracle.json.\n",
                        encoding="utf-8",
                    )
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("Read ../evals/evals.json.\n", encoding="utf-8")
                issues = validate_behavior_eval_files(repository.root)
                self.assertTrue(
                    any("installable content must not reference evals/" in issue.message for issue in issues),
                    issues,
                )

    def test_schema_fixtures_must_be_runner_only_and_case_contained(self) -> None:
        skill = self.repository.add_skill(
            "alpha",
            document={
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Produce report.json.",
                        "expected_output": "A schema-valid report.",
                        "assertions": ["The report is useful."],
                        "checks": [
                            {
                                "type": "json_schema",
                                "path": "report.json",
                                "schema": "fixtures/alpha-core/inputs/report.schema.json",
                            }
                        ],
                    }
                ],
            },
        )
        inputs = skill / "evals" / "fixtures" / "alpha-core" / "inputs"
        inputs.mkdir(parents=True)
        (inputs / "report.schema.json").write_text("{}", encoding="utf-8")

        self.assert_issue("runner-only schema must not be below inputs")

    def test_runner_only_schema_must_be_a_valid_json_schema_object(self) -> None:
        skill = self.repository.add_skill(
            "alpha",
            document={
                "skill_name": "alpha",
                "evals": [
                    {
                        "id": "alpha-core",
                        "prompt": "Produce report.json.",
                        "expected_output": "A schema-valid report.",
                        "assertions": ["The report is useful."],
                        "checks": [
                            {
                                "type": "json_schema",
                                "path": "report.json",
                                "schema": "fixtures/alpha-core/report.schema.json",
                            }
                        ],
                    }
                ],
            },
        )
        schema = skill / "evals" / "fixtures" / "alpha-core" / "report.schema.json"
        schema.parent.mkdir(parents=True)
        schema.write_text('{"type": "not-a-json-schema-type"}', encoding="utf-8")

        self.assert_issue("runner-only schema is not a valid JSON Schema object")

    def test_bundled_runtime_material_requires_one_case_with_a_real_relative_path(self) -> None:
        skill = self.repository.add_skill("alpha")
        references = skill / "references"
        references.mkdir()
        (references / "guide.md").write_text("Follow this.", encoding="utf-8")

        self.assert_issue("must exercise bundled runtime material")

        document = json.loads((skill / "evals" / "evals.json").read_text())
        document["evals"][0]["assertions"].append(
            "The result follows the rules in references/guide.md."
        )
        (skill / "evals" / "evals.json").write_text(json.dumps(document), encoding="utf-8")

        self.assertEqual(validate_behavior_eval_files(self.repository.root), [])

    def test_missing_invalid_or_symlinked_files_fail_as_definition_errors(self) -> None:
        skill = self.repository.add_skill("alpha")
        evals_path = skill / "evals" / "evals.json"
        evals_path.unlink()
        self.assert_issue("missing evals/evals.json")

        evals_path.write_text("{", encoding="utf-8")
        self.assert_issue("contains invalid JSON")

        evals_path.unlink()
        target = skill / "evals" / "elsewhere.json"
        target.write_text("{}", encoding="utf-8")
        evals_path.symlink_to(target)
        self.assert_issue("non-symlink regular file")

        with self.assertRaises(BehaviorDefinitionError):
            load_behavior_evals(self.repository.root)


class DeterministicBehaviorCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.skill_root = self.root / "skills" / "workflows" / "alpha"
        self.fixture_root = self.skill_root / "evals" / "fixtures" / "alpha-core"
        self.outputs = self.root / "results" / "outputs"
        self.fixture_root.mkdir(parents=True)
        self.outputs.mkdir(parents=True)
        self.execution = HarnessExecution(
            response='{"status": "ok"}',
            trace=(),
            duration_ms=10,
            total_tokens=4,
            input_tokens=2,
            output_tokens=2,
            cached_tokens=0,
            token_source="test",
            successful_skill_reads=(),
            exit_code=0,
            failure=None,
            model="test-model",
            reasoning_effort="high",
            timed_out=False,
        )

    def test_artifact_exit_and_response_checks_return_reviewable_results(self) -> None:
        (self.outputs / "report.json").write_text(
            '{"status": "ok"}\n', encoding="utf-8"
        )
        schema = self.fixture_root / "report.schema.json"
        schema.write_text(
            json.dumps(
                {
                    "type": "object",
                    "required": ["status"],
                    "properties": {"status": {"const": "ok"}},
                }
            ),
            encoding="utf-8",
        )
        checks = (
            BehaviorCheck(type="file_exists", path=PurePosixPath("report.json")),
            BehaviorCheck(type="path_absent", path=PurePosixPath("secret.txt")),
            BehaviorCheck(
                type="json_schema",
                path=PurePosixPath("report.json"),
                schema=PurePosixPath("fixtures/alpha-core/report.schema.json"),
            ),
            BehaviorCheck(type="exit_code", expected=0),
            BehaviorCheck(type="no_secret_patterns"),
            BehaviorCheck(
                type="response_protocol",
                format="json",
                schema=PurePosixPath("fixtures/alpha-core/report.schema.json"),
            ),
        )

        results = evaluate_deterministic_checks(
            checks,
            outputs_root=self.outputs,
            response=self.execution.response,
            execution=self.execution,
            skill_root=self.skill_root,
        )

        self.assertEqual([result.id for result in results], [f"check-{n}" for n in range(1, 7)])
        self.assertTrue(all(result.passed for result in results))
        self.assertTrue(all(result.checked_by == "deterministic" for result in results))
        self.assertTrue(all(result.evidence_refs for result in results))

    def test_failed_checks_redact_secrets_and_do_not_raise(self) -> None:
        credential = "gh" + "p_" + ("a" * 36)
        (self.outputs / "leak.txt").write_text(credential, encoding="utf-8")
        checks = (
            BehaviorCheck(type="file_exists", path=PurePosixPath("missing.txt")),
            BehaviorCheck(type="path_absent", path=PurePosixPath("leak.txt")),
            BehaviorCheck(type="no_secret_patterns"),
            BehaviorCheck(type="response_protocol", format="jsonl"),
        )

        results = evaluate_deterministic_checks(
            checks,
            outputs_root=self.outputs,
            response="not-jsonl",
            execution=self.execution,
            skill_root=self.skill_root,
        )

        self.assertFalse(any(result.passed for result in results))
        self.assertNotIn(credential, json.dumps([result.to_dict() for result in results]))

    def test_secret_check_classifies_generic_auth_and_preserves_safe_fake_values(self) -> None:
        sensitive_responses = (
            "Authorization: Bearer opaque-authorization-value",
            "Cookie: session=opaque-cookie-value",
            '{"Authorization":"Bearer opaque-json-value"}',
            '{"Cookie":"session=opaque-json-cookie"}',
        )
        for response in sensitive_responses:
            with self.subTest(response=response.split(":", 1)[0]):
                result = evaluate_deterministic_checks(
                    (BehaviorCheck(type="no_secret_patterns"),),
                    outputs_root=self.outputs,
                    response=response,
                    execution=self.execution,
                    skill_root=self.skill_root,
                )[0]
                self.assertFalse(result.passed)
                self.assertIn("high-confidence secret occurrence(s)", result.evidence)

        safe_response = (
            '{"Authorization":"Bearer FAKE_authorization_value",'
            '"Cookie":"session=FAKE_cookie_value"}'
        )
        result = evaluate_deterministic_checks(
            (BehaviorCheck(type="no_secret_patterns"),),
            outputs_root=self.outputs,
            response=safe_response,
            execution=self.execution,
            skill_root=self.skill_root,
        )[0]
        self.assertTrue(result.passed)

    def test_output_symlinks_are_an_infrastructure_error(self) -> None:
        (self.outputs / "escape").symlink_to(self.root)

        with self.assertRaisesRegex(RuntimeError, "symlink"):
            evaluate_deterministic_checks(
                (BehaviorCheck(type="file_exists", path=PurePosixPath("escape")),),
                outputs_root=self.outputs,
                response=self.execution.response,
                execution=self.execution,
                skill_root=self.skill_root,
            )

    def test_path_absent_uses_descriptor_observed_empty_directories(self) -> None:
        execution = replace(
            self.execution,
            captured_output_paths=(
                CapturedOutputPath(
                    PurePosixPath("secret-directory"),
                    "directory",
                ),
            ),
        )

        result = evaluate_deterministic_checks(
            (
                BehaviorCheck(
                    type="path_absent",
                    path=PurePosixPath("secret-directory"),
                ),
            ),
            outputs_root=self.outputs,
            response=self.execution.response,
            execution=execution,
            skill_root=self.skill_root,
        )[0]

        self.assertFalse(result.passed)
        self.assertFalse((self.outputs / "secret-directory").exists())

    def test_strict_json_loader_rejects_nonfinite_and_resource_hostile_values(self) -> None:
        hostile_values = (
            "NaN",
            "Infinity",
            "1e99999",
            "[" * 200 + "0" + "]" * 200,
            "9" * 5000,
        )

        for value in hostile_values:
            with self.subTest(prefix=value[:12]):
                with self.assertRaises(BoundedJsonError) as raised:
                    strict_bounded_json_loads(value, maximum_bytes=16 * 1024)
                self.assertLess(len(str(raised.exception)), 128)

        with self.assertRaisesRegex(BoundedJsonError, "node limit"):
            strict_bounded_json_loads("[0,0,0]", maximum_nodes=3)
        for parser_error in (
            RecursionError("nested parser input"),
            ValueError("integer conversion limit"),
            MemoryError(),
        ):
            with self.subTest(parser_error=type(parser_error).__name__), patch(
                "scripts.ai_skills_lib.authored_content.json.loads",
                side_effect=parser_error,
            ):
                with self.assertRaises(BoundedJsonError) as raised:
                    strict_bounded_json_loads("{}")
                self.assertLess(len(str(raised.exception)), 128)

        hostile_structures = (
            ("[[0]]", {"maximum_depth": 2}, "depth limit"),
            ("[0,0,0]", {"maximum_nodes": 3}, "node limit"),
        )
        for value, limits, expected_error in hostile_structures:
            with self.subTest(expected_error=expected_error), patch(
                "scripts.ai_skills_lib.authored_content.json.loads",
                side_effect=AssertionError(
                    "structurally hostile JSON reached json.loads"
                ),
            ):
                with self.assertRaisesRegex(BoundedJsonError, expected_error):
                    strict_bounded_json_loads(value, **limits)

    def test_response_protocol_rejects_nonfinite_json_as_a_failed_check(self) -> None:
        result = evaluate_deterministic_checks(
            (BehaviorCheck(type="response_protocol", format="json"),),
            outputs_root=self.outputs,
            response='{"score": NaN}',
            execution=self.execution,
            skill_root=self.skill_root,
        )[0]

        self.assertFalse(result.passed)
        self.assertIn("not valid json", result.evidence.lower())

    def test_runtime_schema_resolution_is_closed_to_external_resources(self) -> None:
        (self.outputs / "report.json").write_text("{}", encoding="utf-8")
        schema = self.fixture_root / "report.schema.json"
        schema.write_text('{"$ref":"file:///etc/passwd"}', encoding="utf-8")

        with self.assertRaisesRegex(ResultArtifactError, "unresolved reference"):
            evaluate_deterministic_checks(
                (
                    BehaviorCheck(
                        type="json_schema",
                        path=PurePosixPath("report.json"),
                        schema=PurePosixPath(
                            "fixtures/alpha-core/report.schema.json"
                        ),
                    ),
                ),
                outputs_root=self.outputs,
                response=self.execution.response,
                execution=self.execution,
                skill_root=self.skill_root,
            )

    def test_runtime_schema_resource_failures_become_result_artifact_errors(self) -> None:
        (self.outputs / "report.json").write_text("{}", encoding="utf-8")
        schema = self.fixture_root / "report.schema.json"
        schema.write_text('{"type":"object"}', encoding="utf-8")
        check = BehaviorCheck(
            type="json_schema",
            path=PurePosixPath("report.json"),
            schema=PurePosixPath("fixtures/alpha-core/report.schema.json"),
        )
        failures = (
            (
                "build_safe_json_schema_validator",
                MemoryError(),
                "declared eval schema is invalid",
            ),
            (
                "bounded_json_schema_errors",
                SystemError("validator exhausted"),
                "validation violated the safe JSON Schema policy",
            ),
        )
        for target, resource_error, expected in failures:
            with self.subTest(resource_error=type(resource_error).__name__), patch.object(
                eval_checks,
                target,
                side_effect=resource_error,
            ):
                with self.assertRaises(ResultArtifactError) as raised:
                    evaluate_deterministic_checks(
                        (check,),
                        outputs_root=self.outputs,
                        response=self.execution.response,
                        execution=self.execution,
                        skill_root=self.skill_root,
                    )

                self.assertIn(expected, str(raised.exception))
                self.assertLess(len(str(raised.exception)), 160)


class BehaviorRunnerTests(unittest.TestCase):
    def _assert_durable_tree_excludes(
        self,
        root: Path,
        forbidden_values: tuple[str, ...],
    ) -> None:
        for path in root.rglob("*"):
            rendered_path = path.relative_to(root).as_posix()
            self.assertTrue(
                all(value not in rendered_path for value in forbidden_values),
                "durable path retained forbidden sensitive text",
            )
            if path.is_file():
                content = path.read_bytes()
                self.assertTrue(
                    all(
                        value.encode("utf-8") not in content
                        for value in forbidden_values
                    ),
                    "durable file retained forbidden sensitive text",
                )

    def _repository(self, base: Path, *, with_fixture: bool = False) -> TemporaryBehaviorRepository:
        repository = TemporaryBehaviorRepository(base / "repository")
        alpha_document = {
            "skill_name": "alpha",
            "evals": [
                {
                    "id": "alpha-core",
                    "prompt": "Perform alpha.",
                    "expected_output": "A complete alpha result.",
                    "assertions": ["The response completes alpha."],
                    "checks": [
                        {"type": "file_exists", "path": "report.json"}
                    ],
                }
            ],
        }
        if with_fixture:
            alpha_document["evals"][0]["prompt"] = (
                "Use context.txt to perform alpha."
            )
            alpha_document["evals"][0]["files"] = [
                "fixtures/alpha-core/inputs/context.txt"
            ]
        alpha = repository.add_skill("alpha", document=alpha_document)
        repository.add_skill("beta", group="integrations")
        if with_fixture:
            fixture_root = alpha / "evals" / "fixtures" / "alpha-core"
            inputs = fixture_root / "inputs"
            inputs.mkdir(parents=True)
            (inputs / "context.txt").write_text("fixture context\n", encoding="utf-8")
            (fixture_root / "mockserverInitialization.json").write_text(
                "[]", encoding="utf-8"
            )
        return repository

    def _execute(
        self,
        base: Path,
        adapter: RecordingBehaviorHarness,
        *,
        with_fixture: bool = False,
    ):
        repository = self._repository(base, with_fixture=with_fixture)
        workspace = create_result_workspace(
            "validate-evals",
            results_dir=base / "results",
            repository_root=repository.root,
        )
        adapter.expected_invocation_manifest = workspace.invocation_manifest
        result = execute_behavior_evals(
            repository.root,
            adapter,
            workspace,
            skill_filter="alpha",
            case_filter=None,
            max_concurrency=2,
            actor_timeout_seconds=60,
            judge_timeout_seconds=30,
        )
        return repository, workspace, result

    def test_standalone_runner_persists_pass_and_expectation_failure_decisions(self) -> None:
        cases = (
            ((), 0, "Decision: pass"),
            (("with-skill",), 1, "Decision: expectations failed"),
        )
        for failed_variants, expected_exit, expected_decision in cases:
            with self.subTest(expected_decision=expected_decision), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                repository = self._repository(base)
                results = base / "results"
                adapter = RecordingBehaviorHarness(
                    failed_variants=failed_variants,
                )
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
                        eval_validation,
                        "run_static_validation",
                        return_value=[],
                    ),
                    patch.object(
                        eval_validation.CodexEvaluationRuntime,
                        "create",
                        return_value=session,
                    ),
                    redirect_stdout(StringIO()),
                ):
                    result = eval_validation.run_behavior_eval_harness(
                        repository.root,
                        harness="codex",
                        skill_filter="alpha",
                        case_filter=None,
                        results_dir=results,
                        max_concurrency=2,
                    )

                self.assertEqual(result, expected_exit)
                self.assertIn(
                    expected_decision,
                    (results / "summary.md").read_text(encoding="utf-8"),
                )

    def test_runs_paired_catalogs_with_one_preflight_and_isolated_judges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = RecordingBehaviorHarness()

            with patch.object(
                eval_validation,
                "load_behavior_evals",
                wraps=eval_validation.load_behavior_evals,
            ) as load_definitions:
                repository, workspace, result = self._execute(base, adapter)
            benchmark = aggregate_results(
                workspace.root,
                "judge",
                repository_root=repository.root,
            )

            self.assertEqual(result.exit_code, 0)
            load_definitions.assert_called_once_with(repository.root)
            self.assertEqual(adapter.preflight_calls, [False])
            actors = [request for request, _ in adapter.requests if request.role == "actor"]
            judges = [request for request, _ in adapter.requests if request.role == "judge"]
            self.assertEqual(len(actors), 2)
            self.assertEqual(len(judges), 2)
            with_skill = next(
                request for request in actors if request.run_variant.endswith("with-skill")
            )
            without_skill = next(
                request for request in actors if request.run_variant.endswith("without-skill")
            )
            self.assertEqual(
                {path.name for path in with_skill.skill_sources}, {"alpha", "beta"}
            )
            self.assertEqual(
                {path.name for path in without_skill.skill_sources}, {"beta"}
            )
            self.assertEqual(with_skill.expected_skill, "alpha")
            self.assertIsNone(without_skill.expected_skill)
            self.assertTrue(all(request.capture_outputs for request in actors))
            self.assertTrue(all(not request.skill_sources for request in judges))
            self.assertTrue(all(not request.capture_outputs for request in judges))
            self.assertTrue(all(request.prompt == "Perform alpha." for request in actors))
            self.assertTrue(
                all("A complete alpha result." in request.prompt for request in judges)
            )
            self.assertTrue(all("untrusted evidence" in request.prompt.lower() for request in judges))
            source = benchmark["source_summaries"]["judge"]
            self.assertEqual(source["summary"]["failed_cases"], 0)
            self.assertEqual(
                set(source["groups"][0]["variants"]),
                {"with_skill", "without_skill"},
            )

    def test_only_with_skill_grading_controls_behavior_exit_one(self) -> None:
        for failed_variants, expected_exit in (
            (("without-skill",), 0),
            (("with-skill",), 1),
        ):
            with self.subTest(failed_variants=failed_variants), tempfile.TemporaryDirectory() as directory:
                adapter = RecordingBehaviorHarness(failed_variants=failed_variants)

                _, _, result = self._execute(Path(directory), adapter)

                self.assertEqual(result.exit_code, expected_exit)

    def test_actor_failure_is_an_execution_error_with_preserved_incomplete_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = RecordingBehaviorHarness(
                actor_failure_variant=eval_validation._injective_run_id(
                    "alpha", "alpha-core", "with-skill"
                )
            )

            _, workspace, result = self._execute(Path(directory), adapter)

            self.assertEqual(result.exit_code, 2)
            failed = next(
                outcome
                for case in result.case_results
                for outcome in case.attempts
                if outcome.variant == "with_skill"
            )
            self.assertIsNotNone(failed.error)
            self.assertTrue((failed.artifact_dir / "timing.json").is_file())
            self.assertFalse((failed.artifact_dir / "grading.json").exists())
            self.assertTrue(workspace.invocation_manifest.is_file())

    def test_run_identifiers_cannot_collide_across_skill_and_case_boundaries(self) -> None:
        first = eval_validation._injective_run_id("a", "b-c", "with-skill")
        second = eval_validation._injective_run_id("a-b", "c", "with-skill")

        self.assertNotEqual(first, second)

    def test_preflighted_capabilities_are_reused_without_another_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            adapter = RecordingBehaviorHarness()
            capabilities = adapter.preflight(require_fixtures=False)
            adapter.preflight_calls.clear()
            repository = self._repository(base)
            workspace = create_result_workspace(
                "validate-evals",
                results_dir=base / "results",
                repository_root=repository.root,
            )

            result = execute_behavior_evals(
                repository.root,
                adapter,
                workspace,
                skill_filter="alpha",
                case_filter=None,
                max_concurrency=2,
                actor_timeout_seconds=60,
                judge_timeout_seconds=30,
                preflighted_capabilities=capabilities,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(adapter.preflight_calls, [])

    def test_actor_response_must_be_preserved_exactly_before_checks_or_judging(self) -> None:
        actor_response = json.dumps({"value": "x" * (64 * 1024)})
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = self._repository(base)
            definition_path = (
                repository.root
                / "skills"
                / "workflows"
                / "alpha"
                / "evals"
                / "evals.json"
            )
            document = json.loads(definition_path.read_text(encoding="utf-8"))
            document["evals"][0]["checks"] = [
                {"type": "response_protocol", "format": "json"}
            ]
            definition_path.write_text(json.dumps(document), encoding="utf-8")
            workspace = create_result_workspace(
                "validate-evals",
                results_dir=base / "results",
                repository_root=repository.root,
            )
            adapter = RecordingBehaviorHarness(actor_response=actor_response)

            with patch.object(
                eval_validation,
                "evaluate_deterministic_checks",
                wraps=evaluate_deterministic_checks,
            ) as deterministic_checks:
                result = execute_behavior_evals(
                    repository.root,
                    adapter,
                    workspace,
                    skill_filter="alpha",
                    case_filter=None,
                    max_concurrency=2,
                    actor_timeout_seconds=60,
                    judge_timeout_seconds=30,
                )

            self.assertEqual(result.exit_code, 2)
            deterministic_checks.assert_not_called()
            self.assertFalse(
                any(request.role == "judge" for request, _ in adapter.requests)
            )
            failed = result.case_results[0].attempts[0]
            durable_response = (
                failed.artifact_dir / "outputs" / "response.md"
            ).read_text(encoding="utf-8")
            trace = (failed.artifact_dir / "execution_trace.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertLessEqual(
                len(durable_response.encode("utf-8")),
                eval_validation._MAX_RESPONSE_BYTES,
            )
            self.assertIn("[TRUNCATED]", durable_response)
            self.assertIn("cannot be preserved exactly", trace)
            self.assertFalse((failed.artifact_dir / "grading.json").exists())

    def test_deterministic_checks_receive_the_exact_durable_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            actor_response = json.dumps(
                {"status": "caf\u00e9"},
                ensure_ascii=False,
            )
            adapter = RecordingBehaviorHarness(actor_response=actor_response)

            with patch.object(
                eval_validation,
                "evaluate_deterministic_checks",
                wraps=evaluate_deterministic_checks,
            ) as deterministic_checks:
                _, workspace, result = self._execute(base, adapter)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(len(deterministic_checks.call_args_list), 2)
            self.assertTrue(
                all(
                    call.kwargs["response"] == actor_response
                    for call in deterministic_checks.call_args_list
                )
            )
            for attempt in workspace.attempts.iterdir():
                self.assertEqual(
                    (attempt / "outputs" / "response.md").read_text(encoding="utf-8"),
                    actor_response,
                )

    def test_judge_trace_evidence_obeys_the_exact_per_artifact_boundary(self) -> None:
        empty_trace = json.dumps(
            {"event": ""},
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        payload_size = (
            eval_validation._MAX_JUDGE_ARTIFACT_BYTES
            - len(empty_trace.encode("utf-8"))
        )

        for extra_byte, expected_exit in ((0, 0), (1, 2)):
            with self.subTest(extra_byte=extra_byte), tempfile.TemporaryDirectory() as directory:
                event = {"event": "x" * (payload_size + extra_byte)}
                expected_trace = json.dumps(
                    event,
                    sort_keys=True,
                    ensure_ascii=True,
                    allow_nan=False,
                )
                adapter = RecordingBehaviorHarness(
                    actor_trace_factory=lambda event=event: (event,)
                )

                with patch.object(
                    eval_validation,
                    "evaluate_deterministic_checks",
                    wraps=evaluate_deterministic_checks,
                ) as deterministic_checks:
                    _, _, result = self._execute(Path(directory), adapter)

                self.assertEqual(result.exit_code, expected_exit)
                judges = [
                    request
                    for request, _ in adapter.requests
                    if request.role == "judge"
                ]
                if extra_byte == 0:
                    self.assertEqual(len(deterministic_checks.call_args_list), 2)
                    self.assertEqual(len(judges), 2)
                    for request in judges:
                        evidence = json.loads(
                            request.prompt.split(
                                "UNTRUSTED_EVIDENCE_JSON\n", 1
                            )[1]
                        )
                        self.assertEqual(
                            evidence["execution_trace.jsonl"],
                            expected_trace,
                        )
                else:
                    deterministic_checks.assert_not_called()
                    self.assertEqual(judges, [])
                    self.assertTrue(
                        all(
                            attempt.error is not None
                            and "per-artifact judge byte limit" in attempt.error
                            for attempt in result.case_results[0].attempts
                        )
                    )

    def test_judge_text_output_obeys_the_exact_per_artifact_boundary(self) -> None:
        for extra_byte, expected_exit in ((0, 0), (1, 2)):
            with self.subTest(extra_byte=extra_byte), tempfile.TemporaryDirectory() as directory:
                report = "\u00e9" * (
                    eval_validation._MAX_JUDGE_ARTIFACT_BYTES // 2
                ) + ("x" * extra_byte)
                self.assertEqual(
                    len(report.encode("utf-8")),
                    eval_validation._MAX_JUDGE_ARTIFACT_BYTES + extra_byte,
                )
                adapter = RecordingBehaviorHarness(captured_report_text=report)

                with patch.object(
                    eval_validation,
                    "evaluate_deterministic_checks",
                    wraps=evaluate_deterministic_checks,
                ) as deterministic_checks:
                    _, _, result = self._execute(Path(directory), adapter)

                self.assertEqual(result.exit_code, expected_exit)
                judges = [
                    request
                    for request, _ in adapter.requests
                    if request.role == "judge"
                ]
                if extra_byte == 0:
                    self.assertEqual(len(deterministic_checks.call_args_list), 2)
                    self.assertEqual(len(judges), 2)
                    for request in judges:
                        evidence = json.loads(
                            request.prompt.split(
                                "UNTRUSTED_EVIDENCE_JSON\n", 1
                            )[1]
                        )
                        self.assertEqual(evidence["outputs/report.json"], report)
                else:
                    deterministic_checks.assert_not_called()
                    self.assertEqual(judges, [])
                    self.assertTrue(
                        all(
                            attempt.error is not None
                            and "per-artifact judge byte limit" in attempt.error
                            for attempt in result.case_results[0].attempts
                        )
                    )

    def test_composed_eval_quarantines_structured_authorization_and_cookie_traces(self) -> None:
        sensitive_events = (
            (
                {"Cookie": "session=opaque-cookie-structured"},
                ("opaque-cookie-structured",),
            ),
            (
                {"Authorization": "Basic opaque-authorization-structured"},
                ("opaque-authorization-structured",),
            ),
            (
                {
                    "message": json.dumps(
                        {
                            "Authorization": (
                                'Bearer opaque-nested-auth"nested-auth-tail'
                            )
                        }
                    )
                },
                ("opaque-nested-auth", "nested-auth-tail"),
            ),
            (
                {
                    "message": json.dumps(
                        {"Cookie": 'session=opaque-nested-cookie"nested-cookie-tail'}
                    )
                },
                ("opaque-nested-cookie", "nested-cookie-tail"),
            ),
        )
        for event, forbidden_values in sensitive_events:
            with self.subTest(event=tuple(event)), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                adapter = RecordingBehaviorHarness(
                    actor_trace_factory=lambda event=event: (dict(event),)
                )

                _, workspace, result = self._execute(base, adapter)

                self.assertEqual(result.exit_code, 2)
                self.assertFalse(
                    any(request.role == "judge" for request, _ in adapter.requests)
                )
                for attempt in workspace.attempts.iterdir():
                    trace = (attempt / "execution_trace.jsonl").read_text(
                        encoding="utf-8"
                    )
                    self.assertIn("actor_trace_quarantine", trace)
                self._assert_durable_tree_excludes(
                    workspace.root,
                    forbidden_values,
                )

    def test_composed_eval_detaches_actor_trace_before_post_scan_mutation(self) -> None:
        original_state = "original-frozen-trace-state"
        mutated_state = "post-scan-mutated-trace-state"
        late_secret = "post-scan-late-cookie-secret"
        source_events: list[dict[str, object]] = []
        immutable_checks: list[bool] = []

        def actor_trace() -> tuple[Mapping[str, object], ...]:
            event: dict[str, object] = {
                "event": "actor.completed",
                "detail": {"state": original_state},
            }
            source_events.append(event)
            return (event,)

        adapter = RecordingBehaviorHarness(actor_trace_factory=actor_trace)
        prepare_execution = eval_validation._prepare_durable_actor_execution

        def prepare_then_mutate(execution: HarnessExecution):
            durable_execution, response = prepare_execution(execution)
            source_event = execution.trace[0]
            source_event["Cookie"] = f"session={late_secret}"
            source_detail = source_event["detail"]
            if not isinstance(source_detail, dict):
                raise AssertionError("test trace detail must remain mutable at its source")
            source_detail["state"] = mutated_state
            try:
                durable_execution.trace[0]["late"] = "mutation"
            except TypeError:
                pass
            else:
                raise AssertionError("prepared actor trace must reject mutation")
            durable_detail = durable_execution.trace[0]["detail"]
            if not isinstance(durable_detail, Mapping):
                raise AssertionError("prepared trace detail must remain a JSON object")
            try:
                durable_detail["state"] = "mutation"
            except TypeError:
                immutable_checks.append(True)
            else:
                raise AssertionError("prepared nested actor trace must reject mutation")
            return durable_execution, response

        with tempfile.TemporaryDirectory() as directory, patch.object(
            eval_validation,
            "_prepare_durable_actor_execution",
            side_effect=prepare_then_mutate,
        ):
            _, workspace, result = self._execute(Path(directory), adapter)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(len(source_events), 2)
            self.assertEqual(immutable_checks, [True, True])
            for attempt in workspace.attempts.iterdir():
                trace = (attempt / "execution_trace.jsonl").read_text(
                    encoding="utf-8"
                )
                self.assertIn(original_state, trace)
            self._assert_durable_tree_excludes(
                workspace.root,
                (mutated_state, late_secret),
            )

    def test_actor_trace_rejects_oversized_scalar_before_encoder_construction(self) -> None:
        trace = (
            {
                "event": "actor.completed",
                "detail": "x" * (eval_validation._MAX_EXECUTION_TRACE_BYTES + 1),
            },
        )
        with patch.object(
            eval_validation.json,
            "JSONEncoder",
            side_effect=AssertionError(
                "oversized trace scalar must be rejected before encoder construction"
            ),
        ) as encoder:
            frozen = eval_validation._freeze_scanned_actor_trace(trace)

        self.assertIsNone(frozen)
        encoder.assert_not_called()

    def test_actor_trace_rejects_small_structural_limits_before_encoder_construction(self) -> None:
        cases = (
            (
                "nodes",
                "_MAX_EXECUTION_TRACE_JSON_NODES",
                3,
                ({"event": "actor.completed", "detail": "safe"},),
            ),
            (
                "depth",
                "_MAX_EXECUTION_TRACE_JSON_DEPTH",
                2,
                ({"event": "actor.completed"},),
            ),
        )
        for case_name, limit_name, limit, trace in cases:
            with self.subTest(case_name=case_name), patch.object(
                eval_validation,
                limit_name,
                limit,
            ), patch.object(
                eval_validation.json,
                "JSONEncoder",
                side_effect=AssertionError(
                    "structurally invalid trace must be rejected before encoding"
                ),
            ) as encoder:
                frozen = eval_validation._freeze_scanned_actor_trace(trace)

            self.assertIsNone(frozen)
            encoder.assert_not_called()

    def test_composed_eval_quarantines_trace_scan_limit_failure(self) -> None:
        original_scan = eval_validation.SecretScanBudget.scan

        def fail_trace_scan(scan_budget, text, source):
            if source == Path("execution_trace.json"):
                raise eval_validation.SecretScanLimitError(
                    "injected trace scan exhaustion"
                )
            return original_scan(scan_budget, text, source)

        with tempfile.TemporaryDirectory() as directory, patch.object(
            eval_validation.SecretScanBudget,
            "scan",
            new=fail_trace_scan,
        ):
            adapter = RecordingBehaviorHarness()
            _, workspace, result = self._execute(Path(directory), adapter)

            self.assertEqual(result.exit_code, 2)
            self.assertFalse(
                any(request.role == "judge" for request, _ in adapter.requests)
            )
            self.assertEqual(len(tuple(workspace.attempts.iterdir())), 2)
            for attempt in workspace.attempts.iterdir():
                trace = (attempt / "execution_trace.jsonl").read_text(
                    encoding="utf-8"
                )
                self.assertIn("actor_trace_quarantine", trace)
                self.assertFalse((attempt / "grading.json").exists())

    def test_composed_codex_eval_quarantines_bearer_cookie_and_escaped_json_evidence(self) -> None:
        from scripts.ai_skills_lib.codex_harness import CodexHarnessAdapter
        from tests.ai_skills.test_codex_harness import (
            FakeSandboxRuntime,
            codex_jsonl,
            command_result,
        )

        escaped_authorization = 'opaque-auth-prefix"auth-secret-suffix'
        escaped_cookie = 'opaque-cookie-prefix"cookie-secret-suffix'
        sensitive_values = (
            "opaque-path-credential",
            "opaque-file-credential",
            "opaque-trace-credential",
            escaped_authorization,
            escaped_cookie,
        )
        forbidden_renderings = (
            *sensitive_values,
            json.dumps(escaped_authorization)[1:-1],
            json.dumps(escaped_cookie)[1:-1],
            "auth-secret-suffix",
            "cookie-secret-suffix",
        )
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = self._repository(base)
            runtime = FakeSandboxRuntime(base / "runtime")
            runtime.remove_case_on_lease_release = True
            expected_skill = (
                runtime.state
                / "worker"
                / "case"
                / "codex-home"
                / "skills"
                / "alpha"
                / "SKILL.md"
            )

            def actor_jsonl(expected_path: Path | None) -> str:
                events = [
                    json.loads(line)
                    for line in codex_jsonl(expected_path).splitlines()
                ]
                events.insert(
                    -1,
                    {
                        "type": "error",
                        "message": f"Cookie: session={sensitive_values[2]}",
                    },
                )
                events.insert(
                    -1,
                    {
                        "type": "error",
                        "message": json.dumps(
                            {
                                "Authorization": (
                                    f"Bearer {escaped_authorization}"
                                )
                            }
                        ),
                    },
                )
                events.insert(
                    -1,
                    {
                        "type": "error",
                        "message": json.dumps(
                            {"Cookie": f"session={escaped_cookie}"}
                        ),
                    },
                )
                return "\n".join(json.dumps(event) for event in events) + "\n"

            runtime.execution_results.extend(
                (
                    command_result(actor_jsonl(expected_skill)),
                    command_result(actor_jsonl(None)),
                )
            )
            original_execute = runtime.execute

            def execute_with_sensitive_outputs(*args, **kwargs):
                worker, case = args[:2]
                if worker.role == "actor":
                    (case.workspace / "report.json").write_text(
                        '{"status":"ok"}',
                        encoding="utf-8",
                    )
                    sensitive_directory = (
                        case.workspace
                        / f"Authorization: Bearer {sensitive_values[0]}"
                    )
                    sensitive_directory.mkdir()
                    (sensitive_directory / "result.txt").write_text(
                        "safe body",
                        encoding="utf-8",
                    )
                    (case.workspace / "cookie.txt").write_text(
                        f"Cookie: session={sensitive_values[1]}",
                        encoding="utf-8",
                    )
                    (case.workspace / "authorization.json").write_text(
                        json.dumps(
                            {
                                "Authorization": (
                                    f"Bearer {escaped_authorization}"
                                )
                            }
                        ),
                        encoding="utf-8",
                    )
                    (case.workspace / "escaped-cookie.json").write_text(
                        json.dumps({"Cookie": f"session={escaped_cookie}"}),
                        encoding="utf-8",
                    )
                return original_execute(*args, **kwargs)

            runtime.execute = execute_with_sensitive_outputs
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=repository.root / "skills",
            )
            capabilities = HarnessCapabilities(
                harness_name="codex",
                available=True,
                actor_model="actor-model",
                actor_reasoning_effort="high",
                judge_model="judge-model",
                judge_reasoning_effort="high",
                reports_token_usage=True,
                reports_successful_skill_reads=True,
            )
            adapter._capabilities = capabilities
            workspace = create_result_workspace(
                "validate-evals",
                results_dir=runtime.results_root / "invocation",
                repository_root=repository.root,
            )

            result = execute_behavior_evals(
                repository.root,
                adapter,
                workspace,
                skill_filter="alpha",
                case_filter=None,
                max_concurrency=1,
                actor_timeout_seconds=60,
                judge_timeout_seconds=30,
                preflighted_capabilities=capabilities,
            )

            self.assertEqual(result.exit_code, 2)
            self.assertFalse(
                any(worker.role == "judge" for worker, *_ in runtime.calls)
            )
            for attempt in workspace.attempts.iterdir():
                self.assertFalse((attempt / "grading.json").exists())
                trace = (attempt / "execution_trace.jsonl").read_text(
                    encoding="utf-8"
                )
                self.assertIn("quarantine", trace.lower())
            self._assert_durable_tree_excludes(
                workspace.root,
                forbidden_renderings,
            )

    def test_composed_codex_eval_quarantines_adjacent_suffixes_in_final_response(self) -> None:
        from scripts.ai_skills_lib.codex_harness import CodexHarnessAdapter
        from tests.ai_skills.test_codex_harness import (
            FakeSandboxRuntime,
            codex_jsonl,
            command_result,
        )

        malformed_responses = (
            (
                "authorization",
                '{"Authorization":"Bearer opaque-auth"auth-secret-suffix}',
                "auth-secret-suffix",
            ),
            (
                "cookie",
                '{"Cookie":"session=opaque-cookie"cookie-secret-suffix}',
                "cookie-secret-suffix",
            ),
            (
                "bearer",
                'Bearer "opaque-bearer"bearer-secret-suffix',
                "bearer-secret-suffix",
            ),
        )

        for case_name, actor_response, suffix in malformed_responses:
            with self.subTest(case_name=case_name), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                repository = self._repository(base)
                runtime = FakeSandboxRuntime(base / "runtime")
                runtime.remove_case_on_lease_release = True
                expected_skill = (
                    runtime.state
                    / "worker"
                    / "case"
                    / "codex-home"
                    / "skills"
                    / "alpha"
                    / "SKILL.md"
                )

                def with_response(expected_path: Path | None) -> str:
                    events = [
                        json.loads(line)
                        for line in codex_jsonl(expected_path).splitlines()
                    ]
                    agent_messages = [
                        event
                        for event in events
                        if event.get("type") == "item.completed"
                        and event.get("item", {}).get("type") == "agent_message"
                    ]
                    agent_messages[-1]["item"]["text"] = actor_response
                    return "\n".join(json.dumps(event) for event in events) + "\n"

                runtime.execution_results.extend(
                    (
                        command_result(with_response(expected_skill)),
                        command_result(with_response(None)),
                    )
                )
                original_execute = runtime.execute

                def execute_with_report(*args, **kwargs):
                    worker, case = args[:2]
                    if worker.role == "actor":
                        (case.workspace / "report.json").write_text(
                            '{"status":"ok"}',
                            encoding="utf-8",
                        )
                    return original_execute(*args, **kwargs)

                runtime.execute = execute_with_report
                adapter = CodexHarnessAdapter(
                    runtime,
                    allowed_skill_root=repository.root / "skills",
                )
                capabilities = HarnessCapabilities(
                    harness_name="codex",
                    available=True,
                    actor_model="actor-model",
                    actor_reasoning_effort="high",
                    judge_model="judge-model",
                    judge_reasoning_effort="high",
                    reports_token_usage=True,
                    reports_successful_skill_reads=True,
                )
                adapter._capabilities = capabilities
                workspace = create_result_workspace(
                    "validate-evals",
                    results_dir=runtime.results_root / "invocation",
                    repository_root=repository.root,
                )

                result = execute_behavior_evals(
                    repository.root,
                    adapter,
                    workspace,
                    skill_filter="alpha",
                    case_filter=None,
                    max_concurrency=1,
                    actor_timeout_seconds=60,
                    judge_timeout_seconds=30,
                    preflighted_capabilities=capabilities,
                )

                self.assertEqual(result.exit_code, 2)
                self.assertFalse(
                    any(worker.role == "judge" for worker, *_ in runtime.calls)
                )
                self.assertEqual(len(tuple(workspace.attempts.iterdir())), 2)
                for attempt in workspace.attempts.iterdir():
                    response = (attempt / "outputs" / "response.md").read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(response, SENSITIVE_TEXT_QUARANTINE)
                    self.assertFalse((attempt / "grading.json").exists())
                self._assert_durable_tree_excludes(workspace.root, (suffix,))

    def test_composed_codex_eval_preserves_safe_fake_response_for_durability_and_judging(self) -> None:
        from scripts.ai_skills_lib.codex_harness import CodexHarnessAdapter
        from tests.ai_skills.test_codex_harness import (
            FakeSandboxRuntime,
            codex_jsonl,
            command_result,
        )

        actor_response = json.dumps(
            {
                "payload": json.dumps(
                    {
                        "Authorization": "Bearer FAKE_actor_response_token",
                        "Cookie": "session=FAKE_actor_cookie",
                    },
                    sort_keys=True,
                )
            },
            sort_keys=True,
        )
        judge_response = json.dumps(
            {
                "assertion_results": [
                    {
                        "id": "assertion-1",
                        "passed": True,
                        "evidence": "The preserved response is complete.",
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
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = self._repository(base)
            runtime = FakeSandboxRuntime(base / "runtime")
            runtime.remove_case_on_lease_release = True
            expected_skill = (
                runtime.state
                / "worker"
                / "case"
                / "codex-home"
                / "skills"
                / "alpha"
                / "SKILL.md"
            )

            def with_response(response: str, expected_path: Path | None = None) -> str:
                events = [
                    json.loads(line)
                    for line in codex_jsonl(expected_path).splitlines()
                ]
                agent_messages = [
                    event
                    for event in events
                    if event.get("type") == "item.completed"
                    and event.get("item", {}).get("type") == "agent_message"
                ]
                agent_messages[-1]["item"]["text"] = response
                return "\n".join(json.dumps(event) for event in events) + "\n"

            runtime.execution_results.extend(
                (
                    command_result(with_response(actor_response, expected_skill)),
                    command_result(with_response(judge_response)),
                    command_result(with_response(actor_response)),
                    command_result(with_response(judge_response)),
                )
            )
            original_execute = runtime.execute

            def execute_with_report(*args, **kwargs):
                worker, case = args[:2]
                if worker.role == "actor":
                    (case.workspace / "report.json").write_text(
                        '{"status":"ok"}',
                        encoding="utf-8",
                    )
                return original_execute(*args, **kwargs)

            runtime.execute = execute_with_report
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=repository.root / "skills",
            )
            capabilities = HarnessCapabilities(
                harness_name="codex",
                available=True,
                actor_model="actor-model",
                actor_reasoning_effort="high",
                judge_model="judge-model",
                judge_reasoning_effort="high",
                reports_token_usage=True,
                reports_successful_skill_reads=True,
            )
            adapter._capabilities = capabilities
            workspace = create_result_workspace(
                "validate-evals",
                results_dir=runtime.results_root / "invocation",
                repository_root=repository.root,
            )

            result = execute_behavior_evals(
                repository.root,
                adapter,
                workspace,
                skill_filter="alpha",
                case_filter=None,
                max_concurrency=1,
                actor_timeout_seconds=60,
                judge_timeout_seconds=30,
                preflighted_capabilities=capabilities,
            )

            self.assertEqual(result.exit_code, 0)
            for attempt in workspace.attempts.iterdir():
                self.assertEqual(
                    (attempt / "outputs" / "response.md").read_text(encoding="utf-8"),
                    actor_response,
                )
            judge_prompts = [
                argv[-1]
                for worker, _, argv, _, _ in runtime.calls
                if worker.role == "judge"
            ]
            self.assertEqual(len(judge_prompts), 2)
            self.assertTrue(
                all(
                    "FAKE_actor_response_token" in prompt
                    and "FAKE_actor_cookie" in prompt
                    for prompt in judge_prompts
                )
            )

    def test_malformed_judge_response_is_preserved_as_bounded_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = RecordingBehaviorHarness(judge_response="not valid judge json")

            _, _, result = self._execute(Path(directory), adapter)

            self.assertEqual(result.exit_code, 2)
            failed = result.case_results[0].attempts[0]
            trace = (failed.artifact_dir / "execution_trace.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertIn("judge_failure", trace)
            self.assertIn("not valid judge json", trace)

    def test_judge_timeout_is_preserved_without_an_invented_grade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = RecordingBehaviorHarness(judge_timed_out=True)

            _, _, result = self._execute(Path(directory), adapter)

            self.assertEqual(result.exit_code, 2)
            failed = result.case_results[0].attempts[0]
            trace = (failed.artifact_dir / "execution_trace.jsonl").read_text(
                encoding="utf-8"
            )
            self.assertIn("judge_failure", trace)
            self.assertIn('"timed_out":true', trace.replace(" ", ""))
            self.assertFalse((failed.artifact_dir / "grading.json").exists())

    def test_judge_prompt_requires_all_evidence_to_fit_aggregate_capacity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            outputs = base / "outputs"
            outputs.mkdir()
            for index in range(4):
                (outputs / f"artifact-{index:02}.txt").write_text(
                    "x" * 1024,
                    encoding="utf-8",
                )
            case = load_behavior_evals(
                self._repository(base / "repo").root
            )[0].cases[0]
            control = eval_validation._prepare_judge_control(case, "with_skill")

            allowed, prompt = eval_validation._judge_prompt(
                case,
                "with_skill",
                "response",
                "transcript",
                (),
                outputs,
                prepared_control=control,
            )
            exact_prompt_bytes = len(prompt.encode("utf-8"))
            expected_artifacts = {
                "outputs/response.md",
                "transcript.md",
                "execution_trace.jsonl",
                *(f"outputs/artifact-{index:02}.txt" for index in range(4)),
            }

            self.assertEqual(set(allowed), expected_artifacts)
            with patch.object(
                eval_validation,
                "_MAX_JUDGE_PROMPT_BYTES",
                exact_prompt_bytes,
            ):
                boundary_allowed, boundary_prompt = eval_validation._judge_prompt(
                    case,
                    "with_skill",
                    "response",
                    "transcript",
                    (),
                    outputs,
                    prepared_control=control,
                )
            self.assertEqual(set(boundary_allowed), expected_artifacts)
            self.assertEqual(boundary_prompt, prompt)

            with patch.object(
                eval_validation,
                "_MAX_JUDGE_PROMPT_BYTES",
                exact_prompt_bytes - 1,
            ):
                with self.assertRaisesRegex(
                    ResultArtifactError,
                    "aggregate judge prompt byte limit",
                ):
                    eval_validation._judge_prompt(
                        case,
                        "with_skill",
                        "response",
                        "transcript",
                        (),
                        outputs,
                        prepared_control=control,
                    )

    def test_fixture_inputs_are_actor_only_and_request_fixture_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            adapter = RecordingBehaviorHarness()

            _, _, result = self._execute(
                Path(directory), adapter, with_fixture=True
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(adapter.preflight_calls, [True])
            actors = [request for request, _ in adapter.requests if request.role == "actor"]
            judges = [request for request, _ in adapter.requests if request.role == "judge"]
            self.assertTrue(
                all(
                    tuple(item.destination.as_posix() for item in request.actor_inputs)
                    == ("context.txt",)
                    for request in actors
                )
            )
            self.assertTrue(all(request.fixture_initialization is not None for request in actors))
            self.assertTrue(all(not request.actor_inputs for request in judges))
            self.assertTrue(all(request.fixture_initialization is None for request in judges))

    def test_prepared_material_survives_repository_mutation_during_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = self._repository(base, with_fixture=True)
            alpha = repository.root / "skills" / "workflows" / "alpha"
            skill_path = alpha / "SKILL.md"
            input_path = (
                alpha
                / "evals"
                / "fixtures"
                / "alpha-core"
                / "inputs"
                / "context.txt"
            )
            initialization_path = (
                alpha
                / "evals"
                / "fixtures"
                / "alpha-core"
                / "mockserverInitialization.json"
            )
            original_skill = skill_path.read_bytes()
            original_input = input_path.read_bytes()
            original_initialization = initialization_path.read_bytes()

            def mutate_sources() -> None:
                skill_path.write_text("mutated during preflight\n", encoding="utf-8")
                input_path.write_text("mutated input\n", encoding="utf-8")
                initialization_path.write_text(
                    '[{"mutated": true}]',
                    encoding="utf-8",
                )

            adapter = MutatingPreflightBehaviorHarness(mutate_sources)
            workspace = create_result_workspace(
                "validate-evals",
                results_dir=base / "results",
                repository_root=repository.root,
            )
            adapter.expected_invocation_manifest = workspace.invocation_manifest

            result = execute_behavior_evals(
                repository.root,
                adapter,
                workspace,
                skill_filter="alpha",
                case_filter=None,
                max_concurrency=2,
                actor_timeout_seconds=60,
                judge_timeout_seconds=30,
            )

            self.assertEqual(result.exit_code, 0)
            actors = [
                request for request, _ in adapter.requests if request.role == "actor"
            ]
            self.assertEqual(len(actors), 2)
            with_skill = next(
                request
                for request in actors
                if request.run_variant.endswith("with-skill")
            )
            without_skill = next(
                request
                for request in actors
                if request.run_variant.endswith("without-skill")
            )
            alpha_source = next(
                source for source in with_skill.skill_sources if source.name == "alpha"
            )
            alpha_skill_file = next(
                item
                for item in alpha_source.files
                if item.relative_path == PurePosixPath("SKILL.md")
            )
            self.assertEqual(alpha_skill_file.content, original_skill)
            self.assertEqual(
                with_skill.actor_inputs[0].prepared.content,
                original_input,
            )
            self.assertIs(
                with_skill.actor_inputs[0].prepared,
                without_skill.actor_inputs[0].prepared,
            )
            self.assertEqual(
                with_skill.fixture_initialization.content,
                original_initialization,
            )
            self.assertIs(
                with_skill.fixture_initialization,
                without_skill.fixture_initialization,
            )
            with_beta = next(
                source for source in with_skill.skill_sources if source.name == "beta"
            )
            without_beta = next(
                source for source in without_skill.skill_sources if source.name == "beta"
            )
            self.assertIs(with_beta, without_beta)

    def test_prepared_schemas_survive_mutation_or_deletion_during_preflight(self) -> None:
        for mutation in ("replace", "delete"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                repository = self._repository(base)
                alpha = repository.root / "skills" / "workflows" / "alpha"
                definition_path = alpha / "evals" / "evals.json"
                document = json.loads(definition_path.read_text(encoding="utf-8"))
                document["evals"][0]["checks"] = [
                    {
                        "type": "json_schema",
                        "path": "report.json",
                        "schema": "fixtures/alpha-core/report.schema.json",
                    },
                    {
                        "type": "response_protocol",
                        "format": "json",
                        "schema": "fixtures/alpha-core/report.schema.json",
                    },
                ]
                definition_path.write_text(json.dumps(document), encoding="utf-8")
                schema_path = (
                    alpha
                    / "evals"
                    / "fixtures"
                    / "alpha-core"
                    / "report.schema.json"
                )
                schema_path.parent.mkdir(parents=True)
                original = json.dumps(
                    {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {"const": "ok"}},
                    },
                    sort_keys=True,
                ).encode("utf-8")
                schema_path.write_bytes(original)

                def mutate_schema() -> None:
                    if mutation == "delete":
                        schema_path.unlink()
                    else:
                        schema_path.write_text(
                            '{"type":"object","required":["mutated"]}',
                            encoding="utf-8",
                        )

                adapter = MutatingPreflightBehaviorHarness(mutate_schema)
                adapter.actor_response = '{"status":"ok"}'
                workspace = create_result_workspace(
                    "validate-evals",
                    results_dir=base / "results",
                    repository_root=repository.root,
                )
                adapter.expected_invocation_manifest = workspace.invocation_manifest

                with patch.object(
                    eval_validation,
                    "evaluate_deterministic_checks",
                    wraps=evaluate_deterministic_checks,
                ) as deterministic_checks:
                    result = execute_behavior_evals(
                        repository.root,
                        adapter,
                        workspace,
                        skill_filter="alpha",
                        case_filter=None,
                        max_concurrency=2,
                        actor_timeout_seconds=60,
                        judge_timeout_seconds=30,
                    )

                self.assertEqual(result.exit_code, 0)
                self.assertEqual(len(deterministic_checks.call_args_list), 2)
                catalogs = tuple(
                    call.kwargs["prepared_schemas"]
                    for call in deterministic_checks.call_args_list
                )
                self.assertIs(catalogs[0], catalogs[1])
                self.assertEqual(len(catalogs[0]), 1)
                relative, prepared = catalogs[0][0]
                self.assertEqual(
                    relative,
                    PurePosixPath("fixtures/alpha-core/report.schema.json"),
                )
                self.assertEqual(prepared.content, original)
                self.assertEqual(prepared.sha256, hashlib.sha256(original).hexdigest())

    def test_fixture_created_during_preflight_is_not_added_to_prepared_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = self._repository(base)
            fixture_root = (
                repository.root
                / "skills"
                / "workflows"
                / "alpha"
                / "evals"
                / "fixtures"
                / "alpha-core"
            )

            def create_late_fixture() -> None:
                fixture_root.mkdir(parents=True)
                (fixture_root / "mockserverInitialization.json").write_text(
                    "[]",
                    encoding="utf-8",
                )

            adapter = MutatingPreflightBehaviorHarness(create_late_fixture)
            workspace = create_result_workspace(
                "validate-evals",
                results_dir=base / "results",
                repository_root=repository.root,
            )
            adapter.expected_invocation_manifest = workspace.invocation_manifest

            result = execute_behavior_evals(
                repository.root,
                adapter,
                workspace,
                skill_filter="alpha",
                case_filter=None,
                max_concurrency=2,
                actor_timeout_seconds=60,
                judge_timeout_seconds=30,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(adapter.preflight_calls, [False])
            actors = [
                request for request, _ in adapter.requests if request.role == "actor"
            ]
            self.assertTrue(
                all(request.fixture_initialization is None for request in actors)
            )
            self.assertTrue(all(request.fixture_root is None for request in actors))


class BehaviorCliTests(unittest.TestCase):
    def test_serialized_judge_controls_are_bounded_before_workspace_or_preflight(self) -> None:
        oracle_values = (
            "\u0001" * 1200,
            "\U0001f600" * 600,
        )
        for index, oracle_value in enumerate(oracle_values):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                repository = TemporaryBehaviorRepository(base / "repository")
                repository.add_skill(
                    "alpha",
                    document={
                        "skill_name": "alpha",
                        "evals": [
                            {
                                "id": "alpha-core",
                                "prompt": "Perform alpha.",
                                "expected_output": "A complete alpha result.",
                                "assertions": [
                                    f"{oracle_value}{assertion_index}"
                                    for assertion_index in range(64)
                                ],
                                "checks": [],
                            }
                        ],
                    },
                )
                results = base / "results"
                output = StringIO()

                with (
                    patch.object(eval_validation, "run_static_validation", return_value=[]),
                    patch.object(
                        eval_validation.CodexEvaluationRuntime,
                        "create",
                    ) as create_runtime,
                    redirect_stdout(output),
                ):
                    result = eval_validation.run_behavior_eval_harness(
                        repository.root,
                        harness="codex",
                        skill_filter=None,
                        case_filter=None,
                        results_dir=results,
                        max_concurrency=2,
                    )

                self.assertEqual(result, 2)
                self.assertFalse(results.exists())
                create_runtime.assert_not_called()
                self.assertIn("judge control envelope", output.getvalue())

    def test_behavior_command_requires_harness_and_supports_case_filter(self) -> None:
        parser = build_parser()

        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["validate", "evals"])
        args = parser.parse_args(
            [
                "validate",
                "evals",
                "--harness",
                "codex",
                "--skill",
                "alpha",
                "--case",
                "alpha-core",
                "--max-concurrency",
                "4",
                "--results-dir",
                "/tmp/behavior-results",
            ]
        )

        self.assertEqual(args.harness, "codex")
        self.assertEqual(args.skill, "alpha")
        self.assertEqual(args.case, "alpha-core")
        self.assertEqual(args.max_concurrency, 4)
        self.assertEqual(args.results_dir, Path("/tmp/behavior-results"))

    def test_cli_dispatches_behavior_runner_without_executing_a_model(self) -> None:
        with patch.object(cli, "run_behavior_eval_harness", return_value=1) as run:
            result = cli.main(
                [
                    "validate",
                    "evals",
                    "--harness",
                    "codex",
                    "--skill",
                    "alpha",
                    "--case",
                    "alpha-core",
                ]
            )

        self.assertEqual(result, 1)
        run.assert_called_once_with(
            cli.REPOSITORY_ROOT,
            harness="codex",
            skill_filter="alpha",
            case_filter="alpha-core",
            results_dir=None,
            max_concurrency=2,
        )

    def test_model_runner_stops_before_results_on_static_contract_issues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            with (
                patch.object(
                    eval_validation,
                    "run_static_validation",
                    return_value=[
                        eval_validation.ValidationIssue(
                            scope="skills/alpha", message="unsafe topology"
                        )
                    ],
                    create=True,
                ),
                patch.object(eval_validation, "create_result_workspace") as create_results,
                redirect_stdout(output),
            ):
                result = eval_validation.run_behavior_eval_harness(
                    Path(directory),
                    harness="codex",
                    skill_filter=None,
                    case_filter=None,
                    results_dir=None,
                    max_concurrency=2,
                )

        self.assertEqual(result, 2)
        create_results.assert_not_called()
        self.assertIn("unsafe topology", output.getvalue())

    def test_post_workspace_declaration_failure_writes_summary_and_result_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = TemporaryBehaviorRepository(base / "repository")
            repository.add_skill("alpha")
            results = base / "results"
            output = StringIO()

            with (
                patch.object(eval_validation, "run_static_validation", return_value=[]),
                patch.object(
                    eval_validation,
                    "declare_behavior_plan",
                    side_effect=ResultArtifactError("cannot declare behavior plan"),
                ),
                redirect_stdout(output),
            ):
                result = eval_validation.run_behavior_eval_harness(
                    repository.root,
                    harness="codex",
                    skill_filter=None,
                    case_filter=None,
                    results_dir=results,
                    max_concurrency=2,
                )

            rendered = output.getvalue()
            summary = (results / "summary.md").read_text(encoding="utf-8")
            self.assertEqual(result, 2)
            self.assertIn("cannot declare behavior plan", rendered)
            self.assertIn(f"Results: {results.resolve()}", rendered)
            self.assertIn("Decision: execution error", summary)
            self.assertIn("cannot declare behavior plan", summary)


if __name__ == "__main__":
    unittest.main()
