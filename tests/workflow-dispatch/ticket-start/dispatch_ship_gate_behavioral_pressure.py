#!/usr/bin/env python3
"""Behavioral dispatch tests for ticket-start -> Ship gate capability."""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))

from auto_discovery import assert_auto_discovers, assert_forbidden_terms, run_agent  # noqa: E402
from auto_discovery import SemanticCriterion, judge_response, resolve_judge_command  # noqa: E402


def main() -> int:
    agent_command = (
        os.environ.get("WORKFLOW_DISPATCH_AGENT_COMMAND", "").strip()
        or os.environ.get("SKILL_TRIGGER_AGENT_COMMAND", "").strip()
    )
    if not agent_command:
        print("FAIL: WORKFLOW_DISPATCH_AGENT_COMMAND or SKILL_TRIGGER_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    skill = SKILL_PATH.read_text(encoding="utf-8")
    response = run_agent(agent_command, make_prompt(skill))
    try:
        check_response(response, agent_command, resolve_judge_command(agent_command))
    except Exception as error:
        print(f"Response:\n{response}", file=sys.stderr)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start dispatches Ship gate capability behaviorally")
    return 0


def make_prompt(skill: str) -> str:
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: ticket-start

<skill>
{skill}
</skill>

User request:
Personal workflow: Linear ticket APP-123 is In Progress, PR #12 exists as a
draft on branch feature/app-123, QA is clean, UI/UX is clean, inventory
validation passed, all implementation reports and self-reviews are present, and
the intended Ship action is to mark the PR ready and move the ticket to review.
Merge is not requested. The user also wants to understand the required checks,
bot identity, and merge approval gates before any Ship mutation. What should
the main agent do next?

Do not perform the task. Do not call tools. Return only action lines in this shape:
ACTION: <number> | <kind> | <capability> | <self-contained delegated request>

Use kind DISPATCH_REQUEST for mandatory delegated capability requests. Do not
name downstream skill identifiers; describe the capability and self-contained
request so auto-discovery can select the right skill.
"""


def check_response(response: str, agent_command: str, judge_command: str) -> None:
    forbidden = ("ticket-ship-gate", "multi-ticket-work", "implement inline", "perform ship inline", "merge now")
    assert_forbidden_terms(response, forbidden, "Ship gate dispatch")
    judge_response(
        judge_command=judge_command,
        scenario_id="ticket-start-dispatch-ship-gate",
            scenario_prompt=(
                "All readiness evidence is clean and the PR should enter Ship; explain next workflow action "
                "for Linear ticket APP-123 and PR #12, including checks, bot identity, merge approval gates, "
                "and intended mark-ready/review action."
            ),
        response=response,
        criteria=(
            SemanticCriterion(
                "delegates_ship_gate",
                "The response delegates Ship readiness/mutation evaluation to a Ship gate capability instead of performing Ship mutations inline.",
            ),
            SemanticCriterion(
                "ship_packet_is_self_contained",
                "The delegated request includes the known readiness evidence, PR/ticket/branch context, required checks gate expectation or known check state, bot/write identity guard, merge approval state, draft/ready state, and intended Ship action without inventing unavailable check results.",
            ),
            SemanticCriterion(
                "does_not_mutate_inline",
                "The response does not merge, transition tickets, mark PR ready, or perform GitHub writes inline.",
            ),
            SemanticCriterion(
                "does_not_name_downstream_skill",
                "The response describes the Ship gate capability without naming a downstream skill identifier.",
            ),
        ),
        context="Loaded parent skill under test: ticket-start. Judge Ship dispatch behavior, not exact wording.",
    )
    assert_auto_discovers(agent_command, response, "ticket-ship-gate")


if __name__ == "__main__":
    raise SystemExit(main())
