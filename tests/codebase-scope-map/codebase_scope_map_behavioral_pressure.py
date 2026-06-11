#!/usr/bin/env python3
"""Behavioral pressure tests for codebase-scope-map."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "codebase-scope-map" / "SKILL.md"
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="codebase-scope-map",
        skill_name="codebase-scope-map",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
        agent_env_var="CODEBASE_SCOPE_MAP_AGENT_COMMAND",
        scenario_filter_env_var="CODEBASE_SCOPE_MAP_SCENARIO",
        prompt_instructions=(
            "Do not inspect a real repository. Return only the scoping behavior, "
            "output shape, and boundaries the scoping agent should follow. Include "
            "the read-only boundary explicitly. For UI/reference scenarios, call out "
            "prototype/reference and affected-surface-map expectations explicitly."
        ),
        judge_context=(
            "Loaded skill under test: codebase-scope-map. Judge scope-map behavior, "
            "read-only boundaries, locator discipline, and compactness. These scenarios "
            "ask for the behavior and report contract only; do not require actual "
            "repository file paths when the prompt says not to inspect a real repo."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
