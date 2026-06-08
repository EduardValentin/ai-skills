#!/usr/bin/env python3
"""Behavioral dispatch test for ticket-start dispatching Scoping first."""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))

from auto_discovery import assert_auto_discovers, assert_forbidden_terms, run_agent  # noqa: E402
from auto_discovery import SemanticCriterion, judge_response, resolve_judge_command  # noqa: E402


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
        check_response(response, agent_command, resolve_judge_command(agent_command))
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

Return only action lines in this shape:
ACTION: <number> | <kind> | <capability> | <self-contained delegated request>

Use kind DISPATCH_REQUEST for any mandatory delegated capability request. For
dispatch details, include the prompt intent and compact inputs that must be
forwarded. Do not name downstream skill identifiers.
"""


def check_response(response: str, agent_command: str, judge_command: str) -> None:
    forbidden_terms = ("agents/scoping.md", "`codebase-scope-map`", "$codebase-scope-map")
    assert_forbidden_terms(response, forbidden_terms, "Scoping dispatch")
    assert_auto_discovers(agent_command, response, "codebase-scope-map")

    judge_response(
        judge_command=judge_command,
        scenario_id="ticket-start-dispatch-scoping",
        scenario_prompt="Use ticket-start to implement Linear issue APP-123 after ticket intake succeeds.",
        response=response,
        criteria=(
            SemanticCriterion(
                "scoping_dispatch_before_local_mapping",
                "The response delegates scoping/codebase mapping before performing local code mapping; setup, source-control, workflow-selection, and intake actions may appear first.",
            ),
            SemanticCriterion(
                "scoping_request_is_self_contained",
                "The delegated request includes enough ticket, acceptance criteria, repository, workflow, and compact input context for a separate agent to map scope.",
            ),
            SemanticCriterion(
                "asks_for_navigable_scope_map",
                "The delegated request asks for a compact navigable scope map with file-line locators, entry points, modules/components, contracts/types, tests, affected surfaces, conflicts, and downstream slices.",
            ),
        ),
        context="Loaded parent skill under test: ticket-start. Judge scoping dispatch behavior, not exact wording.",
    )

    scoping_index = first_index(response, "dispatch_request", "scoping")
    if scoping_index < 0:
        scoping_index = first_index(response, "dispatch_request", "scope")
    if scoping_index < 0:
        raise AssertionError("Scoping dispatch request action is required")

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
