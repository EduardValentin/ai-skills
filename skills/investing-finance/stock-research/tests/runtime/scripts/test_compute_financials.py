"""Tests for compute_financials.py."""
from __future__ import annotations

import json
from pathlib import Path

import responses

import compute_financials
from _lib import ticker_resolver as tr


@responses.activate
def test_compute_financials_writes_full_schema(fixtures_dir: Path, tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        body=(fixtures_dir / "company_facts_AAPL_sample.json").read_text(),
        status=200,
    )

    out_path = tmp_path / "financials.json"
    rc = compute_financials.main(["AAPL", "--years", "3", "--out", str(out_path)])
    assert rc == 0

    data = json.loads(out_path.read_text())
    assert data["ticker"] == "AAPL"
    assert data["schema_version"] == 1
    assert len(data["years"]) == 3

    fy24 = next(y for y in data["years"] if y["fiscal_year"] == 2024)
    assert fy24["revenue"] == 391035000000
    assert fy24["net_income"] == 93736000000
    # Gross margin 180683 / 391035 ≈ 46.2%
    assert round(fy24["gross_margin_pct"], 1) == 46.2
    # Net margin 93736 / 391035 ≈ 24.0%
    assert round(fy24["net_margin_pct"], 1) == 24.0
    # FCF = OCF - capex = 118254 - 9447
    assert fy24["fcf"] == 118254000000 - 9447000000
    assert fy24["diluted_shares"] == 15408095000

    # SBC as % of revenue for FY24
    sbc_pct = fy24["sbc_pct_of_revenue"]
    assert round(sbc_pct, 2) == round(11688000000 / 391035000000 * 100, 2)

    # Balance sheet (only FY24 has cash/LTD in fixture)
    assert fy24["cash"] == 29943000000
    assert fy24["long_term_debt"] == 85750000000
    assert fy24["net_debt"] == 85750000000 - 29943000000

    # FY22 has neither cash nor LTD in fixture → net_debt should be None
    fy22 = next(y for y in data["years"] if y["fiscal_year"] == 2022)
    assert fy22["cash"] is None
    assert fy22["long_term_debt"] is None
    assert fy22["net_debt"] is None

    # Trend pass-fail gate
    assert "trend_gate" in data
    assert data["trend_gate"]["revenue_up_and_right"] in (True, False, "mixed")


@responses.activate
def test_compute_financials_marks_revenue_trend_mixed(
    fixtures_dir, tmp_path
) -> None:
    """FY22 → FY23 down, FY23 → FY24 up → mixed, not 'up_and_right'."""
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        body=(fixtures_dir / "company_facts_AAPL_sample.json").read_text(),
        status=200,
    )
    out_path = tmp_path / "financials.json"
    compute_financials.main(["AAPL", "--years", "3", "--out", str(out_path)])
    data = json.loads(out_path.read_text())
    assert data["trend_gate"]["revenue_up_and_right"] == "mixed"


@responses.activate
def test_compute_financials_returns_2_for_unknown_ticker(fixtures_dir, tmp_path) -> None:
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    out_path = tmp_path / "financials.json"
    rc = compute_financials.main(["ZZZZ", "--out", str(out_path)])
    assert rc == 2


@responses.activate
def test_tag_resolution_recorded(fixtures_dir, tmp_path) -> None:
    """The AAPL fixture uses 'Revenues' for revenue. The output JSON must
    record tag_resolution.revenue == 'Revenues', missing_concepts should
    contain only concepts the fixture truly doesn't include."""
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        body=(fixtures_dir / "company_facts_AAPL_sample.json").read_text(),
        status=200,
    )
    out_path = tmp_path / "financials.json"
    compute_financials.main(["AAPL", "--years", "3", "--out", str(out_path)])
    data = json.loads(out_path.read_text())

    assert "tag_resolution" in data
    assert data["tag_resolution"]["revenue"] == "Revenues"
    assert data["tag_resolution"]["net_income"] == "NetIncomeLoss"
    assert data["tag_resolution"]["cfo"] == "NetCashProvidedByUsedInOperatingActivities"

    # Fixture has all 12 standard concepts, so missing_concepts is empty.
    assert "missing_concepts" in data
    assert data["missing_concepts"] == []


@responses.activate
def test_revenue_fallback_to_asc606_tag(tmp_path) -> None:
    """ServiceNow-style: revenue reported only under
    RevenueFromContractWithCustomerExcludingAssessedTax (post-ASC 606),
    NOT under 'Revenues'. The script should still extract revenue via the
    fallback candidate list."""
    company_tickers = {
        "0": {"cik_str": 1373715, "ticker": "NOW", "title": "ServiceNow, Inc."},
    }
    company_facts = {
        "cik": 1373715,
        "entityName": "ServiceNow, Inc.",
        "facts": {
            "us-gaap": {
                # No "Revenues" concept — only the post-ASC-606 tag
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"end": "2022-12-31", "val": 7245000000, "fy": 2022, "fp": "FY", "form": "10-K"},
                            {"end": "2023-12-31", "val": 8971000000, "fy": 2023, "fp": "FY", "form": "10-K"},
                            {"end": "2024-12-31", "val": 10984000000, "fy": 2024, "fp": "FY", "form": "10-K"},
                        ],
                    },
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"end": "2024-12-31", "val": 1425000000, "fy": 2024, "fp": "FY", "form": "10-K"},
                        ],
                    },
                },
            },
        },
    }
    import json as _json
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=_json.dumps(company_tickers),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0001373715.json",
        body=_json.dumps(company_facts),
        status=200,
    )
    out_path = tmp_path / "financials.json"
    rc = compute_financials.main(["NOW", "--years", "3", "--out", str(out_path)])
    assert rc == 0

    data = json.loads(out_path.read_text())
    # Revenue extracted via fallback
    assert data["tag_resolution"]["revenue"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    fy24 = next(y for y in data["years"] if y["fiscal_year"] == 2024)
    assert fy24["revenue"] == 10984000000
    # Many concepts truly aren't in this minimal fixture; the script should
    # list them in missing_concepts.
    assert "cash" in data["missing_concepts"]
    assert "available_us_gaap_concepts" in data


@responses.activate
def test_revenue_merges_across_candidates(tmp_path) -> None:
    """Company uses 'Revenues' for FY2016 and 'RevenueFromContract...' for
    FY2018-2024. The merged series should cover both windows. tag_resolution
    names the candidate that supplied the most recent fiscal year."""
    company_tickers = {
        "0": {"cik_str": 1373715, "ticker": "NOW", "title": "ServiceNow, Inc."},
    }
    company_facts = {
        "cik": 1373715,
        "entityName": "ServiceNow, Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"end": "2016-12-31", "val": 1391000000, "fy": 2016, "fp": "FY", "form": "10-K"},
                            {"end": "2017-12-31", "val": 1933000000, "fy": 2017, "fp": "FY", "form": "10-K"},
                        ],
                    },
                },
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"end": "2023-12-31", "val": 8971000000, "fy": 2023, "fp": "FY", "form": "10-K"},
                            {"end": "2024-12-31", "val": 10984000000, "fy": 2024, "fp": "FY", "form": "10-K"},
                        ],
                    },
                },
            },
        },
    }
    import json as _json
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=_json.dumps(company_tickers),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0001373715.json",
        body=_json.dumps(company_facts),
        status=200,
    )
    out_path = tmp_path / "financials.json"
    compute_financials.main(["NOW", "--years", "10", "--out", str(out_path)])
    data = json.loads(out_path.read_text())

    # Both candidates contributed; both windows are in the output.
    fys = {y["fiscal_year"]: y["revenue"] for y in data["years"]}
    assert fys[2016] == 1391000000
    assert fys[2017] == 1933000000
    assert fys[2023] == 8971000000
    assert fys[2024] == 10984000000

    # tag_resolution names the candidate that provided the LATEST fiscal year.
    assert data["tag_resolution"]["revenue"] == "RevenueFromContractWithCustomerExcludingAssessedTax"


@responses.activate
def test_missing_concept_listed_with_available_tags(tmp_path) -> None:
    """A company-facts payload with NO recognized revenue concept must end
    up with 'revenue' in missing_concepts AND the available_us_gaap_concepts
    dump must include whatever IS present so the subagent can inspect."""
    company_tickers = {
        "0": {"cik_str": 9999999, "ticker": "ABC", "title": "Weird Corp"},
    }
    company_facts = {
        "cik": 9999999,
        "entityName": "Weird Corp",
        "facts": {
            "us-gaap": {
                "SomeWeirdProprietaryRevenueTag": {
                    "units": {
                        "USD": [
                            {"end": "2024-12-31", "val": 1000000, "fy": 2024, "fp": "FY", "form": "10-K"},
                        ],
                    },
                },
                "Assets": {
                    "units": {"USD": [{"end": "2024-12-31", "val": 5000000, "fy": 2024, "fp": "FY", "form": "10-K"}]},
                },
            },
        },
    }
    import json as _json
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=_json.dumps(company_tickers),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0009999999.json",
        body=_json.dumps(company_facts),
        status=200,
    )
    out_path = tmp_path / "financials.json"
    compute_financials.main(["ABC", "--out", str(out_path)])
    data = json.loads(out_path.read_text())

    assert "revenue" in data["missing_concepts"]
    assert data["tag_resolution"]["revenue"] is None
    # Available concepts list lets the subagent see what IS there
    assert "available_us_gaap_concepts" in data
    assert "SomeWeirdProprietaryRevenueTag" in data["available_us_gaap_concepts"]
    assert "Assets" in data["available_us_gaap_concepts"]


@responses.activate
def test_debt_fallback_uses_debt_instrument_face_amount(tmp_path) -> None:
    company_tickers = {
        "0": {"cik_str": 9999998, "ticker": "DEBT", "title": "Debt Corp"},
    }
    company_facts = {
        "cik": 9999998,
        "entityName": "Debt Corp",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [{"end": "2025-12-31", "val": 5000000000, "fy": 2025, "fp": "FY", "form": "10-K"}]},
                },
                "NetIncomeLoss": {
                    "units": {"USD": [{"end": "2025-12-31", "val": 500000000, "fy": 2025, "fp": "FY", "form": "10-K"}]},
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [{"end": "2025-12-31", "val": 3726000000, "fy": 2025, "fp": "FY", "form": "10-K"}]},
                },
                "DebtInstrumentFaceAmount": {
                    "units": {"USD": [{"end": "2025-12-31", "val": 1500000000, "fy": 2025, "fp": "FY", "form": "10-K"}]},
                },
            },
        },
    }
    import json as _json
    responses.add(responses.GET, tr.COMPANY_TICKERS_URL, body=_json.dumps(company_tickers), status=200)
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0009999998.json",
        body=_json.dumps(company_facts),
        status=200,
    )

    out_path = tmp_path / "financials.json"
    rc = compute_financials.main(["DEBT", "--years", "1", "--out", str(out_path)])
    assert rc == 0

    data = json.loads(out_path.read_text())
    fy25 = next(y for y in data["years"] if y["fiscal_year"] == 2025)
    assert data["tag_resolution"]["long_term_debt"] == "DebtInstrumentFaceAmount"
    assert fy25["long_term_debt"] == 1500000000
    assert fy25["net_debt"] == 1500000000 - 3726000000
    assert data["data_quality"]["metrics"]["long_term_debt"]["status"] == "reported"


@responses.activate
def test_net_debt_is_not_computed_when_debt_input_is_missing(tmp_path) -> None:
    company_tickers = {
        "0": {"cik_str": 9999997, "ticker": "NODEBT", "title": "No Debt Data Corp"},
    }
    company_facts = {
        "cik": 9999997,
        "entityName": "No Debt Data Corp",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [{"end": "2025-12-31", "val": 5000000000, "fy": 2025, "fp": "FY", "form": "10-K"}]},
                },
                "NetIncomeLoss": {
                    "units": {"USD": [{"end": "2025-12-31", "val": 500000000, "fy": 2025, "fp": "FY", "form": "10-K"}]},
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [{"end": "2025-12-31", "val": 3726000000, "fy": 2025, "fp": "FY", "form": "10-K"}]},
                },
            },
        },
    }
    import json as _json
    responses.add(responses.GET, tr.COMPANY_TICKERS_URL, body=_json.dumps(company_tickers), status=200)
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0009999997.json",
        body=_json.dumps(company_facts),
        status=200,
    )

    out_path = tmp_path / "financials.json"
    rc = compute_financials.main(["NODEBT", "--years", "1", "--out", str(out_path)])
    assert rc == 0

    data = json.loads(out_path.read_text())
    fy25 = next(y for y in data["years"] if y["fiscal_year"] == 2025)
    assert "long_term_debt" in data["missing_concepts"]
    assert fy25["cash"] == 3726000000
    assert fy25["long_term_debt"] is None
    assert fy25["net_debt"] is None
    assert data["data_quality"]["metrics"]["long_term_debt"]["status"] == "missing"
    assert data["data_quality"]["derived_metrics"]["net_debt"]["status"] == "unreliable"
