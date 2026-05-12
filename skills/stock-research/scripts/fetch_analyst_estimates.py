"""Fetch analyst consensus from yfinance into market-expectations.json.

Usage:
    fetch_analyst_estimates.py <TICKER> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from _lib import yf_adapter as yfa


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch analyst consensus.")
    p.add_argument("ticker")
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    ticker = args.ticker.upper()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "ticker": ticker,
        "schema_version": 1,
        "fetched_at": date.today().isoformat(),
        "price_target": yfa.get_analyst_price_target(ticker),
        "ratings": yfa.get_recommendations(ticker),
        "earnings_estimate": yfa.get_earnings_estimate(ticker),
        "revenue_estimate": yfa.get_revenue_estimate(ticker),
        "eps_trend": yfa.get_eps_trend(ticker),
        "growth_estimates": yfa.get_growth_estimates(ticker),
    }
    (out_dir / "market-expectations.json").write_text(json.dumps(payload, indent=2))
    print(f"Wrote market-expectations.json for {ticker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
