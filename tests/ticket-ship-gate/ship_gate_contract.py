#!/usr/bin/env python3
"""Contract checks for ticket-ship-gate."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    try:
        check_ticket_start_dispatch(TICKET_START.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-ship-gate contract")
    return 0


def check_ticket_start_dispatch(skill: str) -> None:
    assert_not_contains(skill, "ticket-ship-gate", "ticket-start skill")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
