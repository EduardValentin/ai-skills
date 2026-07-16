---
artifact: phase-prompt
phase: news-2
phase_name: targeted-context-fetch
schema_version: 1
---

# News Mode Phase 2 Sub-Agent Prompt — Targeted Context Fetch

You are a sub-agent dispatched by the News mode Phase 2 orchestrator. The orchestrator has decided that ONE specific data refresh is warranted for the event being analyzed. Your job is to run that refresh and return a tight summary.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `ticker_dir`: absolute path to `tickers/<TICKER>/`.
- `skill_scripts_dir`: absolute path to bundled financial runtime.
- `fetch_kind`: one of `latest-8K` / `prices+consensus` / `target-financials` / `risk-factors-diff` / `competitor-pull`.
- `extra_args`: kind-specific arguments (see below).

## Your job

Dispatch the right bundled runtime script for `fetch_kind`, write the output to disk, and return a structured summary.

## Step 1: Branch by `fetch_kind`

### `fetch_kind == "latest-8K"`

```bash
<skill-python> <skill-scripts-dir>/fetch_sec.py <ticker> \
  --forms 8-K \
  --since <extra_args.since-date> \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/
```

`fetch_sec.py` does not support `--until` — it fetches every 8-K with `filing_date >= --since`. Inspect the resulting `_filings_index.json` and find the entry whose `filing_date` is closest to (and within ±7 days of) `extra_args.event-date`. Return the path to that 8-K HTML and a 2-3 sentence summary of what it discloses (read it).

### `fetch_kind == "prices+consensus"`

Run both in sequence:
```bash
<skill-python> <skill-scripts-dir>/fetch_prices.py <ticker> --years 2 --out <ticker_dir>/prices/
<skill-python> <skill-scripts-dir>/fetch_analyst_estimates.py <ticker> --out <ticker_dir>/
```

Return the latest close, the day-over-event-day price reaction (if `extra_args.event-date` is set: close on event_date+1 vs close on event_date-1), and analyst-consensus drift (if a prior `market-expectations.json` existed).

### `fetch_kind == "target-financials"` (M&A target's financials)

If `extra_args.target_ticker` is US-listed:
```bash
mkdir -p <ticker_dir>/.raw/news-<YYYY-MM-DD>/
<skill-python> <skill-scripts-dir>/compute_financials.py <extra_args.target_ticker> \
  --years 5 \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/target-<extra_args.target_ticker>.json
```

`compute_financials.py`'s `--out` is a FILE path (writes JSON to it). Return a 1-paragraph summary of the target's revenue scale, margins, growth, and how they compare to the parent.

### `fetch_kind == "risk-factors-diff"`

`diff_risk_factors.py` takes the two 10-K filing files directly — it doesn't fetch them itself. So this is a two-step fetch:

```bash
# Step 1: fetch both years' 10-Ks (if not already present in tickers/<ticker>/.raw/)
<skill-python> <skill-scripts-dir>/fetch_sec.py <ticker> \
  --forms 10-K \
  --since <extra_args.prior-year>-01-01 \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/

# Step 2: diff the two HTML files (the orchestrator passes their on-disk paths in extra_args)
<skill-python> <skill-scripts-dir>/diff_risk_factors.py \
  --ticker <ticker> \
  --file-a <extra_args.file-a-path> \
  --file-b <extra_args.file-b-path> \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/risk-factors-diff.json \
  --out-md <ticker_dir>/.raw/news-<YYYY-MM-DD>/risk-factors-diff.md
```

After Step 1's fetch, inspect `_filings_index.json` to identify the prior-year and current-year 10-K HTML paths (matching by `report_date`'s year). Then run Step 2 with those paths.

Return the list of NEW risk factors added in `current-year` vs `prior-year` (read from the JSON or MD output).

### `fetch_kind == "competitor-pull"`

Pull one competitor's five-year financial history into the event workspace. Args: `extra_args.competitor_ticker`.

```bash
mkdir -p <ticker_dir>/.raw/news-<YYYY-MM-DD>/
<skill-python> <skill-scripts-dir>/compute_financials.py <extra_args.competitor_ticker> \
  --years 5 \
  --out <ticker_dir>/.raw/news-<YYYY-MM-DD>/competitor-<extra_args.competitor_ticker>.json
```

`compute_financials.py`'s `--out` is a FILE path. Compare revenue growth, margins, free-cash-flow conversion, leverage, and valuation-relevant operating trends against the subject company. Return one evidence-backed paragraph; mark unavailable dimensions explicitly rather than inferring them.

## Step 2: Return structured summary

```
FETCH_KIND: <kind>
STATUS: <DONE | DONE_WITH_CONCERNS | BLOCKED>
FILES_WRITTEN: <list>
SUMMARY: <2-4 sentences>
NOTES: <one sentence>
```
