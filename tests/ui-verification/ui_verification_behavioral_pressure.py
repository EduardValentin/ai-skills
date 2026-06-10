#!/usr/bin/env python3
"""Behavioral pressure tests for ui-verification."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ui-verification" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="reference-parity-evidence",
        user_request=(
            "Compare the implemented React dashboard against the runnable designs/ "
            "reference app before release. I care about every visible element matching "
            "the prototype, not just the obvious cards."
        ),
        criteria=(
            SemanticCriterion(
                "uses_parity_mode",
                "The response uses parity mode because a runnable reference app is available.",
            ),
            SemanticCriterion(
                "requires_matched_inventory",
                "The response builds or verifies a matched-element inventory covering all relevant visible elements and states.",
            ),
            SemanticCriterion(
                "dom_evidence_primary",
                "The response uses DOM computed-style and bounding-rect evidence as primary evidence, with screenshots only secondary.",
            ),
        ),
        forbidden_terms=("checked the important elements", "screenshot comparison only"),
    ),
    Scenario(
        scenario_id="delegated-uiux-gate",
        user_request=(
            "Ticket-start delegated the UI/UX gate to you. You received production "
            "and prototype URLs, approved requirements/design, changed UI files, and "
            "an affected surface map with prototype/reference rows and production locators."
        ),
        criteria=(
            SemanticCriterion(
                "uses_received_inventory_inputs",
                "The response starts from the affected surface map, approved artifacts, changed UI files, URLs, and live DOM inspection.",
            ),
            SemanticCriterion(
                "fills_evidence_columns",
                "The response requires font, color/background, box, layout, size, state/accessibility, and verdict evidence for every in-scope row.",
            ),
            SemanticCriterion(
                "records_inventory_gaps",
                "The response adds observed production or reference elements missing from supplied inventory under inventory provenance gaps.",
            ),
        ),
    ),
    Scenario(
        scenario_id="no-reference-consistency",
        user_request=(
            "There is no prototype for this UI change. Review whether the new settings "
            "panel matches the rest of the production app's typography, spacing, borders, "
            "shadows, focus states, and accessibility."
        ),
        criteria=(
            SemanticCriterion(
                "uses_consistency_mode",
                "The response uses consistency mode because no runnable reference is present.",
            ),
            SemanticCriterion(
                "pairs_with_production_analogs",
                "The response pairs changed visible elements with credible production siblings or analogs for comparison.",
            ),
            SemanticCriterion(
                "blocks_or_degrades_without_basis",
                "The response returns BLOCKED or degraded evidence for rows where no credible analog can be identified instead of inventing a basis.",
            ),
        ),
    ),
    Scenario(
        scenario_id="missing-inventory-requires-scoping",
        user_request="Verify this frontend change against the ticket description and diff. No affected-element inventory was provided.",
        criteria=(
            SemanticCriterion(
                "requires_inventory_before_verification",
                "The response requires an affected-element inventory before normal UI verification starts.",
            ),
            SemanticCriterion(
                "uses_scoping_support",
                "The response obtains or produces the inventory from ticket description, acceptance criteria, diff or changed UI files, routes/states, and comparison basis before live verification.",
            ),
            SemanticCriterion(
                "does_not_invent_from_impressions",
                "The response does not invent the inventory from screenshots or visual impressions alone.",
            ),
        ),
    ),
    Scenario(
        scenario_id="browser-capability-degradation",
        user_request=(
            "Review visual parity, but the native browser automation tool is unavailable "
            "in this environment. You can still run shell commands."
        ),
        criteria=(
            SemanticCriterion(
                "falls_back_to_playwright_shell",
                "The response falls back to browser automation through shell, such as Playwright, when native browser tooling is unavailable.",
            ),
            SemanticCriterion(
                "uses_dom_extraction_script",
                "The response uses or describes using the bundled extraction script or equivalent DOM computed-style and bounding-rect extraction.",
            ),
            SemanticCriterion(
                "does_not_claim_clean_with_degraded_evidence",
                "If DOM evidence cannot be collected, the response reports degraded manual evidence or BLOCKED instead of claiming normal CLEAN parity.",
            ),
        ),
    ),
    Scenario(
        scenario_id="scoped-rerun-after-findings",
        user_request=(
            "The prior review found V1 major: graph card border and shadow differ from "
            "the prototype; V2 major: heading line-height differs; V3 minor: axis label "
            "typography differs. The approved plan already says preserve placement and "
            "accessibility semantics."
        ),
        criteria=(
            SemanticCriterion(
                "treats_findings_as_actionable",
                "The response treats the supplied issues as actionable parity defects rather than asking low-value confirmation.",
            ),
            SemanticCriterion(
                "scopes_rerun_to_affected_rows",
                "The response scopes rerun verification to affected rows and states unless shared layout or global styles changed.",
            ),
            SemanticCriterion(
                "requires_dom_evidence_after_fix",
                "The response does not accept local visual inspection alone after fixes; it requires rerun evidence.",
            ),
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="ui-verification",
        skill_name="ui-verification",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="UI_VERIFICATION_AGENT_COMMAND",
        scenario_filter_env_var="UI_VERIFICATION_SCENARIO",
        prompt_instructions=(
            "Do not launch a browser or inspect a real app. Return only the UI verification "
            "approach, evidence requirements, fallback behavior, and report verdict shape."
        ),
        judge_context=(
            "Loaded skill under test: ui-verification. Judge parity/consistency mode "
            "selection, inventory scoping, DOM evidence, fallback handling, and rerun behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
