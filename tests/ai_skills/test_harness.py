from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path, PurePosixPath
import tempfile
import unittest

from scripts.ai_skills_lib.harness import (
    ActorInput,
    HarnessAdapter,
    HarnessCapabilities,
    HarnessExecution,
    HarnessRequest,
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
    def test_contract_records_are_frozen_and_keep_configured_model_defaults_unset(self):
        request = HarnessRequest(
            role="actor",
            run_variant="candidate",
            prompt="Perform the case.",
            skill_sources=(Path("skills/workflows/example"),),
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
            {"skill_sources": (Path("skills/workflows/example"),)},
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
        with self.assertRaisesRegex(ValueError, "judge.*fixture"):
            HarnessRequest(
                role="judge",
                run_variant="semantic_grade",
                prompt="Grade the evidence.",
                timeout_seconds=30,
                fixture_initialization=Path("evals/fixtures/example/mockserverInitialization.json"),
            )

    def test_actor_input_contract_rejects_judges_and_unsafe_destinations(self):
        actor_input = ActorInput(
            source=Path("evals/fixtures/example/inputs/request.md"),
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
                    ActorInput(source=Path("request.md"), destination=destination)

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
            source=Path("evals/fixtures/example/inputs/request.md"),
            destination=PurePosixPath("request.md"),
        )
        for fixture_fields in (
            {"actor_inputs": (actor_input,)},
            {
                "fixture_initialization": Path(
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
