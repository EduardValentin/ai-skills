#!/usr/bin/env python3
"""Behavioral pressure tests for verify-pr."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "verify-pr" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from semantic_judge import (  # noqa: E402
    SemanticCriterion,
    assert_forbidden_terms,
    judge_response,
    resolve_judge_command,
)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_request: str
    criteria: tuple[SemanticCriterion, ...]
    forbidden_terms: tuple[str, ...]


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
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("VERIFY_PR_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: VERIFY_PR_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("VERIFY_PR_SCENARIO", "").strip()
    scenarios = [scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter]
    if not scenarios:
        print(f"FAIL: no scenario matched {scenario_filter!r}", file=sys.stderr)
        return 1

    skill = SKILL_PATH.read_text(encoding="utf-8")
    judge_command = resolve_judge_command(agent_command)
    try:
        for scenario in scenarios:
            response = run_agent(agent_command, make_prompt(skill, scenario))
            check_response(scenario, response, judge_command)
            print(f"PASS: {scenario.scenario_id}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(scenarios)} verify-pr behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  VERIFY_PR_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/verify-pr/verify_pr_behavioral_pressure.py

Optional:
  VERIFY_PR_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows a Verify PR skill.

Loaded skill: verify-pr

<skill>
{skill}
</skill>

User request:
{scenario.user_request}

Do not perform external mutations. If metadata is missing and no tool calls are
available in this pressure test, describe the mandatory fetch sequence before a
readiness verdict instead of treating omitted state as final unknown state. If
the scenario gives concrete current PR, ticket, CI, test, review, or comment
state, treat those facts as already-fetched source metadata for the purpose of
checking the gates. If gates pass, list the exact next action. Keep it concise.
"""


def run_agent(agent_command: str, prompt: str) -> str:
    completed = subprocess.run(
        shlex.split(agent_command),
        input=prompt,
        text=True,
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "agent command failed with exit code "
            f"{completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed.stdout


def check_response(scenario: Scenario, response: str, judge_command: str) -> None:
    try:
        assert_forbidden_terms(response, scenario.forbidden_terms, scenario.scenario_id)
        judge_response(
            judge_command=judge_command,
            scenario_id=scenario.scenario_id,
            scenario_prompt=scenario.user_request,
            response=response,
            criteria=scenario.criteria,
            context=(
                "Loaded skill under test: verify-pr. Judge source-of-truth metadata access, "
                "PR readiness gates, no-mutation boundaries, and post-merge monitoring behavior."
            ),
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
