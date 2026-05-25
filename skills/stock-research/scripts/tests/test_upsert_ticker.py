"""Tests for upsert_ticker.py."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import upsert_ticker


def _setup_repo(tmp_path: Path, fixtures_dir: Path) -> Path:
    repo = tmp_path / "research"
    repo.mkdir()
    (repo / "tickers.json").write_text(
        (fixtures_dir / "tickers_json_sample.json").read_text()
    )
    return repo


def test_create_new_ticker_entry(tmp_path: Path, fixtures_dir: Path) -> None:
    repo = _setup_repo(tmp_path, fixtures_dir)
    rc = upsert_ticker.main(
        [
            "AAPL",
            "--repo", str(repo),
            "--field", "name=Apple Inc.",
            "--field", "sector=Technology",
            "--field", "gvd_category=quality-growth",
            "--field", "current_status=WATCH",
            "--field", "current_conviction=medium",
            "--field", "thesis_version=v1",
            "--field", "price_at_last_analysis=195.50",
        ]
    )
    assert rc == 0
    data = json.loads((repo / "tickers.json").read_text())
    assert "AAPL" in data["tickers"]
    assert data["tickers"]["AAPL"]["name"] == "Apple Inc."
    assert data["tickers"]["AAPL"]["price_at_last_analysis"] == 195.50
    assert data["tickers"]["AAPL"]["last_updated"] == date.today().isoformat()
    # MSFT is untouched
    assert data["tickers"]["MSFT"]["name"] == "Microsoft Corporation"


def test_update_existing_ticker_entry(tmp_path: Path, fixtures_dir: Path) -> None:
    repo = _setup_repo(tmp_path, fixtures_dir)
    rc = upsert_ticker.main(
        ["MSFT", "--repo", str(repo), "--field", "current_status=BUY"]
    )
    assert rc == 0
    data = json.loads((repo / "tickers.json").read_text())
    assert data["tickers"]["MSFT"]["current_status"] == "BUY"
    assert data["tickers"]["MSFT"]["last_updated"] == date.today().isoformat()
    # Original fields preserved
    assert data["tickers"]["MSFT"]["sector"] == "Technology"


def test_array_field_via_repeated_flag(tmp_path: Path, fixtures_dir: Path) -> None:
    repo = _setup_repo(tmp_path, fixtures_dir)
    rc = upsert_ticker.main(
        [
            "MSFT",
            "--repo", str(repo),
            "--list-field", "active_sell_triggers=Revenue YoY < 5% for 2 quarters",
            "--list-field", "active_sell_triggers=Gross margin < 65%",
        ]
    )
    assert rc == 0
    data = json.loads((repo / "tickers.json").read_text())
    triggers = data["tickers"]["MSFT"]["active_sell_triggers"]
    assert "Revenue YoY < 5% for 2 quarters" in triggers
    assert "Gross margin < 65%" in triggers


def test_write_is_atomic(tmp_path: Path, fixtures_dir: Path, monkeypatch) -> None:
    repo = _setup_repo(tmp_path, fixtures_dir)

    def boom(*a, **k):
        raise RuntimeError("simulated crash mid-rename")

    import os as _os
    monkeypatch.setattr(_os, "replace", boom)
    try:
        upsert_ticker.main(["MSFT", "--repo", str(repo), "--field", "current_status=BUY"])
    except RuntimeError:
        pass
    # Original file is intact (no partial write).
    data = json.loads((repo / "tickers.json").read_text())
    assert data["tickers"]["MSFT"]["current_status"] == "WATCH"
