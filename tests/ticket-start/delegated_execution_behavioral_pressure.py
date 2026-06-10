#!/usr/bin/env python3
"""Behavioral pressure tests for ticket-start delegated execution orchestration.

Requires TICKET_START_BEHAVIOR_AGENT_COMMAND to name a command that reads a
prompt from stdin and writes the agent response to stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "ticket-start" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import (  # noqa: E402
    SemanticCriterion,
)


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
                "The response preserves the ticket work order: implement first, verify through independent review plus QA plus UI/UX when applicable, aggregate findings, delegate scoped fixes, rerun affected verification, then PR verification.",
            ),
            SemanticCriterion(
                "readiness_requires_resolved_reports",
                "The response says PR verification or handoff waits until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved or explicitly blocked/out of scope.",
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
            "verify-pr",
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
    return run_loaded_skill_behavioral_suite(
        suite_name="ticket-start delegated execution",
        skill_name="ticket-start",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="TICKET_START_BEHAVIOR_AGENT_COMMAND",
        scenario_filter_env_var="TICKET_START_BEHAVIOR_SCENARIO",
        prompt_instructions=(
            "Do not execute the ticket. Return a concise routing plan only. It must explain:\n"
            "- how ticket-start stays the intake and routing orchestrator,\n"
            "- how implementation begins with implementer subagents in a strategy that minimizes dependencies and maximizes throughput and quality,\n"
            "- the order of implementation, independent review, QA, UI/UX when applicable, findings aggregation, scoped fixes, reruns, and PR verification,\n"
            "- how UI/UX verification differs for personal/Linear reference-app parity versus job/Jira visual consistency with existing app elements,\n"
            "- which compact context ticket-start forwards,\n"
            "- how returned reports are reconciled before PR verification or handoff.\n"
            "Do not name downstream skill identifiers."
        ),
        judge_context="Loaded skill under test: ticket-start. Judge the routing plan, not exact wording.",
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
