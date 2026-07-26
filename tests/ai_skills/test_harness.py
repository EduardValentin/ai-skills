from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest

from scripts.ai_skills_lib.harness import (
    ActorInput,
    HarnessAdapter,
    HarnessCapabilities,
    HarnessExecution,
    HarnessRequest,
    PreparedFile,
    PreparedResponseSchema,
    PreparedSkillFile,
    PreparedSkillSource,
    bind_harness_request,
    harness_request_matches_execution_binding,
    validated_actor_skill_read_lifecycle,
)


def prepared_file(source: str = "request.md", content: bytes = b"content\n") -> PreparedFile:
    return PreparedFile(source=Path(source), content=content)


def prepared_skill(name: str = "example") -> PreparedSkillSource:
    return PreparedSkillSource(
        source_root=Path("skills/workflows") / name,
        name=name,
        files=(
            PreparedSkillFile(
                relative_path=PurePosixPath("SKILL.md"),
                content=f"---\nname: {name}\n---\n".encode(),
                executable=False,
            ),
        ),
    )


class RecordingHarness:
    def __init__(self):
        self.requests: list[tuple[HarnessRequest, Path]] = []

    def preflight(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            harness_name="recording",
            available=True,
            actor_model="configured-actor",
            actor_reasoning_effort="medium",
            judge_model="configured-judge",
            judge_reasoning_effort="high",
            reports_token_usage=True,
            reports_successful_skill_reads=True,
            details=("ready",),
            failure=None,
        )

    def execute(self, request: HarnessRequest, artifact_dir: Path) -> HarnessExecution:
        self.requests.append((request, artifact_dir))
        return HarnessExecution(
            response="normalized response",
            trace=({"event": "completed"},),
            duration_ms=25,
            total_tokens=12,
            input_tokens=8,
            output_tokens=4,
            cached_tokens=None,
            token_source="harness_report",
            successful_skill_reads=(Path("/projected/skills/example/SKILL.md"),),
            exit_code=0,
            failure=None,
            model="configured-actor",
            reasoning_effort="medium",
            timed_out=False,
        )


class HarnessContractTests(unittest.TestCase):
    def test_request_rejects_live_filesystem_material(self):
        cases = (
            {
                "skill_sources": (Path("skills/workflows/example"),),
            },
            {
                "fixture_root": Path(
                    "skills/workflows/example/evals/fixtures/case"
                ),
                "fixture_initialization": Path(
                    "skills/workflows/example/evals/fixtures/case/"
                    "mockserverInitialization.json"
                ),
            },
        )

        for fields in cases:
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, "prepared"):
                    HarnessRequest(
                        role="actor",
                        run_variant="candidate",
                        prompt="Perform the case.",
                        timeout_seconds=60,
                        **fields,
                    )

    def test_skill_read_requires_one_complete_bound_command_lifecycle(self):
        skill_path = "/case/codex-home/skills/example/SKILL.md"
        lifecycle = (
            {"event": "harness_thread_started"},
            {"event": "harness_turn_started"},
            {
                "event": "command_started",
                "command_id": "read-1",
                "command": "cat",
            },
            {
                "event": "command_completed",
                "command_id": "read-1",
                "command": "cat",
                "exit_code": 0,
                "status": "completed",
            },
            {
                "event": "skill_read",
                "command_id": "read-1",
                "path": skill_path,
            },
            {"event": "harness_turn_completed"},
        )

        self.assertEqual(
            validated_actor_skill_read_lifecycle(lifecycle),
            (skill_path,),
        )
        with self.assertRaisesRegex(
            ValueError,
            "not bound to a successful trusted command",
        ):
            validated_actor_skill_read_lifecycle(
                (
                    {"event": "harness_thread_started"},
                    {"event": "harness_turn_started"},
                    {
                        "event": "skill_read",
                        "command_id": "read-1",
                        "path": skill_path,
                    },
                    {"event": "harness_turn_completed"},
                )
            )
        with self.assertRaisesRegex(
            ValueError,
            "tool completion is malformed or unmatched",
        ):
            validated_actor_skill_read_lifecycle(
                (
                    {"event": "harness_thread_started"},
                    {"event": "harness_turn_started"},
                    {
                        "event": "tool_completed",
                        "tool_id": "tool-1",
                        "tool_type": "mcp_tool_call",
                    },
                    *lifecycle[2:],
                )
            )

    def test_execution_binding_rejects_request_mutation_after_binding(self):
        request = HarnessRequest(
            role="actor",
            run_variant="candidate",
            prompt="Perform the case.",
            timeout_seconds=60,
        )
        bound = bind_harness_request(
            request,
            invocation_id="a" * 32,
            run_id="candidate",
        )

        self.assertTrue(harness_request_matches_execution_binding(bound))
        self.assertFalse(
            harness_request_matches_execution_binding(
                replace(bound, prompt="Perform a different case.")
            )
        )

    def test_execution_binding_uses_an_immutable_response_schema_snapshot(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
        }
        bound = bind_harness_request(
            HarnessRequest(
                role="judge",
                run_variant="semantic-grade",
                prompt="Grade the evidence.",
                timeout_seconds=30,
                response_schema=schema,
            ),
            invocation_id="b" * 32,
            run_id="semantic-grade",
        )
        schema["required"] = ["verdict"]

        self.assertTrue(harness_request_matches_execution_binding(bound))
        self.assertIsInstance(bound.response_schema, PreparedResponseSchema)
        document = json.loads(bound.response_schema.content)
        self.assertNotIn("required", document)

    def test_response_schema_mapping_is_read_once_before_binding(self):
        class AlternatingSchema(dict):
            def __init__(self):
                super().__init__(
                    type="object",
                    additionalProperties=False,
                )
                self.item_calls = 0

            def items(self):
                self.item_calls += 1
                return {
                    "type": "object",
                    "additionalProperties": self.item_calls % 2 == 0,
                }.items()

        schema = AlternatingSchema()
        bound = bind_harness_request(
            HarnessRequest(
                role="judge",
                run_variant="semantic-grade",
                prompt="Grade the evidence.",
                timeout_seconds=30,
                response_schema=schema,
            ),
            invocation_id="c" * 32,
            run_id="semantic-grade",
        )

        self.assertEqual(schema.item_calls, 1)
        self.assertTrue(harness_request_matches_execution_binding(bound))
        self.assertFalse(json.loads(bound.response_schema.content)["additionalProperties"])

    def test_contract_records_are_frozen_and_keep_configured_model_defaults_unset(self):
        request = HarnessRequest(
            role="actor",
            run_variant="candidate",
            prompt="Perform the case.",
            skill_sources=(prepared_skill(),),
            expected_skill="example",
            model=None,
            reasoning_effort=None,
            timeout_seconds=60,
        )

        self.assertIsNone(request.model)
        self.assertIsNone(request.reasoning_effort)
        with self.assertRaises(FrozenInstanceError):
            request.prompt = "changed"

    def test_request_rejects_unknown_roles_empty_variants_and_nonpositive_timeouts(self):
        valid = {
            "role": "actor",
            "run_variant": "candidate",
            "prompt": "Perform the case.",
            "timeout_seconds": 60,
        }
        invalid_values = (
            ({**valid, "role": "grader"}, "role"),
            ({**valid, "run_variant": ""}, "run_variant"),
            ({**valid, "timeout_seconds": 0}, "timeout_seconds"),
        )

        for arguments, message in invalid_values:
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, message):
                    HarnessRequest(**arguments)

    def test_judge_request_rejects_actor_skill_provisioning(self):
        for restricted in (
            {"skill_sources": (prepared_skill(),)},
            {"expected_skill": "example"},
        ):
            with self.subTest(restricted=restricted):
                with self.assertRaisesRegex(ValueError, "judge.*skill"):
                    HarnessRequest(
                        role="judge",
                        run_variant="semantic_grade",
                        prompt="Grade the evidence.",
                        timeout_seconds=30,
                        **restricted,
                    )

    def test_actor_request_accepts_an_immutable_shell_environment(self):
        request = HarnessRequest(
            role="actor",
            run_variant="fixture",
            prompt="Call the fixture API.",
            timeout_seconds=60,
            shell_environment=(("HTTPS_PROXY", "http://127.0.0.1:1080"),),
        )

        self.assertEqual(
            request.shell_environment,
            (("HTTPS_PROXY", "http://127.0.0.1:1080"),),
        )

    def test_judge_request_rejects_actor_fixture_provisioning(self):
        for restricted in (
            {
                "fixture_initialization": prepared_file(
                    "evals/fixtures/example/mockserverInitialization.json"
                )
            },
            {"capture_outputs": True},
        ):
            with self.subTest(restricted=restricted):
                with self.assertRaisesRegex(ValueError, "judge.*(?:fixture|output)"):
                    HarnessRequest(
                        role="judge",
                        run_variant="semantic_grade",
                        prompt="Grade the evidence.",
                        timeout_seconds=30,
                        **restricted,
                    )

    def test_only_judges_may_receive_a_structured_response_schema(self):
        schema = {"type": "object"}
        judge = HarnessRequest(
            role="judge",
            run_variant="semantic_grade",
            prompt="Grade the evidence.",
            timeout_seconds=30,
            response_schema=schema,
        )

        self.assertIs(judge.response_schema, schema)
        with self.assertRaisesRegex(ValueError, "actor.*response schema"):
            HarnessRequest(
                role="actor",
                run_variant="candidate",
                prompt="Perform the case.",
                timeout_seconds=30,
                response_schema=schema,
            )
        with self.assertRaisesRegex(ValueError, "response_schema"):
            HarnessRequest(
                role="judge",
                run_variant="semantic_grade",
                prompt="Grade the evidence.",
                timeout_seconds=30,
                response_schema="not-a-schema",  # type: ignore[arg-type]
            )

    def test_actor_input_contract_rejects_judges_and_unsafe_destinations(self):
        actor_input = ActorInput(
            prepared=prepared_file(
                "evals/fixtures/example/inputs/request.md"
            ),
            destination=PurePosixPath("request.md"),
        )
        with self.assertRaisesRegex(ValueError, "judge.*input"):
            HarnessRequest(
                role="judge",
                run_variant="semantic_grade",
                prompt="Grade the evidence.",
                timeout_seconds=30,
                actor_inputs=(actor_input,),
            )
        for destination in (
            PurePosixPath("../escape"),
            PurePosixPath("/absolute"),
            PurePosixPath("."),
        ):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(ValueError, "actor input"):
                    ActorInput(
                        prepared=prepared_file(),
                        destination=destination,
                    )

        with self.assertRaisesRegex(ValueError, "actor input destinations"):
            HarnessRequest(
                role="actor",
                run_variant="fixture",
                prompt="Use the inputs.",
                timeout_seconds=30,
                actor_inputs=(actor_input, actor_input),
            )

    def test_actor_fixture_material_requires_an_exact_case_fixture_root(self):
        actor_input = ActorInput(
            prepared=prepared_file(
                "evals/fixtures/example/inputs/request.md"
            ),
            destination=PurePosixPath("request.md"),
        )
        for fixture_fields in (
            {"actor_inputs": (actor_input,)},
            {
                "fixture_initialization": prepared_file(
                    "evals/fixtures/example/mockserverInitialization.json"
                )
            },
        ):
            with self.subTest(fixture_fields=fixture_fields):
                with self.assertRaisesRegex(ValueError, "fixture root"):
                    HarnessRequest(
                        role="actor",
                        run_variant="fixture",
                        prompt="Use the fixture.",
                        timeout_seconds=30,
                        **fixture_fields,
                    )

    def test_request_rejects_unsafe_duplicate_or_judge_shell_environment(self):
        invalid = (
            (("BAD-NAME", "value"),),
            (("HTTPS_PROXY", "one"), ("HTTPS_PROXY", "two")),
            (("HTTPS_PROXY", "value\x00"),),
            (("HOME", "/escape"),),
        )
        for shell_environment in invalid:
            with self.subTest(shell_environment=shell_environment):
                with self.assertRaisesRegex(ValueError, "shell environment"):
                    HarnessRequest(
                        role="actor",
                        run_variant="fixture",
                        prompt="Call the fixture API.",
                        timeout_seconds=60,
                        shell_environment=shell_environment,
                    )

        with self.assertRaisesRegex(ValueError, "judge.*shell environment"):
            HarnessRequest(
                role="judge",
                run_variant="semantic_grade",
                prompt="Grade the evidence.",
                timeout_seconds=30,
                shell_environment=(("HTTPS_PROXY", "http://127.0.0.1:1080"),),
            )

    def test_adapter_protocol_exposes_preflight_and_normalized_execution(self):
        adapter = RecordingHarness()
        request = HarnessRequest(
            role="judge",
            run_variant="semantic_grade",
            prompt="Grade the provided evidence.",
            timeout_seconds=30,
        )

        self.assertIsInstance(adapter, HarnessAdapter)
        self.assertTrue(adapter.preflight().available)
        with tempfile.TemporaryDirectory() as directory:
            execution = adapter.execute(request, Path(directory))

        self.assertEqual(execution.response, "normalized response")
        self.assertEqual(execution.total_tokens, 12)
        self.assertEqual(execution.successful_skill_reads[0].name, "SKILL.md")
        self.assertIsNone(execution.failure)
        with self.assertRaises(FrozenInstanceError):
            execution.exit_code = 2


if __name__ == "__main__":
    unittest.main()
