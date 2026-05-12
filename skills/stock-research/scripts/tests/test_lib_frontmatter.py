"""Tests for _lib.frontmatter."""
from __future__ import annotations

from pathlib import Path

import pytest

from _lib import frontmatter as fm


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "verdict.md"
    meta = {
        "ticker": "AAPL",
        "artifact": "verdict",
        "session": "initial-research",
        "date": "2026-05-11",
        "schema_version": 1,
    }
    body = "# Verdict\n\nWATCH @ <$170.\n"
    fm.write(target, meta, body)

    loaded_meta, loaded_body = fm.read(target)
    assert loaded_meta == meta
    assert loaded_body == body


def test_read_file_without_frontmatter_returns_empty_meta(tmp_path: Path) -> None:
    target = tmp_path / "plain.md"
    target.write_text("# Plain\n\nNo frontmatter here.\n")
    meta, body = fm.read(target)
    assert meta == {}
    assert body.startswith("# Plain")


def test_write_preserves_key_order(tmp_path: Path) -> None:
    target = tmp_path / "ordered.md"
    meta = {"ticker": "MSFT", "artifact": "thesis", "date": "2026-05-11"}
    fm.write(target, meta, "body")
    text = target.read_text()
    ticker_idx = text.index("ticker:")
    artifact_idx = text.index("artifact:")
    date_idx = text.index("date:")
    assert ticker_idx < artifact_idx < date_idx


def test_read_handles_quoted_strings(tmp_path: Path) -> None:
    target = tmp_path / "quoted.md"
    target.write_text(
        '---\n'
        'ticker: "AAPL"\n'
        'note: "value with: a colon"\n'
        '---\n'
        'body\n'
    )
    meta, body = fm.read(target)
    assert meta["ticker"] == "AAPL"
    assert meta["note"] == "value with: a colon"
    assert body == "body\n"


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deep" / "file.md"
    fm.write(target, {"ticker": "X"}, "body")
    assert target.exists()
