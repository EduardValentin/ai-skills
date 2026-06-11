#!/usr/bin/env python3
"""Behavioral pressure tests for ui-verification."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ui-verification" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="ui-verification",
        skill_name="ui-verification",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="UI_VERIFICATION_AGENT_COMMAND",
        scenario_filter_env_var="UI_VERIFICATION_SCENARIO",
        prompt_instructions=(
            "Do not launch a browser or inspect a real app. Return only the UI verification "
            "approach, evidence requirements, fallback behavior, and report verdict shape."
        ),
        judge_context=(
            "Loaded skill under test: ui-verification. Judge parity/consistency mode "
            "selection, inventory scoping, DOM evidence, fallback handling, and rerun behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
