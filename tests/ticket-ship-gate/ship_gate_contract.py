#!/usr/bin/env python3
"""Contract checks for ticket-ship-gate."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHIP_SKILL = REPO_ROOT / "skills" / "ticket-ship-gate" / "SKILL.md"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
BOT_IDENTITY = REPO_ROOT / "skills" / "ticket-start" / "bot-identity.md"


def main() -> int:
    try:
        skill = SHIP_SKILL.read_text(encoding="utf-8")
        check_skill(skill)
        check_bot_identity_reference(skill, BOT_IDENTITY.read_text(encoding="utf-8"))
        check_ticket_start_dispatch(TICKET_START.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-ship-gate contract")
    return 0


def check_skill(skill: str) -> None:
    required_terms = (
        "Ship gate owns readiness and release mutations",
        "Required Inputs",
        "per-work-unit readiness ledger",
        "implementation report",
        "implementer self-review report",
        "QA verification report",
        "UI/UX verification report",
        "explicit backend-only/non-UI skip rationale",
        "Refuse Ship if any readiness ledger row is missing",
        "gh pr checks <PR> --required --json name,state,bucket,workflow,link",
        "no-checks-configured",
        "Every required check whose `bucket` is not `skipping` must have `bucket == \"pass\"`",
        "User approval is required before merge",
        "ambient personal GitHub credentials",
        "Linear/Jira transitions",
        "Ship gate report",
    )
    for term in required_terms:
        assert_contains(skill, term, "ticket-ship-gate skill")


def check_bot_identity_reference(skill: str, bot_identity: str) -> None:
    assert_contains(skill, "ticket-start/bot-identity.md", "ticket-ship-gate skill")
    assert_contains(bot_identity, "GitHub write actions — bot token required", "bot identity runbook")
    assert_contains(bot_identity, "do not rely on the local credential helper", "bot identity runbook")


def check_ticket_start_dispatch(skill: str) -> None:
    assert_contains(skill, "ticket-ship-gate", "ticket-start skill")
    assert_contains(skill, "Ship gate", "ticket-start skill")
    assert_contains(skill, "per-work-unit readiness ledger", "ticket-start skill")


def assert_contains(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"{context} must contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
