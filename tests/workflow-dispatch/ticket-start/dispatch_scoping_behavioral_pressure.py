#!/usr/bin/env python3
"""Behavioral dispatch test for ticket-start dispatching Scoping first."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(REPO_ROOT / "tests"))

from harness import WorkflowDispatchScenario, run_workflow_dispatch_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


def assert_scoping_before_local_mapping(response: str) -> None:
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


SCENARIOS = (
    WorkflowDispatchScenario(
        scenario_id="ticket-start-dispatch-scoping",
        user_request=(
            "Use ticket-start to implement Linear issue APP-123. Assume the Linear ticket can\n"
            "be read successfully and has acceptance criteria."
        ),
        prompt_instructions=(
            "Do not perform the task. Do not call tools. Return only the first workflow\n"
            "actions the main agent must take.\n\n"
            "Return only action lines in this shape:\n"
            "ACTION: <number> | <kind> | <capability> | <self-contained delegated request>\n\n"
            "Use kind DISPATCH_REQUEST for any mandatory delegated capability request. For\n"
            "dispatch details, include the prompt intent and compact inputs that must be\n"
            "forwarded. Do not name downstream skill identifiers."
        ),
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
                "asks_for_scope_evidence",
                "The delegated request asks the scoping agent to return compact scope evidence such as affected files or surfaces, relevant locators, risks, constraints, tests, or downstream implementation slices.",
            ),
        ),
        forbidden_terms=("agents/scoping.md", "`codebase-scope-map`", "$codebase-scope-map"),
        expected_auto_discovery=("codebase-scope-map",),
        require_action_ledger=True,
        response_checks=(assert_scoping_before_local_mapping,),
    ),
)


def main() -> int:
    return run_workflow_dispatch_suite(
        suite_name="ticket-start Scoping dispatch scenarios",
        parent_skill_name="ticket-start",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        scenario_filter_env_var="TICKET_START_SCOPING_DISPATCH_SCENARIO",
    )


if __name__ == "__main__":
    raise SystemExit(main())
