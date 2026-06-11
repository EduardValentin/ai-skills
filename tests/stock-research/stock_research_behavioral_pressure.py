#!/usr/bin/env python3
"""Behavioral pressure tests for stock-research."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "stock-research" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="stock-research",
        skill_name="stock-research",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="STOCK_RESEARCH_AGENT_COMMAND",
        scenario_filter_env_var="STOCK_RESEARCH_SCENARIO",
        prompt_instructions=(
            "Do not fetch data or write research files. Return only the research workflow, "
            "gates, phases, checkpoint behavior, artifact expectations, and out-of-scope handling."
        ),
        judge_context=(
            "Loaded skill under test: stock-research. Judge fundamentals workflow, "
            "setup gates, structured user decisions, artifacts, and scope boundaries."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
