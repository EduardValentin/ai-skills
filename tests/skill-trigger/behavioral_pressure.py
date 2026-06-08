#!/usr/bin/env python3
"""Run skill trigger scenarios against an installed agent harness."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from trigger_scenarios import load_scenarios


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCENARIOS_PATH = SCRIPT_DIR / "scenarios.toml"


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

        for scenario in scenarios:
            run_scenario(agent_command, scenario)
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


def run_scenario(agent_command: str, scenario: dict[str, object]) -> None:
    scenario_id = str(scenario["id"])
    skill = str(scenario["skill"])
    prompt = make_prompt(scenario)
    response = run_agent(agent_command, prompt)

    if skill not in response:
        print(f"Response for {scenario_id}:\n{response}", file=sys.stderr)
        raise ValueError(f"{scenario_id} did not select expected skill: {skill}")

    for term in scenario["response_forbidden_terms"]:
        term_text = str(term)
        if term_text and term_text in response:
            print(f"Response for {scenario_id}:\n{response}", file=sys.stderr)
            raise ValueError(f"{scenario_id} repeated forbidden rationalization term: {term_text}")

    print(f"PASS: {scenario_id} selected {skill}", flush=True)


def run_agent(agent_command: str, prompt: str) -> str:
    completed = subprocess.run(
        shlex.split(agent_command),
        input=prompt,
        text=True,
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "agent command failed with exit code "
            f"{completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed.stdout


def make_prompt(scenario: dict[str, object]) -> str:
    return f"""You are testing installed black-box skill discovery before any task work begins.

User request:
{scenario["prompt"]}

Return only this format:
SELECTED_SKILLS: comma-separated skill names
RATIONALE: one short sentence

Select every skill that should be loaded before acting. Do not perform the user request.
Scenario id: {scenario["id"]}
"""


if __name__ == "__main__":
    raise SystemExit(main())
