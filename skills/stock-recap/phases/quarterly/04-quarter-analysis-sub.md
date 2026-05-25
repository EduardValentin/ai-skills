---
artifact: phase-prompt
phase: quarterly-4
phase_name: per-quarter-analysis
schema_version: 1
---

# Quarterly Phase 4 Sub-Agent Prompt — Per-Quarter Analysis

You are a sub-agent dispatched by the Quarterly Phase 4 orchestrator. Your job is to analyze ONE quarter's filing + earnings-call transcript, produce the analysis artifact, and return a structured per-quarter "actuals slice" the orchestrator uses to build the cross-quarter diff table.

## Context (injected by the orchestrator)

- `ticker`: ticker symbol.
- `quarter`: `YYYY-Qn`.
- `quarter_end_date`: the period-end date for this quarter (`YYYY-MM-DD`).
- `ticker_dir`: absolute path.
- `toolkit_dir`: absolute path to financial-toolkit.
- `filing_path`: absolute path to the cleaned filing extracts written by Phase 2 (in `.raw/recap-<quarter>/`).
- `transcript_path`: absolute path to the cleaned transcript (`earnings-calls/<quarter>.md`).
- `projection_kpis`: the list of KPI names tracked in `projections.json.scenarios.base.years[N]` (excluding `year`). Example: `["revenue", "revenue_growth_pct", "gross_margin_pct", "operating_margin_pct", "net_income", "fcf", "shares_diluted", "eps", "net_debt", "roic_pct", ...]`.
- `thesis_year_for_quarter`: 1-based index into `projections.json.scenarios.<scenario>.years` that this quarter maps to (a quarter ending ~12 months after thesis creation = thesis-year 1; ~24 months = thesis-year 2; etc.).

## Your job

1. Read the filing extracts + transcript.
2. Write `earnings-calls/<quarter>-analysis.md` with the same shape as `stock-research` Phase 5's per-quarter sub-agent output: prepared-remarks summary, Q&A themes, forward-looking statements, KPI mentions, tone (confidence / hedging / defensiveness).
3. For each KPI in `projection_kpis`, find the actual reported value in the filing (or "not reported this quarter") and compute the TTM-equivalent where applicable. Compare it to the bull / base / bear projection for `thesis_year_for_quarter` and tag the row.
4. Return a structured summary.

## Step 1: Write the per-quarter analysis file

Use this template for `<ticker_dir>/earnings-calls/<quarter>-analysis.md`:

```yaml
---
ticker: <TICKER>
quarter: <quarter>
artifact: earnings-call-analysis
schema_version: 1
---

# <TICKER> — <quarter> earnings call & filing analysis

## Headline numbers

| Metric | Reported | TTM | YoY change |
|---|---|---|---|
| Revenue | $X.XB | $Y.YB | +X.X% |
| Operating income | ... | ... | ... |
| Net income | ... | ... | ... |
| Diluted EPS | $X.XX | $Y.YY | +X.X% |
| FCF | ... | ... | ... |

## Prepared remarks — summary

<3-5 sentences. What management led with. What they emphasized vs prior quarter.>

## Q&A themes

<Bullet list. The top 3-4 themes that came up in analyst questions.>

## Forward-looking statements

<Guidance issued or affirmed. Specific numbers if given.>

## KPI mentions and guidance trajectory

<Any KPI the user is watching (from `watch_kpis.generic` and `watch_kpis.story_custom` in verdict.json) that came up. Note direction vs prior quarter.>

## Tone

<One paragraph. Confidence vs hedging vs defensiveness. Cite specific phrases or moments.>
```

## Step 2: Compute per-quarter actuals slice vs projections

For each KPI in `projection_kpis`:

1. Find the reported value for this quarter in the filing (or note "not reported this quarter" — common for things like `roic_pct` that companies don't disclose quarterly).
2. Where the KPI is a flow metric (`revenue`, `net_income`, `fcf`, etc.), use the TTM ending at `quarter_end_date`; where it's a stock/ratio (`gross_margin_pct`, `shares_diluted`, `net_debt`, etc.), use the spot value at `quarter_end_date`.
3. Read the bull / base / bear projection for `thesis_year_for_quarter` from `projections.json`: `scenarios.<scenario>.years[thesis_year_for_quarter - 1][<kpi>]`. Each scenario carries the full KPI dict per year.
4. Tag the row using the default thresholds (the orchestrator may override these in Phase 5):
   - For revenue / EPS / FCF (absolute or growth %): `ahead` if actual > base + 10%; `behind` if actual < base − 10%; `on-track` otherwise. Compare separately to bull and bear to see which scenario the actual most closely matches.
   - For margins (KPI names ending `_pct`): `ahead` if actual > base + 200bps; `behind` if actual < base − 200bps; `on-track` otherwise.
   - For other KPIs (story-custom): `ahead` if > base + 15%; `behind` if < base − 15%; `on-track` otherwise.
   - `cannot-evaluate` if the actual is "not reported this quarter" or if the saved projection has no value for `thesis_year_for_quarter` for this KPI.

## Step 3: Return summary

```
QUARTER: <quarter>
ANALYSIS_FILE: <ticker_dir>/earnings-calls/<quarter>-analysis.md
HEADLINE_TONE: <confident | mixed | hedging | defensive>
GUIDANCE_DIRECTION: <raised | maintained | lowered | no-guidance>
ACTUALS_VS_PROJECTIONS:
  - revenue: actual=$X.XB | base=$Y.YB | tag=on-track | closest-scenario=base
  - operating_margin_pct: actual=22.4 | base=23.0 | tag=on-track | closest-scenario=base
  - eps: actual=$1.45 | base=$1.62 | tag=behind | closest-scenario=bear
  - <... one row per projection_kpi>
SCENARIO_LANDING: <which of bull/base/bear this quarter most closely matches across the majority of metrics, with a 1-sentence justification>
NOTES: <one sentence on anything unusual or unique to this quarter>
STATUS: <DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT>
```

`STATUS` is `NEEDS_CONTEXT` if the filing or transcript file at the injected paths is missing or unreadable (the orchestrator handles re-fetch); `DONE_WITH_CONCERNS` if some KPIs couldn't be resolved (tag = `cannot-evaluate` for >25% of `projection_kpis`); `DONE` otherwise.
