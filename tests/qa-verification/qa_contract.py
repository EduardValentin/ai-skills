#!/usr/bin/env python3
"""Contract checks for qa-verification."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "qa-verification" / "SKILL.md"
TICKET_START_QA_POINTER = REPO_ROOT / "skills" / "ticket-start" / "agents" / "qa.md"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
MULTI_TICKET_WORK = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_skill_contract(skill)
        check_ticket_start_has_no_qa_pointer()
        check_orchestrator_references(TICKET_START.read_text(encoding="utf-8"))
        check_orchestrator_references(MULTI_TICKET_WORK.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: qa-verification contract")
    return 0


def check_skill_contract(skill: str) -> None:
    assert_line_count_at_most(skill, 110)

    required_terms = (
        "name: qa-verification",
        "manually verifying acceptance criteria",
        "running app, API, service, job, script, integration, frontend PR, or mixed executable surface",
        "QA cannot proceed",
        "Manually verify that an implementation satisfies its acceptance criteria",
        "use this mandatory order before verification",
        "first access the PR and ticket through available tooling such as MCP, API, CLI, or authenticated local metadata",
        "ask the caller for the ticket/PR details, acceptance criteria, implemented surface area, and testing instructions",
        "only after the caller cannot provide those details, scope the diff to infer a provisional verification target",
        "Blocked metadata alone is not enough to fall back to the diff",
        "When metadata is available but testing instructions are absent or vague",
        "scope before verification from the PR/ticket details, acceptance criteria, diff/changed files, entry points, setup/data needs, implemented surface, and regression risks",
        "use browser tooling, manually click through the implemented surface",
        "The report must name the app start command or URL, browser actions, and rendered outcomes",
        "use programmatic probes against the running implemented surface",
        "prefer running the GUI and backend/service together and verifying the flow end to end",
        "Unit tests, type checks, source inspection, and static review can support QA context, but they do not count as QA verification by themselves",
        "Every acceptance criterion must map to a concrete observation",
        "Any observed bug changes the verdict to `BUGS FOUND`",
        "Metadata source",
        "Metadata access sequence",
        "Tooling attempted",
        "Caller details requested",
        "Diff fallback used",
        "Scope basis",
        "Manual/programmatic verification performed",
        "Running surface",
        "State and propagation checks",
        "Required next input",
        "ui | backend | mixed | other",
        "Starting the app, scoping from the diff, or inferring testing instructions before attempting available PR/ticket tooling and asking for missing details",
        "Falling back to diff-scoped QA before the caller has had a chance to provide missing ticket/PR details",
        "Reporting a bug without reproduction steps and evidence",
    )
    for term in required_terms:
        assert_contains(skill, term)

    forbidden_terms = (
        "before Ship",
        "Ship",
        "visual parity",
        "UI/UX",
        "layout polish",
        "styling",
        "code review",
        "self-review",
        "QA is distinct from",
        "For visual parity",
        "frontend-pr-test",
        "Frontend PR Test",
        "Quick Reference",
        "Scoping Subagent Prompt",
        "Red Flags",
        "Common Mistakes",
        "test-log",
        "historical",
        "focused tests",
        "Run PR testing notes first",
        "A ticket ID, local diff, or user permission to proceed without PR notes does not replace blocked PR metadata",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term, "qa-verification")


def check_ticket_start_has_no_qa_pointer() -> None:
    if TICKET_START_QA_POINTER.exists():
        raise AssertionError(f"ticket-start should not keep QA pointer file: {TICKET_START_QA_POINTER}")


def check_orchestrator_references(skill: str) -> None:
    assert_not_contains(skill, "qa-verification", "orchestrator skill")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected qa-verification to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
