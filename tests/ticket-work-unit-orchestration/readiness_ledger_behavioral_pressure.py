#!/usr/bin/env python3
"""Behavioral pressure tests for per-work-unit readiness ledgers.

Requires TICKET_WORK_UNIT_AGENT_COMMAND to name a command that reads a prompt
from stdin and writes the agent response to stdout.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATION_SKILL = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"
FALLBACK_SKILL = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from semantic_judge import (  # noqa: E402
    SemanticCriterion,
    assert_forbidden_terms,
    judge_response,
    resolve_judge_command,
)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_request: str
    criteria: tuple[SemanticCriterion, ...]
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
        criteria=(
            SemanticCriterion(
                "separate_unit_rows",
                "The response tracks Billing API, Onboarding UI, and Invite Flow as separate work units rather than one aggregate checklist.",
            ),
            SemanticCriterion(
                "implementation_self_review_qa_per_unit",
                "Each work unit has separate implementation, implementer self-review, and QA evidence expectations.",
            ),
            SemanticCriterion(
                "uiux_for_ui_and_mixed_units",
                "Onboarding UI and Invite Flow require UI/UX verification because they are UI-facing or mixed.",
            ),
            SemanticCriterion(
                "backend_only_skip_rationale",
                "Billing API has an explicit backend-only/non-UI UI/UX skip rationale rather than a missing UI/UX row.",
            ),
            SemanticCriterion(
                "no_premature_completion",
                "The response does not claim the overall workflow is complete until each unit's applicable ledger rows, findings status, and integration status are resolved.",
            ),
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
    judge_command = resolve_judge_command(agent_command)
    for scenario in scenarios:
        response = run_agent(agent_command, make_prompt(skill_path, skill_text, scenario))
        check_response(scenario, response, judge_command, skill_path)
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


def check_response(scenario: Scenario, response: str, judge_command: str, skill_path: Path) -> None:
    try:
        assert_forbidden_terms(response, scenario.forbidden_terms, scenario.scenario_id)
        judge_response(
            judge_command=judge_command,
            scenario_id=scenario.scenario_id,
            scenario_prompt=scenario.user_request,
            response=response,
            criteria=scenario.criteria,
            context=(
                f"Loaded skill path: {skill_path.relative_to(REPO_ROOT)}. "
                "Judge per-work-unit readiness ledger behavior, not exact wording."
            ),
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
