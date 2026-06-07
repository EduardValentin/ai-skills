#!/usr/bin/env python3
"""Behavioral dispatch tests for ticket-start -> Ship gate capability."""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))

from auto_discovery import assert_auto_discovers, assert_concept_groups, assert_forbidden_terms, run_agent  # noqa: E402


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
        check_response(response, agent_command)
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
Personal workflow: QA is clean, UI/UX is clean, inventory validation passed,
all implementation reports and self-reviews are present, and the PR should enter
Ship. The user also wants to understand the required checks, bot identity, and
merge approval gates before any Ship mutation. What should the main agent do next?

Do not perform the task. Do not call tools. Return only action lines in this shape:
ACTION: <number> | <kind> | <capability> | <self-contained delegated request>

Use kind DISPATCH_REQUEST for mandatory delegated capability requests. Do not
name downstream skill identifiers; describe the capability and self-contained
request so auto-discovery can select the right skill.
"""


def check_response(response: str, agent_command: str) -> None:
    required_groups = (
        ("dispatch_request", "dispatch request", "delegated request"),
        ("ship gate", "ship readiness", "ship mutation"),
        ("readiness ledger", "readiness packet", "per-work-unit ledger", "per-unit readiness"),
        ("required checks", "remote checks", "pr checks"),
        ("bot", "github app", "write identity"),
        ("approval", "merge approval", "user approved merge"),
    )
    assert_concept_groups(response, required_groups, "Ship gate dispatch")

    forbidden = ("ticket-ship-gate", "ticket-work-unit-orchestration", "implement inline", "perform ship inline", "merge now")
    assert_forbidden_terms(response, forbidden, "Ship gate dispatch")
    assert_auto_discovers(agent_command, response, "ticket-ship-gate")


if __name__ == "__main__":
    raise SystemExit(main())
