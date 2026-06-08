#!/usr/bin/env python3
"""Behavioral pressure test for multi-ticket-work workflow dispatch."""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = REPO_ROOT / "skills" / "multi-ticket-work" / "SKILL.md"
sys.path.append(str(Path(__file__).resolve().parents[1]))

from auto_discovery import action_lines, assert_forbidden_terms, run_agent  # noqa: E402
from auto_discovery import SemanticCriterion, judge_response, resolve_judge_command  # noqa: E402


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
        check_response(response, resolve_judge_command(agent_command))
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: multi-ticket-work dispatches ticket units")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  WORKFLOW_DISPATCH_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/workflow-dispatch/multi-ticket-work/dispatch_ticket_units_behavioral_pressure.py
"""
    )


def make_prompt() -> str:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: multi-ticket-work

<skill>
{skill}
</skill>

User request:
Work the whole Billing Revamp Epic. It includes four tickets:
- Pricing API must land after Invoice migration.
- Checkout UI must land after Pricing API.
- Analytics events can happen independently.
- Checkout UI should receive the upstream PR context.

Do not perform the implementation. Do not call tools. Based only on the loaded
skill, return the workflow actions the main agent must take to coordinate the
multi-ticket work through PRs and completion reports.

Return only action lines in this exact shape:
ACTION: <number> | <kind> | <target> | <details>

Use kind MAP_SCOPE for ticket discovery and dependency mapping, kind
DISPATCH_SUBAGENT for ticket or unit assignment, and kind REPORT for final
review-order reporting. Do not name downstream skill identifiers.
"""


def check_response(response: str, judge_command: str) -> None:
    lines = action_lines(response)
    if not lines:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("missing ACTION lines")

    first_action = lines[0].casefold()
    if "map_scope" not in first_action:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("first action must map scope and dependencies")

    forbidden = (
        "readiness ledger",
        "implement-unit-of-work",
        "qa-verification",
        "frontend-ui-review",
        "codebase-scope-map",
    )
    assert_forbidden_terms(response, forbidden, "multi-ticket dispatch workflow")

    dispatch_lines = [line for line in lines if "dispatch_subagent" in line.casefold()]
    if not dispatch_lines:
        print(f"Response:\n{response}", file=sys.stderr)
        raise AssertionError("missing DISPATCH_SUBAGENT actions")

    try:
        judge_response(
            judge_command=judge_command,
            scenario_id="multi-ticket-work-ticket-unit-dispatch",
            scenario_prompt=(
                "Coordinate a Billing Revamp Epic with Pricing API, Checkout UI, "
                "Invoice migration, and Analytics events."
            ),
            response=response,
            criteria=(
                SemanticCriterion(
                    "maps_full_scope_first",
                    "The first phase gathers the full Epic ticket set and maps dependencies before dispatching work.",
                ),
                SemanticCriterion(
                    "respects_dependency_order",
                    "The response sequences Invoice migration before Pricing API and Pricing API before Checkout UI.",
                ),
                SemanticCriterion(
                    "parallelizes_independent_ticket",
                    "The response treats Analytics events as safe to dispatch in parallel when repository constraints allow.",
                ),
                SemanticCriterion(
                    "one_subagent_per_ticket_or_unit",
                    "The response dispatches one subagent per ticket or explicitly split unit of work.",
                ),
                SemanticCriterion(
                    "requires_pr_and_report",
                    "Each dispatched ticket or unit requires a PR and completion report before it is complete.",
                ),
                SemanticCriterion(
                    "final_review_order",
                    "The final report lists opened PRs in dependency-aware review order.",
                ),
                SemanticCriterion(
                    "pr_descriptions_include_review_focus",
                    "The workflow requires PR descriptions to surface what the human should inspect carefully.",
                ),
            ),
            context="Loaded parent skill under test: multi-ticket-work. Judge workflow dispatch behavior, not exact wording.",
        )
    except AssertionError:
        print(f"Response:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
