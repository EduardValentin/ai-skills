"""Select a downloaded SEC filing from fetch_sec.py's durable index.

Usage:
    <skill-python> -B <scripts-dir>/select_filing.py --index <path> --form 10-K [--rank N]
                     --field path|report-year

Rank 0 is the newest reporting period. Ties are resolved by filing date and
accession, never by local file timestamps.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


class SelectionError(ValueError):
    pass


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("rank must be zero or greater")
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select an indexed SEC filing.")
    parser.add_argument("--index", required=True, help="Path to _filings_index.json")
    parser.add_argument("--form", required=True, help="Exact SEC form, such as 10-K")
    parser.add_argument("--rank", type=_non_negative_int, default=0)
    parser.add_argument(
        "--field",
        required=True,
        choices=("path", "report-year"),
        help="Value to print for the selected filing",
    )
    return parser.parse_args(argv)


def _parse_date(filing: dict, field: str, *, required: bool = True) -> date | None:
    raw = filing.get(field)
    if not raw and not required:
        return None
    if not isinstance(raw, str):
        raise SelectionError(f"filing has no valid {field}")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SelectionError(f"filing has invalid {field}: {raw!r}") from exc


def _date_key(filing: dict) -> tuple[date, date, str]:
    filing_date = _parse_date(filing, "filing_date")
    report_date = _parse_date(filing, "report_date", required=False) or filing_date
    accession = filing.get("accession", "")
    if not isinstance(accession, str):
        raise SelectionError("filing has no valid accession")
    return report_date, filing_date, accession


def select_filing(index_path: Path, *, form: str, rank: int) -> dict:
    data = json.loads(index_path.read_text())
    if not isinstance(data, dict):
        raise SelectionError("filings index root must be an object")
    filings = data.get("filings")
    if not isinstance(filings, list):
        raise SelectionError("filings index must contain a filings list")
    for index, filing in enumerate(filings):
        if not isinstance(filing, dict):
            raise SelectionError(f"filing entry {index} must be an object")
    matches = [filing for filing in filings if filing.get("form") == form]
    matches.sort(key=_date_key, reverse=True)
    if rank >= len(matches):
        raise SelectionError(f"no {form} filing at rank {rank} in {index_path}")
    return matches[rank]


def _filing_path(index_path: Path, filing: dict) -> Path:
    filename = filing.get("filename")
    if not isinstance(filename, str) or not filename:
        raise SelectionError("selected filing has no valid filename")
    index_dir = index_path.parent.resolve()
    filing_path = (index_dir / filename).resolve()
    try:
        filing_path.relative_to(index_dir)
    except ValueError as exc:
        raise SelectionError("selected filing path escapes the index directory") from exc
    if not filing_path.is_file():
        raise SelectionError(f"selected filing does not exist: {filing_path}")
    return filing_path


def _render_field(index_path: Path, filing: dict, field: str) -> str:
    if field == "path":
        return str(_filing_path(index_path, filing))
    report_date = _parse_date(filing, "report_date")
    return str(report_date.year)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    index_path = Path(args.index)
    try:
        filing = select_filing(index_path, form=args.form, rank=args.rank)
        value = _render_field(index_path, filing, args.field)
    except (OSError, json.JSONDecodeError, SelectionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
