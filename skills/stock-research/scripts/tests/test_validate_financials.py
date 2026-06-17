"""Tests for validate_financials.py."""
from __future__ import annotations

import json
from pathlib import Path

import validate_financials


def test_validate_financials_flags_postmortem_failure_modes(tmp_path: Path) -> None:
    financials = {
        "ticker": "FAIL",
        "years": [
            {
                "fiscal_year": 2023,
                "cash": 1000.0,
                "long_term_debt": None,
                "net_debt": -1000.0,
                "dividends_paid": None,
                "diluted_shares": 206.0,
                "eps": 4.0,
            },
            {
                "fiscal_year": 2024,
                "cash": 1200.0,
                "long_term_debt": None,
                "net_debt": -1200.0,
                "dividends_paid": None,
                "diluted_shares": 1042.0,
                "eps": 0.8,
            },
        ],
        "missing_concepts": ["long_term_debt", "dividends_paid"],
        "available_us_gaap_concepts": ["DebtInstrumentFaceAmount", "LongTermDebtNoncurrent"],
    }
    path = tmp_path / "financials.json"
    path.write_text(json.dumps(financials))

    report = validate_financials.validate(path)

    codes = {item["code"] for item in report["findings"]}
    assert "debt_tags_available_but_unmapped" in codes
    assert "unsafe_net_debt" in codes
    assert "dividends_missing_needs_policy_check" in codes
    assert "possible_split_discontinuity" in codes
    assert report["status"] == "fail"
