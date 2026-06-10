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
    required_terms = (
        "Produce a compact, read-only map",
        "You are a read-only codebase scoping agent",
        "Do not mutate the repository",
        "no file edits",
        "generated-file writes",
        "formatting rewrites",
        "dependency changes",
        "staging, commits, or cleanup changes",
        "Scoping output is the only deliverable",
        "Proposing the solution, selecting an implementation approach, or writing code",
    )
    for term in required_terms:
        assert_contains(skill, term)

    forbidden_terms = (
        "small edits are allowed",
        "minor edits are allowed",
        "cleanup edits are allowed",
        "formatting-only edits are allowed",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term)


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
