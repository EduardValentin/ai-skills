#!/usr/bin/env python3
"""Behavioral pressure tests for qa-verification."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "qa-verification" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="qa-verification",
        skill_name="qa-verification",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="QA_VERIFICATION_AGENT_COMMAND",
        scenario_filter_env_var="QA_VERIFICATION_SCENARIO",
        prompt_instructions=(
            "Do not execute QA. Return only the QA approach and report shape "
            "the QA verifier should use. Keep it concise."
        ),
        judge_context=(
            "Loaded skill under test: qa-verification. Judge QA behavior, scope, "
            "and report boundaries. The pressure prompt asks for the approach/report "
            "shape only; do not require proof that QA was actually executed."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
