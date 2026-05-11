---
artifact: phase-prompt
phase: 7
phase_name: market-expectations
schema_version: 1
---

# Phase 7 Subagent Prompt — Market Expectations

Pull analyst consensus from yfinance into a calibration input for the Phase 8 projection brainstorm.

## Context (injected by orchestrator)

Standard. Phase 7 has no dependencies on prior phases beyond ticker resolution.

## Your job

Produce **two files**:
- `<ticker_dir>/market-expectations.json` — produced directly by `fetch_analyst_estimates.py`
- `<ticker_dir>/market-expectations.md` — human-readable companion you write

Return a **~500-word summary**: consensus price target vs current price, ratings distribution, key EPS/revenue estimates, EPS-trend direction (rising/falling = beat/miss signal). Most importantly: **what consensus expects for growth — this becomes the calibration prompt during Phase 8.**

## Step 1: Fetch analyst estimates

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/fetch_analyst_estimates.py <ticker> \
  --out <ticker_dir>/
```

This produces `market-expectations.json` containing: price target (low/mean/high/num_analysts), ratings (strong_buy/buy/hold/sell/strong_sell counts), earnings_estimate, revenue_estimate, eps_trend, growth_estimates.

If yfinance returns empty across the board (uncommon — even no-coverage names usually have *some* fields), note "No analyst coverage available" and produce a stub `market-expectations.md` saying so. Return `DONE_WITH_CONCERNS`.

## Step 2: Write `market-expectations.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: market-expectations
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then sections:

### 1. Coverage

- **Number of analysts:** N (from `price_target.num_analysts`)
- Categorize: thin (<5), normal (5–25), heavily covered (>25)

### 2. Price target

| Tier | Value |
|---|---|
| Low | $XXX |
| Mean | $XXX |
| High | $XXX |
| **Current price** | $XXX |
| **Implied upside (mean)** | +XX% |
| **Implied upside (high)** | +XX% |

### 3. Ratings distribution

| Rating | Count | % |
|---|---|---|
| Strong Buy | N | XX% |
| Buy | N | XX% |
| Hold | N | XX% |
| Sell | N | XX% |
| Strong Sell | N | XX% |

A one-sentence read: "Consensus is bullish (75% Buy/Strong Buy)" or "Mixed (40% Hold)" or "Bearish minority is large enough to notice".

### 4. EPS estimates (next 4 quarters + current/next FY)

| Period | Consensus EPS | Low | High | # estimates |
|---|---|---|---|---|

A one-sentence read: are estimates clustered (high conviction) or wide (uncertainty)?

### 5. Revenue estimates

Same shape as EPS — period, consensus, range.

### 6. EPS trend (leading indicator)

`eps_trend` shows how the consensus EPS estimate has evolved over the last 90 days. The four columns are typically: `current_estimate`, `7d_ago`, `30d_ago`, `60d_ago`, `90d_ago`.

- Rising estimates = analysts ratcheting expectations up (often a "beat" signal)
- Falling estimates = analysts ratcheting down (often a "miss" signal)
- Flat = market expects what they expect

Report the trend direction for the current quarter and the current FY.

### 7. Growth estimates

`growth_estimates` typically has next-quarter, next-FY, and 5-year growth forecasts for both the ticker and its sector/industry. Report:

| Metric | Ticker | Sector |
|---|---|---|
| Next-FY growth | X% | X% |
| 5-yr growth (annualized) | X% | X% |

A one-sentence read: is the ticker expected to outgrow or underperform its sector?

### 8. **Calibration prompt for Phase 8** (the key section)

Pull the consensus base case in one paragraph that Phase 8's projection brainstorm will use as a foil:

> "Consensus expects revenue +X% next year, EPS +Y% next year, and 5-year revenue growth of Z%/yr. Mean price target $XXX implies +XX% upside in 12 months. The bull case in our projection should typically beat this; the base case should match or modestly beat; the bear case should sit below consensus. **What do you know that consensus doesn't?**"

The orchestrator uses this prompt verbatim during Phase 8 to anchor the brainstorm.

## Output contract (recap)

- `market-expectations.json` (script-produced) + `market-expectations.md` (your write-up)
- ~500-word summary with the consensus snapshot AND the calibration prompt for Phase 8

## Failure modes

- **`DONE_WITH_CONCERNS`** if analyst coverage is empty (rare; small-cap names sometimes)
- **`DONE`** otherwise
