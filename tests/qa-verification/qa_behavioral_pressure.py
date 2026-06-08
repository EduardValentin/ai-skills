#!/usr/bin/env python3
"""Behavioral pressure tests for qa-verification."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "qa-verification" / "SKILL.md"
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
        scenario_id="backend-api-live-behavior",
        user_request=(
            "Use the loaded qa-verification skill for a backend API change. "
            "Acceptance criteria require validating successful creation, duplicate "
            "rejection, auth boundaries, persisted state, and error payloads against "
            "the running service."
        ),
        criteria=(
            SemanticCriterion(
                "live_service_behavior",
                "The QA approach requires validating the running backend/service rather than relying only on unit tests or code inspection.",
            ),
            SemanticCriterion(
                "covers_api_outcomes",
                "The QA approach covers successful creation, duplicate rejection, auth boundaries, persisted state, and error payloads.",
            ),
            SemanticCriterion(
                "maps_acceptance_criteria_to_evidence",
                "The response requires the QA report to map each acceptance criterion to concrete observations and evidence.",
            ),
            SemanticCriterion(
                "bug_report_boundary",
                "The response includes a BUGS FOUND verdict path for failed behavior and requires reproduction steps and evidence for each bug.",
            ),
        ),
        forbidden_terms=(
            "unit tests are enough",
            "clean because tests passed",
            "before Ship",
            "visual parity",
            "UI/UX",
        ),
    ),
    Scenario(
        scenario_id="ui-behavior-states",
        user_request=(
            "Use the loaded qa-verification skill for a user-facing settings form. "
            "Exercise loading, empty, success, error, validation, disabled, rapid-click, "
            "and navigation-mid-save behavior in the running app."
        ),
        criteria=(
            SemanticCriterion(
                "running_app_ui_behavior",
                "The QA approach requires exercising the user-facing settings form in the running app.",
            ),
            SemanticCriterion(
                "covers_named_states_and_interactions",
                "The QA approach covers loading, empty, success, error, validation, disabled, rapid-click, and navigation-mid-save behavior.",
            ),
            SemanticCriterion(
                "reports_evidence_and_verdict",
                "The response describes a QA report with verdict, coverage performed, evidence, bugs, blockers, and notes.",
            ),
        ),
        forbidden_terms=(
            "visual parity",
            "style review",
            "UI/UX",
            "before Ship",
        ),
    ),
    Scenario(
        scenario_id="mixed-api-and-ui",
        user_request=(
            "Use the loaded qa-verification skill for a mixed invite flow where the "
            "invite API and invite form changed together. Verify backend behavior, "
            "browser-observed behavior, and the integration between them."
        ),
        criteria=(
            SemanticCriterion(
                "mixed_mode_covers_backend_and_ui",
                "The QA approach covers both invite API/backend behavior and browser-observed invite form behavior.",
            ),
            SemanticCriterion(
                "integration_between_surfaces",
                "The response verifies that API and UI behavior work together according to acceptance criteria.",
            ),
            SemanticCriterion(
                "reports_acceptance_coverage",
                "The response describes a QA report that ties checks, results, findings, and evidence back to acceptance criteria.",
            ),
        ),
        forbidden_terms=(
            "only backend",
            "only ui",
            "before Ship",
            "visual parity",
            "UI/UX",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("QA_VERIFICATION_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: QA_VERIFICATION_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("QA_VERIFICATION_SCENARIO", "").strip()
    scenarios = [scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter]
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

    print(f"PASS: {len(scenarios)} qa-verification behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  QA_VERIFICATION_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/qa-verification/qa_behavioral_pressure.py

Optional:
  QA_VERIFICATION_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows a QA verification skill.

Loaded skill: qa-verification

<skill>
{skill}
</skill>

User request:
{scenario.user_request}

Do not execute QA. Return only the QA approach and report shape the QA verifier should use. Keep it concise.
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
            context=(
                "Loaded skill under test: qa-verification. Judge QA behavior, scope, "
                "and report boundaries. The pressure prompt asks for the approach/report "
                "shape only; do not require proof that QA was actually executed."
            ),
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
