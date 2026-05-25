"""Atomically upsert a single ticker entry in tickers.json.

Usage:
    upsert_ticker.py <TICKER> --repo <path>
                     [--field key=value ...]
                     [--list-field key=value ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path


def _coerce(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Atomic tickers.json upsert.")
    p.add_argument("ticker")
    p.add_argument("--repo", required=True)
    p.add_argument("--field", action="append", default=[], help="key=value scalar field")
    p.add_argument(
        "--list-field",
        action="append",
        default=[],
        help="key=value appended to a list field (repeatable)",
    )
    return p.parse_args(argv)


def _parse_kv(items: list[str]) -> list[tuple[str, object]]:
    parsed: list[tuple[str, object]] = []
    for raw in items:
        if "=" not in raw:
            raise SystemExit(f"--field/--list-field must be key=value, got {raw!r}")
        k, v = raw.split("=", 1)
        parsed.append((k.strip(), _coerce(v.strip())))
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    repo = Path(args.repo)
    path = repo / "tickers.json"
    data = json.loads(path.read_text())
    data.setdefault("schema_version", 1)
    tickers = data.setdefault("tickers", {})
    ticker = args.ticker.upper()
    entry = tickers.setdefault(ticker, {})

    for k, v in _parse_kv(args.field):
        entry[k] = v
    for k, v in _parse_kv(args.list_field):
        bucket = entry.setdefault(k, [])
        if v not in bucket:
            bucket.append(v)

    if "first_analyzed" not in entry:
        entry["first_analyzed"] = date.today().isoformat()
    entry["last_updated"] = date.today().isoformat()

    # Atomic write via tempfile + os.replace.
    tmp = tempfile.NamedTemporaryFile(
        "w", dir=str(path.parent), delete=False, suffix=".tmp"
    )
    try:
        json.dump(data, tmp, indent=2, sort_keys=False)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, path)
    print(f"Upserted {ticker} in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
