#!/usr/bin/env python3
"""Contract checks for ticket-qa-verification."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
QA_SKILL = REPO_ROOT / "skills" / "ticket-qa-verification" / "SKILL.md"
TICKET_START_QA_POINTER = REPO_ROOT / "skills" / "ticket-start" / "agents" / "qa.md"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
WORK_UNIT = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"


def main() -> int:
    try:
        qa_skill = QA_SKILL.read_text(encoding="utf-8")
        check_qa_skill(qa_skill)
        check_ticket_start_has_no_qa_pointer()
        check_ticket_start_routes(TICKET_START.read_text(encoding="utf-8"))
        check_orchestrator_references(WORK_UNIT.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-qa-verification contract")
    return 0


def check_qa_skill(skill: str) -> None:
    required_terms = (
        "QA reports require live behavior evidence",
        "QA findings are reported, not fixed",
        "Backend/API/Service Mode",
        "UI Mode",
        "Mixed Mode",
        "QA cannot proceed",
        "Report Format",
        "Coverage performed",
        "Bugs found",
        "Out-of-scope flags",
        "Declaring `CLEAN` without exercising every acceptance criterion",
        "Treating unit tests, type checks, static review, or implementation self-review as QA completion",
    )
    for term in required_terms:
        assert_contains(skill, term, "ticket-qa-verification skill")


def check_ticket_start_has_no_qa_pointer() -> None:
    if TICKET_START_QA_POINTER.exists():
        raise AssertionError(f"ticket-start should not keep QA pointer file: {TICKET_START_QA_POINTER}")


def check_orchestrator_references(skill: str) -> None:
    assert_contains(skill, "QA verification report", "orchestrator skill")
    assert_not_contains(skill, "ticket-qa-verification", "orchestrator skill")


def check_ticket_start_routes(skill: str) -> None:
    assert_contains(skill, "QA verification report", "ticket-start skill")
    assert_not_contains(skill, "Dispatch `ticket-qa-verification`", "ticket-start skill")
    assert_not_contains(skill, "ticket-work-unit-orchestration", "ticket-start skill")
    assert_not_contains(skill, "ticket-qa-verification", "ticket-start skill")


def assert_contains(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"{context} must contain {needle!r}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
