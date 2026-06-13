#!/usr/bin/env python3
"""Compatibility wrapper for ui-verification TOML contracts."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "tests"))

from contract_compat import run_compat_contract  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(
        run_compat_contract(
            "skills/ui-verification/tests/contracts.toml",
            "PASS: ui-verification contract",
        )
    )
