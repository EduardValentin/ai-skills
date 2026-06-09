#!/usr/bin/env python3
"""Contract checks for the github-interaction skill."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "github-interaction"
SKILL_PATH = SKILL_DIR / "SKILL.md"
SCRIPT_PATH = SKILL_DIR / "scripts" / "get-bot-gh-token.sh"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        check_skill_contract(skill)
        check_script_contract(script)
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: github-interaction contract")
    return 0


def check_skill_contract(skill: str) -> None:
    assert_line_count_at_most(skill, 70)

    required_terms = (
        "name: github-interaction",
        "Use when a task needs GitHub writes",
        "Requires local GitHub App bot credentials",
        "configured GitHub App bot identity",
        "Never use ambient personal GitHub credentials for writes",
        "Requires shell execution",
        "GitHub CLI or API client that honors `GH_TOKEN`",
        "ai-skills.gh-bot.git-name",
        "ai-skills.gh-bot.git-email",
        "scripts/get-bot-gh-token.sh",
        "creating or editing pull requests",
        "POST/PATCH/PUT/DELETE GitHub API mutations",
        "For `git push`, use a fresh token",
        "Fail Closed",
        "Draft intended text in chat instead of posting through personal credentials",
    )
    for required in required_terms:
        assert_contains(skill, required)

    forbidden_terms = (
        "bot-identity",
        "ticket-start",
        "personal-workflow",
        "job-workflow",
        "Setup runbook",
        "Step A",
        "Token rotation",
        "NordPass",
        "Claude Opus",
        "historical",
        "gh pr create/edit/comment/review/merge",
        "gh api --method",
    )
    for forbidden in forbidden_terms:
        assert_not_contains(skill, forbidden)


def check_script_contract(script: str) -> None:
    required_terms = (
        "ai-skills.gh-bot",
        "security find-generic-password",
        "https://api.github.com/app/installations",
        "printf '%s\\n' \"$TOKEN\"",
    )
    for required in required_terms:
        assert_contains(script, required)

    for forbidden in ("bot-identity", "runbook Step", "personal-workflow", "job-workflow"):
        assert_not_contains(script, forbidden)


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected github-interaction to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
