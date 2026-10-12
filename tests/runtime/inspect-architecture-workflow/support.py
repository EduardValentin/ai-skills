"""Runners and fixture helpers for the architecture command tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / "skills" / "workflows" / "inspect-architecture-workflow"
ARCH = SKILL_DIR / "scripts" / "arch.mjs"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def node_path() -> str:
    node = shutil.which("node")
    assert node is not None, "node is required for these tests"
    return node


def run_arch(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        [node_path(), str(ARCH), *args],
        cwd=cwd,
        env=merged,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def run_node(script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [node_path(), "--input-type=module", "-e", script],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def copy_fixture(name: str, dest: Path) -> Path:
    shutil.copytree(FIXTURES / name, dest, dirs_exist_ok=True)
    return dest


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"},
    )


def init_repo(path: Path) -> None:
    git(["init", "-q", "-b", "main"], path)
    git(["add", "-A"], path)
    git(["commit", "-q", "-m", "fixture"], path)
