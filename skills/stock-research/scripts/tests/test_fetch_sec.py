"""Tests for fetch_sec.py CLI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

import fetch_sec
from _lib import ticker_resolver as tr


@responses.activate
def test_fetch_sec_downloads_and_writes_index(
    fixtures_dir: Path, tmp_path: Path, monkeypatch
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
def test_fetch_sec_filters_by_since(fixtures_dir, tmp_path) -> None:
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
def test_fetch_sec_returns_2_for_unknown_ticker(fixtures_dir, tmp_path) -> None:
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
