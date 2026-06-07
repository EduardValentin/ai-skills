#!/usr/bin/env python3
"""Helpers for workflow-dispatch behavioral auto-discovery checks."""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.append(str(REPO_ROOT / "tests" / "skill-trigger"))

from trigger_scenarios import discover_skill_files, parse_frontmatter  # noqa: E402


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


def skill_index() -> str:
    rows: list[str] = []
    for skill_name, skill_file in sorted(discover_skill_files(REPO_ROOT).items()):
        frontmatter = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        rows.append(f"- {frontmatter.get('name', skill_name)}: {frontmatter.get('description', '')}")
    return "\n".join(rows)


def assert_auto_discovers(agent_command: str, delegated_request: str, expected_skill: str) -> str:
    response = run_agent(agent_command, make_selection_prompt(delegated_request, expected_skill))
    if expected_skill not in response:
        raise AssertionError(
            f"delegated request did not auto-discover {expected_skill}\n"
            f"Request:\n{delegated_request}\n\nDiscovery response:\n{response}"
        )
    return response


def make_selection_prompt(delegated_request: str, expected_skill: str) -> str:
    return f"""You are testing skill auto-discovery for a delegated work request.

Available skills:
{skill_index()}

Delegated request:
{delegated_request}

Return only this format:
SELECTED_SKILLS: comma-separated skill names
RATIONALE: one short sentence

Select every skill that should be loaded before acting on the delegated request.
"""


def assert_concept_groups(text: str, groups: tuple[tuple[str, ...], ...], context: str) -> None:
    normalized = text.casefold()
    missing = [group for group in groups if not any(term.casefold() in normalized for term in group)]
    if missing:
        raise AssertionError(f"{context} missing concept groups: {missing}")


def assert_forbidden_terms(text: str, terms: tuple[str, ...], context: str) -> None:
    normalized = text.casefold()
    present = [term for term in terms if term.casefold() in normalized]
    if present:
        raise AssertionError(f"{context} included forbidden terms: {present}")


def action_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.lstrip().casefold().startswith("action:")]
