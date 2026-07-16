---
artifact: phase-prompt
phase: 4-sub
phase_name: per-competitor-analysis
schema_version: 1
---

# Phase 4 Worker Prompt — Per-Competitor Analysis

You are a worker dispatched by the Phase 4 worker. Your job is to pull one competitor's financials and return a comparison row.

## Context (injected by Phase 4 orchestrator)

- `competitor_ticker`: the competitor's ticker (e.g., "MSFT")
- `scripts_dir`: skill scripts directory
- `raw_dir`: `<parent_ticker_dir>/.raw/competitors/<competitor_ticker>/` — your scratch space

## Your job

1. Pull the competitor's XBRL financials.
2. Compute key metrics (TTM revenue, margins, growth, P/E, etc.).
3. Write a short comparison row + per-competitor notes to `<raw_dir>/summary.md`.
4. Return a compact structured summary that the orchestrator uses to build the side-by-side table.

## Step 1: Pull financials

```bash
mkdir -p <raw_dir>
<scripts_dir>/.venv/bin/python <scripts_dir>/compute_financials.py <competitor_ticker> \
  --years 5 \
  --out <raw_dir>/financials.json
```

If `compute_financials.py` exits non-zero (e.g., the competitor isn't on EDGAR — foreign listing, private company, ETF), return status `NEEDS_CONTEXT` with the error message. The Phase 4 orchestrator will drop you from the comparison.

## Step 2: Pull price + market cap

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/fetch_prices.py <competitor_ticker> \
  --years 2 \
  --out <raw_dir>/prices/
```

If exit code 2 (yfinance returned no data), return `NEEDS_CONTEXT`.

The latest close (last bar in `prices.json`) × diluted shares (from financials.json) = market cap.

## Step 3: Compute the row

From `<raw_dir>/financials.json` and `<raw_dir>/prices/prices.json`:

- `market_cap_b` = latest close × latest diluted shares / 1e9, formatted as "$X.XB"
- `revenue_ttm_b` = latest year's revenue / 1e9
- `revenue_growth_3yr_cagr_pct` = `((revenue_y[-1] / revenue_y[-4]) ^ (1/3) - 1) * 100`
- `gross_margin_pct`, `operating_margin_pct`, `net_margin_pct`, `fcf_margin_pct` = latest year
- `roic_pct` = latest year (from financials.json if available)
- `pe_ttm` = latest close / latest year's EPS
- `diluted_share_growth_3yr_pct` = `((diluted_shares_y[-1] / diluted_shares_y[-4]) - 1) * 100` (positive = dilution, negative = buyback)

## Step 4: Write `<raw_dir>/summary.md`

```yaml
---
competitor_ticker: <COMPETITOR>
parent_ticker: <PARENT>
artifact: competitor-summary
schema_version: 1
---

# <COMPETITOR> vs <PARENT> — comparison row

| Metric | Value |
|---|---|
| Market cap | $X.XB |
| Revenue TTM | $X.XB |
| Revenue 3-yr CAGR | X.X% |
| Gross margin | XX.X% |
| Operating margin | XX.X% |
| Net margin | XX.X% |
| FCF margin | XX.X% |
| ROIC | XX.X% |
| P/E (TTM) | XX.X |
| Diluted-share growth (3-yr) | +X.X% (dilution) / -X.X% (buyback) |

## Strategic note

<2-3 sentences on how this competitor overlaps with PARENT and where they're stronger/weaker on the metrics. Use the financials.json data; don't speculate beyond what the numbers show.>
```

## Output contract (recap)

- File: `<raw_dir>/summary.md`
- Returned summary (one structured paragraph + the metrics in inline form, e.g., "MSFT — market cap $3.1T, revenue $245B TTM, +12% 3-yr CAGR, op margin 44.6%, net margin 36.4%, P/E 35.2× — pulling ahead on cloud (Azure 30%+ growth), gross margin advantage of 200bps vs Apple Services").

## Failure modes

- **`NEEDS_CONTEXT`** if EDGAR or yfinance returns no data for this ticker (foreign, ETF, etc.)
- **`DONE_WITH_CONCERNS`** if some metrics are missing (e.g., financial company without standard income-statement concepts)
- **`DONE`** otherwise
