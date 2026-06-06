#!/usr/bin/env python3
"""Behavioral pressure test for ticket-start dispatching ticket-qa-verification."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("WORKFLOW_DISPATCH_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: WORKFLOW_DISPATCH_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    try:
        response = run_agent(agent_command, make_prompt())
        check_response(response)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start dispatches ticket-qa-verification before UI/UX")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/workflow-dispatch/ticket-start/dispatch_ticket_qa_verification_behavioral_pressure.py
"""
    )


def make_prompt() -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: ticket-start

<skill>
{skill}
</skill>

User request:
The implementation plan is approved and the branch has a mixed backend and UI diff.
The app URL is http://localhost:3000 and local tests passed. Return only the
Verify-phase workflow actions the main agent must take before Ship.

Do not execute the ticket. Do not call tools.

Return only action lines in this exact shape:
ACTION: <number> | <kind> | <target> | <details>

Use kind DISPATCH_SUBAGENT for mandatory verification skill dispatches.
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
    required_terms = (
        "dispatch_subagent",
        "ticket-qa-verification",
        "mixed",
        "full diff",
        "local test",
        "qa",
        "findings",
        "ui/ux",
    )
    missing = [term for term in required_terms if term not in normalized]
    if missing:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError(f"missing required dispatch terms: {missing}")

    qa_index = dispatch_index(response, "ticket-qa-verification")
    uiux_index = dispatch_index(response, "UI/UX")
    if qa_index < 0 or uiux_index < 0 or uiux_index < qa_index:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("ticket-qa-verification must appear before UI/UX")


def dispatch_index(response: str, target: str) -> int:
    for line in response.splitlines():
        normalized_line = line.lower()
        if "dispatch_subagent" in normalized_line and target.lower() in normalized_line:
            return response.find(line)
    return -1


if __name__ == "__main__":
    raise SystemExit(main())
