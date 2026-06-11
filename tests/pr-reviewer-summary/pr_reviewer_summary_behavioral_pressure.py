#!/usr/bin/env python3
"""Behavioral pressure tests for pr-reviewer-summary."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "pr-reviewer-summary" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="pr-reviewer-summary",
        skill_name="pr-reviewer-summary",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="PR_REVIEWER_SUMMARY_AGENT_COMMAND",
        scenario_filter_env_var="PR_REVIEWER_SUMMARY_SCENARIO",
        prompt_instructions=(
            "Do not inspect a real diff. Return only the PR-body drafting workflow, "
            "required context, output sections, and blocker behavior."
        ),
        judge_context=(
            "Loaded skill under test: pr-reviewer-summary. Judge reviewer usefulness, "
            "final-state summarization, context requirements, and manual-testing quality."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
