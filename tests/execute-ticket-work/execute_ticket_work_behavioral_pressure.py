#!/usr/bin/env python3
"""Behavioral pressure tests for execute-ticket-work."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "execute-ticket-work" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="execute-ticket-work",
        skill_name="execute-ticket-work",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="EXECUTE_TICKET_WORK_AGENT_COMMAND",
        scenario_filter_env_var="EXECUTE_TICKET_WORK_SCENARIO",
        prompt_instructions=(
            "Do not perform real execution. Return the execution-phase behavior and report expectations only. "
            "Explicitly describe how nested delegated subagents are used, or how the limitation is reported if unavailable. "
            "Keep it concise and do not name downstream skill identifiers."
        ),
        judge_context="Loaded skill under test: execute-ticket-work. Judge execution-phase boundaries, not exact wording.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
