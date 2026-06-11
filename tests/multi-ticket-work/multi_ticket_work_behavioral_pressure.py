#!/usr/bin/env python3
"""Behavioral pressure tests for multi-ticket work orchestration.

Requires MULTI_TICKET_WORK_AGENT_COMMAND to name a command that reads a prompt
from stdin and writes the agent response to stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="multi-ticket-work",
        skill_name="multi-ticket-work",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="MULTI_TICKET_WORK_AGENT_COMMAND",
        scenario_filter_env_var="MULTI_TICKET_WORK_SCENARIO",
        prompt_instructions=(
            "Do not execute the work. Return a concise orchestration plan only. It must explain:\n"
            "- how the full ticket scope is gathered,\n"
            "- where durable orchestration notes are saved and when they are re-read,\n"
            "- how sequencing and parallel work are decided,\n"
            "- how cross-ticket alignment, spec, plan, and user approval happen before dispatch,\n"
            "- how approved execution packets are prepared,\n"
            "- how first-level ticket coordinator subagents are assigned and what they must not do,\n"
            "- how ticket coordinators dispatch deeper implementation, review, QA, UI/UX, fix, and PR-preparation work,\n"
            "- what makes each ticket or unit complete,\n"
            "- what appears in the final PR review report.\n"
            "Do not name downstream skill identifiers or unrelated skills."
        ),
        judge_context="Loaded skill under test: multi-ticket-work. Judge orchestration behavior, not exact wording.",
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
