#!/usr/bin/env python3
"""Contract checks for ticket-start UI/UX visual verification."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    skill = SKILL_PATH.read_text(encoding="utf-8")

    try:
        check_uiux_contract(skill)
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start UI/UX visual verification contract")
    return 0


def check_uiux_contract(skill: str) -> None:
    assert_not_contains(skill, "frontend-ui-review")

    assert_not_contains(skill, "Do not accept template/source inspection")
    assert_not_contains(skill, "proxy-component screenshots")
    assert_not_contains(skill, "storybook-only renders")
    assert_not_contains(skill, "Every verified row has non-blank")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
