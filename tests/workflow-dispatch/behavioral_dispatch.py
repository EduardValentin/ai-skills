#!/usr/bin/env python3
"""Run grouped workflow-dispatch behavioral pressure tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.append(str(REPO_ROOT / "tests"))

from nested_suite import run_grouped_python_scripts  # noqa: E402


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
ledger on stdout. Grouped tests may inject the loaded parent skill body to
pressure-test workflow instructions. Downstream skill discovery checks must rely
on the installed harness without an injected skill index."""
    )


def run_nested_behavioral_pressure(agent_command: str) -> int:
    env = os.environ.copy()
    env["WORKFLOW_DISPATCH_AGENT_COMMAND"] = agent_command

    return run_grouped_python_scripts(
        suite_dir=SCRIPT_DIR,
        pattern="*/*_behavioral_pressure.py",
        missing_message="workflow-dispatch requires grouped *_behavioral_pressure.py tests",
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
