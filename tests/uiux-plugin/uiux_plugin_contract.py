#!/usr/bin/env python3
"""Compatibility wrapper for UIUX plugin TOML contracts."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "tests"))

from contract_harness import run_contract_suite  # noqa: E402


CONTRACT_PATH = REPO_ROOT / "plugins" / "uiux" / "tests" / "contracts.toml"


def main() -> int:
    try:
        run_contract_suite(CONTRACT_PATH)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: uiux plugin uses colocated TOML contract tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
