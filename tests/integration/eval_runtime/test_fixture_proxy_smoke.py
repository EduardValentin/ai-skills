from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from scripts.ai_skills_lib.codex_harness import CodexHarnessAdapter
from scripts.ai_skills_lib.fixture_proxy import FixtureProxy, FixtureProxyError
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
class FixtureProxySmokeTests(unittest.TestCase):
    def test_intercepts_https_denies_control_and_reuses_worker_sidecar(self) -> None:
        manifest = EvalRuntimeManifest.load(REPOSITORY_ROOT / "config" / "eval-runtime.json")
        invocation_id = f"fixture-smoke-{uuid.uuid4().hex[:10]}"
        with tempfile.TemporaryDirectory(prefix="ai-skills-fixture-smoke-") as directory:
            state = Path(directory)
            skills_root = state / "skills"
            fixture_root = (
                skills_root
                / "integrations"
                / "fixture-smoke"
                / "evals"
                / "fixtures"
                / "fixture-model-route"
            )
            fixture_root.mkdir(parents=True)
            fixture = fixture_root / "mockserverInitialization.json"
            fixture.write_text(
                json.dumps(
                    [
                        {
                            "id": "fixture-ping",
                            "httpRequest": {
                                "method": "GET",
                                "path": "/v1/ping",
                                "headers": {"Host": ["api.example.test"]},
                            },
                            "httpResponse": {
                                "statusCode": 200,
                                "headers": {"Content-Type": ["application/json"]},
                                "body": {"fixture": "fixture-ok"},
                            },
                        }
                    ]
                ),
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
            proxy = FixtureProxy(
                runtime,
                repository_root=REPOSITORY_ROOT,
                allowed_fixture_root=fixture_root,
            )
            adapter = CodexHarnessAdapter(
                runtime,
                allowed_skill_root=skills_root,
                fixture_proxy=proxy,
            )
            try:
                capabilities = adapter.preflight(require_fixtures=True)
                self.assertTrue(capabilities.available, capabilities.failure)
                worker = runtime.acquire_worker("actor")

                actor = adapter.execute(
                    HarnessRequest(
                        role="actor",
                        run_variant="fixture-model-route",
                        prompt=(
                            "Run curl once for https://api.example.test/v1/ping, inspect its JSON, "
                            "and report the fixture value."
                        ),
                        timeout_seconds=manifest.limits.actor_timeout_seconds,
                        fixture_root=fixture_root,
                        fixture_initialization=fixture,
                    ),
                    state / "results" / "fixture-model-route",
                )

                self.assertIn("fixture-ok", actor.response)
                fixture_events = [
                    event for event in actor.trace if event.get("event") == "fixture_request"
                ]
                self.assertEqual(len(fixture_events), 1)
                self.assertEqual(fixture_events[0].get("host"), "api.example.test")
                self.assertEqual(fixture_events[0].get("path"), "/v1/ping")
                self.assertEqual(worker.id, runtime.acquire_worker("actor").id)

                direct_case = runtime.prepare_case(worker, "fixture-boundary")
                session = proxy.prepare_case(worker, direct_case, fixture, fixture.parent)
                unauthenticated = runtime.execute(
                    worker,
                    direct_case,
                    (
                        "curl",
                        "--silent",
                        "--output",
                        "/dev/null",
                        "--write-out",
                        "%{http_code}",
                        "http://127.0.0.1:1080/mockserver/reset",
                    ),
                    timeout_seconds=manifest.limits.preflight_timeout_seconds,
                )
                self.assertEqual(unauthenticated.returncode, 0)
                self.assertIn(unauthenticated.stdout.strip(), {"401", "403"})

                unmatched = runtime.execute(
                    worker,
                    direct_case,
                    (
                        "curl",
                        "--silent",
                        "--show-error",
                        "--fail-with-body",
                        "https://unmatched.example.test/not-declared",
                    ),
                    timeout_seconds=manifest.limits.preflight_timeout_seconds,
                    environment=dict(session.shell_environment),
                )
                self.assertEqual(unmatched.returncode, 22)
                runtime.quiesce_case(worker, direct_case)
                with self.assertRaisesRegex(FixtureProxyError, "request sequence"):
                    proxy.collect_and_reset(worker, direct_case, session)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
