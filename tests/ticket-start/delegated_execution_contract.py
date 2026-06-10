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

    assert_contains(skill, "Do not use for Epics, parent tickets with children requested as one scope")
    assert_contains(skill, "multi-ticket workflow intake")
    assert_contains(skill, "Jira ticket or Linear issue ID as part of an implementation-work request")
    assert_contains(skill, "Use this skill as the main-agent workflow for working one implementation ticket")
    assert_contains(skill, "The main agent stays the user-facing orchestrator")
    assert_contains(skill, "If the ticket is a child issue, subtask, story under an Epic")
    assert_contains(skill, "read the parent tickets or Epic descriptions too")
    assert_contains(skill, "Delegate codebase scoping before planning for implementation tickets")
    assert_contains(skill, "If the scope is clearly trivial, record the skip reason")
    assert_contains(skill, "check `PRD.md` when the ticket or unit of work adds or changes business rules")
    assert_contains(skill, "Check `designs/` or reference apps only when the ticket adds or modifies UI components")
    assert_contains(skill, "corresponding reference surface or component")
    assert_contains(skill, "For UI-facing or mixed tickets, UI/UX verification depends on project type")
    assert_contains(skill, "Personal projects / Linear tickets")
    assert_contains(skill, "production app matches the runnable reference app")
    assert_contains(skill, "Job projects / Jira tickets")
    assert_contains(skill, "visual consistency with the rest of the application")
    assert_contains(skill, "sizing, spacing, component usage")
    assert_contains(skill, "Run a user-facing brainstorming session until the agent and user share a concrete understanding")
    assert_contains(skill, "## Step 3 - Create And Approve The Spec And Plan")
    assert_contains(skill, "The brainstorming phase produces the user-approved spec/design")
    assert_contains(skill, "Do not route plan writing before that approval")
    assert_contains(skill, "After the spec/design is approved, route implementation-plan writing")
    assert_contains(skill, "Get user approval for the implementation plan before coding starts")
    assert_contains(skill, "before both spec approval and implementation-plan approval")
    assert_contains(skill, "After both spec approval and plan approval, implementation begins by delegating work to implementer subagents")
    assert_contains(skill, "minimize dependencies and maximize throughput and quality of work")
    assert_contains(skill, "Respect this ticket sequence")
    assert_contains(skill, "Delegate implementation for the approved plan")
    assert_contains(skill, "Delegate independent review")
    assert_contains(skill, "Delegate QA verification")
    assert_contains(skill, "delegate UI/UX verification")
    assert_contains(skill, "Aggregate findings from independent review, QA, and UI/UX verification")
    assert_contains(skill, "Close execution with a gate note that states whether PR verification is allowed")
    assert_contains(skill, "Track returned reports compactly enough")
    assert_contains(skill, "Do not route the ticket to PR verification until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved")
    assert_contains(skill, "Execution routing is incomplete unless it states that PR verification waits")
    assert_contains(skill, "is not allowed while any required report is missing")
    assert_contains(skill, "CANNOT_VERIFY")
    assert_contains(skill, "Include the `CANNOT_VERIFY` fallback in delegated QA and UI/UX verification requests")
    assert_contains(skill, "When routing verifier work, include this fallback instruction")
    assert_contains(skill, "perform the needed verification in the main session")

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


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


def assert_line_count_at_most(text: str, limit: int) -> None:
    line_count = len(text.splitlines())
    if line_count > limit:
        raise AssertionError(f"expected ticket-start to be at most {limit} lines, found {line_count}")


if __name__ == "__main__":
    raise SystemExit(main())
