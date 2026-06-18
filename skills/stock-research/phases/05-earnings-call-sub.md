---
artifact: phase-prompt
phase: 5-sub
phase_name: per-quarter-call-analysis
schema_version: 1
---

# Phase 5 Sub-subagent Prompt — Per-Quarter Earnings Call Analysis

You handle one quarter's earnings call. Fetch the transcript, clean it, write an analysis.

## Context (injected by Phase 5 orchestrator)

- `quarter_label`: `YYYY-Qn` (e.g., `2024-Q3`)
- `ticker`: parent ticker (e.g., `AAPL`)
- `company_slug`: best-guess slug for Motley Fool URLs
- `toolkit_dir`, `out_dir` (= `<ticker_dir>/earnings-calls/`)

## Your job

Produce two files in `<out_dir>/`:
- `<quarter_label>.md` — cleaned transcript with frontmatter
- `<quarter_label>-analysis.md` — your structured analysis

Return a **~500-word summary**: tone read, key prepared-remarks points, top 2–3 Q&A themes, forward guidance.

## Step 1: Fetch the transcript

```bash
<toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_transcript.py <ticker> \
  --quarter <quarter_label> \
  --company-slug <company_slug> \
  --out <out_dir>
```

This produces `<out_dir>/<quarter_label>.md` with the cleaned transcript (Motley Fool scrape).

If the script exits 3 (no source available), return status `NEEDS_CONTEXT` with this message:
```
Transcript not found via scraper for <ticker> <quarter_label>. Please paste the transcript inline. Orchestrator will re-dispatch with the pasted content.
```

The Phase 5 orchestrator handles user paste and re-dispatches with `--manual` mode. Your re-dispatch will receive the transcript via stdin; pass `--manual` to `fetch_transcript.py` and pipe stdin through:

```bash
echo "$pasted_transcript" | <toolkit_dir>/.venv/bin/python <toolkit_dir>/fetch_transcript.py <ticker> \
  --quarter <quarter_label> \
  --manual \
  --out <out_dir>
```

## Step 2: Read the transcript

Read `<out_dir>/<quarter_label>.md`. The frontmatter is already there; the body is the cleaned transcript with section headers like:
- Prepared Remarks (CEO, CFO, etc. each have their part)
- Q&A (analyst-by-analyst exchanges)

## Step 3: Write `<out_dir>/<quarter_label>-analysis.md`

Frontmatter:

```yaml
---
ticker: <TICKER>
artifact: earnings-call-analysis
quarter: <quarter_label>
session: initial-research
date: <YYYY-MM-DD>
schema_version: 1
---
```

Then sections:

### 1. Prepared remarks summary

3–6 paragraphs covering:
- Topline numbers cited (revenue, EPS, segment performance)
- Strategic announcements (new products, acquisitions, capital returns, leadership changes)
- Reasons given for outperformance / underperformance vs expectations
- Forward-looking commentary

### 2. Q&A themes

3–5 themes that came up in Q&A. For each:
- The question (paraphrased)
- The answer (paraphrased — specificity vs evasion matters)
- Your read: does the answer satisfy the question? Does it dodge?

### 3. Forward-looking statements

A bullet list of every concrete forward statement: guidance numbers, capex plans, hiring plans, geographic expansion plans, product launches, etc. Be specific — "we expect H2 to be strong" is not concrete; "we expect operating margin to expand 100bps in H2" is.

### 4. KPI mentions

Operational KPIs management cited (customer count, units sold, ARPU, etc.). List them with their values. These feed the Phase 5 orchestrator's cross-call KPI table.

### 5. Tone

A 1-paragraph qualitative read:
- Confidence (high / medium / low / declining)
- Hedging (use of "uncertainty", "challenges", "headwinds")
- Q&A defensiveness (deflecting questions, repeating talking points)
- Use of specific language (numbers, dates) vs vague aspirations

### 6. Net read

1 paragraph: what did THIS call tell you that you didn't know before? Worth flagging to the parent orchestrator for Checkpoint 2?

## Output contract (recap)

- 2 files (`<quarter_label>.md` transcript + `<quarter_label>-analysis.md`)
- ~500-word summary

## Failure modes

- **`NEEDS_CONTEXT`** if `fetch_transcript.py` exit code 3 (covered above)
- **`DONE_WITH_CONCERNS`** if transcript is heavily truncated or has obvious parse errors (e.g., paragraphs cut mid-sentence) — note it
- **`DONE`** otherwise
