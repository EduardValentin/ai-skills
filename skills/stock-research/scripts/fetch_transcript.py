"""Fetch an earnings call transcript with graceful fallback.

Order:
  1. Try Motley Fool URL pattern (requires --company-slug).
  2. (Future) Try company IR page (skipped — too variable; manual paste covers).
  3. If --manual passed, read transcript text from stdin.

Usage:
    fetch_transcript.py <TICKER> --quarter YYYY-Qn
        [--company-slug <slug>] [--manual] --out <dir>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from _lib.frontmatter import write as fm_write

MOTLEY_CANDIDATES_PATTERN = (
    "https://www.fool.com/earnings/call-transcripts/{year}/q{quarter}/"
    "{slug}-{year}-q{quarter}-earnings-call-transcript/"
)


def _quarter_components(quarter_label: str) -> tuple[int, int]:
    m = re.match(r"^(\d{4})-Q([1-4])$", quarter_label)
    if not m:
        raise ValueError(f"invalid --quarter: {quarter_label}. Expected YYYY-Qn")
    return int(m.group(1)), int(m.group(2))


def _fetch_motley(slug: str, year: int, quarter: int) -> str | None:
    url = MOTLEY_CANDIDATES_PATTERN.format(slug=slug, year=year, quarter=quarter)
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (stock-research)"},
            timeout=30,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    article = soup.find("article") or soup.body
    if not article:
        return None
    parts: list[str] = []
    for el in article.find_all(["h1", "h2", "h3", "h4", "p"]):
        txt = re.sub(r"\s+", " ", el.get_text(" ")).strip()
        if txt:
            tag = el.name
            if tag in ("h1", "h2", "h3", "h4"):
                parts.append("\n## " + txt)
            else:
                parts.append(txt)
    return "\n\n".join(parts).strip() + "\n"


def _read_manual_stdin() -> str:
    print(
        "Paste the transcript content, then send EOF (Ctrl-D on macOS/Linux):",
        file=sys.stderr,
    )
    return sys.stdin.read()


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch earnings call transcript.")
    p.add_argument("ticker")
    p.add_argument("--quarter", required=True, help="YYYY-Qn")
    p.add_argument("--company-slug", help="Used to build the Motley Fool URL")
    p.add_argument("--manual", action="store_true", help="Read transcript from stdin")
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    ticker = args.ticker.upper()
    year, quarter = _quarter_components(args.quarter)
    body: str | None = None
    source = ""
    if not args.manual and args.company_slug:
        body = _fetch_motley(args.company_slug, year, quarter)
        source = "motley_fool" if body else ""
    if body is None and args.manual:
        body = _read_manual_stdin()
        source = "manual_paste"
    if body is None:
        print(
            "error: no transcript source produced content. Re-run with --manual "
            "and paste the transcript, or supply a working --company-slug.",
            file=sys.stderr,
        )
        return 3

    out_dir = Path(args.out)
    meta = {
        "ticker": ticker,
        "artifact": "earnings-call",
        "quarter": args.quarter,
        "source": source,
        "schema_version": 1,
    }
    fm_write(out_dir / f"{args.quarter}.md", meta, body)
    print(f"Wrote {out_dir / (args.quarter + '.md')} (source={source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
