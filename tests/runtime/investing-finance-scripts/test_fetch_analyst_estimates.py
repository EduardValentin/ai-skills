"""Tests for fetch_analyst_estimates.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

def test_fetch_writes_market_expectations_json(
    tmp_path: Path, fetch_analyst_estimates
) -> None:
    out_dir = tmp_path / "raw"
    yfa = fetch_analyst_estimates.yfa
    with (
        patch.object(
            yfa,
            "get_analyst_price_target",
            return_value={
                "low": 150.0,
                "mean": 200.0,
                "high": 280.0,
                "num_analysts": 35,
            },
        ),
        patch.object(
            yfa,
            "get_recommendations",
            return_value={
                "strong_buy": 10,
                "buy": 15,
                "hold": 8,
                "sell": 2,
                "strong_sell": 0,
            },
        ),
        patch.object(
            yfa, "get_earnings_estimate", return_value={"0q": {"avg": 6.0}}
        ),
        patch.object(
            yfa,
            "get_revenue_estimate",
            return_value={"0q": {"avg": 1.0e11}},
        ),
        patch.object(yfa, "get_eps_trend", return_value={"0q": {"now": 6.1}}),
        patch.object(
            yfa,
            "get_growth_estimates",
            return_value={"ticker": {"0y": 0.08}},
        ),
    ):
        rc = fetch_analyst_estimates.main(["AAPL", "--out", str(out_dir)])
    assert rc == 0
    data = json.loads((out_dir / "market-expectations.json").read_text())
    assert data["ticker"] == "AAPL"
    assert data["schema_version"] == 1
    assert data["price_target"]["mean"] == 200.0
    assert data["ratings"]["buy"] == 15
    assert "eps_trend" in data
    assert "revenue_estimate" in data
    assert "growth_estimates" in data
