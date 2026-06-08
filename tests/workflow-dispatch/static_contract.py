#!/usr/bin/env python3
"""Deterministic contract checks for grouped workflow-dispatch scenarios."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent


def main() -> int:
    try:
        check_downstream_discovery_is_black_box()
        nested_count = run_nested_contracts()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {nested_count} grouped workflow-dispatch contracts satisfy static contracts")
    return 0


def run_nested_contracts() -> int:
    scripts = sorted(SCRIPT_DIR.glob("*/*_contract.py"))
    if not scripts:
        raise RuntimeError("workflow-dispatch requires grouped *_contract.py tests")

    for script in scripts:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode != 0:
            raise RuntimeError(
                f"{script.relative_to(REPO_ROOT)} failed with exit code {completed.returncode}"
            )
    return len(scripts)


def check_downstream_discovery_is_black_box() -> None:
    helper = SCRIPT_DIR / "auto_discovery.py"
    source = helper.read_text(encoding="utf-8")
    forbidden = (
        "Available skills:",
        "discover_skill_files",
        "parse_frontmatter",
        "skill_index",
        "SKILL.md",
    )
    for term in forbidden:
        if term in source:
            raise ValueError(
                f"{helper.relative_to(REPO_ROOT)} must not inject skill context: {term}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
