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
from scripts.ai_skills_lib.all_validation import run_all_evaluation_harness
from scripts.ai_skills_lib.eval_core import (
    ResultArtifactError,
    aggregate_results,
    benchmark_exit_code,
    format_benchmark_summary,
    resolve_external_result_path,
)
from scripts.ai_skills_lib.eval_validation import run_behavior_eval_harness
from scripts.ai_skills_lib.issues import print_grouped_issues
from scripts.ai_skills_lib.local_installs import run_local_install_check
from scripts.ai_skills_lib.runtime_validation import run_runtime_validation
from scripts.ai_skills_lib.static_validation import (
    run_ci_validation,
    run_static_validation,
)
from scripts.ai_skills_lib.trigger_validation import run_trigger_query_harness


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
    if args.command == "evals" and args.evals_command == "aggregate":
        try:
            results_dir = resolve_external_result_path(args.results_dir)
            print(f"Results: {results_dir}")
            benchmark = aggregate_results(results_dir, args.grade_source)
            summary = format_benchmark_summary(benchmark)
            exit_code = benchmark_exit_code(benchmark)
        except ResultArtifactError as error:
            print(f"evals aggregate: FAILED: {error}")
            return 2
        print(summary)
        print("evals aggregate: OK" if exit_code == 0 else "evals aggregate: ASSERTIONS FAILED")
        return exit_code
    if args.command == "validate" and args.target == "static":
        return _report_validation("validate static", run_static_validation(REPOSITORY_ROOT))
    if args.command == "validate" and args.target == "runtime":
        return run_runtime_validation(REPOSITORY_ROOT)
    if args.command == "validate" and args.target == "ci-all":
        try:
            issues = run_ci_validation(REPOSITORY_ROOT)
        except RuntimeError as error:
            print(f"validate ci-all: FAILED: {error}")
            return 1
        failed = run_unit_tests(REPOSITORY_ROOT) != 0
        if run_runtime_validation(REPOSITORY_ROOT) != 0:
            failed = True
        if issues:
            print_grouped_issues(issues)
            failed = True
        if failed:
            print(f"validate ci-all: FAILED ({len(issues)} validation issues)")
            return 1
        print("validate ci-all: OK")
        return 0
    if args.command == "validate" and args.target == "triggers":
        return run_trigger_query_harness(
            REPOSITORY_ROOT,
            harness=args.harness,
            runs=args.runs,
            skill_filter=args.skill,
            query_filter=args.query,
            results_dir=args.results_dir,
            max_concurrency=args.max_concurrency,
        )
    if args.command == "validate" and args.target == "evals":
        return run_behavior_eval_harness(
            REPOSITORY_ROOT,
            harness=args.harness,
            skill_filter=args.skill,
            case_filter=args.case,
            results_dir=args.results_dir,
            max_concurrency=args.max_concurrency,
        )
    if args.command == "validate" and args.target == "all":
        try:
            issues = run_ci_validation(REPOSITORY_ROOT)
        except RuntimeError as error:
            print(f"validate all: FAILED: {error}")
            return 1
        failed = run_unit_tests(REPOSITORY_ROOT) != 0
        if run_runtime_validation(REPOSITORY_ROOT) != 0:
            failed = True
        if issues:
            print_grouped_issues(issues)
            failed = True
        if failed:
            print(f"validate all: DETERMINISTIC CHECKS FAILED ({len(issues)} validation issues)")
            return 1
        return run_all_evaluation_harness(
            REPOSITORY_ROOT,
            harness=args.harness,
            runs=args.runs,
            skill_filter=args.skill,
            results_dir=args.results_dir,
            max_concurrency=args.max_concurrency,
        )
    if args.command == "check-local-installs":
        return run_local_install_check(
            REPOSITORY_ROOT,
            harness=args.harness,
        )
    print(f"{command_label(args)}: not implemented")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
