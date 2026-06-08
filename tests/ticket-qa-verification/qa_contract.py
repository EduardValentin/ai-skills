#!/usr/bin/env python3
"""Contract checks for ticket-qa-verification."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TICKET_START_QA_POINTER = REPO_ROOT / "skills" / "ticket-start" / "agents" / "qa.md"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
MULTI_TICKET_WORK = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        check_ticket_start_has_no_qa_pointer()
        check_ticket_start_routes(TICKET_START.read_text(encoding="utf-8"))
        check_orchestrator_references(MULTI_TICKET_WORK.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-qa-verification contract")
    return 0


def check_ticket_start_has_no_qa_pointer() -> None:
    if TICKET_START_QA_POINTER.exists():
        raise AssertionError(f"ticket-start should not keep QA pointer file: {TICKET_START_QA_POINTER}")


def check_orchestrator_references(skill: str) -> None:
    assert_not_contains(skill, "ticket-qa-verification", "orchestrator skill")


def check_ticket_start_routes(skill: str) -> None:
    assert_not_contains(skill, "Dispatch `ticket-qa-verification`", "ticket-start skill")
    assert_not_contains(skill, "multi-ticket-work", "ticket-start skill")
    assert_not_contains(skill, "ticket-qa-verification", "ticket-start skill")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
