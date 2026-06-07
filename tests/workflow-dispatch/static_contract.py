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


if __name__ == "__main__":
    raise SystemExit(main())
