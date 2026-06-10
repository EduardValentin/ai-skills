#!/usr/bin/env python3
"""Behavioral pressure tests for design-studio."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "design-studio" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="large-reference-app-context-digest",
        user_request=(
            "A user asks for a dashboard redesign in a React reference app. The project "
            "has a large DESIGN.md, brand-voice.md, PRD.md, Tailwind theme files, a "
            "router, and 80 components. A context-isolated worker is available. The "
            "user says to skim files quickly and start because there is no time."
        ),
        criteria=(
            SemanticCriterion(
                "delegates_context_digest",
                "The response delegates or otherwise isolates the project-context digest instead of loading all raw docs, routes, theme files, and component trees into the main session.",
            ),
            SemanticCriterion(
                "uses_compact_digest_then_targeted_reads",
                "The response says the main session proceeds from the compact digest, screenshots/rendered signals, and targeted implementation reads only.",
            ),
            SemanticCriterion(
                "does_not_skip_due_to_time_pressure",
                "The response does not treat time pressure as a reason to skip context discipline or infer from target files only.",
            ),
        ),
        forbidden_terms=("read everything inline", "skip the digest"),
    ),
    Scenario(
        scenario_id="broad-audit-context-isolation",
        user_request=(
            "Audit six reference-app pages for clutter, reusable components, semantic-token "
            "drift, brand-copy issues, responsive problems, and screenshot-visible flaws. "
            "Screenshots and context-isolated workers are available."
        ),
        criteria=(
            SemanticCriterion(
                "delegates_broad_inventory",
                "The response delegates broad inventory or critique work because the audit spans three or more pages/components/routes.",
            ),
            SemanticCriterion(
                "main_context_receives_ranked_summary",
                "The response keeps the main context focused on screenshots, ranked findings, compact summaries, and targeted source reads.",
            ),
            SemanticCriterion(
                "structured_critique_before_implementation",
                "The response produces or requests a structured critique and ranked fix summary before implementation.",
            ),
        ),
    ),
    Scenario(
        scenario_id="prd-generation-from-existing-app",
        user_request=(
            "No PRD.md exists. The user approves generating one from the current React "
            "reference app, which has many routes, mock entities, forms, modals, and "
            "role-specific flows. Code analysis can be delegated."
        ),
        criteria=(
            SemanticCriterion(
                "delegates_app_analysis",
                "The response delegates the code-analysis pass when context isolation is available instead of reading the whole app inline.",
            ),
            SemanticCriterion(
                "uses_product_report_and_screenshots",
                "The response writes the PRD from screenshots plus a structured product/business analysis report, not raw app-file transcripts.",
            ),
            SemanticCriterion(
                "fallback_only_when_no_isolation",
                "The response falls back to inline analysis only if no context-isolated mechanism exists and keeps that fallback compact.",
            ),
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="design-studio",
        skill_name="design-studio",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="DESIGN_STUDIO_AGENT_COMMAND",
        scenario_filter_env_var="DESIGN_STUDIO_SCENARIO",
        prompt_instructions=(
            "Do not inspect files or implement UI. Return only the next workflow action "
            "and context-discipline behavior the design-studio agent should follow."
        ),
        judge_context=(
            "Loaded skill under test: design-studio. Judge context isolation, reference-app "
            "workflow discipline, and PRD/design audit behavior."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
