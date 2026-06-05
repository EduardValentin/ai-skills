#!/usr/bin/env python3
"""Behavioral pressure tests for per-work-unit readiness ledgers.

Requires TICKET_WORK_UNIT_AGENT_COMMAND to name a command that reads a prompt
from stdin and writes the agent response to stdout.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATION_SKILL = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"
FALLBACK_SKILL = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_request: str
    units: tuple[str, ...]
    per_unit_terms: tuple[str, ...]
    global_terms: tuple[str, ...]
    global_any_groups: tuple[tuple[str, ...], ...]
    forbidden_terms: tuple[str, ...]


SCENARIOS = (
    Scenario(
        scenario_id="multi-ticket-readiness-ledger",
        user_request=(
            "Use the loaded ticket workflow for a large approved implementation spanning "
            "three work units: Billing API, Onboarding UI, and Invite Flow. Billing API "
            "is backend-only, Onboarding UI is UI-facing, and Invite Flow is mixed. "
            "Describe how the main agent should track completion before Ship."
        ),
        units=("Billing API", "Onboarding UI", "Invite Flow"),
        per_unit_terms=(
            "implementation",
            "self-review",
            "QA",
        ),
        global_terms=(
            "readiness ledger",
            "UI/UX",
            "backend-only",
        ),
        global_any_groups=(
            ("skip rationale", "backend-only rationale", "non-UI rationale"),
        ),
        forbidden_terms=(
            "one aggregate checklist is enough",
            "overall workflow is complete",
            "skip self-review",
            "QA/UIUX will run later",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("TICKET_WORK_UNIT_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: TICKET_WORK_UNIT_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("TICKET_WORK_UNIT_SCENARIO", "").strip()
    scenarios = [scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter]
    if not scenarios:
        print(f"FAIL: no scenario matched {scenario_filter!r}", file=sys.stderr)
        return 1

    skill_path = ORCHESTRATION_SKILL if ORCHESTRATION_SKILL.exists() else FALLBACK_SKILL
    skill_text = skill_path.read_text(encoding="utf-8")
    for scenario in scenarios:
        response = run_agent(agent_command, make_prompt(skill_path, skill_text, scenario))
        check_response(scenario, response)
        print(f"PASS: {scenario.scenario_id}")

    print(f"PASS: {len(scenarios)} per-work-unit readiness ledger behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  TICKET_WORK_UNIT_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/ticket-work-unit-orchestration/readiness_ledger_behavioral_pressure.py

Optional:
  TICKET_WORK_UNIT_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill_path: Path, skill_text: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows a ticket orchestration skill.

Loaded skill path: {skill_path.relative_to(REPO_ROOT)}

Skill text:
{skill_text}

User request:
{scenario.user_request}

Do not execute the ticket. Return only the completion-tracking plan the main agent
should use before Ship. Keep it concise.
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
    normalized_response = response.lower()

    missing_global = [term for term in scenario.global_terms if term.lower() not in normalized_response]
    missing_groups = [
        group for group in scenario.global_any_groups if not any(term.lower() in normalized_response for term in group)
    ]
    if missing_global or missing_groups:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(
            f"{scenario.scenario_id} missing global terms: {missing_global}; "
            f"missing global term groups: {missing_groups}"
        )

    missing_by_unit: dict[str, list[str]] = {}
    for unit in scenario.units:
        unit_window = window_after(response, unit, 1000)
        if not unit_window:
            missing_by_unit[unit] = ["unit section"]
            continue

        normalized_window = unit_window.lower()
        missing_terms = [term for term in scenario.per_unit_terms if term.lower() not in normalized_window]
        if missing_terms:
            missing_by_unit[unit] = missing_terms

    if missing_by_unit:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(f"{scenario.scenario_id} missing per-unit terms: {missing_by_unit}")

    ui_unit_windows = "\n".join(window_after(response, unit, 1000) for unit in ("Onboarding UI", "Invite Flow"))
    if "ui/ux" not in ui_unit_windows.lower():
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(f"{scenario.scenario_id} missing UI/UX verification on UI-facing units")

    billing_window = window_after(response, "Billing API", 1000).lower()
    if "ui/ux" not in billing_window or not any(term in billing_window for term in ("skip rationale", "backend-only", "non-ui")):
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(f"{scenario.scenario_id} missing backend-only UI/UX skip rationale for Billing API")

    forbidden = [term for term in scenario.forbidden_terms if term.lower() in normalized_response]
    if forbidden:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise AssertionError(f"{scenario.scenario_id} included forbidden terms: {forbidden}")


def window_after(text: str, marker: str, length: int) -> str:
    index = text.lower().find(marker.lower())
    if index < 0:
        return ""
    return text[index : index + length]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
