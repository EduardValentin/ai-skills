"""Merge SEC quarter facts into a saved financials document atomically.

Usage:
    <skill-python> -B <scripts-dir>/refresh_quarterly_financials.py \
      --baseline <financials.json> \
      --annual-refresh <staged-annual.json> \
      --company-facts <raw-company-facts.json> \
      --period YYYY-Qn=YYYY-MM-DD [--period ...] \
      --out <financials.json>

The annual refresh, raw SEC response, and canonical output must be distinct
files. The baseline may equal the output so an existing recap document can be
replaced only after the complete merged payload has been built successfully.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path


PERIOD_RE = re.compile(r"^(\d{4}-Q([1-4]))=(\d{4}-\d{2}-\d{2})$")

FLOW_CONCEPTS: dict[str, tuple[list[str], str]] = {
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
    "gross_profit": (["GrossProfit"], "USD"),
    "operating_income": (
        [
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
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
    "sbc": (
        ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
        "USD",
    ),
    "buybacks": (
        ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
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

AVERAGE_CONCEPTS: dict[str, tuple[list[str], str]] = {
    "diluted_shares": (["WeightedAverageNumberOfDilutedSharesOutstanding"], "shares")
}

DILUTED_EPS_CONCEPTS = (["EarningsPerShareDiluted"], "USD/shares")

INSTANT_CONCEPTS: dict[str, tuple[list[str], str]] = {
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
}

ANNUAL_KEYS = (
    "ticker",
    "cik",
    "name",
    "schema_version",
    "generated_at",
    "years",
    "trend_gate",
    "tag_resolution",
    "missing_concepts",
    "data_quality",
    "available_us_gaap_concepts",
)

TTM_FLOW_FIELDS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "cfo",
    "capex",
    "fcf",
    "sbc",
    "buybacks",
    "dividends_paid",
)


def _parse_period(raw: str) -> tuple[str, str]:
    match = PERIOD_RE.fullmatch(raw)
    if not match:
        raise argparse.ArgumentTypeError(
            "period must use YYYY-Qn=YYYY-MM-DD, for example 2026-Q2=2026-06-30"
        )
    report_date = match.group(3)
    try:
        date.fromisoformat(report_date)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid report date: {report_date}") from exc
    return match.group(1), report_date


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge quarterly SEC facts into financials.json."
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--annual-refresh", required=True)
    parser.add_argument("--company-facts", required=True)
    parser.add_argument("--period", action="append", required=True, type=_parse_period)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    out_path = Path(args.out).resolve()
    annual_path = Path(args.annual_refresh).resolve()
    facts_path = Path(args.company_facts).resolve()
    if len({out_path, annual_path, facts_path}) != 3:
        parser.error(
            "--annual-refresh, --company-facts, and --out must be distinct paths"
        )
    if annual_path == Path(args.baseline).resolve():
        parser.error("--annual-refresh must be distinct from --baseline")
    return args


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    finite_numerator = _finite_float(numerator)
    finite_denominator = _finite_float(denominator)
    if finite_numerator is None or finite_denominator in (None, 0):
        return None
    return finite_numerator / finite_denominator


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _positive_float(value: object) -> float | None:
    converted = _finite_float(value)
    return converted if converted is not None and converted > 0 else None


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    ratio = _safe_div(numerator, denominator)
    return None if ratio is None else ratio * 100.0


def _duration_days(item: dict) -> int | None:
    try:
        return (date.fromisoformat(item["end"]) - date.fromisoformat(item["start"])).days + 1
    except (KeyError, TypeError, ValueError):
        return None


def _latest(items: list[dict]) -> dict | None:
    if not items:
        return None
    return max(
        items,
        key=lambda item: (
            str(item.get("filed", "")),
            str(item.get("accn", "")),
            str(item.get("end", "")),
        ),
    )


def _short_duration_item(items: list[dict]) -> dict | None:
    candidates = [
        item
        for item in items
        if _duration_days(item) is not None
        and 0 < _duration_days(item) <= 130
    ]
    if not candidates:
        return None
    shortest = min(_duration_days(item) for item in candidates)
    return _latest([item for item in candidates if _duration_days(item) == shortest])


def _period_items(items: list[dict], report_date: str) -> list[dict]:
    return [
        item
        for item in items
        if item.get("end") == report_date and item.get("form") in {"10-Q", "10-K"}
    ]


def _standalone_item_for_fp(
    items: list[dict], fiscal_year: int, fiscal_period: str
) -> dict | None:
    matching = [
        item
        for item in items
        if item.get("fy") == fiscal_year and item.get("fp") == fiscal_period
    ]
    return _short_duration_item(matching)


def _standalone_for_fp(
    items: list[dict], fiscal_year: int, fiscal_period: str
) -> float | None:
    selected = _standalone_item_for_fp(items, fiscal_year, fiscal_period)
    return _finite_float(selected.get("val")) if selected else None


def _flow_value_for_items(
    items: list[dict], report_date: str, quarter_number: int
) -> float | None:
    exact = _period_items(items, report_date)
    short = _short_duration_item(exact)
    short_value = _finite_float(short.get("val")) if short else None
    if short_value is not None:
        return short_value

    if quarter_number == 4:
        annual_candidates = [
            item
            for item in exact
            if item.get("form") == "10-K" and item.get("fp") == "FY"
        ]
        annual = _latest(annual_candidates)
        annual_value = _finite_float(annual.get("val")) if annual else None
        if annual_value is None or not isinstance(annual.get("fy"), int):
            return None
        prior_quarters = [
            _standalone_for_fp(items, annual["fy"], fiscal_period)
            for fiscal_period in ("Q1", "Q2", "Q3")
        ]
        if any(value is None for value in prior_quarters):
            return None
        return annual_value - sum(
            value for value in prior_quarters if value is not None
        )

    cumulative = [
        item
        for item in exact
        if _duration_days(item) is not None and _duration_days(item) > 130
    ]
    current_ytd = _latest(cumulative)
    current_ytd_value = (
        _finite_float(current_ytd.get("val")) if current_ytd else None
    )
    if current_ytd_value is None:
        return None
    if quarter_number == 1:
        return current_ytd_value
    fiscal_year = current_ytd.get("fy")
    if not isinstance(fiscal_year, int):
        return None
    previous_period = f"Q{quarter_number - 1}"
    previous_candidates = [
        item
        for item in items
        if item.get("fy") == fiscal_year and item.get("fp") == previous_period
    ]
    previous_ytd = max(
        previous_candidates,
        key=lambda item: (_duration_days(item) or 0, str(item.get("filed", ""))),
        default=None,
    )
    previous_ytd_value = (
        _finite_float(previous_ytd.get("val")) if previous_ytd else None
    )
    if previous_ytd_value is None:
        return None
    return current_ytd_value - previous_ytd_value


def _average_details_for_items(
    items: list[dict], report_date: str, quarter_number: int
) -> tuple[float | None, int | None, str]:
    exact = _period_items(items, report_date)
    short = _short_duration_item(exact)
    short_value = _positive_float(short.get("val")) if short else None
    short_days = _duration_days(short) if short else None
    if short_value is not None and short_days is not None and short_days > 0:
        return short_value, short_days, "reported-quarter"

    if quarter_number == 4:
        annual = _latest(
            [
                item
                for item in exact
                if item.get("form") == "10-K" and item.get("fp") == "FY"
            ]
        )
        annual_value = _positive_float(annual.get("val")) if annual else None
        annual_days = _duration_days(annual) if annual else None
        fiscal_year = annual.get("fy") if annual else None
        if (
            annual_value is None
            or annual_days is None
            or annual_days <= 0
            or not isinstance(fiscal_year, int)
        ):
            return None, None, "unavailable"

        prior_weighted_shares = 0.0
        prior_days = 0
        for fiscal_period in ("Q1", "Q2", "Q3"):
            prior = _standalone_item_for_fp(items, fiscal_year, fiscal_period)
            prior_value = _positive_float(prior.get("val")) if prior else None
            duration = _duration_days(prior) if prior else None
            if prior_value is None or duration is None or duration <= 0:
                return None, None, "unavailable"
            prior_weighted_shares += prior_value * duration
            prior_days += duration

        fourth_quarter_days = annual_days - prior_days
        if fourth_quarter_days <= 0:
            return None, None, "unavailable"
        fourth_quarter_shares = (
            annual_value * annual_days - prior_weighted_shares
        ) / fourth_quarter_days
        if _positive_float(fourth_quarter_shares) is None:
            return None, None, "unavailable"
        return (
            fourth_quarter_shares,
            fourth_quarter_days,
            "fiscal-year-duration-residual",
        )
    return None, None, "unavailable"


def _average_value_for_items(
    items: list[dict], report_date: str, quarter_number: int
) -> float | None:
    value, _, _ = _average_details_for_items(items, report_date, quarter_number)
    return value


def _diluted_eps_for_items(items: list[dict], report_date: str) -> float | None:
    selected = _short_duration_item(_period_items(items, report_date))
    return _finite_float(selected.get("val")) if selected else None


def _instant_value_for_items(items: list[dict], report_date: str) -> float | None:
    selected = _latest(_period_items(items, report_date))
    return _finite_float(selected.get("val")) if selected else None


def _concept_value(
    us_gaap: dict,
    candidates: list[str],
    unit: str,
    report_date: str,
    quarter_number: int,
    kind: str,
) -> tuple[float | None, str | None]:
    for concept in candidates:
        items = us_gaap.get(concept, {}).get("units", {}).get(unit, [])
        if kind == "flow":
            value = _flow_value_for_items(items, report_date, quarter_number)
        elif kind == "average":
            value = _average_value_for_items(items, report_date, quarter_number)
        else:
            value = _instant_value_for_items(items, report_date)
        if value is not None:
            return value, concept
    return None, None


def _build_quarter(us_gaap: dict, period: str, report_date: str) -> dict:
    quarter_number = int(period[-1])
    values: dict[str, float | None] = {}
    sources: dict[str, str | None] = {}
    for metric, (candidates, unit) in FLOW_CONCEPTS.items():
        values[metric], sources[metric] = _concept_value(
            us_gaap, candidates, unit, report_date, quarter_number, "flow"
        )
    diluted_share_candidates, diluted_share_unit = AVERAGE_CONCEPTS[
        "diluted_shares"
    ]
    diluted_shares = None
    diluted_shares_duration_days = None
    diluted_shares_basis = "unavailable"
    diluted_shares_source = None
    for concept in diluted_share_candidates:
        items = (
            us_gaap.get(concept, {})
            .get("units", {})
            .get(diluted_share_unit, [])
        )
        value, duration_days, basis = _average_details_for_items(
            items, report_date, quarter_number
        )
        if value is not None:
            diluted_shares = value
            diluted_shares_duration_days = duration_days
            diluted_shares_basis = basis
            diluted_shares_source = concept
            break
    values["diluted_shares"] = diluted_shares
    sources["diluted_shares"] = diluted_shares_source
    for metric, (candidates, unit) in INSTANT_CONCEPTS.items():
        values[metric], sources[metric] = _concept_value(
            us_gaap, candidates, unit, report_date, quarter_number, "instant"
        )

    reported_diluted_eps = None
    reported_diluted_eps_source = None
    diluted_eps_candidates, diluted_eps_unit = DILUTED_EPS_CONCEPTS
    for concept in diluted_eps_candidates:
        items = us_gaap.get(concept, {}).get("units", {}).get(diluted_eps_unit, [])
        reported_diluted_eps = _diluted_eps_for_items(items, report_date)
        if reported_diluted_eps is not None:
            reported_diluted_eps_source = concept
            break
    sources["eps"] = reported_diluted_eps_source

    revenue = values["revenue"]
    cfo = values["cfo"]
    capex = values["capex"]
    fcf = cfo - capex if cfo is not None and capex is not None else None
    cash = values["cash"]
    debt = values["long_term_debt"]
    derived_eps = _safe_div(values["net_income"], diluted_shares)
    eps = reported_diluted_eps
    eps_basis = "reported-diluted-eps"
    if eps is None:
        eps = derived_eps
        eps_basis = (
            "net-income-over-quarterly-diluted-shares"
            if derived_eps is not None
            else "unavailable"
        )

    missing = sorted(metric for metric, value in values.items() if value is None)
    if fcf is None:
        missing.append("fcf")
    if eps is None:
        missing.append("eps")
    return {
        "period": period,
        "report_date": report_date,
        "form": "10-K" if quarter_number == 4 else "10-Q",
        "revenue": revenue,
        "gross_profit": values["gross_profit"],
        "operating_income": values["operating_income"],
        "net_income": values["net_income"],
        "cfo": cfo,
        "capex": capex,
        "fcf": fcf,
        "cash": cash,
        "long_term_debt": debt,
        "net_debt": debt - cash if debt is not None and cash is not None else None,
        "gross_margin_pct": _pct(values["gross_profit"], revenue),
        "operating_margin_pct": _pct(values["operating_income"], revenue),
        "net_margin_pct": _pct(values["net_income"], revenue),
        "fcf_margin_pct": _pct(fcf, revenue),
        "diluted_shares": diluted_shares,
        "diluted_shares_duration_days": diluted_shares_duration_days,
        "diluted_shares_basis": diluted_shares_basis,
        "eps": eps,
        "eps_basis": eps_basis,
        "sbc": values["sbc"],
        "buybacks": values["buybacks"],
        "dividends_paid": values["dividends_paid"],
        "source_concepts": sources,
        "missing_metrics": sorted(set(missing)),
    }


def _discover_periods(us_gaap: dict, requested: dict[str, str]) -> dict[str, str]:
    discovered: dict[str, str] = {}
    for concept in FLOW_CONCEPTS["revenue"][0]:
        items = us_gaap.get(concept, {}).get("units", {}).get("USD", [])
        for item in items:
            fiscal_year = item.get("fy")
            fiscal_period = item.get("fp")
            report_date = item.get("end")
            if (
                not isinstance(fiscal_year, int)
                or fiscal_period not in {"Q1", "Q2", "Q3", "FY"}
                or not isinstance(report_date, str)
                or item.get("form") not in {"10-Q", "10-K"}
            ):
                continue
            quarter = "Q4" if fiscal_period == "FY" else fiscal_period
            discovered.setdefault(report_date, f"{fiscal_year}-{quarter}")
    for period, report_date in requested.items():
        discovered[report_date] = period
    return discovered


def _sum_complete(records: list[dict], field: str) -> float | None:
    values = [_finite_float(record.get(field)) for record in records]
    if len(values) != 4 or any(value is None for value in values):
        return None
    return float(sum(value for value in values if value is not None))


def _annual_for_date(annual: dict, report_date: str) -> dict:
    return next(
        (
            year
            for year in annual.get("years", [])
            if year.get("report_date") == report_date
        ),
        {},
    )


def _duration_weighted_diluted_shares(
    records: list[dict],
) -> tuple[float | None, list[str]]:
    invalid_periods: list[str] = []
    weighted_shares = 0.0
    covered_days = 0.0
    if len(records) != 4:
        invalid_periods.extend(str(record.get("period", "unknown")) for record in records)

    for record in records:
        shares = _positive_float(record.get("diluted_shares"))
        duration_days = _positive_float(record.get("diluted_shares_duration_days"))
        if shares is None or duration_days is None:
            period = str(record.get("period", "unknown"))
            if period not in invalid_periods:
                invalid_periods.append(period)
            continue
        weighted_shares += shares * duration_days
        covered_days += duration_days

    if invalid_periods or len(records) != 4 or covered_days <= 0:
        return None, invalid_periods
    return weighted_shares / covered_days, []


def _ttm_eps(
    records: list[dict],
    net_income: float | None,
    diluted_shares: float | None,
    diluted_share_gaps: list[str],
) -> tuple[float | None, str, dict]:
    reported_eps: list[float] = []
    reported_eps_gaps: list[str] = []
    for record in records:
        value = (
            _finite_float(record.get("eps"))
            if record.get("eps_basis") == "reported-diluted-eps"
            else None
        )
        if value is None:
            reported_eps_gaps.append(str(record.get("period", "unknown")))
        else:
            reported_eps.append(value)

    quality = {
        "status": "unavailable",
        "missing_or_invalid_reported_eps_periods": reported_eps_gaps,
        "missing_or_invalid_diluted_shares_periods": diluted_share_gaps,
    }
    if len(records) == 4 and not reported_eps_gaps:
        quality["status"] = "reported"
        return float(sum(reported_eps)), "sum-quarterly-diluted-eps", quality

    finite_net_income = _finite_float(net_income)
    if finite_net_income is not None and diluted_shares is not None:
        quality["status"] = "derived"
        return (
            finite_net_income / diluted_shares,
            "net-income-over-duration-weighted-diluted-shares",
            quality,
        )
    return None, "unavailable", quality


def _build_ttm(period: str, records: list[dict], annual: dict) -> dict:
    target = records[-1]
    values = {field: _sum_complete(records, field) for field in TTM_FLOW_FIELDS}
    annual_point = _annual_for_date(annual, target["report_date"])
    if period.endswith("Q4"):
        for field in TTM_FLOW_FIELDS:
            annual_value = _finite_float(annual_point.get(field))
            if values[field] is None and annual_value is not None:
                values[field] = annual_value

    revenue = values["revenue"]
    diluted_shares, diluted_share_gaps = _duration_weighted_diluted_shares(records)
    eps, eps_basis, eps_data_quality = _ttm_eps(
        records, values["net_income"], diluted_shares, diluted_share_gaps
    )
    cash = target.get("cash")
    debt = target.get("long_term_debt")
    missing = sorted(field for field, value in values.items() if value is None)
    if diluted_shares is None:
        missing.append("diluted_shares")
    if eps is None:
        missing.append("eps")
    return {
        "period": period,
        "report_date": target["report_date"],
        **values,
        "cash": cash,
        "long_term_debt": debt,
        "net_debt": debt - cash if debt is not None and cash is not None else None,
        "gross_margin_pct": _pct(values["gross_profit"], revenue),
        "operating_margin_pct": _pct(values["operating_income"], revenue),
        "net_margin_pct": _pct(values["net_income"], revenue),
        "fcf_margin_pct": _pct(values["fcf"], revenue),
        "diluted_shares": diluted_shares,
        "diluted_shares_basis": (
            "duration-weighted-quarterly"
            if diluted_shares is not None
            else "unavailable"
        ),
        "eps": eps,
        "eps_basis": eps_basis,
        "eps_data_quality": eps_data_quality,
        "source_periods": [record["period"] for record in records],
        "missing_metrics": sorted(set(missing)),
    }


def _merge_mappings(existing: dict, refreshed: dict) -> dict:
    merged = copy.deepcopy(existing)
    for key, refreshed_value in refreshed.items():
        existing_value = merged.get(key)
        if isinstance(existing_value, dict) and isinstance(refreshed_value, dict):
            merged[key] = _merge_mappings(existing_value, refreshed_value)
        else:
            merged[key] = copy.deepcopy(refreshed_value)
    return merged


def _merge_dated(existing: list[dict], refreshed: list[dict]) -> list[dict]:
    by_date = {
        item["report_date"]: copy.deepcopy(item)
        for item in existing
        if isinstance(item, dict) and isinstance(item.get("report_date"), str)
    }
    for item in refreshed:
        report_date = item["report_date"]
        by_date[report_date] = _merge_mappings(by_date.get(report_date, {}), item)
    return [by_date[report_date] for report_date in sorted(by_date)]


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _refresh(args: argparse.Namespace) -> dict:
    baseline_path = Path(args.baseline)
    annual_path = Path(args.annual_refresh)
    facts_path = Path(args.company_facts)
    baseline = _load_json(baseline_path)
    annual = _load_json(annual_path)
    company_facts = _load_json(facts_path)

    if baseline.get("schema_version") != 1 or annual.get("schema_version") != 1:
        raise ValueError("baseline and annual refresh must use schema_version 1")
    if baseline.get("ticker") != annual.get("ticker"):
        raise ValueError("baseline and annual refresh ticker values must match")
    latest_before = baseline.get("latest_report_date")
    if not isinstance(latest_before, str):
        raise ValueError("baseline.latest_report_date is required")
    date.fromisoformat(latest_before)

    requested = dict(args.period)
    if len(requested) != len(args.period):
        raise ValueError("each --period label must be unique")
    if len(set(requested.values())) != len(requested):
        raise ValueError("each --period report date must be unique")

    us_gaap = company_facts.get("facts", {}).get("us-gaap", {})
    if not isinstance(us_gaap, dict) or not us_gaap:
        raise ValueError("company-facts has no facts.us-gaap object")

    requested_quarters = [
        _build_quarter(us_gaap, period, report_date)
        for period, report_date in sorted(requested.items(), key=lambda item: item[1])
    ]
    discovered = _discover_periods(us_gaap, requested)
    existing_quarters = baseline.get("quarters", [])
    existing_by_date = {
        item["report_date"]: item
        for item in existing_quarters
        if isinstance(item, dict) and isinstance(item.get("report_date"), str)
    }
    cache = {quarter["report_date"]: quarter for quarter in requested_quarters}

    def record_for(report_date: str) -> dict:
        if report_date not in cache:
            period = discovered.get(report_date)
            if period:
                cache[report_date] = _build_quarter(us_gaap, period, report_date)
            elif report_date in existing_by_date:
                cache[report_date] = existing_by_date[report_date]
            else:
                raise ValueError(f"no quarter facts available for {report_date}")
        return cache[report_date]

    all_dates = set(discovered) | set(existing_by_date)
    refreshed_ttm = []
    for period, report_date in sorted(requested.items(), key=lambda item: item[1]):
        trailing_dates = sorted(value for value in all_dates if value <= report_date)[-4:]
        records = [record_for(value) for value in trailing_dates]
        refreshed_ttm.append(_build_ttm(period, records, annual))

    merged = copy.deepcopy(baseline)
    for key in ANNUAL_KEYS:
        if key in annual:
            if key == "years":
                merged[key] = _merge_dated(baseline.get(key, []), annual[key])
            elif (
                key in {"tag_resolution", "data_quality"}
                and isinstance(baseline.get(key), dict)
                and isinstance(annual[key], dict)
            ):
                merged[key] = _merge_mappings(baseline[key], annual[key])
            else:
                merged[key] = copy.deepcopy(annual[key])
        elif key == "available_us_gaap_concepts":
            merged.pop(key, None)
    merged["quarters"] = _merge_dated(existing_quarters, requested_quarters)
    merged["ttm"] = _merge_dated(baseline.get("ttm", []), refreshed_ttm)

    quarterly_sources = copy.deepcopy(baseline.get("quarterly_tag_resolution", {}))
    quarterly_quality = copy.deepcopy(baseline.get("quarterly_data_quality", {}))
    ttm_by_period = {point["period"]: point for point in refreshed_ttm}
    for quarter in requested_quarters:
        period = quarter["period"]
        existing_sources = quarterly_sources.get(period, {})
        existing_quality = quarterly_quality.get(period, {})
        quarterly_sources[period] = _merge_mappings(
            existing_sources if isinstance(existing_sources, dict) else {},
            quarter["source_concepts"],
        )
        quarterly_quality[period] = _merge_mappings(
            existing_quality if isinstance(existing_quality, dict) else {},
            {
                "quarter_missing_metrics": quarter["missing_metrics"],
                "ttm_missing_metrics": ttm_by_period[period]["missing_metrics"],
            },
        )
    merged["quarterly_tag_resolution"] = quarterly_sources
    merged["quarterly_data_quality"] = quarterly_quality

    report_dates = [
        value
        for value in (
            baseline.get("latest_report_date"),
            annual.get("latest_report_date"),
            *(quarter["report_date"] for quarter in requested_quarters),
        )
        if isinstance(value, str)
    ]
    merged["latest_report_date"] = max(report_dates)
    return merged


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        merged = _refresh(args)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _atomic_write_json(Path(args.out), merged)
    print(
        f"Wrote {args.out} ({len(args.period)} recap periods; "
        f"latest_report_date={merged['latest_report_date']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
