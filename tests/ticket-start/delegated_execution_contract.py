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
    "implement-unit-of-work",
    "qa-verification",
    "verify-pr-readiness",
    "ui-verification",
    "codebase-scope-map",
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
        *DOWNSTREAM_SKILL_IDS,
    )
    for forbidden in forbidden_terms:
        assert_not_contains(skill, forbidden)

    assert_contains(skill, "Do not use for multi-ticket workflow intake")
    assert_contains(skill, "Use this skill as the main-agent workflow for working one implementation ticket")
    assert_contains(skill, "It defines ticket-specific source-of-truth, approval, routing, and reporting gates")
    assert_contains(skill, "does not define the detailed method for brainstorming, plan writing, implementation, review, QA, UI verification, or PR readiness")
    assert_contains(skill, "If the ticket is a child issue, subtask, story under an Epic")
    assert_contains(skill, "read the parent tickets or Epic descriptions too")
    assert_contains(skill, "check `PRD.md` when the ticket or unit of work adds or changes business rules")
    assert_contains(skill, "Check `designs/` or reference apps only when the ticket adds or modifies UI components")
    assert_contains(skill, "corresponding reference surface or component")
    assert_contains(skill, "For UI-facing or mixed tickets, UI/UX verification depends on project type")
    assert_contains(skill, "Personal projects / Linear tickets")
    assert_contains(skill, "production app matches the runnable reference app")
    assert_contains(skill, "Job projects / Jira tickets")
    assert_contains(skill, "visual consistency with the rest of the application")
    assert_contains(skill, "sizing, spacing, component usage")
    assert_contains(skill, "Run a user-facing alignment phase until the agent and user share a concrete understanding")
    assert_contains(skill, "ticket-start does not prescribe the plan format or task mechanics")
    assert_contains(skill, "Let the agent harness and active methodology skills decide the exact subagent strategy")
    assert_contains(skill, "Read `bot-identity.md` when setup or activation details are needed")
    assert_contains(skill, "Route these work categories when applicable")
    assert_contains(skill, "Track returned reports compactly enough")
    assert_contains(skill, "Do not route the ticket to PR readiness until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved")
    assert_contains(skill, "CANNOT_VERIFY")
    assert_contains(skill, "Include the `CANNOT_VERIFY` fallback in delegated QA and UI/UX verification requests")
    assert_contains(skill, "perform the needed verification in the main session")

    for markdown_file in sorted(SKILL_DIR.rglob("*.md")):
        text = markdown_file.read_text(encoding="utf-8")
        for forbidden in DOWNSTREAM_SKILL_IDS:
            assert_not_contains(text, forbidden)

    for removed in ("personal-workflow.md", "job-workflow.md", "verification-fix-loops.md"):
        if (SKILL_DIR / removed).exists():
            raise AssertionError(f"ticket-start should not keep stale companion file: {removed}")


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected ticket-start to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
