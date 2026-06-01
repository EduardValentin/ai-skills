#!/usr/bin/env python3
"""Contract checks for ticket-start UI/UX visual verification."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
PERSONAL_WORKFLOW_PATH = REPO_ROOT / "skills" / "ticket-start" / "personal-workflow.md"


def main() -> int:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    personal_workflow = PERSONAL_WORKFLOW_PATH.read_text(encoding="utf-8")

    try:
        check_uiux_contract(skill, personal_workflow)
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start UI/UX visual verification contract")
    return 0


def check_uiux_contract(skill: str, personal_workflow: str) -> None:
    verify = section_between(skill, "## Verify", "## Ship")

    required_rule = (
        "Visual verification checks the rendered user-visible outcome and every visually "
        "meaningful state, not hidden templates or implementation proxies."
    )

    assert_contains(skill, required_rule)
    assert_contains(verify, required_rule)
    assert_contains(verify, "rendered user-visible outcome")
    assert_contains(verify, "every visually meaningful state")
    assert_contains(verify, "not hidden templates or implementation proxies")
    assert_contains(verify, "Do not accept template/source inspection")
    assert_contains(verify, "proxy-component screenshots")
    assert_contains(verify, "storybook-only renders")

    assert_contains(personal_workflow, required_rule)
    assert_contains(personal_workflow, "same rendered states can be exercised in both apps")

    red_flags = section_between(
        skill,
        "## Red flags — stop and recover",
        "If any of these is true: stop, name the violation, and recover before continuing.",
    )
    assert_contains(red_flags, "hidden templates or implementation proxies")


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
