#!/usr/bin/env python3
"""Contract checks for multi-ticket-work workflow dispatch points."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_contract(skill)
    except Exception as error:
        print(f"FAIL: {SKILL_PATH.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
        return 1

    print("PASS: multi-ticket-work workflow dispatch points")
    return 0


def check_contract(skill: str) -> None:
    forbidden_skill_identifiers = (
        "ticket-start",
        "$ticket-start",
        "execute-ticket-work",
        "$execute-ticket-work",
        "implement-unit-of-work",
        "qa-verification",
        "ui-verification",
        "verify-pr",
        "codebase-scope-map",
        "ticket orchestrator",
        "ticket-orchestrator",
    )
    for identifier in forbidden_skill_identifiers:
        assert_not_contains(skill, identifier)


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
