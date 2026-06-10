#!/usr/bin/env python3
"""Contract checks for the shared behavioral pressure harness."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import (  # noqa: E402
    BehavioralScenario,
    build_loaded_skill_prompt,
    select_scenarios,
)
from semantic_judge import SemanticCriterion  # noqa: E402


def main() -> int:
    try:
        check_behavioral_harness_contract()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: behavioral harness contract")
    return 0


def check_behavioral_harness_contract() -> None:
    scenario = BehavioralScenario(
        scenario_id="demo-scenario",
        user_request="Use the loaded demo skill.",
        criteria=(SemanticCriterion("does_demo", "The response does the demo behavior."),),
        forbidden_terms=("forbidden",),
    )

    prompt = build_loaded_skill_prompt(
        skill_name="demo",
        skill_text="DEMO SKILL BODY",
        scenario=scenario,
        prompt_instructions="Return the demo response shape.",
    )

    for expected in (
        "Loaded skill: demo",
        "<skill>",
        "DEMO SKILL BODY",
        "Use the loaded demo skill.",
        "Return the demo response shape.",
    ):
        assert_contains(prompt, expected)

    selected = select_scenarios((scenario,), "demo-scenario")
    if selected != (scenario,):
        raise AssertionError("select_scenarios should return the matching scenario tuple")

    if select_scenarios((scenario,), "") != (scenario,):
        raise AssertionError("select_scenarios should return all scenarios when no filter is set")

    try:
        select_scenarios((scenario,), "missing")
    except ValueError as error:
        assert_contains(str(error), "missing")
    else:
        raise AssertionError("select_scenarios should reject unknown scenario filters")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
