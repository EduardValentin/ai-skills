#!/usr/bin/env python3
"""Behavioral pressure test for ticket-start delegated execution sequence."""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))

from auto_discovery import assert_forbidden_terms, run_agent  # noqa: E402
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
        check_response(response, resolve_judge_command(agent_command))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start defines delegated execution sequence")
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
backend and UI ticket. Return only the delegated execution workflow actions the
main agent must take before Ship.

Do not execute the ticket. Do not call tools.

Return only action lines in this shape:
ACTION: <number> | <kind> | <capability> | <self-contained delegated request>

Use kind DISPATCH_REQUEST for delegated subagent work. Keep each request
self-contained and do not name downstream skill identifiers.
"""


def check_response(response: str, judge_command: str) -> None:
    forbidden = ("multi-ticket-work", "qa-verification", "frontend-ui-review", "implement-unit-of-work")
    try:
        assert_forbidden_terms(response, forbidden, "execution orchestration dispatch")
        judge_response(
            judge_command=judge_command,
            scenario_id="ticket-start-delegated-execution-sequence",
            scenario_prompt=(
                "Requirements/design artifact and implementation plan are approved for a mixed backend/UI ticket; "
                "return delegated execution workflow actions before Ship."
            ),
            response=response,
            criteria=(
                SemanticCriterion(
                    "initializes_work_unit_status",
                    "The response initializes or maintains a compact work-unit status table or equivalent status ledger before claiming readiness.",
                ),
                SemanticCriterion(
                    "delegates_implementation",
                    "The response delegates implementation for approved work units and asks for changed surfaces, checks, risks, and handoff notes.",
                ),
                SemanticCriterion(
                    "delegates_verifiers",
                    "The response delegates self-review/review, QA verification, and UI/UX verification for UI-facing or mixed work.",
                ),
                SemanticCriterion(
                    "aggregates_findings_and_fixes",
                    "The response aggregates verifier findings, classifies blockers/out-of-scope/fixable items, delegates scoped fixes, and reruns affected verification loops.",
                ),
                SemanticCriterion(
                    "stops_only_when_verifiers_clean_or_blocked",
                    "The response repeats the loop until no verifier reports findings or remaining findings are explicitly blocked or out of scope.",
                ),
            ),
            context="Loaded parent skill under test: ticket-start. Judge the delegated execution sequence, not exact wording.",
        )
    except AssertionError as error:
        print(f"Response:\n{response}", file=sys.stderr)
        raise error


if __name__ == "__main__":
    raise SystemExit(main())
