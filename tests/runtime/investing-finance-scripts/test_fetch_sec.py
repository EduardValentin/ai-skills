"""Tests for fetch_sec.py CLI."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import responses

@responses.activate
def test_fetch_sec_downloads_and_writes_index(
    fixtures_dir: Path, tmp_path: Path, monkeypatch, fetch_sec, tr
) -> None:
    # Mock ticker resolver: AAPL → CIK 320193
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    # Mock submissions
    responses.add(
        responses.GET,
        "https://data.sec.gov/submissions/CIK0000320193.json",
        body=(fixtures_dir / "submissions_AAPL_sample.json").read_text(),
        status=200,
    )
    # Mock the two filing-document downloads (10-K + one 10-Q after the since cutoff)
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240629.htm",
        body="<html>10-Q body</html>",
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000098/aapl-20240928.htm",
        body="<html>10-K body</html>",
        status=200,
    )

    out_dir = tmp_path / "raw"
    rc = fetch_sec.main(
        ["AAPL", "--forms", "10-K,10-Q", "--since", "2024-01-01", "--out", str(out_dir)]
    )
    assert rc == 0

    index_path = out_dir / "_filings_index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text())
    assert index["ticker"] == "AAPL"
    assert index["schema_version"] == 1
    assert index["cik"] == "0000320193"
    assert len(index["filings"]) == 2
    forms_downloaded = sorted(f["form"] for f in index["filings"])
    assert forms_downloaded == ["10-K", "10-Q"]
    for f in index["filings"]:
        assert (out_dir / f["filename"]).exists()


@responses.activate
def test_fetch_sec_filters_by_since(fixtures_dir, tmp_path, fetch_sec, tr) -> None:
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/submissions/CIK0000320193.json",
        body=(fixtures_dir / "submissions_AAPL_sample.json").read_text(),
        status=200,
    )
    # No mock for old 10-Q; the test will fail with ConnectionError if since is ignored.
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000098/aapl-20240928.htm",
        body="<html>10-K body</html>",
        status=200,
    )
    out_dir = tmp_path / "raw"
    rc = fetch_sec.main(
        ["AAPL", "--forms", "10-K", "--since", "2024-01-01", "--out", str(out_dir)]
    )
    assert rc == 0
    index = json.loads((out_dir / "_filings_index.json").read_text())
    assert len(index["filings"]) == 1


@responses.activate
def test_fetch_sec_returns_2_for_unknown_ticker(
    fixtures_dir, tmp_path, fetch_sec, tr
) -> None:
    # company_tickers.json fixture only contains AAPL/MSFT/AMZN — ZZZZ is unknown.
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    out_dir = tmp_path / "raw"
    rc = fetch_sec.main(["ZZZZ", "--out", str(out_dir)])
    assert rc == 2


def test_list_only_filters_strictly_by_report_date_without_downloading_bodies(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stock_recap_fetch_sec,
) -> None:
    filings = [
        SimpleNamespace(
            accession="0001-equal",
            form="10-Q",
            filing_date="2024-05-15",
            report_date="2024-03-31",
        ),
        SimpleNamespace(
            accession="0002-late-old-period",
            form="10-K",
            filing_date="2025-02-15",
            report_date="2023-12-31",
        ),
        SimpleNamespace(
            accession="0003-delayed-new-period",
            form="10-Q",
            filing_date="2025-01-20",
            report_date="2024-06-30",
        ),
    ]
    list_calls = []

    class FakeSECClient:
        def list_filings(self, **kwargs):
            list_calls.append(kwargs)
            return filings

        def get_filing_html(self, filing):
            pytest.fail(f"list-only requested a filing body for {filing.accession}")

    monkeypatch.setattr(
        stock_recap_fetch_sec,
        "resolve",
        lambda ticker: SimpleNamespace(
            ticker=ticker,
            cik_padded="0000000001",
            name="Example Corp",
        ),
    )
    monkeypatch.setattr(stock_recap_fetch_sec, "SECClient", FakeSECClient)

    rc = stock_recap_fetch_sec.main(
        [
            "EXM",
            "--forms",
            "10-K,10-Q",
            "--report-after",
            "2024-03-31",
            "--list-only",
        ]
    )

    assert rc == 0
    assert list_calls == [
        {
            "cik": "0000000001",
            "forms": {"10-K", "10-Q"},
            "since": None,
        }
    ]
    assert json.loads(capsys.readouterr().out) == {
        "ticker": "EXM",
        "schema_version": 1,
        "cik": "0000000001",
        "name": "Example Corp",
        "filings": [
            {
                "accession": "0003-delayed-new-period",
                "form": "10-Q",
                "filing_date": "2025-01-20",
                "report_date": "2024-06-30",
            }
        ],
    }
