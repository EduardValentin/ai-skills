#!/usr/bin/env python3
"""Behavioral pressure tests for stock-research."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "stock-research" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="initial-us-listed-thesis-workflow",
        user_request=(
            "Research AAPL from scratch and tell me whether it belongs in a long-term "
            "portfolio. I want a durable thesis, not short-term trading advice."
        ),
        criteria=(
            SemanticCriterion(
                "checks_setup_and_identity",
                "The response resolves ticker identity, checks SEC user-agent, script environment, research repo, and existing ticker folder before starting.",
            ),
            SemanticCriterion(
                "uses_gvd_lens_and_session_context",
                "The response asks for the GVD lens through structured choice when available and captures free-form session context.",
            ),
            SemanticCriterion(
                "follows_phase_checkpoints",
                "The response follows the phase structure with business/moat, financials, parallel competitors/earnings/valuation/expectations, projections, verdict, and checkpoints.",
            ),
            SemanticCriterion(
                "produces_durable_artifacts",
                "The response writes or plans durable Markdown/JSON research artifacts and uses clear Markdown checkpoint outputs.",
            ),
            SemanticCriterion(
                "avoids_trading_scope",
                "The response stays in long-horizon fundamentals research and avoids technical analysis, options, and day-trading advice.",
            ),
        ),
    ),
    Scenario(
        scenario_id="non-us-or-trading-request-blocks",
        user_request="Do a quick technical analysis on a non-US stock and suggest options trades for next week.",
        criteria=(
            SemanticCriterion(
                "rejects_out_of_scope_request",
                "The response blocks or redirects because non-US listings, technical analysis, options, and short-term trading are outside stock-research scope.",
            ),
            SemanticCriterion(
                "does_not_force_fundamental_workflow",
                "The response does not pretend the stock-research workflow can satisfy an out-of-scope trading request.",
            ),
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="stock-research",
        skill_name="stock-research",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="STOCK_RESEARCH_AGENT_COMMAND",
        scenario_filter_env_var="STOCK_RESEARCH_SCENARIO",
        prompt_instructions=(
            "Do not fetch data or write research files. Return only the research workflow, "
            "gates, phases, checkpoint behavior, artifact expectations, and out-of-scope handling."
        ),
        judge_context=(
            "Loaded skill under test: stock-research. Judge fundamentals workflow, "
            "setup gates, structured user decisions, artifacts, and scope boundaries."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
