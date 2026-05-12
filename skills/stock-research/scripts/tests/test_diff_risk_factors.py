"""Tests for diff_risk_factors.py."""
from __future__ import annotations

import json
from pathlib import Path

import diff_risk_factors


def test_diff_detects_added_removed_modified(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text(
        "---\nticker: AAPL\nsection: item_1a_risk_factors\n---\n"
        "Macroeconomic conditions affect our results.\n\n"
        "Supply chain concentration in China.\n\n"
        "Foreign exchange volatility.\n"
    )
    b.write_text(
        "---\nticker: AAPL\nsection: item_1a_risk_factors\n---\n"
        "Macroeconomic conditions, including tariffs, affect our results.\n\n"
        "Supply chain concentration in China.\n\n"
        "AI competition from new entrants.\n"
    )
    out = tmp_path / "diff.json"
    rc = diff_risk_factors.main(
        ["--file-a", str(a), "--file-b", str(b), "--ticker", "AAPL", "--out", str(out)]
    )
    assert rc == 0
    data = json.loads(out.read_text())
    assert any("AI competition" in r for r in data["added"])
    assert any("Foreign exchange" in r for r in data["removed"])
    # The macro paragraph changed → modified
    assert any(
        ("tariffs" in m["before"] or "tariffs" in m["after"]) for m in data["modified"]
    )


def test_diff_writes_markdown_summary(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Risk A\n\nRisk B\n")
    b.write_text("Risk A\n\nRisk C\n")
    out_json = tmp_path / "diff.json"
    out_md = tmp_path / "diff.md"
    diff_risk_factors.main(
        [
            "--file-a", str(a), "--file-b", str(b),
            "--ticker", "MSFT",
            "--out", str(out_json),
            "--out-md", str(out_md),
        ]
    )
    md = out_md.read_text()
    assert md.startswith("---\n")
    assert "ticker: MSFT" in md
    assert "artifact: risk-factor-diff" in md
    assert "Risk C" in md  # added
    assert "Risk B" in md  # removed
