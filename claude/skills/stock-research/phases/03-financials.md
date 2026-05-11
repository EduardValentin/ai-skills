---
artifact: phase-prompt
phase: 3
phase_name: financials
schema_version: 1
---

# Phase 3 Subagent Prompt — Financials

You are a research subagent for `stock-research`. Your job is Phase 3: financial trends + pass/fail gate.

## Context (injected by orchestrator)

- `ticker`, `cik_padded`, `ticker_dir`, `scripts_dir`, `raw_dir` (same as Phase 2)

## Your job

Produce **two files**:
- `<ticker_dir>/financials.json` — machine-readable, full schema
- `<ticker_dir>/financials.md` — human-readable companion with charts described in prose + the pass/fail gate verdict

Return a **~500-word summary** covering: revenue/net-income trend verdict (up-and-right, down-and-left, mixed), margin trajectory, FCF + SBC concerns, balance-sheet snapshot, capital-allocation scorecard.

## Inputs available

If Phase 2 already ran `compute_financials.py`, `financials.json` exists. Otherwise run:

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/compute_financials.py <ticker> \
  --years 10 \
  --out <ticker_dir>/financials.json
```

Re-read it. Use the data for the markdown companion.

## `financials.json` schema (already produced by the script)

Per `compute_financials.py` output:

```json
{
  "ticker": "AAPL",
  "cik": "0000320193",
  "name": "Apple Inc.",
  "schema_version": 1,
  "generated_at": "2026-05-11",
  "years": [
    {
      "fiscal_year": 2024,
      "revenue": 391035000000,
      "gross_profit": ...,
      "operating_income": ...,
      "net_income": ...,
      "cfo": ...,
      "capex": ...,
      "fcf": ...,
      "gross_margin_pct": ...,
      "operating_margin_pct": ...,
      "net_margin_pct": ...,
      "fcf_margin_pct": ...,
      "diluted_shares": ...,
      "eps": ...,
      "fcf_per_share": ...,
      "sbc": ...,
      "sbc_pct_of_revenue": ...,
      "buybacks": ...,
      "dividends_paid": ...,
      "cash": ...,
      "long_term_debt": ...,
      "net_debt": ...
    },
    ...
  ],
  "trend_gate": {
    "revenue_up_and_right": true | false | "mixed" | "insufficient_data",
    "net_income_up_and_right": ...,
    "fcf_up_and_right": ...
  }
}
```

Your job is NOT to regenerate this — the script did it. Your job is to write the human-readable `financials.md` companion AND verify the trend gate is correct.

## `financials.md` structure

Open with frontmatter:

```yaml
---
ticker: <TICKER>
artifact: financials
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then sections:

### 1. Trend verdict (the gate)

Lead with the trend gate result for the user's methodology check ("up and to the right TTM?"):

- **Revenue trend (5–10 yr):** ⬆ UP / ⬇ DOWN / ↔ MIXED — with the year-by-year numbers in a small table
- **Net income trend:** same
- **FCF trend:** same

Then a one-sentence overall verdict: **"Passes the up-and-to-the-right gate"** or **"Fails the up-and-to-the-right gate (mixed FCF)"** etc.

### 2. Margins over time

| Year | Gross % | Op % | Net % | FCF % |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

A paragraph on the margin story: are they expanding, stable, compressing? Note any inflection points (M&A, restructuring, COVID, AI capex cycle, etc.).

### 3. Stock-based compensation

| Year | SBC ($) | SBC % of revenue |
|---|---|---|

Note any concerning trend (SBC growing faster than revenue = hidden dilution). For tech companies, SBC % of revenue >5% is worth flagging; >10% is a red flag.

### 4. Capital allocation scorecard (5–10 yr)

| Year | FCF | Buybacks | Dividends | Net debt paydown / (incurred) | M&A spend |
|---|---|---|---|---|---|

A paragraph on capital-allocation track record:
- How much FCF was generated over the period?
- How much was returned to shareholders (buybacks + dividends)?
- What was the M&A pattern? Quick sanity check on value creation — do you remember any of these deals (refresh from the 10-K M&A footnotes if needed)?

### 5. Shareholder yield

Compute and report:
- **Buyback yield (TTM)** = `buybacks / market_cap` × 100. Market cap = `latest_price × diluted_shares`. (Use Phase 6's price if available; otherwise note "current price TBD.")
- **Dividend yield (TTM)** = `dividends_paid / market_cap` × 100.
- **Total shareholder yield** = buyback yield + dividend yield + debt-paydown yield.

If this can't be computed (current price not available yet because Phase 6 runs in parallel), note: "Shareholder yield to be computed in Phase 6 once current price is fetched."

### 6. Balance sheet snapshot (latest fiscal year)

- Cash: $X B
- Long-term debt: $Y B
- Net debt: $Z B (positive = net debtor, negative = net cash)
- Net debt / EBITDA: ratio (compute EBITDA approx as `operating_income + depreciation`; if depreciation isn't in the JSON, use operating income as a rough proxy and note the approximation)

A one-paragraph balance-sheet read: cash-heavy / leveraged / balanced. Mention any debt maturity walls or covenant concerns if you can find them in the 10-K.

### 7. ROIC trajectory

If `financials.json` includes ROIC per year, build a small chart-in-prose. If not, compute approximate ROIC year-by-year using: `roic = net_income / (long_term_debt + book_equity)`. Book equity isn't in our schema — note this and skip ROIC if you can't get it from another source.

## Trend-gate verification

Open `financials.json`. The `trend_gate.revenue_up_and_right` field has one of: `true`, `false`, `"mixed"`, `"insufficient_data"`.

Independent check: look at the year-by-year revenue values. Does the gate value match what you see? If not, it's a script bug — note it in your summary so the orchestrator can flag it. (Likely you'll find: gate is correct.)

## Output contract (recap)

- `financials.json` — emitted by `compute_financials.py`, untouched by you
- `financials.md` — human-readable companion you produce
- `~500-word summary` covering trend gate, margins, SBC, capital-allocation, balance sheet

## Failure modes

- **`BLOCKED`** if `compute_financials.py` returns non-zero (ticker resolution or XBRL API failure)
- **`DONE_WITH_CONCERNS`** if balance-sheet fields are sparsely populated (some companies don't report cash/LTD on the XBRL endpoint — the JSON will show `null` for those fields), or if ROIC can't be computed
- **`DONE`** otherwise
