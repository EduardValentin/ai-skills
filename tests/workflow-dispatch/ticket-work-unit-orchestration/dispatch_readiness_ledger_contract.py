#!/usr/bin/env python3
"""Contract checks for ticket-work-unit-orchestration workflow dispatch."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        check_dispatch_contract(skill)
    except Exception as error:
        print(f"FAIL: {SKILL_PATH.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-work-unit-orchestration defines readiness-ledger workflow dispatch")
    return 0


def check_dispatch_contract(skill: str) -> None:
    required_terms = (
        "Build the ledger before delegating implementation",
        "Delegate implementation through an implementation work-unit request",
        "approved work-unit plan slice",
        "Require returned reports to update the ledger",
        "implementation report",
        "implementer self-review report",
        "QA verification report",
        "acceptance-criteria QA behavior verification request",
        "UI/UX verification report",
        "frontend UI/UX visual review request",
        "reviewing implemented frontend UI for visual parity against a runnable prototype/reference or visual consistency against production analogs",
        "Do not make this a generic screenshot validation request",
        "explicit backend-only/non-UI skip rationale",
        "unresolved findings status",
        "integration/out-of-scope status",
        "Do not prescribe a rigid topology",
    )
    for term in required_terms:
        assert_contains(skill, term)

    forbidden_terms = (
        "ticket-implementation-unit",
        "ticket-qa-verification",
        "frontend-ui-review",
        "codebase-scope-map",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term)

    assert_before(skill, "Build the ledger before delegating implementation", "Delegate implementation")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_before(haystack: str, first: str, second: str) -> None:
    first_index = haystack.find(first)
    second_index = haystack.find(second)
    if first_index < 0 or second_index < 0 or first_index > second_index:
        raise AssertionError(f"expected {first!r} to appear before {second!r}")


if __name__ == "__main__":
    raise SystemExit(main())
