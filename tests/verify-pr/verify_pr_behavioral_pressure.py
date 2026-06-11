#!/usr/bin/env python3
"""Behavioral pressure tests for verify-pr."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "verify-pr" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="verify-pr",
        skill_name="verify-pr",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="VERIFY_PR_AGENT_COMMAND",
        scenario_filter_env_var="VERIFY_PR_SCENARIO",
        prompt_instructions=(
            "Do not perform external mutations. If metadata is missing and no tool calls are\n"
            "available in this pressure test, describe the mandatory fetch sequence before a\n"
            "readiness verdict instead of treating omitted state as final unknown state. If\n"
            "the scenario gives concrete current PR, ticket, CI, test, review, or comment\n"
            "state, treat those facts as already-fetched source metadata for the purpose of\n"
            "checking the gates. If gates pass, list the exact next action. Keep it concise."
        ),
        judge_context=(
            "Loaded skill under test: verify-pr. Judge source-of-truth metadata access, "
            "PR readiness gates, no-mutation boundaries, and post-merge monitoring behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
