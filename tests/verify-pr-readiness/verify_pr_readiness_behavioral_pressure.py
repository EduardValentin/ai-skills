#!/usr/bin/env python3
"""Behavioral pressure tests for verify-pr-readiness."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "verify-pr-readiness" / "SKILL.md"
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
        scenario_id="checks-failing-not-ready",
        user_request=(
            "Check readiness for Linear ticket APP-123. The linked PR is #42, the ticket is In Review, "
            "merge is approved, but required PR checks show build=pass, lint=fail, "
            "and e2e=pending."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_on_required_checks",
                "The response returns NOT_READY because required PR or CI checks are failing or pending.",
            ),
            SemanticCriterion(
                "reports_blocking_checks",
                "The response lists the specific blocking check states from the scenario.",
            ),
            SemanticCriterion(
                "does_not_mutate_when_blocked",
                "The response does not merge the PR, mark the PR ready, or move the Linear ticket while checks are blocked.",
            ),
            SemanticCriterion(
                "does_not_delegate_fixes",
                "The response reports the blockers without delegating or attempting fixes.",
            ),
        ),
        forbidden_terms=(
            "merged successfully",
            "moved APP-123 to Done",
            "delegating fixes",
            "start a fix agent",
            "CANNOT " + "SHIP",
        ),
    ),
    Scenario(
        scenario_id="in-progress-ticket-not-ready-for-done",
        user_request=(
            "Check readiness for Jira ticket PROJ-88 to move to Done. The PR checks are passing and merge is "
            "approved, but the Jira ticket status is still In Progress."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_in_progress_to_done",
                "The response returns NOT_READY because the ticket is still In Progress and cannot move directly to Done.",
            ),
            SemanticCriterion(
                "requires_review_state",
                "The response says the ticket must first be in a review or code-review state before readiness actions.",
            ),
            SemanticCriterion(
                "does_not_mutate_when_state_invalid",
                "The response does not merge the PR or move the Jira ticket to Done while the ticket is not in a review state.",
            ),
        ),
        forbidden_terms=(
            "merged successfully",
            "moved PROJ-88 to Done",
            "ready to merge",
            "CANNOT " + "SHIP",
        ),
    ),
    Scenario(
        scenario_id="merge-and-parent-sync",
        user_request=(
            "Check readiness and perform approved actions for Jira child ticket PROJ-4. PR #77 is linked, required checks are "
            "passing, merge is explicitly approved, and PROJ-4 is in Code Review. "
            "The intended actions are merge PR #77 and move PROJ-4 to Done. Its parent Epic "
            "PROJ-1 has children PROJ-4 and PROJ-5; PROJ-5 is already Done, so after PROJ-4 "
            "is done there will be no non-final child tickets."
        ),
        criteria=(
            SemanticCriterion(
                "allows_readiness_when_gates_pass",
                "The response treats the PR and ticket as ready because the ticket is in a review state, checks pass, and merge is approved.",
            ),
            SemanticCriterion(
                "moves_child_to_final_state",
                "The response says to merge the PR and move child ticket PROJ-4 to a final state, or in dry-run mode lists those exact mutations as the actions that would be performed.",
            ),
            SemanticCriterion(
                "rereads_hierarchy",
                "The response requires re-reading the parent and sibling or child ticket statuses before changing the parent.",
            ),
            SemanticCriterion(
                "moves_parent_when_all_children_final",
                "The response says to move parent PROJ-1 to the final state, or in dry-run mode lists that exact parent transition as an action that would be performed, because no child remains non-final.",
            ),
            SemanticCriterion(
                "reports_actions",
                "The response includes a compact report of PR, ticket, and parent-sync actions.",
            ),
        ),
        forbidden_terms=(
            "leave PROJ-1 unchanged",
            "missing approval",
            "checks blocked",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("VERIFY_PR_READINESS_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: VERIFY_PR_READINESS_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("VERIFY_PR_READINESS_SCENARIO", "").strip()
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

    print(f"PASS: {len(scenarios)} verify-pr-readiness behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  VERIFY_PR_READINESS_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/verify-pr-readiness/verify_pr_readiness_behavioral_pressure.py

Optional:
  VERIFY_PR_READINESS_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows a PR readiness skill.

Loaded skill: verify-pr-readiness

<skill>
{skill}
</skill>

User request:
{scenario.user_request}

Do not perform external mutations. Return only the readiness decision and report
shape the agent should use. If gates pass, list the exact mutations that would
be performed. Keep it concise.
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
                "Loaded skill under test: verify-pr-readiness. Judge PR readiness "
                "gates, mutation boundaries, and parent ticket synchronization."
            ),
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
