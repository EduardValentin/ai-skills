"""Tests for compute_pe_band.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    prices = {
        "ticker": "AAPL",
        "schema_version": 1,
        "bars": [
            {"date": "2022-12-30", "open": 130.0, "high": 132.0, "low": 129.0,
             "close": 130.0, "volume": 1},
            {"date": "2023-12-29", "open": 192.0, "high": 193.0, "low": 191.0,
             "close": 192.0, "volume": 1},
            {"date": "2024-12-31", "open": 250.0, "high": 252.0, "low": 248.0,
             "close": 250.0, "volume": 1},
        ],
    }
    financials = {
        "ticker": "AAPL",
        "schema_version": 1,
        "years": [
            {"fiscal_year": 2022, "report_date": "2022-09-24", "eps": 6.11},
            {"fiscal_year": 2023, "report_date": "2023-09-30", "eps": 6.13},
            {"fiscal_year": 2024, "report_date": "2024-09-28", "eps": 6.08},
        ],
    }
    pp = tmp_path / "prices.json"
    fp = tmp_path / "financials.json"
    op = tmp_path / "pe_band.json"
    pp.write_text(json.dumps(prices))
    fp.write_text(json.dumps(financials))
    return pp, fp, op


def test_pe_band_basic(tmp_path: Path, compute_pe_band) -> None:
    pp, fp, op = _make_inputs(tmp_path)
    rc = compute_pe_band.main(
        ["--prices", str(pp), "--financials", str(fp), "--out", str(op)]
    )
    assert rc == 0
    band = json.loads(op.read_text())
    assert band["ticker"] == "AAPL"
    assert band["schema_version"] == 1
    assert "current_pe" in band
    assert "percentile_25" in band
    assert "percentile_50" in band
    assert "percentile_75" in band
    assert "current_percentile" in band
    assert 0 <= band["current_percentile"] <= 100
    # PE TTM at 2024 close = 250 / 6.08 ≈ 41.1
    assert round(band["current_pe"], 1) == round(250 / 6.08, 1)


def test_pe_band_skips_when_eps_zero(tmp_path: Path, compute_pe_band) -> None:
    prices = {
        "ticker": "X",
        "schema_version": 1,
        "bars": [
            {"date": "2024-12-31", "open": 10, "high": 10, "low": 10,
             "close": 10, "volume": 1},
        ],
    }
    financials = {
        "ticker": "X",
        "schema_version": 1,
        "years": [{"fiscal_year": 2024, "eps": 0.0}],
    }
    pp = tmp_path / "p.json"
    fp = tmp_path / "f.json"
    op = tmp_path / "o.json"
    pp.write_text(json.dumps(prices))
    fp.write_text(json.dumps(financials))
    rc = compute_pe_band.main(
        ["--prices", str(pp), "--financials", str(fp), "--out", str(op)]
    )
    assert rc == 0
    band = json.loads(op.read_text())
    assert band["current_pe"] is None


def test_pe_band_emits_explicit_windows_and_ttm_pe(
    tmp_path: Path, compute_pe_band
) -> None:
    prices = {
        "ticker": "AAPL",
        "schema_version": 1,
        "bars": [
            {
                "date": f"{year}-12-31",
                "open": 100.0 + year - 2014,
                "high": 101.0 + year - 2014,
                "low": 99.0 + year - 2014,
                "close": 100.0 + year - 2014,
                "volume": 1,
            }
            for year in range(2014, 2025)
        ],
    }
    financials = {
        "ticker": "AAPL",
        "schema_version": 1,
        "years": [
            {
                "fiscal_year": year,
                "report_date": f"{year}-09-30",
                "eps": 5.0,
            }
            for year in range(2014, 2025)
        ],
        "ttm": [
            {"period": "2024-Q4", "report_date": "2024-09-30", "eps": 8.0}
        ],
    }
    prices_path = tmp_path / "prices.json"
    financials_path = tmp_path / "financials.json"
    out_path = tmp_path / "pe-band.json"
    prices_path.write_text(json.dumps(prices))
    financials_path.write_text(json.dumps(financials))

    rc = compute_pe_band.main(
        [
            "--prices",
            str(prices_path),
            "--financials",
            str(financials_path),
            "--windows",
            "5,10",
            "--ttm-eps",
            "8.0",
            "--out",
            str(out_path),
        ]
    )

    assert rc == 0
    band = json.loads(out_path.read_text())
    assert band["as_of_date"] == "2024-12-31"
    assert band["ttm_eps"] == 8.0
    assert band["current_pe_ttm"] == 110.0 / 8.0
    assert set(band["bands"]) == {"5_year", "10_year"}
    assert band["bands"]["5_year"]["window_start"] == "2019-12-31"
    assert band["bands"]["10_year"]["window_start"] == "2014-12-31"
    assert band["bands"]["5_year"]["n_observations"] == 6
    assert band["bands"]["10_year"]["n_observations"] == 11


@pytest.mark.parametrize(
    "latest_ttm_eps",
    [
        pytest.param(0.0, id="positive-to-zero"),
        pytest.param(-1.5, id="positive-to-negative"),
    ],
)
def test_nonpositive_latest_ttm_eps_ends_historical_pe_and_is_not_meaningful(
    tmp_path: Path,
    compute_pe_band,
    latest_ttm_eps: float,
) -> None:
    prices = {
        "ticker": "LOSS",
        "schema_version": 1,
        "bars": [
            {"date": "2024-06-30", "close": 20.0},
            {"date": "2024-09-30", "close": 18.0},
            {"date": "2024-12-31", "close": 16.0},
        ],
    }
    financials = {
        "ticker": "LOSS",
        "schema_version": 1,
        "ttm": [
            {"period": "2024-Q1", "report_date": "2024-03-31", "eps": 2.0},
            {
                "period": "2024-Q2",
                "report_date": "2024-09-30",
                "eps": latest_ttm_eps,
            },
        ],
    }
    prices_path = tmp_path / "prices.json"
    financials_path = tmp_path / "financials.json"
    out_path = tmp_path / "pe-band.json"
    prices_path.write_text(json.dumps(prices))
    financials_path.write_text(json.dumps(financials))

    rc = compute_pe_band.main(
        [
            "--prices",
            str(prices_path),
            "--financials",
            str(financials_path),
            "--ttm-eps",
            str(latest_ttm_eps),
            "--out",
            str(out_path),
        ]
    )

    assert rc == 0
    band = json.loads(out_path.read_text())
    assert band["ttm_eps"] == latest_ttm_eps
    assert band["current_pe_ttm"] is None
    assert band["current_pe"] is None
    assert band["current_eps_basis"] == "ttm-not-meaningful"
    assert band["n_observations"] == 1
    assert band["current_percentile"] is None
