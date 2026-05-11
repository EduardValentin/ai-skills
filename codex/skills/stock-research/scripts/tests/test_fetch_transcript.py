"""Tests for fetch_transcript.py."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
import responses

import fetch_transcript


@responses.activate
def test_fetch_from_motley_fool(fixtures_dir: Path, tmp_path: Path) -> None:
    html = (fixtures_dir / "transcript_motley_sample.html").read_text()
    # We don't know the exact URL pattern at runtime; the script tries known
    # candidate URLs. Match any motleyfool.com URL with a 200.
    responses.add_passthru = lambda *a, **k: None  # noqa: E731
    responses.add(
        responses.GET,
        url=fetch_transcript.MOTLEY_CANDIDATES_PATTERN.format(
            slug="apple", year=2024, quarter=3
        ),
        body=html,
        status=200,
    )
    out_dir = tmp_path / "calls"
    rc = fetch_transcript.main(
        [
            "AAPL",
            "--quarter", "2024-Q3",
            "--company-slug", "apple",
            "--out", str(out_dir),
        ]
    )
    assert rc == 0
    out_file = out_dir / "2024-Q3.md"
    assert out_file.exists()
    text = out_file.read_text()
    assert text.startswith("---\n")
    assert "ticker: AAPL" in text
    assert "Tim Cook" in text
    assert "85.8 billion" in text


def test_manual_paste_path(monkeypatch, tmp_path: Path) -> None:
    transcript = "## Q3 2024 — manual paste\n\nCEO: Hello world\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(transcript))
    out_dir = tmp_path / "calls"
    rc = fetch_transcript.main(
        ["AAPL", "--quarter", "2024-Q3", "--manual", "--out", str(out_dir)]
    )
    assert rc == 0
    out_file = out_dir / "2024-Q3.md"
    assert out_file.exists()
    text = out_file.read_text()
    assert "Hello world" in text
    assert "ticker: AAPL" in text


@responses.activate
def test_fails_with_clear_error_when_no_source(tmp_path: Path) -> None:
    # No URL registered → motley fetch will 404.
    responses.add(
        responses.GET,
        url=fetch_transcript.MOTLEY_CANDIDATES_PATTERN.format(
            slug="apple", year=2024, quarter=3
        ),
        status=404,
    )
    out_dir = tmp_path / "calls"
    rc = fetch_transcript.main(
        [
            "AAPL",
            "--quarter", "2024-Q3",
            "--company-slug", "apple",
            "--out", str(out_dir),
        ]
    )
    assert rc == 3  # exit code: no source found
