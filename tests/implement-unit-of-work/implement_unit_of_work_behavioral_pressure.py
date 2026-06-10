#!/usr/bin/env python3
"""Behavioral pressure tests for implement-unit-of-work."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "implement-unit-of-work" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import (  # noqa: E402
    SemanticCriterion,
)


SCENARIOS = (
    Scenario(
        scenario_id="approved-ad-hoc-script-implementation",
        user_request=(
            "Use the loaded implement-unit-of-work skill for an approved ad hoc request: "
            "add a repository script that exports stale feature flags. Acceptance criteria, "
            "design direction, implementation plan, and scope notes are approved. Do not edit "
            "files; return the implementation approach and final report shape."
        ),
        criteria=(
            SemanticCriterion(
                "works_for_non_ticket_code_unit",
                "The response treats an ad hoc script as a valid implementation unit, not only a ticket work unit.",
            ),
            SemanticCriterion(
                "requires_approved_inputs_and_scope",
                "The response depends on approved requirements/design direction, acceptance criteria, implementation plan, and codebase scope before coding.",
            ),
            SemanticCriterion(
                "reads_architecture_broadly",
                "The response plans to inspect relevant files beyond the direct edit, including callers, contracts, analogous code, tests, or architecture surfaces.",
            ),
            SemanticCriterion(
                "uses_tdd_when_feasible",
                "The response requires TDD for required features or bug fixes when the project harness supports it: write or update a failing test first, observe the expected failure, implement to green, and report the evidence or a concrete skip rationale.",
            ),
            SemanticCriterion(
                "clean_code_standards",
                "The response emphasizes clear names, focused responsibilities, three-or-fewer parameters, maintainability, and performance.",
            ),
            SemanticCriterion(
                "delegates_self_review",
                "The response requires self-review of the produced work to be delegated to a separate subagent.",
            ),
            SemanticCriterion(
                "implementation_report_shape",
                "The response returns an implementation report shape with changed files, TDD evidence or skip rationale, local checks, delegated self-review result, engineering notes, and risks or blockers.",
            ),
        ),
        forbidden_terms=(
            "QA verification",
            "UI/UX verification",
            "ready to ship",
            "ready to merge",
        ),
    ),
    Scenario(
        scenario_id="blocked-missing-approved-plan",
        user_request=(
            "Use the loaded implement-unit-of-work skill, but the request only says "
            "'add whatever script seems useful' and provides no accepted requirements, "
            "acceptance criteria, approved plan, or scope notes. Describe the correct response."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_without_approved_inputs",
                "The response blocks implementation when approved requirements, acceptance criteria, implementation plan, or scope are missing.",
            ),
            SemanticCriterion(
                "names_missing_inputs",
                "The response names the missing inputs needed before coding can start.",
            ),
            SemanticCriterion(
                "does_not_best_guess",
                "The response avoids best-guess coding or inventing scope from an underspecified request.",
            ),
        ),
        forbidden_terms=(
            "start coding anyway",
            "best guess",
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="implement-unit-of-work",
        skill_name="implement-unit-of-work",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="IMPLEMENT_UNIT_AGENT_COMMAND",
        scenario_filter_env_var="IMPLEMENT_UNIT_SCENARIO",
        prompt_instructions=(
            "Do not perform real implementation. Return only the implementation approach "
            "and report behavior the implementer should use. Keep it concise."
        ),
        judge_context=(
            "Loaded skill under test: implement-unit-of-work. "
            "Judge implementation behavior and report boundaries."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
