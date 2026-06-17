#!/usr/bin/env python3
"""Run skill trigger scenarios against an installed agent harness."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from trigger_scenarios import load_scenarios


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCENARIOS_PATH = SCRIPT_DIR / "scenarios.toml"
sys.path.append(str(REPO_ROOT / "tests"))

from semantic_judge import (  # noqa: E402
    SemanticCriterion,
    assert_forbidden_terms,
    judge_response,
    resolve_judge_command,
    run_command,
)
from behavioral_harness import CAPABILITY_ACCOUNTING_INSTRUCTIONS  # noqa: E402


def main() -> int:
    agent_command = os.environ.get("SKILL_TRIGGER_AGENT_COMMAND", "").strip()
    scenario_filter = os.environ.get("SKILL_TRIGGER_SCENARIO", "").strip()

    if "--help" in sys.argv:
        print_usage()
        return 0

    if not agent_command:
        print_usage()
        print("FAIL: SKILL_TRIGGER_AGENT_COMMAND is required for behavioral pressure tests", file=sys.stderr)
        return 1

    try:
        all_scenarios = load_scenarios(SCENARIOS_PATH)
        scenarios = [
            scenario for scenario in all_scenarios if not scenario_filter or scenario["id"] == scenario_filter
        ]
        if not scenarios:
            raise ValueError("no behavioral scenarios matched")

        judge_command = resolve_judge_command(agent_command)
        for scenario in scenarios:
            run_scenario(agent_command, judge_command, scenario)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(scenarios)} behavioral skill trigger scenarios", flush=True)
    return 0


def print_usage() -> None:
    print(
        """Usage:
  SKILL_TRIGGER_AGENT_COMMAND='<command reading stdin>' python3 tests/skill-trigger/behavioral_pressure.py

Optional:
  SKILL_TRIGGER_SCENARIO='<scenario-id>' to run one scenario.

The agent command receives only the scenario user request plus an output format
on stdin and must print its response on stdout. The harness must rely on its
installed skill discovery; this test does not inject skill bodies or skill indexes.
The response must include the expected skill name from the scenario registry."""
    )


def run_scenario(agent_command: str, judge_command: str, scenario: dict[str, object]) -> None:
    scenario_id = str(scenario["id"])
    skill = str(scenario["skill"])
    should_trigger = bool(scenario.get("should_trigger", True))
    prompt = make_prompt(scenario)
    response = run_agent(agent_command, prompt)
    selected = selected_skills(response)

    if should_trigger and skill not in selected:
        print(f"Response for {scenario_id}:\n{response}", file=sys.stderr)
        raise ValueError(f"{scenario_id} did not select expected skill: {skill}")
    if not should_trigger and skill in selected:
        print(f"Response for {scenario_id}:\n{response}", file=sys.stderr)
        raise ValueError(f"{scenario_id} selected skill that should not trigger: {skill}")

    try:
        assert_forbidden_terms(
            response,
            tuple(str(term) for term in scenario["response_forbidden_terms"]),
            scenario_id,
        )
        judge_response(
            judge_command=judge_command,
            scenario_id=scenario_id,
            scenario_prompt=str(scenario["prompt"]),
            response=response,
            criteria=semantic_criteria(skill, should_trigger),
            context=semantic_context(skill, should_trigger),
        )
    except AssertionError as error:
        print(f"Response for {scenario_id}:\n{response}", file=sys.stderr)
        raise ValueError(f"{scenario_id} failed semantic trigger judgment: {error}") from error

    action = "selected" if should_trigger else "did not select"
    print(f"PASS: {scenario_id} {action} {skill}", flush=True)


def semantic_criteria(skill: str, should_trigger: bool) -> tuple[SemanticCriterion, ...]:
    if should_trigger:
        expected = (
            f"The response includes {skill} because it is relevant to the user "
            "request before any task work begins. Extra selected skills are "
            "acceptable unless they match the scenario's forbidden terms."
        )
    else:
        expected = (
            f"The response does not include {skill} because the user request is "
            "outside that skill's trigger boundary. Other selected skills are "
            "acceptable unless they match the scenario's forbidden terms."
        )

    return (
        SemanticCriterion("expected_skill_boundary", expected),
        SemanticCriterion(
            "selection_is_from_prompt",
            "The rationale is grounded in the user request and the relevant trigger boundary; it does not rely on an injected skill list or perform the task.",
        ),
        SemanticCriterion(
            "does_not_perform_task",
            "The response only reports selected skills and a short rationale; it does not start executing the user request.",
        ),
    )


def semantic_context(skill: str, should_trigger: bool) -> str:
    requirement = "is selected" if should_trigger else "is not selected"
    return (
        "This is an installed-harness black-box skill trigger test. "
        f"The deterministic requirement is that {skill} {requirement}; "
        "extra selected skills are allowed unless explicitly forbidden by the scenario."
    )


def selected_skills(response: str) -> set[str]:
    for line in response.splitlines():
        if not line.startswith("SELECTED_SKILLS:"):
            continue
        value = line.split(":", 1)[1].strip()
        if not value or value.lower() in {"none", "n/a", "no skills"}:
            return set()
        return {part.strip() for part in value.split(",") if part.strip()}
    return set()


def run_agent(agent_command: str, prompt: str) -> str:
    return run_command(agent_command, prompt, "agent")


def make_prompt(scenario: dict[str, object]) -> str:
    return f"""Select skills for this request and stop. Do not perform the task.
Select only skills whose trigger conditions are directly satisfied. It is valid
to select none. Do not choose a closest-fit skill just because the request names
a related domain, ticker, technology, artifact, or predecessor workflow. Respect
each skill's "do not use" and boundary language.

User request:
{scenario["prompt"]}

{CAPABILITY_ACCOUNTING_INSTRUCTIONS}

Return only this format:
SELECTED_SKILLS: comma-separated skill names
RATIONALE: one short sentence

Scenario id: {scenario["id"]}
"""


if __name__ == "__main__":
    raise SystemExit(main())
