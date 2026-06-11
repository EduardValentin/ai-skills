#!/usr/bin/env python3
"""Behavioral workflow-dispatch scenarios for multi-ticket-work."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(REPO_ROOT / "tests"))

from harness import load_workflow_scenarios, run_workflow_dispatch_suite  # noqa: E402


def assert_no_ticket_orchestrator_handoff(response: str) -> None:
    for line in response.splitlines():
        normalized = line.casefold()
        if not normalized.lstrip().startswith("action:"):
            continue
        if "dispatch_request" in normalized and "ticket orchestrator" in normalized:
            raise AssertionError("first-level handoff must be an approved execution-packet request")


def main() -> int:
    return run_workflow_dispatch_suite(
        suite_name="multi-ticket-work workflow dispatch scenarios",
        parent_skill_name="multi-ticket-work",
        skill_path=SKILL_PATH,
        scenarios=load_workflow_scenarios(
            SCENARIOS_PATH,
            response_checks={
                "no_ticket_orchestrator_handoff": assert_no_ticket_orchestrator_handoff,
            },
        ),
        scenario_filter_env_var="MULTI_TICKET_WORK_WORKFLOW_DISPATCH_SCENARIO",
    )


if __name__ == "__main__":
    raise SystemExit(main())
