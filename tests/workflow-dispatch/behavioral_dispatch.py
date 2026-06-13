#!/usr/bin/env python3
"""Run grouped workflow-dispatch behavioral pressure tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.append(str(REPO_ROOT / "tests"))
sys.path.append(str(SCRIPT_DIR))

from harness import run_workflow_dispatch_suite_from_path  # noqa: E402


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
ledger on stdout. Colocated workflow-dispatch TOML suites inject the loaded
parent skill body to pressure-test workflow instructions. Downstream skill
discovery checks must rely on the installed harness without an injected skill
index."""
    )


def run_nested_behavioral_pressure(agent_command: str) -> int:
    suite_paths = discover_workflow_dispatch_suites()
    if not suite_paths:
        raise RuntimeError("workflow-dispatch requires workflow-dispatch.toml scenario tests")

    original = os.environ.get("WORKFLOW_DISPATCH_AGENT_COMMAND")
    os.environ["WORKFLOW_DISPATCH_AGENT_COMMAND"] = agent_command
    try:
        for path in suite_paths:
            result = run_workflow_dispatch_suite_from_path(path)
            if result != 0:
                raise RuntimeError(
                    f"{path.relative_to(REPO_ROOT)} failed with exit code {result}"
                )
    finally:
        if original is None:
            os.environ.pop("WORKFLOW_DISPATCH_AGENT_COMMAND", None)
        else:
            os.environ["WORKFLOW_DISPATCH_AGENT_COMMAND"] = original

    return len(suite_paths)


def discover_workflow_dispatch_suites() -> tuple[Path, ...]:
    paths: set[Path] = set()
    paths.update(SCRIPT_DIR.glob("*/scenarios.toml"))
    paths.update(REPO_ROOT.glob("skills/*/tests/workflow-dispatch.toml"))
    paths.update(REPO_ROOT.glob("plugins/*/skills/*/tests/workflow-dispatch.toml"))
    return tuple(sorted(paths))


if __name__ == "__main__":
    raise SystemExit(main())
