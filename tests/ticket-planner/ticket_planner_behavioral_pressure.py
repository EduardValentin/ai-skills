#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-planner."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-planner" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="ticket-planner",
        skill_name="ticket-planner",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="TICKET_PLANNER_AGENT_COMMAND",
        scenario_filter_env_var="TICKET_PLANNER_SCENARIO",
        prompt_instructions=(
            "Do not create tracker issues or edit PRD.md. Return only the planning "
            "workflow, questions, story-slicing behavior, and approval gates."
        ),
        judge_context=(
            "Loaded skill under test: ticket-planner. Judge product planning, "
            "prototype boundaries, vertical slicing, PRD update gates, and tracker neutrality."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
