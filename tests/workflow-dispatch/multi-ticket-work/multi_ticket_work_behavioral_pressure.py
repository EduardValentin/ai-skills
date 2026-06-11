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

from harness import action_lines, load_workflow_scenarios, run_workflow_dispatch_suite  # noqa: E402


def assert_ticket_coordinator_handoff(response: str) -> None:
    dispatch_lines = []
    for line in action_lines(response):
        normalized = line.casefold()
        if "dispatch_request" in normalized:
            dispatch_lines.append(normalized)

    if not dispatch_lines:
        raise AssertionError("ticket coordinator dispatch request is required")

    first_dispatch = dispatch_lines[0]
    missing = [
        term
        for term in ("ticket coordinator", "approved execution packet")
        if term not in first_dispatch
    ]
    if missing:
        raise AssertionError(f"ticket coordinator handoff missing terms: {missing}")

    deeper_terms = ("implementation", "review", "qa")
    if not all(term in first_dispatch for term in deeper_terms):
        raise AssertionError("ticket coordinator handoff must mention deeper implementation, review, and QA coordination")


def main() -> int:
    return run_workflow_dispatch_suite(
        suite_name="multi-ticket-work workflow dispatch scenarios",
        parent_skill_name="multi-ticket-work",
        skill_path=SKILL_PATH,
        scenarios=load_workflow_scenarios(
            SCENARIOS_PATH,
            response_checks={
                "ticket_coordinator_handoff": assert_ticket_coordinator_handoff,
            },
        ),
        scenario_filter_env_var="MULTI_TICKET_WORK_WORKFLOW_DISPATCH_SCENARIO",
    )


if __name__ == "__main__":
    raise SystemExit(main())
