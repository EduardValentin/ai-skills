"""Compute date-aware historical P/E percentile bands.

Usage:
    <skill-python> -B <scripts-dir>/compute_pe_band.py --prices <path> --financials <path> --out <path>
                       [--windows 5,10] [--ttm-eps <value>]

Historical observations use the most recent dated EPS point available in
``financials.json``. Nonpositive EPS points remain validity boundaries instead
of allowing an older profit period to leak forward. ``--ttm-eps`` is an
explicit current-value input: when it is present, the output reports a distinct
``current_pe_ttm`` value, or null when current TTM EPS is not positive.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from bisect import bisect_right
from datetime import date
from pathlib import Path


def _parse_windows(raw: str) -> list[int]:
    try:
        windows = sorted({int(value.strip()) for value in raw.split(",") if value.strip()})
    except ValueError as exc:
        raise argparse.ArgumentTypeError("windows must be comma-separated integers") from exc
    if not windows or any(window <= 0 for window in windows):
        raise argparse.ArgumentTypeError("windows must contain positive integers")
    return windows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P/E percentile bands.")
    parser.add_argument("--prices", required=True)
    parser.add_argument("--financials", required=True)
    parser.add_argument("--windows", type=_parse_windows, default=[5, 10])
    parser.add_argument("--ttm-eps", type=float)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def _eps_for_date(
    date_str: str, eps_points: list[tuple[str, float]]
) -> float | None:
    keys = [effective_date for effective_date, _ in eps_points]
    idx = bisect_right(keys, date_str) - 1
    if idx < 0:
        return None
    eps = eps_points[idx][1]
    return eps if eps > 0 else None


def _eps_points(financials: dict) -> list[tuple[str, float]]:
    points: dict[str, float] = {}
    for year in financials.get("years", []):
        eps = year.get("eps")
        report_date = year.get("report_date")
        if report_date is None and year.get("fiscal_year") is not None:
            report_date = f"{int(year['fiscal_year']):04d}-12-31"
        if isinstance(report_date, str) and isinstance(eps, (int, float)):
            points[report_date] = float(eps)

    for period in financials.get("ttm", []):
        eps = period.get("eps")
        report_date = period.get("report_date")
        if isinstance(report_date, str) and isinstance(eps, (int, float)):
            points[report_date] = float(eps)
    return sorted(points.items())


def _percentile(sorted_vals: list[float], percentile: float) -> float:
    if not sorted_vals:
        return float("nan")
    position = (len(sorted_vals) - 1) * percentile
    floor = int(position)
    ceiling = min(floor + 1, len(sorted_vals) - 1)
    return sorted_vals[floor] + (
        sorted_vals[ceiling] - sorted_vals[floor]
    ) * (position - floor)


def _percentile_rank(sorted_vals: list[float], value: float) -> float:
    if not sorted_vals:
        return float("nan")
    idx = bisect_right(sorted_vals, value)
    return idx / len(sorted_vals) * 100.0


def _years_ago(date_str: str, years: int) -> str:
    as_of = date.fromisoformat(date_str)
    try:
        return as_of.replace(year=as_of.year - years).isoformat()
    except ValueError:
        return as_of.replace(year=as_of.year - years, day=28).isoformat()


def _band_payload(
    observations: list[tuple[str, float]],
    *,
    window_years: int,
    window_start: str,
    window_end: str,
    current_pe: float | None,
) -> dict:
    values = sorted(
        pe for observation_date, pe in observations if observation_date >= window_start
    )
    return {
        "window_years": window_years,
        "window_start": window_start,
        "window_end": window_end,
        "n_observations": len(values),
        "percentile_25": _percentile(values, 0.25) if values else None,
        "percentile_50": statistics.median(values) if values else None,
        "percentile_75": _percentile(values, 0.75) if values else None,
        "min": values[0] if values else None,
        "max": values[-1] if values else None,
        "current_percentile": (
            _percentile_rank(values, current_pe)
            if values and current_pe is not None
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    prices = json.loads(Path(args.prices).read_text())
    financials = json.loads(Path(args.financials).read_text())
    bars = sorted(prices.get("bars", []), key=lambda bar: bar["date"])
    eps_points = _eps_points(financials)

    observations: list[tuple[str, float]] = []
    for bar in bars:
        eps = _eps_for_date(bar["date"], eps_points)
        if eps is None:
            continue
        pe = bar["close"] / eps
        if 0 < pe < 1000:
            observations.append((bar["date"], pe))

    as_of_date = bars[-1]["date"] if bars else None
    current_close = bars[-1]["close"] if bars else None
    latest_eps = _eps_for_date(as_of_date, eps_points) if as_of_date else None
    current_pe_ttm = (
        current_close / args.ttm_eps
        if current_close is not None
        and args.ttm_eps is not None
        and args.ttm_eps > 0
        else None
    )
    if args.ttm_eps is not None:
        current_pe = current_pe_ttm
        current_eps_basis = "ttm" if args.ttm_eps > 0 else "ttm-not-meaningful"
    elif current_close is not None and latest_eps is not None:
        current_pe = current_close / latest_eps
        current_eps_basis = "latest-dated-financials"
    else:
        current_pe = None
        current_eps_basis = "unavailable"

    bands = {}
    if as_of_date:
        for window in args.windows:
            bands[f"{window}_year"] = _band_payload(
                observations,
                window_years=window,
                window_start=_years_ago(as_of_date, window),
                window_end=as_of_date,
                current_pe=current_pe,
            )

    longest_band = bands.get(f"{max(args.windows)}_year", {})
    out = {
        "ticker": prices.get("ticker"),
        "schema_version": 1,
        "as_of_date": as_of_date,
        "ttm_eps": args.ttm_eps,
        "current_pe_ttm": current_pe_ttm,
        "current_pe": current_pe,
        "current_eps_basis": current_eps_basis,
        "bands": bands,
        # Preserve the original top-level contract as the longest requested window.
        "n_observations": longest_band.get("n_observations", 0),
        "percentile_25": longest_band.get("percentile_25"),
        "percentile_50": longest_band.get("percentile_50"),
        "percentile_75": longest_band.get("percentile_75"),
        "min": longest_band.get("min"),
        "max": longest_band.get("max"),
        "current_percentile": longest_band.get("current_percentile"),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(
        f"Wrote {args.out} (windows={','.join(map(str, args.windows))}, "
        f"current P/E={current_pe})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
