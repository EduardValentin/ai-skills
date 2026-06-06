#!/usr/bin/env python3
"""Contract checks for per-work-unit readiness ledger orchestration.

This is intentionally RED until a dedicated ticket-work-unit-orchestration skill
or equivalent ticket-start section defines the per-unit ledger contract.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATION_SKILL = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"
FALLBACK_SKILL = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    skill_path = ORCHESTRATION_SKILL if ORCHESTRATION_SKILL.exists() else FALLBACK_SKILL
    skill = skill_path.read_text(encoding="utf-8")

    try:
        check_readiness_ledger_contract(skill)
    except AssertionError as error:
        print(f"FAIL: {skill_path.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {skill_path.relative_to(REPO_ROOT)} defines per-work-unit readiness ledger")
    return 0


def check_readiness_ledger_contract(skill: str) -> None:
    assert_any_contains(
        skill,
        (
            "per-work-unit readiness ledger",
            "per-unit readiness ledger",
            "per-ticket readiness ledger",
        ),
    )
    assert_any_contains(
        skill,
        (
            "every ticket/work unit",
            "every work unit",
            "each ticket/work unit",
            "each work unit",
        ),
    )

    required_terms = (
        "implementation report",
        "implementer self-review report",
        "QA verification report",
        "UI/UX verification report",
        "explicit backend-only/non-UI skip rationale",
    )
    for term in required_terms:
        assert_contains(skill, term)

    assert_any_contains(
        skill,
        (
            "A work unit is not complete until",
            "A ticket/work unit is not complete until",
            "Do not mark a work unit complete until",
        ),
    )
    assert_contains(skill, "Self-review is distinct from QA verification and UI/UX verification")
    assert_contains(skill, "UI/UX skip")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_any_contains(haystack: str, needles: tuple[str, ...]) -> None:
    if not any(needle in haystack for needle in needles):
        raise AssertionError(f"expected to find one of: {', '.join(repr(needle) for needle in needles)}")


if __name__ == "__main__":
    raise SystemExit(main())
