"""Validate financials.json for unsafe missing-data interpretations.

Usage:
    validate_financials.py <financials.json> [--out <report.json>]

This is a checkpoint guard for the stock-research workflow. It does not try to
fix values. It flags cases where the orchestrator or Phase 3 worker must inspect
the 10-K narrative or inline XBRL before showing financials to the user.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEBT_TAGS = {
    "LongTermDebt",
    "LongTermDebtNoncurrent",
    "LongTermDebtCurrent",
    "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    "LongTermDebtAndFinanceLeaseObligationsCurrent",
    "ConvertibleDebtNoncurrent",
    "ConvertibleDebtCurrent",
    "DebtInstrumentFaceAmount",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate stock-research financials.json.")
    parser.add_argument("financials_json")
    parser.add_argument("--out")
    return parser.parse_args(argv)


def _finding(code: str, severity: str, message: str, **extra: Any) -> dict[str, Any]:
    item = {"code": code, "severity": severity, "message": message}
    item.update(extra)
    return item


def validate(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text())
    findings: list[dict[str, Any]] = []
    missing = set(data.get("missing_concepts", []))
    available = set(data.get("available_us_gaap_concepts", []))
    years = data.get("years", [])

    if "long_term_debt" in missing and available.intersection(DEBT_TAGS):
        findings.append(
            _finding(
                "debt_tags_available_but_unmapped",
                "error",
                "Debt is missing, but debt-related us-gaap tags are available. Inspect inline XBRL and map the correct debt value before relying on leverage or net debt.",
                tags=sorted(available.intersection(DEBT_TAGS)),
            )
        )

    unsafe_years = [
        y.get("fiscal_year")
        for y in years
        if y.get("cash") is not None
        and y.get("long_term_debt") is None
        and y.get("net_debt") is not None
    ]
    if unsafe_years:
        findings.append(
            _finding(
                "unsafe_net_debt",
                "error",
                "Net debt was computed while debt was missing. Derived debt metrics must be null/unreliable until debt is resolved.",
                fiscal_years=unsafe_years,
            )
        )

    if "dividends_paid" in missing:
        findings.append(
            _finding(
                "dividends_missing_needs_policy_check",
                "warning",
                "Dividends are missing. Check the 10-K dividend-policy language; mark zero only if the filing explicitly supports no common dividend.",
            )
        )

    ordered = [y for y in years if y.get("diluted_shares")]
    for prev, curr in zip(ordered, ordered[1:]):
        ratio = curr["diluted_shares"] / prev["diluted_shares"]
        if ratio >= 2.5 or ratio <= 0.4:
            findings.append(
                _finding(
                    "possible_split_discontinuity",
                    "warning",
                    "Diluted shares changed by a split-like ratio. Use the latest 10-K restated comparative share and EPS values or normalize all years before comparison.",
                    from_fiscal_year=prev.get("fiscal_year"),
                    to_fiscal_year=curr.get("fiscal_year"),
                    ratio=ratio,
                )
            )

    status = "fail" if any(f["severity"] == "error" for f in findings) else "warn" if findings else "pass"
    return {
        "ticker": data.get("ticker"),
        "status": status,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    report = validate(args.financials_json)
    rendered = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(rendered)
    else:
        print(rendered)
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
