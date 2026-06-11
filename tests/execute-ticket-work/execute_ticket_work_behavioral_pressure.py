#!/usr/bin/env python3
"""Behavioral pressure tests for execute-ticket-work."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "execute-ticket-work" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="approved-packet-execution-phase",
        user_request=(
            "An approved execution packet is available for one checkout eligibility work unit. "
            "It includes acceptance criteria, approved spec/design, approved implementation plan, "
            "scope locators, branch state, dependencies, expected checks, UI applicability, and PR/report expectations. "
            "Describe how execution should proceed without doing the work."
        ),
        criteria=(
            SemanticCriterion(
                "validates_packet_first",
                "The response validates the approved execution packet and execution boundary before starting work.",
            ),
            SemanticCriterion(
                "coordinates_separate_phases",
                "The response coordinates implementation, independent review, QA, UI/UX when applicable, fixes, reruns, and PR preparation as separate phases rather than one combined worker task.",
            ),
            SemanticCriterion(
                "supports_nested_phase_delegation",
                "The response uses nested delegated subagents for implementation, independent review, QA, UI/UX verification when applicable, scoped fixes, and PR preparation when the runtime supports it, or reports the limitation when it does not.",
            ),
            SemanticCriterion(
                "does_not_brainstorm_or_change_scope",
                "The response does not conduct brainstorming, invent requirements, negotiate scope, or change the approved plan during execution.",
            ),
            SemanticCriterion(
                "requires_phase_evidence_for_completion",
                "The response requires PR evidence plus implementation, independent review, QA, UI/UX-or-skip, fixes/reruns, checks, risks, and blockers before completion.",
            ),
            SemanticCriterion(
                "reports_parent_input_needed",
                "The response names parent/main-orchestrator input as the path for missing or conflicting approval/scope facts.",
            ),
        ),
        forbidden_terms=(
            "ticket-start",
            "multi-ticket-work",
            "implement-unit-of-work",
            "qa-verification",
            "ui-verification",
            "verify-pr",
            "ticket orchestrator",
            "best guess",
        ),
    ),
    Scenario(
        scenario_id="blocks-missing-approved-packet",
        user_request=(
            "A delegated execution request says only: 'work on the checkout thing and make it pass.' "
            "It has no approved spec, no implementation plan, no acceptance criteria, and no approval state. "
            "Describe the correct response."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_without_packet",
                "The response blocks execution when the approved execution packet is missing required details.",
            ),
            SemanticCriterion(
                "uses_blocked_parent_input_status",
                "The response reports BLOCKED_NEEDS_PARENT_INPUT or an equivalent explicit parent-input block.",
            ),
            SemanticCriterion(
                "names_missing_inputs",
                "The response names missing inputs such as acceptance criteria, approved spec/design, approved plan, approval state, or scope locators.",
            ),
            SemanticCriterion(
                "does_not_infer_or_brainstorm",
                "The response does not infer scope, brainstorm with the human, negotiate requirements, or proceed on a best guess.",
            ),
        ),
        forbidden_terms=(
            "start anyway",
            "best guess",
            "ticket-start",
            "multi-ticket-work",
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="execute-ticket-work",
        skill_name="execute-ticket-work",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="EXECUTE_TICKET_WORK_AGENT_COMMAND",
        scenario_filter_env_var="EXECUTE_TICKET_WORK_SCENARIO",
        prompt_instructions=(
            "Do not perform real execution. Return the execution-phase behavior and report expectations only. "
            "Explicitly describe how nested delegated subagents are used, or how the limitation is reported if unavailable. "
            "Keep it concise and do not name downstream skill identifiers."
        ),
        judge_context="Loaded skill under test: execute-ticket-work. Judge execution-phase boundaries, not exact wording.",
    )


if __name__ == "__main__":
    raise SystemExit(main())
