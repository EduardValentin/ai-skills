#!/usr/bin/env python3
"""Contract checks for ship-ticket."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ship-ticket" / "SKILL.md"
OPENAI_METADATA = REPO_ROOT / "skills" / "ship-ticket" / "agents" / "openai.yaml"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
MULTI_TICKET_WORK = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        metadata = OPENAI_METADATA.read_text(encoding="utf-8")
        check_skill_contract(skill)
        check_metadata(metadata)
        check_parent_skills_do_not_hardcode_ship_skill()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ship-ticket contract")
    return 0


def check_skill_contract(skill: str) -> None:
    required_terms = (
        "name: ship-ticket",
        "Use when a Jira or Linear ticket-linked pull request is ready to ship",
        "CANNOT SHIP",
        "Jira or Linear",
        "review state",
        "In Progress",
        "Done or Closed",
        "Required PR/CI checks",
        "explicit user approval",
        "does not judge how that work was produced",
        "does not",
        "delegate fixes",
        "parent or Epic",
        "child or sibling ticket statuses",
        "non-final state",
    )
    for term in required_terms:
        assert_contains(skill, term, "ship-ticket skill")

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
        assert_not_contains(skill, term, "ship-ticket skill")


def check_metadata(metadata: str) -> None:
    for term in ("Ship Ticket", "$ship-ticket", "Jira or Linear"):
        assert_contains(metadata, term, "ship-ticket metadata")


def check_parent_skills_do_not_hardcode_ship_skill() -> None:
    for path in (TICKET_START, MULTI_TICKET_WORK):
        skill = path.read_text(encoding="utf-8")
        assert_not_contains(skill, "ship-ticket", f"{path.relative_to(REPO_ROOT)}")


def assert_contains(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"{context} must contain {needle!r}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
