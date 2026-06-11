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
SCENARIOS_PATH = Path(__file__).with_name("scenarios.toml")

sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import load_behavioral_scenarios, run_loaded_skill_behavioral_suite  # noqa: E402


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="ticket-start delegated execution",
        skill_name="ticket-start",
        skill_path=SKILL_PATH,
        scenarios=load_behavioral_scenarios(SCENARIOS_PATH),
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
