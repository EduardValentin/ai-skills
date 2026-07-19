from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest

from scripts.ai_skills_lib.harness import (
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
