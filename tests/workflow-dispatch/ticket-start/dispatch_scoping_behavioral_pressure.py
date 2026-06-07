#!/usr/bin/env python3
"""Behavioral dispatch test for ticket-start dispatching Scoping first."""

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

    response = run_agent(agent_command, make_prompt())
    try:
        check_response(response)
    except Exception as error:
        print(f"Response:\n{response}", file=sys.stderr)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: ticket-start dispatches Scoping first behaviorally")
    return 0


def make_prompt() -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: ticket-start

<skill>
{skill}
</skill>

User request:
Use ticket-start to implement Linear issue APP-123. Assume the Linear ticket can
be read successfully and has acceptance criteria.

Do not perform the task. Do not call tools. Return only the first workflow
actions the main agent must take.

Return only action lines in this exact shape:
ACTION: <number> | <kind> | <target> | <details>

Use kind DISPATCH_SUBAGENT for any mandatory subagent dispatch. For subagent
dispatch details, include the prompt intent and compact inputs that must be
forwarded. Include enough detail for a test to verify whether the prompt is a
self-contained work request with the required evidence terms.
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
        "scoping",
        "scope map",
        "token-efficient",
        "navigable",
        "locators",
        "entry points",
        "target modules",
        "types",
        "tests",
        "affected surfaces",
        "downstream",
    )
    missing = [term for term in required_terms if term not in normalized]
    if missing:
        raise AssertionError(f"missing required dispatch terms: {missing}")

    forbidden_terms = ("agents/scoping.md", "codebase-scope-map", "$codebase-scope-map")
    present = [term for term in forbidden_terms if term in normalized]
    if present:
        raise AssertionError(f"included forbidden terms: {present}")

    scoping_index = first_index(response, "DISPATCH_SUBAGENT", "Scoping")
    if scoping_index < 0:
        raise AssertionError("Scoping DISPATCH_SUBAGENT action is required")

    for term in ("plan", "implement"):
        later_index = normalized.find(term)
        if 0 <= later_index < scoping_index:
            raise AssertionError(f"mentioned {term!r} before Scoping dispatch")

    prefix = response[:scoping_index].lower()
    local_scoping_markers = (
        "local scope map",
        "local scoping",
        "map the code",
        "map code",
        "codebase map",
        "scope map",
        "affected surfaces",
    )
    if any(marker in prefix for marker in local_scoping_markers):
        raise AssertionError("performed local scoping before Scoping dispatch")


def first_index(haystack: str, *needles: str) -> int:
    normalized_needles = tuple(needle.lower() for needle in needles)
    for line in haystack.splitlines():
        normalized_line = line.lower()
        if all(needle in normalized_line for needle in normalized_needles):
            return haystack.find(line)
    return -1


if __name__ == "__main__":
    raise SystemExit(main())
