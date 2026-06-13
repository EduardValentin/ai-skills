#!/usr/bin/env python3
"""Contract checks for the shared behavioral pressure harness."""

from __future__ import annotations

import sys
import tempfile
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import (  # noqa: E402
    BehavioralScenario,
    build_loaded_skill_prompt,
    load_behavioral_scenarios,
    load_behavioral_suite_config,
    resolve_behavioral_agent_command,
    select_scenarios,
)
from semantic_judge import SemanticCriterion  # noqa: E402


def main() -> int:
    try:
        check_behavioral_harness_contract()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: behavioral harness contract")
    return 0


def check_behavioral_harness_contract() -> None:
    scenario = BehavioralScenario(
        scenario_id="demo-scenario",
        user_request="Use the loaded demo skill.",
        criteria=(SemanticCriterion("does_demo", "The response does the demo behavior."),),
        forbidden_terms=("forbidden",),
    )

    prompt = build_loaded_skill_prompt(
        skill_name="demo",
        skill_text="DEMO SKILL BODY",
        scenario=scenario,
        prompt_instructions="Return the demo response shape.",
    )

    for expected in (
        "Loaded skill: demo",
        "<skill>",
        "DEMO SKILL BODY",
        "Use the loaded demo skill.",
        "Return the demo response shape.",
    ):
        assert_contains(prompt, expected)

    selected = select_scenarios((scenario,), "demo-scenario")
    if selected != (scenario,):
        raise AssertionError("select_scenarios should return the matching scenario tuple")

    if select_scenarios((scenario,), "") != (scenario,):
        raise AssertionError("select_scenarios should return all scenarios when no filter is set")

    try:
        select_scenarios((scenario,), "missing")
    except ValueError as error:
        assert_contains(str(error), "missing")
    else:
        raise AssertionError("select_scenarios should reject unknown scenario filters")

    with tempfile.TemporaryDirectory() as tmpdir:
        scenarios_path = Path(tmpdir) / "scenarios.toml"
        scenarios_path.write_text(
            """
[suite]
name = "demo-suite"
skill = "demo"
skill_path = "skills/demo/SKILL.md"
agent_env = "DEMO_AGENT_COMMAND"
scenario_env = "DEMO_SCENARIO"
prompt_instructions = "Return the demo response shape."
judge_context = "Judge demo behavior."

[[scenario]]
id = "loaded-from-toml"
user_request = "Use the loaded TOML scenario."
forbidden_terms = ["nope"]

[[scenario.criteria]]
key = "does_toml"
description = "The response follows the TOML scenario."
""".lstrip(),
            encoding="utf-8",
        )
        suite = load_behavioral_suite_config(scenarios_path)
        loaded = load_behavioral_scenarios(scenarios_path)

    if suite.suite_name != "demo-suite":
        raise AssertionError("loaded TOML suite name mismatch")
    if suite.skill_name != "demo":
        raise AssertionError("loaded TOML suite skill mismatch")
    if suite.agent_env_var != "DEMO_AGENT_COMMAND":
        raise AssertionError("loaded TOML suite agent env mismatch")
    if suite.scenario_filter_env_var != "DEMO_SCENARIO":
        raise AssertionError("loaded TOML suite scenario env mismatch")
    if len(loaded) != 1:
        raise AssertionError("load_behavioral_scenarios should return one scenario")
    if loaded[0].scenario_id != "loaded-from-toml":
        raise AssertionError("loaded TOML scenario id mismatch")
    if loaded[0].criteria[0].key != "does_toml":
        raise AssertionError("loaded TOML criterion mismatch")
    if loaded[0].forbidden_terms != ("nope",):
        raise AssertionError("loaded TOML forbidden terms mismatch")

    original_env = os.environ.copy()
    try:
        for key in ("DEMO_AGENT_COMMAND", "BEHAVIORAL_AGENT_COMMAND", "SKILL_TRIGGER_AGENT_COMMAND"):
            os.environ.pop(key, None)

        if resolve_behavioral_agent_command("DEMO_AGENT_COMMAND") != "":
            raise AssertionError("agent command should be empty when no env vars are set")

        os.environ["SKILL_TRIGGER_AGENT_COMMAND"] = "generic-cmd"
        if resolve_behavioral_agent_command("DEMO_AGENT_COMMAND") != "generic-cmd":
            raise AssertionError("generic harness command should be used as fallback")

        os.environ["BEHAVIORAL_AGENT_COMMAND"] = "behavioral-cmd"
        if resolve_behavioral_agent_command("DEMO_AGENT_COMMAND") != "behavioral-cmd":
            raise AssertionError("global behavioral command should override generic fallback")

        os.environ["DEMO_AGENT_COMMAND"] = "suite-cmd"
        if resolve_behavioral_agent_command("DEMO_AGENT_COMMAND") != "suite-cmd":
            raise AssertionError("suite command should override global fallbacks")
    finally:
        os.environ.clear()
        os.environ.update(original_env)


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
