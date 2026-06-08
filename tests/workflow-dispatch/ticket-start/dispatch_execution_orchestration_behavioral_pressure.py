#!/usr/bin/env python3
"""Behavioral pressure test for ticket-start dispatching execution orchestration."""

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

    print("PASS: ticket-start dispatches execution orchestration through auto-discovery")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/workflow-dispatch/ticket-start/dispatch_execution_orchestration_behavioral_pressure.py
"""
    )


def make_prompt() -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: ticket-start

<skill>
{skill}
</skill>

User request:
The requirements/design artifact and implementation plan are approved for a mixed
backend and UI ticket. Return only the execution-routing workflow actions the
main agent must take before Ship.

Do not execute the ticket. Do not call tools.

Return only action lines in this shape:
ACTION: <number> | <kind> | <capability> | <self-contained delegated request>

Use kind DISPATCH_REQUEST for mandatory delegated capability requests. Do not
name downstream skill identifiers; describe the capability and self-contained
request so auto-discovery can select the right skill.
"""


def check_response(response: str, agent_command: str, judge_command: str) -> None:
    forbidden = ("ticket-work-unit-orchestration", "ticket-qa-verification", "frontend-ui-review", "ticket-implementation-unit")
    try:
        assert_forbidden_terms(response, forbidden, "execution orchestration dispatch")
        judge_response(
            judge_command=judge_command,
            scenario_id="ticket-start-dispatch-execution-orchestration",
            scenario_prompt=(
                "Requirements/design artifact and implementation plan are approved for a mixed backend/UI ticket; "
                "return execution-routing workflow actions before Ship."
            ),
            response=response,
            criteria=(
                SemanticCriterion(
                    "delegates_execution_orchestration",
                    "The response delegates approved implementation coordination to an execution-orchestration capability rather than doing implementation/QA/UIUX/fixes directly.",
                ),
                SemanticCriterion(
                    "forwards_approved_context_packet",
                    "The delegated request carries approved requirements/design, approved implementation plan, scope/scoping map, ticket or acceptance context, repo/workflow state, and relevant UI/reference context.",
                ),
                SemanticCriterion(
                    "readiness_ledger_handoff",
                    "The response expects per-work-unit readiness ledger tracking and Ship handoff before Ship.",
                ),
                SemanticCriterion(
                    "no_direct_child_work",
                    "The response does not directly dispatch implementation, QA, UI/UX verification, review, testing, fix loops, or Ship mutations from ticket-start.",
                ),
            ),
            context="Loaded parent skill under test: ticket-start. Judge workflow dispatch behavior, not exact wording.",
        )
    except AssertionError as error:
        print(f"Response:\n{response}", file=sys.stderr)
        raise error

    assert_auto_discovers(agent_command, response, "ticket-work-unit-orchestration")


if __name__ == "__main__":
    raise SystemExit(main())
