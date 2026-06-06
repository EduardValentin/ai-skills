#!/usr/bin/env python3
"""Contract checks for ticket-start delegated orchestration."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    skill = SKILL_PATH.read_text(encoding="utf-8")

    try:
        check_large_orchestration_contract(skill)
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start delegated orchestration contract")
    return 0


def check_large_orchestration_contract(skill: str) -> None:
    assert_line_count_at_most(skill, 175)
    assert_contains(skill, "thin intake and routing orchestrator")
    assert_contains(skill, "Invoke `ticket-work-unit-orchestration`")
    assert_contains(skill, "large workflows spanning multiple tickets")
    assert_contains(skill, "per-work-unit readiness ledger")
    assert_contains(skill, "Use `ticket-ship-gate` for Ship")

    forbidden_terms = (
        "## Large Workflows",
        "## Implement",
        "## Verify",
        "Root -> child -> grandchild",
        "Depth budget",
        "IMPLEMENTATION_SLICE_RESULT",
        "BROWSER_VERIFICATION_RESULT",
        "leaf-only",
        "Grandchildren are helper probes",
        "exact depth budget",
        "Implementation is delegated through `ticket-implementation-unit` subagent(s)",
        "Dispatch `ticket-qa-verification`",
        "Dispatch UI/UX subagent",
        "Every verified row has non-blank",
        "gh pr checks <PR> --required --json name,state,bucket,workflow,link",
    )
    for forbidden in forbidden_terms:
        assert_not_contains(skill, forbidden)

    execution = section_between(skill, "## Execution routing", "## Ship routing")
    assert_contains(execution, "approved requirements/design artifact")
    assert_contains(execution, "approved implementation plan")
    assert_contains(execution, "Do not dispatch implementation, QA, UI/UX, review, testing, or fix-loop work directly from `ticket-start`")

    ship = section_between(skill, "## Ship routing", "## Briefing rule")
    assert_contains(ship, "Use `ticket-ship-gate` for Ship")
    assert_contains(ship, "explicit user merge approval status")
    assert_contains(ship, "intended Ship action")


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


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected ticket-start to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
