"""Tests for extract_10k_sections.py."""
from __future__ import annotations

import json
from pathlib import Path

import extract_10k_sections


def test_extract_sections_from_local_html(fixtures_dir: Path, tmp_path: Path) -> None:
    src = fixtures_dir / "tenk_sample.html"
    out_dir = tmp_path / "out"
    rc = extract_10k_sections.main(
        ["AAPL", "--html", str(src), "--year", "2024", "--out", str(out_dir)]
    )
    assert rc == 0

    index_path = out_dir / "_10k_sections_index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text())
    assert index["ticker"] == "AAPL"
    assert index["year"] == 2024
    assert set(index["sections"]) >= {"item_1_business", "item_1a_risk_factors", "item_7_mda"}

    biz = (out_dir / "item_1_business.md").read_text()
    assert "smartphones" in biz.lower()
    assert "iPhone" in biz

    risks = (out_dir / "item_1a_risk_factors.md").read_text()
    assert "Macroeconomic" in risks
    assert "Supply Chain" in risks

    mda = (out_dir / "item_7_mda.md").read_text()
    assert "Total net sales" in mda
    # Boundary check: MD&A should not include Item 8 content
    assert "Item 8" not in mda


def test_extract_section_files_have_frontmatter(fixtures_dir, tmp_path) -> None:
    src = fixtures_dir / "tenk_sample.html"
    out_dir = tmp_path / "out"
    extract_10k_sections.main(
        ["AAPL", "--html", str(src), "--year", "2024", "--out", str(out_dir)]
    )
    biz = (out_dir / "item_1_business.md").read_text()
    assert biz.startswith("---\n")
    assert "ticker: AAPL" in biz
    assert "artifact: business-and-moat" in biz or "artifact: 10k-section" in biz
