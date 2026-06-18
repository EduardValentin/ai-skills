---
artifact: phase-prompt
phase: 3
phase_name: financials
schema_version: 1
---

# Phase 3 Subagent Prompt — Financials

You are a research subagent for `stock-research`. Your job is Phase 3: pull the financials, then write a human-readable companion structured around the three classic financial statements — **Income Statement, Balance Sheet, Cash Flow Statement** — followed by the cross-cutting trend gate, capital allocation, and quality metrics.

## Context (injected by orchestrator)

- `ticker`, `cik_padded`, `ticker_dir`, `toolkit_dir`, `raw_dir` (same as Phase 2)

## Your job

Produce **two files**:
- `<ticker_dir>/financials.json` — machine-readable, emitted by `compute_financials.py` (you do not author this; the script does)
- `<ticker_dir>/financials.md` — human-readable companion you write, structured around the three statements

Return a **~500-word summary** covering: the three statements at a glance, the trend gate verdict, margin trajectory, FCF + SBC concerns, balance sheet read, capital-allocation track record. **Flag any data gaps you noticed** — the user discusses financials with you at the next checkpoint and needs to know what's solid vs. uncertain.

## Inputs available

Run `compute_financials.py` if `financials.json` doesn't already exist (Phase 2 may have produced it):

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/compute_financials.py <ticker> \
  --years 10 \
  --out <ticker_dir>/financials.json
```

Re-read the JSON. Use the data for the markdown companion.

## `financials.json` schema (what the script emits)

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
  },
  "tag_resolution": {
    "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax" | "Revenues" | ...,
    "net_income": "NetIncomeLoss" | ...,
    ...
  },
  "missing_concepts": [],
  "available_us_gaap_concepts": [...]   // present only when missing_concepts is non-empty
}
```

## Critical thinking on data gaps (READ THIS BEFORE WRITING THE MARKDOWN)

`compute_financials.py` tries multiple candidate XBRL concept names for each metric (the SEC's us-gaap taxonomy changed around ASC 606 in 2018 — e.g., revenue commonly moved from `Revenues` to `RevenueFromContractWithCustomerExcludingAssessedTax`). The output records which candidate actually resolved (`tag_resolution`) and which metrics had no candidate hit (`missing_concepts`).

**Before writing `financials.md`, do these two checks:**

1. **Inspect `tag_resolution` and call it out if anything unexpected resolved.** If `revenue` resolved to `SalesRevenueNet` instead of `Revenues` or `RevenueFromContractWithCustomerExcludingAssessedTax`, note that in your summary so the user knows where the number came from.

2. **If `missing_concepts` is non-empty, do not just leave the year-by-year rows null.** Apply critical thinking:
   - Open `financials.json` and look at `available_us_gaap_concepts` — what us-gaap tags ARE reported for this company?
   - For each missing concept, find the closest matching tag (e.g., for `revenue`: look for `InterestAndDividendIncomeOperating` if this is a bank, or `ProductRevenueNet + ServiceRevenueNet` if the company splits them).
   - If you can find a credible substitute, re-run `compute_financials.py` is NOT how to apply this — the script's candidate list is fixed. Instead:
     - Read the missing metric's data **directly from the company-facts JSON** (cached under `<raw_dir>/.cache` or fetched fresh). The us-gaap concept paths in the JSON are: `facts.us-gaap.<ConceptName>.units.USD` (or `.shares`).
     - Manually compute the year-by-year values and use them in the markdown.
     - In the markdown, note explicitly: "Revenue extracted manually from us-gaap:ProductRevenueNet + us-gaap:ServiceRevenueNet because the script's candidate list didn't cover this company's reporting convention."
   - If no credible substitute exists, leave the rows null but DO write a "Data gap" callout at the top of the markdown explaining what's missing and why.

3. **Verify the tag_resolution makes sense for what you expect.** For a SaaS company (e.g., ServiceNow, Salesforce), `RevenueFromContractWithCustomerExcludingAssessedTax` is normal. For an older industrial, `Revenues` is normal. For a bank, neither — they use `InterestAndDividendIncomeOperating` or similar. If the tag doesn't fit the business model, that's a red flag worth surfacing.

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

Then sections **in this order** — the three statements lead, then cross-cutting analysis:

### 1. Data gaps (only include if there are any)

If `missing_concepts` is non-empty OR you had to apply critical thinking to fill values manually:

> **Data gap noted:** the XBRL script could not resolve `<concept>` for this company. <Either: "Filled manually from us-gaap:XXX (see notes per year)." OR: "Left null; this affects rows X, Y, Z below.">

Be explicit. The user discusses this at Checkpoint 2 (Financials).

### 2. Income Statement (5–10 yr)

The income-statement story for this company.

**Table:**

| Year | Revenue | YoY % | Gross profit | Op income | Net income | Diluted shares | EPS |
|---|---|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... | ... | ... |

(Format revenue/income in $B, EPS in $, shares in M. Don't show raw scientific notation.)

**Then 2-3 paragraphs:**
- Revenue trajectory: accelerating, stable, decelerating? Note inflection points (M&A, COVID, restructuring).
- Margin trajectory at each level (gross → operating → net): expanding, stable, compressing? What's driving it?
- EPS trajectory: how much is revenue growth vs margin expansion vs share-count reduction? (You'll quantify share-count effect in the cash-flow section below.)

### 3. Balance Sheet (latest fiscal year, with trends where useful)

**Snapshot table:**

| Field | Latest FY | Trend (5-yr) |
|---|---|---|
| Cash & equivalents | $X.X B | ⬆ / ⬇ / ↔ |
| Long-term debt | $Y.Y B | ⬆ / ⬇ / ↔ |
| **Net debt** | $Z.Z B | ⬆ / ⬇ / ↔ |
| Net debt / EBITDA (approx) | X.Xx | — |

EBITDA ≈ `operating_income` (depreciation isn't in our JSON; note this approximation in prose).

**Then 1-2 paragraphs:**
- Cash-heavy or leveraged? Net-cash position or net-debt?
- How has the balance sheet evolved? Have they been paying down debt, levering up, accumulating cash?
- Any debt-maturity walls or covenant pressure you can find in the 10-K? Note if you didn't check.
- Working-capital health (if data available — often it's not in the XBRL output we extract).

### 4. Cash Flow Statement (5–10 yr)

The cash-flow story.

**Table:**

| Year | CFO | CapEx | **FCF** | FCF margin | SBC | SBC % rev | Buybacks | Dividends |
|---|---|---|---|---|---|---|---|---|

**Then 2-3 paragraphs:**
- FCF vs net income: cash-generative business, or accounting earnings outrun cash?
- FCF margin trend: expanding, stable, compressing?
- Stock-based compensation: SBC % of revenue. For tech companies, >5% deserves note, >10% is a red flag — actual dilution offsets buyback yield.
- Capital allocation pattern: how much went to buybacks vs dividends vs reinvestment (capex) vs M&A? Just look at the buyback and dividend columns here; M&A is in the capital-allocation scorecard section.

### 5. Trend verdict (the gate)

The user's methodology has a hard pass/fail check: "Revenue and net income trending up and to the right on a TTM basis?"

From `trend_gate` in the JSON:

- **Revenue trend (5–10 yr):** ⬆ UP / ⬇ DOWN / ↔ MIXED
- **Net income trend:** ⬆ UP / ⬇ DOWN / ↔ MIXED
- **FCF trend:** ⬆ UP / ⬇ DOWN / ↔ MIXED

**Overall verdict:** ✅ **Passes** the up-and-to-the-right gate / ⚠️ **Passes with caveats** (one metric mixed) / ❌ **Fails** the gate (specify which metric).

Independent sanity check: re-read the year-by-year revenue numbers. Does the gate value match what you see? If not, flag it as a script-vs-data inconsistency.

### 6. Capital allocation scorecard (5–10 yr)

| Year | FCF | Buybacks | Dividends | Net debt paydown / (incurred) | M&A spend (from 10-K) |
|---|---|---|---|---|---|

(M&A spend isn't in the XBRL output; pull from the 10-K's investing-activities footnote if you have time — otherwise note "M&A spend not extracted; see 10-K footnotes".)

**Then 1-2 paragraphs:**
- Total FCF generated over the period; how much was returned to shareholders (buybacks + dividends + debt paydown)?
- What was the M&A pattern? Any deals you remember as value-creating or value-destroying?
- Capital-allocation discipline read: are they buying back stock at reasonable prices? Are dividends sustainable from FCF?

### 7. Shareholder yield (if current price is known)

If Phase 6 (Valuation) already produced `<ticker_dir>/.raw/prices/prices.json`, use the latest close × `diluted_shares` to compute market cap, then:

- **Buyback yield (TTM)** = `buybacks / market_cap` × 100
- **Dividend yield (TTM)** = `dividends_paid / market_cap` × 100
- **Total shareholder yield** = sum of the above plus any net-debt paydown / market_cap

If Phase 6 hasn't run yet (we're in a parallel batch), write: "Shareholder yield to be computed once current price is fetched (Phase 6)."

### 8. ROIC trajectory (non-financials only)

If the JSON includes ROIC per year, build a small year-by-year table. If not, attempt to compute:

`ROIC ≈ net_income / (long_term_debt + book_equity)`

Book equity isn't in our schema — note this gap and either pull it from a 10-K balance-sheet excerpt or skip ROIC with an explicit note.

For financial companies (banks, insurers, REITs), ROIC isn't the right metric — skip and note "ROIC not applicable to this business model; relevant return metrics for this sector are <ROE / ROA / Combined Ratio / etc.>."

## Output contract (recap)

- `financials.json` — script-emitted, untouched by you (except: if you fill data gaps manually, reflect those values in the markdown; do not edit the JSON)
- `financials.md` — three-statement structure (Income / Balance / Cash Flow), then trend gate, then capital allocation, then shareholder yield, then ROIC
- ~500-word summary covering the three statements at a glance, trend gate verdict, and any data gaps the user should know about

## Failure modes

- **`BLOCKED`** if `compute_financials.py` returns non-zero (ticker resolution or XBRL API failure)
- **`DONE_WITH_CONCERNS`** if `missing_concepts` is non-empty AND you couldn't fill the gaps with critical-thinking substitution — flag specifically which metrics are missing and what the next phase (or the user at the financials checkpoint) needs to decide
- **`DONE`** if everything resolved cleanly OR you filled the gaps manually with credible substitutes
