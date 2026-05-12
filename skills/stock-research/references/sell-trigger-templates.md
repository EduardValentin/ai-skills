---
artifact: reference
purpose: How to write thesis-broken sell triggers in Phase 9 verdict
schema_version: 1
---

# Sell Triggers

The user's methodology has three exit conditions. Phase 9 encodes the first two as concrete, measurable, KPI-tied thresholds at verdict time. These get auto-checked by the future `stock-recap` skill each quarter.

## Sell condition 1: Materially overvalued

Pick one or both:

- **Bull-case overshoot:** "Sell if price exceeds bull-case Y5 fair value, i.e., **$X**" (use the bull case's `share_price_high_y5` from `projections.json`).
- **Reverse-DCF overshoot:** "Sell if reverse-DCF-implied growth at current price exceeds **N%**" (a number the agent picks based on what's plausible for the bucket — for a quality-growth name, ~15% might be the line; for a speculative name, ~25%).

## Sell condition 2: Thesis broken

**3–5 named KPI breach conditions**, story-dependent. The list MUST be specific, measurable, and tied to actual financials. Each trigger is a one-sentence rule that can be auto-evaluated against quarterly data by `stock-recap`.

### Good triggers (specific, measurable)

- "Revenue growth falls below 10% YoY for two consecutive quarters"
- "Gross margin compresses below 65%"
- "Net dollar retention drops below 110%"
- "Customer concentration exceeds 25% from any single client"
- "FCF/dividend coverage falls below 1.1× for two consecutive quarters" (dividend names)
- "Cash burn extends runway below 18 months without raising capital" (speculative names)
- "Capex intensity exceeds 15% of revenue for two consecutive years" (typical capital-light name turning capital-heavy)

### Bad triggers (vague, unmeasurable)

- "Sell if the moat weakens" — what does that mean numerically?
- "Sell if management makes bad decisions" — define "bad"
- "Sell if growth slows" — by how much, over what period?

## Sell condition 3: Better opportunity

Not pre-definable; the framework leaves room. The verdict notes this as: "Sell if a clearly better opportunity emerges (higher conviction, more favorable bull/base asymmetry, better margin of safety) — judged at portfolio level."

## Output format

In `verdict.md`, the Sell Triggers section reads:

```
## 7. Sell triggers

### Materially overvalued
- Bull-case overshoot: $X
- Reverse-DCF overshoot: implied growth > N%

### Thesis broken (any one triggers re-evaluation)
1. Revenue growth < 10% YoY for 2 consecutive quarters
2. Gross margin < 65%
3. ...
4. ...
5. ...

### Better opportunity
- Re-evaluated quarterly against the rest of the portfolio.
```

In `verdict.json`, the same data lives under `sell_triggers.materially_overvalued` (array) and `sell_triggers.thesis_broken` (array of strings).
