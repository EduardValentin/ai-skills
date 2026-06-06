#!/usr/bin/env python3
"""Behavioral pressure test for ticket-work-unit-orchestration workflow dispatch."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-work-unit-orchestration" / "SKILL.md"


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

    print("PASS: ticket-work-unit-orchestration dispatches readiness ledger before work")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/workflow-dispatch/ticket-work-unit-orchestration/dispatch_readiness_ledger_behavioral_pressure.py
"""
    )


def make_prompt() -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: ticket-work-unit-orchestration

<skill>
{skill}
</skill>

User request:
Coordinate an approved implementation plan with three work units:
- Billing API is backend-only.
- Onboarding UI is UI-facing.
- Invite Flow is mixed.

Do not perform the implementation. Do not call tools. Based only on the loaded
skill, return the first workflow actions the main agent must take before Ship.

Return only action lines in this exact shape:
ACTION: <number> | <kind> | <target> | <details>

Use kind SET_UP_LEDGER for the per-work-unit readiness ledger and kind
DISPATCH_SUBAGENT for `ticket-implementation-unit`, self-review,
`ticket-qa-verification`, or UI/UX work.
"""


def run_agent(agent_command: str, prompt: str) -> str:
    completed = subprocess.run(
        agent_command,
        input=prompt,
        text=True,
        shell=True,
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
    action_lines = [line for line in response.splitlines() if line.startswith("ACTION:")]
    if not action_lines:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("missing ACTION lines")

    first_action = action_lines[0].lower()
    if "set_up_ledger" not in first_action or "ledger" not in first_action:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("first action must set up the readiness ledger")

    required_terms = (
        "billing api",
        "onboarding ui",
        "invite flow",
        "implementation",
        "ticket-implementation-unit",
        "self-review",
        "qa",
        "ticket-qa-verification",
        "ui/ux",
        "backend-only",
        "skip rationale",
    )
    missing = [term for term in required_terms if term not in normalized]
    if missing:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError(f"missing required workflow terms: {missing}")

    if "dispatch_subagent" not in normalized:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("missing delegated subagent dispatch")


if __name__ == "__main__":
    raise SystemExit(main())
