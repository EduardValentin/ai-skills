#!/usr/bin/env python3
"""Deterministic contract checks for grouped workflow-dispatch scenarios."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.append(str(REPO_ROOT / "tests"))
sys.path.append(str(SCRIPT_DIR))

from harness import load_workflow_scenario_payload  # noqa: E402
from nested_suite import run_grouped_python_scripts  # noqa: E402


def main() -> int:
    try:
        check_downstream_discovery_is_black_box()
        check_workflow_scenarios_have_auto_discovery()
        nested_count = run_nested_contracts()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {nested_count} grouped workflow-dispatch contracts satisfy static contracts")
    return 0


def run_nested_contracts() -> int:
    return run_grouped_python_scripts(
        suite_dir=SCRIPT_DIR,
        pattern="*/*_contract.py",
        missing_message="workflow-dispatch requires grouped *_contract.py tests",
    )


def check_downstream_discovery_is_black_box() -> None:
    helper = SCRIPT_DIR / "auto_discovery.py"
    source = helper.read_text(encoding="utf-8")
    forbidden = (
        "Available skills:",
        "discover_skill_files",
        "parse_frontmatter",
        "skill_index",
        "SKILL.md",
    )
    for term in forbidden:
        if term in source:
            raise ValueError(
                f"{helper.relative_to(REPO_ROOT)} must not inject skill context: {term}"
            )


def check_workflow_scenarios_have_auto_discovery() -> None:
    for scenarios_path in sorted(SCRIPT_DIR.glob("*/scenarios.toml")):
        payload = load_workflow_scenario_payload(scenarios_path)
        scenarios = payload.get("scenario", [])
        if not isinstance(scenarios, list):
            raise ValueError(f"{scenarios_path.relative_to(REPO_ROOT)} must define scenarios")
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                raise ValueError(f"{scenarios_path.relative_to(REPO_ROOT)} scenario must be a table")
            scenario_id = scenario.get("id", "<missing-id>")
            expected = scenario.get("expected_auto_discovery", [])
            if not isinstance(expected, list) or not expected:
                raise ValueError(
                    f"{scenarios_path.relative_to(REPO_ROOT)}:{scenario_id} must set "
                    "expected_auto_discovery; workflow-dispatch tests must prove "
                    "downstream black-box skill pickup"
                )

    for script in sorted(SCRIPT_DIR.glob("*/*_behavioral_pressure.py")):
        if (script.parent / "scenarios.toml").exists():
            continue
        source = script.read_text(encoding="utf-8")
        if "expected_auto_discovery" not in source:
            raise ValueError(
                f"{script.relative_to(REPO_ROOT)} must assert expected_auto_discovery; "
                "broad loaded-skill behavior belongs in the skill's behavioral tests"
            )


if __name__ == "__main__":
    raise SystemExit(main())
