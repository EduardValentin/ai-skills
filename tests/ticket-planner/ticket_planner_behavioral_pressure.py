#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-planner."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-planner" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="prototype-copy-boundary",
        user_request=(
            "Create a story for the onboarding screen. The React prototype shows "
            "button text, helper text, placeholders, and visual layout details."
        ),
        criteria=(
            SemanticCriterion(
                "references_prototype_without_copying_ui_details",
                "The response references prototype routes/screens/states without repeating button text, helper text, placeholders, layout, styling, or widget choices unless business-critical or explicitly requested.",
            ),
            SemanticCriterion(
                "story_focuses_business_outcome",
                "The response frames the story around user-observable product behavior rather than prototype implementation details.",
            ),
        ),
    ),
    Scenario(
        scenario_id="tracker-unavailable-stays-platform-neutral",
        user_request="Turn the PRD dashboard section into user stories. The issue tracker is not connected.",
        criteria=(
            SemanticCriterion(
                "tracker_not_required",
                "The response produces platform-neutral drafts and does not treat issue-tracker access as required for planning.",
            ),
            SemanticCriterion(
                "no_tracker_metadata_or_creation",
                "The response does not include tracker-specific metadata, IDs, or creation steps as part of planning.",
            ),
        ),
    ),
    Scenario(
        scenario_id="prd-update-approval",
        user_request=(
            "Clarification: archived plans stay visible to coaches forever but clients "
            "cannot see them."
        ),
        criteria=(
            SemanticCriterion(
                "identifies_business_rule",
                "The response identifies this clarification as a business rule or permission/lifecycle rule.",
            ),
            SemanticCriterion(
                "asks_before_prd_edit",
                "The response proposes a concise PRD update and asks before editing PRD.md.",
            ),
        ),
    ),
    Scenario(
        scenario_id="vertical-slice-pressure",
        user_request="Split this feature into tickets: database schema, API, frontend, and notifications.",
        criteria=(
            SemanticCriterion(
                "pushes_back_on_layer_slices",
                "The response pushes back on layer-sliced tickets and proposes vertical stories around user outcomes.",
            ),
            SemanticCriterion(
                "integration_points_in_first_viable_story",
                "The response ensures relevant UI, API, data, permissions, external systems, notifications, and analytics are covered by the first viable story when applicable.",
            ),
        ),
    ),
    Scenario(
        scenario_id="no-prd-or-prototype",
        user_request="Create user stories for a new team invitation feature. There is no PRD or prototype yet.",
        criteria=(
            SemanticCriterion(
                "runs_requirements_brainstorming_first",
                "The response does not draft immediately; it runs requirements brainstorming for users, flow, data, permissions, integrations, edge cases, and non-goals.",
            ),
            SemanticCriterion(
                "brief_approval_before_drafting",
                "The response produces a shared-understanding brief and waits for user approval before drafting stories.",
            ),
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="ticket-planner",
        skill_name="ticket-planner",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="TICKET_PLANNER_AGENT_COMMAND",
        scenario_filter_env_var="TICKET_PLANNER_SCENARIO",
        prompt_instructions=(
            "Do not create tracker issues or edit PRD.md. Return only the planning "
            "workflow, questions, story-slicing behavior, and approval gates."
        ),
        judge_context=(
            "Loaded skill under test: ticket-planner. Judge product planning, "
            "prototype boundaries, vertical slicing, PRD update gates, and tracker neutrality."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
