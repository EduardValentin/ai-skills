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
    required_terms = (
        "name: ui-verification",
        "Visual verification checks the rendered user-visible outcome and every visually meaningful state",
        "## Inventory Scoping",
        "requires an affected-element inventory before normal verification starts",
        "If the caller did not provide an affected-element or matched-element inventory",
        "produce or obtain one before normal verification",
        "Prefer delegated scoping when available",
        "return `BLOCKED` unless the caller explicitly requests best-effort in-session scoping",
        "ticket description",
        "diff or changed UI files",
        "reference or production comparison basis",
        "must not skip the scoping step or invent an inventory from visual impressions alone",
        "Prefer the host's native browser automation",
        "drive Playwright through the shell",
        "degraded manual evidence",
        "CLEAN requires complete DOM evidence",
        "Starting normal verification without a caller-supplied inventory, delegated scoped inventory, or explicitly requested best-effort in-session scoped inventory",
        "Do not replace DOM evidence with visual impressions",
    )
    for term in required_terms:
        assert_contains(skill, term, "ui-verification skill")

    forbidden_terms = (
        "frontend" + "-ui-review",
        "Frontend UI " + "Review",
    )
    for term in forbidden_terms:
        assert_not_contains(skill, term, "ui-verification skill")


def check_metadata(metadata: str) -> None:
    for term in ("UI Verification", "$ui-verification", "rendered", "DOM"):
        assert_contains(metadata, term, "ui-verification metadata")
    assert_not_contains(metadata, "frontend" + "-ui-review", "ui-verification metadata")


def assert_contains(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"{context} must contain {needle!r}")


def assert_not_contains(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"{context} must not contain {needle!r}")


if __name__ == "__main__":
    raise SystemExit(main())
