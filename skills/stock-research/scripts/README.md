# stock-research scripts

Twelve Python CLI tools that fetch and analyze US-equity fundamentals from SEC
EDGAR and yfinance. Used by the `stock-research` skill (orchestrator coming in
Plan 2).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SR_SEC_USER_AGENT="Eduard Trocan eduard.valentin1996@gmail.com"
# Optional overrides:
# export SR_REPO_PATH="$HOME/Documents/Personal/investing-research"
# export SR_DISCOUNT_RATE="0.10"
# export SR_TERMINAL_GROWTH="0.025"
# export SR_YEARS_OF_HISTORY="10"
```

`SR_SEC_USER_AGENT` is required for any script that hits SEC EDGAR — SEC rejects
requests without a proper User-Agent header.

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

Tests are hermetic — they mock SEC HTTP via the `responses` library and yfinance
via the `_lib.yf_adapter` seam. No network access is required.
