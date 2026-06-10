"""Shared runner for workflow-dispatch behavioral pressure tests."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
TESTS_DIR = REPO_ROOT / "tests"
sys.path.append(str(TESTS_DIR))
sys.path.append(str(SCRIPT_DIR))

from auto_discovery import action_lines, assert_auto_discovers  # noqa: E402
from behavioral_harness import (  # noqa: E402
    BehavioralScenario,
    check_semantic_response,
    run_agent,
    select_scenarios,
)
from semantic_judge import resolve_judge_command  # noqa: E402


ResponseCheck = Callable[[str], None]


@dataclass(frozen=True)
class WorkflowDispatchScenario(BehavioralScenario):
    prompt_instructions: str = ""
    expected_auto_discovery: tuple[str, ...] = ()
    require_action_ledger: bool = False
    first_action_contains: tuple[str, ...] = ()
    required_action_contains: tuple[tuple[str, ...], ...] = ()
    response_checks: tuple[ResponseCheck, ...] = ()


def run_workflow_dispatch_suite(
    *,
    suite_name: str,
    parent_skill_name: str,
    skill_path: Path,
    scenarios: tuple[WorkflowDispatchScenario, ...],
    scenario_filter_env_var: str,
    fallback_agent_env_var: str = "SKILL_TRIGGER_AGENT_COMMAND",
) -> int:
    if "--help" in sys.argv:
        print_usage(scenario_filter_env_var, sys.argv[0])
        return 0

    agent_command = (
        os.environ.get("WORKFLOW_DISPATCH_AGENT_COMMAND", "").strip()
        or os.environ.get(fallback_agent_env_var, "").strip()
    )
    if not agent_command:
        print_usage(scenario_filter_env_var, sys.argv[0])
        print(
            f"FAIL: WORKFLOW_DISPATCH_AGENT_COMMAND or {fallback_agent_env_var} is required",
            file=sys.stderr,
        )
        return 1

    try:
        selected = select_scenarios(scenarios, os.environ.get(scenario_filter_env_var, "").strip())
        skill_text = skill_path.read_text(encoding="utf-8")
        judge_command = resolve_judge_command(agent_command)
        for scenario in selected:
            response = run_agent(
                agent_command,
                build_workflow_prompt(
                    parent_skill_name=parent_skill_name,
                    skill_text=skill_text,
                    scenario=scenario,
                ),
            )
            check_workflow_response(
                response=response,
                scenario=scenario,
                agent_command=agent_command,
                judge_command=judge_command,
                parent_skill_name=parent_skill_name,
            )
            print(f"PASS: {scenario.scenario_id}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(selected)} {suite_name}")
    return 0


def build_workflow_prompt(
    *,
    parent_skill_name: str,
    skill_text: str,
    scenario: WorkflowDispatchScenario,
) -> str:
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: {parent_skill_name}

<skill>
{skill_text}
</skill>

User request:
{scenario.user_request}

{scenario.prompt_instructions}
"""


def check_workflow_response(
    *,
    response: str,
    scenario: WorkflowDispatchScenario,
    agent_command: str,
    judge_command: str,
    parent_skill_name: str,
) -> None:
    try:
        if scenario.require_action_ledger:
            require_action_lines(
                response,
                first_action_contains=scenario.first_action_contains,
                required_action_contains=scenario.required_action_contains,
            )
        for check in scenario.response_checks:
            check(response)
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise
    check_semantic_response(
        scenario=scenario,
        response=response,
        judge_command=judge_command,
        judge_context=f"Loaded parent skill under test: {parent_skill_name}. Judge workflow dispatch behavior, not exact wording.",
    )
    try:
        for expected_skill in scenario.expected_auto_discovery:
            assert_auto_discovers(agent_command, response, expected_skill)
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


def require_action_lines(
    response: str,
    *,
    first_action_contains: tuple[str, ...] = (),
    required_action_contains: tuple[tuple[str, ...], ...] = (),
) -> list[str]:
    lines = action_lines(response)
    if not lines:
        raise AssertionError("missing ACTION lines")

    if first_action_contains:
        first_action = lines[0].casefold()
        missing = [term for term in first_action_contains if term.casefold() not in first_action]
        if missing:
            raise AssertionError(f"first action missing terms: {missing}")

    for required_terms in required_action_contains:
        if not any(all(term.casefold() in line.casefold() for term in required_terms) for line in lines):
            raise AssertionError(f"missing ACTION line containing terms: {required_terms}")

    return lines


def print_usage(scenario_filter_env_var: str, script_path: str) -> None:
    print(
        f"""Usage:
  WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' python3 {script_path}

Fallback:
  If WORKFLOW_DISPATCH_AGENT_COMMAND is unset, SKILL_TRIGGER_AGENT_COMMAND is used.

Optional:
  {scenario_filter_env_var}='<scenario-id>' to run one scenario.
"""
    )
