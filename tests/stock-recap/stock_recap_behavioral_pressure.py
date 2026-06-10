#!/usr/bin/env python3
"""Behavioral pressure tests for stock-recap."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "stock-recap" / "SKILL.md"
sys.path.append(str(REPO_ROOT / "tests"))

from behavioral_harness import BehavioralScenario as Scenario  # noqa: E402
from behavioral_harness import run_loaded_skill_behavioral_suite  # noqa: E402
from semantic_judge import SemanticCriterion  # noqa: E402


SCENARIOS = (
    Scenario(
        scenario_id="quarterly-recap-existing-thesis",
        user_request=(
            "Catch me up on MSFT since the last thesis. The saved thesis exists, "
            "new 10-Q/10-K filings may have landed, and I want sell triggers evaluated "
            "against the saved bull/base/bear projections."
        ),
        criteria=(
            SemanticCriterion(
                "checks_prior_research_preconditions",
                "The response requires verdict, projections, financials, market expectations, SEC user-agent, toolkit, and research repo before recapping.",
            ),
            SemanticCriterion(
                "detects_filings_and_routes_mode",
                "The response performs gap detection for new 10-Q/10-K filings and uses the mode picker for quarterly catch-up, news mode, valuation-only recap, or exit as appropriate.",
            ),
            SemanticCriterion(
                "mechanically_diffs_actuals_and_triggers",
                "The response refreshes financials/valuation and evaluates saved sell triggers in fired/flashing/clear/cannot-evaluate states against saved projections.",
            ),
            SemanticCriterion(
                "uses_checkpoints_before_updates",
                "The response uses the required checkpoints and asks before surgical or reclassifying thesis updates and before pushing.",
            ),
        ),
        forbidden_terms=("technical analysis", "day trade", "skip prior thesis"),
    ),
    Scenario(
        scenario_id="missing-prior-thesis-aborts",
        user_request="Recap a brand-new ticker ABCD that has no existing stock-research artifacts.",
        criteria=(
            SemanticCriterion(
                "aborts_without_saved_thesis",
                "The response refuses to run stock-recap without prior stock-research artifacts such as verdict, projections, financials, and market expectations.",
            ),
            SemanticCriterion(
                "routes_to_initial_research",
                "The response instructs the user to run the initial stock research workflow instead of inventing a recap baseline.",
            ),
        ),
    ),
)


def main() -> int:
    return run_loaded_skill_behavioral_suite(
        suite_name="stock-recap",
        skill_name="stock-recap",
        skill_path=SKILL_PATH,
        scenarios=SCENARIOS,
        agent_env_var="STOCK_RECAP_AGENT_COMMAND",
        scenario_filter_env_var="STOCK_RECAP_SCENARIO",
        prompt_instructions=(
            "Do not fetch market data or write research files. Return only the recap "
            "workflow, gates, mode routing, checkpoint behavior, and blocker handling."
        ),
        judge_context=(
            "Loaded skill under test: stock-recap. Judge prerequisite gates, mode routing, "
            "filing/valuation flow, sell-trigger evaluation, and update checkpoints."
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
