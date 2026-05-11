"""Tests for _lib.sec_client."""
from __future__ import annotations

from pathlib import Path

import pytest
import responses

from _lib import sec_client as sec


@responses.activate
def test_get_submissions_returns_filings_list(fixtures_dir: Path) -> None:
    cik = "0000320193"
    body = (fixtures_dir / "submissions_AAPL_sample.json").read_text()
    responses.add(
        responses.GET,
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        body=body,
        status=200,
        content_type="application/json",
    )
    client = sec.SECClient()
    filings = client.list_filings(cik=cik)
    assert len(filings) == 3
    assert filings[0].accession == "0000320193-24-000123"
    assert filings[0].form == "10-Q"
    assert filings[0].filing_date == "2024-08-02"


@responses.activate
def test_filter_filings_by_form(fixtures_dir: Path) -> None:
    cik = "0000320193"
    body = (fixtures_dir / "submissions_AAPL_sample.json").read_text()
    responses.add(
        responses.GET,
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        body=body,
        status=200,
    )
    client = sec.SECClient()
    tenks = client.list_filings(cik=cik, forms={"10-K"})
    assert len(tenks) == 1
    assert tenks[0].form == "10-K"


@responses.activate
def test_get_user_agent_header_is_sent(fixtures_dir: Path) -> None:
    cik = "0000320193"
    body = (fixtures_dir / "submissions_AAPL_sample.json").read_text()
    responses.add(
        responses.GET,
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        body=body,
        status=200,
    )
    client = sec.SECClient()
    client.list_filings(cik=cik)
    assert "User-Agent" in responses.calls[0].request.headers
    assert "Test Suite" in responses.calls[0].request.headers["User-Agent"]


def test_rate_limiter_blocks_when_over_limit() -> None:
    """RateLimiter sleeps when more than max_per_second calls are attempted."""
    import time
    rl = sec.RateLimiter(max_per_second=5)
    start = time.monotonic()
    for _ in range(10):
        rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.5, f"expected >= 0.5s for 10 calls at 5/sec, got {elapsed}"
