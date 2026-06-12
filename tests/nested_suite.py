"""Shared helpers for grouped Python test suites."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_grouped_python_scripts(
    *,
    suite_dir: Path,
    pattern: str,
    missing_message: str,
    env: dict[str, str] | None = None,
) -> int:
    scripts = sorted(suite_dir.glob(pattern))
    if not scripts:
        raise RuntimeError(missing_message)

    for script in scripts:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=REPO_ROOT,
            env=env,
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
    return len(scripts)
