#!/usr/bin/env python3
"""Behavioral pressure tests for linear-issue-writing."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "linear-issue-writing" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="approved-drafts-publishing-gates",
        user_request="Publish these approved platform-neutral stories to Linear.",
        criteria=(
            SemanticCriterion(
                "confirms_linear_publishing_context",
                "The response confirms this is Linear publishing, asks for target project/team and required metadata, and preserves the approved draft scope.",
            ),
            SemanticCriterion(
                "requires_exact_field_approval",
                "The response creates or updates nothing until the user approves exact title, description, parent, project, team, labels, priority, estimate, and other metadata.",
            ),
            SemanticCriterion(
                "runs_duplicate_detection_per_issue",
                "The response runs duplicate detection for each issue before creation and asks whether to skip, update, or create anyway when overlap is found.",
            ),
        ),
    ),
    Scenario(
        scenario_id="no-approved-draft-blocks-publishing",
        user_request="Create Linear tickets for the new onboarding flow.",
        criteria=(
            SemanticCriterion(
                "does_not_invent_product_scope",
                "The response refuses to invent backlog scope inside the Linear publishing skill when approved drafts are missing.",
            ),
            SemanticCriterion(
                "routes_to_drafting_first",
                "The response suggests drafting or refinement first and asks for approved source material before publishing.",
            ),
        ),
    ),
    Scenario(
        scenario_id="linear-unavailable-formats-only",
        user_request="Linear is not connected, but publish these approved stories.",
        criteria=(
            SemanticCriterion(
                "blocks_creation_without_integration",
                "The response states Linear creation or update cannot proceed while the Linear integration is unavailable.",
            ),
            SemanticCriterion(
                "can_format_draft",
                "The response may produce a Linear-ready draft format but does not claim any issue was created.",
            ),
        ),
        forbidden_terms=("created LIN-", "published successfully"),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="linear-issue-writing",
        skill_name="linear-issue-writing",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="LINEAR_ISSUE_WRITING_AGENT_COMMAND",
        scenario_filter_env_var="LINEAR_ISSUE_WRITING_SCENARIO",
        prompt_instructions=(
            "Do not call Linear. Return only the publishing workflow, gates, "
            "questions, and report behavior the Linear issue-writing agent should use."
        ),
        judge_context=(
            "Loaded skill under test: linear-issue-writing. Judge Linear modeling, "
            "approval gates, duplicate detection, and integration fallback behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
