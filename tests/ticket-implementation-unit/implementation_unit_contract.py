#!/usr/bin/env python3
"""Contract checks for ticket-implementation-unit."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_SKILL = REPO_ROOT / "skills" / "ticket-implementation-unit" / "SKILL.md"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
WORK_UNIT = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"


def main() -> int:
    try:
        skill = IMPLEMENTATION_SKILL.read_text(encoding="utf-8")
        check_skill(skill)
        check_orchestrator(TICKET_START.read_text(encoding="utf-8"))
        check_orchestrator(WORK_UNIT.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-implementation-unit contract")
    return 0


def check_skill(skill: str) -> None:
    required_terms = (
        "Implement one approved work unit",
        "ready for verification",
        "Required Inputs",
        "Files changed",
        "Local tests/checks run",
        "Implementer self-review report",
        "Known risks or blockers",
        "Handoff notes for QA/UIUX",
        "Claiming QA/UIUX passed without separate verifier reports",
        "Broadening beyond the provided plan slice",
    )
    for term in required_terms:
        assert_contains(skill, term, "ticket-implementation-unit skill")


def check_orchestrator(skill: str) -> None:
    assert_contains(skill, "implementation report", "orchestrator skill")
    assert_contains(skill, "implementer self-review", "orchestrator skill")
    assert_not_contains(skill, "ticket-implementation-unit", "orchestrator skill")


def assert_contains(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"{context} must contain {needle!r}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
