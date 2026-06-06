#!/usr/bin/env python3
"""Deterministic contract checks for workflow-dispatch scenarios."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCENARIOS_PATH = SCRIPT_DIR / "scenarios.toml"
sys.path.append(str(REPO_ROOT / "tests" / "skill-trigger"))

from trigger_scenarios import load_scenarios as load_toml_scenarios  # noqa: E402


def main() -> int:
    try:
        scenarios = load_scenarios()
        check_scenarios(scenarios)
        nested_count = run_nested_contracts()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(
        f"PASS: {len(scenarios)} workflow-dispatch scenarios and "
        f"{nested_count} grouped contracts satisfy static contracts"
    )
    return 0


def load_scenarios() -> list[dict[str, object]]:
    scenarios = load_toml_scenarios(SCENARIOS_PATH)
    if not scenarios:
        raise ValueError(f"{SCENARIOS_PATH} must define at least one [[scenario]] table")
    return scenarios


def check_scenarios(scenarios: list[dict[str, object]]) -> None:
    seen_ids: set[str] = set()
    for scenario in scenarios:
        scenario_id = required_string(scenario, "id")
        skill = required_string(scenario, "skill")

        if scenario_id in seen_ids:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen_ids.add(scenario_id)

        skill_file = REPO_ROOT / "skills" / skill / "SKILL.md"
        if not skill_file.exists():
            raise ValueError(f"{scenario_id} references missing skill: {skill_file}")

        skill_doc = skill_file.read_text(encoding="utf-8")
        for term in string_list(scenario, "required_skill_terms"):
            assert_contains(skill_doc, term, f"{scenario_id} skill document")
        for term in string_list(scenario, "forbidden_skill_terms"):
            assert_not_contains(skill_doc, term, f"{scenario_id} skill document")


def run_nested_contracts() -> int:
    scripts = sorted(SCRIPT_DIR.glob("*/*_contract.py"))
    for script in scripts:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode != 0:
            raise RuntimeError(
                f"{script.relative_to(REPO_ROOT)} failed with exit code {completed.returncode}"
            )
    return len(scripts)


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
        raise ValueError(f"{context} must contain: {needle}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise ValueError(f"{context} must not contain: {needle}")


if __name__ == "__main__":
    raise SystemExit(main())
