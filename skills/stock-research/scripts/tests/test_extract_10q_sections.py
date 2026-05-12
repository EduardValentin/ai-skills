"""Tests for extract_10q_sections.py."""
from __future__ import annotations

import json
from pathlib import Path

import extract_10q_sections


def test_extract_10q_sections(fixtures_dir: Path, tmp_path: Path) -> None:
    src = fixtures_dir / "tenq_sample.html"
    out_dir = tmp_path / "out"
    rc = extract_10q_sections.main(
        ["AAPL", "--html", str(src), "--quarter", "2024-Q3", "--out", str(out_dir)]
    )
    assert rc == 0

    index = json.loads((out_dir / "_10q_sections_index.json").read_text())
    assert index["quarter"] == "2024-Q3"
    assert "item_2_mda" in index["sections"]

    mda = (out_dir / "item_2_mda.md").read_text()
    assert "Net sales" in mda
    assert "Services net sales" in mda
    # Boundary check: MDA should not include Item 3 content
    assert "Item 3" not in mda


def test_extract_10q_section_has_frontmatter(fixtures_dir, tmp_path) -> None:
    src = fixtures_dir / "tenq_sample.html"
    out_dir = tmp_path / "out"
    extract_10q_sections.main(
        ["AAPL", "--html", str(src), "--quarter", "2024-Q3", "--out", str(out_dir)]
    )
    mda = (out_dir / "item_2_mda.md").read_text()
    assert mda.startswith("---\n")
    assert "ticker: AAPL" in mda
    assert "quarter: 2024-Q3" in mda
