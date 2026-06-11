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
        scenario_id="ticket-start-execution-corectness",
        user_request=(
            "A user asks to start one Linear issue APP-812. The issue is a child under an Epic, "
            "adds a billing eligibility business rule, modifies a checkout UI component with a "
            "matching reference surface, and may require backend, UI, migration, and analytics work. "
            "The user has not yet confirmed the requirements/design understanding, approved a spec, "
            "or approved an implementation plan. Explain the correct main-agent workflow from intake "
            "through final handoff."
        ),
        criteria=(
            SemanticCriterion(
                "ticket_start_is_single_ticket_router",
                "The response treats this as one standalone ticket handled by the main agent as user-facing orchestrator, not as multi-ticket work or inline implementation.",
            ),
            SemanticCriterion(
                "intake_happens_first",
                "The response starts by re-reading the ticket through MCP or API, capturing title, description, acceptance criteria, links, status, dependencies, ambiguity, and parent/Epic context before brainstorming or planning.",
            ),
            SemanticCriterion(
                "artifact_and_repo_freshness",
                "The response gathers only relevant PRD/design/reference context, reads repo instructions, inspects git/branch/PR/recent commit state, fetches origin/main, and creates or verifies a fresh ticket worktree before implementation decisions.",
            ),
            SemanticCriterion(
                "scoping_before_planning",
                "The response delegates codebase scoping before implementation planning, or records a concrete skip reason if the scope is clearly trivial.",
            ),
            SemanticCriterion(
                "brainstorming_before_plan",
                "The response runs a user-facing brainstorming session grounded in ticket, parent, artifact, repo, and scoping facts until shared understanding of work, boundaries, and success criteria is reached.",
            ),
            SemanticCriterion(
                "spec_approval_before_plan",
                "The response says the brainstorming phase produces the approved spec/design and plan writing is routed only after that spec/design approval.",
            ),
            SemanticCriterion(
                "plan_approval_blocks_execution",
                "The response requires explicit user approval of the implementation plan and blocks coding, scaffolding, product mutations, or execution delegation before both spec approval and plan approval.",
            ),
            SemanticCriterion(
                "enters_execution_phase_after_approval",
                "After spec and plan approval, the response enters an execution phase using an approved execution packet while the main agent remains the current-session orchestrator.",
            ),
            SemanticCriterion(
                "does_not_handoff_main_ticket_orchestration",
                "The response does not hand off main-ticket orchestration to another agent or describe a separate ticket orchestrator.",
            ),
            SemanticCriterion(
                "coordinates_execution_and_verification_loop",
                "The response coordinates implementation, independent review, QA, UI/UX where applicable, scoped fixes, and reruns through delegated work as needed instead of doing them inline.",
            ),
            SemanticCriterion(
                "defines_uiux_verification_by_project_type",
                "The response explains that personal/Linear UI/UX verification compares changed production UI against the runnable reference app, while job/Jira UI/UX verification checks visual consistency with the rest of the application and similar existing elements.",
            ),
            SemanticCriterion(
                "forwards_compact_context",
                "The response describes compact context included in delegated requests, such as ticket/AC, parent context, approved decisions, approved plan, artifact slices, scope/codebase locators, branch state, constraints, expected checks, and output expectations.",
            ),
            SemanticCriterion(
                "execution_order",
                "The response preserves the ticket work order: implement first, verify through independent review plus QA plus UI/UX when applicable, aggregate findings, delegate scoped fixes, rerun affected verification, then PR verification.",
            ),
            SemanticCriterion(
                "verifier_cannot_verify_fallback",
                "The response says delegated QA and UI/UX verifiers must report CANNOT_VERIFY with the reason and missing capability when required tooling or access is unavailable, and the main agent records or handles the blocker.",
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
            "execute-ticket-work",
            "TodoWrite",
            "two-stage review",
            "spec compliance reviewer",
            "code quality reviewer",
            "ticket orchestrator",
            "ticket-orchestrator",
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
            "Do not execute the ticket. Return a concise ordered workflow only. It must explain:\n"
            "- how the main agent stays the intake and routing orchestrator for one ticket,\n"
            "- the ticket intake through MCP or API, including title, description, acceptance criteria, links, status, dependencies, ambiguity, and parent context before brainstorming or planning,\n"
            "- the artifact, repo-state, freshness, worktree, and scoping steps before planning,\n"
            "- how the brainstorming phase reaches shared understanding and produces the approved spec/design,\n"
            "- how plan writing is routed after spec/design approval and then gets plan approval,\n"
            "- how explicit user plan approval blocks coding, scaffolding, product mutations, and execution until both spec and plan are approved,\n"
            "- how the main agent enters execution with an approved execution packet while remaining the current-session orchestrator,\n"
            "- the order of implementation, independent review, QA, UI/UX when applicable, findings aggregation, scoped fixes, reruns, PR preparation, and PR verification or handoff,\n"
            "- how UI/UX verification differs for personal/Linear reference-app parity versus job/Jira visual consistency with existing app elements,\n"
            "- which compact context ticket-start forwards,\n"
            "- how CANNOT_VERIFY is handled when verifier tooling or access is missing,\n"
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
