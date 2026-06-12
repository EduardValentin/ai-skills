#!/usr/bin/env python3
"""Contract checks for multi-ticket-work."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_contract(skill)
    except Exception as error:
        print(f"FAIL: {SKILL_PATH.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
        return 1

    print("PASS: multi-ticket-work contract")
    return 0


def check_contract(skill: str) -> None:
    assert_line_count_at_most(skill, 105)

    forbidden_terms = (
        "readiness ledger",
        "Ship readiness",
        "execute-ticket-work",
        "implement-unit-of-work",
        "qa-verification",
        "ui-verification",
        "verify-pr",
        "codebase-scope-map",
        "pr-reviewer-summary",
        "ticket-start",
        "ticket orchestrator",
        "ticket-orchestrator",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term)


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected multi-ticket-work to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
