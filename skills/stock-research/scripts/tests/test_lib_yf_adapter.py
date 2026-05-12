"""Tests for _lib.yf_adapter (mocked at the yfinance.Ticker level)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from _lib import yf_adapter as yfa


@patch("_lib.yf_adapter.yf.Ticker")
def test_get_history_returns_dataframe(ticker_cls) -> None:
    df = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )
    ticker = MagicMock()
    ticker.history.return_value = df
    ticker_cls.return_value = ticker
    result = yfa.get_history("AAPL", period="1y")
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    ticker.history.assert_called_once_with(period="1y", auto_adjust=False)


@patch("_lib.yf_adapter.yf.Ticker")
def test_get_analyst_price_target_returns_dict(ticker_cls) -> None:
    ticker = MagicMock()
    ticker.info = {
        "targetLowPrice": 150.0,
        "targetMeanPrice": 200.0,
        "targetHighPrice": 280.0,
        "numberOfAnalystOpinions": 35,
    }
    ticker_cls.return_value = ticker
    result = yfa.get_analyst_price_target("AAPL")
    assert result == {
        "low": 150.0,
        "mean": 200.0,
        "high": 280.0,
        "num_analysts": 35,
    }


@patch("_lib.yf_adapter.yf.Ticker")
def test_get_recommendations_counts(ticker_cls) -> None:
    df = pd.DataFrame(
        {
            "period": ["0m"],
            "strongBuy": [10],
            "buy": [15],
            "hold": [8],
            "sell": [2],
            "strongSell": [0],
        }
    )
    ticker = MagicMock()
    ticker.recommendations = df
    ticker_cls.return_value = ticker
    result = yfa.get_recommendations("AAPL")
    assert result == {
        "strong_buy": 10,
        "buy": 15,
        "hold": 8,
        "sell": 2,
        "strong_sell": 0,
    }


@patch("_lib.yf_adapter.yf.Ticker")
def test_get_history_raises_on_empty(ticker_cls) -> None:
    ticker = MagicMock()
    ticker.history.return_value = pd.DataFrame()
    ticker_cls.return_value = ticker
    with pytest.raises(yfa.NoDataError, match="empty"):
        yfa.get_history("ZZZZ", period="1y")
