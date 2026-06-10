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
                "dispatches_one_ticket_orchestrator_per_ticket_or_unit",
                "The response dispatches one ticket orchestrator per ticket or per explicitly split unit of work, not implementation workers.",
            ),
            SemanticCriterion(
                "main_agent_orchestrates_only",
                "The response keeps the main agent as orchestrator and does not have it implement ticket work inline.",
            ),
            SemanticCriterion(
                "ticket_orchestrators_delegate_internal_phases",
                "Each first-level ticket orchestrator is responsible for dispatching internal subagents or delegated requests for scoping, implementation, independent review, QA, UI/UX checks when applicable, scoped fixes, reruns, PR creation, and PR verification or handoff.",
            ),
            SemanticCriterion(
                "does_not_replace_verifiers_with_parent_or_worker_checks",
                "The response does not treat parent-side review or implementation-worker self-checks as substitutes for independent per-ticket verifier reports.",
            ),
            SemanticCriterion(
                "requires_pr_and_report_per_unit",
                "A ticket or unit is complete only after its ticket orchestrator opens a PR and returns a report with distinct implementation, review, QA, and UI/UX-or-skip evidence.",
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
        ),
    ),
    Scenario(
        scenario_id="prevents-worker-collapse-of-ticket-orchestration",
        user_request=(
            "The Commerce Epic has five independent tickets. A rushed coordinator proposes: "
            "'dispatch one implementation worker per ticket; each worker should implement, "
            "self-review, QA, run UI checks, push a PR, and the parent session can run one "
            "source-control review afterward.' Explain the correct multi-ticket coordination."
        ),
        criteria=(
            SemanticCriterion(
                "rejects_worker_collapse",
                "The response rejects the proposal to make first-level subagents implementation workers that combine implementation and verification.",
            ),
            SemanticCriterion(
                "first_level_agents_are_ticket_orchestrators",
                "The response makes the first-level subagent for each ticket a ticket orchestrator.",
            ),
            SemanticCriterion(
                "orchestrator_prompts_require_internal_delegation",
                "The response says each ticket orchestrator must dispatch internal subagents or delegated requests for implementation, independent review, QA, and UI/UX checks when applicable rather than performing them directly.",
            ),
            SemanticCriterion(
                "parent_review_is_not_enough",
                "The response says parent-session or source-control review cannot replace independent per-ticket review reports.",
            ),
            SemanticCriterion(
                "completion_needs_distinct_phase_evidence",
                "The response requires distinct returned evidence for implementation, independent review, QA, UI/UX-or-not-applicable, fixes/reruns, PR link, and completion report before marking a ticket complete.",
            ),
        ),
        forbidden_terms=(
            "readiness ledger",
            "implement-unit-of-work",
            "qa-verification",
            "ui-verification",
            "verify-pr",
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
            "- where durable orchestration notes are saved and when they are re-read,\n"
            "- how sequencing and parallel work are decided,\n"
            "- how first-level subagents are assigned and what role they have,\n"
            "- how each ticket orchestrator dispatches internal subagents or delegated requests for implementation and verification phases,\n"
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
