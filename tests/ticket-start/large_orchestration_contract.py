#!/usr/bin/env python3
"""Contract checks for ticket-start delegated orchestration."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
SKILL_DIR = SKILL_PATH.parent
DOWNSTREAM_SKILL_IDS = (
    "ticket-work-unit-orchestration",
    "ticket-implementation-unit",
    "ticket-qa-verification",
    "ticket-ship-gate",
    "frontend-ui-review",
    "codebase-scope-map",
)


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
        *DOWNSTREAM_SKILL_IDS,
    )
    for forbidden in forbidden_terms:
        assert_not_contains(skill, forbidden)

    for markdown_file in sorted(SKILL_DIR.rglob("*.md")):
        text = markdown_file.read_text(encoding="utf-8")
        for forbidden in DOWNSTREAM_SKILL_IDS:
            assert_not_contains(text, forbidden)


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected ticket-start to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
