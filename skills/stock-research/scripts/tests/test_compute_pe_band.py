"""Tests for compute_pe_band.py."""
from __future__ import annotations

import json
from pathlib import Path

import compute_pe_band


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
            {"fiscal_year": 2022, "eps": 6.11},
            {"fiscal_year": 2023, "eps": 6.13},
            {"fiscal_year": 2024, "eps": 6.08},
        ],
    }
    pp = tmp_path / "prices.json"
    fp = tmp_path / "financials.json"
    op = tmp_path / "pe_band.json"
    pp.write_text(json.dumps(prices))
    fp.write_text(json.dumps(financials))
    return pp, fp, op


def test_pe_band_basic(tmp_path: Path) -> None:
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


def test_pe_band_skips_when_eps_zero(tmp_path: Path) -> None:
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
