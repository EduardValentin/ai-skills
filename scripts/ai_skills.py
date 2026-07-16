#!/usr/bin/env python3
"""Command-line entry point for repository AI skills tooling."""

from __future__ import annotations

import sys
from pathlib import Path
import subprocess


if sys.version_info < (3, 11):
    print("ai_skills requires Python 3.11 or newer.", file=sys.stderr)
    raise SystemExit(2)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.ai_skills_lib.config import build_parser, command_label
from scripts.ai_skills_lib.issues import print_grouped_issues
from scripts.ai_skills_lib.static_validation import (
    run_reference_conformance,
    run_static_validation,
)


def run_unit_tests(root: Path) -> int:
    """Run the deterministic repository unit-test suite."""
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests/ai_skills"],
        cwd=root,
        check=False,
    )
    return completed.returncode


def _report_validation(label: str, issues) -> int:
    if issues:
        print_grouped_issues(issues)
        print(f"{label}: FAILED ({len(issues)} issues)")
        return 1
    print(f"{label}: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate" and args.target == "static":
        return _report_validation("validate static", run_static_validation(REPOSITORY_ROOT))
    if args.command == "validate" and args.target == "ci-all":
        failed = run_unit_tests(REPOSITORY_ROOT) != 0
        issues = run_static_validation(REPOSITORY_ROOT)
        try:
            issues.extend(run_reference_conformance(REPOSITORY_ROOT))
        except RuntimeError as error:
            print(f"validate ci-all: FAILED: {error}")
            return 1
        if issues:
            print_grouped_issues(issues)
            failed = True
        if failed:
            print(f"validate ci-all: FAILED ({len(issues)} validation issues)")
            return 1
        print("validate ci-all: OK")
        return 0
    print(f"{command_label(args)}: not implemented")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
