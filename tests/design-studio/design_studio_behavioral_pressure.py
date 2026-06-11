#!/usr/bin/env python3
"""Behavioral pressure tests for design-studio."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "design-studio" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="design-studio",
        skill_name="design-studio",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="DESIGN_STUDIO_AGENT_COMMAND",
        scenario_filter_env_var="DESIGN_STUDIO_SCENARIO",
        prompt_instructions=(
            "Do not inspect files or implement UI. Return only the next workflow action "
            "and context-discipline behavior the design-studio agent should follow."
        ),
        judge_context=(
            "Loaded skill under test: design-studio. Judge context isolation, reference-app "
            "workflow discipline, and PRD/design audit behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
