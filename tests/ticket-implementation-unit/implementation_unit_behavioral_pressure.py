#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-implementation-unit."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-implementation-unit" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from semantic_judge import (  # noqa: E402
    SemanticCriterion,
    assert_forbidden_terms,
    judge_response,
    resolve_judge_command,
)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_request: str
    criteria: tuple[SemanticCriterion, ...]
    forbidden_terms: tuple[str, ...]


SCENARIOS = (
    Scenario(
        scenario_id="approved-slice-report",
        user_request=(
            "Use the loaded implementation-unit skill for an approved Invite Flow plan slice. "
            "Do not edit files. Return the implementation approach and final report shape the "
            "implementer should produce after coding."
        ),
        criteria=(
            SemanticCriterion(
                "approved_slice_report_shape",
                "The response describes an implementation report shape for an approved work-unit slice, including files/surfaces changed, local checks, decisions, risks/blockers, and handoff notes.",
            ),
            SemanticCriterion(
                "includes_implementer_self_review",
                "The response includes a distinct implementer self-review boundary as part of implementation evidence.",
            ),
            SemanticCriterion(
                "ready_for_verification_not_ship",
                "The response marks completed implementation as ready for downstream verification, not ready to ship or merge.",
            ),
            SemanticCriterion(
                "does_not_claim_qa_uiux",
                "The response makes clear QA and UI/UX verification are separate downstream evidence, not claimed by the implementer.",
            ),
        ),
        forbidden_terms=(
            "ready to ship",
            "ready to merge",
        ),
    ),
    Scenario(
        scenario_id="blocked-missing-scope",
        user_request=(
            "Use the loaded implementation-unit skill, but the request only says "
            "'fix the invite flow' and provides no approved plan slice or Scoping locators. "
            "Describe the correct response."
        ),
        criteria=(
            SemanticCriterion(
                "blocks_without_approved_scope",
                "The response blocks implementation when approved plan slice or scoping locators are missing.",
            ),
            SemanticCriterion(
                "requests_missing_inputs",
                "The response identifies the missing approved plan/scope inputs needed before coding can start.",
            ),
            SemanticCriterion(
                "does_not_best_guess",
                "The response avoids best-guess coding or starting implementation from an underspecified request.",
            ),
        ),
        forbidden_terms=(
            "start coding",
            "best guess",
        ),
    ),
    Scenario(
        scenario_id="self-review-not-qa",
        user_request=(
            "Use the loaded implementation-unit skill after a focused fix. Return the report "
            "boundary so the orchestrator knows this is self-reviewed implementation evidence, "
            "not QA or UI/UX completion."
        ),
        criteria=(
            SemanticCriterion(
                "self_review_is_implementation_evidence",
                "The response treats self-review as implementer evidence for the focused fix.",
            ),
            SemanticCriterion(
                "qa_uiux_remain_separate",
                "The response clearly says QA and UI/UX verification remain separate downstream checks.",
            ),
            SemanticCriterion(
                "no_global_completion_claim",
                "The response does not claim the unit or workflow is globally complete based only on implementer self-review.",
            ),
        ),
        forbidden_terms=(
            "globally complete",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("TICKET_IMPLEMENTATION_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: TICKET_IMPLEMENTATION_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("TICKET_IMPLEMENTATION_SCENARIO", "").strip()
    scenarios = [
        scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter
    ]
    if not scenarios:
        print(f"FAIL: no scenario matched {scenario_filter!r}", file=sys.stderr)
        return 1

    skill = SKILL_PATH.read_text(encoding="utf-8")
    judge_command = resolve_judge_command(agent_command)
    try:
        for scenario in scenarios:
            response = run_agent(agent_command, make_prompt(skill, scenario))
            check_response(scenario, response, judge_command)
            print(f"PASS: {scenario.scenario_id}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(scenarios)} ticket-implementation-unit behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  TICKET_IMPLEMENTATION_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/ticket-implementation-unit/implementation_unit_behavioral_pressure.py

Optional:
  TICKET_IMPLEMENTATION_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows an implementation-unit skill.

Loaded skill: ticket-implementation-unit

<skill>
{skill}
</skill>

User request:
{scenario.user_request}

Do not perform real implementation. Return only the approach/report behavior the
implementation agent should use. Keep it concise.
"""


def run_agent(agent_command: str, prompt: str) -> str:
    completed = subprocess.run(
        shlex.split(agent_command),
        input=prompt,
        text=True,
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "agent command failed with exit code "
            f"{completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed.stdout


def check_response(scenario: Scenario, response: str, judge_command: str) -> None:
    try:
        assert_forbidden_terms(response, scenario.forbidden_terms, scenario.scenario_id)
        judge_response(
            judge_command=judge_command,
            scenario_id=scenario.scenario_id,
            scenario_prompt=scenario.user_request,
            response=response,
            criteria=scenario.criteria,
            context="Loaded skill under test: ticket-implementation-unit. Judge behavior/report boundaries.",
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
