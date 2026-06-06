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
    section = section_between(skill, "## Large Workflows", "## Implement")

    assert_contains(section, "The main agent is the orchestrator")
    assert_contains(section, "For workflows spanning multiple tickets")
    assert_contains(section, "delegate each ticket implementation to a different implementation agent")
    assert_contains(section, "review, testing, and verification remain delegated")
    assert_contains(section, "The skill enforces ownership, not mechanics")

    forbidden_terms = (
        "Root -> child -> grandchild",
        "Depth budget",
        "IMPLEMENTATION_SLICE_RESULT",
        "BROWSER_VERIFICATION_RESULT",
        "leaf-only",
        "Grandchildren are helper probes",
        "exact depth budget",
    )
    for forbidden in forbidden_terms:
        assert_not_contains(skill, forbidden)

    implement = section_between(skill, "## Implement", "## Verify")
    assert_contains(implement, "Implementation is delegated through `ticket-implementation-unit` subagent(s)")
    assert_contains(implement, "Review, testing, and verification work stays delegated")
    assert_contains(implement, "The main session coordinates rather than implementing, reviewing, testing, or verifying inline")

    ship = section_between(skill, "## Ship", "## Verification fix loops")
    assert_contains(ship, "Use `ticket-ship-gate` for Ship")
    assert_contains(ship, "per-work-unit readiness ledger")
    assert_contains(ship, "Do not perform Ship mutations inline")


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
