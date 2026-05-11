# `stock-research` Skill — Plan 1: Scripts Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 12 deterministic Python CLI scripts plus shared utilities that fetch and analyze US-equity fundamentals from SEC EDGAR and yfinance, fully test-covered, callable from the future skill orchestrator.

**Architecture:** All scripts live in `claude/skills/stock-research/scripts/`. Five shared utility modules in `_lib/` handle config, SEC HTTP with rate limiting + User-Agent enforcement, ticker→CIK resolution, YAML frontmatter, and a thin yfinance adapter for mockability. Twelve script CLIs sit at the top level. Each script is invokable standalone via `python <script>.py <args>`. Tests use pytest + the `responses` library for SEC HTTP mocking; yfinance is mocked at the adapter level. Fixtures are kept small (snippets of real SEC JSON/HTML).

**Tech Stack:** Python 3.11+, `requests`, `yfinance`, `beautifulsoup4`, `lxml`, `pyyaml`, `pytest`, `responses`.

**Spec reference:** `docs/superpowers/specs/2026-05-11-stock-research-skill-design.md` (commit `e7bb6f6`).

**Scope of this plan:** Scripts only. The skill orchestrator (SKILL.md), per-phase subagent prompts, Codex duplication, and research-repo bootstrap are in **Plan 2** (separate document).

---

## File Structure

```
claude/skills/stock-research/scripts/
├── _lib/
│   ├── __init__.py
│   ├── config.py              # env-var-based config (SR_SEC_USER_AGENT, SR_REPO_PATH, ...)
│   ├── ticker_resolver.py     # ticker → CIK via SEC company_tickers.json
│   ├── sec_client.py          # rate-limited HTTP wrapper for SEC EDGAR
│   ├── frontmatter.py         # YAML frontmatter read/write for .md files
│   └── yf_adapter.py          # thin wrapper around yfinance for mockability
├── fetch_sec.py               # download filings to disk
├── extract_10k_sections.py    # parse Items 1/1A/7/segments
├── extract_10q_sections.py    # parse MD&A + financial summary
├── diff_risk_factors.py       # YoY Item 1A diff
├── compute_financials.py      # XBRL company-facts → financials.json
├── fetch_prices.py            # yfinance OHLCV history
├── fetch_analyst_estimates.py # yfinance analyst consensus
├── compute_pe_band.py         # historical P/E percentile bands
├── compute_reverse_dcf.py     # implied growth at current price
├── fetch_transcript.py        # earnings call transcript hybrid fetch
├── upsert_ticker.py           # atomic tickers.json update
├── update_index.py            # render INDEX.md from tickers.json
├── requirements.txt
├── pytest.ini
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── company_tickers_sample.json
    │   ├── company_facts_AAPL_sample.json
    │   ├── submissions_AAPL_sample.json
    │   ├── tenk_sample.html
    │   ├── tenq_sample.html
    │   ├── transcript_motley_sample.html
    │   └── tickers_json_sample.json
    └── test_*.py              # one per module / script
```

---

## Task 1: Project scaffold

**Files:**
- Create: `claude/skills/stock-research/scripts/requirements.txt`
- Create: `claude/skills/stock-research/scripts/pytest.ini`
- Create: `claude/skills/stock-research/scripts/_lib/__init__.py`
- Create: `claude/skills/stock-research/scripts/tests/__init__.py`
- Create: `claude/skills/stock-research/scripts/tests/conftest.py`
- Create: `claude/skills/stock-research/scripts/tests/fixtures/.gitkeep`

- [ ] **Step 1: Create the directory layout**

```bash
mkdir -p claude/skills/stock-research/scripts/_lib
mkdir -p claude/skills/stock-research/scripts/tests/fixtures
touch claude/skills/stock-research/scripts/_lib/__init__.py
touch claude/skills/stock-research/scripts/tests/__init__.py
touch claude/skills/stock-research/scripts/tests/fixtures/.gitkeep
```

- [ ] **Step 2: Write `requirements.txt`**

File: `claude/skills/stock-research/scripts/requirements.txt`

```
requests>=2.31
yfinance>=0.2.40
beautifulsoup4>=4.12
lxml>=5.0
pyyaml>=6.0
pytest>=8.0
responses>=0.25
```

- [ ] **Step 3: Write `pytest.ini`**

File: `claude/skills/stock-research/scripts/pytest.ini`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra --strict-markers
markers =
    slow: marks tests that take more than a few seconds
```

- [ ] **Step 4: Write `tests/conftest.py`**

File: `claude/skills/stock-research/scripts/tests/conftest.py`

```python
"""Shared pytest fixtures and path setup for stock-research scripts tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def tmp_research_repo(tmp_path: Path) -> Path:
    """Build a minimal investing-research repo layout under tmp_path."""
    (tmp_path / "tickers").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "tickers.json").write_text('{"schema_version": 1, "tickers": {}}\n')
    (tmp_path / "INDEX.md").write_text("# Index\n\n_No tickers yet._\n")
    return tmp_path


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force a known SEC User-Agent in every test so config never reads from the host."""
    monkeypatch.setenv("SR_SEC_USER_AGENT", "Test Suite test@example.com")
    monkeypatch.delenv("SR_REPO_PATH", raising=False)
```

- [ ] **Step 5: Install dependencies and verify pytest runs**

```bash
cd claude/skills/stock-research/scripts
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Expected: `no tests ran in <time>` (no tests yet, but pytest discovers the directory cleanly).

- [ ] **Step 6: Update `.gitignore` to ignore the venv**

Modify: `.gitignore` (worktree root). Append:

```
# Stock-research scripts
claude/skills/stock-research/scripts/.venv/
claude/skills/stock-research/scripts/.pytest_cache/
**/__pycache__/
```

- [ ] **Step 7: Commit**

```bash
git add claude/skills/stock-research/scripts .gitignore
git commit -m "$(cat <<'EOF'
stock-research(scripts): scaffold project layout with pytest

Sets up the scripts/ directory, _lib/ for shared utilities, tests/ with
conftest.py and fixtures/, requirements.txt, and pytest.ini. Tests can now
discover and run (zero tests so far). The autouse isolate_env fixture forces
SR_SEC_USER_AGENT in every test so the suite is hermetic from the host env.
EOF
)"
```

---

## Task 2: `_lib/config.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/_lib/config.py`
- Test: `claude/skills/stock-research/scripts/tests/test_lib_config.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_lib_config.py`

```python
"""Tests for _lib.config."""
from __future__ import annotations

import pytest

from _lib import config as cfg


def test_sec_user_agent_returns_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SR_SEC_USER_AGENT", "Alice alice@example.com")
    assert cfg.sec_user_agent() == "Alice alice@example.com"


def test_sec_user_agent_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SR_SEC_USER_AGENT", raising=False)
    with pytest.raises(cfg.ConfigError, match="SR_SEC_USER_AGENT"):
        cfg.sec_user_agent()


def test_research_repo_path_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SR_REPO_PATH", raising=False)
    assert str(cfg.research_repo_path()).endswith("investing-research")


def test_research_repo_path_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("SR_REPO_PATH", str(tmp_path))
    assert cfg.research_repo_path() == tmp_path


def test_numeric_defaults() -> None:
    assert cfg.discount_rate() == 0.10
    assert cfg.terminal_growth_rate() == 0.025
    assert cfg.years_of_history() == 10


def test_numeric_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SR_DISCOUNT_RATE", "0.12")
    monkeypatch.setenv("SR_TERMINAL_GROWTH", "0.03")
    monkeypatch.setenv("SR_YEARS_OF_HISTORY", "15")
    assert cfg.discount_rate() == 0.12
    assert cfg.terminal_growth_rate() == 0.03
    assert cfg.years_of_history() == 15
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_lib_config.py -v
```

Expected: `ModuleNotFoundError: No module named '_lib.config'` (or test collection error).

- [ ] **Step 3: Implement `_lib/config.py`**

File: `claude/skills/stock-research/scripts/_lib/config.py`

```python
"""Environment-driven config for stock-research scripts.

All settings come from env vars. Required: SR_SEC_USER_AGENT (SEC blocks empty
or default user agents). Optional: SR_REPO_PATH, SR_DISCOUNT_RATE,
SR_TERMINAL_GROWTH, SR_YEARS_OF_HISTORY.
"""
from __future__ import annotations

import os
from pathlib import Path


class ConfigError(RuntimeError):
    pass


DEFAULT_REPO_PATH = Path.home() / "Documents" / "Personal" / "investing-research"


def sec_user_agent() -> str:
    value = os.environ.get("SR_SEC_USER_AGENT")
    if not value:
        raise ConfigError(
            "SR_SEC_USER_AGENT is required. Set it to 'Name email@domain.tld' "
            "so SEC EDGAR accepts the request."
        )
    return value


def research_repo_path() -> Path:
    raw = os.environ.get("SR_REPO_PATH")
    return Path(raw) if raw else DEFAULT_REPO_PATH


def discount_rate() -> float:
    return float(os.environ.get("SR_DISCOUNT_RATE", "0.10"))


def terminal_growth_rate() -> float:
    return float(os.environ.get("SR_TERMINAL_GROWTH", "0.025"))


def years_of_history() -> int:
    return int(os.environ.get("SR_YEARS_OF_HISTORY", "10"))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_lib_config.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/_lib/config.py \
        claude/skills/stock-research/scripts/tests/test_lib_config.py
git commit -m "stock-research(scripts): add _lib.config with env-driven settings"
```

---

## Task 3: `_lib/ticker_resolver.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/_lib/ticker_resolver.py`
- Create: `claude/skills/stock-research/scripts/tests/fixtures/company_tickers_sample.json`
- Test: `claude/skills/stock-research/scripts/tests/test_lib_ticker_resolver.py`

- [ ] **Step 1: Create the fixture**

File: `claude/skills/stock-research/scripts/tests/fixtures/company_tickers_sample.json`

```json
{
  "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
  "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corporation"},
  "2": {"cik_str": 1018724, "ticker": "AMZN", "title": "Amazon.com, Inc."}
}
```

- [ ] **Step 2: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_lib_ticker_resolver.py`

```python
"""Tests for _lib.ticker_resolver."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

from _lib import ticker_resolver as tr


@responses.activate
def test_resolve_aapl(fixtures_dir: Path, tmp_path) -> None:
    body = (fixtures_dir / "company_tickers_sample.json").read_text()
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=body,
        status=200,
        content_type="application/json",
    )
    result = tr.resolve("aapl", cache_dir=tmp_path)
    assert result.cik == 320193
    assert result.cik_padded == "0000320193"
    assert result.ticker == "AAPL"
    assert result.name == "Apple Inc."


@responses.activate
def test_resolve_unknown_raises(fixtures_dir: Path, tmp_path) -> None:
    body = (fixtures_dir / "company_tickers_sample.json").read_text()
    responses.add(responses.GET, tr.COMPANY_TICKERS_URL, body=body, status=200)
    with pytest.raises(tr.TickerNotFound, match="ZZZZ"):
        tr.resolve("ZZZZ", cache_dir=tmp_path)


@responses.activate
def test_resolve_uses_cache_on_second_call(fixtures_dir: Path, tmp_path) -> None:
    body = (fixtures_dir / "company_tickers_sample.json").read_text()
    responses.add(responses.GET, tr.COMPANY_TICKERS_URL, body=body, status=200)
    tr.resolve("AAPL", cache_dir=tmp_path)
    tr.resolve("MSFT", cache_dir=tmp_path)  # second call should hit cache
    assert len(responses.calls) == 1
    assert (tmp_path / "company_tickers.json").exists()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_lib_ticker_resolver.py -v
```

Expected: `ModuleNotFoundError: No module named '_lib.ticker_resolver'`.

- [ ] **Step 4: Implement `_lib/ticker_resolver.py`**

File: `claude/skills/stock-research/scripts/_lib/ticker_resolver.py`

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_lib_ticker_resolver.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add claude/skills/stock-research/scripts/_lib/ticker_resolver.py \
        claude/skills/stock-research/scripts/tests/test_lib_ticker_resolver.py \
        claude/skills/stock-research/scripts/tests/fixtures/company_tickers_sample.json
git commit -m "stock-research(scripts): add ticker→CIK resolver with 24h disk cache"
```

---

## Task 4: `_lib/sec_client.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/_lib/sec_client.py`
- Create: `claude/skills/stock-research/scripts/tests/fixtures/submissions_AAPL_sample.json`
- Test: `claude/skills/stock-research/scripts/tests/test_lib_sec_client.py`

- [ ] **Step 1: Create the fixture**

File: `claude/skills/stock-research/scripts/tests/fixtures/submissions_AAPL_sample.json`

```json
{
  "cik": "320193",
  "name": "Apple Inc.",
  "tickers": ["AAPL"],
  "filings": {
    "recent": {
      "accessionNumber": ["0000320193-24-000123", "0000320193-24-000098", "0000320193-23-000106"],
      "form": ["10-Q", "10-K", "10-Q"],
      "filingDate": ["2024-08-02", "2024-11-01", "2023-08-04"],
      "reportDate": ["2024-06-29", "2024-09-28", "2023-07-01"],
      "primaryDocument": ["aapl-20240629.htm", "aapl-20240928.htm", "aapl-20230701.htm"]
    }
  }
}
```

- [ ] **Step 2: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_lib_sec_client.py`

```python
"""Tests for _lib.sec_client."""
from __future__ import annotations

from pathlib import Path

import pytest
import responses

from _lib import sec_client as sec


@responses.activate
def test_get_submissions_returns_filings_list(fixtures_dir: Path) -> None:
    cik = "0000320193"
    body = (fixtures_dir / "submissions_AAPL_sample.json").read_text()
    responses.add(
        responses.GET,
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        body=body,
        status=200,
        content_type="application/json",
    )
    client = sec.SECClient()
    filings = client.list_filings(cik=cik)
    assert len(filings) == 3
    assert filings[0].accession == "0000320193-24-000123"
    assert filings[0].form == "10-Q"
    assert filings[0].filing_date == "2024-08-02"


@responses.activate
def test_filter_filings_by_form(fixtures_dir: Path) -> None:
    cik = "0000320193"
    body = (fixtures_dir / "submissions_AAPL_sample.json").read_text()
    responses.add(
        responses.GET,
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        body=body,
        status=200,
    )
    client = sec.SECClient()
    tenks = client.list_filings(cik=cik, forms={"10-K"})
    assert len(tenks) == 1
    assert tenks[0].form == "10-K"


@responses.activate
def test_get_user_agent_header_is_sent(fixtures_dir: Path) -> None:
    cik = "0000320193"
    body = (fixtures_dir / "submissions_AAPL_sample.json").read_text()
    responses.add(
        responses.GET,
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        body=body,
        status=200,
    )
    client = sec.SECClient()
    client.list_filings(cik=cik)
    assert "User-Agent" in responses.calls[0].request.headers
    assert "Test Suite" in responses.calls[0].request.headers["User-Agent"]


def test_rate_limiter_blocks_when_over_limit() -> None:
    """RateLimiter sleeps when more than max_per_second calls are attempted."""
    import time
    rl = sec.RateLimiter(max_per_second=5)
    start = time.monotonic()
    for _ in range(10):
        rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.5, f"expected >= 0.5s for 10 calls at 5/sec, got {elapsed}"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_lib_sec_client.py -v
```

Expected: `ModuleNotFoundError: No module named '_lib.sec_client'`.

- [ ] **Step 4: Implement `_lib/sec_client.py`**

File: `claude/skills/stock-research/scripts/_lib/sec_client.py`

```python
"""HTTP client for SEC EDGAR with rate limiting and required User-Agent.

SEC asks <=10 req/sec and a non-empty User-Agent. Failure to comply causes
403s. This client enforces both.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Iterable

import requests

from _lib.config import sec_user_agent

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVES_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_clean}/{filename}"
)


@dataclass(frozen=True)
class FilingRef:
    accession: str
    form: str
    filing_date: str
    report_date: str
    primary_document: str
    cik: str

    @property
    def accession_clean(self) -> str:
        return self.accession.replace("-", "")

    def primary_doc_url(self) -> str:
        return ARCHIVES_URL.format(
            cik_int=int(self.cik),
            accession_clean=self.accession_clean,
            filename=self.primary_document,
        )


class RateLimiter:
    """Sliding window: max_per_second calls per rolling 1-second window."""

    def __init__(self, max_per_second: int = 8) -> None:
        self.max_per_second = max_per_second
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > 1.0:
            self._calls.popleft()
        if len(self._calls) >= self.max_per_second:
            sleep_for = 1.0 - (now - self._calls[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
            self.acquire()
            return
        self._calls.append(time.monotonic())


class SECClient:
    """Thin HTTP wrapper for SEC EDGAR endpoints."""

    def __init__(self, *, rate_limit: int = 8, timeout: int = 30) -> None:
        self._rl = RateLimiter(rate_limit)
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": sec_user_agent()})

    def _get(self, url: str) -> requests.Response:
        self._rl.acquire()
        r = self._session.get(url, timeout=self._timeout)
        r.raise_for_status()
        return r

    def get_submissions(self, cik: str) -> dict:
        return self._get(SUBMISSIONS_URL.format(cik=cik)).json()

    def get_company_facts(self, cik: str) -> dict:
        return self._get(COMPANY_FACTS_URL.format(cik=cik)).json()

    def get_filing_html(self, filing: FilingRef) -> str:
        return self._get(filing.primary_doc_url()).text

    def list_filings(
        self,
        *,
        cik: str,
        forms: Iterable[str] | None = None,
        since: str | None = None,
    ) -> list[FilingRef]:
        data = self.get_submissions(cik)
        recent = data["filings"]["recent"]
        filings: list[FilingRef] = []
        wanted = {f.upper() for f in forms} if forms else None
        for i, accession in enumerate(recent["accessionNumber"]):
            form = recent["form"][i]
            if wanted and form.upper() not in wanted:
                continue
            filing_date = recent["filingDate"][i]
            if since and filing_date < since:
                continue
            filings.append(
                FilingRef(
                    accession=accession,
                    form=form,
                    filing_date=filing_date,
                    report_date=recent["reportDate"][i],
                    primary_document=recent["primaryDocument"][i],
                    cik=cik,
                )
            )
        return filings
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_lib_sec_client.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add claude/skills/stock-research/scripts/_lib/sec_client.py \
        claude/skills/stock-research/scripts/tests/test_lib_sec_client.py \
        claude/skills/stock-research/scripts/tests/fixtures/submissions_AAPL_sample.json
git commit -m "stock-research(scripts): add SEC EDGAR client with rate limit + User-Agent"
```

---

## Task 5: `_lib/frontmatter.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/_lib/frontmatter.py`
- Test: `claude/skills/stock-research/scripts/tests/test_lib_frontmatter.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_lib_frontmatter.py`

```python
"""Tests for _lib.frontmatter."""
from __future__ import annotations

from pathlib import Path

import pytest

from _lib import frontmatter as fm


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "verdict.md"
    meta = {
        "ticker": "AAPL",
        "artifact": "verdict",
        "session": "initial-research",
        "date": "2026-05-11",
        "schema_version": 1,
    }
    body = "# Verdict\n\nWATCH @ <$170.\n"
    fm.write(target, meta, body)

    loaded_meta, loaded_body = fm.read(target)
    assert loaded_meta == meta
    assert loaded_body == body


def test_read_file_without_frontmatter_returns_empty_meta(tmp_path: Path) -> None:
    target = tmp_path / "plain.md"
    target.write_text("# Plain\n\nNo frontmatter here.\n")
    meta, body = fm.read(target)
    assert meta == {}
    assert body.startswith("# Plain")


def test_write_preserves_key_order(tmp_path: Path) -> None:
    target = tmp_path / "ordered.md"
    meta = {"ticker": "MSFT", "artifact": "thesis", "date": "2026-05-11"}
    fm.write(target, meta, "body")
    text = target.read_text()
    ticker_idx = text.index("ticker:")
    artifact_idx = text.index("artifact:")
    date_idx = text.index("date:")
    assert ticker_idx < artifact_idx < date_idx


def test_read_handles_quoted_strings(tmp_path: Path) -> None:
    target = tmp_path / "quoted.md"
    target.write_text(
        '---\n'
        'ticker: "AAPL"\n'
        'note: "value with: a colon"\n'
        '---\n'
        'body\n'
    )
    meta, body = fm.read(target)
    assert meta["ticker"] == "AAPL"
    assert meta["note"] == "value with: a colon"
    assert body == "body\n"


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deep" / "file.md"
    fm.write(target, {"ticker": "X"}, "body")
    assert target.exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_lib_frontmatter.py -v
```

Expected: `ModuleNotFoundError: No module named '_lib.frontmatter'`.

- [ ] **Step 3: Implement `_lib/frontmatter.py`**

File: `claude/skills/stock-research/scripts/_lib/frontmatter.py`

```python
"""YAML frontmatter for .md artifacts.

Frontmatter is a YAML block fenced by `---` lines at the top of the file.
We preserve insertion order so the artifact reads predictably.
"""
from __future__ import annotations

from pathlib import Path

import yaml

FENCE = "---"


def write(path: Path, meta: dict, body: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip()
    content = f"{FENCE}\n{yaml_text}\n{FENCE}\n{body}"
    path.write_text(content)


def read(path: Path) -> tuple[dict, str]:
    path = Path(path)
    text = path.read_text()
    if not text.startswith(FENCE + "\n") and not text.startswith(FENCE + "\r\n"):
        return {}, text
    end_idx = text.find(f"\n{FENCE}\n", len(FENCE))
    if end_idx == -1:
        return {}, text
    yaml_block = text[len(FENCE) + 1 : end_idx]
    body_start = end_idx + len(FENCE) + 2
    meta = yaml.safe_load(yaml_block) or {}
    return meta, text[body_start:]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_lib_frontmatter.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/_lib/frontmatter.py \
        claude/skills/stock-research/scripts/tests/test_lib_frontmatter.py
git commit -m "stock-research(scripts): add YAML frontmatter read/write helper"
```

---

## Task 6: `_lib/yf_adapter.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/_lib/yf_adapter.py`
- Test: `claude/skills/stock-research/scripts/tests/test_lib_yf_adapter.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_lib_yf_adapter.py`

```python
"""Tests for _lib.yf_adapter (mocked at the yfinance.Ticker level)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from _lib import yf_adapter as yfa


@patch("_lib.yf_adapter.yf.Ticker")
def test_get_history_returns_dataframe(ticker_cls) -> None:
    df = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )
    ticker = MagicMock()
    ticker.history.return_value = df
    ticker_cls.return_value = ticker
    result = yfa.get_history("AAPL", period="1y")
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    ticker.history.assert_called_once_with(period="1y", auto_adjust=False)


@patch("_lib.yf_adapter.yf.Ticker")
def test_get_analyst_price_target_returns_dict(ticker_cls) -> None:
    ticker = MagicMock()
    ticker.info = {
        "targetLowPrice": 150.0,
        "targetMeanPrice": 200.0,
        "targetHighPrice": 280.0,
        "numberOfAnalystOpinions": 35,
    }
    ticker_cls.return_value = ticker
    result = yfa.get_analyst_price_target("AAPL")
    assert result == {
        "low": 150.0,
        "mean": 200.0,
        "high": 280.0,
        "num_analysts": 35,
    }


@patch("_lib.yf_adapter.yf.Ticker")
def test_get_recommendations_counts(ticker_cls) -> None:
    df = pd.DataFrame(
        {
            "period": ["0m"],
            "strongBuy": [10],
            "buy": [15],
            "hold": [8],
            "sell": [2],
            "strongSell": [0],
        }
    )
    ticker = MagicMock()
    ticker.recommendations = df
    ticker_cls.return_value = ticker
    result = yfa.get_recommendations("AAPL")
    assert result == {
        "strong_buy": 10,
        "buy": 15,
        "hold": 8,
        "sell": 2,
        "strong_sell": 0,
    }


@patch("_lib.yf_adapter.yf.Ticker")
def test_get_history_raises_on_empty(ticker_cls) -> None:
    ticker = MagicMock()
    ticker.history.return_value = pd.DataFrame()
    ticker_cls.return_value = ticker
    with pytest.raises(yfa.NoDataError, match="empty"):
        yfa.get_history("ZZZZ", period="1y")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_lib_yf_adapter.py -v
```

Expected: `ModuleNotFoundError: No module named '_lib.yf_adapter'`.

- [ ] **Step 3: Implement `_lib/yf_adapter.py`**

File: `claude/skills/stock-research/scripts/_lib/yf_adapter.py`

```python
"""Thin adapter around yfinance so the scripts can be tested with mocks.

yfinance's API is rich and scraping-driven; we normalize what we use into
small dict shapes downstream code can rely on.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf


class NoDataError(RuntimeError):
    pass


def get_history(ticker: str, *, period: str = "10y") -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if df is None or df.empty:
        raise NoDataError(f"yfinance returned empty history for {ticker}")
    return df


def get_dividends(ticker: str) -> pd.Series:
    return yf.Ticker(ticker).dividends


def get_splits(ticker: str) -> pd.Series:
    return yf.Ticker(ticker).splits


def get_info(ticker: str) -> dict:
    return dict(yf.Ticker(ticker).info or {})


def get_analyst_price_target(ticker: str) -> dict:
    info = get_info(ticker)
    return {
        "low": info.get("targetLowPrice"),
        "mean": info.get("targetMeanPrice"),
        "high": info.get("targetHighPrice"),
        "num_analysts": info.get("numberOfAnalystOpinions"),
    }


def get_recommendations(ticker: str) -> dict:
    df = yf.Ticker(ticker).recommendations
    if df is None or df.empty:
        return {"strong_buy": 0, "buy": 0, "hold": 0, "sell": 0, "strong_sell": 0}
    row = df.iloc[0]
    return {
        "strong_buy": int(row.get("strongBuy", 0)),
        "buy": int(row.get("buy", 0)),
        "hold": int(row.get("hold", 0)),
        "sell": int(row.get("sell", 0)),
        "strong_sell": int(row.get("strongSell", 0)),
    }


def get_earnings_estimate(ticker: str) -> dict:
    df = yf.Ticker(ticker).earnings_estimate
    return df.to_dict() if df is not None and not df.empty else {}


def get_revenue_estimate(ticker: str) -> dict:
    df = yf.Ticker(ticker).revenue_estimate
    return df.to_dict() if df is not None and not df.empty else {}


def get_eps_trend(ticker: str) -> dict:
    df = yf.Ticker(ticker).eps_trend
    return df.to_dict() if df is not None and not df.empty else {}


def get_growth_estimates(ticker: str) -> dict:
    df = yf.Ticker(ticker).growth_estimates
    return df.to_dict() if df is not None and not df.empty else {}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_lib_yf_adapter.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/_lib/yf_adapter.py \
        claude/skills/stock-research/scripts/tests/test_lib_yf_adapter.py
git commit -m "stock-research(scripts): add yfinance adapter for mockable market data"
```

---

## Task 7: `fetch_sec.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/fetch_sec.py`
- Test: `claude/skills/stock-research/scripts/tests/test_fetch_sec.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_fetch_sec.py`

```python
"""Tests for fetch_sec.py CLI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

import fetch_sec
from _lib import ticker_resolver as tr


@responses.activate
def test_fetch_sec_downloads_and_writes_index(
    fixtures_dir: Path, tmp_path: Path, monkeypatch
) -> None:
    # Mock ticker resolver: AAPL → CIK 320193
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    # Mock submissions
    responses.add(
        responses.GET,
        "https://data.sec.gov/submissions/CIK0000320193.json",
        body=(fixtures_dir / "submissions_AAPL_sample.json").read_text(),
        status=200,
    )
    # Mock the two filing-document downloads (10-K + one 10-Q after the since cutoff)
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240629.htm",
        body="<html>10-Q body</html>",
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000098/aapl-20240928.htm",
        body="<html>10-K body</html>",
        status=200,
    )

    out_dir = tmp_path / "raw"
    rc = fetch_sec.main(
        ["AAPL", "--forms", "10-K,10-Q", "--since", "2024-01-01", "--out", str(out_dir)]
    )
    assert rc == 0

    index_path = out_dir / "_filings_index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text())
    assert index["ticker"] == "AAPL"
    assert index["cik"] == "0000320193"
    assert len(index["filings"]) == 2
    forms_downloaded = sorted(f["form"] for f in index["filings"])
    assert forms_downloaded == ["10-K", "10-Q"]
    for f in index["filings"]:
        assert (out_dir / f["filename"]).exists()


@responses.activate
def test_fetch_sec_filters_by_since(fixtures_dir, tmp_path) -> None:
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/submissions/CIK0000320193.json",
        body=(fixtures_dir / "submissions_AAPL_sample.json").read_text(),
        status=200,
    )
    # No mock for old 10-Q; the test will fail with ConnectionError if since is ignored.
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019324000098/aapl-20240928.htm",
        body="<html>10-K body</html>",
        status=200,
    )
    out_dir = tmp_path / "raw"
    rc = fetch_sec.main(
        ["AAPL", "--forms", "10-K", "--since", "2024-01-01", "--out", str(out_dir)]
    )
    assert rc == 0
    index = json.loads((out_dir / "_filings_index.json").read_text())
    assert len(index["filings"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_fetch_sec.py -v
```

Expected: `ModuleNotFoundError: No module named 'fetch_sec'`.

- [ ] **Step 3: Implement `fetch_sec.py`**

File: `claude/skills/stock-research/scripts/fetch_sec.py`

```python
"""Download SEC filings for a ticker into a directory.

Usage:
    fetch_sec.py <TICKER> [--forms 10-K,10-Q,8-K] [--since YYYY-MM-DD] --out <dir>

Writes one file per filing plus _filings_index.json listing what was fetched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _lib.sec_client import SECClient
from _lib.ticker_resolver import resolve, TickerNotFound


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download SEC filings for a ticker.")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g., AAPL)")
    parser.add_argument(
        "--forms",
        default="10-K,10-Q,8-K",
        help="Comma-separated SEC form types to fetch (default: 10-K,10-Q,8-K)",
    )
    parser.add_argument("--since", help="Earliest filing date (YYYY-MM-DD)")
    parser.add_argument("--out", required=True, help="Output directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        info = resolve(args.ticker)
    except TickerNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    client = SECClient()
    forms = {f.strip() for f in args.forms.split(",") if f.strip()}
    filings = client.list_filings(cik=info.cik_padded, forms=forms, since=args.since)

    index = {
        "ticker": info.ticker,
        "cik": info.cik_padded,
        "name": info.name,
        "filings": [],
    }
    for f in filings:
        body = client.get_filing_html(f)
        filename = f"{f.accession}-{f.form.replace('/', '_')}-{f.filing_date}.html"
        (out_dir / filename).write_text(body)
        index["filings"].append(
            {
                "accession": f.accession,
                "form": f.form,
                "filing_date": f.filing_date,
                "report_date": f.report_date,
                "filename": filename,
            }
        )

    (out_dir / "_filings_index.json").write_text(json.dumps(index, indent=2))
    print(f"Fetched {len(filings)} filings for {info.ticker} into {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fetch_sec.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/fetch_sec.py \
        claude/skills/stock-research/scripts/tests/test_fetch_sec.py
git commit -m "stock-research(scripts): add fetch_sec.py to download SEC filings"
```

---

## Task 8: `compute_financials.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/compute_financials.py`
- Create: `claude/skills/stock-research/scripts/tests/fixtures/company_facts_AAPL_sample.json`
- Test: `claude/skills/stock-research/scripts/tests/test_compute_financials.py`

- [ ] **Step 1: Create the fixture**

File: `claude/skills/stock-research/scripts/tests/fixtures/company_facts_AAPL_sample.json`

```json
{
  "cik": 320193,
  "entityName": "Apple Inc.",
  "facts": {
    "us-gaap": {
      "Revenues": {
        "label": "Revenues",
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 394328000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 383285000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 391035000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "NetIncomeLoss": {
        "label": "Net Income (Loss)",
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 99803000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 96995000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 93736000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "GrossProfit": {
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 170782000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 169148000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 180683000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "OperatingIncomeLoss": {
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 119437000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 114301000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 123216000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "NetCashProvidedByUsedInOperatingActivities": {
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 122151000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 110543000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 118254000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "PaymentsToAcquirePropertyPlantAndEquipment": {
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 10708000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 10959000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 9447000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "CashAndCashEquivalentsAtCarryingValue": {
        "units": {
          "USD": [
            {"end": "2024-09-28", "val": 29943000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "LongTermDebt": {
        "units": {
          "USD": [
            {"end": "2024-09-28", "val": 85750000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "WeightedAverageNumberOfDilutedSharesOutstanding": {
        "units": {
          "shares": [
            {"end": "2022-09-24", "val": 16215963000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 15812547000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 15408095000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "ShareBasedCompensation": {
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 9038000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 10833000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 11688000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "PaymentsForRepurchaseOfCommonStock": {
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 89402000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 77550000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 94949000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "PaymentsOfDividends": {
        "units": {
          "USD": [
            {"end": "2022-09-24", "val": 14841000000, "fy": 2022, "fp": "FY", "form": "10-K"},
            {"end": "2023-09-30", "val": 15025000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2024-09-28", "val": 15234000000, "fy": 2024, "fp": "FY", "form": "10-K"}
          ]
        }
      }
    }
  }
}
```

- [ ] **Step 2: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_compute_financials.py`

```python
"""Tests for compute_financials.py."""
from __future__ import annotations

import json
from pathlib import Path

import responses

import compute_financials
from _lib import ticker_resolver as tr


@responses.activate
def test_compute_financials_writes_full_schema(fixtures_dir: Path, tmp_path: Path) -> None:
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        body=(fixtures_dir / "company_facts_AAPL_sample.json").read_text(),
        status=200,
    )

    out_path = tmp_path / "financials.json"
    rc = compute_financials.main(["AAPL", "--years", "3", "--out", str(out_path)])
    assert rc == 0

    data = json.loads(out_path.read_text())
    assert data["ticker"] == "AAPL"
    assert data["schema_version"] == 1
    assert len(data["years"]) == 3

    fy24 = next(y for y in data["years"] if y["fiscal_year"] == 2024)
    assert fy24["revenue"] == 391035000000
    assert fy24["net_income"] == 93736000000
    # Gross margin 180683 / 391035 ≈ 46.2%
    assert round(fy24["gross_margin_pct"], 1) == 46.2
    # Net margin 93736 / 391035 ≈ 24.0%
    assert round(fy24["net_margin_pct"], 1) == 24.0
    # FCF = OCF - capex = 118254 - 9447
    assert fy24["fcf"] == 118254000000 - 9447000000
    assert fy24["diluted_shares"] == 15408095000

    # SBC as % of revenue for FY24
    sbc_pct = fy24["sbc_pct_of_revenue"]
    assert round(sbc_pct, 2) == round(11688000000 / 391035000000 * 100, 2)

    # Trend pass-fail gate
    assert "trend_gate" in data
    assert data["trend_gate"]["revenue_up_and_right"] in (True, False, "mixed")


@responses.activate
def test_compute_financials_marks_revenue_trend_mixed(
    fixtures_dir, tmp_path
) -> None:
    """FY22 → FY23 down, FY23 → FY24 up → mixed, not 'up_and_right'."""
    responses.add(
        responses.GET,
        tr.COMPANY_TICKERS_URL,
        body=(fixtures_dir / "company_tickers_sample.json").read_text(),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        body=(fixtures_dir / "company_facts_AAPL_sample.json").read_text(),
        status=200,
    )
    out_path = tmp_path / "financials.json"
    compute_financials.main(["AAPL", "--years", "3", "--out", str(out_path)])
    data = json.loads(out_path.read_text())
    assert data["trend_gate"]["revenue_up_and_right"] == "mixed"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_compute_financials.py -v
```

Expected: `ModuleNotFoundError: No module named 'compute_financials'`.

- [ ] **Step 4: Implement `compute_financials.py`**

File: `claude/skills/stock-research/scripts/compute_financials.py`

```python
"""Pull XBRL company-facts → financials.json with TTM trends and margins.

Usage:
    compute_financials.py <TICKER> [--years N] --out <path>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from _lib.sec_client import SECClient
from _lib.ticker_resolver import resolve, TickerNotFound

# us-gaap concepts we care about. (concept, unit)
CONCEPTS: dict[str, tuple[str, str]] = {
    "revenue": ("Revenues", "USD"),
    "net_income": ("NetIncomeLoss", "USD"),
    "gross_profit": ("GrossProfit", "USD"),
    "operating_income": ("OperatingIncomeLoss", "USD"),
    "cfo": ("NetCashProvidedByUsedInOperatingActivities", "USD"),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "USD"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "USD"),
    "long_term_debt": ("LongTermDebt", "USD"),
    "diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding", "shares"),
    "sbc": ("ShareBasedCompensation", "USD"),
    "buybacks": ("PaymentsForRepurchaseOfCommonStock", "USD"),
    "dividends_paid": ("PaymentsOfDividends", "USD"),
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute financials.json from XBRL.")
    p.add_argument("ticker")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def _pick_fy_values(
    facts: dict, concept: str, unit: str, years: int
) -> dict[int, float]:
    """Return {fiscal_year: value} for FY 10-K facts under the concept."""
    out: dict[int, float] = {}
    section = facts.get("us-gaap", {}).get(concept)
    if not section:
        return out
    for item in section.get("units", {}).get(unit, []):
        if item.get("fp") == "FY" and item.get("form") == "10-K":
            out[int(item["fy"])] = float(item["val"])
    # Keep the most recent N fiscal years
    keep = sorted(out)[-years:]
    return {fy: out[fy] for fy in keep}


def _safe_div(num: float | None, denom: float | None) -> float | None:
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def _pct(num: float | None, denom: float | None) -> float | None:
    r = _safe_div(num, denom)
    return None if r is None else r * 100.0


def _build_year(fy: int, raw: dict[str, dict[int, float]]) -> dict:
    revenue = raw["revenue"].get(fy)
    net_income = raw["net_income"].get(fy)
    gross_profit = raw["gross_profit"].get(fy)
    op_income = raw["operating_income"].get(fy)
    cfo = raw["cfo"].get(fy)
    capex = raw["capex"].get(fy)
    diluted_shares = raw["diluted_shares"].get(fy)
    sbc = raw["sbc"].get(fy)
    buybacks = raw["buybacks"].get(fy)
    dividends_paid = raw["dividends_paid"].get(fy)
    fcf = (cfo - capex) if (cfo is not None and capex is not None) else None
    return {
        "fiscal_year": fy,
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": op_income,
        "net_income": net_income,
        "cfo": cfo,
        "capex": capex,
        "fcf": fcf,
        "gross_margin_pct": _pct(gross_profit, revenue),
        "operating_margin_pct": _pct(op_income, revenue),
        "net_margin_pct": _pct(net_income, revenue),
        "fcf_margin_pct": _pct(fcf, revenue),
        "diluted_shares": diluted_shares,
        "eps": _safe_div(net_income, diluted_shares),
        "fcf_per_share": _safe_div(fcf, diluted_shares),
        "sbc": sbc,
        "sbc_pct_of_revenue": _pct(sbc, revenue),
        "buybacks": buybacks,
        "dividends_paid": dividends_paid,
    }


def _trend_gate(years: list[dict], key: str) -> bool | str:
    vals = [y[key] for y in years if y.get(key) is not None]
    if len(vals) < 3:
        return "insufficient_data"
    ups = sum(1 for a, b in zip(vals, vals[1:]) if b > a)
    downs = sum(1 for a, b in zip(vals, vals[1:]) if b < a)
    if ups == len(vals) - 1:
        return True
    if downs == len(vals) - 1:
        return False
    return "mixed"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        info = resolve(args.ticker)
    except TickerNotFound as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    client = SECClient()
    facts = client.get_company_facts(info.cik_padded).get("facts", {})

    raw = {
        key: _pick_fy_values(facts, concept, unit, args.years)
        for key, (concept, unit) in CONCEPTS.items()
    }
    all_fys: set[int] = set()
    for series in raw.values():
        all_fys.update(series.keys())
    fys = sorted(all_fys)[-args.years :]
    years = [_build_year(fy, raw) for fy in fys]

    result = {
        "ticker": info.ticker,
        "cik": info.cik_padded,
        "name": info.name,
        "schema_version": 1,
        "generated_at": date.today().isoformat(),
        "years": years,
        "trend_gate": {
            "revenue_up_and_right": _trend_gate(years, "revenue"),
            "net_income_up_and_right": _trend_gate(years, "net_income"),
            "fcf_up_and_right": _trend_gate(years, "fcf"),
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(f"Wrote {args.out} ({len(years)} fiscal years)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_compute_financials.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add claude/skills/stock-research/scripts/compute_financials.py \
        claude/skills/stock-research/scripts/tests/test_compute_financials.py \
        claude/skills/stock-research/scripts/tests/fixtures/company_facts_AAPL_sample.json
git commit -m "stock-research(scripts): add compute_financials.py for XBRL → JSON"
```

---

## Task 9: `extract_10k_sections.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/extract_10k_sections.py`
- Create: `claude/skills/stock-research/scripts/tests/fixtures/tenk_sample.html`
- Test: `claude/skills/stock-research/scripts/tests/test_extract_10k_sections.py`

- [ ] **Step 1: Create the fixture (a minimal 10-K-shaped HTML)**

File: `claude/skills/stock-research/scripts/tests/fixtures/tenk_sample.html`

```html
<html>
<body>
<p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p>
<p>FORM 10-K</p>

<h2>Item 1. Business</h2>
<p>The Company designs, manufactures, and markets smartphones, personal
computers, tablets, wearables and accessories, and sells a variety of
related services. The Company's products include iPhone, Mac, iPad, and
Wearables, Home and Accessories.</p>
<p>The Company sells its products and resells third-party products in most
of its major markets directly to consumers and small and mid-sized
businesses through its retail and online stores and its direct sales force.</p>

<h2>Item 1A. Risk Factors</h2>
<p>The Company's business, reputation, results of operations and financial
condition can be affected by a number of factors, whether currently known
or unknown, including those described below.</p>
<p><b>Macroeconomic Conditions.</b> Macroeconomic conditions, including
inflation, interest rates, and tariffs, can materially adversely affect the
Company.</p>
<p><b>Supply Chain Concentration.</b> Substantially all of the Company's
manufacturing is performed in whole or in part by outsourcing partners
located primarily in China mainland.</p>

<h2>Item 7. Management's Discussion and Analysis</h2>
<p>The following discussion should be read in conjunction with the
consolidated financial statements and accompanying notes.</p>
<p>Total net sales in 2024 increased 2% from 2023, driven primarily by
higher Services and iPad net sales, partially offset by lower iPhone net
sales.</p>

<h2>Item 8. Financial Statements</h2>
<p>The financial statements appear in the following pages.</p>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_extract_10k_sections.py`

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_extract_10k_sections.py -v
```

Expected: `ModuleNotFoundError: No module named 'extract_10k_sections'`.

- [ ] **Step 4: Implement `extract_10k_sections.py`**

File: `claude/skills/stock-research/scripts/extract_10k_sections.py`

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_extract_10k_sections.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add claude/skills/stock-research/scripts/extract_10k_sections.py \
        claude/skills/stock-research/scripts/tests/test_extract_10k_sections.py \
        claude/skills/stock-research/scripts/tests/fixtures/tenk_sample.html
git commit -m "stock-research(scripts): add extract_10k_sections.py (Items 1/1A/7/7A)"
```

---

## Task 10: `extract_10q_sections.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/extract_10q_sections.py`
- Create: `claude/skills/stock-research/scripts/tests/fixtures/tenq_sample.html`
- Test: `claude/skills/stock-research/scripts/tests/test_extract_10q_sections.py`

- [ ] **Step 1: Create the fixture**

File: `claude/skills/stock-research/scripts/tests/fixtures/tenq_sample.html`

```html
<html>
<body>
<p>FORM 10-Q</p>

<h2>Item 2. Management's Discussion and Analysis</h2>
<p>Net sales for the third quarter of 2024 were $85.8 billion, an increase
of $4.0 billion, or 5%, from the same period in 2023.</p>
<p>Services net sales increased 14% during Q3 2024, driven by higher
revenue from advertising, the App Store, and subscription services.</p>

<h2>Item 3. Quantitative and Qualitative Disclosures About Market Risk</h2>
<p>There have been no material changes in market risk from the disclosures
provided in the most recent 10-K.</p>

<h2>Item 4. Controls and Procedures</h2>
<p>Management evaluated the Company's disclosure controls and procedures.</p>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_extract_10q_sections.py`

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_extract_10q_sections.py -v
```

Expected: `ModuleNotFoundError: No module named 'extract_10q_sections'`.

- [ ] **Step 4: Implement `extract_10q_sections.py`**

File: `claude/skills/stock-research/scripts/extract_10q_sections.py`

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_extract_10q_sections.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add claude/skills/stock-research/scripts/extract_10q_sections.py \
        claude/skills/stock-research/scripts/tests/test_extract_10q_sections.py \
        claude/skills/stock-research/scripts/tests/fixtures/tenq_sample.html
git commit -m "stock-research(scripts): add extract_10q_sections.py for MD&A"
```

---

## Task 11: `diff_risk_factors.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/diff_risk_factors.py`
- Test: `claude/skills/stock-research/scripts/tests/test_diff_risk_factors.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_diff_risk_factors.py`

```python
"""Tests for diff_risk_factors.py."""
from __future__ import annotations

import json
from pathlib import Path

import diff_risk_factors


def test_diff_detects_added_removed_modified(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text(
        "---\nticker: AAPL\nsection: item_1a_risk_factors\n---\n"
        "Macroeconomic conditions affect our results.\n\n"
        "Supply chain concentration in China.\n\n"
        "Foreign exchange volatility.\n"
    )
    b.write_text(
        "---\nticker: AAPL\nsection: item_1a_risk_factors\n---\n"
        "Macroeconomic conditions, including tariffs, affect our results.\n\n"
        "Supply chain concentration in China.\n\n"
        "AI competition from new entrants.\n"
    )
    out = tmp_path / "diff.json"
    rc = diff_risk_factors.main(
        ["--file-a", str(a), "--file-b", str(b), "--ticker", "AAPL", "--out", str(out)]
    )
    assert rc == 0
    data = json.loads(out.read_text())
    assert any("AI competition" in r for r in data["added"])
    assert any("Foreign exchange" in r for r in data["removed"])
    # The macro paragraph changed → modified
    assert any(
        ("tariffs" in m["before"] or "tariffs" in m["after"]) for m in data["modified"]
    )


def test_diff_writes_markdown_summary(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("Risk A\n\nRisk B\n")
    b.write_text("Risk A\n\nRisk C\n")
    out_json = tmp_path / "diff.json"
    out_md = tmp_path / "diff.md"
    diff_risk_factors.main(
        [
            "--file-a", str(a), "--file-b", str(b),
            "--ticker", "MSFT",
            "--out", str(out_json),
            "--out-md", str(out_md),
        ]
    )
    md = out_md.read_text()
    assert "Risk C" in md  # added
    assert "Risk B" in md  # removed
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_diff_risk_factors.py -v
```

Expected: `ModuleNotFoundError: No module named 'diff_risk_factors'`.

- [ ] **Step 3: Implement `diff_risk_factors.py`**

File: `claude/skills/stock-research/scripts/diff_risk_factors.py`

```python
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

WORD_OVERLAP_THRESHOLD = 0.5
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
    # Cross-check unchanged for added: any "added" that was a near-dup of an
    # unchanged item should drop out.
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_diff_risk_factors.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/diff_risk_factors.py \
        claude/skills/stock-research/scripts/tests/test_diff_risk_factors.py
git commit -m "stock-research(scripts): add diff_risk_factors.py for YoY Item 1A diff"
```

---

## Task 12: `fetch_prices.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/fetch_prices.py`
- Test: `claude/skills/stock-research/scripts/tests/test_fetch_prices.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_fetch_prices.py`

```python
"""Tests for fetch_prices.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import fetch_prices


def _hist_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.5, 102.5],
            "Volume": [1_000_000, 1_100_000],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )


def _div_series() -> pd.Series:
    return pd.Series(
        [0.25, 0.25],
        index=pd.to_datetime(["2025-08-15", "2025-11-15"]),
        name="Dividends",
    )


def _split_series() -> pd.Series:
    return pd.Series([], dtype=float, name="Stock Splits")


@patch("fetch_prices.yfa.get_splits", return_value=_split_series())
@patch("fetch_prices.yfa.get_dividends", return_value=_div_series())
@patch("fetch_prices.yfa.get_history", return_value=_hist_df())
def test_fetch_prices_writes_three_files(_h, _d, _s, tmp_path: Path) -> None:
    out_dir = tmp_path / "raw"
    rc = fetch_prices.main(["AAPL", "--years", "10", "--out", str(out_dir)])
    assert rc == 0

    prices = json.loads((out_dir / "prices.json").read_text())
    assert prices["ticker"] == "AAPL"
    assert prices["schema_version"] == 1
    assert len(prices["bars"]) == 2
    assert prices["bars"][0]["close"] == 101.5

    divs = json.loads((out_dir / "dividends.json").read_text())
    assert len(divs["dividends"]) == 2
    assert divs["dividends"][0]["amount"] == 0.25

    splits = json.loads((out_dir / "splits.json").read_text())
    assert splits["splits"] == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_fetch_prices.py -v
```

Expected: `ModuleNotFoundError: No module named 'fetch_prices'`.

- [ ] **Step 3: Implement `fetch_prices.py`**

File: `claude/skills/stock-research/scripts/fetch_prices.py`

```python
"""Fetch OHLCV + dividends + splits from yfinance.

Usage:
    fetch_prices.py <TICKER> [--years N] --out <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _lib import yf_adapter as yfa


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch price history via yfinance.")
    p.add_argument("ticker")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    ticker = args.ticker.upper()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    period = f"{args.years}y"
    hist = yfa.get_history(ticker, period=period)
    bars = [
        {
            "date": str(idx.date()),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        }
        for idx, row in hist.iterrows()
    ]
    (out_dir / "prices.json").write_text(
        json.dumps(
            {"ticker": ticker, "schema_version": 1, "bars": bars}, indent=2
        )
    )

    divs = yfa.get_dividends(ticker)
    div_records = [
        {"date": str(idx.date()), "amount": float(amt)} for idx, amt in divs.items()
    ]
    (out_dir / "dividends.json").write_text(
        json.dumps(
            {"ticker": ticker, "schema_version": 1, "dividends": div_records},
            indent=2,
        )
    )

    splits = yfa.get_splits(ticker)
    split_records = [
        {"date": str(idx.date()), "ratio": float(r)} for idx, r in splits.items()
    ]
    (out_dir / "splits.json").write_text(
        json.dumps(
            {"ticker": ticker, "schema_version": 1, "splits": split_records},
            indent=2,
        )
    )
    print(f"Wrote prices/dividends/splits for {ticker} to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fetch_prices.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/fetch_prices.py \
        claude/skills/stock-research/scripts/tests/test_fetch_prices.py
git commit -m "stock-research(scripts): add fetch_prices.py via yfinance"
```

---

## Task 13: `fetch_analyst_estimates.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/fetch_analyst_estimates.py`
- Test: `claude/skills/stock-research/scripts/tests/test_fetch_analyst_estimates.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_fetch_analyst_estimates.py`

```python
"""Tests for fetch_analyst_estimates.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import fetch_analyst_estimates


@patch("fetch_analyst_estimates.yfa.get_growth_estimates", return_value={"ticker": {"0y": 0.08}})
@patch("fetch_analyst_estimates.yfa.get_eps_trend", return_value={"0q": {"now": 6.1}})
@patch("fetch_analyst_estimates.yfa.get_revenue_estimate", return_value={"0q": {"avg": 1.0e11}})
@patch("fetch_analyst_estimates.yfa.get_earnings_estimate", return_value={"0q": {"avg": 6.0}})
@patch(
    "fetch_analyst_estimates.yfa.get_recommendations",
    return_value={"strong_buy": 10, "buy": 15, "hold": 8, "sell": 2, "strong_sell": 0},
)
@patch(
    "fetch_analyst_estimates.yfa.get_analyst_price_target",
    return_value={"low": 150.0, "mean": 200.0, "high": 280.0, "num_analysts": 35},
)
def test_fetch_writes_market_expectations_json(*_mocks, tmp_path: Path) -> None:
    out_dir = tmp_path / "raw"
    rc = fetch_analyst_estimates.main(["AAPL", "--out", str(out_dir)])
    assert rc == 0
    data = json.loads((out_dir / "market-expectations.json").read_text())
    assert data["ticker"] == "AAPL"
    assert data["schema_version"] == 1
    assert data["price_target"]["mean"] == 200.0
    assert data["ratings"]["buy"] == 15
    assert "eps_trend" in data
    assert "revenue_estimate" in data
    assert "growth_estimates" in data
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_fetch_analyst_estimates.py -v
```

Expected: `ModuleNotFoundError: No module named 'fetch_analyst_estimates'`.

- [ ] **Step 3: Implement `fetch_analyst_estimates.py`**

File: `claude/skills/stock-research/scripts/fetch_analyst_estimates.py`

```python
"""Fetch analyst consensus from yfinance into market-expectations.json.

Usage:
    fetch_analyst_estimates.py <TICKER> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from _lib import yf_adapter as yfa


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch analyst consensus.")
    p.add_argument("ticker")
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    ticker = args.ticker.upper()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "ticker": ticker,
        "schema_version": 1,
        "fetched_at": date.today().isoformat(),
        "price_target": yfa.get_analyst_price_target(ticker),
        "ratings": yfa.get_recommendations(ticker),
        "earnings_estimate": yfa.get_earnings_estimate(ticker),
        "revenue_estimate": yfa.get_revenue_estimate(ticker),
        "eps_trend": yfa.get_eps_trend(ticker),
        "growth_estimates": yfa.get_growth_estimates(ticker),
    }
    (out_dir / "market-expectations.json").write_text(json.dumps(payload, indent=2))
    print(f"Wrote market-expectations.json for {ticker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fetch_analyst_estimates.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/fetch_analyst_estimates.py \
        claude/skills/stock-research/scripts/tests/test_fetch_analyst_estimates.py
git commit -m "stock-research(scripts): add fetch_analyst_estimates.py via yfinance"
```

---

## Task 14: `compute_pe_band.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/compute_pe_band.py`
- Test: `claude/skills/stock-research/scripts/tests/test_compute_pe_band.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_compute_pe_band.py`

```python
"""Tests for compute_pe_band.py."""
from __future__ import annotations

import json
from pathlib import Path

import compute_pe_band


def _make_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    prices = {
        "ticker": "AAPL",
        "schema_version": 1,
        "bars": [
            {"date": "2022-12-30", "open": 130.0, "high": 132.0, "low": 129.0,
             "close": 130.0, "volume": 1},
            {"date": "2023-12-29", "open": 192.0, "high": 193.0, "low": 191.0,
             "close": 192.0, "volume": 1},
            {"date": "2024-12-31", "open": 250.0, "high": 252.0, "low": 248.0,
             "close": 250.0, "volume": 1},
        ],
    }
    financials = {
        "ticker": "AAPL",
        "schema_version": 1,
        "years": [
            {"fiscal_year": 2022, "eps": 6.11},
            {"fiscal_year": 2023, "eps": 6.13},
            {"fiscal_year": 2024, "eps": 6.08},
        ],
    }
    pp = tmp_path / "prices.json"
    fp = tmp_path / "financials.json"
    op = tmp_path / "pe_band.json"
    pp.write_text(json.dumps(prices))
    fp.write_text(json.dumps(financials))
    return pp, fp, op


def test_pe_band_basic(tmp_path: Path) -> None:
    pp, fp, op = _make_inputs(tmp_path)
    rc = compute_pe_band.main(
        ["--prices", str(pp), "--financials", str(fp), "--out", str(op)]
    )
    assert rc == 0
    band = json.loads(op.read_text())
    assert band["ticker"] == "AAPL"
    assert band["schema_version"] == 1
    assert "current_pe" in band
    assert "percentile_25" in band
    assert "percentile_50" in band
    assert "percentile_75" in band
    assert "current_percentile" in band
    assert 0 <= band["current_percentile"] <= 100
    # PE TTM at 2024 close = 250 / 6.08 ≈ 41.1
    assert round(band["current_pe"], 1) == round(250 / 6.08, 1)


def test_pe_band_skips_when_eps_zero(tmp_path: Path) -> None:
    prices = {
        "ticker": "X",
        "schema_version": 1,
        "bars": [
            {"date": "2024-12-31", "open": 10, "high": 10, "low": 10,
             "close": 10, "volume": 1},
        ],
    }
    financials = {
        "ticker": "X",
        "schema_version": 1,
        "years": [{"fiscal_year": 2024, "eps": 0.0}],
    }
    pp = tmp_path / "p.json"
    fp = tmp_path / "f.json"
    op = tmp_path / "o.json"
    pp.write_text(json.dumps(prices))
    fp.write_text(json.dumps(financials))
    rc = compute_pe_band.main(
        ["--prices", str(pp), "--financials", str(fp), "--out", str(op)]
    )
    assert rc == 0
    band = json.loads(op.read_text())
    assert band["current_pe"] is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_compute_pe_band.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `compute_pe_band.py`**

File: `claude/skills/stock-research/scripts/compute_pe_band.py`

```python
"""Compute historical P/E and percentile bands from prices + financials.

Joins daily closes against annual EPS (latest FY's EPS applied forward until
next FY release) and computes 25/50/75 percentile bands plus current
percentile.

Usage:
    compute_pe_band.py --prices <path> --financials <path> --out <path>
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from bisect import bisect_right
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="P/E percentile bands.")
    p.add_argument("--prices", required=True)
    p.add_argument("--financials", required=True)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def _eps_for_date(date_str: str, fy_eps_sorted: list[tuple[int, float]]) -> float | None:
    year = int(date_str[:4])
    keys = [fy for fy, _ in fy_eps_sorted]
    idx = bisect_right(keys, year) - 1
    if idx < 0:
        return None
    eps = fy_eps_sorted[idx][1]
    return eps if eps and eps > 0 else None


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _percentile_rank(sorted_vals: list[float], value: float) -> float:
    if not sorted_vals:
        return float("nan")
    idx = bisect_right(sorted_vals, value)
    return idx / len(sorted_vals) * 100.0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    prices = json.loads(Path(args.prices).read_text())
    financials = json.loads(Path(args.financials).read_text())
    fy_eps = sorted(
        [(y["fiscal_year"], y.get("eps")) for y in financials.get("years", []) if y.get("eps") is not None],
        key=lambda x: x[0],
    )

    pes: list[float] = []
    for bar in prices.get("bars", []):
        eps = _eps_for_date(bar["date"], fy_eps)
        if eps is None:
            continue
        pe = bar["close"] / eps
        if 0 < pe < 1000:
            pes.append(pe)
    pes_sorted = sorted(pes)

    current_pe: float | None = None
    if prices.get("bars"):
        latest = prices["bars"][-1]
        latest_eps = _eps_for_date(latest["date"], fy_eps)
        if latest_eps is not None:
            current_pe = latest["close"] / latest_eps

    out = {
        "ticker": prices.get("ticker"),
        "schema_version": 1,
        "n_observations": len(pes_sorted),
        "percentile_25": _percentile(pes_sorted, 0.25) if pes_sorted else None,
        "percentile_50": statistics.median(pes_sorted) if pes_sorted else None,
        "percentile_75": _percentile(pes_sorted, 0.75) if pes_sorted else None,
        "min": pes_sorted[0] if pes_sorted else None,
        "max": pes_sorted[-1] if pes_sorted else None,
        "current_pe": current_pe,
        "current_percentile": (
            _percentile_rank(pes_sorted, current_pe) if current_pe is not None else None
        ),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out} (n={out['n_observations']}, current P/E={current_pe})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_compute_pe_band.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/compute_pe_band.py \
        claude/skills/stock-research/scripts/tests/test_compute_pe_band.py
git commit -m "stock-research(scripts): add compute_pe_band.py for historical P/E"
```

---

## Task 15: `compute_reverse_dcf.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/compute_reverse_dcf.py`
- Test: `claude/skills/stock-research/scripts/tests/test_compute_reverse_dcf.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_compute_reverse_dcf.py`

```python
"""Tests for compute_reverse_dcf.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import compute_reverse_dcf


def test_present_value_known_inputs() -> None:
    # FCF grows 10% for 10 yrs, terminal 2.5%, discount 10%. Should NPV cleanly.
    pv = compute_reverse_dcf.present_value(
        fcf0=1000.0,
        growth=0.10,
        years=10,
        terminal_growth=0.025,
        discount_rate=0.10,
    )
    assert pv > 0
    # Sanity: PV should be > 10 * FCF0 (multi-year compounding + terminal).
    assert pv > 10_000


def test_solve_implied_growth_recovers_input() -> None:
    target_growth = 0.12
    fcf0 = 1.0
    shares = 1.0
    price = compute_reverse_dcf.present_value(
        fcf0=fcf0,
        growth=target_growth,
        years=10,
        terminal_growth=0.025,
        discount_rate=0.10,
    ) / shares
    implied = compute_reverse_dcf.solve_implied_growth(
        target_pv=price * shares,
        fcf0=fcf0,
        years=10,
        terminal_growth=0.025,
        discount_rate=0.10,
    )
    assert abs(implied - target_growth) < 1e-4


def test_cli_writes_output_with_implied_growth(tmp_path: Path) -> None:
    financials = {
        "ticker": "AAPL",
        "schema_version": 1,
        "years": [
            {"fiscal_year": 2024, "fcf": 1.0e11, "diluted_shares": 1.5e10}
        ],
    }
    fp = tmp_path / "financials.json"
    fp.write_text(json.dumps(financials))
    op = tmp_path / "reverse_dcf.json"
    rc = compute_reverse_dcf.main(
        [
            "--financials", str(fp),
            "--price", "200",
            "--discount-rate", "0.10",
            "--terminal-growth", "0.025",
            "--out", str(op),
        ]
    )
    assert rc == 0
    data = json.loads(op.read_text())
    assert "implied_growth_pct" in data
    assert data["price"] == 200
    assert data["schema_version"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_compute_reverse_dcf.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `compute_reverse_dcf.py`**

File: `claude/skills/stock-research/scripts/compute_reverse_dcf.py`

```python
"""Reverse DCF: solve for the FCF growth rate implied by today's price.

Two-stage DCF: ``years`` of high-growth at rate g, then Gordon-growth
terminal at ``terminal_growth``. Discount everything back at
``discount_rate``.

Usage:
    compute_reverse_dcf.py --financials <path> --price <p>
                           [--discount-rate 0.10] [--terminal-growth 0.025]
                           [--years 10] --out <path>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def present_value(
    *,
    fcf0: float,
    growth: float,
    years: int,
    terminal_growth: float,
    discount_rate: float,
) -> float:
    if discount_rate <= terminal_growth:
        raise ValueError("discount_rate must be > terminal_growth")
    pv = 0.0
    fcf = fcf0
    for t in range(1, years + 1):
        fcf = fcf * (1 + growth)
        pv += fcf / ((1 + discount_rate) ** t)
    terminal_fcf = fcf * (1 + terminal_growth)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth)
    pv += terminal_value / ((1 + discount_rate) ** years)
    return pv


def solve_implied_growth(
    *,
    target_pv: float,
    fcf0: float,
    years: int,
    terminal_growth: float,
    discount_rate: float,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    lo, hi = -0.10, 0.50
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        pv = present_value(
            fcf0=fcf0,
            growth=mid,
            years=years,
            terminal_growth=terminal_growth,
            discount_rate=discount_rate,
        )
        if abs(pv - target_pv) < tol * max(target_pv, 1.0):
            return mid
        if pv < target_pv:
            lo = mid
        else:
            hi = mid
    return mid


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reverse DCF.")
    p.add_argument("--financials", required=True)
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--discount-rate", type=float, default=0.10)
    p.add_argument("--terminal-growth", type=float, default=0.025)
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def _latest_fcf_and_shares(financials: dict) -> tuple[float, float]:
    years = sorted(
        [y for y in financials.get("years", []) if y.get("fcf") and y.get("diluted_shares")],
        key=lambda y: y["fiscal_year"],
    )
    if not years:
        raise ValueError("financials.json has no year with both fcf and diluted_shares")
    last = years[-1]
    return float(last["fcf"]), float(last["diluted_shares"])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    financials = json.loads(Path(args.financials).read_text())
    fcf0, shares = _latest_fcf_and_shares(financials)
    target_pv = args.price * shares
    g = solve_implied_growth(
        target_pv=target_pv,
        fcf0=fcf0,
        years=args.years,
        terminal_growth=args.terminal_growth,
        discount_rate=args.discount_rate,
    )
    payload = {
        "ticker": financials.get("ticker"),
        "schema_version": 1,
        "price": args.price,
        "fcf_starting": fcf0,
        "diluted_shares": shares,
        "discount_rate": args.discount_rate,
        "terminal_growth": args.terminal_growth,
        "years": args.years,
        "implied_growth_pct": round(g * 100, 4),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(f"Implied FCF growth at price ${args.price}: {g * 100:.2f}% / yr for {args.years} yr")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_compute_reverse_dcf.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/compute_reverse_dcf.py \
        claude/skills/stock-research/scripts/tests/test_compute_reverse_dcf.py
git commit -m "stock-research(scripts): add compute_reverse_dcf.py (bisection solver)"
```

---

## Task 16: `fetch_transcript.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/fetch_transcript.py`
- Create: `claude/skills/stock-research/scripts/tests/fixtures/transcript_motley_sample.html`
- Test: `claude/skills/stock-research/scripts/tests/test_fetch_transcript.py`

- [ ] **Step 1: Create the fixture**

File: `claude/skills/stock-research/scripts/tests/fixtures/transcript_motley_sample.html`

```html
<html>
<body>
<article class="article-body">
<h1>Apple (AAPL) Q3 2024 Earnings Call Transcript</h1>
<h3>Prepared Remarks</h3>
<p><strong>Tim Cook -- Chief Executive Officer</strong></p>
<p>Good afternoon, everyone, and thanks for joining us. Today we are
reporting a June quarter revenue record of $85.8 billion.</p>
<p><strong>Luca Maestri -- Chief Financial Officer</strong></p>
<p>Thank you, Tim. Our services business set a new all-time revenue record.</p>
<h3>Questions & Answers</h3>
<p><strong>Analyst:</strong> Can you talk about iPad demand?</p>
<p><strong>Tim Cook:</strong> iPad had a great quarter, up 24% year over year.</p>
</article>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_fetch_transcript.py`

```python
"""Tests for fetch_transcript.py."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
import responses

import fetch_transcript


@responses.activate
def test_fetch_from_motley_fool(fixtures_dir: Path, tmp_path: Path) -> None:
    html = (fixtures_dir / "transcript_motley_sample.html").read_text()
    # We don't know the exact URL pattern at runtime; the script tries known
    # candidate URLs. Match any motleyfool.com URL with a 200.
    responses.add_passthru = lambda *a, **k: None  # noqa: E731
    responses.add(
        responses.GET,
        url=fetch_transcript.MOTLEY_CANDIDATES_PATTERN.format(
            slug="apple", year=2024, quarter=3
        ),
        body=html,
        status=200,
    )
    out_dir = tmp_path / "calls"
    rc = fetch_transcript.main(
        [
            "AAPL",
            "--quarter", "2024-Q3",
            "--company-slug", "apple",
            "--out", str(out_dir),
        ]
    )
    assert rc == 0
    out_file = out_dir / "2024-Q3.md"
    assert out_file.exists()
    text = out_file.read_text()
    assert text.startswith("---\n")
    assert "ticker: AAPL" in text
    assert "Tim Cook" in text
    assert "85.8 billion" in text


def test_manual_paste_path(monkeypatch, tmp_path: Path) -> None:
    transcript = "## Q3 2024 — manual paste\n\nCEO: Hello world\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(transcript))
    out_dir = tmp_path / "calls"
    rc = fetch_transcript.main(
        ["AAPL", "--quarter", "2024-Q3", "--manual", "--out", str(out_dir)]
    )
    assert rc == 0
    out_file = out_dir / "2024-Q3.md"
    assert out_file.exists()
    text = out_file.read_text()
    assert "Hello world" in text
    assert "ticker: AAPL" in text


@responses.activate
def test_fails_with_clear_error_when_no_source(tmp_path: Path) -> None:
    # No URL registered → motley fetch will 404.
    responses.add(
        responses.GET,
        url=fetch_transcript.MOTLEY_CANDIDATES_PATTERN.format(
            slug="apple", year=2024, quarter=3
        ),
        status=404,
    )
    out_dir = tmp_path / "calls"
    rc = fetch_transcript.main(
        [
            "AAPL",
            "--quarter", "2024-Q3",
            "--company-slug", "apple",
            "--out", str(out_dir),
        ]
    )
    assert rc == 3  # exit code: no source found
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_fetch_transcript.py -v
```

Expected: `ModuleNotFoundError: No module named 'fetch_transcript'`.

- [ ] **Step 4: Implement `fetch_transcript.py`**

File: `claude/skills/stock-research/scripts/fetch_transcript.py`

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_fetch_transcript.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add claude/skills/stock-research/scripts/fetch_transcript.py \
        claude/skills/stock-research/scripts/tests/test_fetch_transcript.py \
        claude/skills/stock-research/scripts/tests/fixtures/transcript_motley_sample.html
git commit -m "stock-research(scripts): add fetch_transcript.py (Motley Fool + manual)"
```

---

## Task 17: `upsert_ticker.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/upsert_ticker.py`
- Create: `claude/skills/stock-research/scripts/tests/fixtures/tickers_json_sample.json`
- Test: `claude/skills/stock-research/scripts/tests/test_upsert_ticker.py`

- [ ] **Step 1: Create the fixture**

File: `claude/skills/stock-research/scripts/tests/fixtures/tickers_json_sample.json`

```json
{
  "schema_version": 1,
  "tickers": {
    "MSFT": {
      "name": "Microsoft Corporation",
      "sector": "Technology",
      "gvd_category": "quality-growth",
      "first_analyzed": "2026-04-12",
      "last_updated": "2026-04-12",
      "current_status": "WATCH",
      "current_conviction": "medium",
      "thesis_version": "v1",
      "price_at_last_analysis": 410.50,
      "buy_zone_low": 370,
      "buy_zone_high": 390,
      "current_target_position_pct": 5,
      "current_actual_position_pct": 0,
      "active_sell_triggers": []
    }
  }
}
```

- [ ] **Step 2: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_upsert_ticker.py`

```python
"""Tests for upsert_ticker.py."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import upsert_ticker


def _setup_repo(tmp_path: Path, fixtures_dir: Path) -> Path:
    repo = tmp_path / "research"
    repo.mkdir()
    (repo / "tickers.json").write_text(
        (fixtures_dir / "tickers_json_sample.json").read_text()
    )
    return repo


def test_create_new_ticker_entry(tmp_path: Path, fixtures_dir: Path) -> None:
    repo = _setup_repo(tmp_path, fixtures_dir)
    rc = upsert_ticker.main(
        [
            "AAPL",
            "--repo", str(repo),
            "--field", "name=Apple Inc.",
            "--field", "sector=Technology",
            "--field", "gvd_category=quality-growth",
            "--field", "current_status=WATCH",
            "--field", "current_conviction=medium",
            "--field", "thesis_version=v1",
            "--field", "price_at_last_analysis=195.50",
        ]
    )
    assert rc == 0
    data = json.loads((repo / "tickers.json").read_text())
    assert "AAPL" in data["tickers"]
    assert data["tickers"]["AAPL"]["name"] == "Apple Inc."
    assert data["tickers"]["AAPL"]["price_at_last_analysis"] == 195.50
    assert data["tickers"]["AAPL"]["last_updated"] == date.today().isoformat()
    # MSFT is untouched
    assert data["tickers"]["MSFT"]["name"] == "Microsoft Corporation"


def test_update_existing_ticker_entry(tmp_path: Path, fixtures_dir: Path) -> None:
    repo = _setup_repo(tmp_path, fixtures_dir)
    rc = upsert_ticker.main(
        ["MSFT", "--repo", str(repo), "--field", "current_status=BUY"]
    )
    assert rc == 0
    data = json.loads((repo / "tickers.json").read_text())
    assert data["tickers"]["MSFT"]["current_status"] == "BUY"
    assert data["tickers"]["MSFT"]["last_updated"] == date.today().isoformat()
    # Original fields preserved
    assert data["tickers"]["MSFT"]["sector"] == "Technology"


def test_array_field_via_repeated_flag(tmp_path: Path, fixtures_dir: Path) -> None:
    repo = _setup_repo(tmp_path, fixtures_dir)
    rc = upsert_ticker.main(
        [
            "MSFT",
            "--repo", str(repo),
            "--list-field", "active_sell_triggers=Revenue YoY < 5% for 2 quarters",
            "--list-field", "active_sell_triggers=Gross margin < 65%",
        ]
    )
    assert rc == 0
    data = json.loads((repo / "tickers.json").read_text())
    triggers = data["tickers"]["MSFT"]["active_sell_triggers"]
    assert "Revenue YoY < 5% for 2 quarters" in triggers
    assert "Gross margin < 65%" in triggers


def test_write_is_atomic(tmp_path: Path, fixtures_dir: Path, monkeypatch) -> None:
    repo = _setup_repo(tmp_path, fixtures_dir)

    def boom(*a, **k):
        raise RuntimeError("simulated crash mid-rename")

    import os as _os
    monkeypatch.setattr(_os, "replace", boom)
    try:
        upsert_ticker.main(["MSFT", "--repo", str(repo), "--field", "current_status=BUY"])
    except RuntimeError:
        pass
    # Original file is intact (no partial write).
    data = json.loads((repo / "tickers.json").read_text())
    assert data["tickers"]["MSFT"]["current_status"] == "WATCH"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_upsert_ticker.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Implement `upsert_ticker.py`**

File: `claude/skills/stock-research/scripts/upsert_ticker.py`

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_upsert_ticker.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add claude/skills/stock-research/scripts/upsert_ticker.py \
        claude/skills/stock-research/scripts/tests/test_upsert_ticker.py \
        claude/skills/stock-research/scripts/tests/fixtures/tickers_json_sample.json
git commit -m "stock-research(scripts): add upsert_ticker.py atomic JSON updates"
```

---

## Task 18: `update_index.py`

**Files:**
- Create: `claude/skills/stock-research/scripts/update_index.py`
- Test: `claude/skills/stock-research/scripts/tests/test_update_index.py`

- [ ] **Step 1: Write the failing test**

File: `claude/skills/stock-research/scripts/tests/test_update_index.py`

```python
"""Tests for update_index.py."""
from __future__ import annotations

import json
from pathlib import Path

import update_index


def _write_tickers(repo: Path) -> None:
    (repo / "tickers.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tickers": {
                    "AAPL": {
                        "name": "Apple Inc.",
                        "sector": "Technology",
                        "gvd_category": "quality-growth",
                        "current_status": "WATCH",
                        "current_conviction": "medium",
                        "buy_zone_low": 160,
                        "buy_zone_high": 175,
                        "current_target_position_pct": 5,
                        "last_updated": "2026-05-11",
                        "active_sell_triggers": ["Revenue < 5%", "GM < 43%"],
                    },
                    "MSFT": {
                        "name": "Microsoft Corporation",
                        "sector": "Technology",
                        "gvd_category": "quality-growth",
                        "current_status": "BUY",
                        "current_conviction": "high",
                        "buy_zone_low": 370,
                        "buy_zone_high": 390,
                        "current_target_position_pct": 7,
                        "last_updated": "2026-04-12",
                        "active_sell_triggers": [],
                    },
                },
            },
            indent=2,
        )
    )


def test_update_index_renders_table(tmp_path: Path) -> None:
    _write_tickers(tmp_path)
    rc = update_index.main(["--repo", str(tmp_path)])
    assert rc == 0
    md = (tmp_path / "INDEX.md").read_text()
    assert "| Ticker |" in md
    assert "| AAPL |" in md
    assert "| MSFT |" in md
    assert "Technology" in md
    # Triggers count rendered
    assert "2" in md  # AAPL has 2 triggers
    # Sorted alphabetically
    assert md.index("| AAPL |") < md.index("| MSFT |")


def test_update_index_handles_empty_repo(tmp_path: Path) -> None:
    (tmp_path / "tickers.json").write_text(
        json.dumps({"schema_version": 1, "tickers": {}})
    )
    rc = update_index.main(["--repo", str(tmp_path)])
    assert rc == 0
    md = (tmp_path / "INDEX.md").read_text()
    assert "No tickers" in md
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_update_index.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `update_index.py`**

File: `claude/skills/stock-research/scripts/update_index.py`

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_update_index.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add claude/skills/stock-research/scripts/update_index.py \
        claude/skills/stock-research/scripts/tests/test_update_index.py
git commit -m "stock-research(scripts): add update_index.py to render INDEX.md"
```

---

## Task 19: Final validation

**Files:** none modified; this task runs the full test suite and smoke-tests every CLI.

- [ ] **Step 1: Run the entire test suite**

```bash
cd claude/skills/stock-research/scripts
source .venv/bin/activate
pytest -v
```

Expected: all tests pass. Tally should be ~35 tests across 13 test modules.

- [ ] **Step 2: Smoke-test every script's `--help`**

```bash
for s in fetch_sec extract_10k_sections extract_10q_sections diff_risk_factors \
         compute_financials fetch_prices fetch_analyst_estimates compute_pe_band \
         compute_reverse_dcf fetch_transcript upsert_ticker update_index; do
  echo "--- $s ---"
  python "$s.py" --help || echo "FAILED: $s.py"
done
```

Expected: each script prints usage and exits 0.

- [ ] **Step 3: Verify all artifacts compile (Python imports cleanly)**

```bash
python -c "
import _lib.config, _lib.ticker_resolver, _lib.sec_client, _lib.frontmatter, _lib.yf_adapter
import fetch_sec, extract_10k_sections, extract_10q_sections, diff_risk_factors
import compute_financials, fetch_prices, fetch_analyst_estimates, compute_pe_band
import compute_reverse_dcf, fetch_transcript, upsert_ticker, update_index
print('All modules import cleanly.')
"
```

Expected: `All modules import cleanly.`

- [ ] **Step 4: Commit a project README for the scripts directory**

File: `claude/skills/stock-research/scripts/README.md`

```markdown
# stock-research scripts

Twelve Python CLI tools that fetch and analyze US-equity fundamentals.
Used by the `stock-research` skill (see ../SKILL.md when Plan 2 lands).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SR_SEC_USER_AGENT="Your Name your@email"   # required for SEC EDGAR
export SR_REPO_PATH="$HOME/Documents/Personal/investing-research"  # optional override
```

## Scripts

| Script | What it does |
|---|---|
| `fetch_sec.py` | Download filings (10-K, 10-Q, 8-K, ...) to a directory |
| `extract_10k_sections.py` | Parse Items 1 / 1A / 7 / 7A from a 10-K HTML |
| `extract_10q_sections.py` | Parse Items 2 / 3 / 4 from a 10-Q HTML |
| `diff_risk_factors.py` | YoY diff of two Item 1A sections |
| `compute_financials.py` | XBRL company-facts → `financials.json` |
| `fetch_prices.py` | OHLCV + dividends + splits via yfinance |
| `fetch_analyst_estimates.py` | Analyst consensus via yfinance |
| `compute_pe_band.py` | Historical P/E percentile bands |
| `compute_reverse_dcf.py` | Implied FCF growth at current price |
| `fetch_transcript.py` | Earnings call transcript (Motley Fool / manual paste) |
| `upsert_ticker.py` | Atomic update of `tickers.json` |
| `update_index.py` | Render `INDEX.md` from `tickers.json` |

Run any script with `--help` for its exact CLI.

## Tests

```bash
pytest -v
```
```

```bash
git add claude/skills/stock-research/scripts/README.md
git commit -m "stock-research(scripts): add scripts directory README"
```

- [ ] **Step 5: Final summary print**

```bash
echo "Plan 1 complete:"
echo "- $(ls claude/skills/stock-research/scripts/*.py | wc -l) script files"
echo "- $(ls claude/skills/stock-research/scripts/_lib/*.py | grep -v __init__ | wc -l) shared utility modules"
echo "- $(ls claude/skills/stock-research/scripts/tests/test_*.py | wc -l) test modules"
echo ""
echo "Next: Plan 2 — Skill orchestration & deployment."
```

---

## Self-Review Notes

**Spec coverage check.** Every script in the spec's §9 table has a task: fetch_sec (Task 7), extract_10k_sections (9), extract_10q_sections (10), fetch_transcript (16), fetch_prices (12), fetch_analyst_estimates (13), compute_financials (8), compute_pe_band (14), compute_reverse_dcf (15), diff_risk_factors (11), update_index (18), upsert_ticker (17). The agent-retrievable conventions (frontmatter, JSON schemas with `schema_version: 1`) appear in every artifact-writing script. Trend gate from the spec's Phase 3 is implemented in `compute_financials.py`. The reverse DCF defaults match spec §10 (10% discount, 2.5% terminal, 10-yr horizon).

**Out of scope for this plan (correctly deferred to Plan 2):** SKILL.md, per-phase subagent prompts, the orchestrator, the Codex duplicate, sync to install dirs, research-repo bootstrap, end-to-end dry run on a real ticker.

**Type/signature consistency check.** `TickerInfo` is the only cross-script type (from `_lib.ticker_resolver`); scripts call `resolve(ticker)` and use `.cik_padded` and `.ticker` — consistent throughout. `SECClient.list_filings` signature `(cik=, forms=, since=)` is consistent. `frontmatter.write(path, meta, body)` and `read(path)` consistent. `yf_adapter` functions all take `ticker: str` and return dicts/dataframes consistently. JSON outputs all carry `schema_version: 1` and `ticker` keys.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-stock-research-plan-1-scripts.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Each of the 19 tasks runs in a clean context, which matters here because the per-task TDD code blocks are substantial.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints for review.

Which approach?
