from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from scripts.ai_skills_lib.codex_harness import (
    CodexHarnessAdapter,
    prepare_actor_skill_source,
)
from scripts.ai_skills_lib.harness import HarnessRequest, bind_harness_request
from scripts.ai_skills_lib.sandbox_runtime import (
    EvalRuntimeManifest,
    SandboxRuntime,
    SubprocessRunner,
)
from tests.integration.eval_runtime.support import prepare_artifact_binding


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUN_REAL_INTEGRATION = os.environ.get("AI_SKILLS_RUN_MODEL_INTEGRATION") == "1"


@unittest.skipUnless(
    RUN_REAL_INTEGRATION,
    "requires explicit AI_SKILLS_RUN_MODEL_INTEGRATION=1 approval",
)
class DockerSandboxesSmokeTests(unittest.TestCase):
    def test_reuses_isolated_actor_and_judge_workers_then_cleans_up(self) -> None:
        manifest = EvalRuntimeManifest.load(REPOSITORY_ROOT / "config" / "eval-runtime.json")
        invocation_id = f"smoke-{uuid.uuid4().hex[:10]}"
        with tempfile.TemporaryDirectory(prefix="ai-skills-sandbox-smoke-") as directory:
            state = Path(directory)
            skills_root = state / "skills"
            skill = skills_root / "sandbox-smoke"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                """---
name: sandbox-smoke
description: Use when asked to confirm the isolated sandbox runtime marker.
---

# Sandbox Smoke

When asked to confirm the isolated sandbox runtime marker, reply exactly
`WITH_SKILL_CONFIRMED`.
""",
                encoding="utf-8",
            )
            runtime = SandboxRuntime(
                manifest=manifest,
                process=SubprocessRunner(manifest.limits.maximum_captured_output_bytes),
                repository_root=REPOSITORY_ROOT,
                results_root=state / "results",
                staging_root=state / "workers",
                invocation_id=invocation_id,
                max_concurrency=1,
            )
            adapter = CodexHarnessAdapter(runtime, allowed_skill_root=skills_root)
            prepared_skill = prepare_actor_skill_source(skill)
            try:
                capabilities = adapter.preflight()
                self.assertTrue(capabilities.available, capabilities.failure)
                self.assertIsNotNone(capabilities.actor_model)
                self.assertIsNotNone(capabilities.actor_reasoning_effort)
                self.assertIsNotNone(capabilities.judge_model)
                self.assertIsNotNone(capabilities.judge_reasoning_effort)
                actor_before = runtime.acquire_worker("actor")
                binding_invocation_id = uuid.uuid4().hex
                prompt = (
                    "Create runtime-marker.txt containing exactly CAPTURE_CONFIRMED. "
                    "Then confirm the isolated sandbox runtime marker. "
                    "If no relevant skill is available, reply WITHOUT_SKILL."
                )
                with_skill_root = state / "results" / "with-skill"
                without_skill_root = state / "results" / "without-skill"
                with_skill_request = bind_harness_request(
                    HarnessRequest(
                        role="actor",
                        run_variant="with-skill",
                        prompt=prompt,
                        timeout_seconds=manifest.limits.actor_timeout_seconds,
                        skill_sources=(prepared_skill,),
                        expected_skill="sandbox-smoke",
                        model=capabilities.actor_model,
                        reasoning_effort=capabilities.actor_reasoning_effort,
                        capture_outputs=True,
                        artifact_binding=prepare_artifact_binding(
                            with_skill_root,
                            REPOSITORY_ROOT,
                        ),
                    ),
                    invocation_id=binding_invocation_id,
                    run_id="with-skill",
                )
                without_skill_request = bind_harness_request(
                    HarnessRequest(
                        role="actor",
                        run_variant="without-skill",
                        prompt=prompt,
                        timeout_seconds=manifest.limits.actor_timeout_seconds,
                        model=capabilities.actor_model,
                        reasoning_effort=capabilities.actor_reasoning_effort,
                        capture_outputs=True,
                        artifact_binding=prepare_artifact_binding(
                            without_skill_root,
                            REPOSITORY_ROOT,
                        ),
                    ),
                    invocation_id=binding_invocation_id,
                    run_id="without-skill",
                )

                with_skill = adapter.execute(
                    with_skill_request,
                    with_skill_root,
                )
                without_skill = adapter.execute(
                    without_skill_request,
                    without_skill_root,
                )
                actor_after = runtime.acquire_worker("actor")

                for execution in (with_skill, without_skill):
                    self.assertIsNone(execution.failure)
                    self.assertFalse(execution.timed_out)
                    self.assertEqual(execution.exit_code, 0)
                self.assertEqual(actor_before.id, actor_after.id)
                self.assertEqual(with_skill.response.strip(), "WITH_SKILL_CONFIRMED")
                self.assertEqual(without_skill.response.strip(), "WITHOUT_SKILL")
                self.assertEqual(len(with_skill.successful_skill_reads), 1)
                self.assertEqual(without_skill.successful_skill_reads, ())
                self.assertFalse(with_skill.successful_skill_reads[0].exists())
                self.assertEqual(
                    (with_skill_root / "outputs" / "runtime-marker.txt").read_text(
                        encoding="utf-8"
                    ),
                    "CAPTURE_CONFIRMED",
                )
                self.assertEqual(
                    (without_skill_root / "outputs" / "runtime-marker.txt").read_text(
                        encoding="utf-8"
                    ),
                    "CAPTURE_CONFIRMED",
                )

                judge_prompt = json.dumps(
                    {
                        "instruction": (
                            "Return {\"verdict\":\"PASS\"} only when the with-skill "
                            "run used the marker and the without-skill run did not "
                            "claim that marker."
                        ),
                        "with_skill": with_skill.response,
                        "without_skill": without_skill.response,
                    }
                )
                judge_request = bind_harness_request(
                    HarnessRequest(
                        role="judge",
                        run_variant="judge",
                        prompt=judge_prompt,
                        timeout_seconds=manifest.limits.judge_timeout_seconds,
                        model=capabilities.judge_model,
                        reasoning_effort=capabilities.judge_reasoning_effort,
                        response_schema={
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["verdict"],
                            "properties": {
                                "verdict": {"const": "PASS"},
                            },
                        },
                    ),
                    invocation_id=binding_invocation_id,
                    run_id="judge",
                )
                judge = adapter.execute(
                    judge_request,
                    state / "results" / "judge",
                )
                judge_worker = runtime.acquire_worker("judge")
                self.assertIsNone(judge.failure)
                self.assertFalse(judge.timed_out)
                self.assertEqual(judge.exit_code, 0)
                self.assertNotEqual(actor_after.id, judge_worker.id)
                self.assertEqual(
                    json.loads(judge.response),
                    {"verdict": "PASS"},
                )
                self.assertFalse((judge_worker.host_root / "case" / "codex-home" / "skills" / "sandbox-smoke").exists())
            finally:
                runtime.close()
            self.assertTrue(runtime.sandbox_cleanup_completed)


if __name__ == "__main__":
    unittest.main()
