#!/usr/bin/env python3
"""Contract checks for ui-verification."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ui-verification" / "SKILL.md"
OPENAI_METADATA = REPO_ROOT / "skills" / "ui-verification" / "agents" / "openai.yaml"


def main() -> int:
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        metadata = OPENAI_METADATA.read_text(encoding="utf-8")
        check_skill_contract(skill)
        check_metadata(metadata)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ui-verification contract")
    return 0


def check_skill_contract(skill: str) -> None:
    forbidden_terms = (
        "frontend" + "-ui-review",
        "Frontend UI " + "Review",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term, "ui-verification skill")


def check_metadata(metadata: str) -> None:
    assert_not_contains(metadata, "frontend" + "-ui-review", "ui-verification metadata")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
