#!/usr/bin/env python3
"""Behavioral pressure tests for manage-bitbucket-pr."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "manage-bitbucket-pr" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="manage-bitbucket-pr",
        skill_name="manage-bitbucket-pr",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="MANAGE_BITBUCKET_PR_AGENT_COMMAND",
        scenario_filter_env_var="MANAGE_BITBUCKET_PR_SCENARIO",
        prompt_instructions=(
            "Do not call Bitbucket. Return only the workflow, safety gates, commands or "
            "API path choices, and report behavior the Bitbucket PR agent should use."
        ),
        judge_context=(
            "Loaded skill under test: manage-bitbucket-pr. Judge host detection, "
            "read-before-write, auth fallback, mutation safety, and PR metadata behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
