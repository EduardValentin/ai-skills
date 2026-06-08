#!/usr/bin/env python3
"""Contract checks for ticket-start dispatching Ship gate capability."""

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

    print("PASS: ticket-start dispatches Ship gate capability")
    return 0


def check_contract(skill: str) -> None:
    assert_contains(skill, "## Step 5 - Ship Or Handoff")
    assert_contains(skill, "Before changing PR, branch, ticket, or merge state")
    assert_contains(skill, "verify readiness and required approvals")
    assert_contains(skill, "require explicit user approval before merge")
    assert_not_contains(skill, "ticket-ship-gate")
    assert_not_contains(skill, "multi-ticket-work")
    assert_not_contains(skill, "gh pr checks <PR> --required --json name,state,bucket,workflow,link")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
