#!/usr/bin/env python3
"""Contract checks for verify-pr-readiness."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "verify-pr-readiness" / "SKILL.md"
OPENAI_METADATA = REPO_ROOT / "skills" / "verify-pr-readiness" / "agents" / "openai.yaml"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
MULTI_TICKET_WORK = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        metadata = OPENAI_METADATA.read_text(encoding="utf-8")
        check_skill_contract(skill)
        check_metadata(metadata)
        check_parent_skills_do_not_hardcode_readiness_skill()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: verify-pr-readiness contract")
    return 0


def check_skill_contract(skill: str) -> None:
    required_terms = (
        "name: verify-pr-readiness",
        "Use when checking whether a ticket-linked PR is ready",
        "Jira/Linear transitions",
        "Not for code review",
        "check readiness",
        "NOT_READY",
        "Jira or Linear",
        "review state",
        "In Progress",
        "Done or Closed",
        "Required PR/CI checks",
        "explicit user approval",
        "does not judge how that work was produced",
        "does not",
        "delegate fixes",
        "When blocked, perform no partial PR, branch, tracker, release, or merge mutations.",
        "parent or Epic",
        "child or sibling ticket statuses",
        "non-final state",
        "# PR readiness report",
    )
    for term in required_terms:
        assert_contains(skill, term, "verify-pr-readiness skill")

    forbidden_terms = (
        "readiness ledger",
        "bot identity",
        "personal workflow",
        "job workflow",
        "implementation report",
        "per-work-unit",
        "source-of-truth freshness",
        "requirements/design approval",
        "visual parity",
        "UIUX",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term, "verify-pr-readiness skill")


def check_metadata(metadata: str) -> None:
    for term in ("Verify PR Readiness", "$verify-pr-readiness", "Jira/Linear"):
        assert_contains(metadata, term, "verify-pr-readiness metadata")


def check_parent_skills_do_not_hardcode_readiness_skill() -> None:
    for path in (TICKET_START, MULTI_TICKET_WORK):
        skill = path.read_text(encoding="utf-8")
        assert_not_contains(skill, "verify-pr-readiness", f"{path.relative_to(REPO_ROOT)}")


def assert_contains(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"{context} must contain {needle!r}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
