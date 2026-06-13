#!/usr/bin/env python3
"""Compatibility wrapper for canonical skill behavioral coverage contracts."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "tests"))

from contract_harness import run_contract_suite  # noqa: E402


CONTRACT_PATH = REPO_ROOT / "tests" / "contracts" / "behavioral-coverage.toml"


def main() -> int:
    try:
        run_contract_suite(CONTRACT_PATH)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: canonical skills use TOML-backed behavioral pressure tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
