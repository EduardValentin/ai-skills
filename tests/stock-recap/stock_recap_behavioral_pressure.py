#!/usr/bin/env python3
"""Behavioral pressure tests for stock-recap."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "stock-recap" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="stock-recap",
        skill_name="stock-recap",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="STOCK_RECAP_AGENT_COMMAND",
        scenario_filter_env_var="STOCK_RECAP_SCENARIO",
        prompt_instructions=(
            "Do not fetch market data or write research files. Return only the recap "
            "workflow, gates, mode routing, checkpoint behavior, and blocker handling."
        ),
        judge_context=(
            "Loaded skill under test: stock-recap. Judge prerequisite gates, mode routing, "
            "filing/valuation flow, sell-trigger evaluation, and update checkpoints."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
