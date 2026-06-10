#!/usr/bin/env python3
"""Behavioral pressure test for ticket-start delegated execution sequence."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(REPO_ROOT / "tests"))

from harness import WorkflowDispatchScenario, run_workflow_dispatch_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    WorkflowDispatchScenario(
        scenario_id="ticket-start-delegated-execution-sequence",
        user_request=(
            "The confirmed requirements/design understanding and implementation plan are approved for a mixed\n"
            "backend and UI ticket. Return the delegated execution workflow actions and final\n"
            "PR verification gate the main agent must use before handoff."
        ),
        prompt_instructions=(
            "Do not execute the ticket. Do not call tools.\n\n"
            "Return only action lines in this shape:\n"
            "ACTION: <number> | <kind> | <capability> | <self-contained delegated request>\n\n"
            "Use kind DISPATCH_REQUEST for delegated subagent work and GATE for the final\n"
            "PR verification gate. Keep each request self-contained and do not name downstream\n"
            "skill identifiers. Include explicit actions for aggregating verifier findings,\n"
            "delegating scoped fixes for fixable findings, rerunning affected verification,\n"
            "and only then reaching the PR verification gate."
        ),
        criteria=(
            SemanticCriterion(
                "delegates_implementation_without_inline_work",
                "The response begins implementation by delegating work to implementer subagents rather than doing it inline.",
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
                "uses_ordered_ticket_sequence",
                "The response follows the order of implementation, independent review, QA, UI/UX when applicable, findings aggregation, scoped fixes, affected verification reruns, then PR verification.",
            ),
            SemanticCriterion(
                "readiness_waits_for_resolved_reports",
                "The response waits to route PR verification until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved or explicitly blocked/out of scope.",
            ),
        ),
        forbidden_terms=("multi-ticket-work", "qa-verification", "ui-verification", "implement-unit-of-work"),
        require_action_ledger=True,
    ),
)


def main() -> int:
    return run_workflow_dispatch_suite(
        suite_name="ticket-start delegated execution dispatch scenarios",
        parent_skill_name="ticket-start",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        scenario_filter_env_var="TICKET_START_EXECUTION_DISPATCH_SCENARIO",
    )


if __name__ == "__main__":
    raise SystemExit(main())
