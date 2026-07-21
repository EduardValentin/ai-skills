from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPOSITORY_ROOT / "scripts" / "sync_native_agents.py"


def run_sync(
    repo: Path,
    home: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["AI_SKILLS_REPO"] = str(repo)
    environment["HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), *args],
        check=False,
        env=environment,
        text=True,
        capture_output=True,
    )


class NativeAgentSyncTests(unittest.TestCase):
    def assert_file_contains(self, path: Path, expected: str) -> None:
        self.assertIn(expected, path.read_text(encoding="utf-8"))

    def test_push_check_and_drift_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            repo = temporary_root / "repo"
            home = temporary_root / "home"
            agents = repo / "agents"
            agents.mkdir(parents=True)
            home.mkdir()
            codex_home = home / ".codex"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                """
model = "gpt-5.5"

[agents.existing-agent]
description = "An existing unmanaged agent."
config_file = "agents/existing-agent.toml"
""".lstrip(),
                encoding="utf-8",
            )
            (agents / "mapper.md").write_text(
                "# Mapper\n\nMap code precisely.\n",
                encoding="utf-8",
            )
            (agents / "manifest.toml").write_text(
                """
version = 1

[[agent]]
id = "demo-mapper"
source = "mapper.md"
description = "Read-only mapper for implementation scoping."
groups = ["ticket-workflow"]
preload_skills = ["demo-scope-skill"]

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

            push = run_sync(repo, home, "push", "--group", "ticket-workflow")
            self.assertEqual(push.returncode, 0, push.stderr or push.stdout)

            codex_agent = home / ".codex" / "agents" / "demo-mapper.toml"
            codex_config = home / ".codex" / "config.toml"
            claude_agent = home / ".claude" / "agents" / "demo-mapper.md"
            self.assert_file_contains(codex_agent, 'sandbox_mode = "read-only"')
            self.assert_file_contains(codex_agent, "developer_instructions = ")
            self.assert_file_contains(
                codex_agent,
                str(
                    home
                    / ".codex"
                    / "skills"
                    / "demo-scope-skill"
                    / "SKILL.md"
                ),
            )
            self.assert_file_contains(codex_agent, "enabled = true")
            self.assert_file_contains(codex_config, "[agents.existing-agent]")
            self.assert_file_contains(
                codex_config,
                "# BEGIN ai-skills native agent registration: demo-mapper",
            )
            self.assert_file_contains(codex_config, "[agents.demo-mapper]")
            self.assert_file_contains(
                codex_config,
                'description = "Read-only mapper for implementation scoping."',
            )
            self.assert_file_contains(
                codex_config,
                'config_file = "agents/demo-mapper.toml"',
            )
            self.assert_file_contains(claude_agent, 'name: "demo-mapper"')
            self.assert_file_contains(claude_agent, 'permissionMode: "plan"')
            self.assert_file_contains(claude_agent, '  - "demo-scope-skill"')
            self.assert_file_contains(claude_agent, "Map code precisely.")

            check = run_sync(repo, home, "check", "--group", "ticket-workflow")
            self.assertEqual(check.returncode, 0, check.stderr or check.stdout)

            codex_agent.write_text(
                codex_agent.read_text(encoding="utf-8") + "# drift\n",
                encoding="utf-8",
            )
            drift = run_sync(repo, home, "check", "--group", "ticket-workflow")
            self.assertNotEqual(drift.returncode, 0)
            self.assertIn("out of sync", drift.stderr)


if __name__ == "__main__":
    unittest.main()
