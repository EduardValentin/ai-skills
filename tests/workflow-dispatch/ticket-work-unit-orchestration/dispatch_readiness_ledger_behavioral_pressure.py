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
    assert_forbidden_terms,
    run_agent,
)
from auto_discovery import SemanticCriterion, judge_response, resolve_judge_command  # noqa: E402


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
        check_response(response, agent_command, resolve_judge_command(agent_command))
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
skill, return the workflow actions the main agent must take before a work unit
can be marked Ship-ready. Include setup actions and the mandatory delegated
capability requests for implementation, QA, and UI/UX where applicable.

Return only action lines in this exact shape:
ACTION: <number> | <kind> | <target> | <details>

Use kind SET_UP_LEDGER for the per-work-unit readiness ledger and kind
DISPATCH_REQUEST for delegated capability requests. Do not name downstream skill
identifiers; describe each capability and self-contained request so
auto-discovery can select the right skill.
"""


def check_response(response: str, agent_command: str, judge_command: str) -> None:
    lines = action_lines(response)
    if not lines:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("missing ACTION lines")

    first_action = lines[0].casefold()
    if "set_up_ledger" not in first_action or "ledger" not in first_action:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("first action must set up the readiness ledger")

    forbidden = ("ticket-implementation-unit", "ticket-qa-verification", "frontend-ui-review", "codebase-scope-map")
    assert_forbidden_terms(response, forbidden, "readiness ledger workflow")

    dispatch_lines = [line for line in lines if "dispatch_request" in line.casefold()]
    if not dispatch_lines:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("missing DISPATCH_REQUEST actions")
    dispatch_text = "\n".join(dispatch_lines)

    judge_response(
        judge_command=judge_command,
        scenario_id="ticket-work-unit-orchestration-readiness-ledger-dispatch",
        scenario_prompt=(
            "Coordinate an approved implementation plan with Billing API backend-only, "
            "Onboarding UI UI-facing, and Invite Flow mixed."
        ),
        response=response,
        criteria=(
            SemanticCriterion(
                "ledger_first",
                "The response builds the per-work-unit readiness ledger before work can be marked Ship-ready.",
            ),
            SemanticCriterion(
                "classifies_each_unit",
                "The response preserves Billing API as backend-only, Onboarding UI as UI-facing, and Invite Flow as mixed.",
            ),
            SemanticCriterion(
                "separate_evidence_rows",
                "The response keeps separate evidence rows for implementation report, implementer self-review, QA, UI/UX or backend-only skip rationale, findings, and integration.",
            ),
            SemanticCriterion(
                "dispatches_required_capabilities",
                "The response dispatches implementation, QA behavior verification, and UI/UX visual review where applicable using self-contained delegated requests.",
            ),
            SemanticCriterion(
                "backend_only_uiux_skip",
                "The backend-only Billing API unit receives an explicit UI/UX skip rationale while UI-facing/mixed units require UI/UX review.",
            ),
            SemanticCriterion(
                "no_collapsed_readiness",
                "The response does not collapse self-review into QA, treat one clean unit as all clean, or mark the workflow complete prematurely.",
            ),
        ),
        context="Loaded parent skill under test: ticket-work-unit-orchestration. Judge workflow dispatch behavior, not exact wording.",
    )

    implementation_request = matching_dispatch_text(
        dispatch_lines,
        ("implementation work-unit", "approved work-unit plan slice", "implementation report", "implementer"),
        "implementation",
    )
    qa_request = matching_dispatch_text(
        dispatch_lines,
        ("acceptance-criteria", "behavior qa", "qa verification", "api routes", "persistence"),
        "QA",
    )
    uiux_request = matching_dispatch_text(
        dispatch_lines,
        ("implemented frontend ui", "visual parity", "visual consistency", "production analog", "runnable prototype"),
        "UI/UX",
    )

    assert_auto_discovers(agent_command, implementation_request, "ticket-implementation-unit")
    assert_auto_discovers(agent_command, qa_request, "ticket-qa-verification")
    assert_auto_discovers(agent_command, uiux_request, "frontend-ui-review")


def matching_dispatch_text(lines: list[str], terms: tuple[str, ...], capability: str) -> str:
    matches = [line for line in lines if any(term.casefold() in line.casefold() for term in terms)]
    if not matches:
        raise AssertionError(f"missing {capability} DISPATCH_REQUEST line")
    return "\n".join(matches)


if __name__ == "__main__":
    raise SystemExit(main())
