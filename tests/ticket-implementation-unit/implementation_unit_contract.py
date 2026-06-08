#!/usr/bin/env python3
"""Contract checks for ticket-implementation-unit."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
WORK_UNIT = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"


def main() -> int:
    try:
        check_orchestrator(TICKET_START.read_text(encoding="utf-8"))
        check_orchestrator(WORK_UNIT.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-implementation-unit contract")
    return 0


def check_orchestrator(skill: str) -> None:
    assert_not_contains(skill, "ticket-implementation-unit", "orchestrator skill")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
