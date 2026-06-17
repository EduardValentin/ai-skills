---
artifact: phase-prompt
phase: 5
phase_name: earnings-calls
schema_version: 1
---

# Phase 5 Subagent Prompt — Earnings Calls (orchestrator)

You orchestrate Phase 5: fetch the last 3 quarterly earnings call transcripts, dispatch a worker per quarter for analysis, then aggregate cross-call themes.

## Context (injected by orchestrator)

Standard: `ticker`, `cik_padded`, `ticker_dir`, `scripts_dir`, `raw_dir`. Plus:
- `company_slug`: lowercase company name used for Motley Fool URLs (e.g., "apple", "microsoft"). The orchestrator passes its best guess; you can override via inspection of the IR page if the scraper fails.

## Your job

Produce these files in `<ticker_dir>/earnings-calls/`:
- `<YYYY-Qn>.md` per quarter (cleaned transcript) — 3 files
- `<YYYY-Qn>-analysis.md` per quarter (your analysis) — 3 files (produced by workers)
- `cross-call-themes.md` (you write this, aggregating across the 3)

Return the Worker Return Contract requested by the top-level orchestrator. Keep the synthesis compact and put tone trajectory, dropped/added themes, key forward-looking guidance, and anything Checkpoint 3 should surface in `checkpoint_highlights`.

## Step 1: Determine the 3 quarters to fetch

Today's date - 9 months back, rounded to the most recent reporting quarter, gives the oldest of the 3. Then the 2 most recent quarters.

Reporting calendars vary by company. A safe default:
- Pull the company's filing history: `<raw_dir>/_filings_index.json` (from Phase 2's `fetch_sec.py`)
- Find the 3 most recent 10-Qs (or 10-K + 2 10-Qs if the most recent reporting period was the fiscal year)
- Each 10-Q's `report_date` tells you which quarter it is

Convert to `YYYY-Qn` labels (e.g., a 10-Q with report_date `2024-06-29` for Apple = `2024-Q3` because Apple's fiscal year ends in September).

**Be careful with fiscal-year offsets.** Most US companies use calendar quarters (Q1 = Jan-Mar, Q4 = Oct-Dec). Some don't — Apple's FY ends in September, so its Q3 reports cover April-June. Walmart's FY ends Jan 31, so its Q4 reports cover Nov-Jan. Pick the convention the company itself uses (you can usually see it in their press releases).

## Step 2: Dispatch workers in parallel (one per quarter)

For each of the 3 quarters, dispatch a worker using `phases/05-earnings-call-sub.md`. Inject:
- `quarter_label`: `YYYY-Qn`
- `ticker`, `company_slug`, `scripts_dir`
- `out_dir`: `<ticker_dir>/earnings-calls/`

Wait for all 3 to complete. Each writes its own `<quarter_label>.md` (transcript) and `<quarter_label>-analysis.md`, and returns a compact summary covering: tone, prepared-remarks highlights, Q&A themes, guidance.

If a worker returns `NEEDS_CONTEXT` (transcript not findable), the orchestrator pauses and asks the user to paste it inline — see Failure Modes.

## Step 3: Write `cross-call-themes.md`

Read all 3 analysis files (or the returned summaries). Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: cross-call-themes
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
quarters_covered: [<Q1>, <Q2>, <Q3>]
---
```

Then sections:

### 1. Tone trajectory

Across the 3 calls, has management's tone shifted? Categories:
- Confidence (e.g., "we're very bullish on..." → "we're cautiously optimistic about...")
- Hedging language (rare → frequent = bad sign)
- Defensiveness in Q&A (more deflecting / fewer specifics = bad sign)
- Specificity (more granular guidance = good; vague aspirations = bad)

Write 2–3 paragraphs describing the trajectory with quotes / paraphrases from specific calls.

### 2. Themes that emerged or dropped

What did management start talking about? What stopped being mentioned?

Examples:
- **Emerged:** "AI" was mentioned 12× in the most recent call vs 2× three calls ago.
- **Dropped:** "Foldable phones" disappeared after Q1 — strategy change?

A short list of 4–8 bullets, each with a quick "good / bad / neutral" tag.

### 3. Guidance trajectory

Find each call's forward guidance (revenue, margin, capex, etc.) and tabulate:

| Quarter | Revenue guide (next quarter) | Margin guide | Capex guide |
|---|---|---|---|
| ... | ... | ... | ... |

Are they raising / lowering / holding guidance? Note any "we don't give guidance" patterns or any one-time changes.

### 4. KPI mentions

If management mentions specific operational KPIs (customer count, ARPU, store count, capacity utilization, take rate, etc.), list them across the 3 calls in a small table — same KPI mentioned each time with its values. This becomes a candidate watchlist for Phase 9.

### 5. What to surface at Checkpoint 2

A short "things worth discussing at Checkpoint 2" list — 3–5 items that you think the user should weigh in on before projections. Examples:
- "Mgmt is suddenly cautious about Q1 next year — they didn't explain why. Worth pressing."
- "AI capex is doubling but they haven't shown the revenue contribution. Bull case has to assume this pays off."

## Output contract (recap)

- 3 transcript files + 3 analysis files + 1 cross-call-themes file
- Worker Return Contract with compact call-trajectory highlights

## Failure modes

- **`NEEDS_CONTEXT`** if any worker returns `NEEDS_CONTEXT` (transcript not found by scraper and no manual paste yet). The orchestrator handles this by pausing to ask the user to paste the missing transcript before re-dispatching that single worker. You report this status to the main orchestrator so it can drive the user interaction.
- **`DONE_WITH_CONCERNS`** if guidance comparison is incomplete (e.g., company doesn't give forward guidance — many don't)
- **`DONE`** otherwise
