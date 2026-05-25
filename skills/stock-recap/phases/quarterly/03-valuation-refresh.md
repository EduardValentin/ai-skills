---
artifact: phase-prompt
phase: quarterly-3-valuation
phase_name: valuation-refresh
schema_version: 1
---

# Quarterly Phase 3 Sub-Agent Prompt — Valuation Refresh

You are a sub-agent dispatched by the Quarterly Phase 3 orchestrator. Your job is to re-pull today's prices, analyst consensus, P/E historical band, and reverse-DCF at today's price; then rewrite `valuation.md` and `market-expectations.{md,json}`.

Runs in parallel with the financials-refresh sub-agent.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `ticker_dir`: absolute path to `tickers/<TICKER>/`.
- `toolkit_dir`: absolute path to the `financial-toolkit` install.
- `saved_buy_zones`: the full `verdict.json.buy_zones` list (each entry has `name`, `price_range` like `"$80-$88"`, `action`). The orchestrator computes the overall low and high by parsing the `price_range` strings and taking `min(low)` / `max(high)` across all zones to pass to the sub-agent as `saved_buy_zone_overall_low` and `saved_buy_zone_overall_high` for the buy-zone-position check below.
- `saved_reverse_dcf_implied_growth`: from the saved `valuation.md` (parse the line if present, else `null`).

## Your job

1. Pull today's price + dividends + splits via yfinance.
2. Pull analyst consensus.
3. Compute 5- and 10-year P/E percentile band.
4. Compute reverse-DCF implied growth at today's price.
5. Rewrite `valuation.md` and `market-expectations.{md,json}`.
6. Return a ~500-word summary.

## Step 1: Prices + dividends + splits

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_prices.py <ticker> \
  --years 10 \
  --out <ticker_dir>/prices/
```

If exit code 2 (yfinance empty — delisted / halted), return status `BLOCKED` with the message — Phase 5 needs price.

## Step 2: Analyst consensus

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_analyst_estimates.py <ticker> \
  --out <ticker_dir>/
```

`--out` is a directory; the script writes `<out>/market-expectations.json`. It does NOT write `market-expectations.md` — generate that in Step 5 from the JSON.

If exit code != 0, return status `DONE_WITH_CONCERNS` with the message; the orchestrator will note "no analyst coverage available" in Checkpoint 1. Skip the auto-recommend rule based on consensus drift in that case.

## Step 3: P/E historical band

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_pe_band.py \
  --prices <ticker_dir>/prices/prices.json \
  --financials <ticker_dir>/financials.json \
  --out <ticker_dir>/.raw/pe-band-<today-YYYY-MM-DD>.json
```

`compute_pe_band.py` takes no ticker positional — only the two input JSON paths and an output JSON path. It writes a single JSON document at `--out`. Read that JSON and incorporate the 25th/50th/75th percentile P/E band figures into the refreshed `valuation.md` section you write in Step 5.

## Step 4: Reverse-DCF at today's price

Read today's close from `<ticker_dir>/prices/prices.json` (latest bar; written by Step 1).

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_reverse_dcf.py \
  --financials <ticker_dir>/financials.json \
  --price <today-close> \
  --discount-rate 0.10 \
  --terminal-growth 0.025 \
  --out <ticker_dir>/.raw/reverse-dcf-<today-YYYY-MM-DD>.json
```

`compute_reverse_dcf.py` takes no ticker positional — only `--financials` (the JSON written by `compute_financials.py`), `--price`, the discount/terminal-growth rates, and `--out` (a JSON file path). Read the output JSON; capture the resulting implied growth rate (a percent) into the summary and into the refreshed `valuation.md` you write in Step 5.

## Step 5: Compute deltas worth flagging

- **Buy-zone position:** today's close vs `saved_buy_zone_overall_low`–`saved_buy_zone_overall_high`. One of: `above-zone-high` / `inside-zone` / `below-zone-low`.
- **Reverse-DCF drift:** `(new_implied_growth - saved_reverse_dcf_implied_growth) / saved_reverse_dcf_implied_growth * 100`. Flag if `|drift| > 50%`. If saved is `null`, mark `cannot-compute-drift`.
- **Consensus drift:** compare new mean price target vs the one in the prior `market-expectations.json` (read from git's index for the file's previous version — `git show HEAD:...market-expectations.json`). Flag if `>15%` change.

## Step 6: Return summary

```
STATUS: <DONE | DONE_WITH_CONCERNS | BLOCKED>
TODAY_CLOSE: $<price>
BUY_ZONE_POSITION: <above-zone-high | inside-zone | below-zone-low>
PE_TTM: <X.X>×
PE_PERCENTILE_10YR: <XX>%
REVERSE_DCF_IMPLIED_GROWTH: <XX>%/yr
REVERSE_DCF_DRIFT_VS_SAVED: <+/-XX%, or cannot-compute-drift>
CONSENSUS_DRIFT_VS_SAVED: <+/-XX%, or cannot-compute-drift>
FILES_WRITTEN: valuation.md, market-expectations.md, market-expectations.json, prices/prices.json
NOTES: <one sentence>
```
