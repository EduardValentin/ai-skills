---
artifact: phase-prompt
phase: 6
phase_name: valuation
schema_version: 1
---

# Phase 6 Subagent Prompt — Valuation

Pull current multiples, build the 5/10-year P/E percentile band, and run reverse DCF.

## Context (injected by orchestrator)

Standard. Plus:
- `financials_path`: `<ticker_dir>/financials.json` — Phase 3 produced this
- `prices_dir`: `<ticker_dir>/.raw/prices/` — you'll produce this

## Your job

Produce **one file**: `<ticker_dir>/valuation.md`. Plus supporting JSON in `.raw/`: `prices.json`, `dividends.json`, `splits.json`, `pe_band.json`, `reverse_dcf.json`.

Return the Worker Return Contract requested by the top-level orchestrator. Keep the synthesis compact and put current multiples, historical P/E band position, reverse-DCF implied growth, and the headline "expensive / fair / cheap" verdict in `checkpoint_highlights`.

## Step 1: Fetch prices and analyst data

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/fetch_prices.py <ticker> \
  --years 10 \
  --out <ticker_dir>/.raw/prices/
```

If exit code 2 (no data — delisted, halted), the entire Phase 6 fails. Report `BLOCKED` to the orchestrator with the message. Phase 6 is load-bearing — without prices we can't do valuation.

## Step 2: Compute P/E band

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/compute_pe_band.py \
  --prices <ticker_dir>/.raw/prices/prices.json \
  --financials <ticker_dir>/financials.json \
  --out <ticker_dir>/.raw/pe_band.json
```

This produces `pe_band.json` with the percentile breakdown.

## Step 3: Compute reverse DCF

Get the current price from `prices.json` (last bar's close):

```bash
current_price=$(jq '.bars[-1].close' <ticker_dir>/.raw/prices/prices.json)
```

Then:

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/compute_reverse_dcf.py \
  --financials <ticker_dir>/financials.json \
  --price "$current_price" \
  --discount-rate 0.10 \
  --terminal-growth 0.025 \
  --years 10 \
  --out <ticker_dir>/.raw/reverse_dcf.json
```

If the latest fiscal year has negative FCF (speculative-growth name), the reverse DCF will produce nonsense (the model assumes positive FCF). In that case, note "Reverse DCF not applicable — latest year FCF is negative; relevant valuation lens is path-to-profitability rather than DCF" and skip this step.

## Step 4: Write `valuation.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: valuation
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
current_price: <number>
---
```

Then sections:

### 1. Current multiples

Compute and report (use `financials.json` latest year + current price):

| Metric | Value | Note |
|---|---|---|
| Current price | $XXX.XX | as of <today> |
| Diluted shares | X.XB | latest FY |
| Market cap | $X.XB | price × shares |
| P/E (TTM) | XX.X | price / EPS_TTM |
| Forward P/E | XX.X | price / consensus next-year EPS (see Phase 7 market expectations) |
| P/S (TTM) | XX.X | market cap / revenue_TTM |
| P/FCF (TTM) | XX.X | market cap / fcf_TTM |
| EV/EBITDA | XX.X | (market cap + net debt) / EBITDA. EBITDA approx = operating income + depreciation; if depreciation not in JSON, use operating income and note approximation |
| P/B (financials only) | XX.X | only meaningful for banks / insurers / asset-heavy financials |

### 2. Historical P/E band (5- and 10-year)

From `pe_band.json`:

| Metric | 10-year |
|---|---|
| 25th percentile | XX.X |
| Median (50th) | XX.X |
| 75th percentile | XX.X |
| Min | XX.X |
| Max | XX.X |
| **Current** | XX.X |
| **Current percentile** | XX.X% |

A paragraph: where is the current P/E in the historical distribution? Above median, below, near a historical high/low? Note any structural reasons the multiple might have shifted (e.g., business mix changed, balance sheet de-risked).

### 3. Reverse DCF — implied growth

From `reverse_dcf.json`:

- **Implied 10-year FCF growth at current price: X.X% / year** (assuming 10% discount rate, 2.5% terminal growth)

A paragraph interpreting this:
- Is this growth rate plausible? Compare with the company's historical FCF growth (from financials.json).
- For the GVD bucket, is this rate aggressive or conservative? (Quality-growth >15% = aggressive; value <8% = conservative.)
- What's the **margin of error**: at 8% discount rate the implied is X.X%; at 12% it's Y.Y%. (Re-run `compute_reverse_dcf.py` with different rates if you want this.)

### 4. Valuation verdict

One-sentence headline: **"Expensive / Fair / Cheap"** at current price, based on:
- P/E vs historical band
- Reverse-DCF implied growth vs plausible
- Multiple comparison vs peers (use the competitors.md row data)

This is a *snapshot* verdict for orchestrator synthesis. The full BUY/WATCH/AVOID call comes in Phase 9 after projections.

## Output contract (recap)

- `valuation.md` + raw JSONs in `.raw/`
- Worker Return Contract with compact valuation highlights

## Failure modes

- **`BLOCKED`** if `fetch_prices.py` returns exit 2 (no price data)
- **`DONE_WITH_CONCERNS`** if reverse DCF is not applicable (negative FCF) — fine, note it
- **`DONE`** otherwise
