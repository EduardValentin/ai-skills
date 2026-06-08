#!/usr/bin/env python3
"""Helpers for workflow-dispatch installed-harness discovery checks."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.append(str(REPO_ROOT / "tests"))

from semantic_judge import (  # noqa: E402
    SemanticCriterion,
    assert_forbidden_terms,
    judge_response,
    resolve_judge_command,
)


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


def assert_auto_discovers(agent_command: str, delegated_request: str, expected_skill: str) -> str:
    response = run_agent(agent_command, make_selection_prompt(delegated_request))
    if expected_skill not in response:
        raise AssertionError(
            f"delegated request did not auto-discover {expected_skill}\n"
            f"Request:\n{delegated_request}\n\nDiscovery response:\n{response}"
        )
    return response


def make_selection_prompt(delegated_request: str) -> str:
    return f"""You are testing installed black-box skill discovery for a delegated work request.

Delegated request:
{delegated_request}

Return only this format:
SELECTED_SKILLS: comma-separated skill names
RATIONALE: one short sentence

Select every skill that should be loaded before acting on the delegated request.
"""


def action_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.lstrip().casefold().startswith("action:")]
