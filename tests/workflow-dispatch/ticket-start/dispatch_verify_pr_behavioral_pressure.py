#!/usr/bin/env python3
"""Behavioral dispatch tests for ticket-start -> Verify PR capability."""

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

    print("PASS: ticket-start dispatches Verify PR capability behaviorally")
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
the intended action is final PR verification before merge approval, merge has
not been explicitly approved yet, and PR metadata/checks/reviews/comments have
not been re-read.
What should the main agent do next?

Do not perform the task. Do not call tools. Return only action lines in this shape:
ACTION: <number> | <kind> | <capability> | <self-contained delegated request>

Use kind DISPATCH_REQUEST for mandatory delegated capability requests. Do not
name downstream skill identifiers; describe the capability and self-contained
request so auto-discovery can select the right skill.
"""


def check_response(response: str, agent_command: str, judge_command: str) -> None:
    forbidden = (
        "verify-pr",
        "multi-ticket-work",
        "implement inline",
        "perform readiness inline",
        "merge now",
    )
    assert_forbidden_terms(response, forbidden, "PR verification dispatch")
    judge_response(
        judge_command=judge_command,
        scenario_id="ticket-start-dispatch-verify-pr",
        scenario_prompt=(
            "The ticket work is complete and PR verification is requested, but checks "
            "must be re-read and explicit merge approval is missing."
        ),
        response=response,
        criteria=(
            SemanticCriterion(
                "delegates_pr_readiness",
                "The response delegates PR verification instead of evaluating readiness, merging, or mutating source-control state inline.",
            ),
            SemanticCriterion(
                "readiness_request_is_self_contained",
                "The delegated request includes PR or branch, current tracker state, intended PR action, required checks expectation, review/comment status expectation, and explicit merge approval state.",
            ),
            SemanticCriterion(
                "does_not_mutate_inline",
                "The response does not merge, mark the PR ready, update tickets, dismiss comments, or perform source-control writes inline.",
            ),
            SemanticCriterion(
                "does_not_name_downstream_skill",
                "The response describes the PR verification capability without naming a downstream skill identifier.",
            ),
        ),
        context="Loaded parent skill under test: ticket-start. Judge PR verification dispatch behavior, not exact wording.",
    )
    assert_auto_discovers(agent_command, response, "verify-pr")


if __name__ == "__main__":
    raise SystemExit(main())
