"""Thin adapter around yfinance so the scripts can be tested with mocks.

yfinance's API is rich and scraping-driven; we normalize what we use into
small dict shapes downstream code can rely on.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf


class NoDataError(RuntimeError):
    pass


def get_history(ticker: str, *, period: str = "10y") -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if df is None or df.empty:
        raise NoDataError(f"yfinance returned empty history for {ticker}")
    return df


def get_dividends(ticker: str) -> pd.Series:
    return yf.Ticker(ticker).dividends


def get_splits(ticker: str) -> pd.Series:
    return yf.Ticker(ticker).splits


def get_info(ticker: str) -> dict:
    return dict(yf.Ticker(ticker).info or {})


def get_analyst_price_target(ticker: str) -> dict:
    info = get_info(ticker)
    return {
        "low": info.get("targetLowPrice"),
        "mean": info.get("targetMeanPrice"),
        "high": info.get("targetHighPrice"),
        "num_analysts": info.get("numberOfAnalystOpinions"),
    }


def get_recommendations(ticker: str) -> dict:
    df = yf.Ticker(ticker).recommendations
    if df is None or df.empty:
        return {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
    row = df.iloc[0]
    return {
        "strong_buy": int(row.get("strongBuy", 0)),
        "buy": int(row.get("buy", 0)),
        "hold": int(row.get("hold", 0)),
        "sell": int(row.get("sell", 0)),
        "strong_sell": int(row.get("strongSell", 0)),
    }


def get_earnings_estimate(ticker: str) -> dict:
    df = yf.Ticker(ticker).earnings_estimate
    return df.to_dict() if df is not None and not df.empty else {}


def get_revenue_estimate(ticker: str) -> dict:
    df = yf.Ticker(ticker).revenue_estimate
    return df.to_dict() if df is not None and not df.empty else {}


def get_eps_trend(ticker: str) -> dict:
    df = yf.Ticker(ticker).eps_trend
    return df.to_dict() if df is not None and not df.empty else {}


def get_growth_estimates(ticker: str) -> dict:
    df = yf.Ticker(ticker).growth_estimates
    return df.to_dict() if df is not None and not df.empty else {}
