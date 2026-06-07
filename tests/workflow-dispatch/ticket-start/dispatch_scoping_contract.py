#!/usr/bin/env python3
"""Contract checks for ticket-start dispatching Scoping before downstream work."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_contract(skill)
    except Exception as error:
        print(f"FAIL: {SKILL_PATH.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start dispatches Scoping before downstream work")
    return 0


def check_contract(skill: str) -> None:
    required_terms = (
        "Scoping dispatch wording",
        "dispatches the Scoping subagent",
        "self-contained codebase mapping request",
        "token-efficient navigable scope map",
        "file:line locators",
        "entry points",
        "target modules/components",
        "types/contracts",
        "tests",
        "affected surfaces",
        "suggested downstream slices",
    )
    for term in required_terms:
        assert_contains(skill, term)

    assert_not_contains(skill, "agents/scoping.md")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
