"""Compatibility helpers for legacy Python contract entrypoints."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT / "tests"))

from contract_harness import run_contract_suite  # noqa: E402


def run_compat_contract(contract_relative_path: str, pass_message: str) -> int:
    try:
        run_contract_suite(REPO_ROOT / contract_relative_path)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(pass_message)
    return 0
