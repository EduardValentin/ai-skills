#!/usr/bin/env python3
"""Contract checks for implement-unit-of-work."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "implement-unit-of-work" / "SKILL.md"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
MULTI_TICKET_WORK = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_skill_contract(skill)
        check_orchestrator(TICKET_START.read_text(encoding="utf-8"))
        check_orchestrator(MULTI_TICKET_WORK.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: implement-unit-of-work contract")
    return 0


def check_skill_contract(skill: str) -> None:
    assert_line_count_at_most(skill, 130)

    required_terms = (
        "name: implement-unit-of-work",
        "approved unit of code",
        "approved requirements/design direction",
        "approved implementation plan",
        "codebase scope",
        "Inspect the relevant code ambitiously before editing",
        "nearby callers/callees",
        "Use TDD for required features and bug fixes",
        "write or update a focused failing test first",
        "TDD evidence",
        "Preserve the surrounding application architecture",
        "Keep new or changed methods/functions to three parameters or fewer",
        "Self-review is required and must be delegated to a separate subagent",
        "Performance/maintainability notes",
    )
    for term in required_terms:
        assert_contains(skill, term)

    forbidden_terms = (
        "QA verification",
        "UI/UX verification",
        "QA/UIUX",
        "ready for verification",
        "readiness ledger",
        "Ship readiness",
        "ticket-state",
        "handoff notes for QA",
        "UI/UX focus",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term, "implement-unit-of-work")


def check_orchestrator(skill: str) -> None:
    assert_not_contains(skill, "implement-unit-of-work", "orchestrator skill")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected implement-unit-of-work to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
