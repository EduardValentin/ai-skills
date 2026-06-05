#!/usr/bin/env python3
"""Run workflow-dispatch scenarios against an agent command."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCENARIOS_PATH = SCRIPT_DIR / "scenarios.toml"
sys.path.append(str(REPO_ROOT / "tests" / "skill-trigger"))

from trigger_scenarios import load_scenarios as load_toml_scenarios  # noqa: E402


def main() -> int:
    agent_command = (
        os.environ.get("WORKFLOW_DISPATCH_AGENT_COMMAND", "").strip()
        or os.environ.get("SKILL_TRIGGER_AGENT_COMMAND", "").strip()
    )
    scenario_filter = os.environ.get("WORKFLOW_DISPATCH_SCENARIO", "").strip()

    if "--help" in sys.argv:
        print_usage()
        return 0

    if not agent_command:
        print_usage()
        print(
            "FAIL: WORKFLOW_DISPATCH_AGENT_COMMAND or SKILL_TRIGGER_AGENT_COMMAND is required",
            file=sys.stderr,
        )
        return 1

    try:
        scenarios = [
            scenario
            for scenario in load_scenarios()
            if not scenario_filter or scenario["id"] == scenario_filter
        ]
        if not scenarios:
            raise ValueError("no workflow-dispatch scenarios matched")

        for scenario in scenarios:
            run_scenario(agent_command, scenario)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(scenarios)} behavioral workflow-dispatch scenarios", flush=True)
    return 0


def print_usage() -> None:
    print(
        """Usage:
  WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/workflow-dispatch/behavioral_dispatch.py

Fallback:
  If WORKFLOW_DISPATCH_AGENT_COMMAND is unset, SKILL_TRIGGER_AGENT_COMMAND is used.

Optional:
  WORKFLOW_DISPATCH_SCENARIO='<scenario-id>' to run one scenario.

The agent command receives a prompt on stdin and must print a workflow action
ledger on stdout. The harness checks that required dispatch actions and prompt
terms appear in the right order."""
    )


def load_scenarios() -> list[dict[str, object]]:
    scenarios = load_toml_scenarios(SCENARIOS_PATH)
    if not scenarios:
        raise ValueError(f"{SCENARIOS_PATH} must define at least one [[scenario]] table")
    return scenarios


def run_scenario(agent_command: str, scenario: dict[str, object]) -> None:
    scenario_id = required_string(scenario, "id")
    response = run_agent(agent_command, make_prompt(scenario))

    for term in string_list(scenario, "required_response_terms"):
        assert_contains(response, term, f"{scenario_id} response")
    for term in string_list(scenario, "forbidden_response_terms"):
        assert_not_contains(response, term, f"{scenario_id} response")

    scoping_index = first_index(response, "DISPATCH_SUBAGENT", "Scoping")
    if scoping_index < 0:
        print(f"Response for {scenario_id}:\n{response}", file=sys.stderr)
        raise ValueError(f"{scenario_id} did not include a Scoping DISPATCH_SUBAGENT action")

    for term in string_list(scenario, "must_precede_terms"):
        later_index = response.find(term)
        if later_index >= 0 and later_index < scoping_index:
            print(f"Response for {scenario_id}:\n{response}", file=sys.stderr)
            raise ValueError(f"{scenario_id} mentioned {term!r} before Scoping dispatch")

    prefix = response[:scoping_index].lower()
    if "local" in prefix and ("scope" in prefix or "map" in prefix):
        print(f"Response for {scenario_id}:\n{response}", file=sys.stderr)
        raise ValueError(f"{scenario_id} performed local scoping before Scoping dispatch")

    print(f"PASS: {scenario_id} dispatched Scoping before downstream phases", flush=True)


def run_agent(agent_command: str, prompt: str) -> str:
    completed = subprocess.run(
        agent_command,
        input=prompt,
        text=True,
        shell=True,
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


def make_prompt(scenario: dict[str, object]) -> str:
    skill = required_string(scenario, "skill")
    skill_doc = (REPO_ROOT / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    prompt = required_string(scenario, "prompt")

    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: {skill}

<skill>
{skill_doc}
</skill>

User request:
{prompt}

Do not perform the user's task. Do not call tools. Based only on the loaded skill,
return the first workflow actions the main agent must take.

Return only action lines in this exact shape:
ACTION: <number> | <kind> | <target> | <details>

Use kind DISPATCH_SUBAGENT for any mandatory subagent dispatch. For subagent
dispatch details, include the prompt intent and the compact inputs that must be
forwarded. Include enough detail for a test to verify whether the prompt is a
self-contained work request with the required evidence terms.
"""


def required_string(scenario: dict[str, object], key: str) -> str:
    value = scenario.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"scenario is missing non-empty string field {key!r}")
    return value.strip()


def string_list(scenario: dict[str, object], key: str) -> list[str]:
    value = scenario.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"scenario {required_string(scenario, 'id')} field {key!r} must be a string list")
    return value


def assert_contains(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        print(f"{context}:\n{haystack}", file=sys.stderr)
        raise ValueError(f"{context} must contain: {needle}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        print(f"{context}:\n{haystack}", file=sys.stderr)
        raise ValueError(f"{context} must not contain: {needle}")


def first_index(haystack: str, *needles: str) -> int:
    for line in haystack.splitlines():
        if all(needle in line for needle in needles):
            return haystack.find(line)
    return -1


if __name__ == "__main__":
    raise SystemExit(main())
