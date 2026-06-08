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
    assert_contains(skill, "## Step 4 - Execute Through Subagents")
    assert_contains(skill, "Let the agent harness decide the exact subagent strategy")
    assert_contains(skill, "Delegate implementation for the approved work units")
    assert_contains(skill, "Delegate self-review or review")
    assert_contains(skill, "Delegate QA verification")
    assert_contains(skill, "delegate UI/UX verification")
    assert_contains(skill, "Delegate scoped fixes")
    assert_not_contains(skill, "multi-ticket-work")
    assert_not_contains(skill, "ticket-implementation-unit")
    assert_not_contains(skill, "Dispatch `ticket-qa-verification`")
    assert_not_contains(skill, "ticket-qa-verification")
    assert_not_contains(skill, "frontend-ui-review")
    assert_not_contains(skill, "QA mode (`backend` / `ui` / `mixed` from diff)")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
