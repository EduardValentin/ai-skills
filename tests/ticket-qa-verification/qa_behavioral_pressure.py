#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-qa-verification."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-qa-verification" / "SKILL.md"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_request: str
    required_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...]


SCENARIOS = (
    Scenario(
        scenario_id="backend-api-live-behavior",
        user_request=(
            "QA a backend-only API change. Unit tests passed, but the acceptance "
            "criteria require validating successful creation, duplicate rejection, "
            "auth boundaries, persisted state, and error payloads against the running service."
        ),
        required_terms=(
            "backend",
            "service",
            "unit test",
            "request",
            "response",
            "persisted",
            "auth",
            "error",
            "QA report",
        ),
        forbidden_terms=(
            "unit tests are enough",
            "clean because tests passed",
            "fix the bug",
        ),
    ),
    Scenario(
        scenario_id="ui-behavior-not-visual-parity",
        user_request=(
            "QA a user-facing settings form. Exercise loading, empty, success, "
            "error, validation, disabled, rapid-click, and navigation-mid-save behavior "
            "in the running app. Do not perform visual parity review."
        ),
        required_terms=(
            "ui",
            "app",
            "loading",
            "empty",
            "success",
            "error",
            "validation",
            "rapid",
            "out-of-scope",
        ),
        forbidden_terms=(
            "visual parity is qa",
            "style review",
            "fix the bug",
        ),
    ),
    Scenario(
        scenario_id="mixed-api-and-ui",
        user_request=(
            "QA a mixed invite flow where the invite API and invite form changed together. "
            "Verify backend behavior and browser-visible behavior before Ship."
        ),
        required_terms=(
            "mixed",
            "backend",
            "ui",
            "api",
            "browser",
            "clean",
            "AC line",
            "QA report",
        ),
        forbidden_terms=(
            "only backend",
            "only ui",
            "fix the bug",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("TICKET_QA_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: TICKET_QA_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("TICKET_QA_SCENARIO", "").strip()
    scenarios = [scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter]
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

    print(f"PASS: {len(scenarios)} ticket-qa-verification behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  TICKET_QA_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/ticket-qa-verification/qa_behavioral_pressure.py

Optional:
  TICKET_QA_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows a QA verification skill.

Loaded skill: ticket-qa-verification

<skill>
{skill}
</skill>

User request:
{scenario.user_request}

Do not execute QA. Return only the QA approach and report shape the QA agent
should use. Keep it concise.
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
