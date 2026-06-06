#!/usr/bin/env python3
"""Behavioral dispatch tests for ticket-start -> ticket-ship-gate."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    agent_command = (
        os.environ.get("WORKFLOW_DISPATCH_AGENT_COMMAND", "").strip()
        or os.environ.get("SKILL_TRIGGER_AGENT_COMMAND", "").strip()
    )
    if not agent_command:
        print("FAIL: WORKFLOW_DISPATCH_AGENT_COMMAND or SKILL_TRIGGER_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    skill = SKILL_PATH.read_text(encoding="utf-8")
    response = run_agent(agent_command, make_prompt(skill))
    try:
        check_response(response)
    except Exception as error:
        print(f"Response:\n{response}", file=sys.stderr)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start dispatches ticket-ship-gate behaviorally")
    return 0


def make_prompt(skill: str) -> str:
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: ticket-start

<skill>
{skill}
</skill>

User request:
Personal workflow: QA is clean, UI/UX is clean, inventory validation passed,
all implementation reports and self-reviews are present, and the PR should enter
Ship. The user also wants to understand the required checks, bot identity, and
merge approval gates before any Ship mutation. What should the main agent do next?

Do not perform the task. Do not call tools. Return only action lines in this shape:
ACTION: <number> | <kind> | <target> | <details>
"""


def run_agent(agent_command: str, prompt: str) -> str:
    completed = subprocess.run(
        shlex.split(agent_command),
        input=prompt,
        text=True,
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "agent command failed with exit code "
            f"{completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed.stdout


def check_response(response: str) -> None:
    normalized = response.lower()
    required = (
        "ticket-ship-gate",
        "readiness ledger",
        "required checks",
        "bot",
        "approval",
    )
    missing = [term for term in required if term not in normalized]
    if missing:
        raise AssertionError(f"missing required terms: {missing}")

    forbidden = ("implement inline", "perform ship inline", "merge now")
    present = [term for term in forbidden if term in normalized]
    if present:
        raise AssertionError(f"included forbidden terms: {present}")


if __name__ == "__main__":
    raise SystemExit(main())
