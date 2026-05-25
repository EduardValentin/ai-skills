"""Download SEC filings for a ticker into a directory.

Usage:
    fetch_sec.py <TICKER> [--forms 10-K,10-Q,8-K] [--since YYYY-MM-DD] --out <dir>

Writes one file per filing plus _filings_index.json listing what was fetched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _lib.sec_client import SECClient
from _lib.ticker_resolver import resolve, TickerNotFound


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download SEC filings for a ticker.")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument(
        "--forms",
        default="10-K,10-Q,8-K",
        help="Comma-separated SEC form types to fetch (default: 10-K,10-Q,8-K)",
    )
    parser.add_argument("--since", help="Earliest filing date (YYYY-MM-DD)")
    parser.add_argument("--out", required=True, help="Output directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = resolve(args.ticker)
    except TickerNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    client = SECClient()
    forms = {f.strip() for f in args.forms.split(",") if f.strip()}
    filings = client.list_filings(cik=info.cik_padded, forms=forms, since=args.since)

    index = {
        "ticker": info.ticker,
        "schema_version": 1,
        "cik": info.cik_padded,
        "name": info.name,
        "filings": [],
    }
    for f in filings:
        body = client.get_filing_html(f)
        filename = f"{f.accession}-{f.form.replace('/', '_')}-{f.filing_date}.html"
        (out_dir / filename).write_text(body)
        index["filings"].append(
            {
                "accession": f.accession,
                "form": f.form,
                "filing_date": f.filing_date,
                "report_date": f.report_date,
                "filename": filename,
            }
        )

    (out_dir / "_filings_index.json").write_text(json.dumps(index, indent=2))
    print(f"Fetched {len(filings)} filings for {info.ticker} into {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
