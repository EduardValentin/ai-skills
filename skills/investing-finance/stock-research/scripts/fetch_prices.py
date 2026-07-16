"""Fetch OHLCV + dividends + splits from yfinance.

Usage:
    fetch_prices.py <TICKER> [--years N] --out <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _lib import yf_adapter as yfa


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch price history via yfinance.")
    p.add_argument("ticker")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    ticker = args.ticker.upper()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    period = f"{args.years}y"
    try:
        hist = yfa.get_history(ticker, period=period)
    except yfa.NoDataError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    bars = [
        {
            "date": str(idx.date()),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        }
        for idx, row in hist.iterrows()
    ]
    (out_dir / "prices.json").write_text(
        json.dumps(
            {"ticker": ticker, "schema_version": 1, "bars": bars}, indent=2
        )
    )

    divs = yfa.get_dividends(ticker)
    div_records = [
        {"date": str(idx.date()), "amount": float(amt)} for idx, amt in divs.items()
    ]
    (out_dir / "dividends.json").write_text(
        json.dumps(
            {"ticker": ticker, "schema_version": 1, "dividends": div_records},
            indent=2,
        )
    )

    splits = yfa.get_splits(ticker)
    split_records = [
        {"date": str(idx.date()), "ratio": float(r)} for idx, r in splits.items()
    ]
    (out_dir / "splits.json").write_text(
        json.dumps(
            {"ticker": ticker, "schema_version": 1, "splits": split_records},
            indent=2,
        )
    )
    print(f"Wrote prices/dividends/splits for {ticker} to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
