#!/usr/bin/env python3
"""Contract checks for ticket-start large feature orchestration."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    skill = SKILL_PATH.read_text(encoding="utf-8")

    try:
        check_large_orchestration_contract(skill)
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start large feature orchestration contract")
    return 0


def check_large_orchestration_contract(skill: str) -> None:
    section = section_between(skill, "## Large Feature Orchestration", "## Implement")

    assert_contains(section, "Use this section when the approved plan contains multiple slices")
    assert_contains(section, "root orchestrator")
    assert_contains(section, "child implementer: owns one bounded implementation slice")
    assert_contains(section, "optional grandchild helper")
    assert_contains(section, "browser verifier: verifies integrated user-visible behavior, leaf-only")

    assert_contains(section, "Root -> child -> grandchild is the maximum topology")
    assert_contains(section, "NEEDS_SPLIT")
    assert_contains(section, "Grandchildren are helper probes, not feature owners")
    assert_contains(section, "They must not own a slice")
    assert_contains(section, "use browser automation")
    assert_contains(section, "spawn further agents")

    assert_contains(section, "Every large-feature subagent handoff starts with an active-task block")
    for required_line in (
        "Active task: [specific goal]",
        "AGENTS.md and skill files are policy/context only; do not acknowledge them.",
        "Do the active task now.",
        "Depth budget: [none|may spawn helper grandchildren for non-browser probes only]",
        "Final response schema: [required schema]",
    ):
        assert_contains(section, required_line)

    assert_contains(section, "Every child implementer handoff includes")
    for required_input in (
        "ticket + AC",
        "approved requirements/design artifact",
        "approved plan or slice",
        "Scoping locators",
        "scoped write surface",
        "expected tests/checks",
        "current branch/worktree state",
        "allowed helper probes",
    ):
        assert_contains(section, required_input)

    assert_contains(section, "IMPLEMENTATION_SLICE_RESULT:")
    for required_field in (
        "status: pass|fail|blocked|needs_split",
        "slice_id:",
        "summary:",
        "files_changed:",
        "tests_checks:",
        "helper_grandchildren:",
        "handoff_for_root:",
    ):
        assert_contains(section, required_field)

    assert_contains(section, "BROWSER_VERIFICATION_RESULT:")
    for required_field in (
        "status: pass|fail|blocked",
        "ticket_or_slice:",
        "url:",
        "states_checked:",
        "evidence:",
        "findings:",
    ):
        assert_contains(section, required_field)

    assert_contains(section, "Browser verifier agents are direct children of the root and leaf-only")
    assert_contains(section, "Browser verifiers do not fix code")
    assert_contains(section, "The root monitors every child and any known grandchild")
    assert_contains(section, "Use finite waits")
    assert_contains(section, "send one status follow-up")
    assert_contains(section, "close it and re-dispatch a narrower task")
    assert_contains(section, "Before Ship, no child or grandchild agents may remain live")

    plan = section_between(skill, "## Plan", "## Large Feature Orchestration")
    assert_contains(plan, "Large feature orchestration map")
    for required_map_item in (
        "slice id",
        "owner role",
        "write surface",
        "dependency order or wave",
        "tests/checks",
        "browser verification needs",
        "grandchildren are allowed",
        "exact depth budget",
    ):
        assert_contains(plan, required_map_item)

    implement = section_between(skill, "## Implement", "## Verify")
    assert_contains(implement, "Large feature orchestration: dispatch implementers by the approved orchestration map")
    assert_contains(implement, "Implementers may spawn grandchildren only when the approved orchestration map explicitly allows")
    assert_contains(implement, "Implementers must not dispatch browser automation subagents")

    ship = section_between(skill, "## Ship", "## Verification fix loops")
    assert_contains(ship, "Large feature orchestration, if used, has no live child or grandchild agents")


def section_between(document: str, start_heading: str, end_heading: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(start_heading)}\n(?P<section>.*?)(?=^{re.escape(end_heading)}\n)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(document)
    if not match:
        raise AssertionError(f"missing section from {start_heading!r} to {end_heading!r}")
    return match.group("section")


def assert_contains(haystack: str, needle: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"expected to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
