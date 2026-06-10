#!/usr/bin/env python3
"""Behavioral pressure tests for codebase-scope-map."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "codebase-scope-map" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="ticket-scoping-read-only-locators",
        user_request=(
            "Before we implement this ticket, map the relevant code surface so the "
            "caller and implementers know exactly which files, tests, patterns, and "
            "risks matter without loading the whole repo into context."
        ),
        criteria=(
            SemanticCriterion(
                "structured_locator_map",
                "Because this pressure prompt forbids real repo inspection, the response should state that an actual scope map must use compact file:line locators and include entry points, target modules, analogous implementations, tests, contracts, dependencies, affected surfaces, and conflict points.",
            ),
            SemanticCriterion(
                "read_only_boundary",
                "The response keeps the scoping task read-only and forbids edits, generated writes, formatting rewrites, staging, commits, cleanup, solution selection, or implementation.",
            ),
            SemanticCriterion(
                "downstream_index_not_transcript",
                "Because this pressure prompt forbids real repo inspection, the response should describe the deliverable as a navigable downstream index, not a broad source dump, transcript, or vague prose-only summary.",
            ),
        ),
        forbidden_terms=("I will edit", "I'll patch"),
    ),
    Scenario(
        scenario_id="token-pressure-compact-map",
        user_request=(
            "The codebase is huge and context is tight. Scope this bug fix for downstream "
            "readers, but keep the result compact enough that the caller can carry it."
        ),
        criteria=(
            SemanticCriterion(
                "compact_grouped_entries",
                "Because this pressure prompt forbids real repo inspection, the response should require one-line representative entries and grouping for large sections rather than listing every search hit.",
            ),
            SemanticCriterion(
                "risks_not_omitted",
                "Because this pressure prompt forbids real repo inspection, the response should say high-risk omitted or uncertain areas belong under conflict points or clarification needs instead of being silently dropped.",
            ),
        ),
        forbidden_terms=("paste full functions", "dump the source"),
    ),
    Scenario(
        scenario_id="reference-backed-ui-scope",
        user_request=(
            "Scope this UI ticket in a repo with a runnable designs/ React reference app. "
            "The later visual reviewer will need prototype element locators for parity "
            "against production."
        ),
        criteria=(
            SemanticCriterion(
                "prototype_elements_required",
                "The response treats prototype/reference elements as mandatory for a reference-backed UI task and requires visible relevant declarations with locators.",
            ),
            SemanticCriterion(
                "affected_surface_map_for_visual_review",
                "The response requires an affected surface map pairing production locators, routes/states/selectors, and prototype counterparts where relevant.",
            ),
            SemanticCriterion(
                "surfaces_inventory_gap",
                "If prototype enumeration cannot be completed, the response reports a conflict or input gap instead of returning none or deferring everything to visual review.",
            ),
        ),
        forbidden_terms=("visual review can discover everything later",),
    ),
    Scenario(
        scenario_id="vague-context-maps-and-asks",
        user_request=(
            "Map the scope for this ticket, but the acceptance criteria are vague and "
            "I am not sure which route owns the feature."
        ),
        criteria=(
            SemanticCriterion(
                "maps_available_evidence",
                "Because this pressure prompt provides no repository to inspect, the response should map what can be known from the prompt and clearly mark incomplete areas.",
            ),
            SemanticCriterion(
                "needs_clarification_section",
                "The response uses the Needs clarification or input section for missing acceptance criteria, route ownership, and why each input matters.",
            ),
            SemanticCriterion(
                "does_not_invent_ownership",
                "The response does not invent feature ownership or choose an implementation direction to compensate for missing requirements.",
            ),
        ),
        forbidden_terms=("scope is complete", "just implement in"),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="codebase-scope-map",
        skill_name="codebase-scope-map",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="CODEBASE_SCOPE_MAP_AGENT_COMMAND",
        scenario_filter_env_var="CODEBASE_SCOPE_MAP_SCENARIO",
        prompt_instructions=(
            "Do not inspect a real repository. Return only the scoping behavior, "
            "output shape, and boundaries the scoping agent should follow. Include "
            "the read-only boundary explicitly. For UI/reference scenarios, call out "
            "prototype/reference and affected-surface-map expectations explicitly."
        ),
        judge_context=(
            "Loaded skill under test: codebase-scope-map. Judge scope-map behavior, "
            "read-only boundaries, locator discipline, and compactness. These scenarios "
            "ask for the behavior and report contract only; do not require actual "
            "repository file paths when the prompt says not to inspect a real repo."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
