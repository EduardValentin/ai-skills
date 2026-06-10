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
    assert_line_count_at_most(skill, 90)

    required_terms = (
        "name: multi-ticket-work",
        "full multi-ticket scope",
        "Epic with multiple tickets",
        "parent ticket with child tickets or sub-tickets",
        "The main agent is the orchestrator",
        "does not implement ticket work inline",
        "Save an uncommitted orchestration note",
        "Re-read it at the start of work, after any context compaction or resume",
        "Re-read the durable orchestration note before reporting",
        "Dispatch one subagent per ticket or unit of work",
        "Each subagent owns the normal one-ticket workflow for its ticket or unit",
        "report blocked when required context, approval, delegated checks, or PR creation is unavailable",
        "opened a PR and returned a completion report",
        "State plainly in each dispatch that the subagent must open a PR and return a completion report",
        "reviewer-friendly PR body expectation",
        "Put the PRs in the order the human should review them",
        "Phrase it as a PR-description or reviewer-summary request",
    )
    for term in required_terms:
        assert_contains(skill, term)

    forbidden_terms = (
        "readiness ledger",
        "Ship readiness",
        "implement-unit-of-work",
        "qa-verification",
        "ui-verification",
        "verify-pr",
        "codebase-scope-map",
        "pr-reviewer-summary",
        "UI/UX verification",
        "QA verification",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term)


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected multi-ticket-work to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
