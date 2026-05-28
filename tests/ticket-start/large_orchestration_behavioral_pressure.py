#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-start large orchestration.

Requires TICKET_START_BEHAVIOR_AGENT_COMMAND to name a command that reads a
prompt from stdin and writes the agent response to stdout.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_request: str
    required_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...]


SCENARIOS = (
    Scenario(
        scenario_id="large-feature-dispatch-and-reporting",
        user_request=(
            "Use ticket-start for a large Linear epic with an approved plan. "
            "The plan has four slices: database migration, backend API, onboarding UI, "
            "and analytics events. The API and UI can run after the migration, analytics "
            "can run in parallel with UI, and the UI needs browser verification after integration. "
            "Describe the orchestration handoffs you would dispatch."
        ),
        required_terms=(
            "Active task:",
            "Depth budget:",
            "IMPLEMENTATION_SLICE_RESULT",
            "BROWSER_VERIFICATION_RESULT",
            "database migration",
            "backend API",
            "onboarding UI",
            "analytics events",
            "root",
            "leaf",
            "no child or grandchild agents may remain live",
        ),
        forbidden_terms=(
            "I would implement inline",
            "The implementer dispatches browser verifier",
            "grandchild owns a feature slice",
            "skip the orchestration map",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("TICKET_START_BEHAVIOR_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: TICKET_START_BEHAVIOR_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("TICKET_START_BEHAVIOR_SCENARIO", "").strip()
    scenarios = [scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter]
    if not scenarios:
        print(f"FAIL: no scenario matched {scenario_filter!r}", file=sys.stderr)
        return 1

    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    for scenario in scenarios:
        response = run_agent(agent_command, make_prompt(skill_text, scenario))
        check_response(scenario, response)
        print(f"PASS: {scenario.scenario_id}")

    print(f"PASS: {len(scenarios)} ticket-start large orchestration behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  TICKET_START_BEHAVIOR_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/ticket-start/large_orchestration_behavioral_pressure.py

Optional:
  TICKET_START_BEHAVIOR_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill_text: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows the ticket-start skill.

Skill text:
{skill_text}

User request:
{scenario.user_request}

Do not execute the ticket. Return a concise dispatch plan only. It must name:
- the orchestration map entries and their waves,
- each child implementer handoff start block,
- each child implementer final response schema,
- browser verifier handoff and final response schema,
- how the root monitors agents before Ship.

Use exact field labels where the skill defines them.
"""


def run_agent(agent_command: str, prompt: str) -> str:
    completed = subprocess.run(
        agent_command,
        input=prompt,
        text=True,
        shell=True,
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


def check_response(scenario: Scenario, response: str) -> None:
    missing = [term for term in scenario.required_terms if term not in response]
    if missing:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(f"{scenario.scenario_id} missing required terms: {missing}")

    forbidden = [term for term in scenario.forbidden_terms if term in response]
    if forbidden:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(f"{scenario.scenario_id} included forbidden terms: {forbidden}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
