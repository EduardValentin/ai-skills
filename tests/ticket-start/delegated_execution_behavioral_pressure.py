#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-start delegated execution orchestration.

Requires TICKET_START_BEHAVIOR_AGENT_COMMAND to name a command that reads a
prompt from stdin and writes the agent response to stdout.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from semantic_judge import (  # noqa: E402
    SemanticCriterion,
    assert_forbidden_terms,
    judge_response,
    resolve_judge_command,
)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    user_request: str
    criteria: tuple[SemanticCriterion, ...]
    forbidden_terms: tuple[str, ...]


SCENARIOS = (
    Scenario(
        scenario_id="substantial-single-ticket-delegated-execution",
        user_request=(
            "Use ticket-start for one Linear issue APP-456 whose approved plan includes a "
            "database migration, backend API, onboarding UI, and analytics events. Explain "
            "how the main agent should route execution after requirements/design and plan approval."
        ),
        criteria=(
            SemanticCriterion(
                "ticket_start_is_single_ticket_router",
                "The response keeps ticket-start as intake/routing orchestrator for one ticket rather than execution owner.",
            ),
            SemanticCriterion(
                "requires_approved_inputs_before_execution",
                "The response treats approved requirements/design and approved implementation plan as prerequisites before execution routing.",
            ),
            SemanticCriterion(
                "delegates_execution_and_verification_loop",
                "The response routes implementation to implementer subagents, then routes independent review, QA, UI/UX where applicable, scoped fixes, and reruns instead of doing them inline.",
            ),
            SemanticCriterion(
                "defines_uiux_verification_by_project_type",
                "The response explains that personal/Linear UI/UX verification compares changed production UI against the runnable reference app, while job/Jira UI/UX verification checks visual consistency with the rest of the application and similar existing elements.",
            ),
            SemanticCriterion(
                "forwards_compact_context",
                "The response describes compact context included in delegated requests, such as ticket/AC, approved artifacts, scope/codebase context, workflow or branch state, and UI/reference context when relevant.",
            ),
            SemanticCriterion(
                "execution_order",
                "The response preserves the ticket work order: implement first, verify through independent review plus QA plus UI/UX when applicable, aggregate findings, delegate scoped fixes, rerun affected verification, then readiness.",
            ),
            SemanticCriterion(
                "readiness_requires_resolved_reports",
                "The response says PR readiness or handoff waits until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved or explicitly blocked/out of scope.",
            ),
        ),
        forbidden_terms=(
            "Depth budget:",
            "IMPLEMENTATION_SLICE_RESULT",
            "BROWSER_VERIFICATION_RESULT",
            "Root -> child -> grandchild",
            "orchestration map",
            "leaf-only",
            "grandchild",
            "four Linear tickets",
            "I would implement inline",
            "qa-verification",
            "implement-unit-of-work",
            "multi-ticket-work",
            "verify-pr-readiness",
            "ui-verification",
            "TodoWrite",
            "two-stage review",
            "spec compliance reviewer",
            "code quality reviewer",
            "does not define",
            "does not prescribe",
        ),
    ),
)


def main() -> int:
    if "--help" in sys.argv:
        print_usage()
        return 0

    agent_command = os.environ.get("TICKET_START_BEHAVIOR_AGENT_COMMAND", "").strip()
    if not agent_command:
        print_usage()
        print("FAIL: TICKET_START_BEHAVIOR_AGENT_COMMAND is required", file=sys.stderr)
        return 1

    scenario_filter = os.environ.get("TICKET_START_BEHAVIOR_SCENARIO", "").strip()
    scenarios = [scenario for scenario in SCENARIOS if not scenario_filter or scenario.scenario_id == scenario_filter]
    if not scenarios:
        print(f"FAIL: no scenario matched {scenario_filter!r}", file=sys.stderr)
        return 1

    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    judge_command = resolve_judge_command(agent_command)
    for scenario in scenarios:
        response = run_agent(agent_command, make_prompt(skill_text, scenario))
        check_response(scenario, response, judge_command)
        print(f"PASS: {scenario.scenario_id}")

    print(f"PASS: {len(scenarios)} ticket-start delegated execution behavioral scenarios")
    return 0


def print_usage() -> None:
    print(
        """Usage:
  TICKET_START_BEHAVIOR_AGENT_COMMAND='<command reading stdin>' \\
    python3 tests/ticket-start/delegated_execution_behavioral_pressure.py

Optional:
  TICKET_START_BEHAVIOR_SCENARIO='<scenario-id>' to run one scenario.
"""
    )


def make_prompt(skill_text: str, scenario: Scenario) -> str:
    return f"""You are pressure-testing whether an agent follows the ticket-start skill.

Skill text:
{skill_text}

User request:
{scenario.user_request}

Do not execute the ticket. Return a concise routing plan only. It must explain:
- how ticket-start stays the intake and routing orchestrator,
- how implementation begins with implementer subagents in a strategy that minimizes dependencies and maximizes throughput and quality,
- the order of implementation, independent review, QA, UI/UX when applicable, findings aggregation, scoped fixes, reruns, and readiness,
- how UI/UX verification differs for personal/Linear reference-app parity versus job/Jira visual consistency with existing app elements,
- which compact context ticket-start forwards,
- how returned reports are reconciled before PR readiness or handoff.
Do not name downstream skill identifiers.
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


def check_response(scenario: Scenario, response: str, judge_command: str) -> None:
    try:
        assert_forbidden_terms(response, scenario.forbidden_terms, scenario.scenario_id)
        judge_response(
            judge_command=judge_command,
            scenario_id=scenario.scenario_id,
            scenario_prompt=scenario.user_request,
            response=response,
            criteria=scenario.criteria,
            context="Loaded skill under test: ticket-start. Judge the routing plan, not exact wording.",
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
