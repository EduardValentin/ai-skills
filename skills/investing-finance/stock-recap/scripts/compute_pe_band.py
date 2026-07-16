"""Compute historical P/E and percentile bands from prices + financials.

Joins daily closes against annual EPS (latest FY's EPS applied forward until
next FY release) and computes 25/50/75 percentile bands plus current
percentile.

Usage:
    compute_pe_band.py --prices <path> --financials <path> --out <path>
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from bisect import bisect_right
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="P/E percentile bands.")
    p.add_argument("--prices", required=True)
    p.add_argument("--financials", required=True)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def _eps_for_date(date_str: str, fy_eps_sorted: list[tuple[int, float]]) -> float | None:
    year = int(date_str[:4])
    keys = [fy for fy, _ in fy_eps_sorted]
    idx = bisect_right(keys, year) - 1
    if idx < 0:
        return None
    eps = fy_eps_sorted[idx][1]
    return eps if eps and eps > 0 else None


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _percentile_rank(sorted_vals: list[float], value: float) -> float:
    if not sorted_vals:
        return float("nan")
    idx = bisect_right(sorted_vals, value)
    return idx / len(sorted_vals) * 100.0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    prices = json.loads(Path(args.prices).read_text())
    financials = json.loads(Path(args.financials).read_text())
    fy_eps = sorted(
        [(y["fiscal_year"], y.get("eps")) for y in financials.get("years", []) if y.get("eps") is not None],
        key=lambda x: x[0],
    )

    pes: list[float] = []
    for bar in prices.get("bars", []):
        eps = _eps_for_date(bar["date"], fy_eps)
        if eps is None:
            continue
        pe = bar["close"] / eps
        if 0 < pe < 1000:
            pes.append(pe)
    pes_sorted = sorted(pes)

    current_pe: float | None = None
    if prices.get("bars"):
        latest = prices["bars"][-1]
        latest_eps = _eps_for_date(latest["date"], fy_eps)
        if latest_eps is not None:
            current_pe = latest["close"] / latest_eps

    out = {
        "ticker": prices.get("ticker"),
        "schema_version": 1,
        "n_observations": len(pes_sorted),
        "percentile_25": _percentile(pes_sorted, 0.25) if pes_sorted else None,
        "percentile_50": statistics.median(pes_sorted) if pes_sorted else None,
        "percentile_75": _percentile(pes_sorted, 0.75) if pes_sorted else None,
        "min": pes_sorted[0] if pes_sorted else None,
        "max": pes_sorted[-1] if pes_sorted else None,
        "current_pe": current_pe,
        "current_percentile": (
            _percentile_rank(pes_sorted, current_pe) if current_pe is not None else None
        ),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out} (n={out['n_observations']}, current P/E={current_pe})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
