#!/usr/bin/env python3
"""Behavioral pressure tests for multi-ticket work orchestration.

Requires MULTI_TICKET_WORK_AGENT_COMMAND to name a command that reads a prompt
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
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"
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
        scenario_id="epic-ticket-set-delegates-prs-and-review-order",
        user_request=(
            "Use multi-ticket-work for the Billing Revamp Epic. It has tickets for "
            "pricing API, checkout UI, invoice migration, and analytics events. "
            "Explain how the main agent should coordinate the full implementation."
        ),
        criteria=(
            SemanticCriterion(
                "gathers_full_ticket_scope",
                "The response gathers every ticket in the Epic or multi-ticket scope, including parent/Epic context when relevant.",
            ),
            SemanticCriterion(
                "maps_sequence_and_parallel_work",
                "The response identifies dependencies, sequencing constraints, and which tickets can run in parallel.",
            ),
            SemanticCriterion(
                "preserves_state_across_compaction",
                "The response maintains a durable uncommitted orchestration note with scope, assignments, status, PRs, blockers, and decisions, and re-reads it after compaction/resume and before later dispatches or final reporting.",
            ),
            SemanticCriterion(
                "dispatches_one_subagent_per_ticket_or_unit",
                "The response dispatches one subagent per ticket or per explicitly split unit of work.",
            ),
            SemanticCriterion(
                "main_agent_orchestrates_only",
                "The response keeps the main agent as orchestrator and does not have it implement ticket work inline.",
            ),
            SemanticCriterion(
                "requires_pr_and_report_per_unit",
                "A ticket or unit is complete only after the assigned subagent opens a PR and returns a completion report.",
            ),
            SemanticCriterion(
                "final_report_lists_pr_review_order",
                "The final report lists opened PRs in the order the human should review them and explains dependency or integration rationale.",
            ),
            SemanticCriterion(
                "pr_description_surfaces_review_focus",
                "The response asks for reviewer-friendly PR body or reviewer-summary wording so each PR makes the human review focus clear.",
            ),
        ),
        forbidden_terms=(
            "readiness ledger",
            "implement-unit-of-work",
            "qa-verification",
            "ui-verification",
            "verify-pr-readiness",
            "implementation inline",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("MULTI_TICKET_WORK_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: MULTI_TICKET_WORK_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("MULTI_TICKET_WORK_SCENARIO", "").strip()
    scenarios = [scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter]
    if not scenarios:
        print(f"FAIL: no scenario matched {scenario_filter!r}", file=sys.stderr)
        return 1

    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    judge_command = resolve_judge_command(agent_command)
    for scenario in scenarios:
        response = run_agent(agent_command, make_prompt(skill_text, scenario))
        check_response(scenario, response, judge_command)
        print(f"PASS: {scenario.scenario_id}")

    print(f"PASS: {len(scenarios)} multi-ticket-work behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  MULTI_TICKET_WORK_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/multi-ticket-work/multi_ticket_work_behavioral_pressure.py

Optional:
  MULTI_TICKET_WORK_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill_text: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows the multi-ticket-work skill.

Skill text:
{skill_text}

User request:
{scenario.user_request}

Do not execute the work. Return a concise orchestration plan only. It must explain:
- how the full ticket scope is gathered,
- how sequencing and parallel work are decided,
- how subagents are assigned,
- what makes each ticket or unit complete,
- what appears in the final PR review report.
Do not name downstream skill identifiers or unrelated skills.
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
            context="Loaded skill under test: multi-ticket-work. Judge orchestration behavior, not exact wording.",
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
