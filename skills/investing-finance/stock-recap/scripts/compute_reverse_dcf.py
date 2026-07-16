"""Reverse DCF: solve for the FCF growth rate implied by today's price.

Two-stage DCF: ``years`` of high-growth at rate g, then Gordon-growth
terminal at ``terminal_growth``. Discount everything back at
``discount_rate``.

Usage:
    compute_reverse_dcf.py --financials <path> --price <p>
                           [--discount-rate 0.10] [--terminal-growth 0.025]
                           [--years 10] --out <path>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def present_value(
    *,
    fcf0: float,
    growth: float,
    years: int,
    terminal_growth: float,
    discount_rate: float,
) -> float:
    if discount_rate <= terminal_growth:
        raise ValueError("discount_rate must be > terminal_growth")
    pv = 0.0
    fcf = fcf0
    for t in range(1, years + 1):
        fcf = fcf * (1 + growth)
        pv += fcf / ((1 + discount_rate) ** t)
    terminal_fcf = fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv += terminal_value / ((1 + discount_rate) ** years)
    return pv


def solve_implied_growth(
    *,
    target_pv: float,
    fcf0: float,
    years: int,
    terminal_growth: float,
    discount_rate: float,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    lo, hi = -0.10, 0.50
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        pv = present_value(
            fcf0=fcf0,
            growth=mid,
            years=years,
            terminal_growth=terminal_growth,
            discount_rate=discount_rate,
        )
        if abs(pv - target_pv) < tol * max(target_pv, 1.0):
            return mid
        if pv < target_pv:
            lo = mid
        else:
            hi = mid
    return mid


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reverse DCF.")
    p.add_argument("--financials", required=True)
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--discount-rate", type=float, default=0.10)
    p.add_argument("--terminal-growth", type=float, default=0.025)
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def _latest_fcf_and_shares(financials: dict) -> tuple[float, float]:
    years = sorted(
        [y for y in financials.get("years", []) if y.get("fcf") and y.get("diluted_shares")],
        key=lambda y: y["fiscal_year"],
    )
    if not years:
        raise ValueError("financials.json has no year with both fcf and diluted_shares")
    last = years[-1]
    return float(last["fcf"]), float(last["diluted_shares"])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    financials = json.loads(Path(args.financials).read_text())
    fcf0, shares = _latest_fcf_and_shares(financials)
    target_pv = args.price * shares
    g = solve_implied_growth(
        target_pv=target_pv,
        fcf0=fcf0,
        years=args.years,
        terminal_growth=args.terminal_growth,
        discount_rate=args.discount_rate,
    )
    payload = {
        "ticker": financials.get("ticker"),
        "schema_version": 1,
        "price": args.price,
        "fcf_starting": fcf0,
        "diluted_shares": shares,
        "discount_rate": args.discount_rate,
        "terminal_growth": args.terminal_growth,
        "years": args.years,
        "implied_growth_pct": round(g * 100, 4),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(f"Implied FCF growth at price ${args.price}: {g * 100:.2f}% / yr for {args.years} yr")
    return 0


if __name__ == "__main__":
    sys.exit(main())
