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
        check_canonical_skills_have_behavioral_pressure()
        check_behavioral_pressure_uses_toml_scenarios()
        check_manual_behavior_docs_were_migrated()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: canonical skills use repo-level behavioral pressure tests")
    return 0


def check_canonical_skills_have_behavioral_pressure() -> None:
    missing: list[str] = []
    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_name = skill_file.parent.name
        behavioral_tests = sorted((TESTS_DIR / skill_name).glob("*behavioral_pressure.py"))
        if not behavioral_tests:
            missing.append(f"{skill_name} ({skill_file.relative_to(REPO_ROOT)})")

    if missing:
        raise AssertionError(
            "canonical skills missing repo-level behavioral pressure tests: "
            + ", ".join(missing)
        )


def check_behavioral_pressure_uses_toml_scenarios() -> None:
    missing_toml: list[str] = []
    embedded_scenarios: list[str] = []

    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_name = skill_file.parent.name
        for behavioral_test in sorted((TESTS_DIR / skill_name).glob("*behavioral_pressure.py")):
            if not (behavioral_test.parent / "scenarios.toml").exists():
                missing_toml.append(str(behavioral_test.relative_to(REPO_ROOT)))
            source = behavioral_test.read_text(encoding="utf-8")
            if "SCENARIOS =" in source or "SemanticCriterion(" in source:
                embedded_scenarios.append(str(behavioral_test.relative_to(REPO_ROOT)))

    if missing_toml:
        raise AssertionError(
            "canonical behavioral pressure tests must load sibling scenarios.toml: "
            + ", ".join(missing_toml)
        )
    if embedded_scenarios:
        raise AssertionError(
            "canonical behavioral pressure scenarios belong in scenarios.toml, not Python: "
            + ", ".join(embedded_scenarios)
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
