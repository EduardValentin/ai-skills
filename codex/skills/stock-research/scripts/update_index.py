"""Regenerate INDEX.md from tickers.json.

Usage:
    update_index.py --repo <path>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

COLUMNS = [
    "Ticker", "Sector", "GVD", "Status", "Conviction",
    "Buy Zone", "Target %", "Last Updated", "Triggers",
]


def _row(ticker: str, entry: dict) -> str:
    buy_zone = ""
    lo, hi = entry.get("buy_zone_low"), entry.get("buy_zone_high")
    if lo is not None and hi is not None:
        buy_zone = f"${lo}–${hi}"
    triggers = entry.get("active_sell_triggers", []) or []
    cells = [
        ticker,
        entry.get("sector", ""),
        entry.get("gvd_category", ""),
        entry.get("current_status", ""),
        entry.get("current_conviction", ""),
        buy_zone,
        f"{entry.get('current_target_position_pct', '')}",
        entry.get("last_updated", ""),
        str(len(triggers)),
    ]
    return "| " + " | ".join(str(c) for c in cells) + " |"


def render(data: dict) -> str:
    tickers = data.get("tickers", {})
    if not tickers:
        return "# Index\n\n_No tickers yet._\n"
    lines = [
        "# Index",
        "",
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "|".join("---" for _ in COLUMNS) + "|",
    ]
    for ticker in sorted(tickers):
        lines.append(_row(ticker, tickers[ticker]))
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Regenerate INDEX.md.")
    p.add_argument("--repo", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    repo = Path(args.repo)
    data = json.loads((repo / "tickers.json").read_text())
    (repo / "INDEX.md").write_text(render(data))
    print(f"Wrote {repo / 'INDEX.md'} ({len(data.get('tickers', {}))} tickers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
