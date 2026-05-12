"""Extract MD&A + supporting sections from a 10-Q HTML.

Usage:
    extract_10q_sections.py <TICKER> --html <path> --quarter YYYY-Qn --out <dir>
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
    ("item_2_mda", re.compile(r"^\s*item\s*2\b\.?\s*management", re.I)),
    ("item_3_market_risk", re.compile(r"^\s*item\s*3\b\.?\s*quantitative", re.I)),
    ("item_4_controls", re.compile(r"^\s*item\s*4\b\.?\s*controls", re.I)),
]


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _walk(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "div", "li"]):
        text = _normalize_text(el.get_text(" "))
        if text:
            out.append(text)
    return out


def _split(blocks: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for text in blocks:
        matched: str | None = None
        for name, pat in SECTION_PATTERNS:
            if pat.match(text):
                matched = name
                break
        if matched is not None:
            current = matched
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(text)
    return sections


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract sections from a 10-Q HTML.")
    p.add_argument("ticker")
    p.add_argument("--html", required=True)
    p.add_argument("--quarter", required=True, help="YYYY-Qn format, e.g., 2024-Q3")
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    html = Path(args.html).read_text()
    soup = BeautifulSoup(html, "lxml")
    sections = _split(_walk(soup))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    artifact_for = {
        "item_2_mda": "10q-mda",
        "item_3_market_risk": "10q-quant-qual-risk",
        "item_4_controls": "10q-controls",
    }
    written: list[str] = []
    for name, paragraphs in sections.items():
        body = "\n\n".join(paragraphs)
        meta = {
            "ticker": args.ticker.upper(),
            "artifact": artifact_for.get(name, "10q-section"),
            "section": name,
            "quarter": args.quarter,
            "schema_version": 1,
        }
        fm_write(out_dir / f"{name}.md", meta, body + "\n")
        written.append(name)

    (out_dir / "_10q_sections_index.json").write_text(
        json.dumps(
            {
                "ticker": args.ticker.upper(),
                "quarter": args.quarter,
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
