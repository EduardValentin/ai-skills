#!/usr/bin/env python3
"""Behavioral dispatch tests for ticket-start -> Verify PR capability."""

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
        scenario_id="ticket-start-dispatch-verify-pr",
        user_request=(
            "Personal workflow: Linear ticket APP-123 is In Review, PR #12 exists as a draft\n"
            "on branch feature/app-123, implementation and verification reports are clean,\n"
            "the intended action is final PR verification before merge approval, merge has\n"
            "not been explicitly approved yet, and PR metadata/checks/reviews/comments have\n"
            "not been re-read.\n"
            "What should the main agent do next?"
        ),
        prompt_instructions=(
            "Do not perform the task. Do not call tools. Return only action lines in this shape:\n"
            "ACTION: <number> | <kind> | <capability> | <self-contained delegated request>\n\n"
            "Use kind DISPATCH_REQUEST for mandatory delegated capability requests. Do not\n"
            "name downstream skill identifiers; describe the capability and self-contained\n"
            "request so auto-discovery can select the right skill. Carry forward all concrete\n"
            "current-state facts provided in the user request, including tracker status, PR\n"
            "draft/readiness state, branch, clean report state, stale metadata, and merge\n"
            "approval state."
        ),
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
        forbidden_terms=("verify-pr", "multi-ticket-work", "implement inline", "perform readiness inline", "merge now"),
        expected_auto_discovery=("verify-pr",),
        require_action_ledger=True,
    ),
)


def main() -> int:
    return run_workflow_dispatch_suite(
        suite_name="ticket-start Verify PR dispatch scenarios",
        parent_skill_name="ticket-start",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        scenario_filter_env_var="TICKET_START_VERIFY_PR_DISPATCH_SCENARIO",
    )


if __name__ == "__main__":
    raise SystemExit(main())
