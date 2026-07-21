---
artifact: phase-prompt
phase: quarterly-3-valuation
phase_name: valuation-refresh
schema_version: 1
---

# Quarterly Phase 3 Sub-Agent Prompt — Valuation Refresh

You are a sub-agent dispatched by the Quarterly Phase 3 orchestrator. Your job is to re-pull today's prices, analyst consensus, P/E historical band, and reverse-DCF at today's price; then rewrite `valuation.md` and `market-expectations.{md,json}`.

In quarterly catch-up, this runs only after financials refresh has completed its atomic canonical write. In valuation-only mode, it reads the unchanged saved financials document.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `ticker_dir`: absolute path to `tickers/<TICKER>/`.
- `skill_scripts_dir`: absolute path to the `bundled financial runtime` install.
- `financials_path`: exact completed JSON input. Quarterly catch-up passes the refreshed canonical path; valuation-only passes the saved canonical path.
- `financials_basis`: `refreshed-quarterly` or `saved-valuation-only`.
- `saved_buy_zones`: the full `verdict.json.buy_zones` list (each entry has `name`, `price_range` like ``USD 80-88``, `action`). The orchestrator computes the overall low and high by parsing the `price_range` strings and taking `min(low)` / `max(high)` across all zones to pass to the sub-agent as `saved_buy_zone_overall_low` and `saved_buy_zone_overall_high` for the buy-zone-position check below.
- `saved_reverse_dcf_implied_growth`: from the saved `valuation.md` (parse the line if present, else `null`).

## Your job

1. Pull today's price + dividends + splits via yfinance.
2. Pull analyst consensus.
3. Compute distinct 5-year and 10-year historical P/E bands and, when available, current P/E from an explicit TTM EPS value.
4. Compute reverse-DCF implied growth at today's price.
5. Rewrite `valuation.md` and `market-expectations.{md,json}`.
6. Return a ~500-word summary.

## Step 1: Prices + dividends + splits

```bash
<skill-python> -B <skill-scripts-dir>/fetch_prices.py <ticker> \
  --years 10 \
  --out <ticker_dir>/prices/
```

If exit code 2 (yfinance empty — delisted / halted), return status `BLOCKED` with the message — Phase 5 needs price.

## Step 2: Analyst consensus

```bash
<skill-python> -B <skill-scripts-dir>/fetch_analyst_estimates.py <ticker> \
  --out <ticker_dir>/
```

`--out` is a directory; the script writes `<out>/market-expectations.json`. It does NOT write `market-expectations.md` — generate that in Step 5 from the JSON.

If exit code != 0, return status `DONE_WITH_CONCERNS` with the message; the orchestrator will note "no analyst coverage available" in Checkpoint 1. Skip the auto-recommend rule based on consensus drift in that case.

## Step 3: P/E historical band

Read `<financials_path>.ttm[]`, keep entries with an ISO `report_date`, sort chronologically, and select the latest record first. Never walk backward to an older profitable period. When that latest record has numeric `.eps`, pass it verbatim as `<latest-ttm-eps>`, including zero or a negative value; the script then emits `current_pe_ttm: null` with `current_eps_basis: ttm-not-meaningful`. When the latest record has missing or nonnumeric EPS, omit `--ttm-eps`; in quarterly catch-up return `DONE_WITH_CONCERNS`, while valuation-only may continue with the saved-data fallback. In either case, label TTM P/E `cannot-compute` for missing EPS or `not-meaningful` for nonpositive EPS, and never relabel latest fiscal-year EPS as TTM.

```bash
<skill-python> -B <skill-scripts-dir>/compute_pe_band.py \
  --prices <ticker_dir>/prices/prices.json \
  --financials <financials_path> \
  --windows 5,10 \
  --ttm-eps <latest-ttm-eps> \
  --out <ticker_dir>/.raw/pe-band-<today-YYYY-MM-DD>.json
```

Omit the `--ttm-eps` pair only when the selected latest TTM record has no numeric EPS or there is no dated TTM record. `compute_pe_band.py` takes no ticker positional. Read `bands.5_year` and `bands.10_year` separately, including each window's `window_start`, `window_end`, observation count, 25th/50th/75th percentiles, and current percentile. Read current TTM P/E only from `current_pe_ttm`, whose input is echoed as `ttm_eps`. Historical observations after a zero or negative dated EPS point remain absent until a later positive EPS point establishes a new meaningful P/E basis.

## Step 4: Reverse-DCF at today's price

Read today's close from `<ticker_dir>/prices/prices.json` (latest bar; written by Step 1).

```bash
<skill-python> -B <skill-scripts-dir>/compute_reverse_dcf.py \
  --financials <financials_path> \
  --price <today-close> \
  --discount-rate 0.10 \
  --terminal-growth 0.025 \
  --out <ticker_dir>/.raw/reverse-dcf-<today-YYYY-MM-DD>.json
```

`compute_reverse_dcf.py` takes no ticker positional — only the exact injected `--financials` path, `--price`, the discount/terminal-growth rates, and `--out` (a JSON file path). Read the output JSON; capture the resulting implied growth rate (a percent) into the summary and into the refreshed `valuation.md` you write in Step 5.

## Step 5: Compute deltas and rewrite `valuation.md` + `market-expectations.md`

First, compute the three deltas worth flagging:

- **Buy-zone position:** today's close vs `saved_buy_zone_overall_low`–`saved_buy_zone_overall_high`. One of: `above-zone-high` / `inside-zone` / `below-zone-low`.
- **Reverse-DCF drift:** `(new_implied_growth - saved_reverse_dcf_implied_growth) / saved_reverse_dcf_implied_growth * 100`. Flag if `|drift| > 50%`. If saved is `null`, mark `cannot-compute-drift`.
- **Consensus drift:** compare new mean price target vs the one in the prior `market-expectations.json` (read from git's index for the file's previous version — `git show HEAD:...market-expectations.json`). Flag if `>15%` change.

Then rewrite the two markdown companions:

- **`<ticker_dir>/valuation.md`** — frontmatter with `ticker`, `artifact: valuation`, `as_of`, and `schema_version: 1`, followed by a current-multiples table, separate 5-year and 10-year P/E band tables, and a reverse-DCF section. Pull figures from `bands.5_year`, `bands.10_year`, `current_pe_ttm`, and the reverse-DCF output. When `current_pe_ttm` is null, use `current_eps_basis` to distinguish `ttm-not-meaningful` from an unavailable or non-TTM fallback basis; never render `current_pe` as TTM P/E. Include the three deltas in a new section at the top: **"What changed since last touch"**.
- **`<ticker_dir>/market-expectations.md`** — generated from the `market-expectations.json` written by `fetch_analyst_estimates.py` (Step 2), with frontmatter (`ticker`, `artifact: market-expectations`, `as_of`, `schema_version: 1`) and sections for analyst coverage, consensus price targets, ratings, EPS estimates, EPS trend, and recent rating changes. If consensus drift was flagged in Step 5, surface it at the top too.

## Step 6: Return summary

```
STATUS: <DONE | DONE_WITH_CONCERNS | BLOCKED>
TODAY_CLOSE: $<price>
BUY_ZONE_POSITION: <above-zone-high | inside-zone | below-zone-low>
PE_TTM: <X.X× | cannot-compute (no saved TTM EPS) | not-meaningful (latest TTM EPS is nonpositive)>
PE_PERCENTILE_5YR: <XX% | cannot-compute>
PE_PERCENTILE_10YR: <XX% | cannot-compute>
REVERSE_DCF_IMPLIED_GROWTH: <XX>%/yr
REVERSE_DCF_DRIFT_VS_SAVED: <+/-XX%, or cannot-compute-drift>
CONSENSUS_DRIFT_VS_SAVED: <+/-XX%, or cannot-compute-drift>
FILES_WRITTEN: valuation.md, market-expectations.md, market-expectations.json, prices/prices.json
NOTES: <one sentence>
```
