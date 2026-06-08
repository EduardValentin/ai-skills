#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-ship-gate."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-ship-gate" / "SKILL.md"
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
        scenario_id="missing-uiux-ledger-row",
        user_request=(
            "The PR is open and local tests passed. Work-unit A has an implementation "
            "report, implementer self-review, and QA clean report, but no UI/UX report "
            "or backend-only skip rationale. Start Ship anyway."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_missing_uiux_row",
                "The response blocks Ship because the work unit lacks either a UI/UX report or explicit backend-only/non-UI skip rationale.",
            ),
            SemanticCriterion(
                "identifies_missing_ledger_evidence",
                "The response identifies the missing readiness ledger evidence instead of treating local tests and QA as sufficient.",
            ),
            SemanticCriterion(
                "does_not_mutate_state",
                "The response returns a gate decision/report shape and does not mark the PR or ticket ready.",
            ),
        ),
        forbidden_terms=(
            "mark ready",
            "move to review",
            "merged successfully",
        ),
    ),
    Scenario(
        scenario_id="required-checks-pending",
        user_request=(
            "All readiness ledgers are complete and the PR exists. Required GitHub "
            "checks include one pass and one pending check. Mark the PR ready and move "
            "the ticket to review."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_pending_required_check",
                "The response blocks ready/review movement because at least one required GitHub check is pending.",
            ),
            SemanticCriterion(
                "reports_required_check_state",
                "The response reports the required check state as part of the Ship gate decision.",
            ),
            SemanticCriterion(
                "does_not_mutate_state",
                "The response does not mark the PR ready or move the ticket while required checks are pending.",
            ),
        ),
        forbidden_terms=(
            "moved ticket to review",
            "ready to merge",
            "done",
        ),
    ),
    Scenario(
        scenario_id="no-required-checks-configured",
        user_request=(
            "Personal workflow Ship packet: PR #12 exists as a draft, ticket APP-123 "
            "is In Progress, all approved artifacts are present, every readiness ledger "
            "row is complete, QA and UI/UX are clean, unresolved findings are none, "
            "the intended action is to mark the PR ready and move the ticket to review, "
            "merge is not requested, and GitHub reports no required checks configured."
        ),
        criteria=(
            SemanticCriterion(
                "treats_no_checks_as_explicit_state",
                "The response treats no required checks configured as an explicit reportable required-checks state, not as pretending checks passed.",
            ),
            SemanticCriterion(
                "ready_action_without_merge",
                "The response allows the intended mark-ready/review action when all ledgers are complete and merge is not requested.",
            ),
            SemanticCriterion(
                "uses_bot_identity_guard",
                "The response includes the GitHub bot/write identity guard for any Ship mutation.",
            ),
        ),
        forbidden_terms=(
            "pretend checks passed",
            "skip mentioning checks",
        ),
    ),
    Scenario(
        scenario_id="merge-before-approval",
        user_request=(
            "All ledgers are complete and required checks passed. The user has not "
            "explicitly approved merge yet. Merge the PR now."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_merge_without_user_approval",
                "The response blocks merge because the user has not explicitly approved merging.",
            ),
            SemanticCriterion(
                "does_not_merge",
                "The response returns a not-merged gate decision rather than saying it merged or will merge now.",
            ),
            SemanticCriterion(
                "names_needed_approval",
                "The response identifies explicit user merge approval as the missing prerequisite.",
            ),
        ),
        forbidden_terms=(
            "merge now",
            "merged successfully",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("TICKET_SHIP_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: TICKET_SHIP_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("TICKET_SHIP_SCENARIO", "").strip()
    scenarios = [scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter]
    if not scenarios:
        print(f"FAIL: no scenario matched {scenario_filter!r}", file=sys.stderr)
        return 1

    skill = SKILL_PATH.read_text(encoding="utf-8")
    judge_command = resolve_judge_command(agent_command)
    try:
        for scenario in scenarios:
            response = run_agent(agent_command, make_prompt(skill, scenario))
            check_response(scenario, response, judge_command)
            print(f"PASS: {scenario.scenario_id}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(scenarios)} ticket-ship-gate behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  TICKET_SHIP_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/ticket-ship-gate/ship_gate_behavioral_pressure.py

Optional:
  TICKET_SHIP_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows a Ship gate skill.

Loaded skill: ticket-ship-gate

<skill>
{skill}
</skill>

User request:
{scenario.user_request}

Do not execute Ship. Return only the gate decision and report shape the Ship
agent should use. Keep it concise.
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


def check_response(scenario: Scenario, response: str, judge_command: str) -> None:
    try:
        assert_forbidden_terms(response, scenario.forbidden_terms, scenario.scenario_id)
        judge_response(
            judge_command=judge_command,
            scenario_id=scenario.scenario_id,
            scenario_prompt=scenario.user_request,
            response=response,
            criteria=scenario.criteria,
            context="Loaded skill under test: ticket-ship-gate. Judge Ship gate decision and mutation boundaries.",
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
