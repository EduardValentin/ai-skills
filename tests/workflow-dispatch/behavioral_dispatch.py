#!/usr/bin/env python3
"""Run grouped workflow-dispatch behavioral pressure tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent


def main() -> int:
    agent_command = (
        os.environ.get("WORKFLOW_DISPATCH_AGENT_COMMAND", "").strip()
        or os.environ.get("SKILL_TRIGGER_AGENT_COMMAND", "").strip()
    )

    if "--help" in sys.argv:
        print_usage()
        return 0

    if not agent_command:
        print_usage()
        print(
            "FAIL: WORKFLOW_DISPATCH_AGENT_COMMAND or SKILL_TRIGGER_AGENT_COMMAND is required",
            file=sys.stderr,
        )
        return 1

    try:
        nested_count = run_nested_behavioral_pressure(agent_command)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {nested_count} grouped behavioral workflow-dispatch tests", flush=True)
    return 0


def print_usage() -> None:
    print(
        """Usage:
  WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/workflow-dispatch/behavioral_dispatch.py

Fallback:
  If WORKFLOW_DISPATCH_AGENT_COMMAND is unset, SKILL_TRIGGER_AGENT_COMMAND is used.

The agent command receives a prompt on stdin and must print a workflow action
ledger on stdout. The harness runs grouped behavioral tests from
tests/workflow-dispatch/<skill-under-test>/."""
    )


def run_nested_behavioral_pressure(agent_command: str) -> int:
    scripts = sorted(SCRIPT_DIR.glob("*/*_behavioral_pressure.py"))
    if not scripts:
        raise RuntimeError("workflow-dispatch requires grouped *_behavioral_pressure.py tests")

    env = os.environ.copy()
    env["WORKFLOW_DISPATCH_AGENT_COMMAND"] = agent_command

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


if __name__ == "__main__":
    raise SystemExit(main())
