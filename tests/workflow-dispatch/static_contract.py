#!/usr/bin/env python3
"""Compatibility wrapper for workflow-dispatch TOML contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.append(str(REPO_ROOT / "tests"))

from contract_harness import run_contract_suite  # noqa: E402


CONTRACT_PATH = REPO_ROOT / "tests" / "contracts" / "workflow-dispatch.toml"


def main() -> int:
    try:
        run_contract_suite(CONTRACT_PATH)
        run_harness_contract()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: workflow-dispatch colocated contracts satisfy static contracts")
    return 0


def run_harness_contract() -> None:
    script = SCRIPT_DIR / "workflow_harness_contract.py"
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


if __name__ == "__main__":
    raise SystemExit(main())
