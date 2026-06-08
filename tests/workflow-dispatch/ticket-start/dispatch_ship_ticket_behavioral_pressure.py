#!/usr/bin/env python3
"""Behavioral dispatch tests for ticket-start -> ticket shipping capability."""

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

    print("PASS: ticket-start dispatches ticket shipping capability behaviorally")
    return 0


def make_prompt(skill: str) -> str:
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: ticket-start

<skill>
{skill}
</skill>

User request:
Personal workflow: Linear ticket APP-123 is In Review, PR #12 exists as a draft
on branch feature/app-123, implementation and verification reports are clean,
the intended action is to merge the PR and move the ticket to Done, merge has
not been explicitly approved yet, and required checks have not been re-read.
What should the main agent do next?

Do not perform the task. Do not call tools. Return only action lines in this shape:
ACTION: <number> | <kind> | <capability> | <self-contained delegated request>

Use kind DISPATCH_REQUEST for mandatory delegated capability requests. Do not
name downstream skill identifiers; describe the capability and self-contained
request so auto-discovery can select the right skill.
"""


def check_response(response: str, agent_command: str, judge_command: str) -> None:
    forbidden = ("ship-ticket", "multi-ticket-work", "implement inline", "perform shipping inline", "merge now")
    assert_forbidden_terms(response, forbidden, "ticket shipping dispatch")
    judge_response(
        judge_command=judge_command,
        scenario_id="ticket-start-dispatch-ship-ticket",
        scenario_prompt=(
            "The ticket work is complete and PR/ticket shipping is requested, but checks "
            "must be re-read and explicit merge approval is missing."
        ),
        response=response,
        criteria=(
            SemanticCriterion(
                "delegates_ticket_shipping",
                "The response delegates PR and ticket shipping readiness evaluation instead of performing merge or ticket mutations inline.",
            ),
            SemanticCriterion(
                "shipping_request_is_self_contained",
                "The delegated request includes PR or branch, current tracker state, intended tracker state, required checks expectation, and explicit merge approval state.",
            ),
            SemanticCriterion(
                "does_not_mutate_inline",
                "The response does not merge, transition tickets, mark PR ready, or perform source-control writes inline.",
            ),
            SemanticCriterion(
                "does_not_name_downstream_skill",
                "The response describes the shipping capability without naming a downstream skill identifier.",
            ),
        ),
        context="Loaded parent skill under test: ticket-start. Judge shipping dispatch behavior, not exact wording.",
    )
    assert_auto_discovers(agent_command, response, "ship-ticket")


if __name__ == "__main__":
    raise SystemExit(main())
