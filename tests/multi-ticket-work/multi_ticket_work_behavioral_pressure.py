#!/usr/bin/env python3
"""Behavioral pressure tests for multi-ticket work orchestration.

Requires MULTI_TICKET_WORK_AGENT_COMMAND to name a command that reads a prompt
from stdin and writes the agent response to stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import (  # noqa: E402
    SemanticCriterion,
)


SCENARIOS = (
    Scenario(
        scenario_id="epic-ticket-set-delegates-prs-and-review-order",
        user_request=(
            "Use multi-ticket-work for the Billing Revamp Epic. It has tickets for "
            "pricing API, checkout UI, invoice migration, and analytics events. "
            "Explain how the main agent should coordinate the full implementation."
        ),
        criteria=(
            SemanticCriterion(
                "gathers_full_ticket_scope",
                "The response gathers every ticket in the Epic or multi-ticket scope, including parent/Epic context when relevant.",
            ),
            SemanticCriterion(
                "maps_sequence_and_parallel_work",
                "The response identifies dependencies, sequencing constraints, and which tickets can run in parallel.",
            ),
            SemanticCriterion(
                "preserves_state_across_compaction",
                "The response maintains a durable uncommitted orchestration note with scope, assignments, status, PRs, blockers, and decisions, and re-reads it after compaction/resume and before later dispatches or final reporting.",
            ),
            SemanticCriterion(
                "dispatches_one_subagent_per_ticket_or_unit",
                "The response dispatches one subagent per ticket or per explicitly split unit of work.",
            ),
            SemanticCriterion(
                "main_agent_orchestrates_only",
                "The response keeps the main agent as orchestrator and does not have it implement ticket work inline.",
            ),
            SemanticCriterion(
                "requires_pr_and_report_per_unit",
                "A ticket or unit is complete only after the assigned subagent opens a PR and returns a completion report.",
            ),
            SemanticCriterion(
                "final_report_lists_pr_review_order",
                "The final report lists opened PRs in the order the human should review them and explains dependency or integration rationale.",
            ),
            SemanticCriterion(
                "pr_description_surfaces_review_focus",
                "The response asks for reviewer-friendly PR body or reviewer-summary wording so each PR makes the human review focus clear.",
            ),
        ),
        forbidden_terms=(
            "readiness ledger",
            "implement-unit-of-work",
            "qa-verification",
            "ui-verification",
            "verify-pr",
            "implementation inline",
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="multi-ticket-work",
        skill_name="multi-ticket-work",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="MULTI_TICKET_WORK_AGENT_COMMAND",
        scenario_filter_env_var="MULTI_TICKET_WORK_SCENARIO",
        prompt_instructions=(
            "Do not execute the work. Return a concise orchestration plan only. It must explain:\n"
            "- how the full ticket scope is gathered,\n"
            "- how sequencing and parallel work are decided,\n"
            "- how subagents are assigned,\n"
            "- what makes each ticket or unit complete,\n"
            "- what appears in the final PR review report.\n"
            "Do not name downstream skill identifiers or unrelated skills."
        ),
        judge_context="Loaded skill under test: multi-ticket-work. Judge orchestration behavior, not exact wording.",
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
