#!/usr/bin/env python3
"""Command-line entry point for repository AI skills tooling."""

from __future__ import annotations

from importlib.machinery import ModuleSpec
from pathlib import Path
import sys
import tempfile
from types import ModuleType


if sys.version_info < (3, 11):
    print("ai_skills requires Python 3.11 or newer.", file=sys.stderr)
    raise SystemExit(2)

from subprocess import TimeoutExpired


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIRECTORY.parent
_UNIT_TEST_PATTERN = "test*.py"


def _bind_repository_scripts_package() -> None:
    package = ModuleType("scripts")
    package.__file__ = str(SCRIPT_DIRECTORY / "__init__.py")
    package.__package__ = "scripts"
    package.__path__ = [str(SCRIPT_DIRECTORY)]
    package_spec = ModuleSpec("scripts", loader=None, is_package=True)
    package_spec.submodule_search_locations = [str(SCRIPT_DIRECTORY)]
    package.__spec__ = package_spec
    sys.modules["scripts"] = package


if __name__ == "__main__":
    if not sys.flags.isolated:
        print(
            "Invoke scripts/ai-skills so Python isolation is active before startup.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    _bind_repository_scripts_package()

from scripts.ai_skills_lib.config import build_parser
from scripts.ai_skills_lib.authored_content import render_safe_diagnostic_text
from scripts.ai_skills_lib.issues import print_grouped_issues


def run_all_evaluation_harness(*args, **kwargs):
    from scripts.ai_skills_lib.all_validation import run_all_evaluation_harness as run

    return run(*args, **kwargs)


def run_behavior_eval_harness(*args, **kwargs):
    from scripts.ai_skills_lib.eval_validation import run_behavior_eval_harness as run

    return run(*args, **kwargs)


def run_local_install_check(*args, **kwargs):
    from scripts.ai_skills_lib.local_installs import run_local_install_check as run

    return run(*args, **kwargs)


def run_runtime_validation(*args, **kwargs):
    from scripts.ai_skills_lib.runtime_validation import run_runtime_validation as run

    return run(*args, **kwargs)


def run_ci_validation(*args, **kwargs):
    from scripts.ai_skills_lib.static_validation import run_ci_validation as run

    return run(*args, **kwargs)


def run_reference_conformance(*args, **kwargs):
    from scripts.ai_skills_lib.static_validation import run_reference_conformance as run

    return run(*args, **kwargs)


def run_static_validation(*args, **kwargs):
    from scripts.ai_skills_lib.static_validation import run_static_validation as run

    return run(*args, **kwargs)


def run_trigger_query_harness(*args, **kwargs):
    from scripts.ai_skills_lib.trigger_validation import run_trigger_query_harness as run

    return run(*args, **kwargs)


def run_unit_tests(root: Path) -> int:
    """Run the deterministic repository unit-test suite."""
    from scripts.ai_skills_lib.runtime_validation import (
        RuntimeTestLayoutError,
        UNIT_TEST_TIMEOUT_SECONDS,
        materialized_test_repository,
        require_contained_test_directory,
    )

    try:
        with materialized_test_repository(root) as snapshot_root:
            unit_test_root = require_contained_test_directory(
                snapshot_root,
                Path("tests/ai_skills"),
            )
            return _run_unit_test_snapshot(
                snapshot_root,
                unit_test_root,
                timeout_seconds=UNIT_TEST_TIMEOUT_SECONDS,
            )
    except RuntimeTestLayoutError as error:
        print(
            "validate unit: FAILED "
            f"({render_safe_diagnostic_text(str(error))})"
        )
        return 1


def _run_unit_test_snapshot(
    snapshot_root: Path,
    unit_test_root: Path,
    *,
    timeout_seconds: int,
) -> int:
    from scripts.ai_skills_lib.runtime_validation import (
        isolated_test_environment,
        report_test_process_output,
        run_bounded_test_process,
    )

    unit_test_files, discovery_issue = _validated_unit_test_files(
        snapshot_root,
        unit_test_root,
    )
    if discovery_issue is not None:
        print(
            "validate unit: FAILED "
            f"({render_safe_diagnostic_text(discovery_issue)})"
        )
        return 1
    try:
        with tempfile.TemporaryDirectory(
            prefix="ai-skills-unit-tests-"
        ) as state:
            completed = run_bounded_test_process(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "pytest",
                    "-q",
                    "-ra",
                    f"--override-ini=python_files={_UNIT_TEST_PATTERN}",
                    *(
                        str(path.relative_to(snapshot_root))
                        for path in unit_test_files
                    ),
                ],
                cwd=snapshot_root,
                env=isolated_test_environment(Path(state)),
                timeout=timeout_seconds,
            )
            output_is_safe = report_test_process_output(
                completed,
                "Unit test suite",
            )
        if not output_is_safe:
            print(
                "validate unit: FAILED "
                "(captured output was quarantined)"
            )
            return 1
        return 0 if completed.returncode == 0 else 1
    except TimeoutExpired:
        print(
            "validate unit: FAILED "
            f"(exceeded {timeout_seconds}s timeout)"
        )
        return 1
    except OSError as error:
        print(
            "validate unit: FAILED "
            f"({render_safe_diagnostic_text(str(error))})"
        )
        return 1


def _validated_unit_test_files(
    snapshot_root: Path,
    unit_test_root: Path,
) -> tuple[tuple[Path, ...], str | None]:
    package_root = snapshot_root / "tests"
    try:
        unit_test_root.relative_to(package_root)
    except ValueError:
        return (), "unit test directory is outside the tests package"
    test_candidates = tuple(sorted(unit_test_root.rglob(_UNIT_TEST_PATTERN)))
    if any(not path.is_file() or path.is_symlink() for path in test_candidates):
        return (), "unit test module candidates must be regular files"
    test_files = test_candidates
    if not test_files:
        return (), f"unit test suite has no {_UNIT_TEST_PATTERN} modules"
    required_packages = {package_root, unit_test_root}
    for test_file in test_files:
        current = test_file.parent
        while current != unit_test_root:
            required_packages.add(current)
            current = current.parent
    for package in sorted(required_packages, key=str):
        initializer = package / "__init__.py"
        if initializer.is_symlink() or not initializer.is_file():
            return (), (
                f"{package.relative_to(snapshot_root)} contains discoverable "
                "unit tests but lacks a regular __init__.py"
            )
    return test_files, None


def _report_validation(label: str, issues) -> int:
    if issues:
        print_grouped_issues(issues)
        print(f"{label}: FAILED ({len(issues)} issues)")
        return 1
    print(f"{label}: OK")
    return 0


def _deterministic_failure_summary(
    *,
    issues,
    unit_failed: bool,
    runtime_failed: bool,
) -> str:
    phases: list[str] = []
    if issues:
        phases.append(f"static/conformance: {len(issues)} issues")
    if unit_failed:
        phases.append("unit tests")
    if runtime_failed:
        phases.append("runtime tests")
    return ", ".join(phases)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "evals" and args.evals_command == "aggregate":
        from scripts.ai_skills_lib.eval_core import (
            ResultArtifactError,
            aggregate_results,
            benchmark_exit_code,
            format_benchmark_summary,
            resolve_external_result_path,
        )

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
    if args.command == "validate" and args.target == "conformance":
        try:
            issues = run_reference_conformance(REPOSITORY_ROOT)
        except RuntimeError as error:
            print(f"validate conformance: FAILED: {error}")
            return 1
        return _report_validation("validate conformance", issues)
    if args.command == "validate" and args.target == "runtime":
        return run_runtime_validation(REPOSITORY_ROOT)
    if args.command == "validate" and args.target == "ci-all":
        try:
            issues = run_ci_validation(REPOSITORY_ROOT)
        except RuntimeError as error:
            print(f"validate ci-all: FAILED: {error}")
            return 1
        unit_failed = run_unit_tests(REPOSITORY_ROOT) != 0
        runtime_failed = run_runtime_validation(REPOSITORY_ROOT) != 0
        if issues:
            print_grouped_issues(issues)
        if issues or unit_failed or runtime_failed:
            detail = _deterministic_failure_summary(
                issues=issues,
                unit_failed=unit_failed,
                runtime_failed=runtime_failed,
            )
            print(f"validate ci-all: FAILED ({detail})")
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
        unit_failed = run_unit_tests(REPOSITORY_ROOT) != 0
        runtime_failed = run_runtime_validation(REPOSITORY_ROOT) != 0
        if issues:
            print_grouped_issues(issues)
        if issues or unit_failed or runtime_failed:
            detail = _deterministic_failure_summary(
                issues=issues,
                unit_failed=unit_failed,
                runtime_failed=runtime_failed,
            )
            print(f"validate all: DETERMINISTIC CHECKS FAILED ({detail})")
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
    raise AssertionError("argparse accepted an undispatched command")


if __name__ == "__main__":
    raise SystemExit(main())
