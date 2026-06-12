#!/usr/bin/env python3
"""Run loaded-skill behavioral pressure scenarios for all canonical skills."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"
sys.path.append(str(TESTS_DIR))

from behavioral_harness import (  # noqa: E402
    GLOBAL_AGENT_ENV_VAR,
    GLOBAL_SCENARIO_FILTER_ENV_VAR,
    load_behavioral_scenarios,
    load_behavioral_suite_config,
    resolve_behavioral_agent_command,
    run_behavioral_suite_from_path,
)


def main() -> int:
    args = parse_args()
    skill_filter = args.skill or os.environ.get("BEHAVIORAL_SKILL", "").strip()
    scenario_filter = args.scenario or os.environ.get(GLOBAL_SCENARIO_FILTER_ENV_VAR, "").strip()

    try:
        suite_paths = discover_behavioral_suite_paths(skill_filter, scenario_filter)
        if args.list:
            print_suite_list(suite_paths)
            return 0

        missing_commands = [
            load_behavioral_suite_config(path).agent_env_var
            for path in suite_paths
            if not resolve_behavioral_agent_command(load_behavioral_suite_config(path).agent_env_var)
        ]
        if missing_commands:
            print_usage()
            raise RuntimeError(
                f"{GLOBAL_AGENT_ENV_VAR} or suite env vars are required: "
                + ", ".join(sorted(set(missing_commands)))
            )

        passed = 0
        for path in suite_paths:
            result = run_behavioral_suite_from_path(
                path,
                scenario_filter=scenario_filter or None,
            )
            if result != 0:
                return result
            passed += 1
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {passed} loaded-skill behavioral suites", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run TOML-backed loaded-skill behavioral pressure suites.",
    )
    parser.add_argument("--skill", help="Run one skill suite, for example codebase-scope-map.")
    parser.add_argument("--scenario", help="Run one scenario id across matching suites.")
    parser.add_argument("--list", action="store_true", help="List discovered suites and exit.")
    return parser.parse_args()


def discover_behavioral_suite_paths(
    skill_filter: str = "",
    scenario_filter: str = "",
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for scenarios_path in sorted(TESTS_DIR.glob("*/scenarios.toml")):
        if scenarios_path.parent.name == "skill-trigger":
            continue
        config = load_behavioral_suite_config(scenarios_path)
        if skill_filter and skill_filter not in {config.skill_name, scenarios_path.parent.name}:
            continue
        if scenario_filter and not scenario_exists(scenarios_path, scenario_filter):
            continue
        paths.append(scenarios_path)

    if not paths:
        detail = []
        if skill_filter:
            detail.append(f"skill={skill_filter!r}")
        if scenario_filter:
            detail.append(f"scenario={scenario_filter!r}")
        suffix = " for " + ", ".join(detail) if detail else ""
        raise ValueError(f"no loaded-skill behavioral suites found{suffix}")

    return tuple(paths)


def scenario_exists(scenarios_path: Path, scenario_id: str) -> bool:
    return any(
        scenario.scenario_id == scenario_id
        for scenario in load_behavioral_scenarios(scenarios_path)
    )


def print_suite_list(paths: tuple[Path, ...]) -> None:
    for path in paths:
        config = load_behavioral_suite_config(path)
        scenario_count = len(load_behavioral_scenarios(path))
        print(
            f"{config.skill_name}: {path.relative_to(REPO_ROOT)} "
            f"({scenario_count} scenarios, env {config.agent_env_var})"
        )


def print_usage() -> None:
    print(
        f"""Usage:
  {GLOBAL_AGENT_ENV_VAR}='<command reading stdin>' python3 tests/behavioral_pressure.py

Optional:
  BEHAVIORAL_SKILL='<skill-name>' or --skill <skill-name>
  {GLOBAL_SCENARIO_FILTER_ENV_VAR}='<scenario-id>' or --scenario <scenario-id>

Per-suite agent env vars are still supported for compatibility.
""",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
