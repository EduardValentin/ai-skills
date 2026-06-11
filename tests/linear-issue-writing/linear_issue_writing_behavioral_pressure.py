#!/usr/bin/env python3
"""Behavioral pressure tests for linear-issue-writing."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "linear-issue-writing" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="linear-issue-writing",
        skill_name="linear-issue-writing",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="LINEAR_ISSUE_WRITING_AGENT_COMMAND",
        scenario_filter_env_var="LINEAR_ISSUE_WRITING_SCENARIO",
        prompt_instructions=(
            "Do not call Linear. Return only the publishing workflow, gates, "
            "questions, and report behavior the Linear issue-writing agent should use."
        ),
        judge_context=(
            "Loaded skill under test: linear-issue-writing. Judge Linear modeling, "
            "approval gates, duplicate detection, and integration fallback behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
