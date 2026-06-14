#!/usr/bin/env python3
"""Exercise native agent generation and sync in an isolated temp workspace."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


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


def assert_file_contains(path: Path, expected: str) -> None:
    if expected not in path.read_text(encoding="utf-8"):
        raise AssertionError(f"expected {path} to contain: {expected}")


def main() -> int:
    script = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("scripts/sync_native_agents.py")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        repo = tmp_root / "repo"
        home = tmp_root / "home"
        agents = repo / "agents"
        agents.mkdir(parents=True)
        home.mkdir()

        (agents / "mapper.md").write_text("# Mapper\n\nMap code precisely.\n", encoding="utf-8")
        (agents / "manifest.toml").write_text(
            """
version = 1

[[agent]]
id = "demo-mapper"
source = "mapper.md"
description = "Read-only mapper for implementation scoping."
groups = ["ticket-start"]
preload_skills = ["codebase-scope-map"]

[agent.codex]
model = "gpt-5.4-mini"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"

[agent.claude]
model = "sonnet"
effort = "medium"
permissionMode = "plan"
tools = ["Read", "Glob", "Grep", "Bash"]
color = "cyan"
""".lstrip(),
            encoding="utf-8",
        )

        push = run_sync(script, repo, home, "push", "--group", "ticket-start")
        if push.returncode != 0:
            raise AssertionError(push.stderr or push.stdout)

        codex_agent = home / ".codex" / "agents" / "demo-mapper.toml"
        claude_agent = home / ".claude" / "agents" / "demo-mapper.md"
        assert_file_contains(codex_agent, 'name = "demo-mapper"')
        assert_file_contains(codex_agent, 'sandbox_mode = "read-only"')
        assert_file_contains(codex_agent, "developer_instructions = ")
        assert_file_contains(codex_agent, str(home / ".codex" / "skills" / "codebase-scope-map" / "SKILL.md"))
        assert_file_contains(claude_agent, 'name: "demo-mapper"')
        assert_file_contains(claude_agent, 'permissionMode: "plan"')
        assert_file_contains(claude_agent, '  - "codebase-scope-map"')
        assert_file_contains(claude_agent, "Map code precisely.")

        check = run_sync(script, repo, home, "check", "--group", "ticket-start")
        if check.returncode != 0:
            raise AssertionError(check.stderr or check.stdout)

        codex_agent.write_text(codex_agent.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
        drift = run_sync(script, repo, home, "check", "--group", "ticket-start")
        if drift.returncode == 0:
            raise AssertionError("expected check to fail after installed file drift")
        if "out of sync" not in drift.stderr:
            raise AssertionError(drift.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
