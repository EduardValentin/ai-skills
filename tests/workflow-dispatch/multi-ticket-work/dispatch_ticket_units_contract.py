#!/usr/bin/env python3
"""Contract checks for multi-ticket-work workflow dispatch."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_dispatch_contract(skill)
    except Exception as error:
        print(f"FAIL: {SKILL_PATH.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
        return 1

    print("PASS: multi-ticket-work defines ticket-unit workflow dispatch")
    return 0


def check_dispatch_contract(skill: str) -> None:
    forbidden_terms = (
        "readiness ledger",
        "implement-unit-of-work",
        "qa-verification",
        "ui-verification",
        "codebase-scope-map",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term)

    assert_contains(skill, "Dispatch one subagent per ticket or unit of work")
    assert_contains(skill, "Each subagent owns the normal one-ticket workflow for its ticket or unit")
    assert_contains(skill, "Save an uncommitted orchestration note")
    assert_contains(skill, "Re-read it at the start of work, after any context compaction or resume")
    assert_contains(skill, "A ticket or unit is not complete until its subagent has opened a PR")
    assert_contains(skill, "returned a completion report")
    assert_contains(skill, "Put the PRs in the order the human should review them")
    assert_contains(skill, "Phrase it as a PR-description or reviewer-summary request")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
