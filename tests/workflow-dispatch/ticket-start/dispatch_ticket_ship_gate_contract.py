#!/usr/bin/env python3
"""Contract checks for ticket-start dispatching ticket-ship-gate."""

from __future__ import annotations

import re
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

    print("PASS: ticket-start dispatches ticket-ship-gate")
    return 0


def check_contract(skill: str) -> None:
    ship = section_between(skill, "## Ship routing", "## Briefing rule")
    assert_contains(ship, "Use `ticket-ship-gate`")
    assert_contains(ship, "required checks gate expectations")
    assert_contains(ship, "per-work-unit readiness ledger")
    assert_contains(ship, "Do not perform Ship mutations inline")
    assert_contains(ship, "explicit user merge approval status")
    assert_contains(ship, "current PR draft/ready state")
    assert_contains(ship, "intended Ship action")
    assert_not_contains(ship, "gh pr checks <PR> --required --json name,state,bucket,workflow,link")


def section_between(document: str, start_heading: str, end_heading: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(start_heading)}\n(?P<section>.*?)(?=^{re.escape(end_heading)}\n)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(document)
    if not match:
        raise AssertionError(f"missing section from {start_heading!r} to {end_heading!r}")
    return match.group("section")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
