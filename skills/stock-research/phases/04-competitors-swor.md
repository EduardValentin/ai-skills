---
artifact: phase-prompt
phase: 4
phase_name: competitors-and-swor
schema_version: 1
---

# Phase 4 Subagent Prompt — Competitors + SWOR (orchestrator)

You are the worker for Phase 4. You fan out to per-competitor workers, then aggregate their results into `competitors.md` and `swor.md`. You also run the risk-factor YoY diff.

## Context (injected by orchestrator)

Same as Phase 2 + 3: `ticker`, `cik_padded`, `ticker_dir`, `scripts_dir`, `raw_dir`, `gvd_category`. Plus:
- `business_and_moat_summary`: the summary returned by Phase 2 (so you know what segments/moat the parent already identified)

## Your job

Produce **three files**:
- `<ticker_dir>/competitors.md` — side-by-side table + per-competitor notes
- `<ticker_dir>/swor.md` — Strengths / Weaknesses / Opportunities / Risks for the company
- `<ticker_dir>/.raw/risk-factor-diff.json` (and `.md`) — YoY diff of the last two 10-K Item 1A sections

Return the Worker Return Contract requested by the top-level orchestrator. Keep the synthesis compact and put top competitors, positioning verdict, SWOR essence, and risk-factor changes in `checkpoint_highlights`.

## Step 1: Identify 3–5 direct competitors

Read `<raw_dir>/10k-sections/item_1_business.md` from Phase 2. The 10-K Item 1 often names competitors directly (especially in the "Competition" subsection). Pull 3–5 names.

If the 10-K doesn't name competitors (common for diversified companies), use the segments + sector to identify the most obvious competitors. For example:
- Apple → Samsung (smartphones), Microsoft + Google (services), Dell + HP (Macs)
- Costco → Walmart (Sam's Club), BJ's, Amazon (membership programs)

Aim for diversity: include both direct competitors and substitution threats where they matter. **Keep the list to 3–5 names.**

## Step 2: Dispatch per-competitor workers in parallel

For each competitor ticker, dispatch a worker using `phases/04-competitor-sub.md` as the prompt. Inject:
- `competitor_ticker`: the competitor's ticker
- `scripts_dir`: same path
- `raw_dir`: `<ticker_dir>/.raw/competitors/<competitor_ticker>/`

Each worker fetches its competitor's financials and returns a comparison row. You wait for all workers to finish before proceeding.

If a competitor isn't on EDGAR (foreign, private, ETF, etc.), the worker reports `NEEDS_CONTEXT`. Drop that competitor from the comparison and note it in `competitors.md` ("no public filings available").

## Step 3: Run the risk-factor YoY diff

If `<raw_dir>/10k-sections/` has Item 1A from the most recent 10-K, also find the prior-year 10-K (it should be in `<raw_dir>` from Phase 2's `fetch_sec.py --since 2y`). Extract its Item 1A:

```bash
prior_tenk=$(ls -t <raw_dir>/*10-K*.html | sed -n '2p')
prior_year=$(echo "$prior_tenk" | grep -oE '[0-9]{4}' | tail -1)
<scripts_dir>/.venv/bin/python <scripts_dir>/extract_10k_sections.py <ticker> \
  --html "$prior_tenk" --year "$prior_year" \
  --out <raw_dir>/10k-sections-prior/
```

Then run the diff:

```bash
<scripts_dir>/.venv/bin/python <scripts_dir>/diff_risk_factors.py \
  --file-a <raw_dir>/10k-sections-prior/item_1a_risk_factors.md \
  --file-b <raw_dir>/10k-sections/item_1a_risk_factors.md \
  --ticker <TICKER> \
  --out <raw_dir>/risk-factor-diff.json \
  --out-md <raw_dir>/risk-factor-diff.md
```

This produces JSON with `added`, `removed`, `modified` paragraphs. You'll use it in Step 5.

## Step 4: Write `competitors.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: competitors
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then:

### Side-by-side table

| Ticker | Name | Market cap | Revenue (TTM) | Rev growth (3-yr CAGR) | Gross margin | Op margin | Net margin | FCF margin | ROIC | P/E (TTM) | Diluted-share growth (3-yr) |
|---|---|---|---|---|---|---|---|---|---|---|---|

Each row is the company we're analyzing (first row, highlight it) and each competitor (returned by the workers). Use the data from each worker's returned contract/artifact.

### Per-competitor notes

For each competitor (3–5), write 3–5 sentences:
- How they overlap with the company's business
- Where they're better / worse on the key metrics
- Any strategic concerns (e.g., "Walmart's e-commerce growth is accelerating into Costco's grocery footprint")

### Competitive positioning summary

Two paragraphs:
1. Where does the company sit in this comparison? Best on which metrics? Worst on which?
2. What's the moat-vs-competitor read? Are they pulling ahead, falling behind, or holding steady?

## Step 5: Write `swor.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: swor
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then four sections:

### Strengths

4–7 bullets. What the company does well. Anchor each to evidence — a margin number, a market-share fact, a moat dimension, a balance-sheet line. **No vague platitudes.**

### Weaknesses

4–7 bullets. What's structurally weak. Same evidence anchoring. Examples: "Single-product concentration: iPhone is 52% of revenue (FY2024)"; "Capital intensity rising — capex grew from 3% of revenue in FY20 to 4.8% in FY24."

### Opportunities

3–5 bullets. Credible growth vectors the company is positioned to capture. Examples: services attach rate; geographic expansion; adjacencies; pricing power runway. Each bullet should be specific enough that you can imagine it in the bull case (Phase 8).

### Risks

5–8 bullets. **Risks framed as "what could break the thesis"**, not abstract external threats. Pull heavily from:
- Item 1A risk factors (from Phase 2's extraction)
- The risk-factor diff (Step 3) — specifically NEW risks added year-over-year (these are the leading-edge signals)
- Competitor moves
- Macro/regulatory exposures

Each bullet should be specific and testable. Examples:
- "China revenue (17% of total) is exposed to trade-policy shocks; the FY24 10-K added a new risk factor about export controls on advanced semis."
- "Services growth depends on App Store economics, which face active antitrust scrutiny (DMA in EU, Epic lawsuit aftermath)."

### Risk-factor YoY diff highlight

A small section (3–5 sentences) calling out what NEW risks the company added in its latest 10-K vs. the prior year. This is the single-best leading indicator that management sees something the market hasn't fully priced. Use `<raw_dir>/risk-factor-diff.md` as source.

## Output contract (recap)

- `competitors.md`, `swor.md`, `.raw/risk-factor-diff.{json,md}`
- Worker Return Contract covering: top competitors named, positioning verdict, SWOR essence, what's new in risk factors

## Failure modes

- **`BLOCKED`** if >50% of competitor workers fail (you can't build a comparison from 1 of 5)
- **`DONE_WITH_CONCERNS`** if:
  - Prior-year 10-K isn't in `<raw_dir>` (some companies are newly public, or fetch failed) — skip the risk diff and note it
  - Some competitor financials are incomplete (e.g., private peer with limited filings)
- **`DONE`** otherwise
