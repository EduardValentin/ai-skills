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


def assert_no_implementation_worker_handoff(response: str) -> None:
    for line in response.splitlines():
        normalized = line.casefold()
        if not normalized.lstrip().startswith("action:"):
            continue
        if (
            "dispatch_request" in normalized
            and "implementation worker" in normalized
            and not is_negated_worker_reference(normalized)
        ):
            raise AssertionError("first-level handoff must not be an implementation-worker prompt")


def is_negated_worker_reference(line: str) -> bool:
    return any(
        phrase in line
        for phrase in (
            "not an implementation worker",
            "not implementation worker",
            "not an implementation-worker",
            "not implementation-worker",
            "rather than an implementation worker",
            "instead of an implementation worker",
        )
    )


def main() -> int:
    return run_workflow_dispatch_suite(
        suite_name="multi-ticket-work workflow dispatch scenarios",
        parent_skill_name="multi-ticket-work",
        skill_path=SKILL_PATH,
        scenarios=load_workflow_scenarios(
            SCENARIOS_PATH,
            response_checks={
                "no_implementation_worker_handoff": assert_no_implementation_worker_handoff,
            },
        ),
        scenario_filter_env_var="MULTI_TICKET_WORK_WORKFLOW_DISPATCH_SCENARIO",
    )


if __name__ == "__main__":
    raise SystemExit(main())
