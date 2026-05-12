"""Tests for fetch_prices.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import fetch_prices


def _hist_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.5, 102.5],
            "Volume": [1_000_000, 1_100_000],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )


def _div_series() -> pd.Series:
    return pd.Series(
        [0.25, 0.25],
        index=pd.to_datetime(["2025-08-15", "2025-11-15"]),
        name="Dividends",
    )


def _split_series() -> pd.Series:
    return pd.Series([], dtype=float, name="Stock Splits")


@patch("fetch_prices.yfa.get_splits", return_value=_split_series())
@patch("fetch_prices.yfa.get_dividends", return_value=_div_series())
@patch("fetch_prices.yfa.get_history", return_value=_hist_df())
def test_fetch_prices_writes_three_files(_h, _d, _s, tmp_path: Path) -> None:
    out_dir = tmp_path / "raw"
    rc = fetch_prices.main(["AAPL", "--years", "10", "--out", str(out_dir)])
    assert rc == 0

    prices = json.loads((out_dir / "prices.json").read_text())
    assert prices["ticker"] == "AAPL"
    assert prices["schema_version"] == 1
    assert len(prices["bars"]) == 2
    assert prices["bars"][0]["close"] == 101.5

    divs = json.loads((out_dir / "dividends.json").read_text())
    assert len(divs["dividends"]) == 2
    assert divs["dividends"][0]["amount"] == 0.25

    splits = json.loads((out_dir / "splits.json").read_text())
    assert splits["splits"] == []


@patch("fetch_prices.yfa.get_history")
def test_fetch_prices_returns_2_on_no_data(history_mock, tmp_path: Path) -> None:
    from _lib.yf_adapter import NoDataError
    history_mock.side_effect = NoDataError("empty history for ZZZZ")
    out_dir = tmp_path / "raw"
    rc = fetch_prices.main(["ZZZZ", "--years", "10", "--out", str(out_dir)])
    assert rc == 2
