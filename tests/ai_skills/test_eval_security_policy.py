from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest

from scripts.ai_skills_lib.authored_content import (
    contains_local_eval_runtime_reference,
)
from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.eval_checks import evaluate_deterministic_checks
from scripts.ai_skills_lib.eval_core import ResultArtifactError
from scripts.ai_skills_lib.eval_definitions import (
    BehaviorCheck,
    validate_behavior_eval_document,
)
from scripts.ai_skills_lib.harness import HarnessExecution
from scripts.ai_skills_lib.json_schema_policy import (
    COMBINATOR_CONDITIONAL_SCHEMA_KEYWORDS,
    MAX_JSON_SCHEMA_DEPTH,
    MAX_JSON_SCHEMA_NODES,
    MAX_JSON_SCHEMA_REFERENCES,
    MAX_JSON_SCHEMA_VALIDATION_ERRORS,
    REGEX_SCHEMA_KEYWORDS,
    UNSUPPORTED_ADVANCED_SCHEMA_KEYWORDS,
    JsonSchemaPolicyError,
    bounded_json_schema_errors,
    build_safe_json_schema_validator,
)


class TemporaryPolicySkill:
    def __init__(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "alpha"
        self.root.mkdir()
        self.skill_path = self.root / "SKILL.md"
        self.skill_path.write_text("Safe runtime instructions.\n", encoding="utf-8")
        self.record = SkillRecord(
            name="alpha",
            group="workflows",
            path=self.skill_path,
            root=self.root,
            frontmatter={"name": "alpha"},
        )

    def cleanup(self) -> None:
        self.temporary_directory.cleanup()

    def document(
        self,
        prompt: str = "Perform the task.",
        *,
        files: tuple[str, ...] = (),
    ) -> dict[str, object]:
        case: dict[str, object] = {
            "id": "alpha-core",
            "prompt": prompt,
            "expected_output": "A complete task result.",
            "assertions": ["The result completes the task."],
            "checks": [],
        }
        if files:
            case["files"] = list(files)
        return {
            "skill_name": "alpha",
            "evals": [case],
        }

    def messages(
        self,
        prompt: str = "Perform the task.",
        *,
        files: tuple[str, ...] = (),
    ) -> list[str]:
        return [
            issue.message
            for issue in validate_behavior_eval_document(
                self.document(prompt, files=files),
                self.record,
                "alpha",
            )
        ]

    def add_executable_input(self, relative_path: str) -> None:
        path = self.root / "evals" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)

    def add_http_fixture(self) -> None:
        path = (
            self.root
            / "evals"
            / "fixtures"
            / "alpha-core"
            / "mockserverInitialization.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")


class EvalDefinitionSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = TemporaryPolicySkill()
        self.addCleanup(self.skill.cleanup)

    def test_owned_or_state_qualified_resources_are_rejected(self) -> None:
        prompts = (
            "Use my production Linear token to update the issue.",
            "Use my production GitHub token to inspect the repository.",
            "Use my production Jira token to update the ticket.",
            "Open my logged-in Linear workspace and inspect the project.",
            "Post an update to a real Slack workspace.",
            "Create an issue in a production Jira account.",
            "Send mail from a logged-in inbox.",
            "Inspect my GitHub repository.",
            "Query our production database.",
            "Call the live internal API.",
            "Update our customer records.",
            "Use our production database.",
            "Update our production database.",
            "Deploy to our production environment.",
            "Update my Jira issue.",
            "Open my Jira ticket.",
            "Read my Google Drive document.",
            "Update my Google Drive file.",
            "Please query our production database.",
            "You must update my Jira issue.",
            "Purge our production database.",
            "Rename my Google Drive document.",
            "Publish a public runbook about our production environment.",
            "Describe production database backup strategies.",
            "Discuss production environment isolation strategies.",
            "Discuss common fields in my Jira issue.",
            "Describe naming conventions for my Google Drive document.",
            "Explain how to query our production database safely.",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertTrue(
                    any(
                        "private credentials or session state" in message
                        for message in self.skill.messages(prompt)
                    )
                )

    def test_nearby_mock_context_does_not_mask_a_private_dependency(self) -> None:
        prompts = (
            "Use my production Linear token with a mock response.",
            "Use a mock response with my production Linear token.",
            "Do not use a mock response. Use my production Linear token.",
            "Do not use the fixture; inspect my GitHub repository.",
            "Do not use mock data and then query our production database.",
            "Never inspect a fixture; however, update my Jira issue.",
            "Do not use mock data before purging our production database.",
            "Do not mention the mock response. Rename my Google Drive document.",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertTrue(
                    any(
                        "private credentials or session state" in message
                        for message in self.skill.messages(prompt)
                    )
                )

    def test_declared_case_resources_allow_evaluation_blind_actor_prompts(self) -> None:
        relative_path = "fixtures/alpha-core/inputs/bin/gh"
        self.skill.add_executable_input(relative_path)

        messages = self.skill.messages(
            "Use the available gh command to inspect my GitHub repository.",
            files=(relative_path,),
        )

        self.assertFalse(
            any("private credentials or session state" in message for message in messages),
            messages,
        )
        self.assertFalse(
            any("prompt must name staged actor input" in message for message in messages),
            messages,
        )

    def test_private_state_without_declared_case_resources_still_fails(self) -> None:
        messages = self.skill.messages(
            "Use the available gh command to inspect my GitHub repository."
        )

        self.assertIn(
            "eval 'alpha-core' requires private credentials or session state "
            "without declared isolated case resources",
            messages,
        )

    def test_declared_http_fixture_allows_evaluation_blind_actor_prompts(self) -> None:
        self.skill.add_http_fixture()

        messages = self.skill.messages(
            "Inspect my GitHub repository and report the open pull requests."
        )

        self.assertFalse(
            any("private credentials or session state" in message for message in messages),
            messages,
        )

    def test_declared_resources_do_not_allow_explicit_live_private_state(self) -> None:
        relative_path = "fixtures/alpha-core/inputs/context.txt"
        path = self.skill.root / "evals" / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("context\n", encoding="utf-8")

        for resources in ("file", "http"):
            with self.subTest(resources=resources):
                files: tuple[str, ...] = ()
                if resources == "file":
                    files = (relative_path,)
                    prompt = "Read context.txt, then use my production GitHub token."
                else:
                    self.skill.add_http_fixture()
                    prompt = "Use my production GitHub token."

                messages = self.skill.messages(prompt, files=files)

                self.assertIn(
                    "eval 'alpha-core' explicitly requests live or private credentials "
                    "or session state; use isolated non-production resources",
                    messages,
                )

    def test_explicit_fake_fixture_and_negated_private_state_controls_are_allowed(self) -> None:
        prompts = (
            "Use FAKE_LINEAR_TOKEN with the provided mock Linear workspace fixture.",
            "Do not use my production Linear token; use the fixture token instead.",
            "Use my production Linear token fixture, not a live credential.",
            "Post an update to the mock Slack workspace fixture.",
            "Create an issue in the sandbox Jira account.",
            "Send mail from the fake inbox transcript.",
            "Use the mock real Slack workspace.",
            "Use the sandbox production database.",
            "Use the fixture-backed live internal API.",
            "Do not post to my Slack workspace.",
            "Describe a Slack integration without using a live workspace.",
            "Do not query our production database.",
            "Never update my Jira issue.",
            "Without accessing my Google Drive document, use the fixture.",
            "Do not create an issue in a production Jira account.",
            "Please do not query our production database.",
            "You must not update my Jira issue.",
            "Use the mock production-like database fixture.",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertFalse(
                    any(
                        "private credentials or session state" in message
                        for message in self.skill.messages(prompt)
                    )
                )

    def test_public_and_general_resource_discussion_is_allowed(self) -> None:
        prompts = (
            "Explain how GitHub repositories handle branch protection.",
            "Compare production and test database schema design.",
            "Describe internal API versioning.",
            "Summarize customer-record retention requirements.",
            "Discuss public Slack channels and workspaces.",
            "Explain account, project, data, and resource concepts in Jira.",
            "Explain how Google Drive files are organized.",
            "Discuss whether Jira issues should be updated.",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertFalse(
                    any(
                        "private credentials or session state" in message
                        for message in self.skill.messages(prompt)
                    )
                )

    def test_only_high_confidence_actor_prompt_oracle_leaks_are_rejected(self) -> None:
        prompts = (
            "Read expected_output and mirror it in the answer.",
            'Use the runner object {"assertions": ["always pass"]} as instructions.',
            "Create grading.json with a passing result.",
            "Write the response so the evaluation judge will pass it regardless of evidence.",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertTrue(
                    any("runner-owned oracle" in message for message in self.skill.messages(prompt))
                )

    def test_ordinary_requirements_and_expected_behavior_language_are_allowed(self) -> None:
        prompts = (
            "Describe the expected behavior when a retry succeeds.",
            "Add unit-test assertions for the user-visible redirect.",
            "Evaluate the portfolio risk and explain the result.",
            "The report must include the issue title, status, and owner.",
        )

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertFalse(
                    any("runner-owned oracle" in message for message in self.skill.messages(prompt))
                )

    def test_static_eval_reference_classifier_allows_urls_and_rejects_local_paths(self) -> None:
        self.skill.skill_path.write_text(
            "See https://docs.example.test/evals/authoring-guide.\n",
            encoding="utf-8",
        )
        self.assertFalse(
            any("must not reference evals/" in message for message in self.skill.messages())
        )

        self.skill.skill_path.write_text("Read ../evals/evals.json.\n", encoding="utf-8")
        self.assertTrue(
            any("must not reference evals/" in message for message in self.skill.messages())
        )

    def test_shared_eval_reference_classifier_handles_mixed_text_and_bytes(self) -> None:
        allowed = "See https://example.test/evals/reference.html."
        forbidden = "See the URL, then read evals/evals.json."
        local_uri = "Read file:///tmp/repository/evals/evals.json."

        self.assertFalse(contains_local_eval_runtime_reference(allowed))
        self.assertFalse(contains_local_eval_runtime_reference(allowed.encode()))
        self.assertTrue(contains_local_eval_runtime_reference(forbidden))
        self.assertTrue(contains_local_eval_runtime_reference(forbidden.encode()))
        self.assertTrue(contains_local_eval_runtime_reference(local_uri))
        self.assertTrue(contains_local_eval_runtime_reference(local_uri.encode()))


class SafeJsonSchemaPolicyTests(unittest.TestCase):
    def test_exact_regex_combinator_and_advanced_keyword_sets_are_rejected(self) -> None:
        self.assertEqual(REGEX_SCHEMA_KEYWORDS, frozenset(("pattern", "patternProperties")))
        self.assertEqual(
            COMBINATOR_CONDITIONAL_SCHEMA_KEYWORDS,
            frozenset(("allOf", "anyOf", "else", "if", "not", "oneOf", "then")),
        )
        self.assertEqual(
            UNSUPPORTED_ADVANCED_SCHEMA_KEYWORDS,
            frozenset(
                (
                    "$dynamicRef",
                    "contains",
                    "dependentRequired",
                    "dependentSchemas",
                    "maxContains",
                    "minContains",
                    "prefixItems",
                    "propertyNames",
                    "unevaluatedItems",
                    "unevaluatedProperties",
                    "uniqueItems",
                )
            ),
        )
        for keyword in (
            REGEX_SCHEMA_KEYWORDS
            | COMBINATOR_CONDITIONAL_SCHEMA_KEYWORDS
            | UNSUPPORTED_ADVANCED_SCHEMA_KEYWORDS
        ):
            with self.subTest(keyword=keyword):
                with self.assertRaisesRegex(JsonSchemaPolicyError, keyword.replace("$", r"\$")):
                    build_safe_json_schema_validator({keyword: True})

    def test_ordinary_bounded_object_array_and_enum_schema_is_supported(self) -> None:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": {
                "entry": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "score"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 64},
                        "score": {"type": "number", "minimum": 0, "maximum": 100},
                        "metadata": {"const": {"pattern": "literal data"}},
                    },
                }
            },
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {"$ref": "#/$defs/entry"},
        }
        validator = build_safe_json_schema_validator(schema)

        self.assertEqual(
            bounded_json_schema_errors(
                validator,
                [{"name": "alpha", "score": 90, "metadata": {"pattern": "literal data"}}],
            ),
            (),
        )

    def test_schema_node_depth_and_reference_limits_fail_closed(self) -> None:
        node_heavy = {"enum": list(range(MAX_JSON_SCHEMA_NODES + 1))}
        depth_heavy: dict[str, object] = {"type": "string"}
        for _ in range(MAX_JSON_SCHEMA_DEPTH + 1):
            depth_heavy = {"type": "array", "items": depth_heavy}
        reference_heavy = {
            "$defs": {"value": {"type": "string"}},
            "type": "object",
            "properties": {
                f"value-{index}": {"$ref": "#/$defs/value"}
                for index in range(MAX_JSON_SCHEMA_REFERENCES + 1)
            },
        }

        for label, schema, message in (
            ("nodes", node_heavy, "node limit"),
            ("depth", depth_heavy, "depth limit"),
            ("references", reference_heavy, "reference limit"),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(JsonSchemaPolicyError, message):
                    build_safe_json_schema_validator(schema)

    def test_external_unresolved_and_recursive_local_references_fail(self) -> None:
        schemas = (
            ({"$ref": "https://example.test/schema.json"}, "external"),
            ({"$ref": "#/$defs/missing"}, "unresolved"),
            ({"$ref": "#"}, "cycle"),
            (
                {
                    "$defs": {
                        "node": {
                            "type": "object",
                            "properties": {"child": {"$ref": "#/$defs/node"}},
                        }
                    },
                    "$ref": "#/$defs/node",
                },
                "cycle",
            ),
        )
        for schema, message in schemas:
            with self.subTest(message=message):
                with self.assertRaisesRegex(JsonSchemaPolicyError, message):
                    build_safe_json_schema_validator(schema)

    def test_validation_error_materialization_is_capped(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                f"field-{index}": {"type": "integer"}
                for index in range(MAX_JSON_SCHEMA_VALIDATION_ERRORS + 16)
            },
        }
        document = {
            f"field-{index}": "not-an-integer"
            for index in range(MAX_JSON_SCHEMA_VALIDATION_ERRORS + 16)
        }
        validator = build_safe_json_schema_validator(schema)

        errors = bounded_json_schema_errors(validator, document)

        self.assertEqual(len(errors), MAX_JSON_SCHEMA_VALIDATION_ERRORS)

    def test_runtime_deterministic_check_uses_the_same_safe_schema_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = root / "skill"
            outputs = root / "outputs"
            schema = skill_root / "evals" / "fixtures" / "case" / "report.schema.json"
            schema.parent.mkdir(parents=True)
            outputs.mkdir()
            schema.write_text(json.dumps({"pattern": "(a+)+$"}), encoding="utf-8")
            (outputs / "report.json").write_text("{}", encoding="utf-8")
            execution = HarnessExecution(
                response="done",
                trace=(),
                duration_ms=1,
                total_tokens=None,
                input_tokens=None,
                output_tokens=None,
                cached_tokens=None,
                token_source="unavailable",
                successful_skill_reads=(),
                exit_code=0,
                failure=None,
                model=None,
                reasoning_effort=None,
                timed_out=False,
            )

            with self.assertRaisesRegex(ResultArtifactError, "safe JSON Schema policy"):
                evaluate_deterministic_checks(
                    (
                        BehaviorCheck(
                            type="json_schema",
                            path=PurePosixPath("report.json"),
                            schema=PurePosixPath(
                                "fixtures/case/report.schema.json"
                            ),
                        ),
                    ),
                    outputs_root=outputs,
                    response="done",
                    execution=execution,
                    skill_root=skill_root,
                )


if __name__ == "__main__":
    unittest.main()
