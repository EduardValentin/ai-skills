#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-implementation-unit."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-implementation-unit" / "SKILL.md"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_request: str
    required_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...]


SCENARIOS = (
    Scenario(
        scenario_id="approved-slice-report",
        user_request=(
            "Use the loaded implementation-unit skill for an approved Invite Flow plan slice. "
            "Do not edit files. Return the implementation approach and final report shape the "
            "implementer should produce after coding."
        ),
        required_terms=(
            "ready for verification",
            "files changed",
            "local tests",
            "self-review",
            "known risks",
            "handoff",
            "qa",
            "ui/ux",
        ),
        forbidden_terms=(
            "ready to ship",
            "ready to merge",
        ),
    ),
    Scenario(
        scenario_id="blocked-missing-scope",
        user_request=(
            "Use the loaded implementation-unit skill, but the request only says "
            "'fix the invite flow' and provides no approved plan slice or Scoping locators. "
            "Describe the correct response."
        ),
        required_terms=(
            "implementation blocked",
            "approved",
            "plan",
            "scope",
        ),
        forbidden_terms=(
            "start coding",
            "best guess",
            "ready for verification",
        ),
    ),
    Scenario(
        scenario_id="self-review-not-qa",
        user_request=(
            "Use the loaded implementation-unit skill after a focused fix. Return the report "
            "boundary so the orchestrator knows this is self-reviewed implementation evidence, "
            "not QA or UI/UX completion."
        ),
        required_terms=(
            "self-review",
            "report",
            "qa",
            "ui/ux",
            "verification",
        ),
        forbidden_terms=(
            "globally complete",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("TICKET_IMPLEMENTATION_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: TICKET_IMPLEMENTATION_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("TICKET_IMPLEMENTATION_SCENARIO", "").strip()
    scenarios = [
        scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter
    ]
    if not scenarios:
        print(f"FAIL: no scenario matched {scenario_filter!r}", file=sys.stderr)
        return 1

    skill = SKILL_PATH.read_text(encoding="utf-8")
    try:
        for scenario in scenarios:
            response = run_agent(agent_command, make_prompt(skill, scenario))
            check_response(scenario, response)
            print(f"PASS: {scenario.scenario_id}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(scenarios)} ticket-implementation-unit behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  TICKET_IMPLEMENTATION_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/ticket-implementation-unit/implementation_unit_behavioral_pressure.py

Optional:
  TICKET_IMPLEMENTATION_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows an implementation-unit skill.

Loaded skill: ticket-implementation-unit

<skill>
{skill}
</skill>

User request:
{scenario.user_request}

Do not perform real implementation. Return only the approach/report behavior the
implementation agent should use. Keep it concise.
"""


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


def check_response(scenario: Scenario, response: str) -> None:
    normalized = response.lower()
    missing = [term for term in scenario.required_terms if term.lower() not in normalized]
    if missing:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(f"{scenario.scenario_id} missing required terms: {missing}")

    forbidden = [term for term in scenario.forbidden_terms if term.lower() in normalized]
    if forbidden:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(f"{scenario.scenario_id} included forbidden terms: {forbidden}")


if __name__ == "__main__":
    raise SystemExit(main())
