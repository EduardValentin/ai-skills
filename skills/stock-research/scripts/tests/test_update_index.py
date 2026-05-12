"""Tests for update_index.py."""
from __future__ import annotations

import json
from pathlib import Path

import update_index


def _write_tickers(repo: Path) -> None:
    (repo / "tickers.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tickers": {
                    "AAPL": {
                        "name": "Apple Inc.",
                        "sector": "Technology",
                        "gvd_category": "quality-growth",
                        "current_status": "WATCH",
                        "current_conviction": "medium",
                        "buy_zone_low": 160,
                        "buy_zone_high": 175,
                        "current_target_position_pct": 5,
                        "last_updated": "2026-05-11",
                        "active_sell_triggers": ["Revenue < 5%", "GM < 43%"],
                    },
                    "MSFT": {
                        "name": "Microsoft Corporation",
                        "sector": "Technology",
                        "gvd_category": "quality-growth",
                        "current_status": "BUY",
                        "current_conviction": "high",
                        "buy_zone_low": 370,
                        "buy_zone_high": 390,
                        "current_target_position_pct": 7,
                        "last_updated": "2026-04-12",
                        "active_sell_triggers": [],
                    },
                },
            },
            indent=2,
        )
    )


def test_update_index_renders_table(tmp_path: Path) -> None:
    _write_tickers(tmp_path)
    rc = update_index.main(["--repo", str(tmp_path)])
    assert rc == 0
    md = (tmp_path / "INDEX.md").read_text()
    assert "| Ticker |" in md
    assert "| AAPL |" in md
    assert "| MSFT |" in md
    assert "Technology" in md
    # Triggers count rendered
    assert "2" in md  # AAPL has 2 triggers
    # Sorted alphabetically
    assert md.index("| AAPL |") < md.index("| MSFT |")


def test_update_index_handles_empty_repo(tmp_path: Path) -> None:
    (tmp_path / "tickers.json").write_text(
        json.dumps({"schema_version": 1, "tickers": {}})
    )
    rc = update_index.main(["--repo", str(tmp_path)])
    assert rc == 0
    md = (tmp_path / "INDEX.md").read_text()
    assert "No tickers" in md
