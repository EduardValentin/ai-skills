#!/usr/bin/env python3
"""Exercise the repo-level skill sync utility in an isolated temp workspace."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def assert_file_contains(path: Path, expected: str) -> None:
    if expected not in path.read_text():
        raise AssertionError(f"expected {path} to contain: {expected}")


def assert_missing(path: Path) -> None:
    if path.exists():
        raise AssertionError(f"expected missing path: {path}")


def run_sync(script: Path, repo: Path, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AI_SKILLS_REPO"] = str(repo)
    env["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(script), *args],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )


def main() -> int:
    script = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("scripts/sync_skill.py")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        repo = tmp_root / "repo"
        home = tmp_root / "home"
        skill = "demo-skill"

        canonical = repo / "skills" / skill
        canonical_tests = canonical / "tests"
        canonical_tests.mkdir(parents=True)
        home.mkdir()
        (canonical / "SKILL.md").write_text("canonical v1\n")
        (canonical_tests / ".gitkeep").write_text("do not sync\n")

        push = run_sync(script, repo, home, "push", skill)
        if push.returncode != 0:
            raise AssertionError(push.stderr or push.stdout)

        claude_skill = home / ".claude" / "skills" / skill
        codex_skill = home / ".codex" / "skills" / skill
        assert_file_contains(claude_skill / "SKILL.md", "canonical v1")
        assert_file_contains(codex_skill / "SKILL.md", "canonical v1")
        assert_missing(claude_skill / "tests" / ".gitkeep")
        assert_missing(codex_skill / "tests" / ".gitkeep")

        (codex_skill / "SKILL.md").write_text("codex v2\n")
        pull = run_sync(script, repo, home, "pull", skill, "codex")
        if pull.returncode != 0:
            raise AssertionError(pull.stderr or pull.stdout)

        assert_file_contains(canonical / "SKILL.md", "codex v2")
        assert_file_contains(claude_skill / "SKILL.md", "codex v2")

        missing = run_sync(script, repo, home, "push", "missing-skill")
        if missing.returncode == 0:
            raise AssertionError("expected missing skill push to fail")
        if "missing canonical skill" not in missing.stderr:
            raise AssertionError(missing.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
