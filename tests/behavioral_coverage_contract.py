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


def check_manual_behavior_docs_were_migrated() -> None:
    forbidden_names = {"pressure-scenarios.md", "evals.md", "test-log.md"}
    leftovers = [
        path.relative_to(REPO_ROOT)
        for path in sorted(SKILLS_DIR.glob("*/tests/*.md"))
        if path.name in forbidden_names
    ]
    if leftovers:
        raise AssertionError(
            "manual skill behavior docs should be migrated to Python harness tests: "
            + ", ".join(str(path) for path in leftovers)
        )


if __name__ == "__main__":
    raise SystemExit(main())
