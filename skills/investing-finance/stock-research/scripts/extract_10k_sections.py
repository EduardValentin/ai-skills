"""Extract the most-referenced sections from a 10-K HTML.

Usage:
    extract_10k_sections.py <TICKER> --html <path-to-10k.html> --year <YYYY> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from _lib.frontmatter import write as fm_write

SECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("item_1_business", re.compile(r"^\s*item\s*1\b\.?\s*business", re.I)),
    ("item_1a_risk_factors", re.compile(r"^\s*item\s*1a\b\.?\s*risk\s*factors", re.I)),
    ("item_7_mda", re.compile(r"^\s*item\s*7\b\.?\s*management", re.I)),
    ("item_7a_market_risk", re.compile(r"^\s*item\s*7a\b\.?\s*", re.I)),
    ("item_8_financials", re.compile(r"^\s*item\s*8\b\.?\s*financial\s*statements", re.I)),
]


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _walk_text_blocks(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Return [(tag-name, normalized-text)] for paragraph-level elements."""
    blocks: list[tuple[str, str]] = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "div", "li"]):
        text = _normalize_text(el.get_text(" "))
        if text:
            blocks.append((el.name, text))
    return blocks


def _split_into_sections(blocks: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Greedy left-to-right scan: a block matching a section header opens that section."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for _, text in blocks:
        matched_section: str | None = None
        for name, pat in SECTION_PATTERNS:
            if pat.match(text):
                matched_section = name
                break
        if matched_section is not None:
            current = matched_section
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(text)
    return sections


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract sections from a 10-K HTML.")
    p.add_argument("ticker")
    p.add_argument("--html", required=True, help="Path to the 10-K HTML file")
    p.add_argument("--year", type=int, required=True, help="Fiscal year of the 10-K")
    p.add_argument("--out", required=True, help="Output directory")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    html = Path(args.html).read_text()
    soup = BeautifulSoup(html, "lxml")
    blocks = _walk_text_blocks(soup)
    sections = _split_into_sections(blocks)
    # Drop the Item 8 marker — we only used it as a stop boundary.
    sections.pop("item_8_financials", None)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    artifact_for = {
        "item_1_business": "business-and-moat",
        "item_1a_risk_factors": "10k-risk-factors",
        "item_7_mda": "10k-mda",
        "item_7a_market_risk": "10k-quant-qual-risk",
    }
    for name, paragraphs in sections.items():
        body = "\n\n".join(paragraphs)
        meta = {
            "ticker": args.ticker.upper(),
            "artifact": artifact_for.get(name, "10k-section"),
            "section": name,
            "fiscal_year": args.year,
            "schema_version": 1,
        }
        fm_write(out_dir / f"{name}.md", meta, body + "\n")
        written.append(name)

    (out_dir / "_10k_sections_index.json").write_text(
        json.dumps(
            {
                "ticker": args.ticker.upper(),
                "year": args.year,
                "sections": written,
                "schema_version": 1,
            },
            indent=2,
        )
    )
    print(f"Extracted {len(written)} sections to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
