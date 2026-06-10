#!/usr/bin/env python3
"""Contract checks for verify-pr."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "verify-pr" / "SKILL.md"
OPENAI_METADATA = REPO_ROOT / "skills" / "verify-pr" / "agents" / "openai.yaml"
TICKET_START = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
MULTI_TICKET_WORK = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        metadata = OPENAI_METADATA.read_text(encoding="utf-8")
        check_skill_contract(skill)
        check_metadata(metadata)
        check_parent_skills_do_not_hardcode_verify_pr_skill()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: verify-pr contract")
    return 0


def check_skill_contract(skill: str) -> None:
    required_terms = (
        "name: verify-pr",
        "Use when checking whether a pull request is ready",
        "post-merge CI monitoring",
        "Verify PR validates",
        "MCP connectors, REST APIs, CLIs",
        "Treat user-provided state as a hint",
        "## Metadata Resolution",
        "return `NOT_READY`",
        "linked Jira or Linear ticket is in a review-state column",
        "Required CI checks are passing",
        "Tests that cover the implemented surface area are passing",
        "required review approval",
        "no active unresolved review comments",
        "## Forbidden Behavior",
        "Returning a final report with `unknown` or `not available` PR state",
        "Merging, marking ready, updating tickets, dismissing comments",
        "Calling an observed post-merge CI failure",
        "start a background process or subagent to monitor post-merge CI",
        "fetch the failing check details from the source-control system",
        "proposed plan of action",
        "# Verify PR report",
        "Status: READY | NOT_READY | MERGED_MONITORING | POST_MERGE_CLEAR | POST_MERGE_BLOCKED",
    )
    for term in required_terms:
        assert_contains(skill, term, "verify-pr skill")

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
        "tracker final-state mutation",
        "parent or Epic",
        "child or sibling ticket statuses",
        "Done or Closed",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term, "verify-pr skill")


def check_metadata(metadata: str) -> None:
    for term in ("Verify PR", "$verify-pr", "post-merge CI"):
        assert_contains(metadata, term, "verify-pr metadata")


def check_parent_skills_do_not_hardcode_verify_pr_skill() -> None:
    for path in (TICKET_START, MULTI_TICKET_WORK):
        skill = path.read_text(encoding="utf-8")
        assert_not_contains(skill, "verify-pr", f"{path.relative_to(REPO_ROOT)}")


def assert_contains(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"{context} must contain {needle!r}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
