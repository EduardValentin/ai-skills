#!/usr/bin/env python3
"""Contract checks for the workflow-dispatch behavioral harness."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "tests"))
sys.path.append(str(REPO_ROOT / "tests" / "workflow-dispatch"))

from harness import (  # noqa: E402
    WorkflowDispatchScenario,
    build_workflow_prompt,
    require_action_lines,
)
from semantic_judge import SemanticCriterion  # noqa: E402


def main() -> int:
    try:
        check_workflow_harness_contract()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: workflow-dispatch harness contract")
    return 0


def check_workflow_harness_contract() -> None:
    scenario = WorkflowDispatchScenario(
        scenario_id="dispatch-demo",
        user_request="Route this parent workflow.",
        criteria=(SemanticCriterion("delegates", "The response delegates work."),),
        prompt_instructions="Return ACTION lines only.",
        forbidden_terms=("inline implementation",),
        expected_auto_discovery=("demo-skill",),
        require_action_ledger=True,
        first_action_contains=("map_scope",),
    )

    prompt = build_workflow_prompt(
        parent_skill_name="ticket-start",
        skill_text="PARENT SKILL BODY",
        scenario=scenario,
    )

    for expected in (
        "Loaded skill: ticket-start",
        "PARENT SKILL BODY",
        "Route this parent workflow.",
        "Return ACTION lines only.",
    ):
        assert_contains(prompt, expected)

    require_action_lines(
        "ACTION: 1 | MAP_SCOPE | ticket | details\nACTION: 2 | REPORT | ticket | done",
        first_action_contains=("map_scope",),
        required_action_contains=(("report",),),
    )

    try:
        require_action_lines("No actions here", first_action_contains=("map_scope",))
    except AssertionError as error:
        assert_contains(str(error), "missing ACTION lines")
    else:
        raise AssertionError("require_action_lines should reject responses without ACTION rows")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
