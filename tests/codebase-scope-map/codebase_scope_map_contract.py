#!/usr/bin/env python3
"""Contract checks for codebase-scope-map."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "codebase-scope-map" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_skill_contract(skill)
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: codebase-scope-map contract")
    return 0


def check_skill_contract(skill: str) -> None:
    forbidden_terms = (
        "small edits are allowed",
        "minor edits are allowed",
        "cleanup edits are allowed",
        "formatting-only edits are allowed",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term)


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
