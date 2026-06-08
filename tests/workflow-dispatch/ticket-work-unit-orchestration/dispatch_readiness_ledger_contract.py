#!/usr/bin/env python3
"""Contract checks for ticket-work-unit-orchestration workflow dispatch."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_dispatch_contract(skill)
    except Exception as error:
        print(f"FAIL: {SKILL_PATH.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-work-unit-orchestration defines readiness-ledger workflow dispatch")
    return 0


def check_dispatch_contract(skill: str) -> None:
    forbidden_terms = (
        "ticket-implementation-unit",
        "ticket-qa-verification",
        "frontend-ui-review",
        "codebase-scope-map",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term)


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
