"""Shared runner for loaded-skill behavioral pressure tests."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from semantic_judge import (  # noqa: E402
    SemanticCriterion,
    assert_forbidden_terms,
    judge_response,
    resolve_judge_command,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class BehavioralScenario:
    scenario_id: str
    user_request: str
    criteria: tuple[SemanticCriterion, ...]
    forbidden_terms: tuple[str, ...] = ()


PromptBuilder = Callable[[str, BehavioralScenario], str]


def run_loaded_skill_behavioral_suite(
    *,
    suite_name: str,
    skill_name: str,
    skill_path: Path,
    scenarios: tuple[BehavioralScenario, ...],
    agent_env_var: str,
    scenario_filter_env_var: str,
    prompt_instructions: str,
    judge_context: str,
    prompt_builder: PromptBuilder | None = None,
) -> int:
    if "--help" in sys.argv:
        print_usage(agent_env_var, scenario_filter_env_var, sys.argv[0])
        return 0

    agent_command = os.environ.get(agent_env_var, "").strip()
    if not agent_command:
        print_usage(agent_env_var, scenario_filter_env_var, sys.argv[0])
        print(f"FAIL: {agent_env_var} is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get(scenario_filter_env_var, "").strip()
    try:
        selected = select_scenarios(scenarios, scenario_filter)
        skill_text = skill_path.read_text(encoding="utf-8")
        judge_command = resolve_judge_command(agent_command)
        builder = prompt_builder or (
            lambda text, scenario: build_loaded_skill_prompt(
                skill_name=skill_name,
                skill_text=text,
                scenario=scenario,
                prompt_instructions=prompt_instructions,
            )
        )

        for scenario in selected:
            response = run_agent(agent_command, builder(skill_text, scenario))
            check_semantic_response(
                scenario=scenario,
                response=response,
                judge_command=judge_command,
                judge_context=judge_context,
            )
            print(f"PASS: {scenario.scenario_id}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(selected)} {suite_name} behavioral scenarios")
    return 0


def build_loaded_skill_prompt(
    *,
    skill_name: str,
    skill_text: str,
    scenario: BehavioralScenario,
    prompt_instructions: str,
) -> str:
    return f"""You are pressure-testing whether an agent follows the {skill_name} skill.

Loaded skill: {skill_name}

<skill>
{skill_text}
</skill>

User request:
{scenario.user_request}

{prompt_instructions}
"""


def select_scenarios(
    scenarios: tuple[BehavioralScenario, ...],
    scenario_filter: str,
) -> tuple[BehavioralScenario, ...]:
    if not scenario_filter:
        return scenarios

    selected = tuple(scenario for scenario in scenarios if scenario.scenario_id == scenario_filter)
    if not selected:
        raise ValueError(f"no scenario matched {scenario_filter!r}")
    return selected


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


def check_semantic_response(
    *,
    scenario: BehavioralScenario,
    response: str,
    judge_command: str,
    judge_context: str,
) -> None:
    try:
        assert_forbidden_terms(response, scenario.forbidden_terms, scenario.scenario_id)
        judge_response(
            judge_command=judge_command,
            scenario_id=scenario.scenario_id,
            scenario_prompt=scenario.user_request,
            response=response,
            criteria=scenario.criteria,
            context=judge_context,
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


def print_usage(agent_env_var: str, scenario_filter_env_var: str, script_path: str) -> None:
    print(
        f"""Usage:
  {agent_env_var}='<command reading stdin>' python3 {script_path}

Optional:
  {scenario_filter_env_var}='<scenario-id>' to run one scenario.
"""
    )
