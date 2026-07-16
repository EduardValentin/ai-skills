"""Pull XBRL company-facts → financials.json with TTM trends and margins.

Usage:
    compute_financials.py <TICKER> [--years N] --out <path>

Companies report the same business metric under different `us-gaap` concept
names — SEC's XBRL taxonomy has evolved (especially around ASC 606 in 2018,
which added `RevenueFromContractWithCustomerExcludingAssessedTax`) and some
companies have their own conventions. For each metric we look at a list of
candidate concepts and pick the first one that has data. The output JSON
records which concept actually resolved (`tag_resolution`) and which metrics
had no candidate hit (`missing_concepts`), so the Phase 3 subagent can apply
critical thinking to fill gaps rather than silently emit null fields.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from _lib.sec_client import SECClient
from _lib.ticker_resolver import resolve, TickerNotFound

# us-gaap concept candidates per metric. Each entry is (candidate_list, unit).
# Candidates are tried in order; the first one with any FY 10-K data wins.
#
# When extending: prefer the most "natural" / current taxonomy name first,
# then fall back to older names, then to broader categories. Adding more
# candidates is cheap — they're only consulted if earlier ones returned no data.
CONCEPTS: dict[str, tuple[list[str], str]] = {
    "revenue": (
        [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
            "Revenue",
        ],
        "USD",
    ),
    "net_income": (
        [
            "NetIncomeLoss",
            "ProfitLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
        ],
        "USD",
    ),
    "gross_profit": (["GrossProfit"], "USD"),
    "operating_income": (
        [
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ],
        "USD",
    ),
    "cfo": (
        [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
        "USD",
    ),
    "capex": (
        [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "PaymentsForPropertyPlantAndEquipment",
        ],
        "USD",
    ),
    "cash": (
        [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "Cash",
        ],
        "USD",
    ),
    "long_term_debt": (
        [
            "LongTermDebt",
            "LongTermDebtNoncurrent",
            "LongTermDebtCurrent",
            "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
            "LongTermDebtAndFinanceLeaseObligationsCurrent",
            "ConvertibleDebtNoncurrent",
            "ConvertibleDebtCurrent",
            "DebtInstrumentFaceAmount",
        ],
        "USD",
    ),
    "diluted_shares": (
        ["WeightedAverageNumberOfDilutedSharesOutstanding"],
        "shares",
    ),
    "sbc": (
        [
            "ShareBasedCompensation",
            "AllocatedShareBasedCompensationExpense",
        ],
        "USD",
    ),
    "buybacks": (
        [
            "PaymentsForRepurchaseOfCommonStock",
            "PaymentsForRepurchaseOfEquity",
        ],
        "USD",
    ),
    "dividends_paid": (
        [
            "PaymentsOfDividends",
            "PaymentsOfDividendsCommonStock",
            "PaymentsOfDividendsMinorityInterest",
        ],
        "USD",
    ),
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute financials.json from XBRL.")
    p.add_argument("ticker")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def _pick_fy_values_for_concept(
    facts: dict, concept: str, unit: str, years: int
) -> dict[int, float]:
    """Return {fiscal_year: value} for FY 10-K facts under a single concept."""
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


def _pick_fy_values_with_fallback(
    facts: dict, candidates: list[str], unit: str, years: int
) -> tuple[dict[int, float], str | None]:
    """Try each candidate concept in order. Return (data, used_concept).

    Merges data across candidates: if Revenues covers FY2015-2017 and
    RevenueFromContractWithCustomerExcludingAssessedTax covers FY2018-2024,
    we want both windows. used_concept names the candidate that contributed
    the LATEST fiscal year (i.e., the one that's currently "in use").
    """
    merged: dict[int, float] = {}
    latest_used: str | None = None
    latest_fy = -1
    for candidate in candidates:
        data = _pick_fy_values_for_concept(facts, candidate, unit, years)
        if not data:
            continue
        for fy, val in data.items():
            merged.setdefault(fy, val)  # first candidate to provide a year wins
            if fy > latest_fy:
                latest_fy = fy
                latest_used = candidate
    # Trim again after merging across candidates
    keep = sorted(merged)[-years:]
    return {fy: merged[fy] for fy in keep}, latest_used


def _safe_div(num: float | None, denom: float | None) -> float | None:
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def _pct(num: float | None, denom: float | None) -> float | None:
    r = _safe_div(num, denom)
    return None if r is None else r * 100.0


def _net_debt(ltd: float | None, cash: float | None) -> float | None:
    if ltd is None or cash is None:
        return None
    return ltd - cash


def _share_discontinuities(years: list[dict]) -> list[dict]:
    """Flag share-count jumps that look like unapplied stock splits."""
    findings: list[dict] = []
    ordered = [y for y in years if y.get("diluted_shares")]
    for prev, curr in zip(ordered, ordered[1:]):
        prev_shares = prev["diluted_shares"]
        curr_shares = curr["diluted_shares"]
        if not prev_shares or not curr_shares:
            continue
        ratio = curr_shares / prev_shares
        if ratio >= 2.5 or ratio <= 0.4:
            findings.append(
                {
                    "code": "possible_split_discontinuity",
                    "from_fiscal_year": prev["fiscal_year"],
                    "to_fiscal_year": curr["fiscal_year"],
                    "ratio": ratio,
                    "message": (
                        "Diluted shares changed by a split-like ratio. Verify the "
                        "latest 10-K restated historical share and per-share data "
                        "before comparing EPS or per-share values."
                    ),
                }
            )
    return findings


def _data_quality(
    tag_resolution: dict[str, str | None],
    missing_concepts: list[str],
    years: list[dict],
) -> dict:
    metric_quality = {}
    for metric, source in tag_resolution.items():
        metric_quality[metric] = {
            "status": "missing" if metric in missing_concepts else "reported",
            "source": source,
        }

    net_debt_inputs_missing = "long_term_debt" in missing_concepts or "cash" in missing_concepts
    return {
        "metrics": metric_quality,
        "derived_metrics": {
            "net_debt": {
                "status": "unreliable" if net_debt_inputs_missing else "computed",
                "requires": ["long_term_debt", "cash"],
                "message": (
                    "Net debt is null/unreliable when cash or debt is missing; "
                    "do not treat missing debt as zero."
                    if net_debt_inputs_missing
                    else "Computed only for years with both cash and debt present."
                ),
            },
        },
        "warnings": _share_discontinuities(years),
    }


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
    cash_val = raw["cash"].get(fy)
    ltd_val = raw["long_term_debt"].get(fy)
    return {
        "fiscal_year": fy,
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": op_income,
        "net_income": net_income,
        "cfo": cfo,
        "capex": capex,
        "fcf": fcf,
        "cash": cash_val,
        "long_term_debt": ltd_val,
        "net_debt": _net_debt(ltd_val, cash_val),
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

    raw: dict[str, dict[int, float]] = {}
    tag_resolution: dict[str, str | None] = {}
    missing_concepts: list[str] = []
    for key, (candidates, unit) in CONCEPTS.items():
        data, used = _pick_fy_values_with_fallback(facts, candidates, unit, args.years)
        raw[key] = data
        tag_resolution[key] = used
        if used is None:
            missing_concepts.append(key)

    all_fys: set[int] = set()
    for series in raw.values():
        all_fys.update(series.keys())
    fys = sorted(all_fys)[-args.years :]
    years = [_build_year(fy, raw) for fy in fys]

    result: dict = {
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
        "tag_resolution": tag_resolution,
        "missing_concepts": missing_concepts,
        "data_quality": _data_quality(tag_resolution, missing_concepts, years),
    }
    # If anything failed to resolve, dump the list of available us-gaap
    # concept names so the subagent can manually pick a substitute.
    if missing_concepts:
        result["available_us_gaap_concepts"] = sorted(
            facts.get("us-gaap", {}).keys()
        )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    if missing_concepts:
        print(
            f"Wrote {args.out} ({len(years)} fiscal years) — "
            f"WARNING: {len(missing_concepts)} concepts had no candidate hit: "
            f"{', '.join(missing_concepts)}. See 'available_us_gaap_concepts' in the JSON.",
            file=sys.stderr,
        )
    else:
        print(f"Wrote {args.out} ({len(years)} fiscal years)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
