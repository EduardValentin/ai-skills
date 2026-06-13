#!/usr/bin/env python3
"""Run colocated TOML-backed deterministic contract suites."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "tests"))

from contract_harness import run_contract_suite  # noqa: E402


def main() -> int:
    args = parse_args()
    try:
        suite_paths = discover_contract_suites(args.suite)
        if args.list:
            for path in suite_paths:
                print(path.relative_to(REPO_ROOT))
            return 0

        for path in suite_paths:
            run_contract_suite(path)
            print(f"PASS: {path.relative_to(REPO_ROOT)}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(suite_paths)} TOML contract suites")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic contract checks defined in contracts.toml files.",
    )
    parser.add_argument("--suite", help="Run one contract suite path or name fragment.")
    parser.add_argument("--list", action="store_true", help="List discovered suites and exit.")
    return parser.parse_args()


def discover_contract_suites(suite_filter: str = "") -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in (
        "tests/contracts/*.toml",
        "skills/*/tests/contracts.toml",
        "plugins/*/tests/contracts.toml",
        "plugins/*/skills/*/tests/contracts.toml",
    ):
        paths.update(REPO_ROOT.glob(pattern))

    selected = tuple(
        sorted(
            path for path in paths
            if not suite_filter or suite_filter in str(path.relative_to(REPO_ROOT))
        )
    )
    if not selected:
        detail = f" matching {suite_filter!r}" if suite_filter else ""
        raise ValueError(f"no contract suites found{detail}")
    return selected


if __name__ == "__main__":
    raise SystemExit(main())
