"""Pull XBRL company-facts → financials.json with TTM trends and margins.

Usage:
    compute_financials.py <TICKER> [--years N] --out <path>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from _lib.sec_client import SECClient
from _lib.ticker_resolver import resolve, TickerNotFound

# us-gaap concepts we care about. (concept, unit)
CONCEPTS: dict[str, tuple[str, str]] = {
    "revenue": ("Revenues", "USD"),
    "net_income": ("NetIncomeLoss", "USD"),
    "gross_profit": ("GrossProfit", "USD"),
    "operating_income": ("OperatingIncomeLoss", "USD"),
    "cfo": ("NetCashProvidedByUsedInOperatingActivities", "USD"),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "USD"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "USD"),
    "long_term_debt": ("LongTermDebt", "USD"),
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding", "shares"),
    "sbc": ("ShareBasedCompensation", "USD"),
    "buybacks": ("PaymentsForRepurchaseOfCommonStock", "USD"),
    "dividends_paid": ("PaymentsOfDividends", "USD"),
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute financials.json from XBRL.")
    p.add_argument("ticker")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def _pick_fy_values(
    facts: dict, concept: str, unit: str, years: int
) -> dict[int, float]:
    """Return {fiscal_year: value} for FY 10-K facts under the concept."""
    out: dict[int, float] = {}
    section = facts.get("us-gaap", {}).get(concept)
    if not section:
        return out
    for item in section.get("units", {}).get(unit, []):
        if item.get("fp") == "FY" and item.get("form") == "10-K":
            out[int(item["fy"])] = float(item["val"])
    # Keep the most recent N fiscal years
    keep = sorted(out)[-years:]
    return {fy: out[fy] for fy in keep}


def _safe_div(num: float | None, denom: float | None) -> float | None:
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def _pct(num: float | None, denom: float | None) -> float | None:
    r = _safe_div(num, denom)
    return None if r is None else r * 100.0


def _build_year(fy: int, raw: dict[str, dict[int, float]]) -> dict:
    revenue = raw["revenue"].get(fy)
    net_income = raw["net_income"].get(fy)
    gross_profit = raw["gross_profit"].get(fy)
    op_income = raw["operating_income"].get(fy)
    cfo = raw["cfo"].get(fy)
    capex = raw["capex"].get(fy)
    diluted_shares = raw["diluted_shares"].get(fy)
    sbc = raw["sbc"].get(fy)
    buybacks = raw["buybacks"].get(fy)
    dividends_paid = raw["dividends_paid"].get(fy)
    fcf = (cfo - capex) if (cfo is not None and capex is not None) else None
    return {
        "fiscal_year": fy,
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": op_income,
        "net_income": net_income,
        "cfo": cfo,
        "capex": capex,
        "fcf": fcf,
        "gross_margin_pct": _pct(gross_profit, revenue),
        "operating_margin_pct": _pct(op_income, revenue),
        "net_margin_pct": _pct(net_income, revenue),
        "fcf_margin_pct": _pct(fcf, revenue),
        "diluted_shares": diluted_shares,
        "eps": _safe_div(net_income, diluted_shares),
        "fcf_per_share": _safe_div(fcf, diluted_shares),
        "sbc": sbc,
        "sbc_pct_of_revenue": _pct(sbc, revenue),
        "buybacks": buybacks,
        "dividends_paid": dividends_paid,
    }


def _trend_gate(years: list[dict], key: str) -> bool | str:
    vals = [y[key] for y in years if y.get(key) is not None]
    if len(vals) < 3:
        return "insufficient_data"
    ups = sum(1 for a, b in zip(vals, vals[1:]) if b > a)
    downs = sum(1 for a, b in zip(vals, vals[1:]) if b < a)
    if ups == len(vals) - 1:
        return True
    if downs == len(vals) - 1:
        return False
    return "mixed"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        info = resolve(args.ticker)
    except TickerNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    client = SECClient()
    facts = client.get_company_facts(info.cik_padded).get("facts", {})

    raw = {
        key: _pick_fy_values(facts, concept, unit, args.years)
        for key, (concept, unit) in CONCEPTS.items()
    }
    all_fys: set[int] = set()
    for series in raw.values():
        all_fys.update(series.keys())
    fys = sorted(all_fys)[-args.years :]
    years = [_build_year(fy, raw) for fy in fys]

    result = {
        "ticker": info.ticker,
        "cik": info.cik_padded,
        "name": info.name,
        "schema_version": 1,
        "generated_at": date.today().isoformat(),
        "years": years,
        "trend_gate": {
            "revenue_up_and_right": _trend_gate(years, "revenue"),
            "net_income_up_and_right": _trend_gate(years, "net_income"),
            "fcf_up_and_right": _trend_gate(years, "fcf"),
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(f"Wrote {args.out} ({len(years)} fiscal years)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
