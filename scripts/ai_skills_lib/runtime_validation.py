"""Deterministic repository runtime-test validation."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


RUNTIME_TESTS_PATH = Path("tests/runtime")


class RuntimeTestLayoutError(ValueError):
    """The repository runtime-test root violates its directory contract."""


def discover_runtime_suites(root: Path) -> tuple[Path, ...]:
    """Return repository runtime-test suite directories in stable order."""
    runtime_root = root / RUNTIME_TESTS_PATH
    if runtime_root.is_symlink():
        raise RuntimeTestLayoutError("tests/runtime must be a non-symlink directory")
    if not runtime_root.exists():
        return ()
    if not runtime_root.is_dir():
        raise RuntimeTestLayoutError("tests/runtime must be a non-symlink directory")

    suites: list[Path] = []
    for entry in sorted(runtime_root.iterdir(), key=lambda path: path.name):
        if entry.is_symlink() or not entry.is_dir() or entry.name.startswith("."):
            raise RuntimeTestLayoutError(
                f"unsupported tests/runtime entry: {entry.name}"
            )
        test_modules = tuple(
            path
            for path in entry.rglob("test_*.py")
            if path.is_file() and not path.is_symlink()
        )
        if not test_modules:
            raise RuntimeTestLayoutError(
                f"runtime suite '{entry.name}' has no test_*.py modules"
            )
        suites.append(entry)
    if not suites:
        raise RuntimeTestLayoutError("tests/runtime contains no runtime test suites")
    return tuple(suites)


def run_runtime_validation(root: Path) -> int:
    """Run deterministic repository runtime tests."""
    try:
        suites = discover_runtime_suites(root)
    except (OSError, RuntimeTestLayoutError) as error:
        print(f"validate runtime: FAILED ({error})")
        return 1
    if not suites:
        print("validate runtime: OK (no runtime test suites found)")
        return 0

    failed_suites: list[str] = []
    for suite in suites:
        relative_suite = suite.relative_to(root)
        print(f"\nRuntime suite: {suite.name}", flush=True)
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-ra", str(relative_suite)],
                cwd=root,
                check=False,
            )
        except OSError as error:
            failed_suites.append(suite.name)
            print(f"Runtime suite {suite.name}: FAILED ({error})")
            continue
        if completed.returncode == 0:
            print(f"Runtime suite {suite.name}: OK")
        else:
            failed_suites.append(suite.name)
            print(
                f"Runtime suite {suite.name}: FAILED "
                f"(pytest exit {completed.returncode})"
            )

    if failed_suites:
        print(
            "validate runtime: FAILED "
            f"({len(failed_suites)} of {len(suites)} suites failed)"
        )
        return 1
    print(f"validate runtime: OK ({len(suites)} suites passed)")
    return 0
