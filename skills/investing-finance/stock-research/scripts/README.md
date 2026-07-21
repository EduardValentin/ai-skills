# stock-research scripts

Fourteen Python CLI tools that fetch, validate, and analyze US-equity
fundamentals from SEC EDGAR and yfinance. Used by the `stock-research` skill.

## Setup

```bash
runtime_home="$(
  PYTHONPATH="<installed-skill>/scripts" python3 -B -c \
    'from _lib.config import ai_skills_runtime_home; print(ai_skills_runtime_home())'
)"
finance_venv="${runtime_home}/investing-finance/venv"
python3 -B -m venv "${finance_venv}"
"${finance_venv}/bin/python" -B -m pip install --requirement "<installed-skill>/scripts/requirements.txt"
export SR_SEC_USER_AGENT="Your Name you@example.com"
export SR_REPO_PATH="/path/to/investing-research"
# Optional overrides:
# export SR_DISCOUNT_RATE="0.10"
# export SR_TERMINAL_GROWTH="0.025"
# export SR_YEARS_OF_HISTORY="10"
```

Use Python 3.10 or newer. Keep the environment outside the installed skill;
the helper applies `AI_SKILLS_RUNTIME_HOME`, XDG, and home-cache precedence.
Pass `-B` to every bundled script or inline helper invocation. If a subprocess
cannot add interpreter flags, set its `PYTHONPYCACHEPREFIX` to
`${runtime_home}/investing-finance/pycache`.

`SR_SEC_USER_AGENT` is required for any script that hits SEC EDGAR — SEC rejects
requests without a proper User-Agent header. `SR_REPO_PATH` is required and must
point to the target investing research repository.

## Scripts

| Script | What it does |
|---|---|
| `fetch_sec.py` | Download filings (10-K, 10-Q, 8-K, ...) to a directory |
| `select_filing.py` | Select a downloaded filing by indexed report and filing dates |
| `extract_10k_sections.py` | Parse Items 1 / 1A / 7 / 7A from a 10-K HTML |
| `extract_10q_sections.py` | Parse Items 2 / 3 / 4 from a 10-Q HTML |
| `diff_risk_factors.py` | YoY diff of two Item 1A sections |
| `compute_financials.py` | XBRL company-facts → `financials.json` |
| `validate_financials.py` | Data-quality checkpoint for debt, net debt, dividends, and split normalization |
| `fetch_prices.py` | OHLCV + dividends + splits via yfinance |
| `fetch_analyst_estimates.py` | Analyst consensus via yfinance |
| `compute_pe_band.py` | Historical P/E percentile bands |
| `compute_reverse_dcf.py` | Implied FCF growth at current price |
| `fetch_transcript.py` | Earnings call transcript (Motley Fool / manual paste) |
| `upsert_ticker.py` | Atomic update of `tickers.json` |
| `update_index.py` | Render `INDEX.md` from `tickers.json` |

Run any script as `"${finance_venv}/bin/python" -B <script>.py --help` for its
exact CLI.
