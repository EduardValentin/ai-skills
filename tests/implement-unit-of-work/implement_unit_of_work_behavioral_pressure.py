#!/usr/bin/env python3
"""Behavioral pressure tests for implement-unit-of-work."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "implement-unit-of-work" / "SKILL.md"
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
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("IMPLEMENT_UNIT_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: IMPLEMENT_UNIT_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("IMPLEMENT_UNIT_SCENARIO", "").strip()
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

    print(f"PASS: {len(scenarios)} implement-unit-of-work behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  IMPLEMENT_UNIT_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/implement-unit-of-work/implement_unit_of_work_behavioral_pressure.py

Optional:
  IMPLEMENT_UNIT_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows the implement-unit-of-work skill.

Loaded skill: implement-unit-of-work

<skill>
{skill}
</skill>

User request:
{scenario.user_request}

Do not perform real implementation. Return only the implementation approach and report behavior the implementer should use. Keep it concise.
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
            context="Loaded skill under test: implement-unit-of-work. Judge implementation behavior and report boundaries.",
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
