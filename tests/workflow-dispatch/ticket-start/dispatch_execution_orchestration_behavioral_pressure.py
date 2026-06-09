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
main agent must take before PR readiness or handoff.

Do not execute the ticket. Do not call tools.

Return only action lines in this shape:
ACTION: <number> | <kind> | <capability> | <self-contained delegated request>

Use kind DISPATCH_REQUEST for delegated subagent work. Keep each request
self-contained and do not name downstream skill identifiers.
"""


def check_response(response: str, judge_command: str) -> None:
    forbidden = ("multi-ticket-work", "qa-verification", "ui-verification", "implement-unit-of-work")
    try:
        assert_forbidden_terms(response, forbidden, "execution orchestration dispatch")
        judge_response(
            judge_command=judge_command,
            scenario_id="ticket-start-delegated-execution-sequence",
            scenario_prompt=(
                "Requirements/design artifact and implementation plan are approved for a mixed backend/UI ticket; "
                "return delegated execution workflow actions before PR readiness or handoff."
            ),
            response=response,
            criteria=(
                SemanticCriterion(
                    "delegates_implementation_without_inline_work",
                    "The response delegates implementation for the approved work instead of doing it inline.",
                ),
                SemanticCriterion(
                    "delegates_verifiers",
                    "The response delegates self-review/review, QA verification, and UI/UX verification for UI-facing or mixed work.",
                ),
                SemanticCriterion(
                    "handles_missing_verifier_tooling",
                    "The response says a verifier that lacks required tooling or access should report CANNOT_VERIFY with a reason, after which the main session performs that verification if it has the tooling or reports the blocker.",
                ),
                SemanticCriterion(
                    "aggregates_findings_and_fixes",
                    "The response aggregates verifier findings, delegates scoped fixes for fixable findings, and reruns affected verification as needed.",
                ),
                SemanticCriterion(
                    "does_not_prescribe_methodology_mechanics",
                    "The response does not prescribe fixed status-table columns, a specific subagent topology, or detailed code-review methodology.",
                ),
                SemanticCriterion(
                    "readiness_waits_for_resolved_reports",
                    "The response waits to route PR readiness until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved or explicitly blocked/out of scope.",
                ),
            ),
            context="Loaded parent skill under test: ticket-start. Judge the delegated execution sequence, not exact wording.",
        )
    except AssertionError as error:
        print(f"Response:\n{response}", file=sys.stderr)
        raise error


if __name__ == "__main__":
    raise SystemExit(main())
