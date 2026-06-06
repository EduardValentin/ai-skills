#!/usr/bin/env python3
"""Contract checks for ticket-start dispatching ticket-qa-verification."""

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

    print("PASS: ticket-start dispatches ticket-qa-verification")
    return 0


def check_contract(skill: str) -> None:
    verify = section_between(skill, "## Verify", "## Ship")
    assert_contains(verify, "Dispatch `ticket-qa-verification`")
    assert_contains(verify, "QA mode (`backend` / `ui` / `mixed` from diff)")
    assert_contains(verify, "Local test runs, manual browser checks, and endpoint probes are evidence")
    assert_contains(verify, "not substitutes for the QA verification report")
    assert_before(verify, "Dispatch `ticket-qa-verification`", "continue to UI/UX")


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


def assert_before(haystack: str, first: str, second: str) -> None:
    first_index = haystack.find(first)
    second_index = haystack.find(second)
    if first_index < 0 or second_index < 0 or first_index > second_index:
        raise AssertionError(f"expected {first!r} to appear before {second!r}")


if __name__ == "__main__":
    raise SystemExit(main())
