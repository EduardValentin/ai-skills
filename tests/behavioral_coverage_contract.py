#!/usr/bin/env python3
"""Contract checks for canonical skill behavioral pressure coverage."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
TESTS_DIR = REPO_ROOT / "tests"


def main() -> int:
    try:
        check_canonical_skills_have_behavioral_scenarios()
        check_behavioral_scenarios_have_suite_metadata()
        check_canonical_skill_dirs_do_not_have_behavioral_wrappers()
        check_manual_behavior_docs_were_migrated()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: canonical skills use TOML-backed behavioral pressure tests")
    return 0


def check_canonical_skills_have_behavioral_scenarios() -> None:
    missing: list[str] = []
    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_name = skill_file.parent.name
        scenarios_path = TESTS_DIR / skill_name / "scenarios.toml"
        if not scenarios_path.exists():
            missing.append(f"{skill_name} ({skill_file.relative_to(REPO_ROOT)})")

    if missing:
        raise AssertionError(
            "canonical skills missing repo-level behavioral scenarios: "
            + ", ".join(missing)
        )


def check_behavioral_scenarios_have_suite_metadata() -> None:
    missing_suite: list[str] = []
    stale_metadata: list[str] = []

    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_name = skill_file.parent.name
        scenarios_path = TESTS_DIR / skill_name / "scenarios.toml"
        source = scenarios_path.read_text(encoding="utf-8")
        if not source.lstrip().startswith("[suite]"):
            missing_suite.append(str(scenarios_path.relative_to(REPO_ROOT)))
            continue
        expected = (
            f'skill = "{skill_name}"',
            f'skill_path = "skills/{skill_name}/SKILL.md"',
            "agent_env = ",
            "scenario_env = ",
            "prompt_instructions = ",
            "judge_context = ",
        )
        missing = [item for item in expected if item not in source]
        if missing:
            stale_metadata.append(
                f"{scenarios_path.relative_to(REPO_ROOT)} missing {missing}"
            )

    if missing_suite:
        raise AssertionError(
            "canonical behavioral scenarios must start with [suite] metadata: "
            + ", ".join(missing_suite)
        )
    if stale_metadata:
        raise AssertionError(
            "canonical behavioral scenario suite metadata is incomplete: "
            + ", ".join(stale_metadata)
        )


def check_canonical_skill_dirs_do_not_have_behavioral_wrappers() -> None:
    wrappers: list[str] = []

    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_name = skill_file.parent.name
        wrappers.extend(
            str(path.relative_to(REPO_ROOT))
            for path in sorted((TESTS_DIR / skill_name).glob("*behavioral_pressure.py"))
        )

    if wrappers:
        raise AssertionError(
            "canonical skill behavioral suites must be TOML-only; use "
            "tests/behavioral_pressure.py instead of per-skill wrappers: "
            + ", ".join(wrappers)
        )


def check_manual_behavior_docs_were_migrated() -> None:
    forbidden_names = {"pressure-scenarios.md", "evals.md", "test-log.md"}
    leftovers = [
        path.relative_to(REPO_ROOT)
        for path in sorted(SKILLS_DIR.glob("*/tests/*.md"))
        if path.name in forbidden_names
    ]
    if leftovers:
        raise AssertionError(
            "manual skill behavior docs should be migrated to repo-level TOML scenario tests: "
            + ", ".join(str(path) for path in leftovers)
        )


if __name__ == "__main__":
    raise SystemExit(main())
