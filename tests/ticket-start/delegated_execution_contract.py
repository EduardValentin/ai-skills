#!/usr/bin/env python3
"""Contract checks for ticket-start delegated execution orchestration."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
SKILL_DIR = SKILL_PATH.parent
DOWNSTREAM_SKILL_IDS = (
    "multi-ticket-work",
    "execute-ticket-work",
    "implement-unit-of-work",
    "qa-verification",
    "verify-pr",
    "ui-verification",
    "codebase-scope-map",
    "github-interaction",
)


def main() -> int:
    skill = SKILL_PATH.read_text(encoding="utf-8")

    try:
        check_delegated_execution_contract(skill)
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start delegated execution contract")
    return 0


def check_delegated_execution_contract(skill: str) -> None:
    assert_line_count_at_most(skill, 140)

    forbidden_terms = (
        "## Large Workflows",
        "large workflows spanning multiple tickets",
        "spans multiple tickets",
        "workflows spanning multiple tickets",
        "each ticket implementation should be delegated",
        "## Implement",
        "## Verify",
        "Root -> child -> grandchild",
        "Depth budget",
        "IMPLEMENTATION_SLICE_RESULT",
        "BROWSER_VERIFICATION_RESULT",
        "leaf-only",
        "Grandchildren are helper probes",
        "exact depth budget",
        "dispatch wording",
        "Scoping dispatch wording",
        "Implementation dispatch wording",
        "UI/UX dispatch wording",
        "auto-discovery",
        "downstream skill identifier",
        "Implementation is delegated through `implement-unit-of-work` subagent(s)",
        "Dispatch `qa-verification`",
        "Dispatch UI/UX subagent",
        "Every verified row has non-blank",
        "gh pr checks <PR> --required --json name,state,bucket,workflow,link",
        "Propose 2-3 approaches",
        "Write design doc",
        "docs/superpowers",
        "Task N:",
        "TodoWrite",
        "two-stage review",
        "spec compliance",
        "code quality reviewer",
        "Initialize a compact work-unit status table",
        "work-unit status table with columns",
        "When returning an execution action list",
        "does not define",
        "does not prescribe",
        "historical context",
        "detailed method",
        "active methodology skills",
        "Let the agent harness",
        "bot-identity.md",
        "get-bot-gh-token.sh",
        "configured GitHub bot identity",
        "ambient personal GitHub credentials",
        *DOWNSTREAM_SKILL_IDS,
    )
    for forbidden in forbidden_terms:
        assert_not_contains(skill, forbidden)

    for markdown_file in sorted(SKILL_DIR.rglob("*.md")):
        text = markdown_file.read_text(encoding="utf-8")
        for forbidden in DOWNSTREAM_SKILL_IDS:
            assert_not_contains(text, forbidden)

    for removed in (
        "personal-workflow.md",
        "job-workflow.md",
        "verification-fix-loops.md",
        "bot-identity.md",
    ):
        if (SKILL_DIR / removed).exists():
            raise AssertionError(f"ticket-start should not keep stale companion file: {removed}")

    if (SKILL_DIR / "scripts" / "get-bot-gh-token.sh").exists():
        raise AssertionError("ticket-start should not own the GitHub bot token helper")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected ticket-start to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
