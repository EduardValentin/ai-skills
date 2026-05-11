"""Tests for compute_financials.py."""
from __future__ import annotations

import json
from pathlib import Path

import responses

import compute_financials
from _lib import ticker_resolver as tr


@responses.activate
def test_compute_financials_writes_full_schema(fixtures_dir: Path, tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        body=(fixtures_dir / "company_facts_AAPL_sample.json").read_text(),
        status=200,
    )

    out_path = tmp_path / "financials.json"
    rc = compute_financials.main(["AAPL", "--years", "3", "--out", str(out_path)])
    assert rc == 0

    data = json.loads(out_path.read_text())
    assert data["ticker"] == "AAPL"
    assert data["schema_version"] == 1
    assert len(data["years"]) == 3

    fy24 = next(y for y in data["years"] if y["fiscal_year"] == 2024)
    assert fy24["revenue"] == 391035000000
    assert fy24["net_income"] == 93736000000
    # Gross margin 180683 / 391035 ≈ 46.2%
    assert round(fy24["gross_margin_pct"], 1) == 46.2
    # Net margin 93736 / 391035 ≈ 24.0%
    assert round(fy24["net_margin_pct"], 1) == 24.0
    # FCF = OCF - capex = 118254 - 9447
    assert fy24["fcf"] == 118254000000 - 9447000000
    assert fy24["diluted_shares"] == 15408095000

    # SBC as % of revenue for FY24
    sbc_pct = fy24["sbc_pct_of_revenue"]
    assert round(sbc_pct, 2) == round(11688000000 / 391035000000 * 100, 2)

    # Trend pass-fail gate
    assert "trend_gate" in data
    assert data["trend_gate"]["revenue_up_and_right"] in (True, False, "mixed")


@responses.activate
def test_compute_financials_marks_revenue_trend_mixed(
    fixtures_dir, tmp_path
) -> None:
    """FY22 → FY23 down, FY23 → FY24 up → mixed, not 'up_and_right'."""
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        body=(fixtures_dir / "company_facts_AAPL_sample.json").read_text(),
        status=200,
    )
    out_path = tmp_path / "financials.json"
    compute_financials.main(["AAPL", "--years", "3", "--out", str(out_path)])
    data = json.loads(out_path.read_text())
    assert data["trend_gate"]["revenue_up_and_right"] == "mixed"
