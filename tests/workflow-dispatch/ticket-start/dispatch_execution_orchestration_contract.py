#!/usr/bin/env python3
"""Contract checks for ticket-start dispatching approved execution orchestration."""

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

    print("PASS: ticket-start dispatches approved execution orchestration")
    return 0


def check_contract(skill: str) -> None:
    execution = section_between(skill, "## Execution routing", "## Ship routing")
    assert_contains(execution, "Dispatch a self-contained approved execution orchestration request")
    assert_contains(execution, "auto-discovery selects the appropriate execution orchestration capability")
    assert_contains(execution, "approved requirements/design artifact")
    assert_contains(execution, "approved implementation plan")
    assert_contains(execution, "Scoping map")
    assert_contains(execution, "per-work-unit readiness ledger")
    assert_contains(execution, "Do not dispatch implementation, QA, UI/UX, review, testing, or fix-loop work directly from `ticket-start`")
    assert_not_contains(execution, "ticket-work-unit-orchestration")
    assert_not_contains(execution, "ticket-implementation-unit")
    assert_not_contains(execution, "Dispatch `ticket-qa-verification`")
    assert_not_contains(execution, "ticket-qa-verification")
    assert_not_contains(execution, "frontend-ui-review")
    assert_not_contains(execution, "QA mode (`backend` / `ui` / `mixed` from diff)")


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
