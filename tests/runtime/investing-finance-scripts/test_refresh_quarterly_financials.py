"""Tests for the stock-research quarterly financials merge runtime."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    REPO_ROOT
    / "skills"
    / "investing-finance"
    / "stock-research"
    / "scripts"
    / "refresh_quarterly_financials.py"
)


def _load_script(tmp_path: Path):
    assert SCRIPT_PATH.is_file(), "stock-research quarterly refresh runtime is missing"
    spec = importlib.util.spec_from_file_location(
        "stock_research_refresh_quarterly_financials", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    original_pycache_prefix = sys.pycache_prefix
    try:
        sys.pycache_prefix = str(tmp_path / "python-pycache")
        spec.loader.exec_module(module)
    finally:
        sys.pycache_prefix = original_pycache_prefix
    return module


def _duration_fact(
    *,
    start: str,
    end: str,
    value: object,
    fiscal_year: int,
    fiscal_period: str,
    form: str,
) -> dict:
    return {
        "start": start,
        "end": end,
        "val": value,
        "fy": fiscal_year,
        "fp": fiscal_period,
        "form": form,
        "filed": "2025-02-01",
    }


def _quarterly_company_facts(
    *,
    diluted_shares: list[object] | None = None,
    diluted_eps: list[object] | None = None,
) -> dict:
    diluted_shares = diluted_shares or [10.0, 10.0, 10.0, 10.0]
    periods = [
        ("2024-01-01", "2024-03-31", "Q1", "10-Q"),
        ("2024-04-01", "2024-06-30", "Q2", "10-Q"),
        ("2024-07-01", "2024-09-30", "Q3", "10-Q"),
        ("2024-01-01", "2024-12-31", "FY", "10-K"),
    ]

    def flow(values: list[float]) -> dict:
        return {
            "units": {
                "USD": [
                    _duration_fact(
                        start=start,
                        end=end,
                        value=value,
                        fiscal_year=2024,
                        fiscal_period=fp,
                        form=form,
                    )
                    for (start, end, fp, form), value in zip(periods, values)
                ]
            }
        }

    shares = {
        "units": {
            "shares": [
                _duration_fact(
                    start=start,
                    end=end,
                    value=value,
                    fiscal_year=2024,
                    fiscal_period=fp,
                    form=form,
                )
                for (start, end, fp, form), value in zip(periods, diluted_shares)
            ]
        }
    }
    instants = [
        {
            "end": end,
            "val": value,
            "fy": 2024,
            "fp": fp,
            "form": form,
            "filed": "2025-02-01",
        }
        for (_, end, fp, form), value in zip(periods, [5.0, 6.0, 7.0, 8.0])
    ]
    us_gaap = {
        "Revenues": flow([10.0, 20.0, 30.0, 100.0]),
        "GrossProfit": flow([5.0, 10.0, 15.0, 50.0]),
        "OperatingIncomeLoss": flow([2.0, 4.0, 6.0, 20.0]),
        "NetIncomeLoss": flow([1.0, 2.0, 3.0, 10.0]),
        "NetCashProvidedByUsedInOperatingActivities": flow(
            [11.0, 21.0, 31.0, 100.0]
        ),
        "PaymentsToAcquirePropertyPlantAndEquipment": flow(
            [1.0, 1.0, 1.0, 10.0]
        ),
        "WeightedAverageNumberOfDilutedSharesOutstanding": shares,
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": instants}},
        "LongTermDebt": {"units": {"USD": instants}},
    }
    if diluted_eps is not None:
        standalone_periods = [
            ("2024-01-01", "2024-03-31", "Q1", "10-Q"),
            ("2024-04-01", "2024-06-30", "Q2", "10-Q"),
            ("2024-07-01", "2024-09-30", "Q3", "10-Q"),
            ("2024-10-01", "2024-12-31", "FY", "10-K"),
        ]
        us_gaap["EarningsPerShareDiluted"] = {
            "units": {
                "USD/shares": [
                    _duration_fact(
                        start=start,
                        end=end,
                        value=value,
                        fiscal_year=2024,
                        fiscal_period=fp,
                        form=form,
                    )
                    for (start, end, fp, form), value in zip(
                        standalone_periods, diluted_eps
                    )
                ]
            }
        }

    return {
        "cik": 1,
        "entityName": "Example Corp",
        "facts": {"us-gaap": us_gaap},
    }


def _write_inputs(
    tmp_path: Path, *, company_facts: dict | None = None
) -> tuple[Path, Path, Path]:
    baseline_path = tmp_path / "financials.json"
    annual_path = tmp_path / "staged-annual.json"
    facts_path = tmp_path / "company-facts.json"
    baseline_path.write_text(
        json.dumps(
            {
                "ticker": "EXM",
                "cik": "0000000001",
                "name": "Example Corp",
                "schema_version": 1,
                "generated_at": "2024-02-01",
                "latest_report_date": "2023-12-31",
                "years": [
                    {
                        "fiscal_year": 2023,
                        "report_date": "2023-12-31",
                        "revenue": 80.0,
                    }
                ],
                "quarters": [
                    {
                        "period": "2023-Q4",
                        "report_date": "2023-12-31",
                        "revenue": 20.0,
                    }
                ],
                "ttm": [
                    {
                        "period": "2023-Q4",
                        "report_date": "2023-12-31",
                        "revenue": 80.0,
                    }
                ],
                "manual_resolution": {"story_metric": "preserve me"},
            },
            indent=2,
        )
    )
    annual_path.write_text(
        json.dumps(
            {
                "ticker": "EXM",
                "cik": "0000000001",
                "name": "Example Corp",
                "schema_version": 1,
                "generated_at": "2025-02-01",
                "latest_report_date": "2024-12-31",
                "years": [
                    {
                        "fiscal_year": 2024,
                        "report_date": "2024-12-31",
                        "revenue": 100.0,
                    }
                ],
                "tag_resolution": {"revenue": "Revenues"},
                "missing_concepts": [],
                "data_quality": {},
                "trend_gate": {},
            },
            indent=2,
        )
    )
    facts_path.write_text(
        json.dumps(company_facts or _quarterly_company_facts(), indent=2)
    )
    return baseline_path, annual_path, facts_path


def _main_args(baseline_path: Path, annual_path: Path, facts_path: Path) -> list[str]:
    args = [
        "--baseline",
        str(baseline_path),
        "--annual-refresh",
        str(annual_path),
        "--company-facts",
        str(facts_path),
    ]
    for period, report_date in (
        ("2024-Q1", "2024-03-31"),
        ("2024-Q2", "2024-06-30"),
        ("2024-Q3", "2024-09-30"),
        ("2024-Q4", "2024-12-31"),
    ):
        args.extend(["--period", f"{period}={report_date}"])
    args.extend(["--out", str(baseline_path)])
    return args


def test_refresh_preserves_prior_state_and_merges_quarterly_ttm(
    tmp_path: Path,
) -> None:
    refresh = _load_script(tmp_path)
    baseline_path, annual_path, facts_path = _write_inputs(tmp_path)

    rc = refresh.main(_main_args(baseline_path, annual_path, facts_path))

    assert rc == 0
    merged = json.loads(baseline_path.read_text())
    assert merged["manual_resolution"] == {"story_metric": "preserve me"}
    assert [point["report_date"] for point in merged["years"]] == [
        "2023-12-31",
        "2024-12-31",
    ]
    assert merged["latest_report_date"] == "2024-12-31"
    assert [q["period"] for q in merged["quarters"]] == [
        "2023-Q4",
        "2024-Q1",
        "2024-Q2",
        "2024-Q3",
        "2024-Q4",
    ]
    q4 = next(q for q in merged["quarters"] if q["period"] == "2024-Q4")
    assert q4["revenue"] == 40.0
    assert q4["fcf"] == 30.0
    latest_ttm = merged["ttm"][-1]
    assert latest_ttm["period"] == "2024-Q4"
    assert latest_ttm["revenue"] == 100.0
    assert latest_ttm["fcf"] == 90.0
    assert latest_ttm["eps"] == 1.0
    assert latest_ttm["diluted_shares"] == 10.0
    assert latest_ttm["eps_basis"] == (
        "net-income-over-duration-weighted-diluted-shares"
    )
    assert latest_ttm["eps_data_quality"]["status"] == "derived"


def test_ttm_eps_sums_reported_quarterly_diluted_eps_with_changing_shares(
    tmp_path: Path,
) -> None:
    refresh = _load_script(tmp_path)
    company_facts = _quarterly_company_facts(
        diluted_shares=[10.0, 8.0, 6.0, 7.5],
        diluted_eps=[0.10, 0.25, 0.50, 0.67],
    )
    baseline_path, annual_path, facts_path = _write_inputs(
        tmp_path, company_facts=company_facts
    )

    assert refresh.main(_main_args(baseline_path, annual_path, facts_path)) == 0

    latest_ttm = json.loads(baseline_path.read_text())["ttm"][-1]
    assert latest_ttm["eps"] == pytest.approx(1.52)
    assert latest_ttm["eps_basis"] == "sum-quarterly-diluted-eps"
    assert latest_ttm["eps_data_quality"] == {
        "status": "reported",
        "missing_or_invalid_reported_eps_periods": [],
        "missing_or_invalid_diluted_shares_periods": [],
    }
    assert latest_ttm["diluted_shares"] == pytest.approx(7.5)
    latest_quarter = next(
        quarter
        for quarter in json.loads(baseline_path.read_text())["quarters"]
        if quarter["period"] == "2024-Q4"
    )
    assert latest_ttm["eps"] != pytest.approx(
        latest_ttm["net_income"] / latest_quarter["diluted_shares"]
    )


@pytest.mark.parametrize("unusable_eps", [None, "invalid"])
def test_ttm_eps_uses_duration_weighted_shares_when_reported_eps_is_incomplete(
    tmp_path: Path, unusable_eps: object
) -> None:
    refresh = _load_script(tmp_path)
    company_facts = _quarterly_company_facts(
        diluted_shares=[10.0, 8.0, 6.0, 7.5],
        diluted_eps=[0.10, unusable_eps, 0.50, 0.67],
    )
    baseline_path, annual_path, facts_path = _write_inputs(
        tmp_path, company_facts=company_facts
    )

    assert refresh.main(_main_args(baseline_path, annual_path, facts_path)) == 0

    latest_ttm = json.loads(baseline_path.read_text())["ttm"][-1]
    assert latest_ttm["diluted_shares"] == pytest.approx(7.5)
    assert latest_ttm["eps"] == pytest.approx(10.0 / 7.5)
    assert latest_ttm["eps_basis"] == (
        "net-income-over-duration-weighted-diluted-shares"
    )
    assert latest_ttm["eps_data_quality"]["status"] == "derived"
    assert latest_ttm["eps_data_quality"][
        "missing_or_invalid_reported_eps_periods"
    ] == ["2024-Q2"]


@pytest.mark.parametrize("invalid_share", [None, 0, "invalid"])
def test_ttm_eps_marks_missing_or_invalid_share_data_unavailable(
    tmp_path: Path, invalid_share: object
) -> None:
    refresh = _load_script(tmp_path)
    company_facts = _quarterly_company_facts(
        diluted_shares=[10.0, invalid_share, 6.0, 7.5]
    )
    baseline_path, annual_path, facts_path = _write_inputs(
        tmp_path, company_facts=company_facts
    )

    assert refresh.main(_main_args(baseline_path, annual_path, facts_path)) == 0

    latest_ttm = json.loads(baseline_path.read_text())["ttm"][-1]
    assert latest_ttm["diluted_shares"] is None
    assert latest_ttm["eps"] is None
    assert latest_ttm["eps_basis"] == "unavailable"
    assert latest_ttm["eps_data_quality"]["status"] == "unavailable"
    assert "2024-Q2" in latest_ttm["eps_data_quality"][
        "missing_or_invalid_diluted_shares_periods"
    ]
    assert {"diluted_shares", "eps"} <= set(latest_ttm["missing_metrics"])


def test_second_refresh_preserves_documented_nested_manual_financial_state(
    tmp_path: Path,
) -> None:
    refresh = _load_script(tmp_path)
    baseline_path, annual_path, facts_path = _write_inputs(tmp_path)
    args = _main_args(baseline_path, annual_path, facts_path)
    assert refresh.main(args) == 0

    first_refresh = json.loads(baseline_path.read_text())
    first_refresh["tag_resolution"]["manual_resolution"] = {
        "revenue": {
            "concept": "RevenueIncludingExciseTax",
            "reason": "Reviewed against the filing footnote",
        }
    }
    first_refresh["data_quality"]["manual_resolution"] = {
        "revenue": {"status": "reviewed", "reviewed_on": "2025-02-02"}
    }
    first_refresh["quarterly_tag_resolution"]["2024-Q4"]["manual_resolution"] = {
        "revenue": {"concept": "QuarterlyRevenueIncludingExciseTax"}
    }
    first_refresh["quarterly_data_quality"]["2024-Q4"]["manual_resolution"] = {
        "revenue": {"status": "reviewed"}
    }
    annual_point = next(
        point
        for point in first_refresh["years"]
        if point["report_date"] == "2024-12-31"
    )
    annual_point["manual_resolution"] = {
        "revenue": {"value": 101.0, "source": "filing footnote"}
    }
    annual_point["review_note"] = "Keep this analyst-authored context."
    baseline_path.write_text(json.dumps(first_refresh, indent=2))

    second_annual = json.loads(annual_path.read_text())
    second_annual["years"][0]["revenue"] = 110.0
    second_annual["tag_resolution"]["revenue"] = (
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    second_annual["data_quality"] = {
        "metrics": {"revenue": {"status": "reported"}}
    }
    annual_path.write_text(json.dumps(second_annual, indent=2))

    assert refresh.main(args) == 0

    second_refresh = json.loads(baseline_path.read_text())
    assert second_refresh["tag_resolution"] == {
        "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "manual_resolution": {
            "revenue": {
                "concept": "RevenueIncludingExciseTax",
                "reason": "Reviewed against the filing footnote",
            }
        },
    }
    assert second_refresh["data_quality"] == {
        "metrics": {"revenue": {"status": "reported"}},
        "manual_resolution": {
            "revenue": {"status": "reviewed", "reviewed_on": "2025-02-02"}
        },
    }
    refreshed_point = next(
        point
        for point in second_refresh["years"]
        if point["report_date"] == "2024-12-31"
    )
    assert refreshed_point["revenue"] == 110.0
    assert refreshed_point["manual_resolution"] == {
        "revenue": {"value": 101.0, "source": "filing footnote"}
    }
    assert refreshed_point["review_note"] == "Keep this analyst-authored context."
    assert second_refresh["quarterly_tag_resolution"]["2024-Q4"][
        "manual_resolution"
    ] == {"revenue": {"concept": "QuarterlyRevenueIncludingExciseTax"}}
    assert second_refresh["quarterly_data_quality"]["2024-Q4"][
        "manual_resolution"
    ] == {"revenue": {"status": "reviewed"}}


def test_refresh_keeps_canonical_file_when_atomic_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    refresh = _load_script(tmp_path)
    baseline_path, annual_path, facts_path = _write_inputs(tmp_path)
    original = baseline_path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(refresh.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        refresh.main(_main_args(baseline_path, annual_path, facts_path))

    assert baseline_path.read_bytes() == original
    assert list(tmp_path.glob(f".{baseline_path.name}.*.tmp")) == []
