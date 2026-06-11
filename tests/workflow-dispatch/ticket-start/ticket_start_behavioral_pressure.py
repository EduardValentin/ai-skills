#!/usr/bin/env python3
"""Behavioral workflow-dispatch scenarios for ticket-start."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(REPO_ROOT / "tests"))

from harness import load_workflow_scenarios, run_workflow_dispatch_suite  # noqa: E402


def assert_no_dispatch_request(response: str) -> None:
    for line in response.splitlines():
        normalized = line.casefold()
        if normalized.lstrip().startswith("action:") and "dispatch_request" in normalized:
            raise AssertionError("execution-phase handoff must use PHASE_CONTRACT, not DISPATCH_REQUEST")


def assert_scoping_before_local_mapping(response: str) -> None:
    scoping_index = first_index(response, "dispatch_request", "scoping")
    if scoping_index < 0:
        scoping_index = first_index(response, "dispatch_request", "scope")
    if scoping_index < 0:
        raise AssertionError("Scoping dispatch request action is required")

    prefix = response[:scoping_index].lower()
    local_scoping_markers = (
        "local scope map",
        "local scoping",
        "map the code",
        "map code",
        "codebase map",
        "scope map",
        "affected surfaces",
    )
    if any(marker in prefix for marker in local_scoping_markers):
        raise AssertionError("performed local scoping before Scoping dispatch")


def first_index(haystack: str, *needles: str) -> int:
    normalized_needles = tuple(needle.lower() for needle in needles)
    for line in haystack.splitlines():
        normalized_line = line.lower()
        if all(needle in normalized_line for needle in normalized_needles):
            return haystack.find(line)
    return -1


def main() -> int:
    return run_workflow_dispatch_suite(
        suite_name="ticket-start workflow dispatch scenarios",
        parent_skill_name="ticket-start",
        skill_path=SKILL_PATH,
        scenarios=load_workflow_scenarios(
            SCENARIOS_PATH,
            response_checks={
                "scoping_before_local_mapping": assert_scoping_before_local_mapping,
                "no_dispatch_request": assert_no_dispatch_request,
            },
        ),
        scenario_filter_env_var="TICKET_START_WORKFLOW_DISPATCH_SCENARIO",
    )


if __name__ == "__main__":
    raise SystemExit(main())
