#!/usr/bin/env python3
"""Behavioral pressure test for multi-ticket-work workflow dispatch."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(REPO_ROOT / "tests"))

from harness import WorkflowDispatchScenario, run_workflow_dispatch_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    WorkflowDispatchScenario(
        scenario_id="multi-ticket-work-ticket-unit-dispatch",
        user_request=(
            "Work the whole Billing Revamp Epic. It includes four tickets:\n"
            "- Pricing API must land after Invoice migration.\n"
            "- Checkout UI must land after Pricing API.\n"
            "- Analytics events can happen independently.\n"
            "- Checkout UI should receive the upstream PR context."
        ),
        prompt_instructions=(
            "Do not perform the implementation. Do not call tools. Based only on the loaded\n"
            "skill, return the workflow actions the main agent must take to coordinate the\n"
            "multi-ticket work through PRs and completion reports. Include explicit actions\n"
            "for durable orchestration note creation/update and required re-read checkpoints\n"
            "when the loaded skill requires them.\n\n"
            "Return only action lines in this exact shape:\n"
            "ACTION: <number> | <kind> | <target> | <details>\n\n"
            "Use kind MAP_SCOPE for ticket discovery and dependency mapping, kind\n"
            "DISPATCH_SUBAGENT for ticket or unit assignment, and kind REPORT for final\n"
            "review-order reporting. Do not name downstream skill identifiers."
        ),
        criteria=(
            SemanticCriterion(
                "maps_full_scope_first",
                "The first phase gathers the full Epic ticket set and maps dependencies before dispatching work.",
            ),
            SemanticCriterion(
                "maintains_durable_orchestration_notes",
                "The response creates or updates a durable uncommitted orchestration note and plans to re-read it after context compaction or resume, before dependent dispatches, and before the final report.",
            ),
            SemanticCriterion(
                "respects_dependency_order",
                "The response sequences Invoice migration before Pricing API and Pricing API before Checkout UI.",
            ),
            SemanticCriterion(
                "parallelizes_independent_ticket",
                "The response treats Analytics events as safe to dispatch in parallel when repository constraints allow.",
            ),
            SemanticCriterion(
                "one_subagent_per_ticket_or_unit",
                "The response dispatches one subagent per ticket or explicitly split unit of work.",
            ),
            SemanticCriterion(
                "requires_pr_and_report",
                "Each dispatched ticket or unit requires a PR and completion report before it is complete.",
            ),
            SemanticCriterion(
                "final_review_order",
                "The final report lists opened PRs in dependency-aware review order.",
            ),
            SemanticCriterion(
                "pr_descriptions_include_review_focus",
                "The workflow asks subagents for reviewer-friendly PR bodies or reviewer-summary wording so the human review focus is clear.",
            ),
        ),
        forbidden_terms=(
            "readiness ledger",
            "implement-unit-of-work",
            "qa-verification",
            "ui-verification",
            "codebase-scope-map",
        ),
        require_action_ledger=True,
        first_action_contains=("map_scope",),
        required_action_contains=(("dispatch_subagent",),),
    ),
)


def main() -> int:
    return run_workflow_dispatch_suite(
        suite_name="multi-ticket-work dispatch scenarios",
        parent_skill_name="multi-ticket-work",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        scenario_filter_env_var="MULTI_TICKET_WORK_DISPATCH_SCENARIO",
    )


if __name__ == "__main__":
    raise SystemExit(main())
