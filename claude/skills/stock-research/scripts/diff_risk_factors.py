"""Diff two 10-K Item 1A risk factor sections paragraph-by-paragraph.

Usage:
    diff_risk_factors.py --file-a <path> --file-b <path> --ticker T
                         --out <json> [--out-md <md>]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

from _lib.frontmatter import read as fm_read

MODIFIED_RATIO_MIN = 0.4
MODIFIED_RATIO_MAX = 0.95


def _paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]


def _load_section_paragraphs(path: Path) -> list[str]:
    _, body = fm_read(path)
    return _paragraphs(body)


def _best_match(p: str, candidates: list[str]) -> tuple[int, float] | None:
    best: tuple[int, float] | None = None
    for i, c in enumerate(candidates):
        ratio = difflib.SequenceMatcher(None, p, c).ratio()
        if best is None or ratio > best[1]:
            best = (i, ratio)
    return best


def diff_paragraphs(old: list[str], new: list[str]) -> dict:
    used_new: set[int] = set()
    modified: list[dict] = []
    removed: list[str] = []
    for p in old:
        match = _best_match(p, new)
        if match and MODIFIED_RATIO_MIN <= match[1] <= MODIFIED_RATIO_MAX:
            modified.append({"before": p, "after": new[match[0]], "ratio": match[1]})
            used_new.add(match[0])
        elif match and match[1] > MODIFIED_RATIO_MAX:
            used_new.add(match[0])  # unchanged
        else:
            removed.append(p)
    added = [n for i, n in enumerate(new) if i not in used_new]
    return {"added": added, "removed": removed, "modified": modified}


def to_markdown(ticker: str, diff: dict) -> str:
    lines = [f"# Risk-factor diff — {ticker}", ""]
    lines.append(f"## Added ({len(diff['added'])})\n")
    for p in diff["added"]:
        lines.append(f"- {p}")
    lines.append("")
    lines.append(f"## Removed ({len(diff['removed'])})\n")
    for p in diff["removed"]:
        lines.append(f"- {p}")
    lines.append("")
    lines.append(f"## Modified ({len(diff['modified'])})\n")
    for m in diff["modified"]:
        lines.append(f"- before: {m['before']}")
        lines.append(f"  after:  {m['after']}")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="YoY diff of 10-K Item 1A risk factors.")
    p.add_argument("--file-a", required=True, help="Older year (e.g., 10-K 2023)")
    p.add_argument("--file-b", required=True, help="Newer year (e.g., 10-K 2024)")
    p.add_argument("--ticker", required=True)
    p.add_argument("--out", required=True, help="Output JSON path")
    p.add_argument("--out-md", help="Optional markdown summary path")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    old = _load_section_paragraphs(Path(args.file_a))
    new = _load_section_paragraphs(Path(args.file_b))
    diff = diff_paragraphs(old, new)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ticker": args.ticker.upper(),
        "schema_version": 1,
        **diff,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(to_markdown(args.ticker.upper(), diff))
    print(
        f"Added: {len(diff['added'])} | Removed: {len(diff['removed'])} | "
        f"Modified: {len(diff['modified'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
