#!/usr/bin/env python3
"""Contract checks for ticket-start delegated execution sequence."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_contract(skill)
    except Exception as error:
        print(f"FAIL: {SKILL_PATH.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start defines delegated execution sequence")
    return 0


def check_contract(skill: str) -> None:
    assert_contains(skill, "## Step 4 - Route Execution And Verification")
    assert_contains(skill, "implementation begins by delegating work to implementer subagents")
    assert_contains(skill, "minimize dependencies and maximize throughput and quality of work")
    assert_contains(skill, "Respect this ticket sequence")
    assert_contains(skill, "Delegate implementation for the approved plan")
    assert_contains(skill, "Delegate independent review")
    assert_contains(skill, "Delegate QA verification")
    assert_contains(skill, "delegate UI/UX verification")
    assert_contains(skill, "Aggregate findings from independent review, QA, and UI/UX verification")
    assert_contains(skill, "Personal projects / Linear tickets")
    assert_contains(skill, "Job projects / Jira tickets")
    assert_contains(skill, "CANNOT_VERIFY")
    assert_contains(skill, "Delegate scoped fixes")
    assert_contains(skill, "Do not route the ticket to PR verification")
    assert_not_contains(skill, "multi-ticket-work")
    assert_not_contains(skill, "implement-unit-of-work")
    assert_not_contains(skill, "Dispatch `qa-verification`")
    assert_not_contains(skill, "qa-verification")
    assert_not_contains(skill, "ui-verification")
    assert_not_contains(skill, "QA mode (`backend` / `ui` / `mixed` from diff)")
    assert_not_contains(skill, "does not define")
    assert_not_contains(skill, "does not prescribe")
    assert_not_contains(skill, "Let the agent harness")
    assert_not_contains(skill, "active methodology skills")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
