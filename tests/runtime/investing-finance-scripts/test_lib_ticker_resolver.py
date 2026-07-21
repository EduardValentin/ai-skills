"""Tests for _lib.ticker_resolver."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

@responses.activate
def test_resolve_aapl(fixtures_dir: Path, tmp_path, tr) -> None:
    body = (fixtures_dir / "company_tickers_sample.json").read_text()
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=body,
        status=200,
        content_type="application/json",
    )
    result = tr.resolve("aapl", cache_dir=tmp_path)
    assert result.cik == 320193
    assert result.cik_padded == "0000320193"
    assert result.ticker == "AAPL"
    assert result.name == "Apple Inc."


@responses.activate
def test_resolve_unknown_raises(fixtures_dir: Path, tmp_path, tr) -> None:
    body = (fixtures_dir / "company_tickers_sample.json").read_text()
    responses.add(responses.GET, tr.COMPANY_TICKERS_URL, body=body, status=200)
    with pytest.raises(tr.TickerNotFound, match="ZZZZ"):
        tr.resolve("ZZZZ", cache_dir=tmp_path)


@responses.activate
def test_resolve_uses_cache_on_second_call(fixtures_dir: Path, tmp_path, tr) -> None:
    body = (fixtures_dir / "company_tickers_sample.json").read_text()
    responses.add(responses.GET, tr.COMPANY_TICKERS_URL, body=body, status=200)
    tr.resolve("AAPL", cache_dir=tmp_path)
    tr.resolve("MSFT", cache_dir=tmp_path)  # second call should hit cache
    assert len(responses.calls) == 1
    assert (tmp_path / "company_tickers.json").exists()


@responses.activate
def test_download_does_not_inherit_ambient_request_settings(
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tr,
) -> None:
    body = (fixtures_dir / "company_tickers_sample.json").read_text()
    responses.add(responses.GET, tr.COMPANY_TICKERS_URL, body=body, status=200)
    session = tr.requests.sessions.Session()
    monkeypatch.setattr(tr.requests, "Session", lambda: session)

    tr.resolve("AAPL", cache_dir=tmp_path)

    assert session.trust_env is False
