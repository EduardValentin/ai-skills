#!/usr/bin/env python3
"""Behavioral pressure tests for implement-unit-of-work."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "implement-unit-of-work" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="implement-unit-of-work",
        skill_name="implement-unit-of-work",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="IMPLEMENT_UNIT_AGENT_COMMAND",
        scenario_filter_env_var="IMPLEMENT_UNIT_SCENARIO",
        prompt_instructions=(
            "Do not perform real implementation. Return only the implementation approach "
            "and report behavior the implementer should use. Keep it concise."
        ),
        judge_context=(
            "Loaded skill under test: implement-unit-of-work. "
            "Judge implementation behavior and report boundaries."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
