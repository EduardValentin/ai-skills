#!/usr/bin/env python3
"""Behavioral pressure tests for declaratia-unica-romania."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "declaratia-unica-romania" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="declaratia-unica-romania",
        skill_name="declaratia-unica-romania",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="DECLARATIA_UNICA_AGENT_COMMAND",
        scenario_filter_env_var="DECLARATIA_UNICA_SCENARIO",
        prompt_instructions=(
            "Nu completa declaratia si nu scrie fisiere. Returneaza doar raspunsul "
            "corect de workflow/gate pentru scenariul dat, in romana, concis."
        ),
        judge_context=(
            "Loaded skill under test: declaratia-unica-romania. Judge fiscal-source "
            "discipline, hard gates, scenario isolation, and artifact isolation."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
