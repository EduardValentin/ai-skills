#!/usr/bin/env python3
"""Behavioral pressure tests for pr-reviewer-summary."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "pr-reviewer-summary" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="final-state-pr-body",
        user_request=(
            "Generate a PR description for a branch that added saved-place filtering. "
            "The work had several iterations and a false start, but the final diff "
            "changes the filter panel, API query parameter, and badge count behavior."
        ),
        criteria=(
            SemanticCriterion(
                "gathers_review_context",
                "The response requires inspecting branch diff, changed files, recent commits, and available ticket or conversation context before drafting.",
            ),
            SemanticCriterion(
                "summarizes_final_state_only",
                "The PR body describes the final shipped behavior and implementation shape, not iteration history, false starts, or chronological fixes.",
            ),
            SemanticCriterion(
                "reviewer_focused_sections",
                "The response uses Summary of Changes and Manual Testing, adding Technical Details only when warranted by cross-module or non-obvious logic.",
            ),
            SemanticCriterion(
                "manual_testing_is_actionable",
                "Manual testing is written as explicit steps with preconditions, expected results, and changed states or regressions relevant to the diff.",
            ),
        ),
        forbidden_terms=("initially", "after feedback", "then we changed it again"),
    ),
    Scenario(
        scenario_id="missing-diff-blocks",
        user_request="Write the PR body, but there is no branch diff, changed-file summary, ticket, or PR URL available.",
        criteria=(
            SemanticCriterion(
                "blocks_without_reliable_context",
                "The response stops and asks for PR diff, changed-file summary, PR URL, or other reliable context instead of inventing a PR body.",
            ),
            SemanticCriterion(
                "does_not_fabricate_summary",
                "The response does not produce a fake Summary of Changes or Manual Testing from missing context.",
            ),
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="pr-reviewer-summary",
        skill_name="pr-reviewer-summary",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="PR_REVIEWER_SUMMARY_AGENT_COMMAND",
        scenario_filter_env_var="PR_REVIEWER_SUMMARY_SCENARIO",
        prompt_instructions=(
            "Do not inspect a real diff. Return only the PR-body drafting workflow, "
            "required context, output sections, and blocker behavior."
        ),
        judge_context=(
            "Loaded skill under test: pr-reviewer-summary. Judge reviewer usefulness, "
            "final-state summarization, context requirements, and manual-testing quality."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
