#!/usr/bin/env python3
"""Contract checks for ticket-start UI/UX visual verification."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
PERSONAL_WORKFLOW_PATH = REPO_ROOT / "skills" / "ticket-start" / "personal-workflow.md"
FRONTEND_UI_REVIEW_PATH = REPO_ROOT / "skills" / "frontend-ui-review" / "SKILL.md"


def main() -> int:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    personal_workflow = PERSONAL_WORKFLOW_PATH.read_text(encoding="utf-8")
    frontend_ui_review = FRONTEND_UI_REVIEW_PATH.read_text(encoding="utf-8")

    try:
        check_uiux_contract(skill, personal_workflow, frontend_ui_review)
    except AssertionError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start UI/UX visual verification contract")
    return 0


def check_uiux_contract(skill: str, personal_workflow: str, frontend_ui_review: str) -> None:
    required_rule = (
        "Visual verification checks the rendered user-visible outcome and every visually "
        "meaningful state, not hidden templates or implementation proxies."
    )

    assert_contains(skill, required_rule)
    assert_contains(skill, "UI/UX verification remains delegated")
    assert_not_contains(skill, "frontend-ui-review")
    assert_contains(frontend_ui_review, required_rule)
    assert_contains(frontend_ui_review, "DOM computed styles")
    assert_contains(frontend_ui_review, "bounding rects")
    assert_contains(frontend_ui_review, "Matched-element inventory")

    assert_not_contains(skill, "Do not accept template/source inspection")
    assert_not_contains(skill, "proxy-component screenshots")
    assert_not_contains(skill, "storybook-only renders")
    assert_not_contains(skill, "Every verified row has non-blank")

    assert_contains(personal_workflow, required_rule)
    assert_contains(personal_workflow, "same rendered states can be exercised in both apps")


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


def assert_not_contains(haystack: str, needle: str) -> None:
    if needle in haystack:
        raise AssertionError(f"expected not to find {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
