#!/usr/bin/env python3
"""Behavioral pressure tests for verify-pr."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "verify-pr" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import (  # noqa: E402
    SemanticCriterion,
)


SCENARIOS = (
    Scenario(
        scenario_id="required-checks-and-surface-tests-block",
        user_request=(
            "Verify PR #42 for Linear ticket APP-123. The ticket is In Review and the PR has one approval "
            "with no unresolved comments. Source-control metadata says build=pass, lint=fail, e2e=pending. "
            "No evidence is available yet for tests covering the implemented invite-form surface."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_on_required_checks",
                "The response returns NOT_READY because required PR or CI checks are failing or pending.",
            ),
            SemanticCriterion(
                "blocks_on_missing_surface_tests",
                "The response also treats missing test evidence for the implemented surface area as a readiness blocker.",
            ),
            SemanticCriterion(
                "reports_specific_blockers",
                "The response lists the specific failing or pending checks and the missing implemented-surface test evidence.",
            ),
            SemanticCriterion(
                "does_not_mutate_when_blocked",
                "The response does not merge the PR, mark it ready, update tickets, or dismiss comments while gates are blocked.",
            ),
        ),
        forbidden_terms=(
            "merged successfully",
            "moved APP-123 to Done",
            "ready to merge",
            "ready for final approval",
        ),
    ),
    Scenario(
        scenario_id="ticket-must-be-review-state",
        user_request=(
            "Verify PR #88 for Jira ticket PROJ-88. Required checks are passing, implemented-surface tests "
            "are passing, the PR is approved, and there are no unresolved comments. The Jira ticket status "
            "is still In Progress."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_in_progress_ticket",
                "The response returns NOT_READY because the linked ticket is still In Progress.",
            ),
            SemanticCriterion(
                "requires_review_state",
                "The response says the linked ticket must be in a review-state column such as In Review or Code Review.",
            ),
            SemanticCriterion(
                "does_not_mutate_when_ticket_invalid",
                "The response does not merge the PR or change the Jira ticket while the ticket state gate is blocked.",
            ),
        ),
        forbidden_terms=(
            "merged successfully",
            "moved PROJ-88 to Done",
            "READY_TO_MERGE",
            "Status: READY",
        ),
    ),
    Scenario(
        scenario_id="unresolved-review-comments-block",
        user_request=(
            "Verify PR #51 for Linear ticket APP-51. The ticket is Ready for Merge, all required CI checks "
            "and surface tests are passing, and one reviewer approved. GitHub shows one active unresolved "
            "review thread and one requested-changes review that has not been cleared."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_unresolved_comments",
                "The response returns NOT_READY because unresolved review comments or active review threads are present.",
            ),
            SemanticCriterion(
                "blocks_requested_changes",
                "The response treats requested-changes review state as a blocker until cleared.",
            ),
            SemanticCriterion(
                "names_review_blockers",
                "The response identifies both the unresolved thread/comment and requested-changes review as blockers.",
            ),
        ),
        forbidden_terms=(
            "no blockers",
            "Status: READY",
            "merge now",
            "dismissed comments",
        ),
    ),
    Scenario(
        scenario_id="fetch-missing-current-state",
        user_request=(
            "Verify this PR for final approval: https://github.com/acme/app/pull/77. I did not provide "
            "the current PR state, linked ticket IDs, ticket status, checks, tests, reviews, or comment state."
        ),
        criteria=(
            SemanticCriterion(
                "fetches_pr_metadata",
                "The response says to fetch current PR metadata directly through available source-control tooling instead of relying on missing user-provided state.",
            ),
            SemanticCriterion(
                "fetches_linked_ticket_metadata",
                "The response says to fetch linked ticket IDs and ticket status from PR metadata or the ticketing system when not provided.",
            ),
            SemanticCriterion(
                "fetches_all_readiness_gates",
                "The response names CI checks, implemented-surface test evidence, reviews, and unresolved comments as metadata that must be fetched before a readiness verdict.",
            ),
            SemanticCriterion(
                "asks_only_if_fetch_blocked",
                "The response asks the user for missing details only if the available tooling cannot fetch the required metadata.",
            ),
        ),
        forbidden_terms=(
            "local diff is enough",
            "assume checks pass",
            "Status: READY",
        ),
    ),
    Scenario(
        scenario_id="after-merge-monitoring-failure",
        user_request=(
            "The previous Verify PR report was READY for PR #99, and I explicitly approve merging it if the "
            "current source-control gates still pass. Re-check the gates before merge. After merge, the "
            "target-branch CI monitor reports deploy-smoke failed on merge commit abc123."
        ),
        criteria=(
            SemanticCriterion(
                "merges_only_after_ready_and_approval",
                "The response treats explicit merge approval plus freshly re-fetched passing readiness gates as prerequisites before merge, and treats the prior READY report only as a hint.",
            ),
            SemanticCriterion(
                "starts_post_merge_monitoring",
                "The response starts, requests, or reports a background post-merge monitor running against the merge commit or target branch.",
            ),
            SemanticCriterion(
                "reports_post_merge_failure",
                "The response reports POST_MERGE_BLOCKED because a post-merge CI check failed.",
            ),
            SemanticCriterion(
                "fetches_failure_details_and_plan",
                "For POST_MERGE_BLOCKED, the response includes a Source-control failure details fetched/requested line and a Proposed plan line, without implementing the fix automatically.",
            ),
        ),
        forbidden_terms=(
            "ignore the failure",
            "implemented the fix",
            "reran without reporting",
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="verify-pr",
        skill_name="verify-pr",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="VERIFY_PR_AGENT_COMMAND",
        scenario_filter_env_var="VERIFY_PR_SCENARIO",
        prompt_instructions=(
            "Do not perform external mutations. If metadata is missing and no tool calls are\n"
            "available in this pressure test, describe the mandatory fetch sequence before a\n"
            "readiness verdict instead of treating omitted state as final unknown state. If\n"
            "the scenario gives concrete current PR, ticket, CI, test, review, or comment\n"
            "state, treat those facts as already-fetched source metadata for the purpose of\n"
            "checking the gates. If gates pass, list the exact next action. Keep it concise."
        ),
        judge_context=(
            "Loaded skill under test: verify-pr. Judge source-of-truth metadata access, "
            "PR readiness gates, no-mutation boundaries, and post-merge monitoring behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
