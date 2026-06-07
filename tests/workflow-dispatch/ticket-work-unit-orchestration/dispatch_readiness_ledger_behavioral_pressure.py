#!/usr/bin/env python3
"""Behavioral pressure test for ticket-work-unit-orchestration workflow dispatch."""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))

from auto_discovery import (  # noqa: E402
    action_lines,
    assert_auto_discovers,
    assert_concept_groups,
    assert_forbidden_terms,
    run_agent,
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("WORKFLOW_DISPATCH_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: WORKFLOW_DISPATCH_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    try:
        response = run_agent(agent_command, make_prompt())
        check_response(response, agent_command)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-work-unit-orchestration dispatches readiness ledger before work")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/workflow-dispatch/ticket-work-unit-orchestration/dispatch_readiness_ledger_behavioral_pressure.py
"""
    )


def make_prompt() -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: ticket-work-unit-orchestration

<skill>
{skill}
</skill>

User request:
Coordinate an approved implementation plan with three work units:
- Billing API is backend-only.
- Onboarding UI is UI-facing.
- Invite Flow is mixed.

Do not perform the implementation. Do not call tools. Based only on the loaded
skill, return the first workflow actions the main agent must take before Ship.

Return only action lines in this exact shape:
ACTION: <number> | <kind> | <target> | <details>

Use kind SET_UP_LEDGER for the per-work-unit readiness ledger and kind
DISPATCH_REQUEST for delegated capability requests. Do not name downstream skill
identifiers; describe each capability and self-contained request so
auto-discovery can select the right skill.
"""


def check_response(response: str, agent_command: str) -> None:
    lines = action_lines(response)
    if not lines:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("missing ACTION lines")

    first_action = lines[0].casefold()
    if "set_up_ledger" not in first_action or "ledger" not in first_action:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("first action must set up the readiness ledger")

    required_groups = (
        ("billing api",),
        ("onboarding ui",),
        ("invite flow",),
        ("implementation", "implementer"),
        ("self-review", "self review"),
        ("qa", "acceptance-criteria verification", "behavior verification"),
        ("ui/ux", "visual verification", "frontend review"),
        ("backend-only", "backend only", "non-ui"),
        ("skip rationale", "non-ui rationale", "backend-only rationale"),
    )
    assert_concept_groups(response, required_groups, "readiness ledger workflow")

    forbidden = ("ticket-implementation-unit", "ticket-qa-verification", "frontend-ui-review", "codebase-scope-map")
    assert_forbidden_terms(response, forbidden, "readiness ledger workflow")

    dispatch_text = "\n".join(lines)
    assert_concept_groups(
        dispatch_text,
        (
            ("dispatch_request", "dispatch request", "delegated request"),
            ("implementation work-unit", "implementation unit", "implementer"),
            ("qa", "acceptance-criteria verification", "behavior verification"),
            ("ui/ux", "visual verification", "frontend review"),
        ),
        "readiness ledger dispatch actions",
    )

    assert_auto_discovers(agent_command, dispatch_text, "ticket-implementation-unit")
    assert_auto_discovers(agent_command, dispatch_text, "ticket-qa-verification")
    assert_auto_discovers(agent_command, dispatch_text, "frontend-ui-review")


if __name__ == "__main__":
    raise SystemExit(main())
