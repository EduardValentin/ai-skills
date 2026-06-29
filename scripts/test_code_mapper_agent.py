#!/usr/bin/env python3
"""Contract checks for the standalone native code-mapper agent."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def assert_contains(text: str, expected: str, context: str) -> None:
    if expected not in text:
        raise AssertionError(f"expected {context} to contain: {expected}")


def assert_not_contains(text: str, unexpected: str, context: str) -> None:
    if unexpected in text:
        raise AssertionError(f"expected {context} not to contain: {unexpected}")


def code_mapper_manifest_block(manifest: str) -> str:
    marker = 'id = "code-mapper"'
    marker_index = manifest.find(marker)
    if marker_index == -1:
        raise AssertionError("missing code-mapper manifest entry")

    block_start = manifest.rfind("[[agent]]", 0, marker_index)
    if block_start == -1:
        raise AssertionError("code-mapper entry is not inside an [[agent]] block")

    block_end = manifest.find("\n[[agent]]", marker_index)
    if block_end == -1:
        block_end = len(manifest)
    return manifest[block_start:block_end]


def main() -> int:
    body_path = REPO_ROOT / "agents" / "code-mapper.md"
    manifest_path = REPO_ROOT / "agents" / "manifest.toml"
    retired_skill_path = REPO_ROOT / "skills" / "codebase-scope-map"

    body = body_path.read_text(encoding="utf-8")
    manifest = manifest_path.read_text(encoding="utf-8")
    mapper_block = code_mapper_manifest_block(manifest)

    if retired_skill_path.exists():
        raise AssertionError(f"retired skill directory still exists: {retired_skill_path}")

    assert_not_contains(body, "codebase-scope-map", "agents/code-mapper.md")
    assert_not_contains(mapper_block, "codebase-scope-map", "code-mapper manifest block")
    assert_not_contains(mapper_block, "preload_skills", "code-mapper manifest block")

    for required in (
        "## Token Discipline",
        "## Prototype / Reference App Rule",
        "## Forbidden Behaviors",
        "## Stop Conditions",
        "## Existing analogous implementations",
    ):
        assert_contains(body, required, "agents/code-mapper.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
