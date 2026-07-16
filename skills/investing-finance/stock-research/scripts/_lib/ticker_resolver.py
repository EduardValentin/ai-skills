"""Resolve a stock ticker to its SEC CIK number.

Uses SEC's company_tickers.json file. Cached locally (24h TTL) to avoid hammering.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from _lib.config import sec_user_agent

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "stock-research"
CACHE_TTL_SECONDS = 24 * 60 * 60


class TickerNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    cik: int
    name: str

    @property
    def cik_padded(self) -> str:
        return f"{self.cik:010d}"


def _load_cached(cache_dir: Path) -> dict | None:
    path = cache_dir / "company_tickers.json"
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > CACHE_TTL_SECONDS:
        return None
    return json.loads(path.read_text())


def _download(cache_dir: Path) -> dict:
    response = requests.get(
        COMPANY_TICKERS_URL,
        headers={"User-Agent": sec_user_agent()},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "company_tickers.json").write_text(json.dumps(data))
    return data


def resolve(ticker: str, *, cache_dir: Path | None = None) -> TickerInfo:
    """Return TickerInfo for the given ticker symbol (case-insensitive)."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    data = _load_cached(cache_dir) or _download(cache_dir)
    needle = ticker.strip().upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == needle:
            return TickerInfo(
                ticker=entry["ticker"],
                cik=int(entry["cik_str"]),
                name=entry["title"],
            )
    raise TickerNotFound(f"Ticker '{ticker}' not found in SEC company_tickers.json")
