from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from scripts.ai_skills_lib.codex_harness import CodexHarnessAdapter
from scripts.ai_skills_lib.harness import HarnessRequest
from scripts.ai_skills_lib.sandbox_runtime import (
    EvalRuntimeManifest,
    SandboxRuntime,
    SubprocessRunner,
)


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
            try:
                capabilities = adapter.preflight()
                self.assertTrue(capabilities.available, capabilities.failure)
                actor_before = runtime.acquire_worker("actor")

                prompt = (
                    "Confirm the isolated sandbox runtime marker. "
                    "If no relevant skill is available, reply WITHOUT_SKILL."
                )
                with_skill = adapter.execute(
                    HarnessRequest(
                        role="actor",
                        run_variant="with-skill",
                        prompt=prompt,
                        timeout_seconds=manifest.limits.actor_timeout_seconds,
                        skill_sources=(skill,),
                        expected_skill="sandbox-smoke",
                    ),
                    state / "results" / "with-skill",
                )
                without_skill = adapter.execute(
                    HarnessRequest(
                        role="actor",
                        run_variant="without-skill",
                        prompt=prompt,
                        timeout_seconds=manifest.limits.actor_timeout_seconds,
                    ),
                    state / "results" / "without-skill",
                )
                actor_after = runtime.acquire_worker("actor")

                self.assertEqual(actor_before.id, actor_after.id)
                self.assertIn("WITH_SKILL_CONFIRMED", with_skill.response)
                self.assertEqual(len(with_skill.successful_skill_reads), 1)
                self.assertEqual(without_skill.successful_skill_reads, ())
                self.assertFalse(with_skill.successful_skill_reads[0].exists())

                judge_prompt = json.dumps(
                    {
                        "instruction": (
                            "Reply PASS only when the with-skill run used the marker and the "
                            "without-skill run did not claim that marker."
                        ),
                        "with_skill": with_skill.response,
                        "without_skill": without_skill.response,
                    }
                )
                judge = adapter.execute(
                    HarnessRequest(
                        role="judge",
                        run_variant="judge",
                        prompt=judge_prompt,
                        timeout_seconds=manifest.limits.judge_timeout_seconds,
                    ),
                    state / "results" / "judge",
                )
                judge_worker = runtime.acquire_worker("judge")
                self.assertNotEqual(actor_after.id, judge_worker.id)
                self.assertIn("PASS", judge.response)
                self.assertFalse((judge_worker.host_root / "case" / "codex-home" / "skills" / "sandbox-smoke").exists())
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
